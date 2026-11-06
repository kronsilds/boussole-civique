"""Axes complementaires mesures par LLM, proposition par proposition et sans identite du candidat.

Axes : ideologie economique / societale / souverainete / ecologie (-100..100, null si non applicable), instrument
juridique requis (categorie), horizon d'effet (categorie), ampleur de la rupture (0..100), droits financiers scindes
en direction (-100..100) et ampleur des beneficiaires (0..100). Un court commentaire d'audit accompagne chaque note.

Entree : selection_precision_2027.json (ou toutes les propositions avec --all). Sortie : axes_2027.json.
Sans --max-cost, plan seul (aucun appel). Cache par proposition et modele : relancer ne repaie rien.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import programme_corpus_2027 as pc
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import digest, request_json
from update_corpus_2027 import journal_cost

INSTRUCTION_VERSION = 1
DEFAULT_COST_PER_CALL = 0.003  # lot de 10 : ~1 000 tokens en entree, ~600 en sortie avec un modele peu couteux

SIGNED_AXES = ("eco", "soc", "sov", "ecolo", "income_direction")
UNSIGNED_AXES = ("rupture", "income_breadth")
LEGAL_INSTRUMENTS = ("decret_ou_arrete", "loi_ordinaire", "loi_de_finances_ou_securite_sociale", "loi_organique",
                     "revision_constitutionnelle", "traite_europeen_ou_international", "non_identifiable")
HORIZONS = ("immediat_moins_1_an", "mandat_1_a_5_ans", "long_terme_plus_5_ans", "non_precise")
FIELDS = {*SIGNED_AXES, *UNSIGNED_AXES, "legal_instrument", "horizon", "note"}

AXES_INSTRUCTIONS = (
    "Tu mesures des propositions de programmes politiques, une par une, sans connaitre leur auteur : ne cherche pas a "
    "deviner le candidat et n'utilise aucune connaissance externe. Pour chaque proposition (titre, description, citation), "
    "donne ces champs ; un champ numerique vaut null quand l'axe ne s'applique pas a la mesure.\n"
    "- eco (-100..100) orientation economique : -100 rupture anticapitaliste ou collectivisation ; -50 redistribution, taxation "
    "du capital, extension des services publics ; 0 mixte ou neutre ; +50 baisse d'impots et de charges, reduction des depenses, "
    "flexibilite ; +100 liberalisation radicale, privatisation massive.\n"
    "- soc (-100..100) orientation societale : -100 extension maximale des libertes et des droits individuels ; -50 liberalisme "
    "culturel moderee ; 0 neutre ; +50 conservatisme moral ou ordre renforce ; +100 restriction forte des libertes au nom de la "
    "norme ou de l'ordre.\n"
    "- sov (-100..100) souverainete et ouverture : -100 integration europeenne ou internationale poussee, ouverture maximale ; "
    "0 neutre ; +100 nationalisme, sortie ou rupture des traites, priorite nationale, fermeture.\n"
    "- ecolo (-100..100) priorite environnementale : -100 priorite a la production et a l'activite contre les contraintes "
    "environnementales ; 0 neutre ; +100 priorite maximale a la protection de l'environnement, transition contraignante.\n"
    "- rupture (0..100) ampleur du changement par rapport au droit et aux pratiques existants : 0 simple ajustement de parametre "
    "ou statu quo ; 50 reforme significative d'un dispositif ; 100 refonte structurelle, abrogation ou creation d'une institution.\n"
    "- income_direction (-100..100) effet sur les revenus ou l'acces financier des menages : -100 baisse ou restriction forte ; "
    "0 sans effet ; +100 hausse ou ouverture forte. null si aucun effet financier direct sur les menages.\n"
    "- income_breadth (0..100) part de la population concernee par cet effet : 0 micro-categorie ; 50 categorie large ; 100 "
    "universel. null si income_direction est null.\n"
    "- legal_instrument : exactement une valeur parmi " + ", ".join(LEGAL_INSTRUMENTS) + " (le texte juridique minimal pour "
    "mettre la mesure en oeuvre).\n"
    "- horizon : exactement une valeur parmi " + ", ".join(HORIZONS) + " (delai d'effet annonce ou raisonnablement implicite).\n"
    "- note : une phrase de 140 caracteres maximum justifiant les notes les plus marquantes.\n"
    "Reponds uniquement par l'objet JSON {\"scores\": [{\"id\": \"...\", \"eco\": 0, \"soc\": null, ...}]} avec tous les champs "
    "pour chaque identifiant recu, sans texte additionnel."
)


class BudgetExhausted(Exception):
    pass


def _check(value: Any, low: int, high: int, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Axe {name}: entier ou null attendu.")
    if not low <= value <= high:
        raise ValueError(f"Axe {name} hors plage {low}..{high}.")
    return int(value)


def parse_axes(content: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
    parsed = pc.parse_json_object(content, "Axes")
    items = parsed.get("scores")
    if set(parsed) != {"scores"} or not isinstance(items, list):
        raise ValueError("Reponse d'axes invalide: objet {'scores': [...]} attendu.")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != FIELDS | {"id"}:
            raise ValueError("Element d'axes invalide: champs manquants ou en trop.")
        if item["id"] in result:
            raise ValueError("Identifiant d'axes en double.")
        row: dict[str, Any] = {name: _check(item[name], -100, 100, name) for name in SIGNED_AXES}
        row.update({name: _check(item[name], 0, 100, name) for name in UNSIGNED_AXES})
        if row["income_direction"] is None:
            row["income_breadth"] = None
        if item["legal_instrument"] not in LEGAL_INSTRUMENTS:
            raise ValueError("Instrument juridique inconnu.")
        if item["horizon"] not in HORIZONS:
            raise ValueError("Horizon inconnu.")
        if not isinstance(item["note"], str):
            raise ValueError("Note d'audit invalide.")
        row.update(legal_instrument=item["legal_instrument"], horizon=item["horizon"], note=item["note"][:200])
        result[item["id"]] = row
    if set(result) != set(ids):
        raise ValueError("Les identifiants d'axes ne correspondent pas au lot envoye.")
    return result


def blind_item(p: dict[str, Any], names: set[str]) -> dict[str, Any]:
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?!\w)",
                         re.I) if names else None

    def mask(text: Any) -> Any:
        return pattern.sub("[le candidat]", text) if pattern and isinstance(text, str) else text
    quote = ((p.get("source_evidence") or [{}])[0]).get("quote", "")[:600]
    return {"id": p["id"], "theme": p.get("theme_id"), "title": mask(p.get("title")), "description": mask(p.get("description")),
            "quote": mask(quote)}


def blind_names(candidates: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for c in candidates or []:
        for key in ("last_name", "party", "party_short", "name", "movement"):
            value = str(c.get(key) or "").strip()
            if len(value) >= 3:
                names.add(value)
        full = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        if len(full) >= 3:
            names.add(full)
    return names


def cache_key(model: str, item: dict[str, Any]) -> str:
    return digest({"v": INSTRUCTION_VERSION, "model": model, "item": item})


def score_all(items: list[dict[str, Any]], score_batch, batch_size: int) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        scores.update(score_batch(batch))
    return scores


def make_scorer(model: str, api_key: str, journal: LLMJournal, cache: dict[str, Any], cache_path: Path,
                max_cost: float, cost_per_call: float, stats: dict[str, int]):
    def score_batch(batch: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        todo = []
        for item in batch:
            key = cache_key(model, item)
            if key in cache:
                result[item["id"]] = cache[key]
                stats["cached"] += 1
            else:
                todo.append(item)
        if not todo:
            return result
        spent = journal_cost(journal.path)
        per_call = spent / stats["calls"] if stats["calls"] else cost_per_call
        if spent + per_call > max_cost:
            raise BudgetExhausted()
        payload = {"model": model, "temperature": 0, "max_tokens": 6000, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": AXES_INSTRUCTIONS + "\n" + json.dumps(todo, ensure_ascii=False)}]}
        request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        stats["calls"] += 1
        try:
            response = request_json(request, 180, journal=journal, stage="axes", proposal_ids=[i["id"] for i in todo])
            choice = (response.get("choices") or [{}])[0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Reponse d'axes interrompue.")
            scores = parse_axes((choice.get("message") or {}).get("content"), [i["id"] for i in todo])
        except (OSError, ValueError, KeyError) as exc:
            stats["failed_batches"] += 1
            print(f"ERREUR axes (lot de {len(todo)}): {exc}", file=sys.stderr)
            return result
        for item in todo:
            cache[cache_key(model, item)] = scores[item["id"]]
            result[item["id"]] = scores[item["id"]]
        pc.save_json(cache_path, cache)
        return result
    return score_batch


def main() -> int:
    from pipeline_scoring_2027 import is_openrouter_jev_model, load_env_file
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("propositions_programmes_2027.json"))
    parser.add_argument("--selection", type=Path, default=Path("selection_precision_2027.json"))
    parser.add_argument("--all", action="store_true", help="Toutes les propositions, sans passer par la selection")
    parser.add_argument("--candidate", action="append", default=[], help="Limiter a un candidat (repetable), ex. pilote")
    parser.add_argument("--limit", type=int, default=0, help="Ne traiter que les N premieres propositions (pilote)")
    parser.add_argument("--out", type=Path, default=Path("axes_2027.json"))
    parser.add_argument("--cache-file", type=Path, default=Path("cache_axes_2027.json"))
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--model", help="Defaut: OPENROUTER_WEB_MODEL du .env")
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-call", type=float, default=DEFAULT_COST_PER_CALL)
    args = parser.parse_args()
    journal = None
    try:
        if args.batch_size < 1 or args.limit < 0 or args.max_cost < 0:
            raise ValueError("Options invalides.")
        load_env_file(Path(__file__).with_name(".env"))
        model = (args.model or os.getenv("OPENROUTER_WEB_MODEL", "")).strip()
        if not model or model.endswith(":online") or is_openrouter_jev_model(model):
            raise ValueError("Definir OPENROUTER_WEB_MODEL (ou --model) : modele chat, pas Jev Decisions.")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        proposals = data["proposals"]
        if not args.all:
            wanted = {x["id"] for x in json.loads(args.selection.read_text(encoding="utf-8"))["selected"]}
            proposals = [p for p in proposals if p["id"] in wanted]
        if args.candidate:
            proposals = [p for p in proposals if p["candidate_id"] in args.candidate]
        if args.limit:
            proposals = proposals[:args.limit]
        if not proposals:
            raise ValueError("Aucune proposition a mesurer.")
        names = blind_names(data.get("candidates", []))
        items = [blind_item(p, names) for p in proposals]
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        todo = [i for i in items if cache_key(model, i) not in cache]
        calls = math.ceil(len(todo) / args.batch_size)
        print(f"Plan: {len(items)} propositions ({len(items) - len(todo)} en cache), {calls} appels ~ "
              f"{calls * args.cost_per_call:.2f} $, modele {model}.")
        if args.max_cost <= 0:
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
        journal = LLMJournal(secrets=(key,))
        stats = {"calls": 0, "cached": 0, "failed_batches": 0}
        scorer = make_scorer(model, key, journal, cache, args.cache_file, args.max_cost, args.cost_per_call, stats)
        exhausted = False
        try:
            scores = score_all(items, scorer, args.batch_size)
        except BudgetExhausted:
            exhausted = True
            scores = {i["id"]: cache[cache_key(model, i)] for i in items if cache_key(model, i) in cache}
        spent = journal_cost(journal.path)
        report = {**stats, "scored": len(scores), "requested": len(items), "cost": round(spent, 4),
                  "exhausted_budget": exhausted, "model": model}
        pc.save_json(args.out, {"meta": report, "scores": scores})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if stats["failed_batches"] or exhausted else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur axes: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
