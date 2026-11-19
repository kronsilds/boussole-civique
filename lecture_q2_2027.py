"""Lecture du questionnaire q2 en production : deux modeles de decision lisent tout, un arbitre tranche leurs desaccords.

  python .\\boussole_2027.py annoter --q2                                # plan (gratuit)
  python .\\boussole_2027.py annoter --q2 --max-cost 12                  # lecteurs 1 et 2, puis arbitre en direct
  python .\\boussole_2027.py annoter --q2 --batch-submit --max-cost 10   # arbitre en batch (lecteurs 1 et 2 deja lus)
  python .\\boussole_2027.py annoter --q2 --batch-collect

Ordre de lecture (proposition du 2026-11-12, arbitrage revu le 2026-11-16, `docs/suivi/09_...`) :
1. lecteur 1 (drex-max, modele de decision) : toutes les mesures a lire ;
2. lecteur 2 (pplx-decider, modele de decision) : les memes, en seconde lecture ;
3. arbitre (Terra, effort bas, texte) : seulement les mesures ou `questionnaire_q2_2027.motifs_arbitrage` trouve un
   motif ; il recoit les questions disputees et les deux lectures, et choisit (arbitrage_q2_2027.py).

Combinaison (`combiner`) : sans motif, la lecture 1 ; avec motif, la reponse de l'arbitre sur chaque litige, les autres
questions de la lecture 1. Un arbitrage peu sur, une reponse qu'aucun lecteur n'avait donnee ou la correction d'une
reponse commune sont signales (`divergences`, file « lectures divergentes »).

Reecriture du 2026-11-16 (methode essai-q2-v6) : les lectures payees en v5 restent valables pour les questions non
reecrites ; une passe ciblee (`methode_cible`, un appel par mesure et par lecteur) relit les seules questions
reecrites (`QUESTIONS_CIBLE`), et sa reponse remplace celle de la v5 (`fusion`). Une mesure nouvelle est lue en entier
en v6. Cles de cache : textes v5 figes (essai_q2_2027.cle_v5_decision) pour les lectures v5 ; masquage enrichi
(commun_2027.masquer_alias) pour toutes les lectures nouvelles. Retoucher une question change la cle v6 : il faudrait
une nouvelle passe ciblee, pas une relecture complete.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import arbitrage_q2_2027 as ARB
import decisions_2027 as DX
import essai_q2_2027 as E
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
from commun_2027 import masquer_alias
from scoring_context_2027 import digest

METHODE = E.METHODE
METHODE_CIBLE = "cible-q2-v7"
LECTEUR1 = "nace-ai/drex-max"
LECTEUR2 = "perplexity/pplx-decider-v1.2"
LECTEURS = (LECTEUR1, LECTEUR2)
ARBITRE, EFFORT_ARBITRE = "openai/gpt-6.1-terra", "low"
# Couts par mesure, bornes prudentes ; le cout reel du journal prime. Renotation v5 (11 054 mesures, 3 appels chacun) :
# environ 10,8 $ pour les deux lecteurs. Passe ciblee : un appel au lieu de trois. Arbitre : litiges seuls, pas tout le
# questionnaire.
COUTS = {LECTEUR1: .0015, LECTEUR2: .0006, ARBITRE: .005}
COUTS_CIBLE = {LECTEUR1: .0006, LECTEUR2: .00025}
PART_ARBITRAGE = .42      # part des mesures envoyees a l'arbitre (573 mesures lues en essai-q2-v3 : 41,5 %)
PAUSES = E.PAUSE           # secondes entre deux appels (pplx-decider limite le debit)
TAILLE_LOT = 10            # arbitre : mesures par requete
CLASSES = tuple(Q1.CLASSES_REVENU)
# Questions reecrites le 2026-11-16 (et la condition des classes de revenu), relues par la passe ciblee : 10 questions,
# un seul appel par mesure (16 au plus par appel).
QUESTIONS_CIBLE = ("a_menages", *CLASSES, "portee", "degre", "soc_autorite", "soc_libertes")


def decision() -> Any:
    return E.methode_decision("score")


def item_lu(it: dict[str, Any]) -> dict[str, Any]:
    """Item d'une lecture nouvelle : masquage enrichi (sigles courts, adjectifs et proches des partis)."""
    return masquer_alias(it)


