"""Relecture humaine du questionnaire q2 (a l'essai) : validation des etalons et arbitrage des desaccords entre modeles.

  python .\\relecture_q2_2027.py preparer      # donnees de la page de relecture (gratuit, aucun appel)
  python .\\relecture_q2_2027.py completer   # second lot : 30 mesures nouvelles ou drex-max et pplx-decider different
                                               # en v5 (portee, revenus), ajoutees a donnees.json (gratuit)
  python .\\relecture_q2_2027.py bilan        # bilan des reponses saisies (runs/relecture_q2_2027/reponses.json,
                                               # ou export/reponses/*.json lus depuis la base de l'artifact)
  python .\\relecture_q2_2027.py evaluer       # lecteurs, passe ciblee et arbitre compares a la relecture (gratuit) ;
                                               # ecrit aussi uids.txt, pour `annoter --q2 --uids` sur ces mesures
  python .\\relecture_q2_2027.py aleatoire [--taille 120] [--graine N] [--forcer]
                                               # echantillon tire au hasard dans la base publiee, relu a l'aveugle :
                                               # fiches et page de saisie dans runs/relecture_q2_2027/aleatoire/
  python .\\relecture_q2_2027.py bilan-aleatoire   # taux de justesse de l'echantillon (docs/relecture_aleatoire_q2_2027.md)
                                               # ces deux commandes : relecture_aleatoire_q2_2027.py

Page publiee : https://claude.ai/artifact/Kf3FY7AcG9ptdSwRJDYn16 (prive ; base de l'artifact, collection `reponses`).

`preparer` ecrit `runs/relecture_q2_2027/donnees.json`, lu par la page `web/relecture_q2_2027.html` (publiee en
artifact ; les reponses y sont gardees dans la base de l'artifact, collection `reponses`, puis recopiees dans
`runs/relecture_q2_2027/reponses.json`). Deux sortes de fiches, chacune sur une mesure, a l'aveugle (noms masques) :

- **etalon** : les questions de `donnees/etalons_q2_2027.json` ; la reponse attendue n'est montree qu'apres la saisie ;
- **desaccord** : une question ou deux modeles au moins different. Portee et degre : drex-max / pplx-decider sur la
  redaction actuelle (rapport `runs/essai_q2_portee.json`, essai-q2-v3) ; classes de revenu : Terra, drex-max et
  pplx-decider (rapport `runs/essai_q2_2027.json`, essai-q2-v2, meme texte pour ces questions). Les reponses des
  modeles ne sont montrees qu'apres la saisie.

Les reponses des modeles sont reconstituees depuis les paires des rapports (une question absente des differences d'une
paire a la meme reponse chez les deux modeles). Rien n'est modifie dans la base ni dans les etalons.
"""
from __future__ import annotations

import argparse
import json
import random
import types
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import base_2027 as B
import boussole_2027 as BO
import contexte_2027 as CX
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
import relecture_aleatoire_q2_2027 as RA
from commun_2027 import blind_names

DOSSIER = Path("runs") / "relecture_q2_2027"
NOMS_MODELES = {"gpt-6.1-terra:low": "terra", "drex-max:decisions": "drex", "pplx-decider-v1.2:decisions": "pplx"}
FAMILLES = {"portee": ("portee",), "degre": ("degre",), "revenus": tuple(Q1.CLASSES_REVENU)}
PLAFONDS = {"portee": 20, "degre": 20, "revenus": 20}   # fiches par famille (tirees au hasard au-dela)
GRAINE = 2027
SANS_OBJET = "__sans_objet__"   # « ne s'applique pas » : condition fermee, reponse null


def reponses_par_modele(rapport: dict[str, Any], questions: tuple[str, ...]) -> dict[str, dict[str, dict[str, Any]]]:
    """uid -> question -> {modele: reponse} pour les questions ou au moins une paire differe."""
    connu: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    egal: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for paire, lignes in rapport["mesures"].items():
        a, b = (NOMS_MODELES[x.strip()] for x in paire.split(" / "))
        for x in lignes:
            for q in questions:
                if q in x["differences"]:
                    va, vb = x["differences"][q]
                    connu[x["uid"]][q].update({a: va, b: vb})
                else:
                    egal[x["uid"]][q].append((a, b))
    for uid, qs in connu.items():   # propage les egalites (deux passes suffisent a trois modeles)
        for q, rep in qs.items():
            for _ in range(2):
                for a, b in egal[uid][q]:
                    if a in rep and b not in rep:
                        rep[b] = rep[a]
                    elif b in rep and a not in rep:
                        rep[a] = rep[b]
    return {u: {q: dict(r) for q, r in qs.items()} for u, qs in connu.items()}


