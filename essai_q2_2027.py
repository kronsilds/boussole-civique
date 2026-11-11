"""Essai du questionnaire q2 (questionnaire_q2_2027.py) : memes mesures, memes elements, plusieurs modeles.

Rien n'est applique a la base ni a l'export. Chaque modele lit, avec la proposition, le passage du document et le
lexique, a l'aveugle (contexte_2027.item) :
- l'echantillon de mise au point (170 mesures : l'echantillon fige des comparaisons et un groupe « nouveaux_axes »),
  sur lequel les questions ont ete corrigees ;
- un echantillon neuf, jamais vu pendant la mise au point (groupes « neuf_representatif », « neuf_alliances »,
  « neuf_menages »), qui dit si les corrections tiennent ailleurs ;
- des etalons (donnees/etalons_q2_2027.json) : mesures nettes dont les reponses attendues sont ecrites a la main.

  python .\\essai_q2_2027.py                                   # plan : aucun appel, rapport sur le cache
  python .\\essai_q2_2027.py --limite 3 --max-cost 0.05        # essai de format sur 3 mesures par groupe
  python .\\essai_q2_2027.py --groupes etalon --max-cost 0.2   # un ou plusieurs groupes seulement
  python .\\essai_q2_2027.py --max-cost 1                      # lectures manquantes, plafond total du run

Deux formats pour les memes textes :
- modele de texte (`modele:effort`, par exemple openai/gpt-6.1-terra:low) : consigne, bareme JSON, lots de 10 mesures ;
  il repond d'abord aux conditions (true/false), puis aux questions (null si la condition est fausse) ;
- modele de decision (`modele:decisions`, API /api/alpha/decisions) : une mesure a la fois, trois appels (16 questions
  au plus par appel) ; condition = question oui/non (`noul`), echelle = `score`, choix = `choice` ; chaque question est
  complete en elle-meme, car le modele y repond sans voir les autres. Sous SEUIL, la condition est fausse.
`--repetitions 2` relit les modeles de decision une seconde fois (base de bruit) ; un modele de texte n'est lu qu'une fois.
Lectures : donnees/cache_essai_q2_2027.json. Rapport : runs/essai_q2_2027.{json,md}.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import time
import types
from collections import Counter
from pathlib import Path
from typing import Any

import annotation_2027 as A
import base_2027 as B
import boussole_2027 as BO
import comparer_modeles_2027 as CM
import contexte_2027 as CX
import decisions_2027 as DX
import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
from commun_2027 import blind_names
from scoring_context_2027 import digest, number

METHODE = "essai-q2-v3"
SEUIL = .5
AXES_Q1 = ("eco", "soc", "sov", "ouverture", "ecolo")
THEMES_NOUVEAUX = ("institutions", "international")
MODELES = (("openai/gpt-6.1-terra", "low"), ("nace-ai/drex-max", DX.EFFORT), ("perplexity/pplx-decider-v1.2", DX.EFFORT))
# Cout par mesure avant le premier appel (borne prudente) ; le cout reel du journal prime ensuite.
COUT_PAR_MESURE = {"openai/gpt-6.1-terra": .006, "nace-ai/drex-max": .0015, "perplexity/pplx-decider-v1.2": .0006}
PAUSE = {"perplexity/pplx-decider-v1.2": 1.0}   # secondes entre deux appels : ce fournisseur limite le debit
GROUPES_NEUFS = {"neuf_alliances": 15, "neuf_menages": 15, "neuf_representatif": 50}   # tires dans cet ordre
MOTS_ALLIANCES = re.compile(r"\bOTAN\b|atlanti|non[- ]align|États-Unis|Ukrain|Russie|opérations? extérieure|"
                            r"défense européenne|armée européenne|Europe de la défense|autonomie stratégique|\balliés\b|"
                            r"accords? de défense|bases? militaires?", re.I)

# --- Format « modele de texte » ----------------------------------------------------------------------------------------
CONSIGNE = (
    "Tu décris des propositions de programmes politiques sans connaître leur auteur. Ne cherche pas à deviner le "
    "candidat et n'utilise aucune connaissance sur les partis : seuls comptent `title`, `description`, `quote` et "
    "`passage`.\n"
    "`passage` est l'extrait du document autour de la citation : il sert à comprendre le sens des termes et le contenu "
    "de la mesure ; ne note pas les autres mesures qu'il contient. `lexique`, s'il est présent, donne le sens que "
    "l'auteur donne à certains termes ; il ne sert qu'à lever une ambiguïté de vocabulaire.\n"
    "Procède en deux temps pour chaque proposition.\n"
    "1. `conditions` : réponds true ou false à chaque condition de `rubric.conditions`, d'après ses définitions `oui` "
    "et `non`. Une condition porte sur l'objet de la mesure, pas sur ses conséquences lointaines : dans le doute, "
    "réponds false. Un objectif seulement annoncé remplit la condition s'il porte clairement sur ce sujet, sauf pour "
    "`a_dispositif`, qui exige un moyen identifiable.\n"
    "2. `assessments` : pour chaque question de `rubric.questions`, choisis exactement une clé de `options`. Si la "
    "question a un champ `si` et que tu as répondu false à cette condition (à toutes, si `si` en liste "
    "plusieurs), réponds null.\n"
    "Il y a deux familles de questions. `levier`, `portee`, `chiffree`, `instrument`, `cout`, `financement` et les "
    "questions `rev_` décrivent ce que le texte prévoit réellement. `degre` et les questions d'axe décrivent ce que "
    "la mesure vise, même si les moyens ne sont pas précisés. Les options d'une échelle vont d'un pôle à l'autre : "
    "lis-les toutes avant de choisir. L'option du milieu (« inchangé », « neutre », « équilibre ») est réservée aux "
    "mesures dont les effets se compensent réellement ; ne la choisis jamais parce que les moyens, le coût ou le "
    "calendrier manquent. Si la mesure ne prend aucune direction sur un sujet, c'est que sa condition est false. "
    "Exception : les trois questions `eco_` regardent chacune un aspect différent de la même mesure ; l'option du "
    "milieu y est la bonne réponse dès que la mesure ne touche pas cet aspect.\n"
    "Donne pour chaque question une confiance entre 0 et 1 (0,5 : tu hésites entre deux options), puis une note "
    "d'audit très brève (160 caractères au plus) sur le choix le plus hésitant.\n"
    "Réponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"conditions\": {\"condition\": true}, "
    "\"assessments\": {\"question\": {\"value\": \"...\", \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entrée par "
    "identifiant reçu.")


def rubrique() -> dict[str, Any]:
    return {"conditions": Q2.CONDITIONS,
            "questions": {k: {"question": q["question"], "options": q["options"], **({"si": q["condition"] if isinstance(q["condition"], str) else list(q["condition"])} if q["condition"] else {})}
                          for k, q in Q2.QUESTIONS.items()}}


def schema() -> dict[str, Any]:
    def valeur(q: dict[str, Any]) -> dict[str, Any]:
        options = list(q["options"])
        return {"type": ["string", "null"], "enum": options + [None]} if q["condition"] else {"type": "string", "enum": options}
    a = {k: {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
             "properties": {"value": valeur(q), "confidence": {"type": "number"}}} for k, q in Q2.QUESTIONS.items()}
    review = {"type": "object", "additionalProperties": False, "required": ["id", "conditions", "assessments", "note"],
              "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                             "conditions": {"type": "object", "additionalProperties": False, "required": list(Q2.CONDITIONS),
                                            "properties": {c: {"type": "boolean"} for c in Q2.CONDITIONS}},
                             "assessments": {"type": "object", "additionalProperties": False, "required": list(Q2.QUESTIONS),
                                             "properties": a}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "items": review}}}


def requete(modele: str, lot: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    max_tokens = {"minimal": 20000, "low": 20000, "medium": 32000}.get(effort, 48000)   # 34 reponses par mesure
    sch = CX.schema_anyof(schema()) if modele.startswith("anthropic/") else schema()
    return {"model": modele, "max_tokens": max_tokens, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "questionnaire_q2", "strict": True, "schema": sch}},
            "messages": [{"role": "user", "content": CONSIGNE + "\n" + json.dumps({"rubric": rubrique(), "proposals": lot},
                                                                                  ensure_ascii=False)}]}


def lire(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reponse chat -> {id court: lecture}. Une question dont la condition est fausse vaut null, quoi que le modele ait
    ecrit ; une reponse manquante, hors options ou sans confiance ecarte la mesure."""
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Questionnaire q2").get("reviews") or []
    attendus, out = {x["id"] for x in lot}, {}
    for it in items:
        if not isinstance(it, dict) or it.get("id") not in attendus or it["id"] in out:
            continue
        cond, a, propre = it.get("conditions") or {}, it.get("assessments") or {}, {}
        if any(not isinstance(cond.get(c), bool) for c in Q2.CONDITIONS):
            continue
        for k, q in Q2.QUESTIONS.items():
            e = a.get(k) if isinstance(a.get(k), dict) else {}
            val, conf = e.get("value"), e.get("confidence")
            if not Q2.ouverte(q, cond.get):
                val = None
            if (val is None and not q["condition"]) or (val is not None and val not in q["options"]) or not number(conf) \
                    or not 0 <= conf <= 1:
                break
            propre[k] = {"value": val, "confidence": round(float(conf), 2)}
        else:
            out[it["id"]] = {"conditions": {c: float(cond[c]) for c in Q2.CONDITIONS}, "assessments": propre,
                             "note": str(it.get("note") or "")[:200]}
    if not out:
        raise ValueError("Aucune lecture q2 valide.")
    return out


