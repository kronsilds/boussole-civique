"""Questionnaire unifie q1 et calcul de toutes les notes (spec_descripteurs_2027.md section 11, spec pipeline 5.4).

Une seule lecture a l'aveugle par mesure, uniquement des questions a choix :
- communes : levier, public_vise, portee, changement, precision, instrument, cout, faisabilite ;
- de sens, posees seulement si l'axe s'applique (sinon null) : economie (eco_etat, eco_distrib), societe
  (soc_autorite, soc_libertes), souverainete (sov_niveau), immigration (ouv_sens), environnement (env_sens), acces aux
  droits selon le statut (droits_statut), effet sur les revenus (revenus_sens).
Les notes sont calculees : axe = 100 x sens x force du levier (propre a l'axe) x ampleur, comme l'axe economique
(descripteurs_2027). Aucune note numerique n'est demandee au modele. Horizon retire (decision du 2026-11-06).
"""
from __future__ import annotations

from typing import Any

import descripteurs_2027 as D
import pipeline_scoring_2027 as ps

VERSION = "q1"

ps_q = ps.TYPESAFE_QUESTIONS


def _criteres(question: str) -> dict[str, str]:
    crit = ps_q[question]["criteria"]
    return dict(crit) if isinstance(crit, dict) else {}


QUESTIONS: dict[str, dict[str, Any]] = {
    # --- communes ---------------------------------------------------------------------------------------------------
    "levier": {**D.QUESTIONS["levier"], "libelle": "Levier"},
    "public_vise": {**D.QUESTIONS["public_vise"], "libelle": "Public visé"},
    "portee": {**D.QUESTIONS["portee"], "libelle": "Portée"},
    "changement": {"libelle": "Ampleur du changement", "instructions":
                   "Quelle est l'ampleur du changement que la mesure vise par rapport au droit et aux pratiques existants, "
                   "meme si les moyens ne sont pas precises ?",
                   "criteria": {"statu_quo_ou_ajustement": "Statu quo, ajustement d'un paramètre ou prolongation d'un dispositif",
                                "extension_moderee": "Extension ou modification modérée d'un dispositif existant",
                                "reforme_significative": "Réforme significative d'un dispositif ou d'une politique publique",
                                "refonte_structurelle": "Refonte structurelle, abrogation, création d'une institution ou d'un système"}},
    "precision": {"libelle": "Précision", "instructions": "Quel est le degré de précision de l'engagement ?",
                  "criteria": {"chiffre": "Chiffré : montant, nombre, taux, date ou seuil explicite",
                               "precis": "Précis : dispositif identifiable sans chiffre",
                               "orientation_generale": "Orientation générale : intention sans dispositif identifiable"}},
    "instrument": {"libelle": "Instrument juridique", "instructions": ps_q["legal_instrument"]["instructions"],
                   "criteria": _criteres("legal_instrument")},
    "cout": {"libelle": "Ordre de grandeur budgétaire", "instructions": ps_q["cost_estimate"]["instructions"],
             "criteria": _criteres("cost_estimate")},
    "faisabilite": {"libelle": "Faisabilité", "instructions":
                    "Quel est le degré de faisabilité juridique, constitutionnelle et budgétaire de la mesure ?",
                    "criteria": {"obstacle_majeur": "Obstacle majeur : révision constitutionnelle lourde, rupture des traités ou financement massif sans mécanisme crédible",
                                 "faible": "Faible : risque élevé de censure, conflit avec le droit européen ou coût majeur non financé",
                                 "moyenne": "Moyenne : loi ordinaire ou de finances d'ampleur, arbitrage budgétaire ou négociation complexe",
                                 "elevee": "Élevée : mesure législative ou budgétaire classique, compatible avec la Constitution et l'Europe",
                                 "immediate": "Immédiate : décret, circulaire ou ajustement directement applicable par l'exécutif",
                                 "non_evaluable": "Texte trop vague pour juger"}},
    # --- sens, si l'axe s'applique --------------------------------------------------------------------------------------
    "eco_etat": {**D.QUESTIONS["eco_etat"], "libelle": "Action publique", "condition": "has_eco"},
    "eco_distrib": {**D.QUESTIONS["eco_distrib"], "libelle": "Redistribution", "condition": "has_eco"},
    "soc_autorite": {"libelle": "Autorité", "condition": "has_soc", "instructions":
                     "La mesure renforce-t-elle ou allège-t-elle le contrôle, la surveillance, la sanction ou les normes "
                     "imposées aux personnes par l'État ?",
                     "criteria": {"renforce": "Plus de contrôle, de surveillance, de sanction ou de normes imposées",
                                  "inchange": "Ni l'un ni l'autre, ou effets qui se compensent",
                                  "allege": "Moins de contrôle, de surveillance, de sanction ou de normes imposées"}},
    "soc_libertes": {"libelle": "Libertés", "condition": "has_soc", "instructions":
                     "La mesure étend-elle ou restreint-elle des libertés et droits individuels (y compris ceux des minorités) ?",
                     "criteria": {"etend": "Étend des libertés ou des droits individuels",
                                  "inchange": "Sans effet sur les libertés et droits individuels",
                                  "restreint": "Restreint des libertés ou des droits individuels"}},
    "sov_niveau": {"libelle": "Niveau de décision", "condition": "has_sov", "instructions":
                   "Vers quel niveau la mesure déplace-t-elle la décision ?",
                   "criteria": {"vers_europe_international": "Vers l'Union européenne ou l'international : compétences partagées, intégration, ouverture commerciale",
                                "equilibre": "Équilibre entre décision nationale et coopération",
                                "vers_national": "Vers le national : reprise de compétences, dérogation ou refus de règles européennes ou d'accords"}},
    "ouv_sens": {"libelle": "Accueil des étrangers", "condition": "has_ouverture", "instructions":
                 "La mesure facilite-t-elle ou restreint-elle l'entrée, le séjour, l'asile ou la naturalisation des étrangers ?",
                 "criteria": {"accueil": "Facilite l'entrée, le séjour, l'asile, la régularisation ou la naturalisation",
                              "inchange": "Ajustement technique ou effets qui se compensent",
                              "fermeture": "Restreint l'entrée, le séjour, l'asile ou la naturalisation, facilite les expulsions"}},
    "env_sens": {"libelle": "Environnement", "condition": "has_ecolo", "instructions":
                 "La mesure renforce-t-elle ou allège-t-elle la protection de l'environnement, du climat ou de la biodiversité ?",
                 "criteria": {"protege": "Renforce la protection (normes, investissements, incitations, interdictions)",
                              "neutre": "Effet neutre ou équilibré",
                              "allege": "Allège ou reporte des contraintes environnementales, ou favorise les énergies fossiles"}},
    "droits_statut": {"libelle": "Accès aux droits selon le statut", "condition": "has_rights_status",
                      "instructions": ps_q["rights_status"]["instructions"],
                      "criteria": {"reserve_nationaux": "Droits réservés aux nationaux (préférence nationale)",
                                   "conditionne": "Droits conditionnés plus strictement (séjour, ancienneté, contreparties)",
                                   "inchange": "Conditions inchangées ou ajustement technique",
                                   "etendu": "Droits étendus à des personnes jusqu'ici exclues",
                                   "universel": "Droits universels pour toute personne résidente"}},
    "revenus_sens": {"libelle": "Effet sur les revenus", "condition": "has_rights_income",
                     "instructions": ps_q["income_direction"]["instructions"],
                     "criteria": {"baisse_forte": "Baisse forte des revenus ou suppression d'un droit ou d'une prestation",
                                  "baisse_moderee": "Baisse modérée, condition plus stricte ou contribution supplémentaire",
                                  "neutre": "Effet neutre, mixte ou compensé",
                                  "hausse_moderee": "Hausse modérée d'un revenu, d'une prestation ou d'un accès",
                                  "hausse_forte": "Hausse forte de revenus ou nouveau droit financier"}},
}
# Complements : questions ajoutees apres coup, posees a part aux mesures deja annotees (et a la suite du questionnaire
# principal pour les nouvelles). Hors de QUESTIONS pour ne pas changer la cle de cache des lectures deja payees.
COMPLEMENTS: dict[str, dict[str, Any]] = {
    "soc_finalite": {"libelle": "Finalité (société)", "condition": "has_soc", "instructions":
                     "Au nom de quoi la mesure agit-elle sur les libertés ou l'ordre ? Choisis l'objet principal de la mesure, "
                     "pas la façon dont elle est présentée.",
                     "criteria": {"droits_egalite": "Faire respecter l'égalité et les droits fondamentaux : lutte contre les discriminations, "
                                                    "le racisme, le sexisme, l'homophobie, droits des minorités, accès aux droits "
                                                    "(une sanction de ces atteintes compte ici)",
                                  "ordre_securite": "Ordre public, sécurité, répression de la délinquance, autorité, normes morales, "
                                                    "identitaires ou religieuses (y compris l'alourdissement des peines au nom des victimes)",
                                  "probite_pouvoirs": "Contrôler les élus, l'administration, la justice ou les entreprises : probité, "
                                                      "transparence, corruption, conflits d'intérêts, lobbying",
                                  "autre": "Autre finalité (mœurs, vie privée, fin de vie, laïcité, expression…)"}},
}
COMPLEMENTS["degre_rupture"] = {
    "libelle": "Degré de rupture (société, immigration)",
    "instructions": "Quel est le degré de rupture de la mesure avec le cadre juridique et les principes actuels, sur les "
                    "libertés, l'ordre ou l'accueil des étrangers ? Juge ce que la mesure vise, même seulement annoncé.",
    "criteria": {"ajustement": "Ajustement, précision ou meilleure application d'une règle existante",
                 "notable": "Durcissement ou assouplissement notable, dans le cadre juridique et les principes existants",
                 "rupture": "Rupture du cadre : abolition, création ou renversement d'un principe établi (droit du sol, peine de "
                            "mort, dépénalisation, arrêt de l'immigration, régularisation générale, préférence nationale, "
                            "sortie d'une convention internationale)"}}