def question_page(k: str) -> dict[str, Any]:
    if k in Q2.CONDITIONS:
        c = Q2.CONDITIONS[k]
        return {"libelle": k.replace("a_", "Condition : ").replace("_", " "), "question": c["question"], "condition": True,
                "options": [["oui", "Oui. " + c["oui"]], ["non", "Non. " + c["non"]]]}
    q = Q2.QUESTIONS[k]
    return {"libelle": q["libelle"], "question": q["question"], "condition": False,
            "options": [[v, ({Q2.OUI: "Oui. ", Q2.NON: "Non. "}.get(v, "") if q["type"] == "oui_non" else "") + t]
                        for v, t in q["options"].items()],
            "si": " ou ".join(q["condition"]) if isinstance(q["condition"], (list, tuple)) else q["condition"]}


def valeur_page(k: str, v: Any) -> Any:
    if k in Q2.CONDITIONS:
        return "oui" if v else "non"
    return SANS_OBJET if v is None else v


def preparer(racine: Path) -> dict[str, Any]:
    c = BO.chemins(types.SimpleNamespace(racine=str(racine)))
    base = BO.charger_base(c)
    par_uid = {m["uid"]: m for m in base["mesures"]}
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    etalons = B.lire_json(c["donnees"] / "etalons_q2_2027.json", {}).get("etalons") or {}
    v2 = B.lire_json(racine / "runs" / "essai_q2_2027.json", {})
    v3 = B.lire_json(racine / "runs" / "essai_q2_portee.json", {})
    hasard = random.Random(GRAINE)
    fiches: list[dict[str, Any]] = []
    for uid, e in etalons.items():
        fiches.append({"id": f"etalon:{uid}", "type": "etalon", "uid": uid,
                       "questions": [{"k": k, "attendu": [valeur_page(k, x) for x in (v if isinstance(v, list) else [v])]}
                                     for k, v in e["attendu"].items()]})
    for famille, qs in FAMILLES.items():
        source = v2 if famille == "revenus" else v3
        par_mesure = reponses_par_modele(source, qs)
        candidats = sorted(u for u in par_mesure if u not in etalons and u in par_uid)
        hasard.shuffle(candidats)
        for uid in candidats[:PLAFONDS[famille]]:
            fiches.append({"id": f"desaccord:{famille}:{uid}", "type": "desaccord", "famille": famille, "uid": uid,
                           "source": source.get("methode"),
                           "questions": [{"k": k, "modeles": {m: valeur_page(k, v) for m, v in sorted(par_mesure[uid][k].items())}}
                                         for k in qs if k in par_mesure[uid]]})
    hasard.shuffle(fiches)
    mesures = {}
    for f in fiches:
        it = CX.item(par_uid[f["uid"]], noms, c["corpus"] / "texts", lexique, masque)
        propre = lambda t: t.replace("�", "·") if isinstance(t, str) else t  # noqa: E731  (puce illisible du PDF)
        mesures[f["uid"]] = {"titre": propre(it.get("title")), "description": propre(it.get("description")),
                             "citation": propre(it.get("quote")), "passage": propre(it.get("passage")), "theme": it.get("theme"),
                             "lexique": it.get("lexique")}
    cles = sorted({q["k"] for f in fiches for q in f["questions"]}, key=lambda k: (k not in Q2.CONDITIONS, k))
    return {"version": 1, "graine": GRAINE, "sans_objet": SANS_OBJET,
            "modeles": {"terra": "GPT-6.1 Terra (effort bas)", "drex": "drex-max", "pplx": "pplx-decider-v1.2"},
            "questions": {k: question_page(k) for k in cles}, "mesures": mesures, "fiches": fiches}


LOT2 = {"portee": 15, "revenus": 15}   # second lot : mesures nouvelles ou les deux lecteurs v5 different
GRAINE_LOT2 = 20271116


