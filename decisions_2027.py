"""Questionnaire q1 pose a un modele de decision (OpenRouter, /api/alpha/decisions) : essai comparatif.

Un modele de decision ne genere pas de texte : il recoit un etat (ici la mesure, son passage et son lexique, a
l'aveugle) et des questions typees, et rend pour chacune une probabilite par option. Adaptation de la methode standard
(contexte_2027), sans changer le questionnaire ni les formules :
- une mesure a la fois (l'etat ne contient qu'elle), toutes les questions, complements compris (les jetons de sortie
  ne sont pas factures : poser les complements plus tard n'economise rien), en lots de MAX_QUESTIONS par appel ;
- chaque question a choix devient `choice` ; la condition d'un axe (`applies_if`) devient une question oui/non
  (`predicate`), posee une fois par axe : sous SEUIL_AXE, les questions de l'axe valent null ;
- pas de message, donc pas de consigne generale : ses regles sont rappelees dans l'etat (`regles`) et dans les
  instructions des questions qu'elles concernent (moyen reel, orientation visee, « indetermine ») ;
- confiance = celle que rend le modele pour l'option retenue (a defaut sa probabilite), bornee par la probabilite de
  la condition ; ce n'est pas une auto-evaluation redigee.
Rien n'est applique a la base : les lectures vont dans le cache de comparer_modeles_2027.py (`modele:decisions`).
Les reponses brutes (probabilites) sont gardees dans la lecture, pour changer de seuil sans repayer.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

import contexte_2027 as CX
import pipeline_scoring_2027 as ps
import questionnaire_2027 as Q
from scoring_context_2027 import digest, number, request_json

METHODE = "decisions-v1"
URL = "https://openrouter.ai/api/alpha/decisions"
EFFORT = "decisions"     # tient lieu d'effort dans « modele:effort » (comparer_modeles_2027.py)
SEUIL_AXE = .5           # probabilite minimale de la condition pour que l'axe s'applique
COUT_ESTIME = .003       # par mesure, borne prudente tant que le journal ne donne pas de cout reel
ECHECS_MAX = 3           # echecs de suite avant l'arret (format de reponse inattendu, reseau)
MAX_QUESTIONS = 16       # par appel : limite de nace-ai/drex-max (HTTP 422 au-dela)

REGLES = ("Proposition d'un programme politique, décrite sans connaître son auteur : ne cherche pas à deviner le candidat "
          "et n'utilise aucune connaissance sur les partis. `passage` est l'extrait du document autour de la citation : il "
          "sert à comprendre le sens des termes et le contenu de la mesure, sans noter les autres mesures du passage. "
          "`lexique`, s'il est présent, donne le sens que l'auteur donne à certains termes (source secondaire).")
MOYEN = " Décris le moyen réellement prévu : un objectif sans moyen précisé est une déclaration."
VISE = (" Décris ce que la mesure vise, même seulement annoncé : un objectif déclaré a un sens et une ampleur. Ne réponds "
        "« inchangé », « neutre » ou « statu quo » que si l'orientation ou le changement visés sont réellement mixtes ou "
        "nuls, jamais parce que les moyens manquent.")
SENS = (" « indetermine » seulement si la direction elle-même manque ou se contredit, jamais parce que les moyens, le coût, "
        "le calendrier ou le périmètre ne sont pas précisés.")
CONDITION = " Un objectif seulement déclaré, sans moyen précisé, remplit la condition s'il porte sur ce sujet."
COUT = (" Donne un ordre de grandeur réaliste du dispositif (effectifs, bénéficiaires, montants comparables) ; "
        "indéterminable seulement si le texte est trop vague.")
QUESTIONS_MOYEN = ("levier", "portee", "precision", "instrument", "cout", "faisabilite")
CHAMPS_ETAT = ("theme", "title", "description", "quote", "passage", "lexique")


def conditions() -> tuple[str, ...]:
    """Conditions d'axe, une question oui/non chacune (has_eco, has_soc, ...)."""
    return tuple(dict.fromkeys(q["condition"] for q in Q.TOUTES.values() if q.get("condition")))


def permis(k: str) -> list[str]:
    return list(Q.TOUTES[k]["criteria"]) + ([Q.INDETERMINE] if k in CX.SENS else [])