def lire_cible(reponse: dict[str, Any]) -> dict[str, Any]:
    """Reponse de la passe ciblee -> reponses brutes des questions reecrites (verifiees : une reponse manquante ou hors
    options ecarte la mesure)."""
    brut = DX._answers(reponse)
    for k in QUESTIONS_CIBLE:
        if k in Q2.CONDITIONS or Q2.QUESTIONS[k]["type"] == "oui_non":
            E._proba(brut.get(k), k)
        else:
            E._option(brut.get(k), k)
    return {"methode": METHODE_CIBLE, "brut": E.garder({k: brut[k] for k in QUESTIONS_CIBLE})}


def methode_cible() -> types.SimpleNamespace:
    qs = E.questions_decision("score")
    sous = {k: qs[k] for k in QUESTIONS_CIBLE}
    return types.SimpleNamespace(
        requetes=lambda modele, it: [{"model": modele, "state": E.etat(it), "questions": sous}],
        lire=lire_cible, ETAPE="lecture_q2_cible",
        cle=lambda modele, it: digest({"methode": METHODE_CIBLE, "modele": modele, "item": it, "regles": E.REGLES,
                                       "questions": sous}))


def fusion(v5: dict[str, Any], cible: dict[str, Any]) -> dict[str, Any]:
    """Lecture v5 dont les questions reecrites sont remplacees par la passe ciblee (relue avec les regles actuelles)."""
    lu = E.lire_decision({"answers": {**v5["brut"], **cible["brut"]}})
    return {**lu, "methode": f"{E.gel_v5()['methode']}+{METHODE_CIBLE}"}


def a_lire(base: dict[str, Any], decisions: list[dict[str, Any]], uids: set[str] | None = None,
           relues: bool = False) -> list[dict[str, Any]]:
    """Mesures a lire en q2 : actives ou non reprises, sans lecture q2 de leur version courante (texte modifie, nouvelle
    mesure, lecture d'une methode precedente) ou avec un retraitement demande depuis. `uids` : seulement celles-ci
    (pilote). `relues` : aussi celles deja lues, pour recombiner leurs lectures en cache apres un changement de regle
    (sans appel)."""
    demandes: dict[str, str] = {}
    for d in decisions:
        if d["type"] == "retraiter":
            demandes[d["uid"]] = max(d["date"], demandes.get(d["uid"], ""))
    out = []
    for m in base["mesures"]:
        if m["statut"] not in ("active", "non_reprise") or (uids is not None and m["uid"] not in uids):
            continue
        a = m.get("annotation") or {}
        lue = (a.get("version") == Q2.VERSION and a.get("methode") == METHODE and a.get("version_mesure") == len(m["versions"])
               and not m.get("a_annoter"))
        if relues or not lue or demandes.get(m["uid"], "") > (a.get("date") or ""):
            out.append(m)
    return out


def _conf(lecture: dict[str, Any], k: str) -> float | None:
    return (lecture["assessments"].get(k) or {}).get("confidence")


def conf_accord(l1: dict[str, Any], l2: dict[str, Any], k: str) -> float | None:
    """Confiance d'une reponse donnee par les deux lecteurs : la plus haute des deux. L'accord de deux modeles
    independants est deja le controle ; la reponse n'est douteuse que si les deux hesitaient (premier run reel, 200
    mesures : 49 mesures sous 0,5 avec la plus basse des deux, 15 avec la plus haute, 33 avec la moyenne)."""
    return max((c for c in (_conf(l1, k), _conf(l2, k)) if c is not None), default=None)


def _cherche(caches: list[dict[str, Any]], k: str) -> Any:
    return next((c[k] for c in caches if k in c), None)


