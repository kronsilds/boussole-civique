"""Lecture avec contexte : questionnaire q1 pose avec le passage du document et le lexique du candidat.

Methode standard de notation depuis le 2026-11-07 (toutes les mesures, memes regles et memes elements) ; d'abord
appliquee aux seules mesures en confiance basse (questions de sens). Le questionnaire q1 est pose avec :
- `passage` : l'extrait du document autour de la citation (source principale, avec la proposition elle-meme) ;
- `lexique` : les definitions, citees dans les documents du meme auteur, des termes ambigus qu'elle emploie
  (source secondaire, seulement pour lever une ambiguite de vocabulaire ; voir lexique_2027.py) ;
- une reponse « indetermine » aux questions de sens, reservee a une direction absente ou contradictoire.
Aveugle conserve : noms et partis masques. La nouvelle lecture remplace les reponses q1 (l'ancienne reste dans
l'historique de la mesure). Essais : SUIVI_PROJET.md, pilote_contexte_2027.py.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import annotation_2027 as A
import programme_corpus_2027 as pc
import questionnaire_2027 as Q
from scoring_context_2027 import digest, request_json

METHODE = "contexte-v1"
SENS = tuple(k for k in Q.QUESTIONS_SENS if k in Q.QUESTIONS)
FENETRE = 1200          # caracteres avant et apres la citation
COUT_ESTIME = .003      # par mesure (essais du 2026-11-07 : 0,0028 $ avec le passage)
SEUIL = .5
CONSIGNE = A.CONSIGNE.replace(
    "Donne pour chaque question une confiance",
    "Chaque proposition est accompagnee de `passage`, l'extrait du document d'ou elle vient, autour de la citation : "
    "sers-t'en pour comprendre le sens que le document donne a ses termes et le contenu de la mesure, sans noter les "
    "autres mesures du passage. Une proposition peut aussi avoir `lexique` : pour des termes qu'elle emploie, des phrases "
    "d'autres documents du meme auteur qui montrent le sens qu'il leur donne. C'est une source secondaire : la "
    "proposition et le passage priment ; le lexique sert seulement a lever une ambiguite de vocabulaire, jamais a en "
    "deduire d'autres mesures. Pour les questions de sens, « indetermine » est reserve au cas ou la direction elle-meme "
    "manque ou se contredit, dans la proposition comme dans le passage. Un objectif annonce sans moyen (reduire la "
    "depense, proteger un secteur, garantir un prix, renforcer un controle) a une direction : donne-la. N'utilise jamais "
    "« indetermine » parce que les moyens, le cout, le calendrier ou le perimetre ne sont pas precises, ni a la place de "
    "null quand l'axe ne s'applique pas.\n"
    "Donne pour chaque question une confiance")


def rubrique() -> dict[str, Any]:
    r = A.rubrique()
    for k in SENS:
        r[k] = {**r[k], "options": {**r[k]["options"], Q.INDETERMINE: Q.LIBELLE_INDETERMINE}}
    return r


def schema() -> dict[str, Any]:
    s = A.schema()
    props = s["properties"]["reviews"]["items"]["properties"]["assessments"]["properties"]
    for k in SENS:
        props[k]["properties"]["value"]["enum"] = [v for v in props[k]["properties"]["value"]["enum"] if v is not None] + \
            [Q.INDETERMINE] + ([None] if k in Q.CONDITIONNELLES else [])
    return s


def requete(modele: str, lot: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    return {"model": modele, "max_tokens": 12000, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "questionnaire", "strict": True, "schema": schema()}},
            "messages": [{"role": "user", "content": CONSIGNE + "\n" + json.dumps({"rubric": rubrique(), "proposals": lot},
                                                                                  ensure_ascii=False)}]}


def lire(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reponse chat -> {id court: {assessments, note}} ; une entree incomplete ou invalide est ecartee."""
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Questionnaire").get("reviews") or []
    attendus, out = {x["id"] for x in lot}, {}
    for it in items:
        if not isinstance(it, dict) or it.get("id") not in attendus or it["id"] in out:
            continue
        a, propre = it.get("assessments") or {}, {}
        for k in Q.QUESTIONS:
            e = a.get(k) if isinstance(a.get(k), dict) else {}
            val, conf = e.get("value"), e.get("confidence")
            permis = set(Q.QUESTIONS[k]["criteria"]) | ({Q.INDETERMINE} if k in SENS else set())
            if (val is None and k not in Q.CONDITIONNELLES) or (val is not None and val not in permis) or \
                    isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                break
            propre[k] = {"value": val, "confidence": round(float(conf), 2)}
        else:
            out[it["id"]] = {"assessments": propre, "note": str(it.get("note") or "")[:200]}
    if not out:
        raise ValueError("Aucune relecture valide.")
    return out


def masqueur(noms: set[str]):
    motif = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True)) + r")(?!\w)", re.I) \
        if noms else None
    return lambda t: motif.sub("[le candidat]", t) if motif and t else t


def passage(m: dict[str, Any], textes: Path, masque) -> str:
    """Extrait du document autour de la premiere citation (pages voisines comprises si la citation est en bord de page)."""
    src = (m["versions"][-1].get("sources") or [{}])[0] or {}
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
    citation = src.get("quote") or ""
    pos = texte.find(citation[:60])
    pos = pos if pos >= 0 else int(src.get("start") or 0)
    bloc, debut = avant + "\n" + texte + "\n" + apres, len(avant) + 1 + pos
    return masque(bloc[max(0, debut - FENETRE):debut + len(citation) + FENETRE].strip())


