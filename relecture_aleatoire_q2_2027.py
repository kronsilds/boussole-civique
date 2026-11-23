"""Relecture humaine a l'aveugle d'un echantillon tire au hasard dans la base publiee (questionnaire q2).

  python .\\relecture_q2_2027.py aleatoire [--taille 120] [--graine N] [--forcer]   # tirage, fiches, page de saisie
  python .\\relecture_q2_2027.py bilan-aleatoire                                    # taux de justesse (gratuit)
  python .\\relecture_q2_2027.py aleatoire --page                                   # page refaite, memes fiches

Page publiee : https://claude.ai/artifact/GyDMqCf7oiZbQdxDrH5ae3 (privee ; reponses dans la base de l'artifact,
collection `reponses`, a recopier dans export/reponses/<id>.json ou a telecharger en reponses.json depuis la page).
Republier : `relecture_artifact.html` (meme page sans squelette), capacites `db`, `downloads` et `user`. Plusieurs
relecteurs : chaque reponse porte l'identifiant opaque du relecteur (`relecteur`, capacite `user`, ni nom ni adresse) ;
la page laisse choisir de prendre les fiches depuis le debut ou depuis la fin ; une fiche enregistree entre-temps par
un autre relecteur n'est pas ecrasee (la seconde lecture va dans la collection `doublons`, hors bilan).

Pourquoi : la relecture des desaccords (`relecture_q2_2027.py preparer`, 97 cas) dit qui a raison quand les modeles
divergent, pas la justesse d'ensemble ; les erreurs communes aux deux lecteurs y restent invisibles. Ici, un
echantillon tire au hasard parmi les propositions publiees est relu a l'aveugle, sans montrer les reponses des modeles
ni avant ni apres la saisie (les voir orienterait les fiches suivantes).

Tirage (`tirer`) : population = propositions publiees lues en q2 (lignes de `donnees/donnees_interface_2027.json` hors
badge « en_revision », dont le texte publie est une version precedente ; sans export, les mesures actives ou non
reprises). Strates = candidat x arbitrage (mesure arbitree ou non). Allocation proportionnelle a la taille des strates
(reste le plus fort), au moins une fiche par candidat ; dans chaque strate, tirage systematique sur les mesures rangees
par theme, ce qui etale l'echantillon sur les themes. Graine fixee et journalisee, empreinte de la population : la meme
base et la meme graine redonnent le meme echantillon. Poids de chaque fiche = taille de sa strate / fiches de la strate
(taux ponderes du bilan).

Fiches (`fiches`) : titre, resume, citation et passage du document, noms masques (blind_names puis masquer_alias),
theme. Questions : fidelite du resume a la citation (extraction), dispositif, blocs touches (conditions du q2), degre,
portee, questions de sens des blocs coches, effet sur les cinq classes de revenu. La page n'affiche que les questions
ouvertes par les reponses du relecteur lui-meme (meme logique de conditions que le q2).

Sorties dans `runs/relecture_q2_2027/aleatoire/` (ignore par git) : `donnees.json` (fiches, sans reponse de modele),
`relecture.html` (page de saisie, donnees incluses : s'ouvre sans serveur), `references.json` (reponses publiees et
lectures des deux lecteurs, lues seulement par le bilan), `tirage.json` (journal du tirage), `reponses.json` (saisies,
telechargees depuis la page ou recopiees de la base de l'artifact). Bilan : `docs/relecture_aleatoire_q2_2027.md`,
`runs/.../aleatoire/bilan.json` (detail) et `donnees/relecture_aleatoire_q2_2027.json` (resume public, repris par
l'export dans `meta.relecture_aleatoire` et affiche par la page Coulisses une fois la relecture terminee).

Rien n'est modifie dans `donnees/base_2027.json` ni dans `donnees/decisions_2027.json`. Aucun appel : les lectures des
deux lecteurs viennent des caches de production.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import types
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
from commun_2027 import masquer_alias

DOSSIER = Path("runs") / "relecture_q2_2027" / "aleatoire"
PAGE = Path("web") / "relecture_aleatoire_q2_2027.html"
DOC = Path("docs") / "relecture_aleatoire_q2_2027.md"
RESUME = Path("donnees") / "relecture_aleatoire_q2_2027.json"
TAILLE = 120
GRAINE = 20271122
NSP = "__ne_sait_pas__"
SANS_OBJET = "__sans_objet__"
CLASSES = tuple(Q1.CLASSES_REVENU)
PUBLIC = ("a_menages", "a_eco", "a_ecolo")          # conditions de la portee
CONTENU = ("degre", "portee", "sens", "revenus")      # taux d'ensemble : les conditions a part (un bloc ferme des deux
                                                      # cotes, cas le plus frequent, gonflerait le taux)
BLOCS = ("a_menages", "a_eco", "a_soc", "a_sov", "a_immigration", "a_droits", "a_ecolo", "a_institutions",
         "a_alliances", "a_defense")
# Questions de sens posees pour chaque bloc coche (questions q2 dont la condition est ce bloc)
SENS_DU_BLOC = {b: tuple(k for k in Q2.QUESTIONS_SENS if Q2.QUESTIONS[k]["condition"] == b) for b in BLOCS}
# Questions qui disent qu'un bloc est ouvert dans une lecture (une reponse non nulle)
QUESTIONS_DU_BLOC = {c: tuple(k for k, q in Q2.QUESTIONS.items() if q["condition"] == c) for c in (*BLOCS, "a_dispositif")}
FIDELITE = {
    "fidele": "Fidèle : le résumé dit ce que dit la citation, avec ses conditions, et c'est bien la position du candidat.",
    "hypothese": "Engagement inventé : la citation n'avance qu'une hypothèse, une piste, un souhait ou une question, que "
                 "le résumé présente comme un engagement.",
    "conditions": "Conditions perdues : une condition, une limite, un seuil ou un calendrier de la citation a disparu ou "
                  "changé dans le résumé.",
    "adversaire": "Pas la position du candidat : la citation rapporte la position d'un adversaire, un constat ou une "
                  "critique, que le résumé attribue au candidat comme une proposition.",
    "deformation": "Autre déformation : le sens, l'objet, la portée ou un chiffre ne correspondent pas à la citation.",
}


# --- Tirage ------------------------------------------------------------------------------------------------------------
def population(base: dict[str, Any], export: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Propositions publiees lues en q2 : (uid, candidat, theme, arbitree), triees par uid."""
    if export and export.get("proposals"):
        publiees = {r["id"] for r in export["proposals"] if r.get("badge") != "en_revision"}
        garder = lambda m: m["uid"] in publiees and m["statut"] in ("active", "non_reprise")  # noqa: E731
    else:
        garder = lambda m: m["statut"] in ("active", "non_reprise")  # noqa: E731
    out = []
    for m in base["mesures"]:
        a = m.get("annotation") or {}
        if garder(m) and a.get("version") == Q2.VERSION and a.get("reponses"):
            out.append({"uid": m["uid"], "candidat": m["candidate_id"], "theme": m.get("theme_id") or "",
                        "arbitree": bool(a.get("arbitrage"))})
    return sorted(out, key=lambda x: x["uid"])