def etat(items: list[dict[str, Any]], caches: list[dict[str, Any]]) -> dict[str, Any]:
    """Ou en sont les lectures. Par lecteur : `lues` (id court -> lecture complete : v6, ou v5 fusionnee avec la passe
    ciblee), `completes` (items a lire en entier : aucune lecture), `ciblees` (items a relire par la passe ciblee : v5
    seule). Puis l'arbitre : `arbitres` (id court -> (litiges, arbitrage)), `file` (items de l'arbitre a lire). Les
    items rendus sont ceux des lectures nouvelles (item_lu)."""
    lus_items = {it["id"]: item_lu(it) for it in items}
    dec, cib = decision(), methode_cible()
    out: dict[str, Any] = {}
    for lecteur in LECTEURS:
        lues, completes, ciblees = {}, [], []
        for it in items:
            lu = lus_items[it["id"]]
            x = _cherche(caches, dec.cle(lecteur, lu))
            if x is None:
                v5 = _cherche(caches, E.cle_v5_decision(lecteur, it))
                if v5 is None:
                    completes.append(lu)
                    continue
                c = _cherche(caches, cib.cle(lecteur, lu))
                if c is None:
                    ciblees.append(lu)
                    continue
                x = fusion(v5, c)
            lues[it["id"]] = x
        out[lecteur] = {"lues": lues, "completes": completes, "ciblees": ciblees}
    arbitres, file = {}, []
    for it in items:
        l1, l2 = out[LECTEUR1]["lues"].get(it["id"]), out[LECTEUR2]["lues"].get(it["id"])
        if not (l1 and l2):
            continue
        lits = ARB.litiges(l1, l2, it["id"])
        if not lits:
            continue
        ia = ARB.item(lus_items[it["id"]], lits)
        a = _cherche(caches, ARB.cle(ARBITRE, ia, EFFORT_ARBITRE))
        if a is None:
            file.append(ia)
        else:
            arbitres[it["id"]] = (lits, a)
    out.update(arbitres=arbitres, file=file)
    return out