def item(m: dict[str, Any], noms: set[str], textes: Path, lexique: dict[str, Any], masque, reprise: int = 0) -> dict[str, Any]:
    """reprise > 0 : retraitement demande au tableau de bord ; change la cle de cache, donc force une nouvelle lecture."""
    import lexique_2027 as LX
    it = A.item(m, noms, reprise)
    it["passage"] = passage(m, textes, masque)
    v = m["versions"][-1]
    texte = f"{v['title']} {v.get('description') or ''} {((v.get('sources') or [{}])[0] or {}).get('quote') or ''}"
    entrees = LX.entrees(lexique, m["candidate_id"], texte)
    if entrees:
        it["lexique"] = entrees
    return it


def cle(modele: str, it: dict[str, Any], effort: str) -> str:
    return digest({"methode": METHODE, "modele": modele, "effort": effort, "item": it, "rubrique": rubrique(), "consigne": CONSIGNE})


def doutes(a: dict[str, Any], corrections: dict[str, Any] | None = None) -> list[str]:
    """Questions de sens sous le seuil (hors reponses corrigees et hors « indetermine », reponse explicite)."""
    conf, rep = a.get("confiances") or {}, a.get("reponses") or {}
    return [k for k in SENS if k not in (corrections or {}) and rep.get(k) != Q.INDETERMINE
            and conf.get(k) is not None and conf[k] < SEUIL]


def a_relire(base: dict[str, Any], decisions: list[dict[str, Any]] | None = None, tous: bool = False) -> list[dict[str, Any]]:
    """Mesures a lire avec le contexte, pas encore lues ainsi pour leur version (ou retraitement demande depuis).

    Par defaut : mesures annotees en q1 avec un doute de sens. tous=True : toute mesure active (notation homogene),
    y compris une mesure nouvelle, sans annotation, ou au texte modifie.
    """
    demandes: dict[str, str] = {}
    for d in decisions or []:
        if d["type"] == "retraiter":
            demandes[d["uid"]] = max(d["date"], demandes.get(d["uid"], ""))
    out = []
    for m in base["mesures"]:
        if m["statut"] not in ("active", "non_reprise"):
            continue
        a = m.get("annotation") or {}
        ctx = a.get("contexte") or {}
        demande = demandes.get(m["uid"], "") > (ctx.get("date") or a.get("date") or "")
        if ctx.get("version_mesure") == len(m["versions"]) and not m.get("a_annoter") and not demande:
            continue
        annotee = a.get("version") == Q.VERSION and not m.get("a_annoter")
        if tous or demande or (annotee and doutes(a)):
            out.append(m)
    return out


def relire_direct(lots: list[list[dict[str, Any]]], modele: str, effort: str, cle_api: str, journal: Any,
                  cache: dict[str, Any], max_cost: float, ecrire=None, appel=None) -> dict[str, int]:
    """Appels directs lot par lot sous plafond (cumul estime ou cout reel du journal, le plus grand)."""
    from update_corpus_2027 import journal_cost
    appel = appel or request_json
    stats = {"lots": 0, "echecs": 0, "relues": 0}
    estime = 0.0
    for lot in lots:
        depense = max(estime, journal_cost(journal.path) if journal is not None else 0.0)
        if depense + COUT_ESTIME * len(lot) > max_cost:
            print("Plafond atteint : arret (relancer reprend ou il s'est arrete).")
            break
        estime = depense + COUT_ESTIME * len(lot)
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(requete(modele, lot, effort), ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
        stats["lots"] += 1
        try:
            res = lire(appel(req, 600, journal=journal, stage="relecture_contexte", proposal_ids=[x["id"] for x in lot]), lot)
        except (OSError, ValueError, KeyError) as exc:
            stats["echecs"] += 1
            print(f"ERREUR relecture ({len(lot)} mesures) : {exc}", file=sys.stderr)
            continue
        for x in lot:
            if x["id"] in res:
                cache[cle(modele, x, effort)] = res[x["id"]]
                stats["relues"] += 1
        if ecrire:
            ecrire(cache)  # cache ecrit apres chaque lot : une interruption ne fait rien perdre
    return stats


def appliquer(m: dict[str, Any], review: dict[str, Any], modele: str, date: str) -> None:
    """Annotation q1 lue avec le contexte : remplace la precedente (gardee dans l'historique) ; les complements sont
    conserves si le texte de la mesure n'a pas change depuis."""
    a = m.get("annotation") or {}
    if a.get("reponses"):
        m.setdefault("historique", {}).setdefault("annotations_precedentes", []).append(
            {k: a.get(k) for k in ("version", "methode", "modele", "date", "reponses", "confiances", "note")})
    meme_texte = a.get("version_mesure", len(m["versions"])) == len(m["versions"]) and not m.get("a_annoter")
    complements = {k: v for k, v in (a.get("reponses") or {}).items() if k not in Q.QUESTIONS} if meme_texte else {}
    conf_compl = {k: v for k, v in (a.get("confiances") or {}).items() if k not in Q.QUESTIONS} if meme_texte else {}
    m["annotation"] = {"version": Q.VERSION, "methode": A.METHODE, "modele": modele, "date": date,
                       "version_mesure": len(m["versions"]),
                       "reponses": {**{k: e["value"] for k, e in review["assessments"].items()}, **complements},
                       "confiances": {**{k: e["confidence"] for k, e in review["assessments"].items()}, **conf_compl},
                       "note": review.get("note"),
                       "contexte": {"methode": METHODE, "modele": modele, "date": date, "version_mesure": len(m["versions"])}}
    m["a_annoter"] = False
