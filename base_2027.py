"""Base unique des mesures et etapes gratuites du pipeline unifie (spec_pipeline_unifie_2027.md, phase 1).

- migrer : construit ou met a jour base_2027.json depuis une sortie de scoring (uid stables, versions, statuts) ;
- decisions humaines : decisions_2027.json, en ajout seulement, liees a une version de mesure ;
- calculs : decisions appliquees, note eco recalculee si une reponse est corrigee, importance structurelle, ideologie ;
- file : motifs de validation avec priorite et date ;
- export : donnees_interface_2027.json (meme format que export_interface_2027) et nouveautes_2027.json ;
- bilan : runs/AAAA-MM-JJ_HHMM.json et .md.

Aucun appel reseau. Les etapes payantes (sources, extraction, rapprochement, annotation) viennent aux phases 2, 3 et 5.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import export_interface_2027 as ei
import pipeline_scoring_2027 as ps
import questionnaire_2027 as Q
import questionnaire_q2_2027 as Q2
from scoring_context_2027 import dimension_value, update_importance

VERSION_BASE = 1
CHAMPS_EXCLUS = ("scoring_context",)  # 32 Mo de contexte d'audit, conserve dans les fichiers d'origine
STATUTS = ("active", "non_reprise", "remplacee", "rejetee")
TYPES_DECISION = ("validation", "correction", "rejet", "fusion", "separation", "retraiter", "note")
PRIORITES = {"mesure_modifiee": 1, "decision_a_revoir": 1, "rapprochement_incertain": 1, "deplacement_fort": 2,
             "axe_perdu_ou_gagne": 2, "nouvelle_mesure": 2, "confiance_basse": 3, "divergence_lectures": 3, "non_reprise": 3}
BLOQUANTS = frozenset({"mesure_modifiee", "rapprochement_incertain"})  # la version publiee precedente reste affichee
NON_RELUE = frozenset({"nouvelle_mesure", "confiance_basse"})          # publiee tout de suite, badge « non relue »
SEUIL_CONFIANCE = .5
SEUIL_DEPLACEMENT = 25
SEUIL_NOUVEAUTE = 10
AXES_SUIVIS = ("eco", "soc", "sov", "ouverture", "ecolo")
# Explications en mots exportees (fiche d'une proposition) : axes suivis, axes ajoutes par q2, faisabilite calculee (q2).
EXPLIQUES = (*AXES_SUIVIS, "inst", "inter", "defense", "feasibility")
METHODES_QUESTIONNAIRE = ("questionnaire-q1", "questionnaire-q2")


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empreinte(title: Any, description: Any) -> str:
    texte = " ".join(f"{title or ''} || {description or ''}".split()).casefold()
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


# --- Fichiers ---------------------------------------------------------------------------------------------------

def lire_json(path: Path, defaut: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else defaut


def ecrire_json(path: Path, data: Any, sauvegardes: Path | None = None, garder: int = 5, compact: bool = False) -> None:
    """Ecriture atomique (fichier temporaire puis renommage), avec rotation des sauvegardes si demandee."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if sauvegardes and path.exists():
        sauvegardes.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.replace(path, sauvegardes / f"{path.stem}_{stamp}{path.suffix}")
        anciennes = sorted(sauvegardes.glob(f"{path.stem}_*{path.suffix}"))
        for vieille in anciennes[:-garder]:
            vieille.unlink()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":") if compact else None,
                              indent=None if compact else 1), encoding="utf-8")
    os.replace(tmp, path)


# --- Migration ----------------------------------------------------------------------------------------------------