def instructions(k: str) -> str:
    texte = Q.TOUTES[k]["instructions"]
    if k in QUESTIONS_MOYEN:
        texte += MOYEN
    if k == "cout":
        texte += COUT
    if k == "changement" or k in CX.SENS:
        texte += VISE
    if k in CX.SENS:
        texte += SENS
    if k == "droits_statut":
        texte += " " + CX.LECTURE_DROITS
    if k in Q.CLASSES_REVENU:   # pas de null dans un choix : la classe « non concernée » en tient lieu
        texte = texte.replace("Réponds null", "Réponds « non_concernee »")
    return texte


def questions() -> dict[str, dict[str, Any]]:
    """Questions au format de l'API (objet {nom: question}) : `noul` (oui/non) pour une condition, `choice` sinon."""
    out: dict[str, dict[str, Any]] = {}
    for c in conditions():
        q = ps.TYPESAFE_QUESTIONS[c]
        crit = q.get("criteria") or {}
        detail = f" (Oui : {crit['true']}. Non : {crit['false']}.)" if crit.get("true") and crit.get("false") else ""
        out[c] = {"type": "noul", "instructions": q["instructions"] + detail + CONDITION}
    for k, q in Q.TOUTES.items():
        libelles = {**q["criteria"], **({Q.INDETERMINE: Q.LIBELLE_INDETERMINE} if k in CX.SENS else {})}
        out[k] = {"type": "choice", "instructions": instructions(k), "criteria": {v: libelles[v] for v in permis(k)}}
    return out


def etat(it: dict[str, Any]) -> dict[str, Any]:
    """Etat envoye : les regles de lecture, puis la mesure aveugle (sans identifiant)."""
    return {"regles": REGLES, **{k: it[k] for k in CHAMPS_ETAT if it.get(k)}}


def lots_questions() -> list[dict[str, dict[str, Any]]]:
    """Questions par appel (MAX_QUESTIONS au plus) : d'abord les conditions d'axe et la description du moyen, puis les
    questions de sens et leurs complements."""
    qs = questions()
    premier = [*conditions(), *(k for k in Q.TOUTES if k not in Q.QUESTIONS_SENS and k not in Q.CLASSES_REVENU)]
    ordre = premier + [k for k in qs if k not in premier]
    return [{k: qs[k] for k in ordre[i:i + MAX_QUESTIONS]} for i in range(0, len(ordre), MAX_QUESTIONS)]


def requetes(modele: str, it: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"model": modele, "state": etat(it), "questions": lot} for lot in lots_questions()]


def _answers(reponse: dict[str, Any]) -> dict[str, Any]:
    brut = reponse.get("answers")
    if isinstance(brut, list):
        brut = {str(x.get("name")): x for x in brut if isinstance(x, dict) and x.get("name")}
    if not isinstance(brut, dict):
        raise ValueError("Reponse sans champ `answers`.")
    return brut


def cle(modele: str, it: dict[str, Any]) -> str:
    return digest({"methode": METHODE, "modele": modele, "item": it, "regles": REGLES, "questions": questions()})


def _proba(ans: Any, nom: str) -> float:
    p = ans.get("probability", ans.get("noul")) if isinstance(ans, dict) else None
    if not number(p) or not 0 <= p <= 1:
        raise ValueError(f"Condition sans probabilite : {nom}.")
    return float(p)


def _choix(ans: Any, k: str) -> tuple[str, float, float | None]:
    """Option retenue, confiance et probabilite de l'option."""
    if not isinstance(ans, dict):
        raise ValueError(f"Question sans reponse : {k}.")
    probs = {str(a): b for a, b in (ans.get("probabilities") or {}).items() if number(b)} \
        if isinstance(ans.get("probabilities"), dict) else {}
    val = ans.get("choice")
    if val is None and probs:
        val = max(probs, key=lambda a: probs[a])
    if val not in permis(k):
        raise ValueError(f"Option inconnue pour {k} : {val!r}.")
    p = probs.get(val)
    conf = ans.get("confidence") if number(ans.get("confidence")) else p
    if not number(conf) or not 0 <= conf <= 1:
        raise ValueError(f"Confiance absente ou hors plage : {k}.")
    return val, float(conf), p


