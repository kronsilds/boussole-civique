"""Seconde lecture des notes Jev a confiance basse par un modele chat, a l'aveugle, avec note d'audit.

Entree : sortie du pipeline Jev (ex. donnees_programmes_2027.json). Pour chaque proposition, les dimensions signalees
par la file de revision (seuil --threshold) et revisables sont relues. Le modele ne voit ni le candidat ni la note Jev :
c'est une lecture independante. La valeur revisee remplace la note Jev, qui reste dans score_details (jev_value,
jev_confidence). Un ecart fort entre les deux lectures est signale pour relecture humaine (revision.disagreements).
L'ideologie et les tags deduits sont recalcules apres revision. Pas de recherche web (elle revelerait le candidat).

File restante : une note revisee qui concorde avec Jev est confirmee ; seules restent les divergences (et les notes
non revisees). La confiance declaree par le modele chat n'est pas calibree et ne sert pas de critere.

Sans --max-cost, plan seul (aucun appel). Cache par proposition, dimensions et modele : relancer ne repaie rien.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
from axes_2027 import BudgetExhausted, blind_item, blind_names
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import (AXES_DIMENSIONS, DIMENSIONS, dimension_value, digest, number, request_json,
                                  review_issues, review_queue, set_dimension, update_importance)
from update_corpus_2027 import journal_cost

INSTRUCTION_VERSION = 1
DEFAULT_COST_PER_CALL = 0.003
REVIEWABLE = ("feasibility", "rights_income", "rights_status", "eco", "soc", "sov", "ouverture", "ecolo", "income_direction",
              "rupture", "legal_instrument")  # horizon : indicatif, non revise
# Instrument juridique : seule une divergence de classe compte (loi ordinaire / loi de finances n'en est pas une).
INSTRUMENT_CLASSES = {"decret_ou_arrete": "executif", "loi_ordinaire": "loi", "loi_de_finances_ou_securite_sociale": "loi",
                      "loi_organique": "loi", "revision_constitutionnelle": "constitution_ou_traite",
                      "traite_europeen_ou_international": "constitution_ou_traite", "non_identifiable": "non_identifiable"}
GATES = {"feasibility": "has_feasibility", "rights_income": "has_rights_income", "rights_status": "has_rights_status",
         "income_direction": "has_rights_income", "eco": "has_eco", "soc": "has_soc", "sov": "has_sov",
         "ouverture": "has_ouverture",
         "ecolo": "has_ecolo"}
DISAGREEMENT_SHARE = .25  # ecart > 25 % de l'etendue de l'echelle (50 pts sur -100..100, 25 pts sur 0..100)
# Seconde lecture « non applicable » face a une note Jev : tranche en faveur de la seconde lecture, sans relecture humaine.
# Arbitrage aveugle du 2026-11-05 (323 couples) : la seconde lecture a raison dans 96 % (arbitre Claude) et 94 % (GPT-6.1
# Terra) de ces cas ; Jev note l'economie ou les moeurs de mesures qui n'en relevent pas. Faisabilite exclue (null = vague).
RESOLVE_NOT_APPLICABLE = frozenset(GATES) - {"feasibility"}
# Anciennes definitions des questions d'applicabilite (avant le 2026-11-05) : les relectures deja payees avec ces
# definitions restent reutilisables (actif par defaut, --no-legacy-cache pour l'ignorer). has_eco incluait le simple
# cout (« depense publique ») ; les notes eco concernees hors themes economiques sont relues par relecture_ciblee_2027.py.
LEGACY_GATE_INSTRUCTIONS = {
    "has_eco": "La mesure dans `title` et `description` a-t-elle une dimension économique identifiable : répartition des "
               "revenus ou du patrimoine, fiscalité, dépense publique, rôle de l'État ou du marché, droit du travail ?",
}

REVIEW_INSTRUCTIONS = (
    "Tu relis, sans connaitre leur auteur, des propositions de programmes politiques dont une premiere notation "
    "automatique est incertaine. Ne cherche pas a deviner le candidat et n'utilise aucune connaissance sur les partis. "
    "Pour chaque proposition (theme, title, description, quote), note uniquement les dimensions listees dans son champ "
    "`dimensions`, selon le bareme `rubric` :\n"
    "- echelle (`range` et `anchors`) : un entier dans la plage, en t'appuyant sur les ancres (interpolation permise) ;\n"
    "- choix (`options`) : exactement une des cles ;\n"
    "- null si la dimension ne s'applique pas a la mesure (voir `applies_if`) ; pour la faisabilite, null si le texte "
    "est trop vague pour la juger.\n"
    "Donne pour chaque dimension une confiance entre 0 et 1 (probabilite que ta note soit la bonne a un ancre pres), "
    "puis une note d'audit de 220 caracteres maximum qui justifie les notes les plus discutables.\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"dimension\": "
    "{\"value\": ..., \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu, sans autre texte."
)


def dimension_range(dimension: str) -> tuple[Any, Any]:
    return AXES_DIMENSIONS.get(dimension) or DIMENSIONS[dimension]


def rubric(dimensions: list[str], legacy: bool = False) -> dict[str, Any]:
    """Bareme envoye au modele, tire des questions Jev (memes definitions pour les deux lectures).

    legacy=True : anciennes definitions d'applicabilite, seulement pour retrouver les cles du cache deja paye.
    """
    out: dict[str, Any] = {}
    for dim in dimensions:
        question = ps.TYPESAFE_QUESTIONS[dim]
        entry: dict[str, Any] = {"question": question["instructions"]}
        if question["type"] == "choice":
            entry["options"] = question["criteria"]
        else:
            lo, hi = dimension_range(dim)
            levels = question["criteria"]
            entry["range"] = [lo, hi]
            entry["anchors"] = {str(round(lo + i * (hi - lo) / (len(levels) - 1))): label for i, label in enumerate(levels)}
        if dim in GATES:
            gate = GATES[dim]
            entry["applies_if"] = (LEGACY_GATE_INSTRUCTIONS.get(gate) if legacy else None) or ps.TYPESAFE_QUESTIONS[gate]["instructions"]
        out[dim] = entry
    return out


def dimensions_to_review(proposal: dict[str, Any], threshold: float) -> list[str]:
    return sorted({i["dimension"] for i in review_issues(proposal, threshold) if i["dimension"] in REVIEWABLE},
                  key=REVIEWABLE.index)


def cache_key(model: str, item: dict[str, Any], legacy: bool = False) -> str:
    return digest({"v": INSTRUCTION_VERSION, "model": model, "item": item, "rubric": rubric(item["dimensions"], legacy)})


def cached_review(cache: dict[str, Any], model: str, item: dict[str, Any], legacy: bool) -> tuple[Any, bool]:
    """(relecture en cache ou None, vrai si retrouvee sous l'ancienne definition)."""
    key = cache_key(model, item)
    if key in cache:
        return cache[key], False
    if legacy:
        old = cache_key(model, item, legacy=True)
        if old != key and old in cache:
            return cache[old], True
    return None, False


def parse_reviews(content: Any, batch: list[dict[str, Any]], dropped: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Analyse tolerante : une dimension ou une proposition invalide est ecartee (elle reste en file), le reste est garde.

    Leve une erreur seulement si la reponse est illisible ou ne contient aucune proposition valide.
    """
    parsed = pc.parse_json_object(content, "Revision")
    items = parsed.get("reviews")
    if isinstance(items, dict):  # variante {"reviews": {id: {...}}}
        items = [{"id": k, **v} for k, v in items.items() if isinstance(v, dict)]
    if not isinstance(items, list):
        raise ValueError("Reponse de revision invalide: objet {'reviews': [...]} attendu.")
    dropped = dropped if dropped is not None else {}
    wanted = {i["id"]: i["dimensions"] for i in batch}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in wanted or item["id"] in result:
            dropped["proposals"] = dropped.get("proposals", 0) + 1
            continue
        assessments = item.get("assessments") if isinstance(item.get("assessments"), dict) else {}
        note = item.get("note")
        clean: dict[str, dict[str, Any]] = {}
        # Dimension omise ou invalide : la note Jev reste en file ; dimension non demandee : ignoree.
        for dim in wanted[item["id"]]:
            a = assessments.get(dim)
            try:
                if not isinstance(a, dict) or "value" not in a or "confidence" not in a:
                    raise ValueError("value et confidence requis")
                value, conf = a["value"], a["confidence"]
                if isinstance(conf, bool) or not number(conf) or not 0 <= conf <= 1:
                    raise ValueError("confiance entre 0 et 1 attendue")
                if value is not None:
                    if dim in ps.JEV_CHOICE_AXES:
                        if value not in ps.TYPESAFE_QUESTIONS[dim]["criteria"]:
                            raise ValueError("option inconnue")
                    else:
                        lo, hi = dimension_range(dim)
                        if isinstance(value, bool) or not number(value) or not lo <= value <= hi:
                            raise ValueError("valeur hors plage")
                        value = round(value)
            except ValueError:
                dropped["dimensions"] = dropped.get("dimensions", 0) + 1
                continue
            clean[dim] = {"value": value, "confidence": round(float(conf), 2)}
        if not clean or not isinstance(note, str) or not note.strip():
            dropped["proposals"] = dropped.get("proposals", 0) + 1
            continue
        result[item["id"]] = {"assessments": clean, "note": note.strip()[:220]}
    if not result:
        raise ValueError("Aucune revision valide dans la reponse.")
    return result


def disagrees(dim: str, before: Any, after: Any) -> bool:
    if (before is None) != (after is None):
        return True
    if before is None:
        return False
    if dim == "legal_instrument":
        return INSTRUMENT_CLASSES.get(before, before) != INSTRUMENT_CLASSES.get(after, after)
    if dim in ps.JEV_CHOICE_AXES:
        return before != after
    lo, hi = dimension_range(dim)
    return abs(after - before) > DISAGREEMENT_SHARE * (hi - lo)


def apply_review(proposal: dict[str, Any], review: dict[str, Any], model: str) -> dict[str, Any]:
    q = {**proposal, "score_details": dict(proposal.get("score_details") or {}),
         "importance_sources": dict(proposal.get("importance_sources") or {})}
    if isinstance(proposal.get("axes"), dict):
        q["axes"] = dict(proposal["axes"])
    disagreements = []
    for dim, a in review["assessments"].items():
        before_value = dimension_value(proposal, dim)
        before = (proposal.get("score_details") or {}).get(dim) or {}
        set_dimension(q, dim, a["value"])
        status = "scored" if a["value"] is not None else "insufficient_evidence" if dim == "feasibility" else "not_applicable"
        q["score_details"][dim] = {
            "status": status, "confidence": a["confidence"], "method": "revision-chat", "model": model,
            "rationale": review["note"], "jev_value": before_value, "jev_status": before.get("status"),
            "jev_confidence": before.get("confidence")}
        disagreement = disagrees(dim, before_value, a["value"])
        if disagreement and dim in RESOLVE_NOT_APPLICABLE and a["value"] is None and before_value is not None:
            disagreement = False
            q["score_details"][dim]["resolution"] = "non_applicable_seconde_lecture"
        q["score_details"][dim]["disagreement"] = disagreement
        if disagreement:
            disagreements.append(dim)
    q["revision"] = {"model": model, "note": review["note"], "dimensions": list(review["assessments"]),
                     "disagreements": disagreements, "human_review_required": bool(disagreements),
                     "note_method": "Lecture independante a l'aveugle ; confiance declaree, non calibree."}
    ps.derive_fields(q)
    update_importance(q)
    return q


def review_payload(model: str, items: list[dict[str, Any]], instructions: str = REVIEW_INSTRUCTIONS,
                   payload_hook=None) -> dict[str, Any]:
    """Corps de requete chat/completions d'un lot (partage par l'appel direct et l'API batch)."""
    wanted = {d for i in items for d in i["dimensions"]}
    dims = [d for d in REVIEWABLE if d in wanted] + sorted(wanted - set(REVIEWABLE))
    body = {"rubric": rubric(dims), "proposals": items}
    payload = {"model": model, "temperature": 0, "max_tokens": 6000, "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": instructions + "\n" + json.dumps(body, ensure_ascii=False)}]}
    if payload_hook:
        payload.update(payload_hook(items, dims))
        payload = {k: v for k, v in payload.items() if v is not None}  # None : parametre retire
    return payload


