"""Mise a jour automatisee du corpus des programmes 2027.

Enchaine : git pull du depot amont -> collecte (rafraichissement) -> relecture locale -> plan chiffre ->
(sur autorisation de budget) OCR -> extraction avec relances reseau -> export -> bilan qualite.

Sans --max-cost, rien de payant n'est lance : le script s'arrete apres le plan et son estimation de cout.
Les etapes sont celles de programme_corpus_2027.py (cache par empreinte, reprise sans repayer).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import programme_corpus_2027 as pc
from llm_logging_2027 import LLMJournal

DEFAULT_COST_PER_CALL = 0.004  # mesure : ~0,0035 $/morceau avec Haiku 5.5 ; marge de securite
OUTLIER_FACTOR = 2.5


def budget_calls(max_cost: float, spent: float, cost_per_call: float) -> int:
    """Nombre d'appels que le budget restant autorise (0 si epuise)."""
    if max_cost <= 0 or cost_per_call <= 0:
        return 0
    return max(0, int((max_cost - spent) / cost_per_call + 1e-9))


def journal_cost(path: Path) -> float:
    """Cout reel (usage.cost des reponses) cumule dans un journal JSONL."""
    total = 0.0
    if not path.exists():
        return total
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            usage = (json.loads(line).get("response") or {}).get("usage") or {}
        except (ValueError, AttributeError):
            continue
        total += float(usage.get("cost") or 0)
    return total


def pending_ocr_pages(root: Path, manifest: dict[str, Any], doc_ids: list[str], engine: str) -> int:
    pending = 0
    for doc_id in doc_ids:
        doc = manifest["documents"][doc_id]
        for page in doc.get("text_incomplete_pages", []):
            key = pc.digest({"version": 1, "content_hash": doc["content_hash"], "page": page, "engine": engine})
            if not pc.corpus_path(root, str(Path("ocr") / f"{key}.json")).exists():
                pending += 1
    return pending


def pending_chunks(root: Path, manifest: dict[str, Any], doc_ids: list[str], themes: dict[str, str],
                   model: str) -> Counter:
    """Morceaux sans extraction en cache, par candidat (sans appel, sans journal)."""
    pending: Counter = Counter()
    for doc_id in doc_ids:
        doc = manifest["documents"][doc_id]
        if doc.get("status") != "ready":
            continue
        document = json.loads(pc.corpus_path(root, doc["text_path"]).read_text(encoding="utf-8"))
        for chunk in pc.document_chunks(document):
            key = pc.extraction_key(doc, chunk, model, themes)
            if not pc.corpus_path(root, str(Path("extractions") / f"{key}.json")).exists():
                for candidate in {b["candidate_id"] for b in doc["bindings"]}:
                    pending[candidate] += 1
    return pending


def git_pull(repo_dir: Path) -> str:
    """Met a jour le clone amont en avance rapide ; renvoie un resume."""
    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True, check=False)
        if done.returncode:
            raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip() or done.stdout.strip()}")
        return done.stdout.strip()
    before = git("rev-parse", "HEAD")
    git("pull", "--ff-only", "origin", "main")
    after = git("rev-parse", "HEAD")
    return "depot amont deja a jour" if before == after else f"depot amont mis a jour {before[:7]} -> {after[:7]}"