def strate(x: dict[str, Any]) -> str:
    return f"{x['candidat']}|{'arbitree' if x['arbitree'] else 'accord'}"


def allocation(tailles: dict[str, int], n: int) -> dict[str, int]:
    """Fiches par strate : proportionnelle (reste le plus fort, egalites departagees par le nom de la strate), puis au
    moins une fiche par candidat (prise a la strate la plus servie par rapport a sa part)."""
    total = sum(tailles.values())
    n = min(n, total)
    quotas = {h: n * t / total for h, t in tailles.items()}
    alloc = {h: int(q) for h, q in quotas.items()}
    for h in sorted(quotas, key=lambda h: (-(quotas[h] - alloc[h]), h))[:n - sum(alloc.values())]:
        alloc[h] += 1
    candidats = sorted({h.split("|")[0] for h in tailles})
    for c in candidats:
        siennes = [h for h in tailles if h.startswith(c + "|")]
        if sum(alloc[h] for h in siennes) == 0:
            donneuse = max((h for h in alloc if alloc[h] > 1 and not h.startswith(c + "|")),
                           key=lambda h: (alloc[h] - quotas[h], h), default=None)
            if donneuse is None:
                continue
            alloc[donneuse] -= 1
            alloc[max(siennes, key=lambda h: (tailles[h], h))] += 1
    return alloc


