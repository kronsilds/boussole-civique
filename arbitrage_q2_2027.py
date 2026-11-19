"""Arbitrage q2 (decision du 2026-11-16) : l'arbitre recoit le desaccord des deux lecteurs et choisit la reponse la mieux
fondee, au lieu de relire tout le questionnaire comme un troisieme lecteur.

Pour chaque mesure de la file (`questionnaire_q2_2027.motifs_arbitrage`), l'arbitre (Terra, modele de texte) recoit :
- la mesure et son contexte (titre, description, citation, passage, lexique), a l'aveugle ;
- chaque question disputee, avec sa formulation exacte et toutes ses options (et « sans_objet » si elle a une
  condition) ;
- les deux lectures, nommees A et B (sans nom de modele ; l'ordre est tire pour chaque mesure, de facon reproductible,
  contre le biais de position) : la reponse de chacune et la probabilite que le modele donnait a chaque option (les
  modeles de decision ne redigent pas de justification ; la probabilite dit s'ils hesitaient).

Il repond, par litige, une option pour chaque question (celle de A, celle de B ou une autre si les deux ont tort), sa
confiance et une raison d'une ou deux phrases, affichee dans la fiche du tableau de bord.

Litiges : chaque question de sens disputee, la portee, le degre ; les cinq classes de revenu forment un seul litige
(motif « revenus ») ; sur le motif de coherence (les deux lectures d'accord : aucun menage touche, alors que la mesure
preleve, fixe un prix ou un revenu, ou transfere vers les modestes), le litige porte la reponse commune et un doute a
lever.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import essai_q2_2027 as E
import programme_corpus_2027 as pc
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
from scoring_context_2027 import digest, number

METHODE = "arbitrage-q2-v2"   # v2 : condition montree dans « sans_objet », ampleur sans montant (2026-11-16)
SANS_OBJET = "sans_objet"
CLASSES = tuple(Q1.CLASSES_REVENU)
QUESTIONS_LITIGE = (*Q2.QUESTIONS_SENS, "portee", "degre")
PROBA_MIN = .05            # probabilites plus basses non montrees a l'arbitre
CONF_FAIBLE = .5           # arbitrage sous ce seuil : signale (file « lectures divergentes »)

CONSIGNE = (
    "Tu arbitres un désaccord entre deux lectures d'une même proposition de programme politique, faites par deux modèles "
    "qui ont répondu au même questionnaire. Tu ne connais pas l'auteur de la proposition : n'utilise aucune connaissance "
    "sur les partis ou les candidats.\n"
    "Pour chaque mesure de `mesures` : la mesure à juger est celle de `title` et `description` ; `quote` est sa citation ; "
    "`passage` est l'extrait du document qui l'entoure et sert seulement à la comprendre ; `lexique`, s'il est présent, "
    "donne le sens que l'auteur donne à certains termes. Chaque litige nomme une ou plusieurs questions, dont la "
    "formulation exacte et toutes les options sont dans `questions` ; `A` et `B` donnent la réponse de chaque lecture et, "
    "quand elle est connue, la probabilité que le modèle donnait à chaque option. `sans_objet` veut dire que la question "
    "ne se pose pas pour cette mesure (sa condition n'est pas remplie).\n"
    "Choisis la réponse la mieux fondée d'après le texte de la mesure et les définitions des options : celle de A, celle "
    "de B, ou une autre option si les deux ont tort. La probabilité d'un modèle dit seulement s'il hésitait, pas s'il a "
    "raison : ne la suis pas, vérifie la définition. Un montant non précisé n'empêche pas de juger une ampleur : juge "
    "l'ordre de grandeur que le dispositif implique, sans choisir par prudence le niveau le plus faible. Un litige avec `doute` : les deux lectures sont d'accord, mais une "
    "règle de cohérence les met en doute ; confirme-les ou corrige-les. Pour un litige à plusieurs questions, réponds à "
    "chacune.\n"
    "Pour chaque litige, donne `confiance` (de 0 à 1 : ta certitude que ta réponse est la bonne) et `raison` (une ou deux "
    "phrases qui citent ce qui, dans la mesure, tranche entre les options)."
)


def _valeur(v: Any) -> str:
    return SANS_OBJET if v is None else v


def _probabilites(lecture: dict[str, Any], k: str) -> dict[str, float] | None:
    """Probabilite que le lecteur donnait a chaque option (reponse brute d'un modele de decision), ou None."""
    brut, q = (lecture.get("brut") or {}).get(k), Q2.QUESTIONS[k]
    if lecture["assessments"][k]["value"] is None:   # condition non remplie : sa probabilite la mieux remplie
        p = max((lecture.get("conditions") or {}).get(c, 0.0) for c in Q2.conditions_de(q))
        return {SANS_OBJET: round(1 - p, 2)}
    if not isinstance(brut, dict):
        return None
    options = list(q["options"])
    if q["type"] == "oui_non":
        p = brut.get("noul", brut.get("probability"))
        return {Q2.OUI: round(p, 2), Q2.NON: round(1 - p, 2)} if number(p) else None
    probs = brut.get("probabilities") if isinstance(brut.get("probabilities"), dict) else {}
    out = {}
    for a, p in probs.items():
        if not number(p) or p < PROBA_MIN:
            continue
        opt = options[int(a)] if str(a).isdigit() and int(a) < len(options) else a
        if opt in options:
            out[opt] = round(float(p), 2)
    return out or None


def _cote(lecture: dict[str, Any], questions: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for k in questions:
        e = {"reponse": _valeur(lecture["assessments"][k]["value"])}
        p = _probabilites(lecture, k)
        if p:
            e["probabilites"] = p
        out[k] = e
    return out


def _echange(uid: str) -> bool:
    """Ordre A/B tire pour chaque mesure, reproductible (meme mesure, meme ordre)."""
    return hashlib.sha256(uid.encode("utf-8")).digest()[0] % 2 == 1


def litiges(l1: dict[str, Any], l2: dict[str, Any], uid: str) -> list[dict[str, Any]]:
    """Litiges d'une mesure lue par les deux lecteurs (liste vide : pas d'arbitrage)."""
    r1, r2 = E.reponses(l1), E.reponses(l2)
    motifs = Q2.motifs_arbitrage(r1, r2)
    if not motifs:
        return []
    a, b = (l2, l1) if _echange(uid) else (l1, l2)
    out = []
    for k in QUESTIONS_LITIGE:
        if r1.get(k) != r2.get(k):
            out.append({"litige": k, "questions": [k], "A": _cote(a, (k,)), "B": _cote(b, (k,))})
    if "revenus" in motifs or "revenus_coherence" in motifs:
        x = {"litige": "revenus", "questions": list(CLASSES), "A": _cote(a, CLASSES), "B": _cote(b, CLASSES)}
        if "revenus_coherence" in motifs:
            x["doute"] = Q2.MOTIFS_ARBITRAGE["revenus_coherence"]
        out.append(x)
    return out


def item(it: dict[str, Any], lits: list[dict[str, Any]]) -> dict[str, Any]:
    """Item envoye a l'arbitre (la cle de cache en depend : memes lectures, meme arbitrage)."""
    return {**it, "litiges": lits}


def _question(k: str) -> dict[str, Any]:
    q = Q2.QUESTIONS[k]
    options = dict(q["options"])
    if q["condition"]:   # l'arbitre juge aussi si la question se pose : il lui faut la condition elle-meme
        conds = " ; ou ".join(f"« {Q2.CONDITIONS[c]['question']} » (oui si : {Q2.CONDITIONS[c]['oui']})"
                              for c in Q2.conditions_de(q))
        options[SANS_OBJET] = ("La question ne se pose pas pour cette mesure : la réponse est non à "
                               + ("chacune de ces questions : " if len(Q2.conditions_de(q)) > 1 else "la question : ") + conds)
    return {"question": q["question"], "options": options}


def questions(lot: list[dict[str, Any]]) -> dict[str, Any]:
    ks = sorted({k for it in lot for x in it["litiges"] for k in x["questions"]})
    return {k: _question(k) for k in ks}


def schema() -> dict[str, Any]:
    rep = {"type": "object", "additionalProperties": False, "required": ["question", "reponse"],
           "properties": {"question": {"type": "string"}, "reponse": {"type": "string"}}}
    lit = {"type": "object", "additionalProperties": False, "required": ["litige", "reponses", "confiance", "raison"],
           "properties": {"litige": {"type": "string"}, "reponses": {"type": "array", "items": rep},
                          "confiance": {"type": "number"}, "raison": {"type": "string"}}}
    arb = {"type": "object", "additionalProperties": False, "required": ["id", "litiges"],
           "properties": {"id": {"type": "string"}, "litiges": {"type": "array", "items": lit}}}
    return {"type": "object", "additionalProperties": False, "required": ["arbitrages"],
            "properties": {"arbitrages": {"type": "array", "items": arb}}}


def requete(modele: str, lot: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    return {"model": modele, "max_tokens": {"minimal": 12000, "low": 12000, "medium": 20000}.get(effort, 32000),
            "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "arbitrage_q2", "strict": True, "schema": schema()}},
            "messages": [{"role": "user", "content": CONSIGNE + "\n" + json.dumps(
                {"questions": questions(lot), "mesures": lot}, ensure_ascii=False)}]}


def lire(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reponse chat -> {id court: arbitrage}. Une mesure dont un litige manque, ou dont une reponse est hors options, est
    ecartee (relue au prochain run)."""
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    recus = pc.parse_json_object((choix.get("message") or {}).get("content"), "Arbitrage q2").get("arbitrages") or []
    attendus, out = {x["id"]: x for x in lot}, {}
    for a in recus:
        it = attendus.get(a.get("id")) if isinstance(a, dict) else None
        if not it or it["id"] in out:
            continue
        par_litige = {x.get("litige"): x for x in a.get("litiges") or [] if isinstance(x, dict)}
        propre = {}
        for lit in it["litiges"]:
            x = par_litige.get(lit["litige"])
            if not x or not number(x.get("confiance")) or not 0 <= x["confiance"] <= 1:
                break
            reps = {r.get("question"): r.get("reponse") for r in x.get("reponses") or [] if isinstance(r, dict)}
            valeurs = {}
            for k in lit["questions"]:
                v = reps.get(k)
                permis = set(Q2.QUESTIONS[k]["options"]) | ({SANS_OBJET} if Q2.QUESTIONS[k]["condition"] else set())
                if v not in permis:
                    break
                valeurs[k] = None if v == SANS_OBJET else v
            else:
                propre[lit["litige"]] = {"reponses": valeurs, "confiance": round(float(x["confiance"]), 2),
                                         "raison": str(x.get("raison") or "").strip()[:400]}
                continue
            break
        else:
            out[it["id"]] = {"methode": METHODE, "litiges": propre}
    if not out:
        raise ValueError("Aucun arbitrage q2 valide.")
    return out


def cle(modele: str, it: dict[str, Any], effort: str) -> str:
    return digest({"methode": METHODE, "modele": modele, "effort": effort, "item": it,
                   "questions": questions([it]), "consigne": CONSIGNE})


def appliquer_arbitrage(l1: dict[str, Any], l2: dict[str, Any], lits: list[dict[str, Any]],
                        arb: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    """Reponses et confiances retenues sur les questions en litige, questions signalees, detail par litige.
    Signale : un arbitrage sous CONF_FAIBLE, une reponse qu'aucun lecteur n'avait donnee, et (motif de coherence)
    une correction de la reponse commune (erreur commune possible : a verifier)."""
    r1, r2 = E.reponses(l1), E.reponses(l2)
    reponses, confiances, signalees, detail = {}, {}, [], {}
    for lit in lits:
        a = arb["litiges"][lit["litige"]]
        qs = lit["questions"]
        for k in qs:
            reponses[k], confiances[k] = a["reponses"][k], a["confiance"]
        vals, v1, v2 = tuple(a["reponses"][k] for k in qs), tuple(r1.get(k) for k in qs), tuple(r2.get(k) for k in qs)
        choix = "les_deux" if vals == v1 == v2 else "lecteur1" if vals == v1 else "lecteur2" if vals == v2 else "autre"
        if a["confiance"] < CONF_FAIBLE or choix == "autre":
            signalees.append(lit["litige"])
        detail[lit["litige"]] = {"choix": choix, "confiance": a["confiance"], "raison": a["raison"]}
    return reponses, confiances, signalees, detail