def migrer(data: dict[str, Any], marqueurs: dict[str, dict[str, Any]] | None = None,
           base: dict[str, Any] | None = None, date: str | None = None) -> tuple[dict[str, Any], dict[str, int]]:
    """Cree la base, ou la met a jour en gardant uid, versions, decisions et file (cle : identifiant corpus)."""
    date = date or maintenant()
    marqueurs = marqueurs or {}
    premiere = base is None
    base = base or {"meta": {"version_base": VERSION_BASE, "cree_le": date}, "compteurs": {}, "mesures": []}
    par_corpus = {m["historique"]["corpus_id"]: m for m in base["mesures"]}
    vus, rapport = set(), Counter()
    for p in data["proposals"]:
        cid = p["id"]
        vus.add(cid)
        proposition = {k: v for k, v in p.items() if k not in CHAMPS_EXCLUS}
        texte = empreinte(p.get("title"), p.get("description"))
        marque = marqueurs.get(cid) or {}
        m = par_corpus.get(cid)
        if m is None:
            cand = p["candidate_id"]
            n = base["compteurs"].get(cand, 0) + 1
            base["compteurs"][cand] = n
            m = {"uid": f"m-{cand}-{n:04d}", "candidate_id": cand, "theme_id": p.get("theme_id"), "statut": "active",
                 "versions": [], "file": [], "historique": {"corpus_id": cid}, "ajoutee_le": date,
                 "nouvelle": not premiere}
            base["mesures"].append(m)
            par_corpus[cid] = m
            rapport["ajoutees"] += 1
        elif m["statut"] == "non_reprise":
            m["statut"] = "active"
            rapport["reprises"] += 1
        if not m["versions"] or m["versions"][-1]["empreinte"] != texte:
            if m["versions"]:
                rapport["nouvelles_versions"] += 1
                m["a_annoter"] = True  # notes de l'ancienne version gardees jusqu'a la reannotation
            m["versions"].append({"n": len(m["versions"]) + 1, "date": date, "title": p.get("title"),
                                  "description": p.get("description"), "empreinte": texte,
                                  "sources": p.get("source_evidence") or []})
        m["theme_id"] = p.get("theme_id")
        m["proposition"] = proposition
        m.setdefault("annotation", None)  # l'annotation q1 n'est jamais ecrasee par une migration
        m["affichage"] = {"selection": marque.get("selection") or p.get("selection") or "n8",
                          "precision": marque.get("precision") or p.get("precision"),
                          "precision_llm": marque.get("precision_llm", p.get("precision_llm"))}
    for m in base["mesures"]:
        if m["historique"]["corpus_id"] not in vus and m["statut"] == "active":
            m["statut"] = "non_reprise"
            rapport["non_reprises"] += 1
    base["meta"].update(mis_a_jour_le=date, source=data.get("meta", {}).get("pipeline"))
    for key in ("candidates", "themes", "dimensions_schema"):
        if key in data:
            base[key] = data[key]
    rapport["mesures"] = len(base["mesures"])
    return base, dict(rapport)


# --- Decisions ------------------------------------------------------------------------------------------------------

def nouvelle_decision(decisions: list[dict[str, Any]], base: dict[str, Any], uid: str, type_: str,
                      champ: str | None = None, valeur: Any = None, cible: str | None = None,
                      motif: str | None = None, auteur: str = "local", date: str | None = None) -> dict[str, Any]:
    """Valide puis ajoute une decision (liee a la version courante de la mesure)."""
    mesures = {m["uid"]: m for m in base["mesures"]}
    if uid not in mesures:
        raise ValueError(f"Mesure inconnue : {uid}")
    if type_ not in TYPES_DECISION:
        raise ValueError(f"Type de decision inconnu : {type_}")
    if type_ == "correction":
        a = mesures[uid].get("annotation")
        if not a:
            raise ValueError("Mesure sans annotation : rien a corriger avant l'annotation.")
        if a.get("version") == Q2.VERSION:
            q = Q2.QUESTIONS.get(champ)
            if q is None:
                raise ValueError(f"Champ corrigeable (q2) : {', '.join(Q2.QUESTIONS)}")
            if valeur is not None and valeur not in q["options"]:
                raise ValueError(f"Valeur inconnue pour {champ}")
        elif a.get("version") != Q.VERSION:
            raise ValueError(f"Annotation {a.get('version')} : relancer l'annotation {Q.VERSION} avant de corriger.")
        elif champ not in Q.TOUTES:
            raise ValueError(f"Champ corrigeable : {', '.join(Q.TOUTES)}")
        elif valeur not in Q.TOUTES[champ]["criteria"] and not (valeur is None and champ in Q.CONDITIONNELLES) \
                and not (valeur == Q.INDETERMINE and champ in Q.QUESTIONS_SENS):
            raise ValueError(f"Valeur inconnue pour {champ}")
    if type_ == "fusion" and (cible not in mesures or cible == uid):
        raise ValueError("Fusion : --cible doit etre une autre mesure existante.")
    if type_ == "rejet" and not motif:
        raise ValueError("Rejet : un motif est requis.")
    decision = {"id": f"d-{len(decisions) + 1:06d}", "date": date or maintenant(), "auteur": auteur, "uid": uid,
                "version": len(mesures[uid]["versions"]), "type": type_}
    decision.update({k: v for k, v in (("champ", champ), ("valeur", valeur), ("cible", cible), ("motif", motif))
                     if v is not None or (k == "valeur" and type_ == "correction")})
    decisions.append(decision)
    return decision