TOUTES = {**QUESTIONS, **COMPLEMENTS}
CONDITIONNELLES = tuple(k for k, q in TOUTES.items() if q.get("condition"))

# Force du levier par axe (0..1). L'economie reprend descripteurs_2027.LEVIER_ECO ; une declaration prend sa force de
# l'ampleur du changement vise (de 0,15 a 0,85), sur tous les axes.
_L = ("declaration_ou_symbole", "information_ou_evaluation", "organisation_institutionnelle", "incitation",
      "depense_ou_service", "prelevement", "obligation_ou_interdiction", "controle_prix_ou_revenus",
      "sanction_ou_controle", "suppression_ou_allegement", "propriete_publique", "transfert_au_prive")


def _forces(*valeurs: float) -> dict[str, float]:
    return dict(zip(_L, valeurs))


FORCES = {
    "eco": D.LEVIER_ECO,
    "soc": _forces(.15, .15, .5, .3, .4, .3, .75, .3, .8, .6, .3, .3),
    "sov": _forces(.15, .15, .8, .3, .4, .5, .6, .5, .4, .6, .6, .5),
    "ouverture": _forces(.15, .15, .7, .4, .4, .4, .75, .3, .8, .65, .3, .3),
    "ecolo": _forces(.15, .15, .4, .5, .6, .7, .85, .5, .6, .7, .6, .4),
}
CHANGEMENT = {"statu_quo_ou_ajustement": 0, "extension_moderee": 33, "reforme_significative": 67, "refonte_structurelle": 100}
FAISABILITE = {"obstacle_majeur": 0, "faible": 25, "moyenne": 50, "elevee": 75, "immediate": 100, "non_evaluable": None}
DROITS = {"reserve_nationaux": 0, "conditionne": 25, "inchange": 50, "etendu": 75, "universel": 100}
REVENUS = {"baisse_forte": -100, "baisse_moderee": -50, "neutre": 0, "hausse_moderee": 50, "hausse_forte": 100}
# Questions qui fixent le sens d'une position (gauche/droite, ordre/libertes, etc.) : une reponse peu sure peut
# inverser la mesure sur son axe. Les autres (cout, changement, public, instrument...) ne changent que l'ampleur.
QUESTIONS_SENS = ("eco_etat", "eco_distrib", "soc_autorite", "soc_libertes", "soc_finalite", "sov_niveau", "ouv_sens",
                  "env_sens", "droits_statut", "revenus_sens")
