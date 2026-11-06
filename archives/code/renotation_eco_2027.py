"""Pilote : renotation de l'axe economique avec des reperes intermediaires (-75, -25, +25, +75).

Constat (2026-11-06) : avec cinq reperes (-100 collectivisation, -50 redistribution, 0, +50, +100), les notes collent
a -50 et cinq candidats de gauche tiennent en 5,5 points, alors qu'aucun ne propose de collectivisation. Ce pilote
renote, a l'aveugle, un echantillon de mesures des themes economiques selon deux baremes et avec le meme modele :
- eco9 : neuf reperes (nouveau) ;
- eco5 : les cinq reperes actuels (temoin, pour separer l'effet du bareme de celui du modele).

N'ecrit rien dans les donnees du projet : produit un rapport (pilotes/pilote_eco9_2027.json). Sans --max-cost, plan seul.
Cache propre (cache_eco9_2027.json), cle = modele + proposition + bareme.
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
from pathlib import Path
from typing import Any

import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import relecture_ciblee_2027 as rc
import revision_2027 as rv
from axes_2027 import BudgetExhausted, blind_item, blind_names
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import request_json
from update_corpus_2027 import journal_cost

VERSION = 1
ECO9_ANCHORS = {
    "-100": "Collectivisation : nationalisations larges, expropriation, réquisition ou abolition du profit privé",
    "-75": "Intervention forte de l'État ou rupture : nationalisation ciblée d'une entreprise ou d'un secteur, blocage "
           "ou contrôle des prix, forte hausse du salaire minimum ou des minima sociaux, planification, interdiction "
           "des licenciements, imposition très lourde des hauts patrimoines ou revenus",
    "-50": "Redistribution : taxation accrue du capital ou des hauts revenus, hausse des salaires ou prestations, "
           "extension des services publics, régulation renforcée des marchés",
    "-25": "Correctif social modéré : ajustement ciblé d'une prestation, d'un service public ou d'une protection, "
           "sans changement d'ampleur",
    "0": "Mesure mixte, équilibrant intervention publique et incitations de marché",
    "25": "Allègement ciblé : baisse limitée d'un impôt ou d'une charge, simplification administrative, incitation de "
          "marché",
    "50": "Baisse d'impôts ou de charges, réduction des dépenses publiques, flexibilité du travail ou allègement des "
          "réglementations",
    "75": "Libéralisation forte : baisse générale et forte des impôts ou des dépenses, privatisation d'une entreprise "
          "ou ouverture d'un secteur à la concurrence, suppression d'une protection importante du travail",
    "100": "Libéralisation radicale : privatisations massives, suppression d'impôts majeurs ou démantèlement de "
           "protections sociales",
}
BAREMES = ("eco9", "eco5")

INSTRUCTIONS = (
    "Tu notes, sans connaitre leur auteur, des propositions de programmes politiques. Ne cherche pas a deviner le "
    "candidat et n'utilise aucune connaissance sur les partis. Pour chaque proposition (theme, title, description, "
    "quote), note uniquement la dimension eco selon le bareme `rubric` : un entier dans `range`, en choisissant le "
    "repere de `anchors` dont la description correspond le mieux a la mesure (une valeur entre deux reperes voisins est "
    "permise si la mesure est entre les deux) ; null si la condition `applies_if` n'est pas remplie.\n"
    "Donne une confiance entre 0 et 1, puis une note d'audit tres breve (120 caracteres maximum) qui dit pourquoi ce "
    "repere plutot que ses voisins.\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"eco\": "
    "{\"value\": ..., \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu."
)

# Echantillon par defaut : les cinq candidats de gauche resserres (objet du pilote), Arthaud pour l'extreme, et
# quelques mesures des autres pour verifier que les reperes de droite et +-25 ne derivent pas.
DEFAULT_PLAN = {"roussel": 8, "melenchon": 8, "ruffin": 8, "glucksmann": 8, "tondelier": 8, "arthaud": 4}
DEFAULT_OTHERS = 2
DEFAULT_COST_PER_ITEM = 0.00074  # mesure des pilotes GPT-6.1 Terra medium du 2026-11-05 (appel direct)


def rubric(bareme: str) -> dict[str, Any]:
    entry = rv.rubric(["eco"])["eco"]
    if bareme == "eco9":
        entry = {**entry, "anchors": dict(ECO9_ANCHORS)}
    elif bareme != "eco5":
        raise ValueError(f"Bareme inconnu : {bareme}")
    return {"eco": entry}


def cache_key(model: str, bareme: str, item: dict[str, Any]) -> str:
    return rv.digest({"v": VERSION, "model": model, "item": item, "rubric": rubric(bareme), "instructions": INSTRUCTIONS})


def select_sample(displayed: list[dict[str, Any]], plan: dict[str, int], others: int, seed: int) -> list[dict[str, Any]]:
    """Mesures affichees, des themes economiques, avec une note eco ; tirage aleatoire reproductible par candidat."""
    pool: dict[str, list[dict[str, Any]]] = {}
    for p in displayed:
        if p.get("t") in rc.ECONOMIC_THEMES and (p.get("v") or {}).get("eco") is not None:
            pool.setdefault(p["c"], []).append(p)
    rng = random.Random(seed)
    sample = []
    for cand in sorted(pool):
        group = sorted(pool[cand], key=lambda p: p["id"])
        sample += rng.sample(group, min(plan.get(cand, others), len(group)))
    return sample


def make_item(proposal: dict[str, Any], names: set[str]) -> dict[str, Any]:
    item = blind_item(proposal, names)
    item["id"] = rc.short_id(proposal["id"])
    item["dimensions"] = ["eco"]
    return item


def payload(model: str, bareme: str, items: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    body = {"rubric": rubric(bareme), "proposals": items}
    out = {"model": model, "messages": [{"role": "user", "content": INSTRUCTIONS + "\n" + json.dumps(body, ensure_ascii=False)}]}
    out.update(rc.payload_hook(effort)(items, ["eco"]))
    return {k: v for k, v in out.items() if v is not None}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(xs: list[int]) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        return {"n": len(xs), "moyenne": round(statistics.mean(xs), 1), "mediane": statistics.median(xs),
                "part_sous_-60": round(sum(x <= -60 for x in xs) / len(xs), 2),
                "part_-55_-45": round(sum(-55 <= x <= -45 for x in xs) / len(xs), 2)}
    out: dict[str, Any] = {}
    for cand in sorted({r["c"] for r in rows}):
        sub = [r for r in rows if r["c"] == cand]
        out[cand] = {key: stats([r[key] for r in sub if r.get(key) is not None])
                     for key in ("actuelle", "eco5", "eco9")}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("donnees_programmes_2027.json"))
    parser.add_argument("--interface", type=Path, default=Path("donnees_interface_2027.json"),
                        help="Mesures affichees et notes actuelles (echantillonnage)")
    parser.add_argument("--out", type=Path, default=Path("pilotes/pilote_eco9_2027.json"))
    parser.add_argument("--cache-file", type=Path, default=Path("cache_eco9_2027.json"))
    parser.add_argument("--model", default="openai/gpt-6.1-terra")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--baremes", default="eco9,eco5", help="eco9 (nouveau), eco5 (temoin) ou les deux")
    parser.add_argument("--others", type=int, default=DEFAULT_OTHERS, help="Mesures par candidat hors plan par defaut")
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-cost", type=float, default=0.0, help="Budget en dollars ; 0 = plan seul")
    parser.add_argument("--cost-per-item", type=float, default=DEFAULT_COST_PER_ITEM)
    args = parser.parse_args()
    journal = None
    try:
        baremes = [b.strip() for b in args.baremes.split(",") if b.strip()]
        if not baremes or any(b not in BAREMES for b in baremes) or args.batch_size < 1 or args.max_cost < 0:
            raise ValueError("Options invalides.")
        if ps.is_openrouter_jev_model(args.model) or args.model.endswith(":online"):
            raise ValueError("Modele chat attendu (ni Jev Decisions, ni :online).")
        ps.load_env_file(Path(__file__).with_name(".env"))
        displayed = json.loads(args.interface.read_text(encoding="utf-8"))["proposals"]
        sample = select_sample(displayed, DEFAULT_PLAN, args.others, args.seed)
        data = json.loads(args.input.read_text(encoding="utf-8"))
        by_id = {p["id"]: p for p in data["proposals"]}
        names = blind_names(data.get("candidates", []))
        missing = [s["id"] for s in sample if s["id"] not in by_id]
        if missing:
            raise ValueError(f"{len(missing)} mesures de l'interface absentes de {args.input}.")
        items = [make_item(by_id[s["id"]], names) for s in sample]
        if len({i["id"] for i in items}) != len(items):
            raise ValueError("Identifiants courts en collision.")
        cache = json.loads(args.cache_file.read_text(encoding="utf-8")) if args.cache_file.exists() else {}
        todo = {b: [i for i in items if cache_key(args.model, b, i) not in cache] for b in baremes}
        n_todo = sum(len(v) for v in todo.values())
        calls = sum(math.ceil(len(v) / args.batch_size) for v in todo.values())
        counts: dict[str, int] = {}
        for s in sample:
            counts[s["c"]] = counts.get(s["c"], 0) + 1
        print(f"Echantillon : {len(sample)} mesures {counts}")
        print(f"Plan : baremes {baremes}, {n_todo} notations a faire ({len(items) * len(baremes) - n_todo} en cache), "
              f"{calls} appels, estimation {n_todo * args.cost_per_item:.3f} $, modele {args.model}, "
              f"raisonnement {args.reasoning_effort}.")
        if n_todo and args.max_cost <= 0:
            print("Aucun appel lance (pas de --max-cost). Pour autoriser : --max-cost <dollars>.")
            return 0
        if n_todo:
            key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not key:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(key,))
            n_calls = 0
            for bareme in baremes:
                pending = todo[bareme]
                for start in range(0, len(pending), args.batch_size):
                    lot = pending[start:start + args.batch_size]
                    spent = journal_cost(journal.path)
                    per_call = spent / n_calls if n_calls else args.cost_per_item * len(lot)
                    if spent + per_call > args.max_cost:
                        raise BudgetExhausted()
                    request = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=json.dumps(payload(args.model, bareme, lot, args.reasoning_effort), ensure_ascii=False).encode("utf-8"),
                        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                    n_calls += 1
                    try:
                        response = request_json(request, 300, journal=journal, stage=f"pilote_{bareme}",
                                                proposal_ids=[i["id"] for i in lot])
                        reviews = rv.parse_completion(response, lot, {})
                    except (OSError, ValueError, KeyError) as exc:
                        print(f"ERREUR lot {bareme} ({len(lot)}) : {exc}", file=sys.stderr)
                        continue
                    for item in lot:
                        if item["id"] in reviews:
                            cache[cache_key(args.model, bareme, item)] = reviews[item["id"]]
                    pc.save_json(args.cache_file, cache)
        rows = []
        for s, item in zip(sample, items):
            row = {"id": s["id"], "c": s["c"], "t": s["t"], "title": s["title"], "actuelle": s["v"]["eco"],
                   "methode_actuelle": (s.get("meth") or {}).get("eco")}
            for bareme in baremes:
                hit = cache.get(cache_key(args.model, bareme, item))
                if hit:
                    a = hit["assessments"].get("eco") or {}
                    row[bareme], row[bareme + "_confiance"], row[bareme + "_note"] = a.get("value"), a.get("confidence"), hit["note"]
            rows.append(row)
        done = {b: sum(b in r for r in rows) for b in baremes}
        report = {"modele": args.model, "raisonnement": args.reasoning_effort, "seed": args.seed, "baremes": baremes,
                  "notes_obtenues": done, "cout": round(journal_cost(journal.path), 4) if journal else 0.0,
                  "reperes_eco9": ECO9_ANCHORS, "par_candidat": summarize(rows), "mesures": rows}
        pc.save_json(args.out, report)
        print(json.dumps({k: report[k] for k in ("notes_obtenues", "cout", "par_candidat")}, ensure_ascii=False, indent=1))
        return 0 if all(v == len(rows) for v in done.values()) else 2
    except BudgetExhausted:
        print("Plafond atteint : arret, cache conserve.", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur pilote eco9: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
