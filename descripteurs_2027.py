"""Descripteurs factuels des propositions et calcul de l'axe economique (projet, voir spec_descripteurs_2027.md).

Les descripteurs sont des questions a choix, posees a l'aveugle pour toutes les propositions (levier, public vise,
portee) ou seulement quand l'axe s'applique (effet sur l'action publique, effet distributif). La note eco n'est plus
demandee au modele : elle est calculee par une formule publique a partir de ces reponses et de deux dimensions deja
notees (rupture, cost_estimate). Aucun appel reseau ici.
"""
from __future__ import annotations

from typing import Any

QUESTIONS: dict[str, dict[str, Any]] = {
    "levier": {
        "type": "choice", "scope": "toutes",
        "instructions": "Quel est le principal moyen d'action publique de la mesure dans `title` et `description` ? "
                        "Choisis celui qui porte l'essentiel de l'effet.",
        "criteria": {
            "declaration_ou_symbole": "Intention, objectif sans moyen précisé, reconnaissance, commémoration, appel",
            "information_ou_evaluation": "Rapport, audit, étude, transparence, consultation, débat, expérimentation",
            "organisation_institutionnelle": "Règles des institutions, élections, compétences, organisation administrative ou judiciaire",
            "incitation": "Crédit d'impôt, bonus-malus, subvention conditionnelle, label, prime à un comportement",
            "depense_ou_service": "Financement, investissement, recrutement, création ou extension d'un service ou d'une prestation (ou leur réduction)",
            "prelevement": "Création, hausse, baisse ou suppression d'un impôt, d'une taxe ou d'une cotisation",
            "obligation_ou_interdiction": "Norme, obligation, quota ou interdiction imposés à des personnes ou des acteurs privés",
            "controle_prix_ou_revenus": "Prix ou loyers plafonnés ou bloqués, salaire minimum, tarifs réglementés, encadrement des rémunérations",
            "sanction_ou_controle": "Contrôles, surveillance, sanctions pénales ou administratives, moyens de police ou de justice",
            "suppression_ou_allegement": "Suppression ou assouplissement d'une règle, d'une obligation, d'un organisme ; simplification",
            "propriete_publique": "Nationalisation, réquisition, expropriation, création d'une entreprise ou d'un pôle public",
            "transfert_au_prive": "Privatisation, ouverture à la concurrence, délégation au privé",
        },
    },
    "public_vise": {
        "type": "choice", "scope": "toutes",
        "instructions": "Quel public la mesure dans `title` et `description` vise-t-elle principalement, en bien ou en mal ?",
        "criteria": {
            "toute_la_population": "L'ensemble des habitants ou des citoyens",
            "menages_modestes": "Ménages modestes, précaires, bénéficiaires de minima",
            "classes_moyennes": "Classes moyennes, propriétaires occupants, ménages actifs",
            "menages_aises": "Hauts revenus, gros patrimoines, héritages importants",
            "jeunes_ou_etudiants": "Enfants, jeunes, étudiants",
            "retraites_ou_ages": "Retraités, personnes âgées, dépendance",
            "salaries": "Salariés, demandeurs d'emploi, travailleurs",
            "independants_pme_agriculteurs": "Indépendants, artisans, commerçants, PME, agriculteurs",
            "grandes_entreprises_ou_finance": "Grandes entreprises, multinationales, banques, actionnaires",
            "un_secteur": "Un secteur ou une profession déterminés (santé, énergie, culture, transport…)",
            "etrangers": "Étrangers, migrants, demandeurs d'asile",
            "auteurs_d_infractions": "Délinquants, détenus, auteurs d'infractions",
            "agents_ou_administrations": "Agents publics, administrations, collectivités",
            "elus_ou_institutions": "Élus, partis, institutions politiques",
            "etats_ou_union_europeenne": "États étrangers, Union européenne, organisations internationales",
            "aucun_identifiable": "Aucun public identifiable",
        },
    },
    "portee": {
        "type": "choice", "scope": "toutes",
        "instructions": "Quelle est l'étendue de la mesure dans `title` et `description` : combien de personnes ou "
                        "d'acteurs sont directement concernés ?",
        "criteria": {
            "individuelle": "Quelques acteurs : une entreprise, un site, un statut rare, un cas particulier",
            "ciblee": "Une catégorie délimitée par une condition (ressources, âge, situation, profession)",
            "large": "Une grande catégorie (tous les salariés, tous les locataires, un secteur entier)",
            "generale": "Toute la population ou toute l'économie",
        },
    },
    "eco_etat": {
        "type": "choice", "scope": "has_eco",
        "instructions": "La mesure dans `title` et `description` augmente-t-elle ou réduit-elle le poids de l'action "
                        "publique dans l'économie (dépense, prélèvements, règles imposées au marché, propriété publique) ?",
        "criteria": {
            "augmente": "Plus de dépense publique, de prélèvements, de règles imposées au marché ou de propriété publique",
            "inchange_ou_mixte": "Effet nul, ou hausse d'un côté compensée par une baisse de l'autre",
            "diminue": "Moins de dépense publique, de prélèvements, de règles ou de propriété publique",
        },
    },
    "eco_distrib": {
        "type": "choice", "scope": "has_eco",
        "instructions": "Dans quel sens la mesure dans `title` et `description` déplace-t-elle les revenus, le "
                        "patrimoine ou le pouvoir économique ?",
        "criteria": {
            "vers_modestes_ou_salaries": "Des plus aisés, du capital ou des entreprises vers les ménages modestes ou les salariés",
            "neutre": "Sans déplacement marqué, ou bénéfice partagé par tous",
            "vers_aises_ou_entreprises": "Vers les entreprises, le capital ou les ménages aisés, ou financé surtout par les plus modestes",
        },
    },
}

