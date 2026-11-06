"""Etape d'annotation du pipeline unifie : questionnaire q1, a l'aveugle, en appel direct ou en batch (phase 3).

Mesures a annoter : sans annotation q1, texte nouveau ou modifie (a_annoter), ou retraitement demande. Pilote : liste
d'uid. Cache par questionnaire, modele et texte aveugle : relancer ne repaie rien. Aucun appel sans plafond.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

import pipeline_scoring_2027 as ps
import programme_corpus_2027 as pc
import questionnaire_2027 as Q
import commun_2027 as rc
from commun_2027 import blind_item
from scoring_context_2027 import digest, request_json

METHODE = "questionnaire-q1"
COUT_DIRECT = .0025   # par mesure, estimation avant pilote (17 questions, raisonnement moyen) ; batch = moitie
TAILLE_LOT = 10

CONSIGNE = (
    "Tu decris, sans connaitre leur auteur, des propositions de programmes politiques. Ne cherche pas a deviner le "
    "candidat et n'utilise aucune connaissance sur les partis. Pour chaque proposition (theme, title, description, quote), "
    "reponds a chaque question du bareme `rubric` en choisissant exactement une cle de `options`. Une question qui a une "
    "condition `applies_if` recoit null si la condition n'est pas remplie.\n"
    "`levier`, `portee`, `precision`, `instrument`, `cout` et `faisabilite` decrivent le moyen reellement prevu : un "
    "objectif sans moyen precise est une declaration. `changement` et les questions de sens decrivent ce que la mesure "
    "vise, meme seulement annonce : un objectif declare (abolir le capitalisme, socialiser l'economie, sortir d'un "
    "traite, reduire fortement la depense publique, renover massivement les logements) a un sens et une ampleur de "
    "changement visee, et remplit la condition de son axe. Reponds « inchange », « neutre » ou « statu quo » seulement "
    "si l'orientation ou le changement vise sont reellement mixtes ou nuls, jamais parce que les moyens manquent. Pour `cout`, "
    "donne un ordre de grandeur realiste du dispositif (effectifs, beneficiaires, montants comparables) ; indeterminable "
    "seulement si le texte est trop vague.\n"
    "Donne pour chaque question une confiance entre 0 et 1, puis une note d'audit tres breve (160 caracteres maximum) "
    "sur les choix les plus hesitants.\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"question\": "
    "{\"value\": \"...\", \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu.")


def rubrique() -> dict[str, Any]:
    out = {}
    for k, q in Q.QUESTIONS.items():
        entree = {"question": q["instructions"], "options": q["criteria"]}
        if q.get("condition"):
            entree["applies_if"] = ps.TYPESAFE_QUESTIONS[q["condition"]]["instructions"]
        out[k] = entree
    return out


def schema() -> dict[str, Any]:
    def valeur(k: str) -> dict[str, Any]:
        options = list(Q.QUESTIONS[k]["criteria"])
        return {"type": ["string", "null"], "enum": options + [None]} if k in Q.CONDITIONNELLES else {"type": "string", "enum": options}
    a = {k: {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
             "properties": {"value": valeur(k), "confidence": {"type": "number"}}} for k in Q.QUESTIONS}
    review = {"type": "object", "additionalProperties": False, "required": ["id", "assessments", "note"],
              "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                             "assessments": {"type": "object", "additionalProperties": False, "required": list(Q.QUESTIONS),
                                             "properties": a}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "items": review}}}


def requete(modele: str, lot: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    corps = {"rubric": rubrique(), "proposals": lot}
    # Plafond de sortie par lot de 10 : environ 3 000 tokens mesures en low, 3 600 en medium, davantage en high.
    # OpenRouter reserve ce plafond pour estimer un batch : un plafond trop haut fait refuser l'envoi.
    max_tokens = {"low": 10000, "medium": 16000}.get(effort, 32000)
    return {"model": modele, "max_tokens": max_tokens, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "questionnaire", "strict": True, "schema": schema()}},
            "messages": [{"role": "user", "content": CONSIGNE + "\n" + json.dumps(corps, ensure_ascii=False)}]}


def item(m: dict[str, Any], noms: set[str], reprise: int = 0) -> dict[str, Any]:
    """Texte aveugle de la derniere version (l'identifiant envoye ne contient pas le nom du candidat).

    reprise > 0 : retraitement demande ; le numero change la cle de cache, donc force une nouvelle lecture.
    """
    v = m["versions"][-1]
    it = blind_item({"id": m["uid"], "theme_id": m.get("theme_id"), "title": v["title"], "description": v["description"],
                     "source_evidence": v.get("sources") or [{}]}, noms)
    it["id"] = rc.short_id(m["historique"]["corpus_id"])
    if reprise:
        it["reprise"] = reprise
    return it


def reprises(m: dict[str, Any], decisions: list[dict[str, Any]]) -> int:
    return sum(d["uid"] == m["uid"] and d["type"] == "retraiter" for d in decisions)


def cle(modele: str, it: dict[str, Any], effort: str = "medium") -> str:
    """Cle de cache ; l'effort n'y entre que s'il differe de « medium » (le cache existant reste valable)."""
    contenu = {"v": Q.VERSION, "modele": modele, "item": it, "rubrique": rubrique(), "consigne": CONSIGNE}
    if effort != "medium":
        contenu["effort"] = effort
    return digest(contenu)


def lire(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reponse chat -> {id court: {assessments, note}} ; une entree incomplete ou invalide est ecartee."""
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Questionnaire").get("reviews")
    if not isinstance(items, list):
        raise ValueError("Objet {'reviews': [...]} attendu.")
    attendus = {x["id"] for x in lot}
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict) or it.get("id") not in attendus or it["id"] in out:
            continue
        a, propre = it.get("assessments") or {}, {}
        for k in Q.QUESTIONS:
            e = a.get(k)
            if not isinstance(e, dict):
                break
            val, conf = e.get("value"), e.get("confidence")
            if (val is None and k not in Q.CONDITIONNELLES) or (val is not None and val not in Q.QUESTIONS[k]["criteria"]):
                break
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                break
            propre[k] = {"value": val, "confidence": round(float(conf), 2)}
        else:
            out[it["id"]] = {"assessments": propre, "note": str(it.get("note") or "")[:200]}
    if not out:
        raise ValueError("Aucune annotation valide.")
    return out


def a_annoter(base: dict[str, Any], decisions: list[dict[str, Any]], uids: set[str] | None = None) -> list[dict[str, Any]]:
    """Mesures a (re)annoter : pilote (uids), ou sans q1, a_annoter, ou retraitement demande sur la version courante."""
    derniere_demande: dict[str, str] = {}
    for d in decisions:
        if d["type"] == "retraiter":
            derniere_demande[d["uid"]] = max(d["date"], derniere_demande.get(d["uid"], ""))
    out = []
    for m in base["mesures"]:
        if m["statut"] in ("rejetee", "remplacee"):
            continue
        if uids is not None:
            if m["uid"] in uids:
                out.append(m)
            continue
        a = m.get("annotation") or {}
        demande = derniere_demande.get(m["uid"], "") > (a.get("date") or "")  # retraitement posterieur a l'annotation
        if a.get("version") != Q.VERSION or m.get("a_annoter") or demande:
            out.append(m)
    return out


def annoter_direct(lots: list[list[dict[str, Any]]], modele: str, effort: str, cle_api: str, journal: Any,
                   cache: dict[str, Any], max_cost: float, appel=None) -> dict[str, int]:
    """Appels directs lot par lot sous plafond (cumul estime ou cout reel du journal, le plus grand)."""
    from update_corpus_2027 import journal_cost
    appel = appel or request_json
    stats = {"lots": 0, "echecs": 0, "annotees": 0}
    estime = 0.0
    for lot in lots:
        depense = max(estime, journal_cost(journal.path) if journal is not None else 0.0)
        if depense + COUT_DIRECT * len(lot) > max_cost:
            break
        estime = depense + COUT_DIRECT * len(lot)
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(requete(modele, lot, effort), ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
        stats["lots"] += 1
        try:
            res = lire(appel(req, 600, journal=journal, stage="annotation_q1", proposal_ids=[x["id"] for x in lot]), lot)
        except (OSError, ValueError, KeyError) as exc:
            stats["echecs"] += 1
            print(f"ERREUR annotation ({len(lot)} mesures) : {exc}", file=sys.stderr)
            continue
        for x in lot:
            if x["id"] in res:
                cache[cle(modele, x, effort)] = res[x["id"]]
                stats["annotees"] += 1
    return stats


def appliquer(m: dict[str, Any], review: dict[str, Any], modele: str, date: str) -> None:
    precedente = m.get("annotation")
    if precedente and precedente.get("version") != Q.VERSION:
        m.setdefault("historique", {}).setdefault("annotations_precedentes", []).append(
            {k: precedente.get(k) for k in ("version", "methode", "modele", "reponses")})
    m["annotation"] = {"version": Q.VERSION, "methode": METHODE, "modele": modele, "date": date,
                       "version_mesure": len(m["versions"]),
                       "reponses": {k: a["value"] for k, a in review["assessments"].items()},
                       "confiances": {k: a["confidence"] for k, a in review["assessments"].items()},
                       "note": review.get("note")}
    m["a_annoter"] = False


def comparer(mesures: list[dict[str, Any]], items: list[dict[str, Any]], cache: dict[str, Any], modele: str,
             effort: str, reference: str, cout: float = 0.0) -> dict[str, Any]:
    """Compare deux lectures en cache (efforts differents) : accord par question et ecarts par axe calcule."""
    import statistics
    lignes, accord, n = [], {k: 0 for k in Q.QUESTIONS}, 0
    axes = ("eco", "soc", "sov", "ouverture", "ecolo", "feasibility", "rights_status", "income_direction")
    ecarts: dict[str, list[float]] = {a: [] for a in axes}
    applic = {a: [0, 0] for a in axes}  # [meme applicabilite, total]
    for m, it in zip(mesures, items):
        a, b = cache.get(cle(modele, it, effort)), cache.get(cle(modele, it, reference))
        if not a or not b:
            continue
        n += 1
        ra = {k: x["value"] for k, x in a["assessments"].items()}
        rb = {k: x["value"] for k, x in b["assessments"].items()}
        for k in Q.QUESTIONS:
            accord[k] += ra.get(k) == rb.get(k)
        va, _ = Q.calculer(ra)
        vb, _ = Q.calculer(rb)
        for ax in axes:
            applic[ax][1] += 1
            applic[ax][0] += (va[ax] is None) == (vb[ax] is None)
            if va[ax] is not None and vb[ax] is not None:
                ecarts[ax].append(abs(va[ax] - vb[ax]))
        lignes.append({"uid": m["uid"], "title": m["versions"][-1]["title"], effort: va, reference: vb,
                       "differences": {k: [ra.get(k), rb.get(k)] for k in Q.QUESTIONS if ra.get(k) != rb.get(k)}})
    par_axe = {ax: {"meme_applicabilite": round(applic[ax][0] / applic[ax][1], 2) if applic[ax][1] else None,
                    "n_deux_notes": len(e), "ecart_moyen": round(statistics.mean(e), 1) if e else None,
                    "part_a_10_points": round(sum(x <= 10 for x in e) / len(e), 2) if e else None,
                    "part_a_25_points": round(sum(x <= 25 for x in e) / len(e), 2) if e else None}
               for ax, e in ecarts.items()}
    return {"modele": modele, "effort": effort, "reference": reference, "mesures_comparees": n, "cout": round(cout, 4),
            "accord_par_question": {k: round(v / n, 2) for k, v in accord.items()} if n else {},
            "par_axe": par_axe, "mesures": lignes}


# --- Complements : questions ajoutees apres coup (questionnaire_2027.COMPLEMENTS) --------------------------------------

COUT_COMPLEMENT = .0004   # par mesure en appel direct (une question courte), estimation prudente ; batch = moitie
TAILLE_LOT_COMPLEMENT = 20
CONDITIONS_COMPLEMENT = {  # mesures concernees : celles dont l'axe de la question s'applique deja
    "soc_finalite": lambda r: r.get("soc_autorite") is not None or r.get("soc_libertes") is not None,
    # mesures dont l'axe immigration s'applique, ou l'axe societe (hors probite et hors finalite jugee non applicable)
    "degre_rupture": lambda r: r.get("ouv_sens") is not None or (
        r.get("soc_autorite") is not None and (r.get("soc_finalite") not in (None, "probite_pouvoirs") if "soc_finalite" in r else True)),
}
CONSIGNE_COMPLEMENT = (
    "Tu decris, sans connaitre leur auteur, des propositions de programmes politiques. Ne cherche pas a deviner le "
    "candidat et n'utilise aucune connaissance sur les partis. Pour chaque proposition (theme, title, description, quote), "
    "reponds uniquement aux questions du bareme `rubric` en choisissant exactement une cle de `options` ; null si la "
    "condition `applies_if` n'est pas remplie. Choisis selon l'objet principal de la mesure, pas selon sa presentation.\n"
    "Donne pour chaque question une confiance entre 0 et 1, puis une note tres breve (100 caracteres maximum).\n"
    "Reponds uniquement par l'objet JSON {\"reviews\": [{\"id\": \"...\", \"assessments\": {\"question\": "
    "{\"value\": \"...\", \"confidence\": 0.0}}, \"note\": \"...\"}]}, une entree par identifiant recu.")


def rubrique_complement(questions: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for k in questions:
        q = Q.COMPLEMENTS[k]
        out[k] = {"question": q["instructions"], "options": q["criteria"],
                  **({"applies_if": ps.TYPESAFE_QUESTIONS[q["condition"]]["instructions"]} if q.get("condition") else {})}
    return out


def schema_complement(questions: tuple[str, ...]) -> dict[str, Any]:
    a = {k: {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
             "properties": {"value": {"type": ["string", "null"], "enum": list(Q.COMPLEMENTS[k]["criteria"]) + [None]},
                            "confidence": {"type": "number"}}} for k in questions}
    review = {"type": "object", "additionalProperties": False, "required": ["id", "assessments", "note"],
              "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                             "assessments": {"type": "object", "additionalProperties": False, "required": list(questions),
                                             "properties": a}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "items": review}}}


def requete_complement(modele: str, lot: list[dict[str, Any]], effort: str, questions: tuple[str, ...]) -> dict[str, Any]:
    corps = {"rubric": rubrique_complement(questions), "proposals": lot}
    return {"model": modele, "max_tokens": {"low": 4000, "medium": 8000}.get(effort, 16000), "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "complement", "strict": True,
                                                                        "schema": schema_complement(questions)}},
            "messages": [{"role": "user", "content": CONSIGNE_COMPLEMENT + "\n" + json.dumps(corps, ensure_ascii=False)}]}


def cle_complement(modele: str, it: dict[str, Any], questions: tuple[str, ...], effort: str = "low") -> str:
    return digest({"v": Q.VERSION, "complement": list(questions), "modele": modele, "effort": effort, "item": it,
                   "rubrique": rubrique_complement(questions), "consigne": CONSIGNE_COMPLEMENT})


def lire_complement(reponse: dict[str, Any], lot: list[dict[str, Any]], questions: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Complement").get("reviews")
    attendus, out = {x["id"] for x in lot}, {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("id") not in attendus or it["id"] in out:
            continue
        a, propre = it.get("assessments") or {}, {}
        for k in questions:
            e = a.get(k) if isinstance(a, dict) else None
            if not isinstance(e, dict):
                break
            val, conf = e.get("value"), e.get("confidence")
            if (val is not None and val not in Q.COMPLEMENTS[k]["criteria"]) or isinstance(conf, bool) \
                    or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                break
            propre[k] = {"value": val, "confidence": round(float(conf), 2)}
        else:
            out[it["id"]] = {"assessments": propre, "note": str(it.get("note") or "")[:160]}
    if not out:
        raise ValueError("Aucune reponse de complement valide.")
    return out


def a_completer(base: dict[str, Any], question: str, uids: set[str] | None = None) -> list[dict[str, Any]]:
    """Mesures annotees en q1, concernees par la question (axe deja applicable) et sans reponse a celle-ci."""
    condition = CONDITIONS_COMPLEMENT[question]
    out = []
    for m in base["mesures"]:
        a = m.get("annotation") or {}
        if m["statut"] in ("rejetee", "remplacee") or a.get("version") != Q.VERSION or (uids is not None and m["uid"] not in uids):
            continue
        if question not in (a.get("reponses") or {}) and condition(a["reponses"]):
            out.append(m)
    return out


def completer_direct(lots: list[list[dict[str, Any]]], modele: str, effort: str, questions: tuple[str, ...], cle_api: str,
                     journal: Any, cache: dict[str, Any], max_cost: float, appel=None) -> dict[str, int]:
    from update_corpus_2027 import journal_cost
    appel = appel or request_json
    stats, estime = {"lots": 0, "echecs": 0, "completees": 0}, 0.0
    for lot in lots:
        depense = max(estime, journal_cost(journal.path) if journal is not None else 0.0)
        if depense + COUT_COMPLEMENT * len(lot) > max_cost:
            break
        estime = depense + COUT_COMPLEMENT * len(lot)
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(requete_complement(modele, lot, effort, questions), ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
        stats["lots"] += 1
        try:
            res = lire_complement(appel(req, 300, journal=journal, stage="complement_q1", proposal_ids=[x["id"] for x in lot]),
                                  lot, questions)
        except (OSError, ValueError, KeyError) as exc:
            stats["echecs"] += 1
            print(f"ERREUR complement ({len(lot)} mesures) : {exc}", file=sys.stderr)
            continue
        for x in lot:
            if x["id"] in res:
                cache[cle_complement(modele, x, questions, effort)] = res[x["id"]]
                stats["completees"] += 1
    return stats


def appliquer_complement(m: dict[str, Any], review: dict[str, Any], modele: str, effort: str, date: str) -> None:
    a = m["annotation"]
    for k, x in review["assessments"].items():
        a["reponses"][k] = x["value"]
        a.setdefault("confiances", {})[k] = x["confidence"]
        a.setdefault("complements", {})[k] = {"modele": modele, "effort": effort, "date": date, "note": review.get("note")}