def cle(modele: str, it: dict[str, Any], effort: str) -> str:
    return digest({"methode": METHODE, "modele": modele, "effort": effort, "item": it, "rubrique": rubrique(), "consigne": CONSIGNE})


CHAT = types.SimpleNamespace(requete=requete, lire=lire, cle=cle, ETAPE="essai_q2")

# --- Format « modele de decision » -------------------------------------------------------------------------------------
REGLES = ("Proposition d'un programme politique, décrite sans connaître son auteur : n'utilise aucune connaissance sur "
          "les partis. La mesure à juger est celle de `title` et `description` ; `quote` est sa citation ; `passage` est "
          "l'extrait du document qui l'entoure et sert seulement à la comprendre, sans juger les autres mesures qu'il "
          "contient ; `lexique`, s'il est présent, donne le sens que l'auteur donne à certains termes.")
PREFIXE = "À propos de la mesure décrite dans `title` et `description` (contexte : `passage`). "
RAPPEL_CONDITION = " Un objectif seulement annoncé compte s'il porte clairement sur ce sujet."
RAPPEL_SENS = (" Juge ce que la mesure vise, même si les moyens ne sont pas précisés ; le niveau du milieu est réservé aux "
               "effets qui se compensent réellement.")
RAPPEL_ASPECT = (" Juge ce que la mesure vise, même si les moyens ne sont pas précisés ; le niveau du milieu est la "
                 "bonne réponse si la mesure ne touche pas cet aspect.")
