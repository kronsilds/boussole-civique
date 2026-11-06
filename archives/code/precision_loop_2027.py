"""Precision scoree par LLM + boucle de pioche pour la selection des propositions a scorer.

1. Tour 1 : le LLM note la precision (0..100) des N meilleures propositions heuristiques de chaque
   (candidat, theme), par lots.
2. Si, dans un groupe, l'heuristique et le LLM divergent trop (ecart moyen > --tolerance), on pioche d'autres
   propositions du groupe (moitie dans l'ordre heuristique, moitie au hasard) et on les note, jusqu'a
   convergence (selection stable ou ecart acceptable), epuisement du groupe, --max-rounds ou budget.
3. Selection finale : les N plus precises *selon le LLM* de chaque groupe -> selection_precision_2027.json.

Sans --max-cost, plan seul (aucun appel). Cache par proposition et modele : relancer ne repaie rien.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

import programme_corpus_2027 as pc
import selection_scoring_2027 as sel
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import digest, request_json
from update_corpus_2027 import journal_cost

INSTRUCTION_VERSION = 1
DEFAULT_COST_PER_CALL = 0.002  # mesure au pilote : ~0,001 $/lot de 20 ; remplacee par le cout moyen reel observe

PRECISION_INSTRUCTIONS = (
    "Tu evalues la PRECISION d'engagements de programme politique, sans juger leur valeur ni leur orientation. "
    "Pour chaque proposition, donne un entier 'precision' de 0 a 100 :\n"
    "0-33 orientation generale : intention ou principe sans action verifiable ni parametre (ex. soutenir, favoriser, "
    "lutter contre, defendre une valeur) ;\n"
    "34-66 precis : action ou instrument nettement identifie (loi, taxe, suppression, creation d'un dispositif, "
    "regle precise) mais sans parametre chiffre ni echeance ;\n"
    "67-100 chiffre : montant, taux, seuil, quantite, duree ou echeance explicites, applicables sans interpretation.\n"
    "Note uniquement ce que disent le titre, la description et la citation fournis. N'utilise aucune connaissance "
    "externe. Reponds uniquement par l'objet JSON {\"scores\": [{\"id\": \"...\", \"precision\": 0}]} contenant "
    "exactement un element par identifiant recu, sans texte additionnel."
)


class BudgetExhausted(Exception):
    pass


def label_of(precision: float) -> str:
    return "chiffre" if precision >= 67 else "precis" if precision >= 34 else "orientation_generale"


def heuristic100(score: int) -> float:
    """Echelle 0..100 du score heuristique entier (typiquement -3..9)."""
    return max(0.0, min(1.0, (score + 2) / 10)) * 100


def run_loop(pools: dict[tuple[str, str], list[tuple[int, str, dict[str, Any]]]],
             score_batch: Callable[[list[dict[str, Any]]], dict[str, int]], *, per_theme: int = 8,
             tolerance: float = 25.0, max_rounds: int = 3, seed: int = 7) -> dict[str, Any]:
    """Boucle de pioche. score_batch(items) -> {id: precision} (peut lever BudgetExhausted)."""
    rng = random.Random(seed)
    state: dict[tuple[str, str], dict[str, Any]] = {}
    for key, pool in pools.items():
        state[key] = {"pool": pool, "llm": {}, "cursor": 0, "rounds": 0, "top": None, "done": False,
                      "next": [t[2]["id"] for t in pool[:per_theme]]}
    exhausted = False
    for round_number in range(1, max_rounds + 1):
        wanted = [(key, pid) for key, s in state.items() if not s["done"] for pid in s["next"] if pid not in s["llm"]]
        if not wanted:
            break
        by_id = {t[2]["id"]: t[2] for s in state.values() for t in s["pool"]}
        try:
            scores = score_batch([by_id[pid] for _, pid in wanted])
        except BudgetExhausted:
            exhausted = True
            scores = {}
        for key, pid in wanted:
            if pid in scores:
                state[key]["llm"][pid] = scores[pid]
        for key, s in state.items():
            if s["done"]:
                continue
            s["rounds"] = round_number
            heur = {t[2]["id"]: t[0] for t in s["pool"]}
            scored = s["llm"]
            ranked = sorted(scored, key=lambda i: (-scored[i], -heur[i], i))[:per_theme]
            s["divergence"] = (sum(abs(heuristic100(heur[i]) - scored[i]) for i in scored) / len(scored)) if scored else None
            remaining = [t[2]["id"] for t in s["pool"] if t[2]["id"] not in scored]
            stable = s["top"] is not None and set(ranked) == s["top"]
            s["top"] = set(ranked)
            if exhausted or not remaining or s["divergence"] is None or s["divergence"] <= tolerance or stable \
                    or round_number == max_rounds:
                s["done"] = True
                continue
            draw = max(2, per_theme // 2)
            ordered = remaining[:math.ceil(draw / 2)]
            rest = remaining[len(ordered):]
            s["next"] = ordered + rng.sample(rest, min(len(rest), draw // 2))
        if exhausted:
            break
    chosen, report = [], {"groups": len(state), "rounds_used": max((s["rounds"] for s in state.values()), default=0),
                          "exhausted_budget": exhausted, "extra_drawn": 0, "incomplete_groups": 0,
                          "high_divergence_groups": 0}
    for (candidate, theme), s in sorted(state.items()):
        heur = {t[2]["id"]: (t[0], t[1]) for t in s["pool"]}
        scored = s["llm"]
        report["extra_drawn"] += max(0, len(scored) - per_theme)
        if not scored or len(scored) < min(per_theme, len(s["pool"])):
            report["incomplete_groups"] += 1
        if s.get("divergence") is not None and s["divergence"] > tolerance:
            report["high_divergence_groups"] += 1
        for pid in sorted(scored, key=lambda i: (-scored[i], -heur[i][0], i))[:per_theme]:
            chosen.append({"id": pid, "candidate_id": candidate, "theme_id": theme, "precision_llm": scored[pid],
                           "precision": label_of(scored[pid]), "precision_heuristic": heur[pid][0],
                           "heuristic_label": heur[pid][1], "group_divergence": s.get("divergence")})
    report["selected"] = len(chosen)
    return {"selected": chosen, "report": report}


def parse_scores(content: Any, ids: list[str]) -> dict[str, int]:
    parsed = pc.parse_json_object(content, "Precision")
    items = parsed.get("scores")
    if set(parsed) != {"scores"} or not isinstance(items, list):
        raise ValueError("Reponse de precision invalide: objet {'scores': [...]} attendu.")
    result: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "precision"}:
            raise ValueError("Element de precision invalide.")
        value = item["precision"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("Precision hors plage 0..100.")
        if item["id"] in result:
            raise ValueError("Identifiant de precision en double.")
        result[item["id"]] = value
    if set(result) != set(ids):
        raise ValueError("Les identifiants de precision ne correspondent pas au lot envoye.")
    return result


def cache_key(model: str, p: dict[str, Any]) -> str:
    quote = ((p.get("source_evidence") or [{}])[0]).get("quote", "")
    return digest({"v": INSTRUCTION_VERSION, "model": model, "id": p["id"],
                   "text": [p.get("title"), p.get("description"), quote]})


def make_scorer(model: str, api_key: str, journal: LLMJournal, cache: dict[str, int], cache_path: Path,
                batch_size: int, max_cost: float, cost_per_call: float, stats: dict[str, Any]):
    def score_batch(items: list[dict[str, Any]]) -> dict[str, int]:
        result: dict[str, int] = {}
        todo = []
        for p in items:
            key = cache_key(model, p)
            if key in cache:
                result[p["id"]] = cache[key]
                stats["cached"] += 1
            else:
                todo.append(p)
        for start in range(0, len(todo), batch_size):
            batch = todo[start:start + batch_size]
            spent = journal_cost(journal.path)
            per_call = spent / stats["calls"] if stats["calls"] else cost_per_call
            if spent + per_call > max_cost:
                raise BudgetExhausted()
            payload = {"model": model, "temperature": 0, "max_tokens": 4096,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": PRECISION_INSTRUCTIONS + "\n" + json.dumps([
                           {"id": p["id"], "title": p.get("title"), "description": p.get("description"),
                            "quote": ((p.get("source_evidence") or [{}])[0]).get("quote", "")[:600]}
                           for p in batch], ensure_ascii=False)}]}
            request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                             data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                             headers={"Authorization": "Bearer " + api_key,
                                                      "Content-Type": "application/json"})
            stats["calls"] += 1
            try:
                response = request_json(request, 180, journal=journal, stage="precision",
                                        proposal_ids=[p["id"] for p in batch])
                choice = (response.get("choices") or [{}])[0]
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Reponse de precision interrompue.")
                scores = parse_scores((choice.get("message") or {}).get("content"), [p["id"] for p in batch])
            except (OSError, ValueError, KeyError) as exc:
                stats["failed_batches"] += 1
                print(f"ERREUR precision (lot de {len(batch)}): {exc}", file=sys.stderr)
                continue
            for p in batch:
                cache[cache_key(model, p)] = scores[p["id"]]
                result[p["id"]] = scores[p["id"]]
            pc.save_json(cache_path, cache)
        return result
    return score_batch


def main() -> int:
    from pipeline_scoring_2027 import is_openrouter_jev_model, load_env_file
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("propositions_programmes_2027.json"))
    parser.add_argument("--out", type=Path, default=Path("selection_precision_2027.json"))
    parser.add_argument("--cache-file", type=Path, default=Path("cache_precision_2027.json"))
    parser.add_argument("--candidate", action="append", default=[], help="Limiter a un candidat (repetable), ex. pilote")
    parser.add_argument("--per-theme", type=int, default=8)
    parser.add_argument("--tolerance", type=float, default=25.0, help="Ecart moyen heuristique/LLM (0..100) declenchant la pioche")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--model", help="Defaut: OPENROUTER_WEB_MODEL du .env")
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-call", type=float, default=DEFAULT_COST_PER_CALL)
    args = parser.parse_args()
    journal = None
    try:
        if min(args.per_theme, args.max_rounds, args.batch_size) < 1 or args.max_cost < 0:
            raise ValueError("Options invalides.")
        load_env_file(Path(__file__).with_name(".env"))
        model = (args.model or os.getenv("OPENROUTER_WEB_MODEL", "")).strip()
        if not model or model.endswith(":online") or is_openrouter_jev_model(model):
            raise ValueError("Definir OPENROUTER_WEB_MODEL (ou --model) : modele chat, pas Jev Decisions.")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        proposals = [p for p in data["proposals"] if not args.candidate or p["candidate_id"] in args.candidate]
        if not proposals:
            raise ValueError("Aucune proposition pour cette selection de candidats.")
        pools = sel.ordered_pools(proposals)
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        first = [t[2] for pool in pools.values() for t in pool[:args.per_theme]]
        todo = [p for p in first if cache_key(model, p) not in cache]
        calls = math.ceil(len(todo) / args.batch_size)
        print(f"Plan: {len(pools)} groupes, {len(first)} propositions au tour 1 ({len(first) - len(todo)} en cache), "
              f"{calls} appels ~ {calls * args.cost_per_call:.2f} $ ; tours suivants selon la divergence "
              f"(prevoir jusqu'a ~50 % de plus), modele {model}.")
        if args.max_cost <= 0:
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
        journal = LLMJournal(secrets=(key,))
        stats = {"calls": 0, "cached": 0, "failed_batches": 0}
        scorer = make_scorer(model, key, journal, cache, args.cache_file, args.batch_size, args.max_cost,
                             args.cost_per_call, stats)
        result = run_loop(pools, scorer, per_theme=args.per_theme, tolerance=args.tolerance,
                          max_rounds=args.max_rounds)
        spent = journal_cost(journal.path)
        result["report"].update(stats, cost=round(spent, 4), per_theme=args.per_theme, tolerance=args.tolerance,
                                model=model)
        pc.save_json(args.out, result)
        print(json.dumps(result["report"], ensure_ascii=False, indent=2))
        return 2 if stats["failed_batches"] or result["report"]["exhausted_budget"] else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur precision: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