def quality_report(root: Path, manifest: dict[str, Any], doc_ids: list[str]) -> list[str]:
    """Bilan par candidat avec alertes sur les densites aberrantes (propositions par morceau)."""
    stats: dict[str, dict[str, int]] = {}
    for doc_id in doc_ids:
        doc = manifest["documents"][doc_id]
        for chunk in (doc.get("extraction") or {}).get("chunks", []):
            if chunk.get("status") != "ready":
                for candidate in {b["candidate_id"] for b in doc["bindings"]}:
                    stats.setdefault(candidate, Counter())["erreurs"] += 1
                continue
            record = json.loads(pc.corpus_path(root, chunk["path"]).read_text(encoding="utf-8"))
            for candidate in {b["candidate_id"] for b in doc["bindings"]}:
                s = stats.setdefault(candidate, Counter())
                s["morceaux"] += 1
                s["propositions"] += len(record["proposals"])
                s["vides"] += not record["proposals"]
                s["ecartees"] += len(record.get("rejected_proposals", []))
    densities = {c: s["propositions"] / s["morceaux"] for c, s in stats.items() if s["morceaux"]}
    median = statistics.median(densities.values()) if densities else 0
    lines = [f"{'candidat':<15}{'morceaux':>9}{'propos.':>9}{'par morc.':>10}{'vides':>7}{'ecart.':>7}{'erreurs':>8}"]
    for candidate in sorted(stats):
        s = stats[candidate]
        density = densities.get(candidate, 0)
        alert = ""
        if median and density > OUTLIER_FACTOR * median:
            alert = "  ALERTE densite elevee (biais possible au scoring)"
        elif median and density < median / OUTLIER_FACTOR:
            alert = "  ALERTE densite faible (extraction a verifier)"
        if s["erreurs"]:
            alert += "  ERREURS d'extraction"
        lines.append(f"{candidate:<15}{s['morceaux']:>9}{s['propositions']:>9}{density:>10.1f}"
                     f"{s['vides']:>7}{s['ecartees']:>7}{s['erreurs']:>8}{alert}")
    return lines