def lire(reponse: dict[str, Any], seuil: float = SEUIL_AXE) -> dict[str, Any]:
    """Reponse de l'API -> lecture au format de l'annotation ({assessments, note}), plus `complements`, `conditions`
    (probabilite de chaque condition d'axe) et `brut` (reponses du modele). Toute reponse manquante ou invalide rejette
    la mesure : une lecture partielle ne serait pas comparable."""
    brut = _answers(reponse)
    cond = {c: _proba(brut.get(c), c) for c in conditions()}
    ouvert = {c: p >= seuil for c, p in cond.items()}

    def une(k: str, c: str | None) -> dict[str, Any]:
        val, conf, p = _choix(brut.get(k), k)
        return {"value": val, "confidence": round(min(conf, cond[c]) if c else conf, 2), "p": p}

    assessments = {}
    for k, q in Q.QUESTIONS.items():
        c = q.get("condition")
        assessments[k] = une(k, c) if not c or ouvert[c] else {"value": None, "confidence": round(1 - cond[c], 2)}
    complements = {}
    if ouvert["has_soc"]:
        complements["soc_finalite"] = une("soc_finalite", "has_soc")
    if ouvert["has_soc"] or ouvert["has_ouverture"]:   # comme annotation_2027.CONDITIONS_COMPLEMENT
        complements["degre_rupture"] = une("degre_rupture", None)
    if ouvert["has_eco"] or ouvert["has_rights_income"]:
        complements.update({k: une(k, None) for k in Q.CLASSES_REVENU})
    garde = ("choice", "probabilities", "confidence", "probability", "noul")
    return {"assessments": assessments, "complements": complements, "conditions": {c: round(p, 3) for c, p in cond.items()},
            "note": "", "brut": {n: {a: b for a, b in x.items() if a in garde} for n, x in brut.items() if isinstance(x, dict)}}


def reponses(review: dict[str, Any], complements: bool = True) -> dict[str, Any]:
    """Reponses pour questionnaire_2027.calculer (avec ou sans les complements)."""
    r = {k: e["value"] for k, e in review["assessments"].items()}
    if complements:
        r.update({k: e["value"] for k, e in (review.get("complements") or {}).items()})
    return r


def lire_direct(items: list[dict[str, Any]], modele: str, cle_api: str, journal: Any, max_cost: float, ecrire,
                appel=None, cout_estime: float | None = None, methode: Any = None) -> dict[str, int]:
    """Mesure par mesure (un appel par lot de questions), sous plafond : depense = cout reel du journal des qu'il en
    donne un (sinon l'estimation cumulee), et la mesure suivante est comptee a 1,5 fois le cout moyen observe.
    `ecrire({cle: lecture})` apres chaque mesure : une interruption ne fait rien perdre. Une erreur HTTP permanente
    (ScoringAPIError) remonte et arrete le run. `methode` : autre questionnaire (objet avec `requetes`, `lire`, `cle`,
    comme essai_q2_2027.methode_decision) ; par defaut, le questionnaire q1 de ce module."""
    from update_corpus_2027 import journal_cost
    appel = appel or request_json
    m = methode or sys.modules[__name__]
    stats = {"mesures": 0, "appels": 0, "echecs": 0, "lues": 0}
    prudent, suite = cout_estime or COUT_ESTIME, 0
    entetes = {"Authorization": "Bearer " + cle_api, "Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "Boussole2027/decisions"}
    for it in items:
        reel = journal_cost(journal.path) if journal is not None else 0.0
        depense = reel if reel > 0 else prudent * stats["mesures"]
        unitaire = 1.5 * reel / stats["mesures"] if reel > 0 and stats["mesures"] else prudent
        if depense + unitaire > max_cost:
            print("Plafond atteint : arret (relancer reprend ou il s'est arrete).")
            break
        stats["mesures"] += 1
        try:
            fusion: dict[str, Any] = {}
            for corps in m.requetes(modele, it):
                req = urllib.request.Request(URL, data=json.dumps(corps, ensure_ascii=False).encode("utf-8"), headers=entetes)
                stats["appels"] += 1
                fusion.update(_answers(appel(req, 120, journal=journal, stage=getattr(m, "ETAPE", "decisions_q1"),
                                             proposal_ids=[it["id"]])))
            review = m.lire({"answers": fusion})
        except (OSError, ValueError, KeyError) as exc:
            stats["echecs"] += 1
            suite += 1
            print(f"ERREUR decisions ({it['id']}) : {exc}")
            if suite >= ECHECS_MAX:
                print(f"{ECHECS_MAX} echecs de suite : arret.")
                break
            continue
        suite = 0
        stats["lues"] += 1
        ecrire({m.cle(modele, it): review})
    return stats