# Reponse possible aux questions de sens apres la relecture contextuelle (contexte_2027.py), hors QUESTIONS pour garder
# la cle de cache des lectures q1 : la direction elle-meme manque ou se contredit.
INDETERMINE = "indetermine"
LIBELLE_INDETERMINE = ("La direction elle-meme manque ou se contredit (pas seulement les moyens), dans la proposition "
                       "comme dans le passage.")
NEUTRES = {"eco_etat": "inchange_ou_mixte", "eco_distrib": "neutre", "soc_autorite": "inchange", "soc_libertes": "inchange"}
PAIRES_SENS = (("eco_etat", "eco_distrib"), ("soc_autorite", "soc_libertes"))


def normaliser(r: dict[str, Any]) -> dict[str, Any]:
    """« indetermine » -> valeurs de calcul : neutre dans une paire (eco, societe) dont l'autre question est tranchee ;
    sinon l'axe n'est pas calcule (null), comme une mesure dont l'axe ne s'applique pas."""
    if INDETERMINE not in r.values():
        return r
    r = dict(r)
    for paire in PAIRES_SENS:
        if all(r.get(k) == INDETERMINE for k in paire):
            r.update({k: None for k in paire})
        else:
            r.update({k: NEUTRES[k] for k in paire if r.get(k) == INDETERMINE})
    return {k: (None if v == INDETERMINE else v) for k, v in r.items()}