def completer(racine: Path, donnees: dict[str, Any], plafonds: dict[str, int] | None = None) -> tuple[dict[str, Any], dict[str, int]]:
    """Ajoute aux fiches existantes (inchangees, memes id) un lot de mesures jamais relues ou drex-max et pplx-decider
    different dans leur lecture v5 de la production (portee, ou une classe de revenu au moins : la fiche pose alors les
    cinq classes, les erreurs de la v7 touchant aussi celles ou les lecteurs v5 s'accordaient). Les questions sont
    affichees dans leur redaction actuelle ; les reponses v5 des deux lecteurs ne sont montrees qu'apres la saisie.
    Aucun appel : seulement le cache de production."""
    import annotation_2027 as A
    import essai_q2_2027 as E
    import lecture_q2_2027 as L
    plafonds = plafonds or LOT2
    c = BO.chemins(types.SimpleNamespace(racine=str(racine)))
    base, decisions = BO.charger_base(c), B.lire_json(c["decisions"], [])
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    caches = [B.lire_json(c["cache_lecture_q2"], {})]
    deja = {f["uid"] for f in donnees["fiches"]}
    pool: dict[str, list[tuple[str, dict[str, dict[str, Any]]]]] = defaultdict(list)
    for m in base["mesures"]:
        if m["uid"] in deja or m.get("statut") in ("rejetee", "ecartee"):
            continue
        it = CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions))
        lus = [L._cherche(caches, E.cle_v5_decision(x, it)) for x in (L.LECTEUR1, L.LECTEUR2)]
        if not all(lus):
            continue
        r1, r2 = (E.reponses(x) for x in lus)
        for famille in plafonds:
            if any(not egales(k, r1.get(k), r2.get(k)) for k in FAMILLES[famille]):   # toutes les classes, pas les seules divergentes
                pool[famille].append((m["uid"], {k: {"drex": valeur_page(k, r1.get(k)), "pplx": valeur_page(k, r2.get(k))}
                                                 for k in FAMILLES[famille]}))
    hasard = random.Random(GRAINE_LOT2)
    nouvelles, pris = [], set()
    for famille, n in plafonds.items():
        candidats = sorted(pool[famille])
        hasard.shuffle(candidats)
        for uid, diff in [x for x in candidats if x[0] not in pris][:n]:
            pris.add(uid)
            nouvelles.append({"id": f"desaccord:{famille}:{uid}", "type": "desaccord", "famille": famille, "uid": uid,
                              "source": "lecture-q2-v5", "lot": 2,
                              "questions": [{"k": k, "modeles": diff[k]} for k in FAMILLES[famille] if k in diff]})
    hasard.shuffle(nouvelles)
    par_uid = {m["uid"]: m for m in base["mesures"]}
    propre = lambda t: t.replace("�", "·") if isinstance(t, str) else t  # noqa: E731  (puce illisible du PDF)
    for f in nouvelles:
        it = CX.item(par_uid[f["uid"]], noms, c["corpus"] / "texts", lexique, masque)
        donnees["mesures"][f["uid"]] = {"titre": propre(it.get("title")), "description": propre(it.get("description")),
                                        "citation": propre(it.get("quote")), "passage": propre(it.get("passage")),
                                        "theme": it.get("theme"), "lexique": it.get("lexique")}
    donnees["fiches"] += nouvelles
    cles = sorted({q["k"] for f in donnees["fiches"] for q in f["questions"]}, key=lambda k: (k not in Q2.CONDITIONS, k))
    donnees["questions"] = {k: question_page(k) for k in cles}   # redaction actuelle (v7)
    donnees["version"] = 2
    return donnees, {f: len(v) for f, v in pool.items()}