def empreinte(pop: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(pop, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def tirer(pop: list[dict[str, Any]], n: int = TAILLE, graine: int = GRAINE) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Echantillon stratifie reproductible. Rend les fiches tirees (avec strate et poids) et le journal du tirage."""
    hasard = random.Random(graine)
    par_strate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in pop:
        par_strate[strate(x)].append(x)
    tailles = {h: len(v) for h, v in par_strate.items()}
    alloc = allocation(tailles, n)
    tires = []
    for h in sorted(par_strate):
        k = alloc[h]
        if not k:
            continue
        membres = sorted(par_strate[h], key=lambda x: (x["theme"], x["uid"]))   # tirage systematique : etale les themes
        pas = len(membres) / k
        depart = hasard.random() * pas
        for i in range(k):
            x = membres[min(len(membres) - 1, int(depart + i * pas))]
            tires.append({**x, "strate": h, "poids": round(tailles[h] / k, 6)})
    hasard.shuffle(tires)   # ordre de presentation : ni par candidat ni par theme
    journal = {"graine": graine, "taille_demandee": n, "taille": len(tires), "population": len(pop),
               "empreinte_population": empreinte(pop),
               "strates": {h: {"taille": tailles[h], "fiches": alloc[h]} for h in sorted(tailles)},
               "par_candidat": dict(sorted(Counter(x["candidat"] for x in tires).items())),
               "par_theme": dict(sorted(Counter(x["theme"] for x in tires).items())),
               "arbitrees": sum(x["arbitree"] for x in tires),
               "themes_population": len({x["theme"] for x in pop}), "themes_echantillon": len({x["theme"] for x in tires})}
    return tires, journal


# --- Fiches et page ----------------------------------------------------------------------------------------------------
def _option(k: str, v: str, t: str) -> list[str]:
    prefixe = {Q2.OUI: "Oui. ", Q2.NON: "Non. "}.get(v, "") if Q2.QUESTIONS[k]["type"] == "oui_non" else ""
    return [v, prefixe + t]


def questions_page() -> dict[str, Any]:
    """Questions de la page, redaction actuelle du q2 (memes textes que les lecteurs) ; `si` : blocs qui ouvrent la
    question (cochee par le relecteur)."""
    qs: dict[str, Any] = {"fidelite": {"libelle": "Fidélité du résumé", "question": "Le titre et le résumé rendent-ils "
                                       "fidèlement la citation ? Juge l'extraction, pas la mesure.",
                                       "options": [[k, t] for k, t in FIDELITE.items()]}}
    c = Q2.CONDITIONS["a_dispositif"]
    qs["a_dispositif"] = {"libelle": "Dispositif", "question": c["question"],
                          "options": [["oui", "Oui. " + c["oui"]], ["non", "Non. " + c["non"]]]}
    qs["blocs"] = {"libelle": "Blocs touchés", "question": "Cochez chaque bloc que la mesure touche (aucun : « aucun de "
                   "ces blocs »). Les questions de sens des blocs cochés s'afficheront ensuite.",
                   "blocs": [{"k": b, "question": Q2.CONDITIONS[b]["question"], "oui": Q2.CONDITIONS[b]["oui"],
                              "non": Q2.CONDITIONS[b]["non"]} for b in BLOCS]}
    for k in ("degre", "portee"):
        q = Q2.QUESTIONS[k]
        qs[k] = {"libelle": q["libelle"], "question": q["question"], "options": [_option(k, v, t) for v, t in q["options"].items()],
                 "si": list(PUBLIC) if k == "portee" else None}
    for b, ks in SENS_DU_BLOC.items():
        for k in ks:
            q = Q2.QUESTIONS[k]
            qs[k] = {"libelle": q["libelle"], "question": q["question"], "si": [b],
                     "options": [_option(k, v, t) for v, t in q["options"].items()]}
    q = Q2.QUESTIONS[CLASSES[0]]
    qs["revenus"] = {"libelle": "Effet financier par classe de revenu", "si": ["a_menages"],
                     "question": q["question"].split(". ", 1)[1],
                     "classes": [{"k": k, "libelle": lib, "definition": d} for k, (lib, d, _pos) in Q1.CLASSES_REVENU.items()],
                     "options": [[v, t] for v, t in q["options"].items()]}
    return qs


def _propre(t: Any) -> Any:
    return masquer_alias(t.replace("\ufffd", "·")) if isinstance(t, str) else t   # puce illisible du PDF


def fiches(tires: list[dict[str, Any]], items: dict[str, dict[str, Any]], themes: dict[str, str], graine: int) -> dict[str, Any]:
    """Donnees de la page : aucune reponse de modele, ni la strate (qui dirait si la mesure a ete arbitree)."""
    mesures = {}
    for x in tires:
        it = items[x["uid"]]
        mesures[x["uid"]] = {"titre": _propre(it.get("title")), "description": _propre(it.get("description")),
                             "citation": _propre(it.get("quote")), "passage": _propre(it.get("passage")),
                             "theme": themes.get(x["theme"], x["theme"]) or None,
                             "lexique": {t: [_propre(x) for x in v] for t, v in it["lexique"].items()} if it.get("lexique") else None}
    return {"version": 1, "sorte": "aleatoire", "graine": graine, "nsp": NSP, "sans_objet": SANS_OBJET,
            "questions": questions_page(), "mesures": mesures,
            "fiches": [{"id": f"aleatoire:{x['uid']}", "uid": x["uid"]} for x in tires]}


def page(gabarit: str, donnees: dict[str, Any]) -> str:
    """Page de saisie autonome : les donnees sont incluses (aucun serveur ; `fetch` reste le secours de l'artifact)."""
    contenu = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    return gabarit.replace('<script type="application/json" id="donnees-incluses"></script>',
                           f'<script type="application/json" id="donnees-incluses">{contenu}</script>')


# --- References : ce que les modeles ont repondu -----------------------------------------------------------------------
def bloc_ouvert(r: dict[str, Any] | None, c: str) -> bool | None:
    """Condition d'une lecture, deduite de ses reponses (une question du bloc non nulle). Menages : un effet sur au
    moins une classe (« pas concernee » partout = aucun menage touche, comme `egales`)."""
    if r is None:
        return None
    if c == "a_menages":
        return any(r.get(k) not in (None, "non_concernee") for k in CLASSES)
    return any(r.get(k) is not None for k in QUESTIONS_DU_BLOC[c])


def references(racine: Path, uids: set[str]) -> dict[str, dict[str, Any]]:
    """uid -> reponses publiees (apres arbitrage) et lectures des deux lecteurs qui les ont produites : lecture v5 pour
    une annotation v5, lecture actuelle (v7, ou v5 completee par la passe ciblee) sinon. Aucun appel : les caches."""
    import annotation_2027 as A
    import base_2027 as B
    import boussole_2027 as BO
    import contexte_2027 as CX
    import essai_q2_2027 as E
    import lecture_q2_2027 as L
    from commun_2027 import blind_names
    c = BO.chemins(types.SimpleNamespace(racine=str(racine)))
    base, decisions = BO.charger_base(c), B.lire_json(c["decisions"], [])
    mesures = [m for m in base["mesures"] if m["uid"] in uids]
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
    caches = [B.lire_json(c["cache_lecture_q2"], {}), B.lire_json(c["cache_essai_q2"], {})]
    et = L.etat(items, caches)
    out = {}
    for m, it in zip(mesures, items):
        a = m["annotation"]
        lus = []
        for x in L.LECTEURS:
            if a.get("methode") == E.METHODE:
                lu = et[x]["lues"].get(it["id"])
            else:
                lu = L._cherche(caches, E.cle_v5_decision(x, it))
            lus.append(E.reponses(lu) if lu else None)
        out[m["uid"]] = {"publiee": a["reponses"], "lecteur1": lus[0], "lecteur2": lus[1], "methode": a.get("methode"),
                         "arbitrage": a.get("arbitrage") or [], "modele": a.get("modele")}
    return out


# --- Bilan -------------------------------------------------------------------------------------------------------------
def egales(k: str, a: Any, b: Any) -> bool:
    if k in CLASSES:
        a, b = (None if x == "non_concernee" else x for x in (a, b))
    return a == b


def humain(rep: dict[str, Any]) -> dict[str, Any]:
    """Reponses saisies -> valeurs comparables : conditions en booleens, « ne s'applique pas » a None (comme une
    question fermee chez le modele), questions fermees par les blocs du relecteur absentes, « je ne sais pas » absent.
    Un bloc coche dont toutes les questions de sens « ne s'appliquent pas » compte comme non touche ; le bloc menages
    est touche si une classe au moins gagne ou perd."""
    out: dict[str, Any] = {}

    def lire(k: str) -> None:
        v = rep.get(k)
        if v not in (None, NSP):
            out[k] = None if v == SANS_OBJET else v
    blocs = rep.get("blocs")
    if rep.get("a_dispositif") in ("oui", "non"):
        out["a_dispositif"] = rep["a_dispositif"] == "oui"
    lire("degre")
    if isinstance(blocs, list):
        ouverts = set(blocs)
        if ouverts & set(PUBLIC):
            lire("portee")
        for b in BLOCS:
            ks = SENS_DU_BLOC[b] if b in ouverts else ()
            for k in ks:
                lire(k)
            out[b] = b in ouverts and not (ks and all(rep.get(k) == SANS_OBJET for k in ks))
        if "a_menages" in ouverts:
            out.pop("a_menages")
            for k in CLASSES:
                lire(k)
            if all(rep.get(k) not in (None, NSP) for k in CLASSES):
                out["a_menages"] = any(rep.get(k) not in ("non_concernee", SANS_OBJET) for k in CLASSES)
    return out


def comparaisons(h: dict[str, Any], ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Une ligne par question jugee : conditions sur toutes les fiches ; questions (degre mis a part) seulement si le
    relecteur les a ouvertes (une reponse nulle du modele y est fausse). `accord` : les deux lecteurs disaient la
    meme chose (None si une lecture manque)."""
    lignes = []

    def valeur(source: str, k: str) -> Any:
        r = ref.get(source)
        if r is None:
            return ...
        return bloc_ouvert(r, k) if k in BLOCS or k == "a_dispositif" else r.get(k)
    for k, v in h.items():
        sorte = "dispositif" if k == "a_dispositif" else ("bloc_oui" if v else "bloc_non") if k in BLOCS else \
            "revenus" if k in CLASSES else "sens" if k in Q2.QUESTIONS_SENS else k
        l1, l2 = valeur("lecteur1", k), valeur("lecteur2", k)
        ligne = {"k": k, "sorte": sorte, "humain": v,
                 "accord": None if ... in (l1, l2) else egales(k, l1, l2)}
        for s in ("publiee", "lecteur1", "lecteur2"):
            x = valeur(s, k)
            ligne[s] = None if x is ... else egales(k, x, v)
        lignes.append(ligne)
    return lignes


def wilson(justes: float, n: float, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    p = justes / n
    d = 1 + z * z / n
    centre, marge = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, centre - marge), 3), round(min(1.0, centre + marge), 3)]


def _taux(c: Counter, cle: str = "") -> dict[str, Any] | None:
    n, j = c[cle + "lues"], c[cle + "justes"]
    return {"justes": j, "lues": n, "taux": round(j / n, 3), "intervalle": wilson(j, n)} if n else None


def _relecteurs(c: Counter) -> dict[str, int]:
    """Fiches relues par relecteur, sans l'identifiant (« relecteur 1 » : le plus de fiches) ; les reponses saisies
    avant l'identification des relecteurs comptent a part."""
    out = {f"relecteur {i}": n for i, (k, n) in enumerate(sorted(((k, n) for k, n in c.items() if k),
                                                                  key=lambda x: (-x[1], x[0])), 1)}
    if c.get(None):
        out["non identifié"] = c[None]
    return out


def bilan(donnees: dict[str, Any], refs: dict[str, dict[str, Any]], tires: dict[str, dict[str, Any]],
          reponses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Taux de justesse a partir des saisies. `tires` : uid -> fiche du tirage (theme, strate, poids, arbitree)."""
    par_q: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    par_sorte: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    par_theme: dict[str, Counter] = defaultdict(Counter)
    par_accord: dict[str, Counter] = defaultdict(Counter)       # sorte|accord -> publiee justes / lues
    par_arbitrage: dict[str, Counter] = defaultdict(Counter)    # arbitree|accord -> sources
    global_: Counter = Counter()
    fidelite: Counter = Counter()
    fid_theme: dict[str, Counter] = defaultdict(Counter)
    erreurs_communes = []
    relues = 0
    relecteurs: Counter = Counter()   # identifiants opaques de l'artifact, renommes « relecteur 1, 2 » dans la sortie
    for f in donnees["fiches"]:
        saisie = (reponses.get(f["id"]) or {}).get("reponses")
        if not saisie or f["uid"] not in refs:
            continue
        relues += 1
        relecteurs[(reponses.get(f["id"]) or {}).get("relecteur")] += 1
        notes = (reponses.get(f["id"]) or {}).get("commentaires") or {}
        t = tires.get(f["uid"]) or {}
        theme, poids = t.get("theme") or "?", float(t.get("poids") or 1.0)
        arb = "arbitree" if t.get("arbitree") else "accord"
        fid = saisie.get("fidelite")
        if fid in FIDELITE:
            fidelite[fid] += 1
            fid_theme[theme]["lues"] += 1
            fid_theme[theme]["justes"] += fid == "fidele"
        for ligne in comparaisons(humain(saisie), refs[f["uid"]]):
            for s in ("publiee", "lecteur1", "lecteur2"):
                if ligne[s] is None:
                    continue
                for c in (par_q[ligne["k"]][s], par_sorte[ligne["sorte"]][s], par_arbitrage[arb + "|" + s]):
                    c["lues"] += 1
                    c["justes"] += ligne[s]
            if ligne["publiee"] is None:
                continue
            if ligne["sorte"] in CONTENU:
                global_["lues"] += 1
                global_["justes"] += ligne["publiee"]
                global_["lues_p"] += poids
                global_["justes_p"] += poids * ligne["publiee"]
                par_theme[theme]["lues"] += 1
                par_theme[theme]["justes"] += ligne["publiee"]
            if ligne["accord"] is not None:
                c = par_accord[f"{ligne['sorte']}|{'accord' if ligne['accord'] else 'desaccord'}"]
                c["lues"] += 1
                c["justes"] += ligne["publiee"]
                if ligne["accord"] and not ligne["publiee"]:
                    erreurs_communes.append({"uid": f["uid"], "titre": donnees["mesures"][f["uid"]]["titre"],
                                             "question": ligne["k"], "humain": ligne["humain"],
                                             "commentaire": notes.get(ligne["k"]) or notes.get("fiche")})
    n_fid = sum(fidelite.values())
    out = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graine": donnees.get("graine"), "fiches": len(donnees["fiches"]), "relues": relues,
        "complete": relues == len(donnees["fiches"]) and relues > 0,
        "relecteurs": _relecteurs(relecteurs),
        "global": {**(_taux(global_) or {}), "taux_pondere": round(global_["justes_p"] / global_["lues_p"], 3)
                   if global_["lues_p"] else None},
        "par_sorte": {s: {src: _taux(c) for src, c in d.items()} for s, d in sorted(par_sorte.items())},
        "par_question": {k: {src: _taux(c) for src, c in d.items()} for k, d in sorted(par_q.items())},
        "par_theme": {th: _taux(c) for th, c in sorted(par_theme.items())},
        "accord_lecteurs": {k: _taux(c) for k, c in sorted(par_accord.items())},
        "arbitrage": {k: _taux(c) for k, c in sorted(par_arbitrage.items())},
        "fidelite": {"lues": n_fid, "fideles": fidelite["fidele"],
                     "taux": round(fidelite["fidele"] / n_fid, 3) if n_fid else None,
                     "intervalle": wilson(fidelite["fidele"], n_fid),
                     "erreurs": {k: fidelite[k] for k in FIDELITE if k != "fidele"},
                     "par_theme": {th: _taux(c) for th, c in sorted(fid_theme.items())}},
        "erreurs_communes": erreurs_communes,
    }
    return out


SOURCES = (("lecteur1", "lecteur 1 seul (avant arbitrage)"), ("lecteur2", "lecteur 2 seul"), ("publiee", "publiée (après arbitrage)"))
SORTES = (("dispositif", "Dispositif nommé"), ("bloc_oui", "Blocs touchés selon la relecture (le modèle les ouvre aussi)"),
          ("bloc_non", "Blocs non touchés selon la relecture (le modèle les laisse fermés)"), ("degre", "Degré de changement"), ("portee", "Public touché (portée)"),
          ("sens", "Sens (questions des axes)"), ("revenus", "Effet sur les classes de revenu"))


def _cell(t: dict[str, Any] | None) -> str:
    if not t:
        return "—"
    i = t.get("intervalle")
    return f"{t['justes']}/{t['lues']} ({round(100 * t['taux'])} %" + (f", {round(100 * i[0])}–{round(100 * i[1])} %)" if i else ")")


def markdown(b: dict[str, Any], themes: dict[str, str] | None = None) -> str:
    themes = themes or {}
    md = ["# Relecture humaine d'un échantillon tiré au hasard (questionnaire q2)", "",
          f"Graine {b['graine']} ; {b['relues']} fiches relues sur {b['fiches']}"
          + ("" if b["complete"] else " : **relecture inachevée, taux provisoires, ne pas publier**") + "."
          + (" Relecteurs : " + ", ".join(f"{k} {n}" for k, n in b.get("relecteurs", {}).items()) + "."
             if b.get("relecteurs") else ""), "",
          "Chaque taux : réponses justes / réponses jugées (intervalle de confiance à 95 %, Wilson, sans tenir compte "
          "de la pondération ni du regroupement des questions d'une même fiche). « Je ne sais pas » n'est pas compté.", ""]
    g = b["global"]
    if g.get("lues"):
        md += [f"**Réponses de contenu publiées** (degré, public touché, sens, revenus) : {_cell(g)} ; pondéré par la taille des strates : "
               f"{round(100 * g['taux_pondere'])} %.", ""]
    f = b["fidelite"]
    if f["lues"]:
        md += [f"**Fidélité de l'extraction** : {f['fideles']} résumés fidèles sur {f['lues']} "
               f"({round(100 * f['taux'])} %, {round(100 * f['intervalle'][0])}–{round(100 * f['intervalle'][1])} %). "
               "Erreurs : " + ", ".join(f"{k} {v}" for k, v in f["erreurs"].items()) + ".", ""]
    md += ["## Par famille de questions", "", "| Famille | " + " | ".join(lib for _, lib in SOURCES) + " |",
           "|---|" + "---|" * len(SOURCES)]
    for s, lib in SORTES:
        if s in b["par_sorte"]:
            md.append(f"| {lib} | " + " | ".join(_cell(b["par_sorte"][s].get(src)) for src, _ in SOURCES) + " |")
    md += ["", "## Accord et désaccord des deux lecteurs (réponse publiée)", "",
           "| Famille | Lecteurs d'accord | Lecteurs en désaccord |", "|---|---|---|"]
    for s, lib in SORTES:
        a, d = b["accord_lecteurs"].get(f"{s}|accord"), b["accord_lecteurs"].get(f"{s}|desaccord")
        if a or d:
            md.append(f"| {lib} | {_cell(a)} | {_cell(d)} |")
    md += ["", "## Mesures arbitrées ou non (toutes questions)", "", "| Mesures | " + " | ".join(lib for _, lib in SOURCES) + " |",
           "|---|" + "---|" * len(SOURCES)]
    for k, lib in (("accord", "sans arbitrage"), ("arbitree", "arbitrées")):
        md.append(f"| {lib} | " + " | ".join(_cell(b["arbitrage"].get(f"{k}|{src}")) for src, _ in SOURCES) + " |")
    md += ["", "## Par question", "", "| Question | " + " | ".join(lib for _, lib in SOURCES) + " |", "|---|" + "---|" * len(SOURCES)]
    for k, d in b["par_question"].items():
        lib = "Blocs : " + k if k in BLOCS else (Q2.QUESTIONS.get(k) or {}).get("libelle") or k
        md.append(f"| {lib} | " + " | ".join(_cell(d.get(src)) for src, _ in SOURCES) + " |")
    md += ["", "## Par thème (réponses publiées ; fidélité)", "", "| Thème | Réponses justes | Résumés fidèles |", "|---|---|---|"]
    for th in sorted(set(b["par_theme"]) | set(f["par_theme"])):
        md.append(f"| {themes.get(th, th)} | {_cell(b['par_theme'].get(th))} | {_cell(f['par_theme'].get(th))} |")
    if b["erreurs_communes"]:
        md += ["", "## Erreurs communes aux deux lecteurs", "", "| Mesure | Question | Relecture | Commentaire |", "|---|---|---|---|"]
        md += [f"| {x['titre']} | {x['question']} | {x['humain']} | {x['commentaire'] or ''} |" for x in b["erreurs_communes"]]
    return "\n".join(md) + "\n"


def resume_public(b: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    """Ce que l'export publie (meta.relecture_aleatoire) : taux seulement, aucun titre ni commentaire. `publiable` tant
    que toutes les fiches sont relues ; la page Coulisses n'affiche rien d'autre qu'un emplacement sinon."""
    garde = lambda d: {k: {"justes": v["justes"], "lues": v["lues"]} for k, v in d.items() if v}  # noqa: E731
    return {"version": 1, "genere_le": b["genere_le"], "publiable": b["complete"], "graine": b["graine"],
            "fiches": b["fiches"], "relues": b["relues"], "relecteurs": len([k for k in b.get("relecteurs", {}) if k != "non identifié"]) or None,
            "population": journal.get("population"),
            "empreinte_population": journal.get("empreinte_population"),
            "global": {k: b["global"].get(k) for k in ("justes", "lues", "taux_pondere")},
            "fidelite": {k: b["fidelite"][k] for k in ("fideles", "lues", "erreurs")},
            "par_sorte": {s: garde(d) for s, d in b["par_sorte"].items()},
            "accord_lecteurs": garde(b["accord_lecteurs"]),
            "arbitrage": garde(b["arbitrage"])}


# --- Commandes ---------------------------------------------------------------------------------------------------------
def preparer(racine: Path, taille: int = TAILLE, graine: int = GRAINE,
             refs: Callable[[Path, set[str]], dict[str, dict[str, Any]]] = references) -> dict[str, Any]:
    """Tirage, fiches, page de saisie et references. Rend le journal du tirage."""
    import annotation_2027 as A
    import base_2027 as B
    import boussole_2027 as BO
    import contexte_2027 as CX
    from commun_2027 import blind_names
    c = BO.chemins(types.SimpleNamespace(racine=str(racine)))
    base = BO.charger_base(c)
    pop = population(base, B.lire_json(c["export"], None))
    tires, journal = tirer(pop, taille, graine)
    journal["date"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    journal["source"] = "export" if c["export"].exists() else "base"
    par_uid = {m["uid"]: m for m in base["mesures"]}
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    items = {x["uid"]: CX.item(par_uid[x["uid"]], noms, c["corpus"] / "texts", lexique, masque) for x in tires}
    themes = {t["id"]: t.get("label") or t["id"] for t in base.get("themes") or []}
    donnees = fiches(tires, items, themes, graine)
    r = refs(racine, {x["uid"] for x in tires})
    # Controle : sans arbitrage, la reponse publiee est celle du lecteur 1
    sans = [x["uid"] for x in tires if not x["arbitree"] and (r.get(x["uid"]) or {}).get("lecteur1")]
    journal["controle_lecteur1"] = {"sans_arbitrage": len(sans), "identiques_publiee": sum(
        all(egales(k, r[u]["lecteur1"].get(k), r[u]["publiee"].get(k)) for k in Q2.QUESTIONS) for u in sans)}
    journal["lectures_manquantes"] = {s: sum((r.get(x["uid"]) or {}).get(s) is None for x in tires) for s in ("lecteur1", "lecteur2")}
    dossier = racine / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "donnees.json").write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    reconstruire_page(racine)
    (dossier / "references.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    (dossier / "tirage.json").write_text(json.dumps({**journal, "fiches": tires}, ensure_ascii=False, indent=1), encoding="utf-8")
    return journal


def version_artifact(html: str) -> str:
    """Page a publier en artifact claude.ai : le squelette (doctype, html, head, body, charset, viewport) est ajoute a
    la publication, il est donc retire ici ; le reste est identique (reponses dans la base de l'artifact)."""
    for t in ('<!doctype html>\n', '<html lang="fr">\n', '<head>\n', '<meta charset="utf-8">\n', '<meta name="viewport" content="width=device-width, initial-scale=1">\n', '</head>\n', '<body>\n', '</body>\n', '</html>\n'):
        html = html.replace(t, "", 1)
    return html


def reconstruire_page(racine: Path) -> Path:
    """Page de saisie refaite depuis le gabarit actuel et les fiches deja tirees (sans nouveau tirage), et sa version
    artifact (relecture_artifact.html)."""
    dossier = racine / DOSSIER
    donnees = json.loads((dossier / "donnees.json").read_text(encoding="utf-8"))
    gabarit = (Path(__file__).resolve().parent / PAGE).read_text(encoding="utf-8")
    html = page(gabarit, donnees)
    (dossier / "relecture.html").write_text(html, encoding="utf-8")
    (dossier / "relecture_artifact.html").write_text(version_artifact(html), encoding="utf-8")
    return dossier / "relecture.html"


def lire_reponses(dossier: Path) -> dict[str, dict[str, Any]]:
    """reponses.json (telecharge depuis la page), sinon export/reponses/<id>.json (base de l'artifact)."""
    fichier = dossier / "reponses.json"
    if fichier.exists():
        return json.loads(fichier.read_text(encoding="utf-8"))
    rep = {}
    for f in sorted((dossier / "export" / "reponses").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc = doc.get("data", doc) if isinstance(doc.get("data"), dict) else doc
        rep[doc.get("fiche") or f.stem] = doc
    return rep


def evaluer(racine: Path) -> tuple[dict[str, Any], str]:
    dossier = racine / DOSSIER
    donnees = json.loads((dossier / "donnees.json").read_text(encoding="utf-8"))
    refs = json.loads((dossier / "references.json").read_text(encoding="utf-8"))
    journal = json.loads((dossier / "tirage.json").read_text(encoding="utf-8"))
    tires = {x["uid"]: x for x in journal["fiches"]}
    b = bilan(donnees, refs, tires, lire_reponses(dossier))
    themes = {}
    try:
        import base_2027 as B
        themes = {t["id"]: t.get("label") or t["id"] for t in (B.lire_json(racine / "donnees" / "themes_2027.json", {}) or {}).get("themes") or []}
    except (OSError, ValueError, AttributeError):
        pass
    md = markdown(b, themes)
    (dossier / "bilan.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    (racine / DOC).parent.mkdir(parents=True, exist_ok=True)
    (racine / DOC).write_text(md, encoding="utf-8")
    (racine / RESUME).parent.mkdir(parents=True, exist_ok=True)
    (racine / RESUME).write_text(json.dumps(resume_public(b, journal), ensure_ascii=False, indent=1), encoding="utf-8")
    return b, md
