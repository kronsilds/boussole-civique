"""Comparaison de deux modeles (ou efforts) sur la methode standard de notation (lecture avec contexte).

Les deux lisent exactement les memes mesures, avec les memes elements (proposition, passage du document, lexique) et
la meme consigne que la production (contexte_2027). Par defaut, l'echantillon est celui du premier essai de contexte
(runs/pilote_contexte_2027.json : 50 mesures en confiance basse, 20 avec un mot ambigu), pour garder la comparaison
stable meme si la base a change depuis. S'y ajoute un groupe « representatif » (--n-representatif, 30 par defaut) :
des mesures actives tirees au hasard (graine fixe), hors de cet echantillon, a tour de role entre candidats pour que
chacun soit present.

  python .\\comparer_modeles_2027.py                                   # plan : aucun appel, rapport sur le cache
  python .\\comparer_modeles_2027.py --max-cost 0.5                    # lectures manquantes, plafond total
  python .\\comparer_modeles_2027.py --candidat openai/gpt-6-luna:medium

Les lectures de reference deja payees en production (donnees/cache_contexte_2027.json) sont reprises ; les nouvelles
vont dans donnees/cache_comparaison_modeles_2027.json. Le rapport ne dit pas qui a raison : il montre ou les deux
lectures divergent, avec la note de chacune, pour un jugement humain.
Rapport : runs/comparaison_modeles_2027.{json,md}.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import annotation_2027 as A
import base_2027 as B
import boussole_2027 as BO
import contexte_2027 as CX
import pipeline_scoring_2027 as ps
import questionnaire_2027 as Q
from commun_2027 import blind_names

AXES = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rights_status")


def config(texte: str) -> tuple[str, str]:
    modele, _, effort = texte.rpartition(":")
    if not modele or effort not in ("minimal", "low", "medium", "high"):
        raise argparse.ArgumentTypeError("format attendu : modele:effort (ex. openai/gpt-6-luna:high)")
    return modele, effort


def usage(journal: Path) -> dict[str, float]:
    """Jetons et cout reels cumules d'un journal JSONL."""
    tot = Counter()
    if journal.exists():
        for ligne in journal.read_text(encoding="utf-8").splitlines():
            try:
                u = (json.loads(ligne).get("response") or {}).get("usage") or {}
            except (ValueError, AttributeError):
                continue
            tot["cout"] += float(u.get("cost") or 0)
            tot["entree"] += int(u.get("prompt_tokens") or 0)
            tot["sortie"] += int(u.get("completion_tokens") or 0)
            tot["raisonnement"] += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    return dict(tot)