def bilan(donnees: dict[str, Any], reponses: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """Etalons : reponses attendues confirmees ou contestees. Desaccords : quel modele rejoint la reponse humaine."""
    et = {"questions": 0, "conformes": 0, "contestees": [], "ignorees": 0}
    ds: dict[str, Counter] = defaultdict(Counter)
    detail_ds = []
    for f in donnees["fiches"]:
        r = (reponses.get(f["id"]) or {}).get("reponses") or {}
        notes = (reponses.get(f["id"]) or {}).get("commentaires") or {}
        for q in f["questions"]:
            v = r.get(q["k"])
            if v in (None, "__ne_sait_pas__"):
                if f["type"] == "etalon":
                    et["ignorees"] += v == "__ne_sait_pas__"
                continue
            if f["type"] == "etalon":
                et["questions"] += 1
                if v in q["attendu"]:
                    et["conformes"] += 1
                else:
                    et["contestees"].append({"uid": f["uid"], "titre": donnees["mesures"][f["uid"]]["titre"], "question": q["k"],
                                             "attendu": q["attendu"], "humain": v, "commentaire": notes.get(q["k"])})
            else:
                c = ds[f["famille"]]
                c["questions"] += 1
                for m, mv in q["modeles"].items():
                    c[f"{m}_lu"] += 1
                    c[f"{m}_juste"] += mv == v
                detail_ds.append({"famille": f["famille"], "uid": f["uid"], "question": q["k"], "humain": v, **q["modeles"],
                                  "commentaire": notes.get(q["k"])})
    out = {"etalons": et, "desaccords": {k: dict(v) for k, v in ds.items()}, "detail_desaccords": detail_ds}
    md = ["# Relecture humaine du questionnaire q2", "",
          f"Étalons : {et['conformes']} réponses attendues confirmées sur {et['questions']} ({et['ignorees']} « je ne sais pas »).", ""]
    if et["contestees"]:
        md += ["## Réponses attendues contestées", "", "| Mesure | Question | Attendu | Relecture | Commentaire |", "|---|---|---|---|---|"]
        md += [f"| {x['titre']} | {x['question']} | {', '.join(map(str, x['attendu']))} | {x['humain']} | {x['commentaire'] or ''} |"
               for x in et["contestees"]]
        md.append("")
    md += ["## Désaccords : qui rejoint la relecture", "", "| Famille | Questions | Terra | drex-max | pplx-decider |", "|---|---|---|---|---|"]
    for fam, c in out["desaccords"].items():
        cell = lambda m: f"{c[m + '_juste']} sur {c[m + '_lu']}" if c.get(m + "_lu") else "—"  # noqa: E731
        md.append(f"| {fam} | {c['questions']} | {cell('terra')} | {cell('drex')} | {cell('pplx')} |")
    return out, "\n".join(md) + "\n"


def humaines(donnees: dict[str, Any], reponses: dict[str, dict[str, Any]]) -> dict[tuple[str, str], Any]:
    """(uid, question) -> reponse de la relecture (questions du questionnaire seulement ; « ne s'applique pas » = None)."""
    out = {}
    for f in donnees["fiches"]:
        r = (reponses.get(f["id"]) or {}).get("reponses") or {}
        for q in f["questions"]:
            v = r.get(q["k"])
            if q["k"] in Q2.QUESTIONS and v not in (None, "__ne_sait_pas__"):
                out[(f["uid"], q["k"])] = None if v == SANS_OBJET else v
    return out


def egales(k: str, a: Any, b: Any) -> bool:
    """Classe de revenu : « pas concernee » et « ne s'applique pas » (condition fermee) disent la meme chose, aucun effet."""
    if k in Q1.CLASSES_REVENU:
        a, b = (None if x == "non_concernee" else x for x in (a, b))
    return a == b


def evaluer(racine: Path, donnees: dict[str, Any], reponses: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """Reponses justes, par famille de questions, de chaque lecture comparee a la relecture humaine : lectures v5 des deux
    lecteurs, lectures apres la passe ciblee, combinaison en base (avant), combinaison actuelle (lecteurs et arbitre).
    Aucun appel : seulement les caches."""
    import annotation_2027 as A
    import essai_q2_2027 as E
    import lecture_q2_2027 as L
    vrai = humaines(donnees, reponses)
    c = BO.chemins(types.SimpleNamespace(racine=str(racine)))
    base, decisions = BO.charger_base(c), B.lire_json(c["decisions"], [])
    uids = {u for u, _ in vrai}
    mesures = [m for m in base["mesures"] if m["uid"] in uids]
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
    caches = [B.lire_json(c["cache_lecture_q2"], {}), B.lire_json(c["cache_essai_q2"], {})]
    et = L.etat(items, caches)
    res = L.resultats(items, et)
    sources: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)   # source -> uid -> reponses
    for m, it in zip(mesures, items):
        for n, x in ((1, L.LECTEUR1), (2, L.LECTEUR2)):
            v5 = L._cherche(caches, E.cle_v5_decision(x, it))
            if v5:
                sources[f"lecteur{n}_v5"][m["uid"]] = E.reponses(v5)
            if it["id"] in et[x]["lues"]:
                sources[f"lecteur{n}_v6"][m["uid"]] = E.reponses(et[x]["lues"][it["id"]])
        if (m.get("annotation") or {}).get("reponses"):
            sources["base_avant"][m["uid"]] = m["annotation"]["reponses"]
        if it["id"] in res:
            sources["combinaison_v6"][m["uid"]] = res[it["id"]]["reponses"]

    def famille(k: str) -> str:
        return "revenus" if k in Q1.CLASSES_REVENU else k if k in ("portee", "degre") else             "societe" if k in ("soc_autorite", "soc_libertes") else "autres"
    stats: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for (u, k), v in vrai.items():
        for s, par_uid in sources.items():
            if u in par_uid:
                stats[famille(k)][s]["lues"] += 1
                stats[famille(k)][s]["justes"] += egales(k, par_uid[u].get(k), v)
    ordre = ("lecteur1_v5", "lecteur2_v5", "base_avant", "lecteur1_v6", "lecteur2_v6", "combinaison_v6")
    out = {"mesures": len(mesures), "arbitrees": sum(it["id"] in et["arbitres"] for it in items),
           "file_arbitre": len(et["file"]), "passe_ciblee_a_faire": {x: len(et[x]["ciblees"]) for x in L.LECTEURS},
           "familles": {f: {s: dict(v) for s, v in d.items()} for f, d in stats.items()}}
    md = ["# Lectures q2 comparées à la relecture humaine", "",
          f"{out['mesures']} mesures relues ; passe ciblée encore à faire : {out['passe_ciblee_a_faire']} ; "
          f"arbitrées : {out['arbitrees']} (file de l'arbitre : {out['file_arbitre']}).", "",
          "| Famille | " + " | ".join(ordre) + " |", "|---|" + "---|" * len(ordre)]
    for f in ("portee", "degre", "revenus", "societe", "autres"):
        if f in stats:
            md.append(f"| {f} | " + " | ".join(f"{stats[f][s]['justes']}/{stats[f][s]['lues']}" if stats[f][s]["lues"] else "—"
                                                for s in ordre) + " |")
    return out, "\n".join(md) + "\n"


def lire_reponses(dossier: Path) -> dict[str, dict[str, Any]]:
    fichier = dossier / "reponses.json"
    if fichier.exists():
        return json.loads(fichier.read_text(encoding="utf-8"))
    rep = {}   # lecture de la base de l'artifact enregistree document par document (export/reponses/<id>.json)
    for f in sorted((dossier / "export" / "reponses").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc = doc.get("data", doc) if isinstance(doc.get("data"), dict) else doc
        rep[doc.get("fiche") or f.stem] = doc
    return rep


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("commande", choices=("preparer", "completer", "bilan", "evaluer", "aleatoire", "bilan-aleatoire"))
    p.add_argument("--racine", default=".")
    p.add_argument("--taille", type=int, default=RA.TAILLE, help="aleatoire : nombre de fiches tirees")
    p.add_argument("--graine", type=int, default=RA.GRAINE, help="aleatoire : graine du tirage (journalisee)")
    p.add_argument("--forcer", action="store_true", help="aleatoire : refaire le tirage meme si des fiches existent")
    args = p.parse_args()
    racine = Path(args.racine)
    if args.commande == "aleatoire":
        if (racine / RA.DOSSIER / "donnees.json").exists() and not args.forcer:
            print(f"Un tirage existe deja ({racine / RA.DOSSIER}) : un nouveau tirage separerait les reponses saisies de "
                  "leurs fiches. --forcer pour le refaire.")
            return 1
        journal = RA.preparer(racine, args.taille, args.graine)
        print(json.dumps({k: journal[k] for k in ("graine", "population", "empreinte_population", "taille", "arbitrees",
                                                   "themes_population", "themes_echantillon", "par_candidat",
                                                   "controle_lecteur1", "lectures_manquantes")}, ensure_ascii=False, indent=1))
        print(f"Page de saisie : {racine / RA.DOSSIER / 'relecture.html'}")
        return 0
    if args.commande == "bilan-aleatoire":
        _, md = RA.evaluer(racine)
        print(md)
        return 0
    dossier = racine / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    if args.commande == "preparer":
        d = preparer(racine)
        (dossier / "donnees.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        compte = Counter(f.get("famille", "etalon") for f in d["fiches"])
        print(json.dumps({"fiches": len(d["fiches"]), "par_sorte": compte,
                          "questions": sum(len(f["questions"]) for f in d["fiches"])}, ensure_ascii=False, indent=1))
        return 0
    d = json.loads((dossier / "donnees.json").read_text(encoding="utf-8"))
    if args.commande == "completer":
        if any(f.get("lot") == 2 for f in d["fiches"]):
            print("Le second lot est deja dans donnees.json.")
            return 1
        d, pool = completer(racine, d)
        (dossier / "donnees.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"fiches": len(d["fiches"]), "lot2": Counter(f["famille"] for f in d["fiches"] if f.get("lot") == 2),
                          "desaccords_v5_disponibles": pool}, ensure_ascii=False, indent=1))
        return 0
    rep = lire_reponses(dossier)
    if args.commande == "evaluer":
        (dossier / "uids.txt").write_text("\n".join(sorted({f["uid"] for f in d["fiches"]})) + "\n", encoding="utf-8")
        out, md = evaluer(racine, d, rep)
        (dossier / "evaluation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        (dossier / "evaluation.md").write_text(md, encoding="utf-8")
        print(md)
        return 0
    out, md = bilan(d, rep)
    (dossier / "bilan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (dossier / "bilan.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
