"""Essai : relire une mesure avec le passage de son document et une reponse « indetermine » aux questions de sens.

  python .\\pilote_contexte_2027.py                      # echantillon et plan (gratuit)
  python .\\pilote_contexte_2027.py --max-cost 0.15      # relecture plafonnee, puis rapport

Echantillon : mesures en confiance basse (sens) et mesures contenant des mots ambigus (souverainete, laicite...).
Comparaison avec l'annotation q1 actuelle (meme modele, meme effort) : la seule difference est le passage et l'option
« indetermine ». Aveugle conserve : noms et partis masques dans le passage. Ne modifie ni la base ni le cache q1 ;
cache propre (donnees/cache_pilote_contexte_2027.json), rapport dans runs/pilote_contexte_2027.{json,md}.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import annotation_2027 as A
import base_2027 as B
import boussole_2027 as BO
import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import questionnaire_2027 as Q
from commun_2027 import blind_names
from scoring_context_2027 import digest, request_json

SENS = tuple(k for k in Q.QUESTIONS_SENS if k in Q.QUESTIONS)
INDETERMINE = "indetermine"
MOTS = ("souverainet", "laïcit", "laicit", "liberté", "simplif", "protection", "mérite")
FENETRE = 1200          # caracteres avant et apres la citation
COUT_ESTIME = .003      # par mesure (mesure au premier essai : 0,0028 $ avec le passage) ; le cout reel du journal prime
NEUTRE = {"eco_etat": "inchange_ou_mixte", "eco_distrib": "neutre", "soc_autorite": "inchange", "soc_libertes": "inchange"}
PAIRES = (("eco_etat", "eco_distrib"), ("soc_autorite", "soc_libertes"))
AXES = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rights_status")
CONSIGNE = A.CONSIGNE.replace(
    "Donne pour chaque question une confiance",
    "Chaque proposition est accompagnee de `passage`, l'extrait du document d'ou elle vient, autour de la citation : "
    "sers-t'en pour comprendre le sens que le document donne a ses termes et le contenu de la mesure, sans noter les "
    "autres mesures du passage. Pour les questions de sens, « indetermine » est reserve au cas ou la direction elle-meme "
    "manque ou se contredit, dans la proposition comme dans le passage. Un objectif annonce sans moyen (reduire la "
    "depense, proteger un secteur, garantir un prix, renforcer un controle) a une direction : donne-la. N'utilise jamais "
    "« indetermine » parce que les moyens, le cout, le calendrier ou le perimetre ne sont pas precises, ni a la place de "
    "null quand l'axe ne s'applique pas.\n"
    "Donne pour chaque question une confiance")


CONSIGNE_LEXIQUE = CONSIGNE.replace(
    "Donne pour chaque question une confiance",
    "Une proposition peut aussi avoir `lexique` : pour des termes qu'elle emploie, des phrases tirees des documents du "
    "meme auteur qui montrent le sens qu'il leur donne. Lis ces termes dans ce sens-la, sans en deduire d'autres mesures.\n"
    "Donne pour chaque question une confiance")


def rubrique() -> dict[str, Any]:
    r = A.rubrique()
    for k in SENS:
        r[k] = {**r[k], "options": {**r[k]["options"], INDETERMINE: "La direction elle-meme manque ou se contredit (pas seulement les moyens), dans la proposition comme dans le passage."}}
    return r


def schema() -> dict[str, Any]:
    s = A.schema()
    props = s["properties"]["reviews"]["items"]["properties"]["assessments"]["properties"]
    for k in SENS:
        props[k]["properties"]["value"]["enum"] = [v for v in props[k]["properties"]["value"]["enum"] if v is not None] + \
            [INDETERMINE] + ([None] if k in Q.CONDITIONNELLES else [])
    return s


def requete(modele: str, lot: list[dict[str, Any]], effort: str, consigne: str = CONSIGNE) -> dict[str, Any]:
    return {"model": modele, "max_tokens": 12000, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "questionnaire", "strict": True, "schema": schema()}},
            "messages": [{"role": "user", "content": consigne + "\n" + json.dumps({"rubric": rubrique(), "proposals": lot},
                                                                                  ensure_ascii=False)}]}


def lire(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Questionnaire").get("reviews") or []
    attendus, out = {x["id"] for x in lot}, {}
    for it in items:
        if not isinstance(it, dict) or it.get("id") not in attendus:
            continue
        a, propre = it.get("assessments") or {}, {}
        for k in Q.QUESTIONS:
            e = a.get(k) if isinstance(a.get(k), dict) else {}
            val, conf = e.get("value"), e.get("confidence")
            permis = set(Q.QUESTIONS[k]["criteria"]) | ({INDETERMINE} if k in SENS else set())
            if (val is None and k not in Q.CONDITIONNELLES) or (val is not None and val not in permis) or \
                    isinstance(conf, bool) or not isinstance(conf, (int, float)):
                break
            propre[k] = {"value": val, "confidence": round(float(conf), 2)}
        else:
            out[it["id"]] = {"assessments": propre, "note": str(it.get("note") or "")[:200]}
    return out


def passage(m: dict[str, Any], textes: Path, masque) -> str:
    """Extrait du document autour de la premiere citation (pages voisines comprises si la citation est en bord de page)."""
    src = (m["versions"][-1].get("sources") or [{}])[0]
    f = textes / f"{src.get('content_hash')}.json"
    if not f.exists():
        return ""
    segs = json.loads(f.read_text(encoding="utf-8"))["segments"]
    i = next((n for n, s in enumerate(segs) if s["id"] == src.get("segment_id")), None)
    if i is None:
        return ""
    avant = "\n".join(s["text"] for s in segs[max(0, i - 1):i])
    texte = segs[i]["text"]
    apres = "\n".join(s["text"] for s in segs[i + 1:i + 2])
    pos = texte.find((src.get("quote") or "")[:60])
    pos = pos if pos >= 0 else int(src.get("start") or 0)
    bloc, debut = avant + "\n" + texte + "\n" + apres, len(avant) + 1 + pos
    return masque(bloc[max(0, debut - FENETRE):debut + len(src.get("quote") or "") + FENETRE].strip())


def echantillon(base: dict[str, Any], n_basse: int, n_mots: int, graine: int) -> list[tuple[str, dict[str, Any]]]:
    rnd = random.Random(graine)
    basses, mots = [], {}
    for m in base["mesures"]:
        a = m.get("annotation") or {}
        if m["statut"] != "active" or a.get("version") != Q.VERSION:
            continue
        conf = a.get("confiances") or {}
        doutes = [k for k in SENS if (conf.get(k) if conf.get(k) is not None else 1) < B.SEUIL_CONFIANCE]
        texte = f"{m['versions'][-1]['title']} {m['versions'][-1].get('description') or ''}".lower()
        if doutes:
            v, _ = Q.calculer(a["reponses"])
            basses.append((max(abs(v.get(x) or 0) for x in AXES[:5]) >= 25, doutes[0], m))
        else:
            for mot in MOTS:
                if mot in texte:
                    mots.setdefault(mot.replace("laicit", "laïcit"), []).append(m)
                    break
    # confiance basse : d'abord les mesures nettement placees malgre le doute, reparties par question douteuse
    marquees = [x for x in basses if x[0]]
    rnd.shuffle(marquees)
    par_q: dict[str, list] = {}
    for _, q, m in marquees:
        par_q.setdefault(q, []).append(m)
    choix: list[tuple[str, dict[str, Any]]] = []
    while len(choix) < n_basse and any(par_q.values()):
        for q in list(par_q):
            if par_q[q] and len(choix) < n_basse:
                choix.append(("confiance_basse", par_q[q].pop()))
    # mots ambigus : mesures sans doute declare, reparties par mot
    for lst in mots.values():
        rnd.shuffle(lst)
    while len([c for c in choix if c[0] == "mot_ambigu"]) < n_mots and any(mots.values()):
        for mot in list(mots):
            if mots[mot] and len([c for c in choix if c[0] == "mot_ambigu"]) < n_mots:
                choix.append(("mot_ambigu", mots[mot].pop()))
    return choix


def comparer(avant: dict[str, Any], apres: dict[str, Any]) -> dict[str, Any]:
    ra = avant["reponses"]
    rb = {k: e["value"] for k, e in apres["assessments"].items()}
    cb = {k: e["confidence"] for k, e in apres["assessments"].items()}
    ca = avant.get("confiances") or {}
    sens_change = [k for k in SENS if ra.get(k) != rb.get(k) and rb.get(k) != INDETERMINE]
    indet = [k for k in SENS if rb.get(k) == INDETERMINE]
    # « indetermine » sur une question d'une paire (eco, societe) compte comme neutre si l'autre est tranchee ;
    # l'axe ne disparait que si tout son sens est indetermine (questions a une seule composante : axe retire).
    calc = dict(rb)
    for paire in PAIRES:
        if all(calc.get(k) == INDETERMINE for k in paire):
            calc.update({k: None for k in paire})
        else:
            calc.update({k: NEUTRE[k] for k in paire if calc.get(k) == INDETERMINE})
    calc = {k: (None if v == INDETERMINE else v) for k, v in calc.items()}
    va, _ = Q.calculer(ra)
    vb, _ = Q.calculer({**{k: ra.get(k) for k in Q.CONDITIONNELLES if k not in Q.QUESTIONS and k in ra}, **calc})
    deltas = {x: (va.get(x), vb.get(x)) for x in AXES if va.get(x) != vb.get(x)}
    doutes_avant = [k for k in SENS if (ca.get(k) if ca.get(k) is not None else 1) < B.SEUIL_CONFIANCE]
    doutes_apres = [k for k in SENS if rb.get(k) != INDETERMINE and (cb.get(k) if cb.get(k) is not None else 1) < B.SEUIL_CONFIANCE]
    return {"sens_change": sens_change, "indetermine": indet, "doutes_avant": doutes_avant, "doutes_apres": doutes_apres,
            "deltas": deltas, "ecart_max": max((abs((b or 0) - (a or 0)) for a, b in deltas.values()), default=0),
            "axe_perdu": [x for x, (a, b) in deltas.items() if a is not None and b is None]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--racine", default=".")
    p.add_argument("--max-cost", type=float, default=0.0)
    p.add_argument("--n-basse", type=int, default=50)
    p.add_argument("--n-mots", type=int, default=20)
    p.add_argument("--graine", type=int, default=2027)
    p.add_argument("--modele", default="openai/gpt-6.1-terra")
    p.add_argument("--effort", default="low")
    p.add_argument("--lexique", action="store_true", help="Ajoute le lexique du candidat (donnees/lexique_2027.json) ; "
                   "seules les mesures qui emploient un terme du lexique sont relues")
    args = p.parse_args()
    consigne = CONSIGNE_LEXIQUE if args.lexique else CONSIGNE
    suffixe = "_lexique" if args.lexique else ""
    c = BO.chemins(args)
    base = BO.charger_base(c)
    noms = blind_names(base.get("candidates") or [])
    motif = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True)) + r")(?!\w)", re.I)
    masque = lambda t: motif.sub("[le candidat]", t) if noms else t  # noqa: E731
    choix = echantillon(base, args.n_basse, args.n_mots, args.graine)
    items, par_id, sans_lexique = [], {}, {}
    lexique = B.lire_json(c["donnees"] / "lexique_2027.json", {}) if args.lexique else {}
    for groupe, m in choix:
        it = A.item(m, noms)
        it["passage"] = passage(m, c["corpus"] / "texts", masque)
        if args.lexique:
            import lexique_2027 as LX
            v = m["versions"][-1]
            texte = f"{v['title']} {v.get('description') or ''} {((v.get('sources') or [{}])[0] or {}).get('quote') or ''}"
            entrees = LX.entrees(lexique, m["candidate_id"], texte)
            if not entrees:
                continue
            sans_lexique[it["id"]] = dict(it)
            it["lexique"] = entrees
        items.append(it)
        par_id[it["id"]] = (groupe, m)
    sans_passage = sum(not it["passage"] for it in items)
    cache_path = c["donnees"] / "cache_pilote_contexte_2027.json"
    cache = B.lire_json(cache_path, {})
    cle = lambda it, cons=consigne: digest({"modele": args.modele, "effort": args.effort, "item": it, "rubrique": rubrique(),  # noqa: E731
                                            "consigne": cons})
    a_faire = [it for it in items if cle(it) not in cache]
    print(f"Echantillon : {Counter(g for g, _ in choix)} ; passages trouves {len(items) - sans_passage}/{len(items)} ; "
          f"{len(a_faire)} a lire, estimation {len(a_faire) * COUT_ESTIME:.3f} $ (plafond {args.max_cost} $).")
    if a_faire and args.max_cost <= 0:
        print("Aucun appel (--max-cost pour lancer) ; rapport sur les lectures deja en cache.")
    if a_faire and args.max_cost > 0:
        from llm_logging_2027 import LLMJournal
        from update_corpus_2027 import journal_cost
        ps.load_env_file(Path(__file__).with_name(".env"))
        cle_api = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not cle_api:
            raise SystemExit("OPENROUTER_API_KEY manque ; aucun appel lance.")
        journal = LLMJournal(secrets=(cle_api,))
        estime = 0.0
        try:
            for n in range(0, len(a_faire), A.TAILLE_LOT):
                lot = a_faire[n:n + A.TAILLE_LOT]
                depense = max(estime, journal_cost(journal.path))
                if depense + COUT_ESTIME * len(lot) > args.max_cost:
                    print("Plafond atteint : arret.")
                    break
                estime = depense + COUT_ESTIME * len(lot)
                req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                             data=json.dumps(requete(args.modele, lot, args.effort, consigne), ensure_ascii=False).encode("utf-8"),
                                             headers={"Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
                try:
                    res = lire(request_json(req, 600, journal=journal, stage="pilote_contexte", proposal_ids=[x["id"] for x in lot]), lot)
                except (OSError, ValueError, KeyError) as exc:
                    print(f"ERREUR lot : {exc}", file=sys.stderr)
                    continue
                for x in lot:
                    if x["id"] in res:
                        cache[cle(x)] = res[x["id"]]
                B.ecrire_json(cache_path, cache)
            cout = journal_cost(journal.path)
        finally:
            journal.close()
        print(f"Cout reel : {cout:.4f} $")
    lignes = []
    for it in items:
        groupe, m = par_id[it["id"]]
        r = cache.get(cle(it))
        if not r:
            continue
        ligne = {"uid": m["uid"], "groupe": groupe, "titre": m["versions"][-1]["title"], "theme": m.get("theme_id"),
                 "precision": m["annotation"]["reponses"].get("precision"), "note": r["note"],
                 "passage_trouve": bool(it["passage"]), **comparer(m["annotation"], r)}
        if args.lexique:  # comparaison avec la lecture « passage seul » (meme mesure, sans lexique)
            seul = cache.get(cle(sans_lexique[it["id"]], CONSIGNE))
            ligne["lexique_termes"] = sorted(it["lexique"])
            ligne["vs_passage"] = None if not seul else [
                k for k in SENS if seul["assessments"][k]["value"] != r["assessments"][k]["value"]]
            ligne["reponses_passage"] = None if not seul else {k: seul["assessments"][k]["value"] for k in SENS}
            ligne["reponses_lexique"] = {k: r["assessments"][k]["value"] for k in SENS}
        lignes.append(ligne)
    synthese = {}
    for g in ("confiance_basse", "mot_ambigu"):
        L = [x for x in lignes if x["groupe"] == g]
        if not L:
            continue
        synthese[g] = {"mesures": len(L), "sens_change": sum(bool(x["sens_change"]) for x in L),
                       "indetermine": sum(bool(x["indetermine"]) for x in L),
                       "doute_leve": sum(bool(x["doutes_avant"]) and not x["doutes_apres"] for x in L),
                       "doute_reste": sum(bool(x["doutes_apres"]) for x in L),
                       "axe_retire": sum(bool(x["axe_perdu"]) for x in L),
                       "deplacement_25_plus": sum(x["ecart_max"] >= 25 for x in L),
                       "questions_changees": dict(Counter(q for x in L for q in x["sens_change"]).most_common()),
                       "questions_indeterminees": dict(Counter(q for x in L for q in x["indetermine"]).most_common())}
        if args.lexique:
            synthese[g]["differe_du_passage_seul"] = sum(bool(x.get("vs_passage")) for x in L)
    rapport = {"modele": args.modele, "effort": args.effort, "synthese": synthese, "mesures": lignes}
    B.ecrire_json(c["runs"] / f"pilote_contexte_2027{suffixe}.json", rapport)
    md = ["# Essai : passage du document et option « indetermine »", "", "```", json.dumps(synthese, ensure_ascii=False, indent=1), "```", ""]
    for x in lignes:
        if x["sens_change"] or x["indetermine"] or x["ecart_max"] >= 25:
            md.append(f"- [{x['groupe']}] {x['uid']} — {x['titre'][:90]} — change {x['sens_change']} indetermine {x['indetermine']} "
                      f"deltas {x['deltas']} — {x['note']}")
    (c["runs"] / f"pilote_contexte_2027{suffixe}.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(synthese, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
