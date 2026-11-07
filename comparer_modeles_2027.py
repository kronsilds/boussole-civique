"""Comparaison de modeles (ou d'efforts) sur la methode standard de notation (lecture avec contexte).

Tous lisent exactement les memes mesures, avec les memes elements (proposition, passage du document, lexique) et
la meme consigne que la production (contexte_2027). Par defaut, l'echantillon est celui du premier essai de contexte
(runs/pilote_contexte_2027.json : 50 mesures en confiance basse, 20 avec un mot ambigu), pour garder la comparaison
stable meme si la base a change depuis. S'y ajoute un groupe « representatif » (--n-representatif, 30 par defaut) :
des mesures actives tirees au hasard (graine fixe), hors de cet echantillon, a tour de role entre candidats pour que
chacun soit present.

  python .\\comparer_modeles_2027.py                                   # plan : aucun appel, rapport sur le cache
  python .\\comparer_modeles_2027.py --max-cost 0.5                    # lectures manquantes, plafond total
  python .\\comparer_modeles_2027.py --candidat openai/gpt-6-luna:high openai/gpt-6-luna:low --repetitions 2 --max-cost 0.45

Avec --repetitions 2, chaque modele lit deux fois les memes mesures (meme requete, appel distinct) : l'accord d'un
modele avec lui-meme donne la base de bruit a laquelle comparer l'accord entre modeles.
Les lectures deja payees en production (donnees/cache_contexte_2027.json) sont reprises comme premiere lecture ; les
nouvelles vont dans donnees/cache_comparaison_modeles_2027.json. Le rapport ne dit pas qui a raison : il montre ou les
lectures divergent, avec la note de chacune, pour un jugement humain.
Rapport : runs/comparaison_modeles_2027.{json,md}.
"""
from __future__ import annotations

import argparse
import json
import os
import random
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
from scoring_context_2027 import digest

AXES = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rights_status")
# Cout par mesure pour le plafond avant chaque lot (mesure le 2026-11-07) ; le cout reel du journal prime.
COUT_PAR_MESURE = {"openai/gpt-6.1-terra": .003, "openai/gpt-6-luna": .001}


def config(texte: str) -> tuple[str, str]:
    modele, _, effort = texte.rpartition(":")
    if not modele or effort not in ("minimal", "low", "medium", "high"):
        raise argparse.ArgumentTypeError("format attendu : modele:effort (ex. openai/gpt-6-luna:high)")
    return modele, effort


def nom(conf: tuple[str, str]) -> str:
    return f"{conf[0].split('/')[-1]}:{conf[1]}"


def cle_lecture(conf: tuple[str, str], it: dict[str, Any], repetition: int) -> str:
    """Lecture 0 : cle de production (lectures deja payees reprises) ; suivantes : meme requete, cle distincte."""
    cle = CX.cle(conf[0], it, conf[1])
    return cle if repetition == 0 else digest({"cle": cle, "repetition": repetition})


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
            "eco": (va.get("eco"), vb.get("eco")),
            "deltas": deltas, "ecart_max": ecart,
            "axe_present_d_un_cote": [x for x, (a, b) in deltas.items() if (a is None) != (b is None)],
            "notes": (ref.get("note"), cand.get("note"))}


