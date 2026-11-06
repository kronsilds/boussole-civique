"""Selection (gratuite, sans LLM) des propositions a scorer, par precision.

Reprend la typologie de l'amont : chiffre / precis / orientation_generale, estimee par heuristique sur le
titre, la description et la citation. Retient au plus N propositions par candidat et par theme, les plus
precises d'abord, en ecartant les quasi-doublons. Ecrit selection_scoring_2027.json (identifiants + precision).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

UNITS = (r"%|€|euros?|md|mds|milliards?|millions?|m€|ans?|mois|jours?|heures?|h\b|semaines?|annees?|années?|"
         r"places?|postes?|logements?|km|mw|gw|tw|lits?|classes?|enseignants?|policiers?|gendarmes?|agents?|"
         r"habitants?|communes?|salaries?|salariés?|personnes?|etablissements?|établissements?|ecoles?|écoles?|"
         r"departements?|départements?|mandats?|reacteurs?|réacteurs?|epr2?|hectares?|tonnes?|points?|fois|pour cent")
WORD_NUMBER = (r"(?:un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|quinze|vingt|trente|quarante|"
               r"cinquante|soixante|cent|mille|million|milliard|moitie|moitié|tiers|quart|double|triple)")
NUMBER_UNIT = re.compile(r"(?:\d[\d\s.,]*|\b" + WORD_NUMBER + r"\b[\s-]*)\s*(?:" + UNITS + r")\b", re.I)
DIGIT = re.compile(r"\d")
DEADLINE = re.compile(r"\b(d'ici|dès|des|avant|en|a partir de|à partir de)\s+(20\d\d|\d+\s+(ans|mois|jours))", re.I)
CONCRETE = re.compile(
    r"\b(supprim|interdi|cré|instaur|rétabli|retabli|abrog|porter|fixer|plafonn|baiss|augment|relev|"
    r"nationalis|rembours|exon|taxe|impôt|impot|loi\b|référendum|referendum|quota|obligation|sanction|"
    r"ouvrir|construire|recruter|embaucher|indexer|généralis|generalis)", re.I)
VAGUE = re.compile(
    r"\b(soutenir|promouvoir|favoriser|encourager|défendre|defendre|veiller|valoriser|accompagner|"
    r"sensibiliser|réfléchir|reflechir|engager une réflexion|mener une politique|lutter contre|agir pour)\b", re.I)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def precision_score(p: dict[str, Any]) -> tuple[int, str]:
    """Score entier et etiquette (chiffre / precis / orientation_generale)."""
    quote = ((p.get("source_evidence") or [{}])[0]).get("quote", "")
    text = " ".join([p.get("title", ""), p.get("description", ""), quote])
    score = 0
    numeric = bool(NUMBER_UNIT.search(text))
    if numeric:
        score += 4
    elif DIGIT.search(p.get("title", "") + " " + p.get("description", "")):
        score += 2
    if DEADLINE.search(text):
        score += 1
    if CONCRETE.search(p.get("title", "") + " " + p.get("description", "")):
        score += 2
    if VAGUE.search(p.get("description", "")) and not numeric:
        score -= 2
    if len(p.get("description", "")) < 50:
        score -= 1
    label = "chiffre" if numeric else "precis" if score >= 2 else "orientation_generale"
    return score, label


def _tokens(title: str) -> set[str]:
    return {t for t in _norm(title).split() if len(t) > 3}


def ordered_pools(proposals: list[dict[str, Any]]) -> dict[tuple[str, str], list[tuple[int, str, dict[str, Any]]]]:
    """Par (candidat, theme) : propositions triees par precision heuristique, quasi-doublons retires."""
    groups: dict[tuple[str, str], list[tuple[int, str, dict[str, Any]]]] = defaultdict(list)
    for p in proposals:
        score, label = precision_score(p)
        groups[(p["candidate_id"], p["theme_id"])].append((score, label, p))
    pools = {}
    for key, items in groups.items():
        items.sort(key=lambda t: (-t[0], -len(t[2].get("description", "")), t[2]["id"]))
        kept: list[tuple[int, str, dict[str, Any]]] = []
        kept_tokens: list[set[str]] = []
        for score, label, p in items:
            tokens = _tokens(p.get("title", ""))
            if any(tokens and len(tokens & other) / len(tokens | other) > .6 for other in kept_tokens):
                continue
            kept.append((score, label, p))
            kept_tokens.append(tokens)
        pools[key] = kept
    return pools


def select(proposals: list[dict[str, Any]], per_theme: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chosen = []
    for (candidate, theme), items in sorted(ordered_pools(proposals).items()):
        kept = items[:per_theme]
        for score, label, p in kept:
            chosen.append({"id": p["id"], "candidate_id": candidate, "theme_id": theme,
                           "precision": label, "precision_score": score})
    stats = {"total_proposals": len(proposals), "selected": len(chosen), "per_theme": per_theme,
             "by_precision": dict(Counter(c["precision"] for c in chosen)),
             "by_candidate": dict(sorted(Counter(c["candidate_id"] for c in chosen).items()))}
    return chosen, stats


CULTURAL_THEMES = ("immigration", "securite", "famille", "institutions", "europe", "culture")


def extend_selection(proposals: list[dict[str, Any]], base: list[dict[str, Any]],
                     themes: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Garde la selection de base (marquee n8) et y ajoute toutes les propositions des themes donnes, quasi-doublons
    ecartes (marquees theme_complet). L'affichage peut se limiter a n8 ; les moyennes utilisent l'ensemble."""
    chosen = [{**b, "selection": "n8"} for b in base]
    known = {b["id"] for b in base}
    for (candidate, theme), items in sorted(ordered_pools(proposals).items()):
        if theme not in themes:
            continue
        for score, label, p in items:
            if p["id"] not in known:
                chosen.append({"id": p["id"], "candidate_id": candidate, "theme_id": theme, "precision": label,
                               "precision_score": score, "selection": "theme_complet"})
                known.add(p["id"])
    stats = {"base": len(base), "added": len(chosen) - len(base), "selected": len(chosen), "full_themes": list(themes),
             "added_by_candidate": dict(sorted(Counter(c["candidate_id"] for c in chosen
                                                       if c["selection"] == "theme_complet").items()))}
    return chosen, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("propositions_programmes_2027.json"))
    parser.add_argument("--out", type=Path, default=Path("selection_scoring_2027.json"))
    parser.add_argument("--per-theme", type=int, default=12, help="Maximum par candidat et par theme (defaut: 12)")
    parser.add_argument("--base", type=Path, help="Selection existante a etendre (ex. selection_precision_2027.json)")
    parser.add_argument("--full-themes", nargs="*", default=None,
                        help="Avec --base : themes ajoutes en entier (defaut : themes culturels)")
    args = parser.parse_args()
    if args.per_theme < 1:
        print("Erreur: --per-theme doit etre >= 1.", file=sys.stderr)
        return 2
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if args.base:
        base = json.loads(args.base.read_text(encoding="utf-8"))["selected"]
        chosen, stats = extend_selection(data["proposals"], base, tuple(args.full_themes or CULTURAL_THEMES))
    else:
        chosen, stats = select(data["proposals"], args.per_theme)
    args.out.write_text(json.dumps({"meta": stats, "selected": chosen}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
