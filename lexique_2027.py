"""Lexique par candidat : ce que ses propres documents entendent par les termes ambigus (laicite, souverainete...).

  python .\\lexique_2027.py                     # recherche gratuite des phrases candidates, plan
  python .\\lexique_2027.py --max-cost 0.25     # choix des citations par le modele, ecrit donnees/lexique_2027.json

1. Gratuit : dans les documents de chaque candidat, phrases qui emploient un terme du lexique, classees par indices
   de definition (« c'est », « signifie », « repose sur »...).
2. Payant, plafonne : le modele choisit, par numero, au plus deux phrases qui montrent le sens donne au terme (ou
   aucune). Il ne reformule rien : chaque entree est une citation exacte, avec son document et sa page.
Les noms et partis sont masques avant l'envoi et dans le lexique. Utilisation : `entrees(lexique, candidat, texte)`
donne, pour une mesure, les definitions des termes qu'elle emploie.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

TERMES = {
    "laïcité": r"la[ïi]cit",
    "souveraineté": r"souverainet",
    "liberté": r"libert[ée]",
    "mérite": r"m[ée]rite",
    "simplification": r"simplifi",
    "protection": r"protection(?!\s+sociale)|prot[ée]ger",
    "sécurité": r"s[ée]curit[ée](?!\s+sociale)",
    "assimilation": r"assimil",
    "intégration": r"int[ée]gration",
    "identité": r"identit[ée]",
    "écologie": r"[ée]colog",
    "justice sociale": r"justice sociale",
    "démocratie": r"d[ée]mocrati",
    "autorité": r"autorit[ée]",
    "valeur travail": r"valeur(?:\s+du)?\s+travail",
}
MOTIFS = {k: re.compile(v, re.I) for k, v in TERMES.items()}
INDICES = re.compile(r"\b(c'est|c’est|ce n'est pas|ce n’est pas|signifie|veut dire|consiste|nous entendons|"
                     r"nous d[ée]fendons|repose sur|doit [êe]tre|n'est pas|n’est pas|principe|garanti[rt]|au service de)\b", re.I)
PAR_TERME = 10          # phrases candidates par terme et par candidat
COUT_ESTIME = .012      # par candidat (une requete)


def phrases(texte: str) -> list[str]:
    morceaux = re.split(r"(?<=[.!?;])\s+|\n{1,}", texte)
    return [re.sub(r"\s+", " ", m).strip() for m in morceaux if 50 <= len(m.strip()) <= 450]


def candidates(corpus: Path, masque) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """{candidat: {terme: [{id, texte, document_id, page}]}} : phrases les plus definitoires d'abord."""
    manifeste = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    brut: dict[str, dict[str, list[tuple[float, dict[str, Any]]]]] = {}
    for doc in manifeste["documents"].values():
        f = corpus / "texts" / f"{doc.get('content_hash')}.json"
        cands = {b.get("candidate_id") for b in doc.get("bindings") or [] if b.get("candidate_id")}
        if doc.get("status") != "ready" or not f.exists() or not cands:
            continue
        for seg in json.loads(f.read_text(encoding="utf-8"))["segments"]:
            for ph in phrases(seg.get("text") or ""):
                for terme, motif in MOTIFS.items():
                    if not motif.search(ph):
                        continue
                    score = 2 * bool(INDICES.search(ph)) + min(len(motif.findall(ph)), 3) - len(ph) / 600
                    for c in cands:
                        brut.setdefault(c, {}).setdefault(terme, []).append(
                            (score, {"texte": masque(ph), "document_id": doc["id"], "page": seg.get("page")}))
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for c, termes in brut.items():
        for terme, lst in termes.items():
            vus, garde = set(), []
            for _, x in sorted(lst, key=lambda t: -t[0]):
                cle = x["texte"].lower()[:120]
                if cle in vus:
                    continue
                vus.add(cle)
                garde.append({**x, "id": f"{len(garde) + 1}"})
                if len(garde) >= PAR_TERME:
                    break
            out.setdefault(c, {})[terme] = garde
    return out


CONSIGNE = (
    "Voici, pour un auteur de programme politique (anonyme), des phrases de ses documents qui emploient certains termes. "
    "Pour chaque terme, choisis au plus deux phrases, par leur numero, qui montrent le mieux ce que ce document entend "
    "par ce terme : definition, contenu concret, ce que le terme implique ou exclut. Ecarte les simples mentions, slogans "
    "ou emplois dans un autre sens (par exemple « securite sociale » pour « securite »). Si aucune phrase ne precise le "
    "sens, ne choisis rien. Ne reformule pas.\n"
    "Reponds uniquement par l'objet JSON {\"lexique\": [{\"terme\": \"...\", \"ids\": [\"...\"]}]}, une entree par terme recu.")