def synthese(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(lignes)
    out: dict[str, Any] = {"mesures_comparees": n}
    if not n:
        return out
    q_diff = Counter(q for x in lignes for q in x["differences"])
    eco = [abs(b - a) for x in lignes for a, b in [x["eco"]] if a is not None and b is not None]
    out.update({
        "accord_sens_complet": sum(not x["sens_differe"] for x in lignes),
        "accord_par_question": {q: round(1 - q_diff[q] / n, 3) for q in Q.QUESTIONS},
        "indetermine": [sum(bool(x["indetermine"][i]) for x in lignes) for i in (0, 1)],
        "ecart_eco_absolu_moyen": round(sum(eco) / len(eco), 1) if eco else None,
        "ecart_axe_25_plus": sum(x["ecart_max"] >= 25 for x in lignes),
        "axe_present_d_un_seul_cote": sum(bool(x["axe_present_d_un_cote"]) for x in lignes),
        "par_groupe": {g: {"mesures": sum(x["groupe"] == g for x in lignes),
                           "accord_sens_complet": sum(x["groupe"] == g and not x["sens_differe"] for x in lignes)}
                       for g in sorted({x["groupe"] for x in lignes})},
    })
    return out


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
    p.add_argument("--candidat", type=config, nargs="+", default=[("openai/gpt-6-luna", "high")])
    p.add_argument("--repetitions", type=int, default=1, help="lectures par modele (2 : mesure du bruit)")
    p.add_argument("--n-representatif", type=int, default=30, help="mesures tirees au hasard hors de l'echantillon d'essai")
    p.add_argument("--graine", type=int, default=2027)
    p.add_argument("--max-cost", type=float, default=0.0, help="plafond total de ce run ; 0 = plan, aucun appel")
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
    decisions = B.lire_json(c["decisions"], [])
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    mesures = [par_uid[u] for u in groupes if u in par_uid]
    items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
    cache_prod = B.lire_json(c["cache_contexte"], {})
    cache_path = c["donnees"] / "cache_comparaison_modeles_2027.json"
    cache = B.lire_json(cache_path, {})

    def lecture(conf, it, r=0):
        k = cle_lecture(conf, it, r)
        return cache.get(k) or (cache_prod.get(k) if r == 0 else None)

    confs = [args.reference] + [x for x in args.candidat if x != args.reference]
    taches = [(conf, r) for conf in confs for r in range(args.repetitions)]
    a_lire = {t: [it for it in items if not lecture(t[0], it, t[1])] for t in taches}
    estimation = sum(len(v) * COUT_PAR_MESURE.get(t[0][0], CX.COUT_ESTIME) for t, v in a_lire.items())
    print(f"Echantillon : {len(items)} mesures ({dict(Counter(groupes[m['uid']] for m in mesures))}), "
          f"{len(absentes)} absentes de la base, {sum('lexique' in it for it in items)} avec lexique.")
    for (conf, r), v in a_lire.items():
        print(f"  {nom(conf)} lecture {r + 1} : {len(items) - len(v)} en cache, {len(v)} a lire.")
    print(f"Estimation : {estimation:.2f} $ (plafond {args.max_cost} $).")
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
        for (conf, r), v in a_lire.items():
            if not v or reste <= 0:
                continue
            par_cle = {CX.cle(conf[0], it, conf[1]): cle_lecture(conf, it, r) for it in v}

            def ecrire(tmp, par_cle=par_cle):  # resultats ranges sous la cle de cette lecture ; cache ecrit apres chaque lot
                cache.update({par_cle[k]: x for k, x in tmp.items() if k in par_cle})
                B.ecrire_json(cache_path, cache)

            journal = LLMJournal(secrets=(cle_api,))
            try:
                lots = [v[i:i + A.TAILLE_LOT] for i in range(0, len(v), A.TAILLE_LOT)]
                stats = CX.relire_direct(lots, conf[0], conf[1], cle_api, journal, {}, reste, ecrire=ecrire,
                                         cout_estime=COUT_PAR_MESURE.get(conf[0]))
            finally:
                journal.close()
            k = f"{nom(conf)} lecture {r + 1}"
            couts[k] = {**usage(journal.path), "mesures_lues": stats["relues"], "echecs": stats["echecs"]}
            reste -= couts[k].get("cout", 0.0)
            print(f"  {k} : {stats['relues']} lues, {stats['echecs']} lots en echec, cout reel {couts[k].get('cout', 0):.4f} $")

    def paires(t1, t2):
        out = []
        for m, it in zip(mesures, items):
            a, b = lecture(t1[0], it, t1[1]), lecture(t2[0], it, t2[1])
            if a and b:
                out.append({"uid": m["uid"], "groupe": groupes[m["uid"]], "titre": m["versions"][-1]["title"],
                            "lexique": "lexique" in it, **comparer(a, b)})
        return out

    stabilite = {nom(conf): synthese(paires((conf, 0), (conf, 1))) for conf in confs} if args.repetitions >= 2 else {}
    croise = {f"{nom(a)} / {nom(b)}": paires((a, 0), (b, 0)) for i, a in enumerate(confs) for b in confs[i + 1:]}
    rapport = {"modeles": [nom(x) for x in confs], "repetitions": args.repetitions, "echantillon": args.echantillon,
               "couts_ce_run": couts, "stabilite": stabilite, "croise": {k: synthese(v) for k, v in croise.items()},
               "mesures": croise}
    B.ecrire_json(c["runs"] / "comparaison_modeles_2027.json", rapport)
    md = [f"# Comparaison de modeles : {', '.join(nom(x) for x in confs)}", "",
          "Memes mesures, memes elements (proposition, passage, lexique), meme consigne. Paires : (premier, second).",
          "Stabilite : accord d'un modele avec sa propre seconde lecture (base de bruit).", "",
          "```", json.dumps({"couts_ce_run": couts, "stabilite": stabilite, "croise": rapport["croise"]}, ensure_ascii=False, indent=1),
          "```", ""]
    for titre, lignes in croise.items():
        md += [f"## {titre} : divergences de sens ou ecart d'axe de 25 points et plus", ""]
        for x in sorted(lignes, key=lambda x: -x["ecart_max"]):
            if x["sens_differe"] or x["ecart_max"] >= 25:
                diff = ", ".join(f"{k} {a} → {b}" for k, (a, b) in x["differences"].items() if k in x["sens_differe"])
                md += [f"- [{x['groupe']}] {x['uid']} — {x['titre'][:100]}", f"  - sens : {diff or '—'} ; axes {x['deltas']}",
                       f"  - premier : {x['notes'][0]}", f"  - second : {x['notes'][1]}"]
        md.append("")
    (c["runs"] / "comparaison_modeles_2027.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"stabilite": stabilite, "croise": rapport["croise"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