SANS_RAPPEL = ("a_dispositif", "a_menages")
LOTS = (("a_dispositif", "levier", "portee", "chiffree", "degre", "instrument", "cout", "financement", "a_menages",
         *Q1.CLASSES_REVENU),
        ("a_eco", *Q2.POIDS_ECO, "a_soc", "soc_autorite", "soc_libertes", "soc_egalite", "a_ecolo", "env_sens"),
        ("a_sov", "sov_niveau", "a_immigration", "ouv_sens", "a_droits", "droits_statut", "a_institutions", "inst_pouvoir",
         "a_alliances", "int_alliances", "a_defense", "def_effort"))


def questions_decision(echelles: str = "score") -> dict[str, dict[str, Any]]:
    """Questions au format de l'API. `echelles` : « score » (echelle ordonnee) ou « choice » si un modele refuse `score`."""
    out: dict[str, dict[str, Any]] = {}
    for c, q in Q2.CONDITIONS.items():
        out[c] = {"type": "noul", "instructions": PREFIXE + q["question"] + ("" if c in SANS_RAPPEL else RAPPEL_CONDITION),
                  "criteria": {"true": q["oui"], "false": q["non"]}}
    for k, q in Q2.QUESTIONS.items():
        texte = PREFIXE + q["question"] + (RAPPEL_ASPECT if k in Q2.POIDS_ECO else RAPPEL_SENS if k in Q2.QUESTIONS_SENS else "")
        if q["type"] == "oui_non":
            out[k] = {"type": "noul", "instructions": texte, "criteria": {"true": q["options"][Q2.OUI], "false": q["options"][Q2.NON]}}
        elif q["type"] == "echelle" and echelles == "score":
            out[k] = {"type": "score", "instructions": texte, "criteria": list(q["options"].values())}
        else:
            out[k] = {"type": "choice", "instructions": texte, "criteria": dict(q["options"])}
    return out


def etat(it: dict[str, Any]) -> dict[str, Any]:
    return {"lecture": REGLES, **{k: it[k] for k in DX.CHAMPS_ETAT if it.get(k)}}


def _proba(ans: Any, nom: str) -> float:
    if isinstance(ans, dict) and ans.get("type") == "refusal":
        raise ValueError(f"Question refusee : {nom}.")
    return DX._proba(ans, nom)


def _option(ans: Any, k: str) -> tuple[str, float]:
    """Option retenue et confiance d'une reponse `choice` ou `score`."""
    options = list(Q2.QUESTIONS[k]["options"])
    if not isinstance(ans, dict) or ans.get("type") == "refusal":
        raise ValueError(f"Question sans reponse : {k}.")
    probs = {str(a): b for a, b in (ans.get("probabilities") or {}).items() if number(b)} \
        if isinstance(ans.get("probabilities"), dict) else {}
    if ans.get("type") == "score" or "score" in ans:   # niveaux numerotes a partir de 0, dans l'ordre des options
        niveau = max(probs, key=lambda a: probs[a]) if probs else ans.get("score")
        try:
            val = options[int(round(float(niveau)))]
        except (TypeError, ValueError, IndexError):
            raise ValueError(f"Niveau inconnu pour {k} : {niveau!r}.") from None
        p = probs.get(str(options.index(val)))
    else:
        val = ans.get("choice") if ans.get("choice") is not None else (max(probs, key=lambda a: probs[a]) if probs else None)
        if val not in options:
            raise ValueError(f"Option inconnue pour {k} : {val!r}.")
        p = probs.get(val)
    conf = ans.get("confidence") if number(ans.get("confidence")) else p
    if not number(conf) or not 0 <= conf <= 1:
        raise ValueError(f"Confiance absente ou hors plage : {k}.")
    return val, float(conf)