def requete(modele: str, termes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    corps = {t: [{"id": x["id"], "texte": x["texte"]} for x in lst] for t, lst in termes.items()}
    schema = {"type": "object", "additionalProperties": False, "required": ["lexique"], "properties": {"lexique": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["terme", "ids"],
                                   "properties": {"terme": {"type": "string", "enum": list(termes)},
                                                  "ids": {"type": "array", "items": {"type": "string"}}}}}}}
    return {"model": modele, "max_tokens": 4000, "reasoning": {"effort": "low"},
            "response_format": {"type": "json_schema", "json_schema": {"name": "lexique", "strict": True, "schema": schema}},
            "messages": [{"role": "user", "content": CONSIGNE + "\n" + json.dumps(corps, ensure_ascii=False)}]}


def lire(reponse: dict[str, Any], termes: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    import programme_corpus_2027 as pc
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    out: dict[str, list[dict[str, Any]]] = {}
    for e in pc.parse_json_object((choix.get("message") or {}).get("content"), "Lexique").get("lexique") or []:
        par_id = {x["id"]: x for x in termes.get(e.get("terme"), [])}
        garde = [par_id[i] for i in (e.get("ids") or [])[:2] if i in par_id]  # citation exacte : choisie par numero
        if garde:
            out[e["terme"]] = [{k: x[k] for k in ("texte", "document_id", "page")} for x in garde]
    return out


def entrees(lexique: dict[str, Any], candidat: str, texte: str) -> dict[str, list[str]]:
    """Definitions du candidat pour les termes employes dans le texte d'une mesure."""
    termes = (lexique.get("candidats") or {}).get(candidat) or {}
    return {t: [x["texte"] for x in termes[t]] for t, motif in MOTIFS.items() if t in termes and motif.search(texte or "")}


def main() -> int:
    import base_2027 as B
    import boussole_2027 as BO
    import pipeline_scoring_2027 as ps
    from commun_2027 import blind_names
    from scoring_context_2027 import request_json
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--racine", default=".")
    p.add_argument("--max-cost", type=float, default=0.0)
    p.add_argument("--modele", default="openai/gpt-6.1-terra")
    args = p.parse_args()
    c = BO.chemins(args)
    base = BO.charger_base(c)
    noms = blind_names(base.get("candidates") or [])
    motif = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True)) + r")(?!\w)", re.I)
    masque = lambda t: motif.sub("[le candidat]", t) if noms else t  # noqa: E731
    cands = candidates(c["corpus"], masque)
    for cand in sorted(cands):
        print(f"  {cand:14} " + ", ".join(f"{t} {len(v)}" for t, v in sorted(cands[cand].items())))
    chemin = c["donnees"] / "lexique_2027.json"
    lexique = B.lire_json(chemin, {"modele": args.modele, "candidats": {}})
    a_faire = [x for x in sorted(cands) if x not in lexique["candidats"]]
    print(f"{len(a_faire)} candidats a traiter, estimation {len(a_faire) * COUT_ESTIME:.3f} $ (plafond {args.max_cost} $).")
    if not a_faire or args.max_cost <= 0:
        return 0
    from llm_logging_2027 import LLMJournal
    from update_corpus_2027 import journal_cost
    ps.load_env_file(Path(__file__).with_name(".env"))
    cle = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not cle:
        raise SystemExit("OPENROUTER_API_KEY manque ; aucun appel lance.")
    journal = LLMJournal(secrets=(cle,))
    estime = 0.0
    try:
        for cand in a_faire:
            depense = max(estime, journal_cost(journal.path))
            if depense + COUT_ESTIME > args.max_cost:
                print("Plafond atteint : arret.")
                break
            estime = depense + COUT_ESTIME
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps(requete(args.modele, cands[cand]), ensure_ascii=False).encode("utf-8"),
                                         headers={"Authorization": "Bearer " + cle, "Content-Type": "application/json"})
            try:
                lexique["candidats"][cand] = lire(request_json(req, 600, journal=journal, stage="lexique"), cands[cand])
            except (OSError, ValueError, KeyError) as exc:
                print(f"ERREUR {cand} : {exc}", file=sys.stderr)
                continue
            B.ecrire_json(chemin, lexique)
            print(f"  {cand} : {len(lexique['candidats'][cand])} termes definis")
        print(f"Cout reel : {journal_cost(journal.path):.4f} $")
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
