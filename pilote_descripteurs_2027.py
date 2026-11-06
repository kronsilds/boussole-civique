"""Pilote (etape 2 de spec_descripteurs_2027.md) : descripteurs factuels et note eco calculee.

Echantillon : les 60 mesures du pilote eco9 (pilotes/pilote_eco9_2027.json, comparaison directe) et 40 mesures hors
economie (8 par theme : institutions, securite, europe, immigration, culture). 30 d'entre elles sont relues une seconde
fois, dans des lots d'une autre composition, pour mesurer la stabilite de chaque question.

Questions (descripteurs_2027.QUESTIONS) posees a l'aveugle pour toutes les mesures : levier, public_vise, portee ;
eco_etat et eco_distrib avec null si l'axe economique ne s'applique pas (condition has_eco). La note eco est calculee
(descripteurs_2027.eco_score) avec rupture et cost_estimate deja notes.

N'ecrit rien dans les donnees du projet : rapport pilotes/pilote_descripteurs_2027.json et cache propre. Sans
--max-cost, plan seul.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import descripteurs_2027 as D
import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import relecture_ciblee_2027 as rc
import revision_2027 as rv
from axes_2027 import BudgetExhausted, blind_item, blind_names
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import dimension_value, request_json
from update_corpus_2027 import journal_cost

VERSION = 1
COMMON = ("levier", "public_vise", "portee")
ECO = ("eco_etat", "eco_distrib")
QUESTIONS = COMMON + ECO
OTHER_THEMES = ("institutions", "securite", "europe", "immigration", "culture")
DEFAULT_COST_PER_ITEM = 0.0008  # estimation : pilote eco9 a 0,00048 $ pour une question, ici cinq questions courtes

_HEAD = (
    "Tu decris, sans connaitre leur auteur, des propositions de programmes politiques. Ne cherche pas a deviner le "
    "candidat et n'utilise aucune connaissance sur les partis. Pour chaque proposition (theme, title, description, "
    "quote), reponds a chaque question du bareme `rubric` en choisissant exactement une cle de `options`. Pour les "
    "questions qui ont une condition `applies_if`, reponds null si la condition n'est pas remplie. ")
_TAIL = (
    "\nDonne pour chaque question une confiance entre 0 et 1, puis une note d'audit tres breve (120 caracteres maximum) "
    "sur le choix le plus hesitant.\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"question\": "
    "{\"value\": \"...\", \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu."
)
# Premiere lecture du pilote (2026-11-06) : conservee pour retrouver le cache deja paye.
INSTRUCTIONS_V1 = _HEAD + "Decris ce que la mesure fait, pas l'intention affichee." + _TAIL
# Correctif : une orientation seulement annoncee (« mettre fin au capitalisme ») perdait son sens et son axe.
INSTRUCTIONS = _HEAD + (
    "`levier` et `portee` decrivent le moyen reellement prevu : un objectif sans moyen precise est une declaration. "
    "Les questions de sens (`eco_etat`, `eco_distrib`) decrivent l'orientation de la mesure, meme si elle est seulement "
    "annoncee : un objectif economique declare (abolir le capitalisme, reduire la dette, socialiser l'economie) remplit "
    "la condition `applies_if` et a un sens. Reponds inchange_ou_mixte ou neutre seulement si l'orientation est "
    "reellement mixte ou nulle, pas parce que les moyens manquent.") + _TAIL
# Mesures relues par --correctif : declarations, sens nul ou axe economique perdu en premiere lecture.
def needs_fix(first: dict[str, Any], eco_actuelle: Any) -> bool:
    a = {q: first["assessments"][q]["value"] for q in QUESTIONS}
    return (a["levier"] == "declaration_ou_symbole" or (a["eco_etat"] == "inchange_ou_mixte" and a["eco_distrib"] == "neutre")
            or (eco_actuelle is not None and a["eco_etat"] is None))


def rubric() -> dict[str, Any]:
    gate = ps.TYPESAFE_QUESTIONS["has_eco"]["instructions"]
    out = {}
    for q in QUESTIONS:
        spec = D.QUESTIONS[q]
        out[q] = {"question": spec["instructions"], "options": spec["criteria"]}
        if q in ECO:
            out[q]["applies_if"] = gate
    return out


def response_schema() -> dict[str, Any]:
    def value(q: str) -> dict[str, Any]:
        options = list(D.QUESTIONS[q]["criteria"])
        return {"type": ["string", "null"], "enum": options + [None]} if q in ECO else {"type": "string", "enum": options}
    assessment = {q: {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                      "properties": {"value": value(q), "confidence": {"type": "number"}}} for q in QUESTIONS}
    review = {"type": "object", "additionalProperties": False, "required": ["id", "assessments", "note"],
              "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                             "assessments": {"type": "object", "additionalProperties": False, "required": list(QUESTIONS),
                                             "properties": assessment}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "items": review}}}


def payload(model: str, items: list[dict[str, Any]], effort: str, instructions: str = INSTRUCTIONS) -> dict[str, Any]:
    body = {"rubric": rubric(), "proposals": items}
    return {"model": model, "max_tokens": 24000, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "descripteurs", "strict": True,
                                                                        "schema": response_schema()}},
            "messages": [{"role": "user", "content": instructions + "\n" + json.dumps(body, ensure_ascii=False)}]}


def cache_key(model: str, item: dict[str, Any], reading: int, instructions: str = INSTRUCTIONS_V1) -> str:
    return rv.digest({"v": VERSION, "model": model, "item": item, "reading": reading, "rubric": rubric(),
                      "instructions": instructions})


def parse(response: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reponse -> {id court: {question: (valeur, confiance)}, note} ; une entree invalide est ecartee."""
    choice = (response.get("choices") or [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choice.get("message") or {}).get("content"), "Descripteurs").get("reviews")
    if not isinstance(items, list):
        raise ValueError("Objet {'reviews': [...]} attendu.")
    wanted = {i["id"] for i in lot}
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in wanted or item["id"] in out:
            continue
        a = item.get("assessments") or {}
        clean = {}
        for q in QUESTIONS:
            entry = a.get(q)
            if not isinstance(entry, dict):
                break
            value, conf = entry.get("value"), entry.get("confidence")
            if (value is None and q not in ECO) or (value is not None and value not in D.QUESTIONS[q]["criteria"]):
                break
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                break
            clean[q] = {"value": value, "confidence": round(float(conf), 2)}
        else:
            out[item["id"]] = {"assessments": clean, "note": str(item.get("note") or "")[:160]}
    if not out:
        raise ValueError("Aucune description valide.")
    return out