def decisions_par_mesure(decisions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in sorted(decisions, key=lambda d: d["date"]):
        out.setdefault(d["uid"], []).append(d)
    return out


# --- Calculs --------------------------------------------------------------------------------------------------------

def importance_structurelle(p: dict[str, Any], precision: str | None) -> int:
    """Importance v1 (0..100), gratuite et explicable ; poids a recalibrer (spec pipeline, decision 2)."""
    rep = p.get("repetition") or {}
    proches = min(rep.get("related_proposals") or 0, 6) / 6
    redites = min(1, (rep.get("similar_proposals") or 0) + max(0, (rep.get("documents") or 1) - 1)
                  + max(0, len(p.get("source_evidence") or []) - 1))
    prec = {"chiffre": 1.0, "precis": .6}.get(precision or p.get("precision"), 0.0)
    pos = ((p.get("source_evidence") or [{}])[0].get("position") or {})
    debut = 1 - pos["segment_index"] / max(pos["segment_total"], 1) if pos.get("segment_total") else .5
    return round(15 + 30 * proches + 20 * redites + 20 * prec + 15 * debut)


def vue(m: dict[str, Any], decisions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Proposition affichable (format historique) avec decisions appliquees, et etat de relecture."""
    version = len(m["versions"])
    etat = {"validee_le": None, "a_revoir": False, "rejetee": None, "fusion": None, "retraiter": False, "corrections": {}}
    for d in decisions:
        if d["version"] != version:
            if d["type"] in ("validation", "correction"):
                etat["a_revoir"] = True
            continue
        if d["type"] == "validation":
            etat["validee_le"] = d["date"]
            etat["a_revoir"] = False
        elif d["type"] == "correction":
            etat["corrections"][d["champ"]] = d["valeur"]
        elif d["type"] == "rejet":
            etat["rejetee"] = d.get("motif")
        elif d["type"] == "fusion":
            etat["fusion"] = d["cible"]
        elif d["type"] == "retraiter":
            etat["retraiter"] = True
    p = dict(m["proposition"])
    p["id"] = m["uid"]
    a = m.get("annotation")
    precision = m["affichage"].get("precision")
    if a and a.get("version") == Q.VERSION:
        p = appliquer_q1(p, a, etat["corrections"])
        precision = p.get("precision")
        p["importance_sources"] = {**(p.get("importance_sources") or {}), "programme": importance_structurelle(p, precision)}
        ps.derive_fields(p)
        p["threshold_tags"] = Q.etiquettes({**a["reponses"], **etat["corrections"]})  # etiquettes calculees
        p["ideology"] = Q.ideologie(p.get("axes") or {})  # comme la constellation
        update_importance(p)
        return p, etat
    if a and a.get("version") == Q2.VERSION:
        p = appliquer_q2(p, a, etat["corrections"])
        p["importance_sources"] = {**(p.get("importance_sources") or {}), "programme": importance_structurelle(p, p.get("precision"))}
        ps.derive_fields(p)
        reponses = {**a["reponses"], **etat["corrections"]}
        p["threshold_tags"] = Q.etiquettes({**reponses, "levier": Q2.levier(reponses), "precision": p.get("precision")})
        p["ideology"] = Q2.ideologie(p.get("axes") or {})
        update_importance(p)
        return p, etat
    # Mesure pas encore annotee (q1) : notes de la proposition d'origine, en attendant l'annotation.
    p["importance_sources"] = {**(p.get("importance_sources") or {}),
                               "programme": importance_structurelle(p, m["affichage"].get("precision"))}
    ps.derive_fields(p)
    update_importance(p)
    return p, etat


AXES_Q1 = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rupture", "legal_instrument", "cost_estimate",
           *Q.AXES_REVENU)
REPONSES_PAR_AXE = {"eco": ("eco_etat", "eco_distrib", "levier", "portee"), "soc": ("soc_autorite", "soc_libertes", "soc_finalite", "levier", "portee"),
                    "sov": ("sov_niveau", "levier", "portee"), "ouverture": ("ouv_sens", "droits_statut", "levier", "portee"),
                    "ecolo": ("env_sens", "levier", "portee"), "income_direction": ("revenus_sens",), "rupture": ("changement",),
                    "legal_instrument": ("instrument",), "cost_estimate": ("cout",), "feasibility": ("faisabilite",),
                    "rights_status": ("droits_statut",), "rights_income": ("portee",),
                    **{k: tuple(Q.CLASSES_REVENU) for k in Q.AXES_REVENU}}


def appliquer_q1(p: dict[str, Any], a: dict[str, Any], corrections: dict[str, Any]) -> dict[str, Any]:
    """Toutes les notes recalculees depuis les reponses q1 (corrections humaines comprises) ; l'historique est garde
    dans la fiche de la base, pas dans la vue publiee."""
    reponses = {**a["reponses"], **corrections}
    conf = {**(a.get("confiances") or {}), **{k: 1.0 for k in corrections}}
    valeurs, explications = Q.calculer(reponses)
    q = {**p, "axes": dict(p.get("axes") or {}), "score_details": {}}
    for k in AXES_Q1:
        q["axes"][k] = valeurs.get(k)
    q["axes"]["horizon"] = None  # retire du questionnaire (decision du 2026-11-06)
    # « Personnes concernees » (rights_income) = portee de la mesure (0 quelques acteurs ... 100 toute la population)
    portee = Q.D.PORTEE.get(reponses.get("portee"))
    q.update(feasibility=valeurs["feasibility"], rights_status=valeurs["rights_status"],
             rights_income=None if portee is None else round(100 * portee),
             precision=valeurs["precision"], revision=None, relecture_ciblee=None,
             indicateurs=[k for k in Q.INDICATEURS if valeurs.get(k)] or None)
    for k, deps in REPONSES_PAR_AXE.items():
        valeur = q["axes"].get(k) if k in AXES_Q1 else q.get(k)
        q["score_details"][k] = {"status": "scored" if valeur is not None else "not_applicable", "method": "questionnaire-q1",
                                 "model": a.get("modele"),
                                 "confidence": min((conf[d] for d in deps if d in conf), default=None),
                                 "rationale": explications.get(k), "corrigee": sorted(set(deps) & set(corrections)) or None}
    return q


AXES_Q2 = (*(k for k in AXES_Q1), "inst", "inter", "defense", "financement")
REPONSES_PAR_AXE_Q2 = {
    **{axe: (*qs, "levier", "degre", *(("portee",) if axe in Q2.AXES_PORTEE else ()))
       for axe, qs in {"eco": tuple(Q2.POIDS_ECO), "soc": ("soc_autorite", "soc_libertes", "soc_egalite"),
                       "sov": ("sov_niveau",), "ouverture": ("ouv_sens", "droits_statut"), "ecolo": ("env_sens",),
                       "inst": ("inst_objet", "inst_controle"), "inter": ("int_alliances",), "defense": ("def_effort",)}.items()},
    "rupture": ("degre",), "legal_instrument": ("instrument",), "cost_estimate": ("cout",), "financement": ("financement",),
    "feasibility": ("instrument", "cout", "financement", "degre"), "rights_status": ("droits_statut",),
    "rights_income": ("portee",), **{k: tuple(Q.CLASSES_REVENU) for k in Q.AXES_REVENU},
}
_INDICATEUR_Q2 = {"etend": "democratie_directe", "recule": "-democratie_directe"}


def explication_faisabilite(r: dict[str, Any]) -> str | None:
    """Faisabilite q2 : calculee, jamais demandee ; on dit de quoi."""
    if Q2.faisabilite(r) is None:
        return None
    mots = [f"texte nécessaire : {r['instrument'].replace('_', ' ')}"]
    if r.get("cout"):
        mots.append(f"coût : {r['cout'].replace('_', ' ')}")
    if r.get("cout") in Q2.COUTS and r.get("financement"):
        mots.append(f"financement : {r['financement'].replace('_', ' ')}")
    if r.get("degre") == "rupture":
        mots.append("rupture")
    return "calculée · " + " · ".join(mots)


def appliquer_q2(p: dict[str, Any], a: dict[str, Any], corrections: dict[str, Any]) -> dict[str, Any]:
    """Notes recalculees depuis les reponses q2 (questionnaire_q2_2027.calculer) : trois axes de plus (contre-pouvoirs,
    alliances, defense), faisabilite calculee, financement, indicateurs de frequence (democratie directe, probite,
    protection contre les discriminations), regle societe q2. « Personnes concernees » (rights_income) = portee,
    null quand la mesure n'a pas de public (portee non posee)."""
    reponses = {**a["reponses"], **corrections}
    conf = {**(a.get("confiances") or {}), **{k: 1.0 for k in corrections}}
    valeurs, explications = Q2.calculer(reponses)
    explications["feasibility"] = explication_faisabilite(reponses)
    q = {**p, "axes": dict(p.get("axes") or {}), "score_details": {}}
    for k in AXES_Q2:
        q["axes"][k] = valeurs.get(k)
    q["axes"]["horizon"] = None
    portee = Q2.PORTEE.get(reponses.get("portee"))
    indicateurs = [k for k in ("probite", "antidiscrimination") if valeurs.get(k) is True]
    if valeurs.get("democratie_directe") in _INDICATEUR_Q2:   # une mesure qui retire de la decision directe compte en moins
        indicateurs.insert(0, _INDICATEUR_Q2[valeurs["democratie_directe"]])
    q.update(feasibility=valeurs["feasibility"], rights_status=valeurs["rights_status"],
             rights_income=None if portee is None else round(100 * portee),
             precision=valeurs["precision"], revision=None, relecture_ciblee=None, indicateurs=indicateurs or None)
    for k, deps in REPONSES_PAR_AXE_Q2.items():
        valeur = q["axes"].get(k) if k in AXES_Q2 else q.get(k)
        q["score_details"][k] = {"status": "scored" if valeur is not None else "not_applicable", "method": "questionnaire-q2",
                                 "model": a.get("modele"),
                                 "confidence": min((conf[d] for d in deps if conf.get(d) is not None), default=None),
                                 "rationale": explications.get(k), "corrigee": sorted(set(deps) & set(corrections)) or None}
    return q


def calculer(base: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    par = decisions_par_mesure(decisions)
    out = {}
    for m in base["mesures"]:
        p, etat = vue(m, par.get(m["uid"], []))
        if etat["rejetee"]:
            m["statut"] = "rejetee"
        elif etat["fusion"]:
            m["statut"], m["remplacee_par"] = "remplacee", etat["fusion"]
        elif m["statut"] in ("rejetee", "remplacee"):  # decision liee a une ancienne version : la mesure revient
            m["statut"] = "active"
            m.pop("remplacee_par", None)
        details = p.get("score_details") or {}
        explications = {k: (details.get(k) or {}).get("rationale") for k in EXPLIQUES
                        if (details.get(k) or {}).get("method") in METHODES_QUESTIONNAIRE and (details.get(k) or {}).get("rationale")}
        m["calculs"] = {"axes": {k: dimension_value(p, k) for k in AXES_SUIVIS}, "ideologie": p.get("ideology"),
                        "importance": p.get("importance"), "explications": explications,
                        "explication_eco": explications.get("eco")}
        out[m["uid"]] = (p, etat)
    return out


def divergences_ouvertes(a: dict[str, Any], corrections: dict[str, Any]) -> list[str]:
    """q2 : reponses sur lesquelles les trois lecteurs different (« revenus » : le bloc des classes de revenu, ou les
    revenus tranches par l'arbitre seul), pas encore corrigees a la main."""
    out = []
    for k in a.get("divergences") or []:
        corrige = bool(set(Q.CLASSES_REVENU) & set(corrections)) if k == "revenus" else k in corrections
        if not corrige:
            out.append(k)
    return out


# --- File de validation ------------------------------------------------------------------------------------------

def construire_file(base: dict[str, Any], vues: dict[str, tuple[dict[str, Any], dict[str, Any]]],
                    precedent: dict[str, dict[str, Any]], date: str | None = None,
                    changement_methode: bool = False) -> Counter:
    """Motifs par mesure ; un motif garde sa date d'apparition et disparait avec une validation posterieure.

    changement_methode : run de renotation voulue (nouvelle methode, nouveau questionnaire) ; les deplacements qui en
    resultent ne sont pas des changements de programme et ne sont pas signales (ceux deja en file sont retires).
    """
    date = date or maintenant()
    compte: Counter = Counter()
    for m in base["mesures"]:
        p, etat = vues[m["uid"]]
        anciens = {f["motif"]: f["depuis"] for f in m.get("file") or []}
        motifs = set()
        if m["statut"] in ("rejetee", "remplacee"):
            m["file"] = []
            continue
        if m["statut"] == "non_reprise":
            motifs.add("non_reprise")
        if etat["a_revoir"]:
            motifs.add("decision_a_revoir")
        if m.get("nouvelle"):
            motifs.add("nouvelle_mesure")
        if len(m["versions"]) > 1 and m["versions"][-1].get("nature", "texte") in ("texte", "modifiee"):
            motifs.add("mesure_modifiee")  # une version « precisee » ne change pas l'engagement : pas de relecture
        if (m.get("rapprochement") or {}).get("etat") == "incertain":
            motifs.add("rapprochement_incertain")
        a = m.get("annotation")
        q2 = (a or {}).get("version") == Q2.VERSION
        # q2 : une question fermee par sa condition (null) n'est pas un doute de sens
        sans_doute = (Q.INDETERMINE, None) if q2 else (Q.INDETERMINE,)
        if a and any((c or 0) < SEUIL_CONFIANCE for q, c in (a.get("confiances") or {}).items()
                     if q in (Q2.QUESTIONS_SENS if q2 else Q.QUESTIONS_SENS) and q not in etat["corrections"]  # le sens seulement
                     and a["reponses"].get(q) not in sans_doute):  # « indetermine » : reponse explicite, pas un doute
            motifs.add("confiance_basse")
        if a and q2 and divergences_ouvertes(a, etat["corrections"]):
            motifs.add("divergence_lectures")
        if (p.get("revision") or {}).get("human_review_required"):
            motifs.add("divergence_lectures")
        avant = (precedent.get(m["uid"]) or {}).get("v") or {}
        for k in AXES_SUIVIS if not changement_methode else ():
            x, y = avant.get(k), (m["calculs"]["axes"] or {}).get(k)
            if m["uid"] in precedent and (x is None) != (y is None):
                motifs.add("axe_perdu_ou_gagne")
            elif x is not None and y is not None and abs(x - y) > SEUIL_DEPLACEMENT:
                motifs.add("deplacement_fort")
        if "deplacement_fort" in anciens and not changement_methode:  # transitoire : garde jusqu'a validation
            motifs.add("deplacement_fort")
        file = []
        for motif in sorted(motifs, key=lambda x: (PRIORITES[x], x)):
            depuis = anciens.get(motif, date)
            permanent = motif in ("non_reprise", "decision_a_revoir")
            if not permanent and etat["validee_le"] and etat["validee_le"] >= depuis:
                continue
            file.append({"motif": motif, "priorite": PRIORITES[motif], "depuis": depuis})
            compte[motif] += 1
        m["file"] = file
    return compte


# --- Export ---------------------------------------------------------------------------------------------------------

def lien_public(url: Any) -> str | None:
    """Seuls les liens http(s) sont publies : un document depose a une adresse locale (file://) qui n'a pas a sortir."""
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None


def recap_sources(base: dict[str, Any], publiees: set[str], manifeste: dict[str, Any] | None,
                  ajouts: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Documents du corpus avec, par candidat, le nombre de propositions qui en sont tirees, et sources en attente.

    `ext` : mesures de la base qui citent le document (hors rejetees et remplacees) ; `n` : celles publiees dans
    l'export. Une proposition reprise dans plusieurs documents compte pour chacun.
    """
    ext: Counter = Counter()
    pub: Counter = Counter()
    for m in base["mesures"]:
        if m["statut"] in ("rejetee", "remplacee"):
            continue
        for doc in {s.get("document_id") for s in m["versions"][-1]["sources"]} - {None}:
            ext[(doc, m["candidate_id"])] += 1
            if m["uid"] in publiees:
                pub[(doc, m["candidate_id"])] += 1
    docs = []
    for d in ((manifeste or {}).get("documents") or {}).values():
        liaisons = d.get("bindings") or [{}]
        principale = next((b for b in liaisons if b.get("role") == "programme"), liaisons[0])
        candidats = dict.fromkeys([b.get("candidate_id") for b in liaisons] + [c for (i, c) in ext if i == d["id"]])
        for cand in [c for c in candidats if c] or [None]:
            b = principale if principale.get("candidate_id") == cand else \
                next((x for x in liaisons if x.get("candidate_id") == cand), principale)
            docs.append({"id": d["id"], "c": cand, "titre": b.get("title"),
                         "url": lien_public(d.get("url")), "type": b.get("role"), "date": b.get("published_date"),
                         "format": d.get("format"), "statut": d.get("status"), "depot": not lien_public(d.get("url")),
                         "n": pub.get((d["id"], cand), 0), "ext": ext.get((d["id"], cand), 0)})
    docs.sort(key=lambda x: (x["c"] or "", -(x["ext"]), x["date"] or ""))
    attente = [{"c": a.get("candidate_id"), "titre": a.get("titre"), "url": lien_public(a.get("url")), "type": a.get("type"),
                "date": a.get("date"), "ajoutee_le": (a.get("ajoutee_le") or "")[:10] or None}
               for a in ajouts or [] if a.get("statut") == "en_attente"]
    return docs, attente


LONGUEUR_RAISON = 400  # raison de l'arbitre publiee dans la fiche (export : quelques Mo de plus au plus)


def resume_lecture(a: dict[str, Any] | None, motifs: set[str], etat: dict[str, Any]) -> dict[str, Any]:
    """Comment la mesure a ete lue, pour la fiche de la constellation (champ `lec` de l'export) : `m` modeles lecteurs
    (sans l'arbitre), `arb` arbitre, `vote` 1 si l'arbitre a relu toute la mesure et que chaque reponse est celle d'au
    moins deux des trois lecteurs (methode v5 ; sinon il n'a tranche que les litiges), `lit` blocs ou questions sur
    lesquels les deux lecteurs ont repondu differemment, `sig` questions signalees (v5 : trois avis differents ; ensuite :
    arbitrage peu sur ou reponse nouvelle), `raison` note de l'arbitre (v5) ou raison de son choix,
    `rel` motifs du badge « non relue », `val` date de validation humaine de la version publiee."""
    out: dict[str, Any] = {}
    if a and a.get("version") in (Q.VERSION, Q2.VERSION):
        lecteurs = [x.split("/")[-1] for x in a.get("lecteurs") or []] or [a.get("modele")]
        if a.get("arbitrage") and len(lecteurs) > 2:
            out["arb"] = lecteurs.pop()
            if str(a.get("methode") or "").startswith("essai-q2-v5"):
                out["vote"] = 1  # ancien arbitre : troisieme lecture complete, chaque reponse a la majorite des trois
        out["m"] = [x for x in lecteurs if x]
        for cle, champ in (("lit", "arbitrage"), ("sig", "divergences")):
            if a.get(champ):
                out[cle] = list(a[champ])
        if out.get("arb") and a.get("note"):
            note = a["note"]
            out["raison"] = note if len(note) <= LONGUEUR_RAISON else note[:LONGUEUR_RAISON - 1].rstrip() + "…"
    if motifs & NON_RELUE:
        out["rel"] = sorted(motifs & NON_RELUE)
    if etat.get("validee_le"):
        out["val"] = etat["validee_le"][:10]
    return out


def exporter(base: dict[str, Any], vues: dict[str, tuple[dict[str, Any], dict[str, Any]]],
             precedent: dict[str, dict[str, Any]], votes: dict[str, list[dict[str, Any]]] | None = None,
             manifeste: dict[str, Any] | None = None, ajouts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """`votes` : liens vote-mesure a jour par uid (votes_2027.Donnees.pour_export), joints a chaque ligne publiee.
    `manifeste` (corpus_programmes/manifest.json) et `ajouts` (sources_2027.json) : recapitulatif des sources publie."""
    rows = []
    for m in base["mesures"]:
        if m["statut"] in ("rejetee", "remplacee"):
            continue
        p, etat = vues[m["uid"]]
        motifs = {f["motif"] for f in m.get("file") or []}
        if motifs & BLOQUANTS and m["uid"] in precedent:
            row = dict(precedent[m["uid"]])  # version publiee precedente, jusqu'a validation
            row["badge"] = "en_revision"
        elif "rapprochement_incertain" in motifs:
            continue  # doublon possible d'une mesure existante : publiee seulement apres validation
        else:
            affichage = m["affichage"]
            if (m.get("annotation") or {}).get("version") in (Q.VERSION, Q2.VERSION):  # precision issue du questionnaire
                affichage = {**affichage, "precision": p.get("precision")}
            row = ei.compact(p, affichage)
            row["id"] = m["uid"]
            lec = resume_lecture(m.get("annotation"), motifs, etat)
            if lec:
                row["lec"] = lec
            if motifs & NON_RELUE:
                row["badge"] = "non_relue"
            if m["statut"] == "non_reprise":
                row["badge"] = "non_reprise"
            if m["calculs"].get("explications"):
                row["expl"] = m["calculs"]["explications"]
        row["maj"] = m["versions"][-1]["date"][:10]
        row["url"] = lien_public(row.get("url"))
        row.pop("votes", None)  # toujours les liens du moment, jamais ceux d'un export precedent
        if votes and votes.get(m["uid"]):
            row["votes"] = votes[m["uid"]]
        rows.append(row)
    shell = ei.export({**base, "proposals": []}, None)
    shell["meta"].update(base=VERSION_BASE, genere_le=maintenant(), proposals=len(rows),
                         note="Valeurs inconnues = null (jamais 0). Badge non_relue : mesure publiee avant relecture.")
    shell["proposals"] = rows
    notation = Counter((m.get("annotation") or {}).get("modele") for m in base["mesures"] if m["statut"] not in ("rejetee", "remplacee"))
    shell["meta"]["modeles"] = {"notation": {k: v for k, v in notation.items() if k}}  # page « Méthode » de la constellation
    # questionnaire des mesures publiees (q1, q2) : la constellation n'affiche les nouveautes de q2 que s'il y en a
    publiees = {r["id"] for r in rows}
    versions = Counter((m.get("annotation") or {}).get("version") for m in base["mesures"] if m["uid"] in publiees)
    shell["meta"]["questionnaires"] = {k: v for k, v in versions.items() if k}
    # lecteurs et arbitre les plus frequents : ecrits une fois dans meta.lecture ; une ligne qui les a porte 1 (taille)
    for cle in ("m", "arb"):
        freq = Counter(json.dumps(r["lec"][cle]) for r in rows if cle in (r.get("lec") or {}))
        if freq:
            commun = freq.most_common(1)[0][0]
            shell["meta"].setdefault("lecture", {})[cle] = json.loads(commun)
            for r in rows:
                if cle in (r.get("lec") or {}) and json.dumps(r["lec"][cle]) == commun:
                    r["lec"][cle] = 1
    # page « Coulisses » de la constellation : questionnaire q2 complet (annexe, et libelles des questions qui ont divise
    # les lecteurs dans la fiche), constantes des formules, et redactions (methodes) des lectures publiees
    shell["meta"]["questionnaire_q2"] = {"conditions": Q2.CONDITIONS, "questions": Q2.QUESTIONS}
    shell["meta"]["formules_q2"] = {"forces": Q2.FORCES, "poids_eco": Q2.POIDS_ECO, "poids_soc": Q2.POIDS_SOC,
                                    "degre_ampleur": Q2.DEGRE_AMPLEUR, "degre_force": Q2.DEGRE_FORCE,
                                    "declaration": Q2.DECLARATION, "portee": Q2.PORTEE, "axes_portee": list(Q2.AXES_PORTEE),
                                    "ampleur_min": Q2.D.AMPLEUR_MIN, "base_faisabilite": Q2.BASE_FAISABILITE,
                                    "motifs_arbitrage": Q2.MOTIFS_ARBITRAGE}
    methodes = Counter((m.get("annotation") or {}).get("methode") for m in base["mesures"] if m["uid"] in publiees)
    shell["meta"]["methodes"] = {k: v for k, v in methodes.items() if k}
    if manifeste is not None:
        shell["sources"], shell["sources_en_attente"] = recap_sources(base, {r["id"] for r in rows}, manifeste, ajouts)
        extraction = Counter((d.get("extraction") or {}).get("model") for d in (manifeste.get("documents") or {}).values())
        shell["meta"]["modeles"]["extraction"] = {k: v for k, v in extraction.items() if k}
    return shell


def nouveautes(precedent: dict[str, dict[str, Any]], export: dict[str, Any], date: str | None = None) -> dict[str, Any]:
    actuel = {r["id"]: r for r in export["proposals"]}
    ajoutees = [i for i in actuel if i not in precedent]
    retirees = [i for i in precedent if i not in actuel]
    modifiees = [i for i in actuel if i in precedent and (actuel[i].get("title"), actuel[i].get("desc"))
                 != (precedent[i].get("title"), precedent[i].get("desc"))]
    deplacees = []
    for i in actuel:
        if i in precedent:
            for k in AXES_SUIVIS:
                x, y = (precedent[i].get("v") or {}).get(k), (actuel[i].get("v") or {}).get(k)
                if x is not None and y is not None and abs(x - y) > SEUIL_NOUVEAUTE:
                    deplacees.append({"id": i, "axe": k, "avant": x, "apres": y})

    def etoiles(rows):
        groupes: dict[tuple[str, str, str], list[int]] = {}
        for r in rows.values():
            for k in AXES_SUIVIS:
                v = (r.get("v") or {}).get(k)
                if v is not None:
                    groupes.setdefault((r["c"], r["t"], k), []).append(v)
        return {g: statistics.mean(v) for g, v in groupes.items()}
    e0, e1 = etoiles(precedent), etoiles(actuel)
    etoiles_deplacees = [{"candidat": c, "theme": t, "axe": k, "avant": round(e0[(c, t, k)]), "apres": round(v)}
                         for (c, t, k), v in e1.items() if (c, t, k) in e0 and abs(v - e0[(c, t, k)]) > SEUIL_NOUVEAUTE]
    return {"date": date or maintenant(), "ajoutees": ajoutees, "retirees": retirees, "modifiees": modifiees,
            "mesures_deplacees": deplacees, "etoiles_deplacees": etoiles_deplacees}


# --- Bilan ------------------------------------------------------------------------------------------------------------

def bilan(base: dict[str, Any], file: Counter, nouv: dict[str, Any] | None, etapes: list[str], cout: float,
          rapport_migration: dict[str, int] | None = None) -> tuple[dict[str, Any], str]:
    statuts = Counter(m["statut"] for m in base["mesures"])
    data = {"date": maintenant(), "etapes": etapes, "cout": cout, "mesures": dict(statuts), "file": dict(file),
            "migration": rapport_migration,
            "nouveautes": {k: len(v) for k, v in (nouv or {}).items() if isinstance(v, list)}}
    lignes = [f"# Bilan du run {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
              f"- Étapes : {', '.join(etapes)}", f"- Coût : {cout:.3f} $",
              "- Mesures : " + ", ".join(f"{k} {v}" for k, v in statuts.most_common()),
              "- File de validation : " + (", ".join(f"{k} {v}" for k, v in file.most_common()) or "vide")]
    if rapport_migration:
        lignes.append("- Migration : " + ", ".join(f"{k} {v}" for k, v in rapport_migration.items()))
    if nouv:
        lignes.append("- Nouveautés : " + ", ".join(f"{k} {len(v)}" for k, v in nouv.items() if isinstance(v, list)))
    return data, "\n".join(lignes) + "\n"
