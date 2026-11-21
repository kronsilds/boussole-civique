"""Export allege des donnees pour l'interface (constellation) : seuls les champs affiches, cles courtes.

Entree : sortie du scoring (Jev, ou Jev + revision), ex. donnees_programmes_2027.json ou scores_jev_etendu_2027.json.
La selection (selection_etendue_2027.json) fournit le marqueur d'affichage n8 / theme_complet et la precision.
Sortie : donnees_interface_2027.json, lu par constellation_2027.html. Aucun appel reseau.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pipeline_scoring_2027 as ps
import questionnaire_q2_2027 as Q2

SCALES = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rupture", "revenu_position", "revenu_effet",
          "revenu_redistrib")
TOP_SCALES = ("rights_income", "rights_status", "feasibility", "budget_net_bn_year")
CATEGORIES = ("legal_instrument", "horizon", "cost_estimate")
# Ajouts de q2, exportes seulement quand ils ont une valeur (les mesures lues en q1 n'en ont pas : export inchange).
SCALES_Q2 = ("inst", "inter", "defense")
CATEGORIES_Q2 = ("financement",)
METHODS = {"jev-calibrated": "jev", "revision-chat": "revision", "relecture-ciblee": "relecture", "corpus-structure": "corpus",
           "axes-composite": "derive"}


def short(text: Any, limit: int) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def compact(p: dict[str, Any], marker: dict[str, Any] | None) -> dict[str, Any]:
    axes = p.get("axes") or {}
    details = p.get("score_details") or {}
    evidence = (p.get("source_evidence") or [{}])[0]
    values = {k: axes.get(k) for k in SCALES}
    values.update({k: p.get(k) for k in TOP_SCALES})
    values.update({k: axes[k] for k in SCALES_Q2 if axes.get(k) is not None})
    cats = {k: axes.get(k) for k in CATEGORIES}
    cats.update({k: axes[k] for k in CATEGORIES_Q2 if axes.get(k) is not None})
    dims = [*SCALES, *TOP_SCALES, *CATEGORIES, *SCALES_Q2, *CATEGORIES_Q2]
    row: dict[str, Any] = {
        "id": p["id"], "c": p["candidate_id"], "t": p["theme_id"],
        "sel": (marker or {}).get("selection") or p.get("selection") or "n8",
        "title": short(p.get("title"), 160), "desc": short(p.get("description"), 500),
        "quote": short(evidence.get("quote"), 500), "url": p.get("source_url"), "src": short(p.get("source_title"), 140),
        "page": p.get("source_page"), "date": p.get("source_date"),
        "imp": p.get("importance"), "imp_src": p.get("importance_sources"),
        "prec": (marker or {}).get("precision") or p.get("precision"),
        "prec_llm": (marker or {}).get("precision_llm", p.get("precision_llm")),
        "v": values, "cat": cats,
        "conf": {k: (details.get(k) or {}).get("confidence") for k in dims if (details.get(k) or {}).get("confidence") is not None},
        "meth": {k: METHODS.get((details.get(k) or {}).get("method"), (details.get(k) or {}).get("method"))
                 for k in dims if (details.get(k) or {}).get("method")},
        "tags": p.get("threshold_tags") or [],
    }
    if p.get("indicateurs"):   # indicateurs de frequence (antidiscrimination), comptes par candidat dans la constellation
        row["ind"] = p["indicateurs"]
    revision = p.get("revision")
    relecture = p.get("relecture_ciblee") if isinstance(p.get("relecture_ciblee"), dict) else {}
    if isinstance(revision, dict) or relecture:
        revision = revision if isinstance(revision, dict) else {}
        reread = [*(revision.get("dimensions") or []), *[d for d in relecture.get("dimensions") or [] if d in SCALES]]
        row["rev"] = {"note": revision.get("note"),
                      "dis": sorted({*(revision.get("disagreements") or []), *(relecture.get("disagreements") or [])}),
                      "jev": {k: (details.get(k) or {}).get("jev_value") for k in dict.fromkeys(reread)}}
    if relecture:
        row["rel"] = {"note": relecture.get("note"), "dims": relecture.get("dimensions") or []}
    return row


def schema_q2() -> dict[str, Any]:
    """Dimensions ajoutees par q2 (axes contre-pouvoirs, alliances, defense ; financement), au format du schema."""
    out: dict[str, Any] = {}
    for k, q in (("inst", "inst_controle"), ("inter", "int_alliances"), ("defense", "def_effort")):
        label, low, high = Q2.AXES[k]
        out[k] = {"label": label, "field": f"axes.{k}", "question": Q2.QUESTIONS[q]["question"], "type": "scale",
                  "range": [-100, 100], "low_label": low, "high_label": high,
                  "null_means": "non applicable : la mesure ne touche pas cet aspect"}
    f = Q2.QUESTIONS["financement"]
    out["financement"] = {"label": f["libelle"], "field": "axes.financement", "question": f["question"], "type": "category",
                          "options": f["options"], "null_means": "non applicable : pas de coût (ou coût inconnu)"}
    out["feasibility_q2"] = {"label": "Faisabilité (q2)", "field": "feasibility", "type": "derived", "range": [0, 100],
                             "formula": ("calculée, sans question propre : selon le texte nécessaire (décret 100, loi 50, traité 25, "
                                         "révision constitutionnelle 0), un cran de plus pour une loi au coût ou au gain "
                                         "faible, un cran de moins pour une rupture qui passe par un traité ou pour un "
                                         "coût massif dont le financement n'est pas désigné")}
    return out


def export(data: dict[str, Any], selection: list[dict[str, Any]] | None) -> dict[str, Any]:
    markers = {s["id"]: s for s in selection or []}
    proposals = [p for p in data["proposals"] if not markers or p["id"] in markers]
    candidates = [{**{k: c.get(k) for k in ("id", "name", "first_name", "last_name", "party_short", "movement", "color",
                                           "initials", "status")},
                   **({"retrait": c["retrait"]} if c.get("retrait") else {})}  # candidat retire : date, soutien, source
                  for c in data.get("candidates", [])]
    themes = [{k: t.get(k) for k in ("id", "label", "short", "icon", "description")} for t in data.get("themes", [])]
    return {
        "meta": {"source": data.get("meta", {}).get("pipeline"), "revision": data.get("meta", {}).get("revision"),
                 "proposals": len(proposals), "note": "Valeurs inconnues = null (jamais 0). Notes à valider humainement."},
        "schema": {**ps.dimensions_schema(), **schema_q2()}, "candidates": candidates, "themes": themes,
        "proposals": [compact(p, markers.get(p["id"])) for p in proposals],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--selection", type=Path, help="Sélection donnant le marqueur n8 / theme_complet")
    parser.add_argument("--out", type=Path, default=Path("donnees_interface_2027.json"))
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        selection = json.loads(args.selection.read_text(encoding="utf-8"))["selected"] if args.selection else None
        result = export(data, selection)
        args.out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Écrit {args.out}: {len(result['proposals'])} propositions, {args.out.stat().st_size / 1e6:.1f} Mo.")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erreur export: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
