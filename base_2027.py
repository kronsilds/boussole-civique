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
        if a.get("version") != Q.VERSION:
            raise ValueError(f"Annotation {a.get('version')} : relancer l'annotation {Q.VERSION} avant de corriger.")
        if champ not in Q.TOUTES:
            raise ValueError(f"Champ corrigeable : {', '.join(Q.TOUTES)}")
        if valeur not in Q.TOUTES[champ]["criteria"] and not (valeur is None and champ in Q.CONDITIONNELLES) \
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
        p["ideology"] = Q.ideologie({**(p.get("axes") or {}), "rights_status": p.get("rights_status")})  # comme la constellation
        update_importance(p)
        return p, etat
    # Mesure pas encore annotee (q1) : notes de la proposition d'origine, en attendant l'annotation.
    p["importance_sources"] = {**(p.get("importance_sources") or {}),
                               "programme": importance_structurelle(p, m["affichage"].get("precision"))}
    ps.derive_fields(p)
    update_importance(p)
    return p, etat


AXES_Q1 = ("eco", "soc", "sov", "ouverture", "ecolo", "income_direction", "rupture", "legal_instrument", "cost_estimate")
REPONSES_PAR_AXE = {"eco": ("eco_etat", "eco_distrib", "levier", "portee"), "soc": ("soc_autorite", "soc_libertes", "soc_finalite", "levier", "portee"),
                    "sov": ("sov_niveau", "levier", "portee"), "ouverture": ("ouv_sens", "levier", "portee"),
                    "ecolo": ("env_sens", "levier", "portee"), "income_direction": ("revenus_sens",), "rupture": ("changement",),
                    "legal_instrument": ("instrument",), "cost_estimate": ("cout",), "feasibility": ("faisabilite",),
                    "rights_status": ("droits_statut",)}


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
    q.update(feasibility=valeurs["feasibility"], rights_status=valeurs["rights_status"], rights_income=None,
             precision=valeurs["precision"], revision=None, relecture_ciblee=None)
    for k, deps in REPONSES_PAR_AXE.items():
        valeur = q["axes"].get(k) if k in AXES_Q1 else q.get(k)
        q["score_details"][k] = {"status": "scored" if valeur is not None else "not_applicable", "method": "questionnaire-q1",
                                 "model": a.get("modele"),
                                 "confidence": min((conf[d] for d in deps if d in conf), default=None),
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
        explications = {k: (details.get(k) or {}).get("rationale") for k in AXES_SUIVIS
                        if (details.get(k) or {}).get("method") == "questionnaire-q1" and (details.get(k) or {}).get("rationale")}
        m["calculs"] = {"axes": {k: dimension_value(p, k) for k in AXES_SUIVIS}, "ideologie": p.get("ideology"),
                        "importance": p.get("importance"), "explications": explications,
                        "explication_eco": explications.get("eco")}
        out[m["uid"]] = (p, etat)
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
        if a and any((c or 0) < SEUIL_CONFIANCE for q, c in (a.get("confiances") or {}).items()
                     if q in Q.QUESTIONS_SENS and q not in etat["corrections"]  # le sens seulement, pas l'ampleur
                     and a["reponses"].get(q) != Q.INDETERMINE):  # « indetermine » : reponse explicite, pas un doute
            motifs.add("confiance_basse")
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

def exporter(base: dict[str, Any], vues: dict[str, tuple[dict[str, Any], dict[str, Any]]],
             precedent: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
            if (m.get("annotation") or {}).get("version") == Q.VERSION:  # precision issue du questionnaire
                affichage = {**affichage, "precision": p.get("precision")}
            row = ei.compact(p, affichage)
            row["id"] = m["uid"]
            if motifs & NON_RELUE:
                row["badge"] = "non_relue"
            if m["statut"] == "non_reprise":
                row["badge"] = "non_reprise"
            if m["calculs"].get("explications"):
                row["expl"] = m["calculs"]["explications"]
        row["maj"] = m["versions"][-1]["date"][:10]
        rows.append(row)
    shell = ei.export({**base, "proposals": []}, None)
    shell["meta"].update(base=VERSION_BASE, genere_le=maintenant(), proposals=len(rows),
                         note="Valeurs inconnues = null (jamais 0). Badge non_relue : mesure publiee avant relecture.")
    shell["proposals"] = rows
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