def parse_completion(response: dict[str, Any], items: list[dict[str, Any]], dropped: dict[str, int]) -> dict[str, dict[str, Any]]:
    choice = (response.get("choices") or [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Reponse de revision interrompue.")
    return parse_reviews((choice.get("message") or {}).get("content"), items, dropped)


def make_reviewer(model: str, api_key: str, journal: LLMJournal, cache: dict[str, Any], cache_path: Path,
                  max_cost: float, cost_per_call: float, stats: dict[str, int], *, legacy: bool = True,
                  instructions: str = REVIEW_INSTRUCTIONS, payload_hook=None, stage: str = "revision"):
    """payload_hook(items, dims) -> dict fusionne dans la requete (ex. effort de raisonnement, schema JSON strict)."""
    def call(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        spent = journal_cost(journal.path)
        per_call = spent / stats["calls"] if stats["calls"] else cost_per_call
        if spent + per_call > max_cost:
            raise BudgetExhausted()
        payload = review_payload(model, items, instructions, payload_hook)
        request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        stats["calls"] += 1
        try:
            response = request_json(request, 300, journal=journal, stage=stage, proposal_ids=[i["id"] for i in items])
            dropped: dict[str, int] = {}
            reviews = parse_completion(response, items, dropped)
            stats["dropped_dimensions"] += dropped.get("dimensions", 0)
        except (OSError, ValueError, KeyError) as exc:
            stats["failed_batches"] += 1
            print(f"ERREUR revision (lot de {len(items)}): {exc}", file=sys.stderr)
            return {}
        for item in items:
            if item["id"] in reviews:
                cache[cache_key(model, item)] = reviews[item["id"]]
        pc.save_json(cache_path, cache)
        return reviews

    def review_batch(batch: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        todo = []
        for item in batch:
            hit, old = cached_review(cache, model, item, legacy)
            if hit is not None:
                result[item["id"]] = hit
                stats["cached"] += 1
                stats["legacy_cached"] = stats.get("legacy_cached", 0) + old
            else:
                todo.append(item)
        if not todo:
            return result
        result.update(call(todo))
        missing = [i for i in todo if i["id"] not in result]
        if len(todo) > 1:  # lot illisible ou incomplet : une seule relance, proposition par proposition
            for item in missing:
                stats["retried"] += 1
                result.update(call([item]))
        stats["unreviewed"] += sum(i["id"] not in result for i in todo)
        return result
    return review_batch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="Sortie du pipeline Jev")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--review-queue", type=Path, help="File de revision restante apres seconde lecture")
    parser.add_argument("--cache-file", type=Path, default=Path("cache_revision_2027.json"))
    parser.add_argument("--threshold", type=float, default=.65, help="Seuil de confiance Jev declenchant la revision")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--model", help="Defaut: OPENROUTER_WEB_MODEL du .env")
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-call", type=float, default=DEFAULT_COST_PER_CALL)
    parser.add_argument("--no-legacy-cache", action="store_true",
                        help="Ne pas reutiliser les relectures faites avec les anciennes definitions d'applicabilite")
    args = parser.parse_args()
    legacy = not args.no_legacy_cache
    journal = None
    try:
        if args.batch_size < 1 or args.max_cost < 0 or not 0 < args.threshold <= 1:
            raise ValueError("Options invalides.")
        ps.load_env_file(Path(__file__).with_name(".env"))
        model = (args.model or os.getenv("OPENROUTER_WEB_MODEL", "")).strip()
        if not model or model.endswith(":online") or ps.is_openrouter_jev_model(model):
            raise ValueError("Definir OPENROUTER_WEB_MODEL (ou --model) : modele chat, pas Jev Decisions.")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        names = blind_names(data.get("candidates", []))
        items = []
        for p in data["proposals"]:
            dims = dimensions_to_review(p, args.threshold)
            if dims:
                items.append({**blind_item(p, names), "dimensions": dims})
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        lookups = [cached_review(cache, model, i, legacy) for i in items]
        todo = [i for i, (hit, _) in zip(items, lookups) if hit is None]
        n_legacy = sum(old for _, old in lookups)
        calls = math.ceil(len(todo) / args.batch_size)
        n_dims = sum(len(i["dimensions"]) for i in items)
        print(f"Plan: {len(items)}/{len(data['proposals'])} propositions a revoir ({n_dims} dimensions, "
              f"{len(items) - len(todo)} en cache dont {n_legacy} sous l'ancienne definition), {calls} appels ~ {calls * args.cost_per_call:.2f} $, modele {model}.")
        if args.max_cost <= 0:
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
        journal = LLMJournal(secrets=(key,))
        stats = {"calls": 0, "cached": 0, "failed_batches": 0, "retried": 0, "unreviewed": 0, "dropped_dimensions": 0}
        reviewer = make_reviewer(model, key, journal, cache, args.cache_file, args.max_cost, args.cost_per_call, stats,
                                 legacy=legacy)
        reviews: dict[str, dict[str, Any]] = {}
        exhausted = False
        try:
            for start in range(0, len(items), args.batch_size):
                reviews.update(reviewer(items[start:start + args.batch_size]))
        except BudgetExhausted:
            exhausted = True
        proposals = [apply_review(p, reviews[p["id"]], model) if p.get("id") in reviews else p for p in data["proposals"]]
        disagreements = sum(bool((p.get("revision") or {}).get("disagreements")) for p in proposals)
        remaining = review_queue(proposals, args.threshold)
        report = {**stats, "to_review": len(items), "reviewed": len(reviews), "dimensions": n_dims,
                  "disagreements": disagreements, "remaining_queue": len(remaining),
                  "cost": round(journal_cost(journal.path), 4), "exhausted_budget": exhausted, "model": model,
                  "threshold": args.threshold}
        pc.save_json(args.out, {**data, "meta": {**data.get("meta", {}), "revision": report},
                                "dimensions_schema": ps.dimensions_schema(), "proposals": proposals})
        if args.review_queue:
            pc.save_json(args.review_queue, {"threshold": args.threshold, "proposals": remaining})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if stats["unreviewed"] or exhausted else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur revision: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
