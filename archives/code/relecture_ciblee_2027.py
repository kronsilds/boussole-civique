"""Relecture ciblee, a l'aveugle, apres la seconde lecture : axe economique hors themes economiques et ordre de grandeur budgetaire.

Entree : sortie de revision_2027.py (ex. donnees_revision_2027.json). Pour chaque proposition :
- cost_estimate (ordre de grandeur budgetaire annuel estime, indicatif) : toutes les propositions ;
- eco : propositions hors themes economiques dont l'axe economique est renseigne. La definition de has_eco a ete
  resserree le 2026-11-05 (le simple cout d'une mesure de securite, justice, defense, culture ou institutions ne suffit
  plus) ; l'ancienne note eco reste dans score_details (previous_value, jev_value).

Une note eco devenue « non applicable » est tranchee sans relecture humaine (meme regle que revision_2027) ; un ecart
fort entre deux valeurs est signale. cost_estimate n'est jamais signale (indicatif). Modele chat via OpenRouter, avec
effort de raisonnement et schema JSON strict. Sans --max-cost, plan seul. Cache par proposition, dimensions et modele.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import revision_2027 as rv
from axes_2027 import BudgetExhausted, blind_item, blind_names
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import dimension_value, request_json, review_queue, set_dimension, update_importance
from update_corpus_2027 import journal_cost

METHOD = "relecture-ciblee"
# Themes dont les mesures sont economiques par construction : l'axe eco y est juste a 95 % (controle du 2026-11-05).
ECONOMIC_THEMES = frozenset({"economie", "fiscalite", "emploi", "retraites", "logement", "energie", "services_publics",
                             "sante", "agriculture", "ecologie"})
DIMS = ("eco", "cost_estimate")
DEFAULT_COST_PER_CALL = 0.02

INSTRUCTIONS = (
    "Tu relis, sans connaitre leur auteur, des propositions de programmes politiques. Ne cherche pas a deviner le "
    "candidat et n'utilise aucune connaissance sur les partis. Pour chaque proposition (theme, title, description, quote "
    "et, s'il existe, montant_annuel_publie_md), note uniquement les dimensions listees dans son champ `dimensions`, "
    "selon le bareme `rubric` :\n"
    "- echelle (`range` et `anchors`) : un entier dans la plage, ou null si la condition `applies_if` n'est pas remplie ;\n"
    "- choix (`options`) : exactement une des cles.\n"
    "Pour cost_estimate, donne un ordre de grandeur realiste du dispositif decrit (effectifs, beneficiaires, montants "
    "comparables) ; indeterminable seulement si le texte est trop vague pour estimer.\n"
    "Donne pour chaque dimension une confiance entre 0 et 1, puis une note d'audit tres breve (90 caracteres maximum) qui "
    "justifie l'ordre de grandeur et, si eco est demande, son applicabilite.\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"dimension\": "
    "{\"value\": ..., \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu."
)


def targeted_dimensions(proposal: dict[str, Any]) -> list[str]:
    dims = []
    if proposal.get("theme_id") not in ECONOMIC_THEMES and (proposal.get("axes") or {}).get("eco") is not None:
        dims.append("eco")
    dims.append("cost_estimate")
    return dims


def short_id(proposal_id: str) -> str:
    """Identifiant court envoye au modele (moins de tokens en entree et en sortie), stable pour le cache."""
    return proposal_id[-8:]


def make_item(proposal: dict[str, Any], names: set[str]) -> dict[str, Any]:
    item = blind_item(proposal, names)
    item["id"] = short_id(proposal["id"])
    if ps.number(proposal.get("budget_net_bn_year")):
        item["montant_annuel_publie_md"] = proposal["budget_net_bn_year"]
    item["dimensions"] = targeted_dimensions(proposal)
    return item


def value_schema(dim: str) -> dict[str, Any]:
    if dim in ps.JEV_CHOICE_AXES:
        return {"type": "string", "enum": list(ps.TYPESAFE_QUESTIONS[dim]["criteria"])}
    return {"type": ["integer", "null"]}


def response_schema(dims: list[str]) -> dict[str, Any]:
    assessment = {d: {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                      "properties": {"value": value_schema(d), "confidence": {"type": "number"}}} for d in dims}
    review = {"type": "object", "additionalProperties": False, "required": ["id", "assessments", "note"],
              "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                             "assessments": {"type": "object", "additionalProperties": False, "required": list(dims),
                                             "properties": assessment}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "items": review}}}


def payload_hook(effort: str):
    def hook(items: list[dict[str, Any]], dims: list[str]) -> dict[str, Any]:
        # Lots homogenes (memes dimensions) : le schema impose exactement les dimensions demandees.
        return {"temperature": None, "max_tokens": 24000, "reasoning": {"effort": effort},
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "relecture", "strict": True, "schema": response_schema(dims)}}}
    return hook


BATCH_URL = "https://openrouter.ai/api/v1/batches"
# Mesure des pilotes du 2026-11-05 : 0,00074 $ par proposition en appel direct (GPT-6.1 Terra, medium) ; batch = moitie.
DEFAULT_BATCH_COST_PER_ITEM = 0.00037


def lots(groups: dict[tuple[str, ...], list[dict[str, Any]]], todo: set[str], batch_size: int) -> list[list[dict[str, Any]]]:
    out = []
    for group in groups.values():
        pending = [i for i in group if i["id"] in todo]
        out += [pending[s:s + batch_size] for s in range(0, len(pending), batch_size)]
    return out


def batch_submit(state_path: Path, model: str, effort: str, key: str, batches: list[list[dict[str, Any]]],
                 max_cost: float, cost_per_item: float, journal: LLMJournal, make_body=None) -> dict[str, Any]:
    """Envoie tous les lots en un batch OpenRouter (asynchrone, non annulable) si l'estimation tient dans le plafond.

    make_body(lot) -> corps chat/completions ; par defaut, la relecture ciblee de ce module.
    """
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not state.get("collected_at"):
            raise ValueError(f"Batch {state.get('batch_id')} deja envoye et non recupere : --batch-collect d'abord.")
    n_items = sum(len(b) for b in batches)
    estimate = n_items * cost_per_item
    print(f"Batch : {len(batches)} requetes, {n_items} propositions, estimation {estimate:.2f} $ (plafond {max_cost:.2f} $).")
    if estimate > max_cost:
        raise ValueError("Estimation au-dessus du plafond : batch non envoye (un batch ne peut pas etre annule).")
    hook = payload_hook(effort)
    make_body = make_body or (lambda b: rv.review_payload(model, b, INSTRUCTIONS, hook))
    requests = [{"custom_id": f"lot-{n:04d}", "body": make_body(b)} for n, b in enumerate(batches)]
    body = {"endpoint": "/v1/chat/completions", "model": model, "requests": requests}
    request = urllib.request.Request(BATCH_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    response = request_json(request, 600, journal=journal, stage="relecture_batch_submit")
    state = {"batch_id": response.get("id"), "status": response.get("status"), "model": model, "effort": effort,
             "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "estimate": round(estimate, 4),
             "lots": {r["custom_id"]: b for r, b in zip(requests, batches)}}
    pc.save_json(state_path, state)
    return state


def batch_collect(state_path: Path, key: str, cache: dict[str, Any], cache_path: Path, journal: LLMJournal,
                  raw_path: Path | None = None, parse=None, key_fn=None) -> dict[str, Any]:
    """Recupere un batch termine et range chaque relecture valide dans le cache (aucun cout).

    parse(corps, lot) -> {id: relecture} et key_fn(modele, item) -> cle de cache ; par defaut, ceux de la relecture.
    """
    key_fn = key_fn or rv.cache_key
    state = json.loads(state_path.read_text(encoding="utf-8"))
    request = urllib.request.Request(f"{BATCH_URL}/{state['batch_id']}", headers={"Authorization": "Bearer " + key})
    response = request_json(request, 300, journal=journal, stage="relecture_batch_collect")
    status, counts = response.get("status"), response.get("request_counts") or {}
    report = {"batch_id": state["batch_id"], "status": status, "request_counts": counts}
    if status not in {"completed", "expired", "failed", "cancelled"}:
        return report
    stats = {"lots_ok": 0, "lots_failed": 0, "reviews": 0, "dropped_dimensions": 0}
    for result in response.get("results") or []:
        batch = state["lots"].get(result.get("custom_id"))
        body = (result.get("response") or {}).get("body")
        if batch is None or result.get("error") or not isinstance(body, dict):
            stats["lots_failed"] += 1
            continue
        try:
            dropped: dict[str, int] = {}
            reviews = parse(body, batch) if parse else rv.parse_completion(body, batch, dropped)
        except ValueError:
            stats["lots_failed"] += 1
            continue
        stats["lots_ok"] += 1
        stats["dropped_dimensions"] += dropped.get("dimensions", 0)
        for item in batch:
            if item["id"] in reviews:
                cache[key_fn(state["model"], item)] = reviews[item["id"]]
                stats["reviews"] += 1
    pc.save_json(cache_path, cache)
    if raw_path:
        pc.save_json(raw_path, response)
    usage = response.get("usage") or {}
    state.update(status=status, collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 cost=usage.get("cost"), usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                 collect=stats)
    pc.save_json(state_path, state)
    return {**report, **stats, "cost": usage.get("cost"), "estimate": state.get("estimate")}


def apply_targeted(proposal: dict[str, Any], review: dict[str, Any], model: str) -> dict[str, Any]:
    q = {**proposal, "score_details": dict(proposal.get("score_details") or {}),
         "importance_sources": dict(proposal.get("importance_sources") or {}), "axes": dict(proposal.get("axes") or {})}
    disagreements = []
    for dim, a in review["assessments"].items():
        before_value = dimension_value(proposal, dim)
        before = (proposal.get("score_details") or {}).get(dim) or {}
        set_dimension(q, dim, a["value"])
        from_revision = before.get("method") in {"revision-chat", METHOD}
        detail = {"status": "scored" if a["value"] is not None else "not_applicable", "confidence": a["confidence"],
                  "method": METHOD, "model": model, "rationale": review["note"],
                  "previous_value": before_value, "previous_method": before.get("method"),
                  "jev_value": before.get("jev_value") if from_revision else before_value,
                  "jev_confidence": before.get("jev_confidence") if from_revision else before.get("confidence")}
        disagreement = False
        if dim == "eco" and before_value is not None:
            if a["value"] is None:
                detail["resolution"] = "non_applicable_relecture"
            else:
                disagreement = rv.disagrees(dim, before_value, a["value"])
        detail["disagreement"] = disagreement
        q["score_details"][dim] = detail
        if disagreement:
            disagreements.append(dim)
    dims = list(review["assessments"])
    q["relecture_ciblee"] = {"model": model, "note": review["note"], "dimensions": dims, "disagreements": disagreements,
                             "note_method": "Lecture independante a l'aveugle ; definition resserree de l'axe economique."}
    if isinstance(proposal.get("revision"), dict):  # la relecture remplace la divergence anterieure sur ces dimensions
        kept = [d for d in proposal["revision"].get("disagreements") or [] if d not in dims]
        q["revision"] = {**proposal["revision"], "disagreements": kept,
                         "human_review_required": bool(kept or disagreements)}
    ps.derive_fields(q)
    update_importance(q)
    return q


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="Sortie de revision_2027.py")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--review-queue", type=Path)
    parser.add_argument("--cache-file", type=Path, default=Path("cache_relecture_2027.json"))
    parser.add_argument("--model", required=True, help="Modele chat OpenRouter, ex. openai/gpt-6.1-terra")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0, help="Pilote : seulement N propositions (apres --offset)")
    parser.add_argument("--offset", type=int, default=0, help="Pilote : propositions ignorees en tete de fichier")
    parser.add_argument("--threshold", type=float, default=.65)
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-call", type=float, default=DEFAULT_COST_PER_CALL)
    parser.add_argument("--batch-submit", action="store_true",
                        help="Envoie les lots non caches en un batch OpenRouter (moitie prix, sous 24 h, non annulable)")
    parser.add_argument("--batch-collect", action="store_true", help="Recupere le batch envoye et remplit le cache (gratuit)")
    parser.add_argument("--batch-state", type=Path, default=Path("relecture_batch_2027.json"))
    parser.add_argument("--batch-cost-per-item", type=float, default=DEFAULT_BATCH_COST_PER_ITEM)
    args = parser.parse_args()
    journal = None
    try:
        if args.batch_size < 1 or args.max_cost < 0 or args.limit < 0:
            raise ValueError("Options invalides.")
        if ps.is_openrouter_jev_model(args.model) or args.model.endswith(":online"):
            raise ValueError("Modele chat attendu (ni Jev Decisions, ni :online).")
        ps.load_env_file(Path(__file__).with_name(".env"))
        data = json.loads(args.input.read_text(encoding="utf-8"))
        names = blind_names(data.get("candidates", []))
        proposals = data["proposals"][args.offset:args.offset + args.limit if args.limit else None]
        items = sorted((make_item(p, names) for p in proposals), key=lambda i: len(i["dimensions"]))
        full_id = {short_id(p["id"]): p["id"] for p in proposals}
        if len(full_id) != len(proposals):
            raise ValueError("Identifiants courts en collision : allonger short_id.")
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        todo = {i["id"] for i in items if rv.cache_key(args.model, i) not in cache}
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for i in items:
            groups.setdefault(tuple(i["dimensions"]), []).append(i)
        calls = sum(math.ceil(sum(i["id"] in todo for i in g) / args.batch_size) for g in groups.values())
        n_eco = sum("eco" in i["dimensions"] for i in items)
        print(f"Plan: {len(items)} propositions (eco relu : {n_eco} ; cost_estimate : {len(items)}), "
              f"{len(items) - len(todo)} en cache, {calls} appels ~ {calls * args.cost_per_call:.2f} $, "
              f"modele {args.model}, raisonnement {args.reasoning_effort}.")
        if args.batch_submit and args.batch_collect:
            raise ValueError("--batch-submit et --batch-collect s'excluent.")
        if args.max_cost <= 0 and not args.batch_collect and (todo or args.batch_submit):  # tout en cache : ecriture gratuite
            if args.batch_submit:
                print(f"Batch : estimation {len(todo) * args.batch_cost_per_item:.2f} $ pour {len(todo)} propositions.")
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key and (todo or args.batch_submit or args.batch_collect):
            raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
        journal = LLMJournal(secrets=(key,))
        if args.batch_collect:  # gratuit : remplit le cache ; relancer ensuite sans option pour ecrire les sorties
            report = batch_collect(args.batch_state, key, cache, args.cache_file, journal,
                                   args.batch_state.with_name(args.batch_state.stem + "_resultats.json"))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.batch_submit:
            state = batch_submit(args.batch_state, args.model, args.reasoning_effort, key, lots(groups, todo, args.batch_size),
                                 args.max_cost, args.batch_cost_per_item, journal)
            print(f"Batch envoye : {state['batch_id']} ({state['status']}), {len(state['lots'])} requetes. "
                  f"Recuperer avec --batch-collect (resultats sous 24 h).")
            return 0
        stats = {"calls": 0, "cached": 0, "failed_batches": 0, "retried": 0, "unreviewed": 0, "dropped_dimensions": 0}
        reviewer = rv.make_reviewer(args.model, key, journal, cache, args.cache_file, args.max_cost, args.cost_per_call,
                                    stats, legacy=False, instructions=INSTRUCTIONS,
                                    payload_hook=payload_hook(args.reasoning_effort), stage="relecture_ciblee")
        reviews: dict[str, dict[str, Any]] = {}
        exhausted = False
        try:
            for group in groups.values():
                for start in range(0, len(group), args.batch_size):
                    reviews.update(reviewer(group[start:start + args.batch_size]))
        except BudgetExhausted:
            exhausted = True
        reviews = {full_id[k]: v for k, v in reviews.items()}
        by_id = {p["id"]: p for p in proposals}
        out_props = [apply_targeted(p, reviews[p["id"]], args.model) if p["id"] in reviews and p["id"] in by_id else p
                     for p in data["proposals"]]
        n_na = sum(((p.get("score_details") or {}).get("eco") or {}).get("resolution") == "non_applicable_relecture"
                   for p in out_props)
        remaining = review_queue(out_props, args.threshold)
        report = {**stats, "to_review": len(items), "reviewed": len(reviews), "eco_reread": n_eco,
                  "eco_now_not_applicable": n_na,
                  "eco_disagreements": sum("eco" in ((p.get("relecture_ciblee") or {}).get("disagreements") or [])
                                           for p in out_props),
                  "remaining_queue": len(remaining), "cost": round(journal_cost(journal.path), 4),
                  "exhausted_budget": exhausted, "model": args.model, "reasoning_effort": args.reasoning_effort,
                  "limit": args.limit or None}
        pc.save_json(args.out, {**data, "meta": {**data.get("meta", {}), "relecture_ciblee": report},
                                "dimensions_schema": ps.dimensions_schema(), "proposals": out_props})
        if args.review_queue:
            pc.save_json(args.review_queue, {"threshold": args.threshold, "proposals": remaining})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if stats["unreviewed"] or exhausted else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur relecture: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