def lire_decision(reponse: dict[str, Any], seuil: float = SEUIL) -> dict[str, Any]:
    """Reponses fusionnees des trois appels -> lecture. Condition sous le seuil : questions du bloc a null. La confiance
    d'une reponse est bornee par la probabilite de sa condition. `brut` garde les probabilites (changer de seuil sans
    repayer)."""
    brut = DX._answers(reponse)
    cond = {c: _proba(brut.get(c), c) for c in Q2.CONDITIONS}
    assessments = {}
    for k, q in Q2.QUESTIONS.items():
        c = max((cond[x] for x in Q2.conditions_de(q)), default=None)   # probabilite de la condition la mieux remplie
        if c is not None and c < seuil:
            assessments[k] = {"value": None, "confidence": round(1 - c, 2)}
            continue
        if q["type"] == "oui_non":
            p = _proba(brut.get(k), k)
            val, conf = (Q2.OUI if p >= .5 else Q2.NON), abs(2 * p - 1)
        else:
            val, conf = _option(brut.get(k), k)
        assessments[k] = {"value": val, "confidence": round(conf if c is None else min(conf, c), 2)}
    garde = ("type", "choice", "score", "probabilities", "confidence", "noul")
    return {"conditions": {c: round(p, 3) for c, p in cond.items()}, "assessments": assessments, "note": "",
            "brut": {n: {a: b for a, b in x.items() if a in garde} for n, x in brut.items() if isinstance(x, dict)}}


def methode_decision(echelles: str = "score") -> types.SimpleNamespace:
    qs = questions_decision(echelles)
    return types.SimpleNamespace(
        requetes=lambda modele, it: [{"model": modele, "state": etat(it), "questions": {k: qs[k] for k in lot}} for lot in LOTS],
        lire=lire_decision, ETAPE="essai_q2_decisions",
        cle=lambda modele, it: digest({"methode": METHODE, "modele": modele, "item": it, "regles": REGLES, "questions": qs}))


# --- Echantillon, comparaison, rapport ---------------------------------------------------------------------------------
def nouveaux_axes(base: dict[str, Any], exclus: set[str], n: int, graine: int) -> list[str]:
    """n mesures actives sans aucun axe en q1, des themes institutions et international a tour de role, puis a tour de
    role entre candidats (tirage reproductible)."""
    rng = random.Random(graine)
    files: dict[str, list[list[str]]] = {}
    for theme in THEMES_NOUVEAUX:
        par_candidat: dict[str, list[str]] = {}
        for m in base["mesures"]:
            if m["statut"] != "active" or not m.get("annotation") or m["uid"] in exclus or m.get("theme_id") != theme:
                continue
            v, _ = Q1.calculer(m["annotation"]["reponses"])
            if all(v.get(x) is None for x in AXES_Q1) and v.get("rights_status") is None:
                par_candidat.setdefault(m["candidate_id"], []).append(m["uid"])
        files[theme] = []
        for cand in sorted(par_candidat):
            uids = sorted(par_candidat[cand])
            rng.shuffle(uids)
            files[theme].append(uids)
        rng.shuffle(files[theme])
    out: list[str] = []
    while len(out) < n and any(f for fs in files.values() for f in fs):
        for theme in THEMES_NOUVEAUX:
            f = next((f for f in files[theme] if f), None)
            if f and len(out) < n:
                out.append(f.pop())
                files[theme].append(files[theme].pop(files[theme].index(f)))   # candidat suivant au prochain tour
    return out


def echantillon_neuf(base: dict[str, Any], exclus: set[str], graine: int, tailles: dict[str, int] | None = None) -> dict[str, list[str]]:
    """Mesures actives jamais vues pendant la mise au point, a tour de role entre candidats (tirage reproductible) :
    « neuf_alliances » (mots des alliances et de la defense), « neuf_menages » (un effet par classe de revenu en q1),
    « neuf_representatif » (toutes les mesures). Une mesure n'entre que dans un groupe."""
    rng = random.Random(graine)
    filtres = {"neuf_alliances": lambda m: bool(MOTS_ALLIANCES.search(m["versions"][-1]["title"] + " " + (m["versions"][-1].get("description") or ""))),
               "neuf_menages": lambda m: Q1.profil_revenu(m["annotation"]["reponses"]) is not None,
               "neuf_representatif": lambda m: True}
    pris, out = set(exclus), {}
    for groupe, n in (tailles or GROUPES_NEUFS).items():
        par_candidat: dict[str, list[str]] = {}
        for m in base["mesures"]:
            if m["statut"] == "active" and m.get("annotation") and m["uid"] not in pris and filtres[groupe](m):
                par_candidat.setdefault(m["candidate_id"], []).append(m["uid"])
        files = []
        for cand in sorted(par_candidat):
            uids = sorted(par_candidat[cand])
            rng.shuffle(uids)
            files.append(uids)
        rng.shuffle(files)
        out[groupe] = []
        while len(out[groupe]) < n and any(files):
            for f in files:
                if f and len(out[groupe]) < n:
                    out[groupe].append(f.pop())
        pris.update(out[groupe])
    return out