SENS = {  # signe des axes : eco -100 gauche ; soc -100 libertes ; sov -100 supranational ; ouverture -100 accueil ;
          # ecolo -100 production contre environnement (+100 transition contraignante)
    "soc_autorite": {"renforce": 1, "inchange": 0, "allege": -1},
    "soc_libertes": {"restreint": 1, "inchange": 0, "etend": -1},
    "sov_niveau": {"vers_europe_international": -1, "equilibre": 0, "vers_national": 1},
    "ouv_sens": {"accueil": -1, "inchange": 0, "fermeture": 1},
    "env_sens": {"allege": -1, "neutre": 0, "protege": 1},
}
MOTS = {
    "soc_finalite": {"droits_egalite": "au nom de l'égalité et des droits", "ordre_securite": "au nom de l'ordre",
                     "probite_pouvoirs": "contrôle des pouvoirs", "autre": "autre finalité"},
    "soc_autorite": {"renforce": "plus d'autorité", "inchange": "autorité inchangée", "allege": "moins d'autorité"},
    "soc_libertes": {"etend": "libertés étendues", "inchange": "libertés inchangées", "restreint": "libertés restreintes"},
    "sov_niveau": {"vers_europe_international": "vers l'Europe", "equilibre": "équilibre", "vers_national": "vers le national"},
    "ouv_sens": {"accueil": "plus d'accueil", "inchange": "accueil inchangé", "fermeture": "plus de fermeture"},
    "env_sens": {"protege": "plus de protection", "neutre": "effet neutre", "allege": "moins de protection"},
}


def _changement(r: dict[str, Any]) -> float:
    return (CHANGEMENT.get(r.get("changement")) or 0) / 100


def _ampleur(r: dict[str, Any]) -> float:
    budget = D.BUDGET.get(r.get("cout"))
    chg = max(_changement(r), budget if budget is not None else 0)
    return D.AMPLEUR_MIN + (1 - D.AMPLEUR_MIN) * (D.PORTEE[r["portee"]] + chg) / 2


def _force(axe: str, r: dict[str, Any]) -> float:
    force = FORCES[axe][r["levier"]]
    if r["levier"] == "declaration_ou_symbole":
        force += (D.DECLARATION_MAX - force) * _changement(r)
    return force


# Degre de rupture (complement) pour les axes societe et immigration : il remplace la portee dans l'ampleur (une mesure
# migratoire vise par definition une categorie) et fixe une force minimale (une rupture pese au maximum, quel que soit le levier).
DEGRE_FORCE = {"ajustement": 0.0, "notable": .7, "rupture": 1.0}
DEGRE_AMPLEUR = {"ajustement": .2, "notable": .6, "rupture": 1.0}
AXES_DEGRE = ("soc", "ouverture")


def axe(axe_: str, sens: float, r: dict[str, Any]) -> int:
    degre = r.get("degre_rupture")
    if axe_ in AXES_DEGRE and degre in DEGRE_FORCE:
        force = max(_force(axe_, r), DEGRE_FORCE[degre])
        ampleur = D.AMPLEUR_MIN + (1 - D.AMPLEUR_MIN) * DEGRE_AMPLEUR[degre]
        return round(100 * max(-1.0, min(1.0, sens)) * force * ampleur)
    return round(100 * max(-1.0, min(1.0, sens)) * _force(axe_, r) * _ampleur(r))