def select_sample(eco9_rows: list[dict[str, Any]], displayed: list[dict[str, Any]], per_theme: int,
                  seed: int) -> list[dict[str, Any]]:
    ids = {r["id"] for r in eco9_rows}
    by_id = {p["id"]: p for p in displayed}
    sample = [by_id[i] for i in (r["id"] for r in eco9_rows) if i in by_id]
    rng = random.Random(seed)
    for theme in OTHER_THEMES:
        pool = sorted((p for p in displayed if p.get("t") == theme and p["id"] not in ids), key=lambda p: p["id"])
        sample += rng.sample(pool, min(per_theme, len(pool)))
    return sample


def make_item(proposal: dict[str, Any], names: set[str]) -> dict[str, Any]:
    item = blind_item(proposal, names)
    item["id"] = rc.short_id(proposal["id"])
    return item


def agreement(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for q in QUESTIONS:
        pairs = [(first[k]["assessments"][q]["value"], second[k]["assessments"][q]["value"]) for k in second if k in first]
        out[q] = round(sum(a == b for a, b in pairs) / len(pairs), 2) if pairs else None
    return out


def build_report(sample, items, full, eco9_by_id, cache_get, double_ids, fixed_get=lambda item: None) -> dict[str, Any]:
    rows, first, second = [], {}, {}
    for s, item in zip(sample, items):
        hit = cache_get(item, 1)
        if hit:
            first[item["id"]] = hit  # stabilite mesuree sur la premiere lecture (meme consigne que la seconde)
        fixed = fixed_get(item)
        row = {"id": s["id"], "c": s["c"], "t": s["t"], "title": s["title"], "eco_actuelle": (s.get("v") or {}).get("eco"),
               "eco9": (eco9_by_id.get(s["id"]) or {}).get("eco9"), "corrigee": fixed is not None}
        if fixed:
            row["premiere_lecture"] = {q: hit["assessments"][q]["value"] for q in QUESTIONS} if hit else None
            hit = fixed
        if hit:
            desc = {q: hit["assessments"][q]["value"] for q in QUESTIONS}
            desc["rupture"] = dimension_value(full[s["id"]], "rupture")
            desc["cost_estimate"] = dimension_value(full[s["id"]], "cost_estimate")
            value, detail = D.eco_score(desc)
            row.update(descripteurs=desc, confiances={q: hit["assessments"][q]["confidence"] for q in QUESTIONS},
                       eco_calculee=value, explication=detail.get("explication"), note=hit["note"])
        if item["id"] in double_ids:
            hit2 = cache_get(item, 2)
            if hit2:
                second[item["id"]] = hit2
                row["seconde_lecture"] = {q: hit2["assessments"][q]["value"] for q in QUESTIONS}
        rows.append(row)
    calc = [r["eco_calculee"] for r in rows if r.get("eco_calculee") is not None]
    e9 = [r["eco9"] for r in rows if r.get("eco9") is not None]
    both = [r for r in rows if r.get("eco_calculee") is not None and r.get("eco9") is not None]

    def spread(xs):
        if not xs:
            return {"n": 0}
        top = Counter(xs).most_common(1)[0]
        return {"n": len(xs), "valeurs_distinctes": len(set(xs)), "pic": top[0], "part_du_pic": round(top[1] / len(xs), 2)}
    by_cand = {}
    for cand in sorted({r["c"] for r in rows}):
        sub = [r for r in rows if r["c"] == cand]
        by_cand[cand] = {k: (round(statistics.mean(v), 1) if v else None, len(v)) for k, v in
                         {key: [r[key] for r in sub if r.get(key) is not None]
                          for key in ("eco_actuelle", "eco9", "eco_calculee")}.items()}
    gate = [r for r in rows if r.get("descripteurs") and r["t"] in rc.ECONOMIC_THEMES | set(OTHER_THEMES)]
    return {
        "lectures": {"premiere": len(first), "seconde": len(second), "attendues": [len(items), len(double_ids)],
                     "corrigees": sum(r["corrigee"] for r in rows)},
        "stabilite": agreement(first, second),
        "paliers": {"eco_calculee": spread(calc), "eco9": spread(e9)},
        "accord_eco9": {"n": len(both), "part_moins_de_25_points": round(sum(abs(r["eco_calculee"] - r["eco9"]) <= 25
                                                                             for r in both) / len(both), 2) if both else None,
                        "plus_gros_ecarts": sorted(({"title": r["title"], "c": r["c"], "eco9": r["eco9"],
                                                     "eco_calculee": r["eco_calculee"], "explication": r["explication"]}
                                                    for r in both), key=lambda x: -abs(x["eco_calculee"] - x["eco9"]))[:12]},
        "condition_eco": {"eco_actuelle_renseignee_mais_null": sum(r["eco_actuelle"] is not None and r["descripteurs"]["eco_etat"] is None for r in gate),
                          "eco_actuelle_absente_mais_repondu": sum(r["eco_actuelle"] is None and r["descripteurs"]["eco_etat"] is not None for r in gate)},
        "repartitions": {q: dict(Counter(r["descripteurs"][q] for r in rows if r.get("descripteurs")).most_common())
                         for q in QUESTIONS},
        "par_candidat_moyenne_n": by_cand,
        "mesures": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("donnees_programmes_2027.json"))
    parser.add_argument("--interface", type=Path, default=Path("donnees_interface_2027.json"))
    parser.add_argument("--eco9", type=Path, default=Path("pilotes/pilote_eco9_2027.json"))
    parser.add_argument("--out", type=Path, default=Path("pilotes/pilote_descripteurs_2027.json"))
    parser.add_argument("--cache-file", type=Path, default=Path("cache_descripteurs_2027.json"))
    parser.add_argument("--model", default="openai/gpt-6.1-terra")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--per-theme", type=int, default=8)
    parser.add_argument("--double", type=int, default=30, help="Mesures relues deux fois (stabilite)")
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-item", type=float, default=DEFAULT_COST_PER_ITEM)
    parser.add_argument("--correctif", action="store_true",
                        help="Relit avec la consigne corrigee les mesures declaratives, sans sens ou sorties de l'axe")
    args = parser.parse_args()
    journal = None
    try:
        if args.batch_size < 1 or args.max_cost < 0 or args.double < 0:
            raise ValueError("Options invalides.")
        if ps.is_openrouter_jev_model(args.model) or args.model.endswith(":online"):
            raise ValueError("Modele chat attendu (ni Jev Decisions, ni :online).")
        ps.load_env_file(Path(__file__).with_name(".env"))
        eco9_rows = json.loads(args.eco9.read_text(encoding="utf-8"))["mesures"]
        displayed = json.loads(args.interface.read_text(encoding="utf-8"))["proposals"]
        sample = select_sample(eco9_rows, displayed, args.per_theme, args.seed)
        data = json.loads(args.input.read_text(encoding="utf-8"))
        full = {p["id"]: p for p in data["proposals"]}
        missing = [s["id"] for s in sample if s["id"] not in full]
        if missing:
            raise ValueError(f"{len(missing)} mesures absentes de {args.input}.")
        names = blind_names(data.get("candidates", []))
        items = [make_item(full[s["id"]], names) for s in sample]
        if len({i["id"] for i in items}) != len(items):
            raise ValueError("Identifiants courts en collision.")
        rng = random.Random(args.seed + 1)
        double_items = rng.sample(items, min(args.double, len(items)))
        double_ids = {i["id"] for i in double_items}
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        eco_now = {rc.short_id(s["id"]): (s.get("v") or {}).get("eco") for s in sample}
        fix_items = [i for i in items if (h := cache.get(cache_key(args.model, i, 1))) and needs_fix(h, eco_now[i["id"]])]
        todo = [  # (etape, lecture, consigne, mesures)
            ("premiere", 1, INSTRUCTIONS_V1, [i for i in items if cache_key(args.model, i, 1) not in cache]),
            ("seconde", 2, INSTRUCTIONS_V1,  # autre ordre, autres lots
             [i for i in reversed(double_items) if cache_key(args.model, i, 2) not in cache]),
            ("correctif", 1, INSTRUCTIONS,
             [i for i in fix_items if cache_key(args.model, i, 1, INSTRUCTIONS) not in cache] if args.correctif else [])]
        n_todo = sum(len(t[3]) for t in todo)
        calls = sum(math.ceil(len(t[3]) / args.batch_size) for t in todo)
        if args.correctif:
            print(f"Correctif : {len(fix_items)} mesures a relire avec la consigne corrigee.")
        themes = Counter(s["t"] for s in sample)
        print(f"Echantillon : {len(sample)} mesures ({sum(1 for s in sample if s['t'] in rc.ECONOMIC_THEMES)} economiques "
              f"du pilote eco9 ; hors economie {dict((t, themes[t]) for t in OTHER_THEMES)}), {len(double_ids)} relues deux fois.")
        print(f"Plan : {n_todo} lectures a faire ({len(items) + len(double_ids) - n_todo} en cache), {calls} appels, "
              f"estimation {n_todo * args.cost_per_item:.3f} $, modele {args.model}, raisonnement {args.reasoning_effort}.")
        if n_todo and args.max_cost <= 0:
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        if n_todo:
            key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not key:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(key,))
            n_calls = 0
            for stage, reading, instructions, pending in todo:
                for start in range(0, len(pending), args.batch_size):
                    lot = pending[start:start + args.batch_size]
                    spent = journal_cost(journal.path)
                    per_call = spent / n_calls if n_calls else args.cost_per_item * len(lot)
                    if spent + per_call > args.max_cost:
                        raise BudgetExhausted()
                    request = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=json.dumps(payload(args.model, lot, args.reasoning_effort, instructions), ensure_ascii=False).encode("utf-8"),
                        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                    n_calls += 1
                    try:
                        response = request_json(request, 300, journal=journal, stage=f"pilote_descripteurs_{stage}",
                                                proposal_ids=[i["id"] for i in lot])
                        results = parse(response, lot)
                    except (OSError, ValueError, KeyError) as exc:
                        print(f"ERREUR lot {stage} ({len(lot)}) : {exc}", file=sys.stderr)
                        continue
                    for item in lot:
                        if item["id"] in results:
                            cache[cache_key(args.model, item, reading, instructions)] = results[item["id"]]
                    pc.save_json(args.cache_file, cache)
        eco9_by_id = {r["id"]: r for r in eco9_rows}
        report = build_report(sample, items, full, eco9_by_id,
                              lambda item, reading: cache.get(cache_key(args.model, item, reading)), double_ids,
                              lambda item: cache.get(cache_key(args.model, item, 1, INSTRUCTIONS)))
        report = {"modele": args.model, "raisonnement": args.reasoning_effort, "seed": args.seed,
                  "cout": round(journal_cost(journal.path), 4) if journal else 0.0, **report}
        pc.save_json(args.out, report)
        print(json.dumps({k: report[k] for k in ("cout", "lectures", "stabilite", "paliers", "condition_eco")},
                         ensure_ascii=False, indent=1))
        complete = report["lectures"]["premiere"] == len(items) and report["lectures"]["seconde"] == len(double_ids)
        return 0 if complete else 2
    except BudgetExhausted:
        print("Plafond atteint : arret, cache conserve.", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur pilote descripteurs: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