def ecarts_etalon(lecture: dict[str, Any], attendu: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Reponses d'une lecture qui s'ecartent d'un etalon. `attendu` : condition -> true/false, question -> liste des
    reponses acceptees (null accepte « non note »)."""
    out = []
    for k, voulu in attendu.items():
        obtenu = lecture["conditions"][k] >= SEUIL if k in Q2.CONDITIONS else lecture["assessments"][k]["value"]
        if (obtenu != voulu) if k in Q2.CONDITIONS else (obtenu not in voulu):
            out.append((k, voulu, obtenu))
    return out


def trois_lectures(lectures: dict[str, list[dict[str, Any] | None]]) -> dict[str, Any]:
    """Questions de sens sur les mesures lues par tous les modeles : reponses unanimes, modele seul contre les autres."""
    noms = list(lectures)
    communes = [ls for ls in zip(*lectures.values()) if all(ls)]
    out = {"mesures_lues_par_tous": len(communes), "reponses": len(communes) * len(Q2.QUESTIONS_SENS), "unanimes": 0,
           "accord_complet": 0, "seul_contre_les_autres": dict.fromkeys(noms, 0), "plus_de_deux_avis": 0}
    for ls in communes:
        complet = True
        for k in Q2.QUESTIONS_SENS:
            vals = [x["assessments"][k]["value"] for x in ls]
            compte = Counter(vals)
            if len(compte) == 1:
                out["unanimes"] += 1
                continue
            complet = False
            seuls = [n for n, v in zip(noms, vals) if compte[v] == 1]
            if len(compte) == 2 and len(seuls) == 1:
                out["seul_contre_les_autres"][seuls[0]] += 1
            else:
                out["plus_de_deux_avis"] += 1
        out["accord_complet"] += complet
    return out


def appel_patient(pause: float = 0.0, attentes: tuple[int, ...] = (10, 30, 60)):
    """Appel HTTP qui attend `pause` secondes avant chaque requete et reessaie apres un HTTP 429 (debit limite)."""
    from scoring_context_2027 import request_json

    def appel(req, timeout, **k):
        for attente in (*attentes, None):
            time.sleep(pause)
            try:
                return request_json(req, timeout, **k)
            except Exception as exc:   # noqa: BLE001 : seul le 429 est reessaye, le reste remonte
                if attente is None or "HTTP 429" not in str(exc):
                    raise
                time.sleep(attente)
    return appel


def reponses(lecture: dict[str, Any]) -> dict[str, Any]:
    return {k: e["value"] for k, e in lecture["assessments"].items()}


def comparer(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    ra, rb = reponses(a), reponses(b)
    va, vb = Q2.calculer(ra)[0], Q2.calculer(rb)[0]
    return {"conditions": {c: (a["conditions"][c] >= SEUIL, b["conditions"][c] >= SEUIL) for c in Q2.CONDITIONS},
            "differences": {k: (ra[k], rb[k]) for k in Q2.QUESTIONS if ra[k] != rb[k]},
            "sens_differe": [k for k in Q2.QUESTIONS_SENS if ra[k] != rb[k]],
            "axes": {x: (va[x], vb[x]) for x in Q2.AXES}, "notes": (a.get("note"), b.get("note"))}


def synthese(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(lignes)
    if not n:
        return {"mesures_comparees": 0}
    cond = {c: {"accord": sum(x["conditions"][c][0] == x["conditions"][c][1] for x in lignes),
                "oui_premier_seul": sum(x["conditions"][c][0] and not x["conditions"][c][1] for x in lignes),
                "oui_second_seul": sum(x["conditions"][c][1] and not x["conditions"][c][0] for x in lignes),
                "oui_des_deux": sum(all(x["conditions"][c]) for x in lignes)} for c in Q2.CONDITIONS}
    questions = {}
    for k, q in Q2.QUESTIONS.items():   # accord sur les mesures ou les deux lectures repondent
        deux = [x for x in lignes if all(Q2.ouverte(q, lambda c, i=i: x["conditions"][c][i]) for i in (0, 1))]
        questions[k] = {"n": len(deux), "accord": sum(k not in x["differences"] for x in deux)}
        if q["type"] == "echelle" and len(q["options"]) > 3:   # echelle longue : accord a un niveau pres, et sur le cote
            o, milieu = list(q["options"]), len(q["options"]) // 2
            paires_k = [x["differences"].get(k) for x in deux]
            hors = lambda d: d[0] not in o or d[1] not in o  # noqa: E731  (sans reponse ou hors echelle : compte comme ecart)
            questions[k]["a_un_niveau"] = sum(d is None or (not hors(d) and abs(o.index(d[0]) - o.index(d[1])) <= 1) for d in paires_k)
            if len(o) % 2:
                cote = lambda v: (o.index(v) > milieu) - (o.index(v) < milieu)  # noqa: E731
                questions[k]["meme_cote"] = sum(d is None or (not hors(d) and cote(d[0]) == cote(d[1])) for d in paires_k)
    axes = {}
    for ax in Q2.AXES:
        e = [(a, b) for x in lignes for a, b in [x["axes"][ax]] if a is not None and b is not None]
        axes[ax] = {"notes_des_deux": len(e), "ecart_moyen": round(statistics.mean(abs(a - b) for a, b in e), 1) if e else None,
                    "a_25_points": sum(abs(a - b) <= 25 for a, b in e),
                    "signes_opposes": sum(a * b < 0 and min(abs(a), abs(b)) >= 15 for a, b in e)}
    return {"mesures_comparees": n, "accord_sens_complet": sum(not x["sens_differe"] for x in lignes),
            "conditions": cond, "questions": questions, "axes": axes}


def couverture(lectures: list[dict[str, Any] | None], mesures: list[dict[str, Any]]) -> dict[str, Any]:
    """Ce que q2 note, et comment il se situe par rapport aux notes q1 de production (memes mesures)."""
    lues = [(m, x) for m, x in zip(mesures, lectures) if x]
    par_axe: dict[str, Any] = {ax: {"notees": 0} for ax in Q2.AXES}
    sans_q1 = avec_q2 = 0
    paires: dict[str, list[tuple[int, int]]] = {ax: [] for ax in AXES_Q1}
    seul = {ax: [0, 0] for ax in AXES_Q1}   # [q1 seul, q2 seul]
    for m, x in lues:
        v2, v1 = Q2.calculer(reponses(x))[0], Q1.calculer(m["annotation"]["reponses"])[0]
        for ax in Q2.AXES:
            par_axe[ax]["notees"] += v2[ax] is not None
        if all(v1.get(ax) is None for ax in AXES_Q1) and v1.get("rights_status") is None:
            sans_q1 += 1
            avec_q2 += any(v2[ax] is not None for ax in Q2.AXES)
        for ax in AXES_Q1:
            a, b = v1.get(ax), v2[ax]
            if a is not None and b is not None:
                paires[ax].append((a, b))
            elif a is not None or b is not None:
                seul[ax][b is not None] += 1
    for ax in AXES_Q1:
        e = paires[ax]
        par_axe[ax].update({"notes_q1_et_q2": len(e), "q1_seul": seul[ax][0], "q2_seul": seul[ax][1],
                            "ecart_moyen_q1": round(statistics.mean(abs(a - b) for a, b in e), 1) if e else None,
                            "signes_opposes_q1": sum(a * b < 0 and min(abs(a), abs(b)) >= 15 for a, b in e)})
    return {"mesures_lues": len(lues), "sans_axe_en_q1": sans_q1, "dont_un_axe_en_q2": avec_q2,
            "dispositif": sum(x["conditions"]["a_dispositif"] >= SEUIL for _, x in lues), "par_axe": par_axe}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--racine", default=".")
    p.add_argument("--echantillon", default="runs/pilote_contexte_2027.json")
    p.add_argument("--modeles", type=CM.config, nargs="+", default=list(MODELES), help="modele:effort ou modele:decisions ; le premier sert de reference")
    p.add_argument("--repetitions", type=int, default=1, help="lectures par modele de decision (2 : base de bruit)")
    p.add_argument("--n-nouveaux", type=int, default=40, help="mesures sans axe en q1 (institutions, international)")
    p.add_argument("--limite", type=int, default=0, help="ne lire que les N premieres mesures de chaque groupe (essai de format)")
    p.add_argument("--groupes", nargs="*", default=[], help="ne lire que ces groupes (etalon, neuf_representatif, representatif...)")
    p.add_argument("--echelles", choices=("score", "choice"), default="score", help="type des echelles pour les modeles de decision")
    p.add_argument("--graine", type=int, default=2027)
    p.add_argument("--max-cost", type=float, default=0.0, help="plafond total de ce run ; 0 = plan, aucun appel")
    p.add_argument("--rapport", default="essai_q2_2027")
    args = p.parse_args()
    c = BO.chemins(args)
    base = BO.charger_base(c)
    groupes = {x["uid"]: x["groupe"] for x in (B.lire_json(Path(args.racine) / args.echantillon, {}).get("mesures") or [])}
    fige = B.lire_json(c["runs"] / "echantillon_comparaison_2027.json", {})
    for g in ("representatif", "extreme_douteux"):
        groupes.update({u: g for u in fige.get(g) or [] if u not in groupes})
    if not groupes:
        raise SystemExit("Echantillon des comparaisons introuvable (runs/pilote_contexte_2027.json).")
    fige_q2_path = c["runs"] / "echantillon_q2_2027.json"
    fige_q2 = B.lire_json(fige_q2_path, {})
    if "nouveaux_axes" not in fige_q2:   # fige au premier tirage : l'essai reste comparable quand la base change
        fige_q2["nouveaux_axes"] = nouveaux_axes(base, set(groupes), args.n_nouveaux, args.graine)
        B.ecrire_json(fige_q2_path, fige_q2)
    groupes.update({u: "nouveaux_axes" for u in fige_q2["nouveaux_axes"] if u not in groupes})
    etalons = B.lire_json(c["donnees"] / "etalons_q2_2027.json", {}).get("etalons") or {}
    if "neuf" not in fige_q2:   # jamais vu pendant la mise au point des questions, fige lui aussi
        fige_q2["neuf"] = echantillon_neuf(base, set(groupes) | set(etalons), args.graine)
        B.ecrire_json(fige_q2_path, fige_q2)
    for g, us in fige_q2["neuf"].items():
        groupes.update({u: g for u in us if u not in groupes})
    groupes.update({u: "etalon" for u in etalons if u not in groupes})
    for g, us in (fige_q2.get("themes") or {}).items():   # groupes thematiques (« theme_... ») : lus seulement sur demande
        if g in args.groupes:
            groupes.update({u: g for u in us if u not in groupes})
    par_uid = {m["uid"]: m for m in base["mesures"]}
    uids = [u for u in groupes if u in par_uid and (not args.groupes or groupes[u] in args.groupes)]
    if args.limite:
        vus: Counter = Counter()
        uids = [u for u in uids if (vus.update([groupes[u]]) or vus[groupes[u]] <= args.limite)]
    mesures = [par_uid[u] for u in uids]
    decisions = B.lire_json(c["decisions"], [])
    noms = blind_names(base.get("candidates") or [])
    lexique, masque = B.lire_json(c["lexique"], {}), CX.masqueur(noms)
    items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
    cache_path = c["donnees"] / "cache_essai_q2_2027.json"
    cache = B.lire_json(cache_path, {})
    decision = methode_decision(args.echelles)

    def cle_lecture(conf, it, r=0):
        k = decision.cle(conf[0], it) if conf[1] == DX.EFFORT else cle(conf[0], it, conf[1])
        return k if r == 0 else digest({"cle": k, "repetition": r})

    confs = list(dict.fromkeys(args.modeles))
    taches = [(conf, r) for conf in confs for r in range(args.repetitions if conf[1] == DX.EFFORT else 1)]
    a_lire = {t: [it for it in items if cle_lecture(t[0], it, t[1]) not in cache] for t in taches}
    estimation = sum(len(v) * COUT_PAR_MESURE.get(t[0][0], .006 if t[0][1] != DX.EFFORT else .003) for t, v in a_lire.items())
    print(f"Echantillon : {len(items)} mesures ({dict(Counter(groupes[u] for u in uids))}).")
    for (conf, r), v in a_lire.items():
        print(f"  {CM.nom(conf)} lecture {r + 1} : {len(items) - len(v)} en cache, {len(v)} a lire.")
    print(f"Estimation prudente : {estimation:.2f} $ (plafond {args.max_cost} $).")
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
            par_cle = {cle_lecture(conf, it, 0): cle_lecture(conf, it, r) for it in v}

            def ecrire(tmp, par_cle=par_cle):   # cache ecrit apres chaque mesure ou chaque lot
                cache.update({par_cle[k]: x for k, x in tmp.items() if k in par_cle})
                B.ecrire_json(cache_path, cache)

            journal = LLMJournal(secrets=(cle_api,))
            unitaire = COUT_PAR_MESURE.get(conf[0])
            try:
                if conf[1] == DX.EFFORT:
                    stats = DX.lire_direct(v, conf[0], cle_api, journal, reste, ecrire, cout_estime=unitaire, methode=decision,
                                           appel=appel_patient(PAUSE.get(conf[0], 0.0)))
                    stats["relues"] = stats["lues"]
                else:
                    lots = [v[i:i + A.TAILLE_LOT] for i in range(0, len(v), A.TAILLE_LOT)]
                    stats = CX.relire_direct(lots, conf[0], conf[1], cle_api, journal, {}, reste, ecrire=ecrire,
                                             cout_estime=unitaire, methode=CHAT)
            finally:
                journal.close()
            k = f"{CM.nom(conf)} lecture {r + 1}"
            couts[k] = {**CM.usage(journal.path), "mesures_lues": stats["relues"], "echecs": stats["echecs"]}
            reste -= couts[k].get("cout", 0.0)
            print(f"  {k} : {stats['relues']} lues, {stats['echecs']} echecs, cout reel {couts[k].get('cout', 0):.4f} $")

    def lectures(conf, r=0):
        return [cache.get(cle_lecture(conf, it, r)) for it in items]

    def paires(l1, l2):
        return [{"uid": m["uid"], "groupe": groupes[m["uid"]], "titre": m["versions"][-1]["title"], **comparer(a, b)}
                for m, a, b in zip(mesures, l1, l2) if a and b]

    def phase(uid):   # mise au point (questions corrigees sur ces mesures), neuf (jamais vu) ou etalon
        g = groupes[uid]
        return "etalon" if g == "etalon" else "neuf" if g.startswith("neuf_") else "theme" if g.startswith("theme_") else "mise_au_point"

    def par_phase(lignes):
        return {"tout": synthese(lignes), **{ph: synthese([x for x in lignes if phase(x["uid"]) == ph]) for ph in ("mise_au_point", "neuf")}}

    def de_phase(liste, ph):
        return [x for m, x in zip(mesures, liste) if ph == "tout" or phase(m["uid"]) == ph]

    croise = {f"{CM.nom(a)} / {CM.nom(b)}": paires(lectures(a), lectures(b)) for i, a in enumerate(confs) for b in confs[i + 1:]}
    stabilite = {CM.nom(conf): par_phase(paires(lectures(conf), lectures(conf, 1)))
                 for conf in confs if conf[1] == DX.EFFORT and args.repetitions >= 2}
    conformite = {}
    for conf in confs:
        lus = [(m, x) for m, x in zip(mesures, lectures(conf)) if x and m["uid"] in etalons]
        ecarts = [{"uid": m["uid"], "titre": m["versions"][-1]["title"], "question": k, "attendu": voulu, "obtenu": obtenu}
                  for m, x in lus for k, voulu, obtenu in ecarts_etalon(x, etalons[m["uid"]]["attendu"])]
        attendues = sum(len(etalons[m["uid"]]["attendu"]) for m, _ in lus)
        conformite[CM.nom(conf)] = {"etalons_lus": len(lus), "reponses_attendues": attendues,
                                    "conformes": attendues - len(ecarts), "ecarts": ecarts}
    rapport = {"questionnaire": Q2.VERSION, "methode": METHODE, "modeles": [CM.nom(x) for x in confs], "couts_ce_run": couts,
               "couverture": {CM.nom(conf): {ph: couverture(de_phase(lectures(conf), ph), de_phase(mesures, ph)) for ph in ("tout", "neuf")}
                              for conf in confs},
               "etalons": conformite,
               "trois_lectures": {ph: trois_lectures({CM.nom(conf): de_phase(lectures(conf), ph) for conf in confs})
                                  for ph in ("mise_au_point", "neuf")} if len(confs) > 2 else {},
               "stabilite": stabilite, "croise": {k: par_phase(v) for k, v in croise.items()}, "mesures": croise}
    B.ecrire_json(c["runs"] / f"{args.rapport}.json", rapport)
    resume = {k: rapport[k] for k in ("couts_ce_run", "couverture", "etalons", "trois_lectures", "stabilite", "croise")}
    md = [f"# Essai du questionnaire q2 : {', '.join(rapport['modeles'])}", "",
          "Memes mesures, memes elements (proposition, passage, lexique). Paires : (premier, second).", "",
          "```", json.dumps(resume, ensure_ascii=False, indent=1), "```", "", "## Nouveaux axes, mesure par mesure", ""]
    for m, *ls in zip(mesures, *(lectures(conf) for conf in confs)):
        notes = []
        for conf, x in zip(confs, ls):
            v = Q2.calculer(reponses(x))[0] if x else {}
            notes.append(f"{CM.nom(conf)} : " + (", ".join(f"{ax} {v[ax]:+d}" for ax in ("inst", "inter", "defense") if v.get(ax) is not None) or "—"))
        if any(not n.endswith("—") for n in notes):
            md += [f"- [{groupes[m['uid']]}] {m['uid']} — {m['versions'][-1]['title'][:100]}", *(f"  - {n}" for n in notes)]
    for titre, lignes in croise.items():
        md += ["", f"## {titre} : questions de sens differentes", ""]
        for x in lignes:
            if x["sens_differe"]:
                diff = ", ".join(f"{k} {x['differences'][k][0]} → {x['differences'][k][1]}" for k in x["sens_differe"])
                md += [f"- [{x['groupe']}] {x['uid']} — {x['titre'][:100]}", f"  - {diff}",
                       *(f"  - note : {n}" for n in x["notes"] if n)]
    (c["runs"] / f"{args.rapport}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for nom, e in conformite.items():
        print(f"Etalons, {nom} : {e['conformes']}/{e['reponses_attendues']} reponses conformes sur {e['etalons_lus']} mesures.")
    for titre, x in rapport["croise"].items():
        print(f"{titre} : accord complet de sens " + ", ".join(
            f"{ph} {x[ph].get('accord_sens_complet', 0)}/{x[ph]['mesures_comparees']}" for ph in ("mise_au_point", "neuf")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