def run(args: argparse.Namespace, transformer=None, resume: dict[str, Any] | None = None) -> int:
    """transformer(data) -> data : modifie les donnees amont (sources ajoutees) ; resume : rempli avec cout et compteurs."""
    from pipeline_scoring_2027 import ingest_json, is_openrouter_jev_model, load_env_file
    load_env_file(Path(__file__).with_name(".env"))
    model = (args.model or os.getenv("OPENROUTER_WEB_MODEL", "")).strip()
    if not model or model.endswith(":online") or is_openrouter_jev_model(model):
        raise ValueError("Definir OPENROUTER_WEB_MODEL (ou --model) : modele chat sans :online, pas Jev Decisions.")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if args.max_cost > 0 and not key:
        raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")

    if not args.no_pull:
        print("1/6", git_pull(args.repo_dir))
    data = ingest_json(args.repo_dir / "public-data" / "data-v2.json")
    if transformer:
        data = transformer(data)
    themes = {str(t["id"]): str(t.get("label", t["id"])) for t in data.get("themes", [])}
    if not themes:
        raise ValueError("Themes normalises manquants dans la source.")
    root = args.corpus_dir
    manifest = pc.load_manifest(root)
    replace_urls, exclude_urls = pc.load_source_overrides(args.sources_file)
    known = {i: d.get("content_hash") for i, d in manifest["documents"].items()}
    doc_ids = pc.inventory(data, manifest, args.candidate, replace_urls, exclude_urls)
    pc.save_json(root / "manifest.json", manifest)

    print(f"2/6 collecte ({len(doc_ids)} documents, controle des documents verifies depuis plus de {args.max_age_days} j)")
    pc.collect(root, manifest, doc_ids, refresh=args.force_refresh, max_age_days=args.max_age_days,
               max_bytes=args.max_download_mib * 1024 * 1024)
    reparse = pc.reparse_local(root, manifest, doc_ids)
    new = [i for i in doc_ids if i not in known]
    changed = [i for i in doc_ids if i in known and known[i] != manifest["documents"][i].get("content_hash")]
    unavailable = [i for i in doc_ids if manifest["documents"][i].get("status") != "ready"]
    print(f"   nouveaux: {len(new)}, modifies: {len(changed)}, indisponibles: {len(unavailable)}, "
          f"relecture locale: {reparse['reparsed']} (echecs {reparse['failed']})")
    for i in unavailable:
        d = manifest["documents"][i]
        print(f"   A TRAITER ({d.get('status')}): {d['url']} - {d.get('error')} "
              "(corriger via sources_surcharges.json si lien mort ou hors programme)")

    ocr_pending = pending_ocr_pages(root, manifest, doc_ids, args.pdf_engine)
    chunk_pending = pending_chunks(root, manifest, doc_ids, themes, model)
    total_chunks = sum(chunk_pending.values())
    estimate = (ocr_pending + total_chunks) * args.cost_per_call
    print(f"3/6 plan: {ocr_pending} pages OCR + {total_chunks} morceaux a extraire (modele {model}) "
          f"~ {estimate:.2f} $ (estimation a {args.cost_per_call} $/appel)")
    for candidate, n in sorted(chunk_pending.items()):
        print(f"   {candidate}: {n} morceaux")

    spent = 0.0
    journal = None
    failed = False
    try:
        if args.max_cost <= 0:
            print("Aucun appel payant lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
        elif ocr_pending or total_chunks:
            journal = LLMJournal(secrets=(key,))
            print(f"Journal: {journal.path}")
            if ocr_pending:
                calls = min(ocr_pending, budget_calls(args.max_cost, spent, args.cost_per_call))
                print(f"4/6 OCR: plafond {calls} appels")
                counts = pc.ocr_pages(root, manifest, doc_ids, model, key, calls, args.pdf_engine, journal)
                print("   ", json.dumps(counts))
                spent = journal_cost(journal.path)
                chunk_pending = pending_chunks(root, manifest, doc_ids, themes, model)
            for attempt in range(args.retries + 1):
                calls = budget_calls(args.max_cost, spent, args.cost_per_call)
                if not calls:
                    print("   budget epuise : extraction interrompue (reprise possible, le cache est conserve).")
                    failed = True
                    break
                print(f"5/6 extraction (essai {attempt + 1}/{args.retries + 1}): plafond {calls} appels")
                counts = pc.extract_proposals(root, manifest, doc_ids, themes, model, key, calls, journal,
                                              max_tokens=args.max_tokens)
                print("   ", json.dumps(counts))
                spent = journal_cost(journal.path)
                failed = bool(counts["failed_chunks"] or counts["deferred_chunks"] or counts["unavailable_documents"])
                if not counts["failed_chunks"]:
                    break
                time.sleep(args.retry_wait * 2 ** attempt)
            print(f"   cout reel ~ {spent:.3f} $ sur un budget de {args.max_cost} $")
    finally:
        if journal:
            journal.close()

    if resume is not None:
        resume.update(cout=round(spent, 4), nouveaux=new, modifies=changed, indisponibles=unavailable, doc_ids=doc_ids,
                      estimation=round(estimate, 4), ocr=ocr_pending, morceaux=total_chunks, echec=failed)
    print("6/6 export (partiel autorise : les pages sans texte sont listees par document)")
    result = pc.export_proposals(root, manifest, doc_ids, data, True, replace_urls, exclude_urls)
    pc.save_json(args.out, result)
    print(f"   {len(result['proposals'])} propositions sourcees -> {args.out}")
    print("\nBilan qualite")
    for line in quality_report(root, manifest, doc_ids):
        print(line)
    return 2 if failed or unavailable else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", type=Path, default=Path("upstream_repo"))
    parser.add_argument("--corpus-dir", type=Path, default=Path("corpus_programmes"))
    parser.add_argument("--sources-file", type=Path, default=Path("donnees/sources_surcharges.json"))
    parser.add_argument("--out", type=Path, default=Path("donnees/propositions_programmes_2027.json"))
    parser.add_argument("--candidate", action="append", default=[], help="Limiter a un candidat (repetable)")
    parser.add_argument("--model", help="Defaut: OPENROUTER_WEB_MODEL du .env")
    parser.add_argument("--max-cost", type=float, default=0.0,
                        help="Budget en dollars partage par l'OCR et l'extraction ; 0 = plan seul (defaut)")
    parser.add_argument("--cost-per-call", type=float, default=DEFAULT_COST_PER_CALL)
    parser.add_argument("--retries", type=int, default=3, help="Relances apres erreurs reseau (defaut: 3)")
    parser.add_argument("--retry-wait", type=float, default=15.0, help="Attente initiale en secondes, doublee a chaque essai")
    parser.add_argument("--max-tokens", type=int, default=32768)
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="Ne revérifie que les documents controles depuis plus de N jours (defaut: 7)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Revérifie tous les documents sans tenir compte de l'age (lent: ~6 s par page web)")
    parser.add_argument("--max-download-mib", type=int, default=50)
    parser.add_argument("--pdf-engine", choices=("mistral-ocr", "cloudflare-ai"), default="mistral-ocr")
    parser.add_argument("--no-pull", action="store_true", help="Ne pas mettre a jour upstream_repo")
    args = parser.parse_args()
    try:
        if args.max_cost < 0 or args.retries < 0 or args.max_age_days < 1:
            raise ValueError("Options invalides: budget et relances positifs, age superieur a zero.")
        return run(args)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur mise a jour: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
