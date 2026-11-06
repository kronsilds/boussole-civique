"""Generalisation des descripteurs factuels a tout le corpus et note eco calculee (spec_descripteurs_2027.md).

Pour chaque proposition, cinq questions a choix posees a l'aveugle (consigne corrigee du pilote,
pilote_descripteurs_2027.INSTRUCTIONS) : levier, public_vise, portee, et eco_etat / eco_distrib (null si l'axe
economique ne s'applique pas). La note eco est ensuite calculee par descripteurs_2027.eco_score et remplace l'ancienne,
qui reste dans score_details.eco.previous_value pour l'audit.

Etapes (aucun appel payant sans plafond) :
1. sans option : plan et estimation ;
2. --batch-submit --max-cost X : envoi en un batch OpenRouter (moitie prix, sous 24 h, non annulable) ;
3. --batch-collect : recuperation gratuite dans le cache (partage avec le pilote, dont les lectures corrigees servent) ;
4. --out FICHIER : ecriture des donnees enrichies quand tout est en cache (ou --allow-partial).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import descripteurs_2027 as D
import pilote_descripteurs_2027 as pd
import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import relecture_ciblee_2027 as rc
from axes_2027 import blind_names
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import dimension_value, set_dimension

METHOD = "descripteurs-formule"
# Pilote du 2026-11-06 : 0,146 $ pour 155 lectures en appel direct (0,00094 $) ; batch = moitie, arrondi au-dessus.
DEFAULT_BATCH_COST_PER_ITEM = 0.0005


def cache_key(model: str, item: dict[str, Any]) -> str:
    return pd.cache_key(model, item, 1, pd.INSTRUCTIONS)


def apply_descriptors(proposal: dict[str, Any], review: dict[str, Any], model: str) -> dict[str, Any]:
    q = {**proposal, "axes": dict(proposal.get("axes") or {}), "score_details": dict(proposal.get("score_details") or {})}
    answers = {k: review["assessments"][k]["value"] for k in pd.QUESTIONS}
    conf = {k: review["assessments"][k]["confidence"] for k in pd.QUESTIONS}
    q["descripteurs"] = {k: answers[k] for k in pd.COMMON}
    q["score_details"]["descripteurs"] = {"method": METHOD, "model": model, "reponses": answers, "confidences": conf,
                                         "note": review["note"]}
    value, detail = D.eco_score({**answers, "rupture": dimension_value(proposal, "rupture"),
                                 "cost_estimate": dimension_value(proposal, "cost_estimate")})
    before = (proposal.get("score_details") or {}).get("eco") or {}
    previous = dimension_value(proposal, "eco")
    set_dimension(q, "eco", value)
    eco = {"status": "scored" if value is not None else "not_applicable", "method": METHOD, "model": model,
           "confidence": min(conf["eco_etat"], conf["eco_distrib"]),
           "rationale": detail.get("explication") or review["note"],
           "reponses": {k: answers[k] for k in pd.ECO}, "formule": {k: detail[k] for k in ("sens", "force_levier", "ampleur")} if detail else None,
           "previous_value": previous, "previous_method": before.get("method"),
           "previous_confidence": before.get("confidence"), "disagreement": False}
    if previous is not None and value is None:
        eco["resolution"] = "non_applicable_descripteurs"
    q["score_details"]["eco"] = eco
    if isinstance(q.get("revision"), dict):  # la note calculee remplace une divergence anterieure sur eco
        kept = [d for d in q["revision"].get("disagreements") or [] if d != "eco"]
        q["revision"] = {**q["revision"], "disagreements": kept, "human_review_required": bool(kept)}
    ps.derive_fields(q)
    return q


def summary(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    def eco(p):
        return dimension_value(p, "eco")
    old, new = [eco(p) for p in before], [eco(p) for p in after]
    vals = [v for v in new if v is not None]
    top = Counter(vals).most_common(1)[0] if vals else (None, 0)
    by_cand: dict[str, Any] = {}
    for cand in sorted({p.get("candidate_id") or p.get("candidate") or "?" for p in after}):
        o = [eco(p) for p in before if (p.get("candidate_id") or p.get("candidate") or "?") == cand and eco(p) is not None]
        n = [eco(p) for p in after if (p.get("candidate_id") or p.get("candidate") or "?") == cand and eco(p) is not None]
        by_cand[cand] = {"avant": (round(statistics.mean(o), 1) if o else None, len(o)),
                         "apres": (round(statistics.mean(n), 1) if n else None, len(n))}
    return {"eco_avant": sum(v is not None for v in old), "eco_apres": len(vals),
            "devenues_non_applicables": sum(o is not None and n is None for o, n in zip(old, new)),
            "nouvelles": sum(o is None and n is not None for o, n in zip(old, new)),
            "valeurs_distinctes": len(set(vals)), "pic": top[0], "part_du_pic": round(top[1] / len(vals), 2) if vals else None,
            "leviers": dict(Counter((p.get("descripteurs") or {}).get("levier") for p in after).most_common()),
            "moyenne_eco_par_candidat": by_cand}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("donnees_programmes_2027.json"))
    parser.add_argument("--out", type=Path, help="Donnees enrichies (ecrites seulement si tout est en cache)")
    parser.add_argument("--allow-partial", action="store_true", help="Ecrire --out meme s'il manque des descriptions")
    parser.add_argument("--cache-file", type=Path, default=Path("cache_descripteurs_2027.json"))
    parser.add_argument("--model", default="openai/gpt-6.1-terra")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0, help="Essai : seulement les N premieres propositions")
    parser.add_argument("--max-cost", type=float, default=0.0, help="Plafond en dollars sur l'estimation ; 0 = plan seul")
    parser.add_argument("--batch-submit", action="store_true")
    parser.add_argument("--batch-collect", action="store_true", help="Recupere le batch (gratuit) et remplit le cache")
    parser.add_argument("--batch-state", type=Path, default=Path("descripteurs_batch_2027.json"))
    parser.add_argument("--batch-cost-per-item", type=float, default=DEFAULT_BATCH_COST_PER_ITEM)
    args = parser.parse_args()
    journal = None
    try:
        if args.batch_size < 1 or args.max_cost < 0 or args.limit < 0 or (args.batch_submit and args.batch_collect):
            raise ValueError("Options invalides.")
        if ps.is_openrouter_jev_model(args.model) or args.model.endswith(":online"):
            raise ValueError("Modele chat attendu (ni Jev Decisions, ni :online).")
        ps.load_env_file(Path(__file__).with_name(".env"))
        data = json.loads(args.input.read_text(encoding="utf-8"))
        proposals = data["proposals"][:args.limit or None]
        names = blind_names(data.get("candidates", []))
        items = [pd.make_item(p, names) for p in proposals]
        full_id = {i["id"]: p["id"] for i, p in zip(items, proposals)}
        if len(full_id) != len(items):
            raise ValueError("Identifiants courts en collision : allonger short_id.")
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        todo = [i for i in items if cache_key(args.model, i) not in cache]
        lots = [todo[s:s + args.batch_size] for s in range(0, len(todo), args.batch_size)]
        print(f"Plan : {len(items)} propositions, {len(items) - len(todo)} en cache, {len(todo)} a decrire en "
              f"{len(lots)} requetes ; estimation batch {len(todo) * args.batch_cost_per_item:.2f} $ "
              f"(direct ~ {len(todo) * args.batch_cost_per_item * 2:.2f} $), modele {args.model}, "
              f"raisonnement {args.reasoning_effort}.")
        if args.batch_submit or args.batch_collect:
            key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not key:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(key,))
            if args.batch_collect:
                report = rc.batch_collect(args.batch_state, key, cache, args.cache_file, journal,
                                          args.batch_state.with_name(args.batch_state.stem + "_resultats.json"),
                                          parse=pd.parse, key_fn=cache_key)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0
            if not lots:
                print("Tout est deja en cache : rien a envoyer.")
                return 0
            if args.max_cost <= 0:
                raise ValueError("--max-cost requis pour envoyer le batch.")
            state = rc.batch_submit(args.batch_state, args.model, args.reasoning_effort, key, lots, args.max_cost,
                                    args.batch_cost_per_item, journal,
                                    make_body=lambda lot: pd.payload(args.model, lot, args.reasoning_effort))
            print(f"Batch envoye : {state['batch_id']} ({state['status']}), {len(state['lots'])} requetes. "
                  f"Recuperer avec --batch-collect (resultats sous 24 h).")
            return 0
        if not args.out:
            print("Aucun appel lance. Envoi : --batch-submit --max-cost <dollars> ; ecriture : --out <fichier>.")
            return 0
        if todo and not args.allow_partial:
            raise ValueError(f"{len(todo)} propositions sans description : --batch-collect d'abord, ou --allow-partial.")
        reviews = {full_id[i["id"]]: cache[cache_key(args.model, i)] for i in items if cache_key(args.model, i) in cache}
        out_props = [apply_descriptors(p, reviews[p["id"]], args.model) if p["id"] in reviews else p for p in data["proposals"]]
        report = {"model": args.model, "reasoning_effort": args.reasoning_effort, "decrites": len(reviews),
                  "manquantes": len(todo), **summary(data["proposals"], out_props)}
        pc.save_json(args.out, {**data, "meta": {**data.get("meta", {}), "descripteurs": report}, "proposals": out_props})
        print(json.dumps({k: v for k, v in report.items() if k != "moyenne_eco_par_candidat"}, ensure_ascii=False, indent=1))
        return 2 if todo else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur descripteurs: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