def valeurs(review: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return ({k: e["value"] for k, e in review["assessments"].items()},
            {k: e["confidence"] for k, e in review["assessments"].items()})


def comparer(ref: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    ra, ca = valeurs(ref)
    rb, cb = valeurs(cand)
    va, _ = Q.calculer(ra)
    vb, _ = Q.calculer(rb)
    deltas = {x: (va.get(x), vb.get(x)) for x in AXES if va.get(x) != vb.get(x)}
    ecart = max((abs(b - a) for a, b in deltas.values() if a is not None and b is not None), default=0)
    doute = lambda r, c: [k for k in CX.SENS if r.get(k) != Q.INDETERMINE and c.get(k) is not None and c[k] < CX.SEUIL]  # noqa: E731
    return {"differences": {k: (ra.get(k), rb.get(k)) for k in Q.QUESTIONS if ra.get(k) != rb.get(k)},
            "sens_differe": [k for k in CX.SENS if ra.get(k) != rb.get(k)],
            "indetermine": ([k for k in CX.SENS if ra.get(k) == Q.INDETERMINE], [k for k in CX.SENS if rb.get(k) == Q.INDETERMINE]),
            "doutes": (doute(ra, ca), doute(rb, cb)),
            "confiance_sens": (sum(ca.get(k) or 0 for k in CX.SENS) / len(CX.SENS), sum(cb.get(k) or 0 for k in CX.SENS) / len(CX.SENS)),
            "deltas": deltas, "ecart_max": ecart,
            "axe_present_d_un_cote": [x for x, (a, b) in deltas.items() if (a is None) != (b is None)],
            "notes": (ref.get("note"), cand.get("note"))}


def representatif(base: dict[str, Any], exclus: set[str], n: int, graine: int) -> list[str]:
    """n mesures actives annotees, hors `exclus`, tirees au hasard a tour de role entre candidats (tirage reproductible)."""
    rng = random.Random(graine)
    par_candidat: dict[str, list[str]] = {}
    for m in base["mesures"]:
        if m["statut"] == "active" and m.get("annotation") and m["uid"] not in exclus:
            par_candidat.setdefault(m["candidate_id"], []).append(m["uid"])
    files = []
    for cand in sorted(par_candidat):
        uids = sorted(par_candidat[cand])
        rng.shuffle(uids)
        files.append(uids)
    rng.shuffle(files)
    out: list[str] = []
    while len(out) < n and any(files):
        for f in files:
            if f and len(out) < n:
                out.append(f.pop())
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--racine", default=".")
    p.add_argument("--echantillon", default="runs/pilote_contexte_2027.json", help="rapport d'essai dont on reprend les mesures (uid)")
    p.add_argument("--reference", type=config, default=("openai/gpt-6.1-terra", "low"))
    p.add_argument("--candidat", type=config, default=("openai/gpt-6-luna", "high"))
    p.add_argument("--n-representatif", type=int, default=30, help="mesures tirees au hasard hors de l'echantillon d'essai")
    p.add_argument("--graine", type=int, default=2027)
    p.add_argument("--max-cost", type=float, default=0.0, help="plafond total des deux lectures ; 0 = plan, aucun appel")
    args = p.parse_args()
    c = BO.chemins(args)
    base = BO.charger_base(c)
    rapport_echantillon = B.lire_json(Path(args.racine) / args.echantillon, {})
    groupes = {x["uid"]: x["groupe"] for x in rapport_echantillon.get("mesures") or []}
    if not groupes:
        raise SystemExit(f"Echantillon vide ou introuvable : {args.echantillon}")
    par_uid = {m["uid"]: m for m in base["mesures"]}
    groupes.update({u: "representatif" for u in representatif(base, set(groupes), args.n_representatif, args.graine)})
    absentes = [u for u in groupes if u not in par_uid]
    decisions = B.lire_json(c["decisions"], []) if "decisions" in c else []
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    mesures = [par_uid[u] for u in groupes if u in par_uid]
    items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
    cache_prod = B.lire_json(c["cache_contexte"], {})
    cache_path = c["donnees"] / "cache_comparaison_modeles_2027.json"
    cache = B.lire_json(cache_path, {})
    lecture = lambda conf, it: cache.get(CX.cle(conf[0], it, conf[1])) or cache_prod.get(CX.cle(conf[0], it, conf[1]))  # noqa: E731
    confs = {"reference": args.reference, "candidat": args.candidat}
    a_lire = {n: [it for it in items if not lecture(conf, it)] for n, conf in confs.items()}
    print(f"Echantillon : {len(items)} mesures ({dict(Counter(groupes[m['uid']] for m in mesures))}), "
          f"{len(absentes)} absentes de la base, {sum('lexique' in it for it in items)} avec lexique.")
    for n, conf in confs.items():
        print(f"  {n} {conf[0]} ({conf[1]}) : {len(items) - len(a_lire[n])} en cache, {len(a_lire[n])} a lire.")
    couts: dict[str, dict[str, float]] = {}
    if any(a_lire.values()) and args.max_cost <= 0:
        print("Aucun appel (--max-cost pour lancer) ; rapport sur les lectures deja en cache.")
    elif any(a_lire.values()):
        from llm_logging_2027 import LLMJournal
        ps.load_env_file(Path(__file__).with_name(".env"))
        cle_api = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not cle_api:
            raise SystemExit("OPENROUTER_API_KEY manque ; aucun appel lance.")
        reste = args.max_cost
        for n, conf in confs.items():
            if not a_lire[n]:
                continue
            journal = LLMJournal(secrets=(cle_api,))
            try:
                lots = [a_lire[n][i:i + A.TAILLE_LOT] for i in range(0, len(a_lire[n]), A.TAILLE_LOT)]
                stats = CX.relire_direct(lots, conf[0], conf[1], cle_api, journal, cache, reste,
                                         ecrire=lambda x: B.ecrire_json(cache_path, x))
            finally:
                journal.close()
            couts[n] = {**usage(journal.path), "mesures_lues": stats["relues"], "echecs": stats["echecs"]}
            reste -= couts[n].get("cout", 0.0)
            print(f"  {n} : {stats['relues']} lues, {stats['echecs']} lots en echec, cout reel {couts[n].get('cout', 0):.4f} $")
    lignes = []
    for m, it in zip(mesures, items):
        ref, cand = lecture(args.reference, it), lecture(args.candidat, it)
        if ref and cand:
            lignes.append({"uid": m["uid"], "groupe": groupes[m["uid"]], "titre": m["versions"][-1]["title"],
                           "lexique": "lexique" in it, **comparer(ref, cand)})
    n = len(lignes)
    synthese: dict[str, Any] = {"mesures_comparees": n}
    if n:
        q_diff = Counter(q for x in lignes for q in x["differences"])
        synthese.update({
            "accord_sens_complet": sum(not x["sens_differe"] for x in lignes),
            "accord_par_question": {q: round(1 - q_diff[q] / n, 3) for q in Q.QUESTIONS},
            "indetermine": [sum(bool(x["indetermine"][i]) for x in lignes) for i in (0, 1)],
            "doutes_de_sens": [sum(bool(x["doutes"][i]) for x in lignes) for i in (0, 1)],
            "confiance_sens_moyenne": [round(sum(x["confiance_sens"][i] for x in lignes) / n, 3) for i in (0, 1)],
            "ecart_axe_25_plus": sum(x["ecart_max"] >= 25 for x in lignes),
            "axe_present_d_un_seul_cote": sum(bool(x["axe_present_d_un_cote"]) for x in lignes),
            "par_groupe": {g: {"mesures": sum(x["groupe"] == g for x in lignes),
                               "accord_sens_complet": sum(x["groupe"] == g and not x["sens_differe"] for x in lignes)}
                           for g in sorted({x["groupe"] for x in lignes})},
        })
    rapport = {"reference": "%s:%s" % args.reference, "candidat": "%s:%s" % args.candidat, "echantillon": args.echantillon,
               "couts_ce_run": couts, "synthese": synthese, "mesures": lignes}
    B.ecrire_json(c["runs"] / "comparaison_modeles_2027.json", rapport)
    ref_n, cand_n = rapport["reference"], rapport["candidat"]
    md = [f"# Comparaison : {ref_n} (reference) / {cand_n} (candidat)", "",
          "Memes mesures, memes elements (proposition, passage, lexique), meme consigne. Paires : (reference, candidat).", "",
          "```", json.dumps({"couts_ce_run": couts, **synthese}, ensure_ascii=False, indent=1), "```", "",
          "## Divergences sur les questions de sens ou ecart d'axe de 25 points et plus", ""]
    for x in sorted(lignes, key=lambda x: -x["ecart_max"]):
        if x["sens_differe"] or x["ecart_max"] >= 25:
            diff = ", ".join(f"{k} {a} → {b}" for k, (a, b) in x["differences"].items() if k in x["sens_differe"])
            md += [f"- [{x['groupe']}] {x['uid']} — {x['titre'][:100]}", f"  - sens : {diff or '—'} ; axes {x['deltas']}",
                   f"  - reference : {x['notes'][0]}", f"  - candidat : {x['notes'][1]}"]
    (c["runs"] / "comparaison_modeles_2027.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(synthese, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