def calculer(r: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Reponses -> valeurs de toutes les dimensions (format historique) et explications en mots."""
    r = normaliser(r)
    v: dict[str, Any] = {"rupture": CHANGEMENT.get(r.get("changement")), "legal_instrument": r.get("instrument"),
                         "cost_estimate": r.get("cout"), "feasibility": FAISABILITE.get(r.get("faisabilite")),
                         "precision": r.get("precision"), "rights_status": DROITS.get(r.get("droits_statut")),
                         "income_direction": REVENUS.get(r.get("revenus_sens"))}
    expl: dict[str, str] = {}
    base_mots = [D.MOTS["levier"][r["levier"]], D.MOTS["portee"][r["portee"]]]
    degre_mot = {"ajustement": "ajustement", "notable": "changement notable", "rupture": "rupture du cadre"}.get(r.get("degre_rupture"))
    if r.get("eco_etat") is not None and r.get("eco_distrib") is not None:
        val, det = D.eco_score({**r, "rupture": v["rupture"], "cost_estimate": r.get("cout")})
        v["eco"], expl["eco"] = val, det.get("explication")
    else:
        v["eco"] = None
    finalite = r.get("soc_finalite")
    # Complement repondu « null » : la lecture ciblee juge que l'axe ne s'applique pas (elle prime sur la premiere).
    hors_axe = finalite == "probite_pouvoirs" or ("soc_finalite" in r and finalite is None)
    if r.get("soc_autorite") is not None and r.get("soc_libertes") is not None and not hors_axe:
        a, lib = SENS["soc_autorite"][r["soc_autorite"]], SENS["soc_libertes"][r["soc_libertes"]]
        if finalite == "droits_egalite":  # faire respecter l'egalite : meme une sanction va du cote des libertes
            sens = -min(1.0, .6 * abs(a) + .6 * abs(lib))
        else:
            sens = .6 * a + .6 * lib
        v["soc"] = axe("soc", sens, r)
        expl["soc"] = " · ".join([*([MOTS["soc_finalite"][finalite]] if finalite in MOTS["soc_finalite"] else []),
                                  MOTS["soc_autorite"][r["soc_autorite"]], MOTS["soc_libertes"][r["soc_libertes"]], *base_mots,
                                  *([degre_mot] if degre_mot else [])])
    else:
        v["soc"] = None  # probite et controle des pouvoirs : pas une question de libertes contre l'ordre
    for axe_, q in (("sov", "sov_niveau"), ("ouverture", "ouv_sens"), ("ecolo", "env_sens")):
        if r.get(q) is not None:
            v[axe_] = axe(axe_, SENS[q][r[q]], r)
            expl[axe_] = " · ".join([MOTS[q][r[q]], *base_mots, *([degre_mot] if degre_mot and axe_ in AXES_DEGRE else [])])
        else:
            v[axe_] = None
    return v, expl


def etiquettes(r: dict[str, Any]) -> list[str]:
    """Etiquettes calculees (remplacent les etiquettes devinees par le modele)."""
    t = ps.TAGS
    out = []
    if r.get("instrument") in ps.LICORNE_INSTRUMENTS:
        out.append(t[0])
    if r.get("cout") == "cout_massif":
        out.append(t[1])
    if r.get("portee") == "individuelle":
        out.append(t[3])
    if r.get("levier") == "declaration_ou_symbole" or r.get("precision") == "orientation_generale":
        out.append(t[4])
    return out


# Ideologie d'une mesure (meme definition et memes poids par defaut que la constellation) : economie 1, societe 2
# (moyenne de libertes/ordre, immigration et acces aux droits signe), souverainete 0,5, ecologie 0,5 comptee a gauche.
POIDS_IDEOLOGIE = {"eco": 1.0, "culturel": 2.0, "sov": .5, "ecolo": .5}


def _moyenne(parts: list[tuple[Any, float]]) -> float | None:
    vals = [(v, w) for v, w in parts if v is not None and w > 0]
    return sum(v * w for v, w in vals) / sum(w for _, w in vals) if vals else None


def ideologie(v: dict[str, Any]) -> int | None:
    droits = None if v.get("rights_status") is None else (50 - v["rights_status"]) * 2
    culturel = _moyenne([(v.get("soc"), 1), (v.get("ouverture"), 1), (droits, 1)])
    w = POIDS_IDEOLOGIE
    x = _moyenne([(v.get("eco"), w["eco"]), (culturel, w["culturel"]), (v.get("sov"), w["sov"]),
                  (None if v.get("ecolo") is None else -v["ecolo"], w["ecolo"])])
    return None if x is None else round(x)