# Force propre du levier sur l'axe economique (0 a 1) : intervention la plus legere -> la plus structurante.
LEVIER_ECO = {
    "declaration_ou_symbole": .15, "information_ou_evaluation": .15, "organisation_institutionnelle": .25,
    "incitation": .4, "sanction_ou_controle": .4, "suppression_ou_allegement": .65, "depense_ou_service": .7,
    "obligation_ou_interdiction": .7, "prelevement": .75, "controle_prix_ou_revenus": .85,
    "propriete_publique": 1.0, "transfert_au_prive": 1.0,
}
PORTEE = {"individuelle": 0.0, "ciblee": 1 / 3, "large": 2 / 3, "generale": 1.0}
BUDGET = {"sans_impact_notable": 0.0, "cout_faible": 0.0, "gain_faible": 0.0, "cout_modere": 1 / 3, "gain_modere": 1 / 3,
          "cout_important": 2 / 3, "gain_important": 2 / 3, "cout_massif": 1.0, "gain_massif": 1.0}
ETAT = {"augmente": -1, "inchange_ou_mixte": 0, "diminue": 1}
DISTRIB = {"vers_modestes_ou_salaries": -1, "neutre": 0, "vers_aises_ou_entreprises": 1}
POIDS_ETAT = .75      # effet sur le poids de l'action publique
POIDS_DISTRIB = .5    # effet distributif ; les deux dans le meme sens saturent a 1
AMPLEUR_MIN = .55     # une mesure minime garde 55 % de la force de son levier
# Une orientation seulement annoncee pese selon l'ampleur du changement vise (rupture) : de 0,15 (objectif modeste) a 0,85
# (« mettre fin au capitalisme »), comme un controle des prix.
DECLARATION_MAX = .85

MOTS = {
    "eco_etat": {"augmente": "plus d'action publique", "inchange_ou_mixte": "action publique inchangée",
                 "diminue": "moins d'action publique"},
    "eco_distrib": {"vers_modestes_ou_salaries": "vers les modestes", "neutre": "sans effet redistributif",
                    "vers_aises_ou_entreprises": "vers les aisés ou les entreprises"},
    "levier": {"declaration_ou_symbole": "déclaration", "information_ou_evaluation": "étude ou rapport",
               "organisation_institutionnelle": "organisation des institutions", "incitation": "incitation",
               "depense_ou_service": "dépense ou service public", "prelevement": "impôt ou cotisation",
               "obligation_ou_interdiction": "obligation ou interdiction", "controle_prix_ou_revenus": "contrôle des prix ou des revenus",
               "sanction_ou_controle": "contrôle et sanction", "suppression_ou_allegement": "allègement de règles",
               "propriete_publique": "propriété publique", "transfert_au_prive": "transfert au privé"},
    "portee": {"individuelle": "portée très limitée", "ciblee": "portée ciblée", "large": "portée large",
               "generale": "portée générale"},
}


def eco_score(d: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    """Note eco (-100..100) et detail du calcul ; None si l'axe ne s'applique pas ou si une reponse manque."""
    needed = ("eco_etat", "eco_distrib", "levier", "portee")
    if any(d.get(k) is None for k in needed):
        return None, {}
    sens = max(-1.0, min(1.0, POIDS_ETAT * ETAT[d["eco_etat"]] + POIDS_DISTRIB * DISTRIB[d["eco_distrib"]]))
    changement = max(filter(lambda x: x is not None,
                            ((d.get("rupture") or 0) / 100, BUDGET.get(d.get("cost_estimate")))))
    force = LEVIER_ECO[d["levier"]]
    if d["levier"] == "declaration_ou_symbole":  # ambition du changement seule : un montant annonce n'est pas un moyen
        force += (DECLARATION_MAX - force) * (d.get("rupture") or 0) / 100
    ampleur = AMPLEUR_MIN + (1 - AMPLEUR_MIN) * (PORTEE[d["portee"]] + changement) / 2
    value = round(100 * sens * force * ampleur)
    words = [MOTS["eco_etat"][d["eco_etat"]], MOTS["eco_distrib"][d["eco_distrib"]],
             MOTS["levier"][d["levier"]], MOTS["portee"][d["portee"]]]
    return value, {"sens": round(sens, 2), "force_levier": force, "ampleur": round(ampleur, 2), "explication": " · ".join(words)}