def combiner(l1: dict[str, Any], l2: dict[str, Any], lits: list[dict[str, Any]] | None = None,
             arb: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Lectures (et arbitrage) -> reponses retenues. None tant que l'arbitre manque a une mesure qui en a besoin."""
    r1, r2 = E.reponses(l1), E.reponses(l2)
    reponses = dict(r1)
    confiances = {k: conf_accord(l1, l2, k) if r1[k] == r2.get(k) else _conf(l1, k) for k in r1}
    motifs = Q2.motifs_arbitrage(r1, r2)
    if not motifs:
        return {"reponses": reponses, "confiances": confiances, "arbitrage": [], "divergences": [], "arbitrages": {}}
    if arb is None or lits is None:
        return None
    reps, confs, signalees, detail = ARB.appliquer_arbitrage(l1, l2, lits, arb)
    reponses.update(reps)
    confiances.update(confs)
    note = " ".join(f"{(Q2.QUESTIONS.get(k) or {}).get('libelle', 'Revenus')} : {d['raison']}" for k, d in detail.items()
                    if d["raison"])
    return {"reponses": reponses, "confiances": confiances, "arbitrage": motifs, "divergences": signalees,
            "arbitrages": detail, "note": note[:1200] or None}


def appliquer(m: dict[str, Any], resultat: dict[str, Any], date: str) -> None:
    """Annotation q2 : remplace la precedente (gardee dans l'historique de la fiche)."""
    a = m.get("annotation") or {}
    recombinee = a.get("version") == Q2.VERSION and a.get("methode") == METHODE and a.get("version_mesure") == len(m["versions"])
    if a.get("reponses") and not recombinee:   # memes lectures recombinees : rien a garder
        m.setdefault("historique", {}).setdefault("annotations_precedentes", []).append(
            {k: a.get(k) for k in ("version", "methode", "modele", "date", "reponses", "confiances", "note")})
    lecteurs = [*LECTEURS, *([ARBITRE] if resultat["arbitrage"] else [])]
    m["annotation"] = {"version": Q2.VERSION, "methode": METHODE, "modele": " + ".join(x.split("/")[-1] for x in lecteurs),
                       "lecteurs": lecteurs, "date": date, "version_mesure": len(m["versions"]),
                       "reponses": resultat["reponses"], "confiances": resultat["confiances"],
                       "arbitrage": resultat["arbitrage"], "divergences": resultat["divergences"],
                       "arbitrages": resultat.get("arbitrages") or {}, "note": resultat.get("note")}
    m["a_annoter"] = False


def plan(items: list[dict[str, Any]], et: dict[str, Any]) -> dict[str, Any]:
    """Ce qui reste a lire, et son cout estime (direct ; l'arbitre en batch coute moitie)."""
    lus = [it for it in items if all(it["id"] in et[x]["lues"] for x in LECTEURS)]
    inconnus = len(items) - len(lus)
    a3 = len(et["file"]) + round(PART_ARBITRAGE * inconnus)
    out: dict[str, Any] = {"mesures": len(items)}
    cout = 0.0
    for n, x in enumerate(LECTEURS, 1):
        c, k = len(et[x]["completes"]), len(et[x]["ciblees"])
        out[f"lecteur{n}_a_lire"], out[f"lecteur{n}_passe_ciblee"] = c, k
        cout += c * COUTS[x] + k * COUTS_CIBLE[x]
    out.update(file_arbitrage_connue=len(et["file"]), arbitrees=len(et["arbitres"]), a_lire_arbitre_estime=a3,
               cout_lecteurs=round(cout, 2), cout_arbitre_direct=round(a3 * COUTS[ARBITRE], 2),
               cout_arbitre_batch=round(a3 * COUTS[ARBITRE] / 2, 2))
    return out


def lire_decisions(et: dict[str, Any], lecteur: str, cle_api: str, journal: Any, max_cost: float, ecrire,
                   appel=None) -> dict[str, Any]:
    """Lecteur 1 ou 2 : passe ciblee sur les mesures lues en v5, puis lecture complete des mesures jamais lues (ecrit
    dans le cache de production). Le plafond est celui du run (lire_direct compte toute la depense du journal)."""
    appel = appel or E.appel_patient(PAUSES.get(lecteur, 0.0))
    out = {}
    if et[lecteur]["ciblees"] and max_cost > 0:
        out["passe_ciblee"] = DX.lire_direct(et[lecteur]["ciblees"], lecteur, cle_api, journal, max_cost, ecrire,
                                             cout_estime=COUTS_CIBLE[lecteur], methode=methode_cible(), appel=appel)
    if et[lecteur]["completes"] and max_cost > 0:
        out["completes"] = DX.lire_direct(et[lecteur]["completes"], lecteur, cle_api, journal, max_cost, ecrire,
                                          cout_estime=COUTS[lecteur], methode=decision(), appel=appel)
    return out


def resultats(items: list[dict[str, Any]], et: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """id court -> reponses retenues, pour les mesures dont toutes les lectures necessaires sont la."""
    out = {}
    for it in items:
        l1, l2 = et[LECTEUR1]["lues"].get(it["id"]), et[LECTEUR2]["lues"].get(it["id"])
        if l1 and l2:
            lits, arb = et["arbitres"].get(it["id"], (None, None))
            r = combiner(l1, l2, lits, arb)
            if r:
                out[it["id"]] = r
    return out


def resume(base: dict[str, Any]) -> dict[str, Any]:
    """Etat de la base : mesures lues en q2, arbitrees, divergentes."""
    actives = [m for m in base["mesures"] if m["statut"] in ("active", "non_reprise")]
    q2 = [m["annotation"] for m in actives if (m.get("annotation") or {}).get("version") == Q2.VERSION]
    return {"actives": len(actives), "lues_q2": len(q2), "methode_courante": sum(a.get("methode") == METHODE for a in q2),
            "arbitrees": sum(bool(a.get("arbitrage")) for a in q2), "divergentes": sum(bool(a.get("divergences")) for a in q2)}


if __name__ == "__main__":
    print(__doc__)
    sys.exit(0)
