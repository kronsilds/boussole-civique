"""Questionnaire q2 : projet a l'essai (docs/questionnaire_q2_2027.md). Rien ici n'est branche sur le pipeline :
la production reste en q1 (questionnaire_2027.py) tant qu'aucune decision n'est prise.

Ce qui change par rapport a q1 (review du 2026-11-10, docs/review_notation_2027.md) :
- une condition oui/non par bloc (`CONDITIONS`), decidee avant les questions du bloc : elle remplace `applies_if`, la
  reponse « indetermine » et les options « non identifiable », « non evaluable », « indeterminable » ;
- doublons retires : `public_vise` (jamais utilise), `changement` (remplace par `degre`, pose a toutes les mesures),
  `faisabilite` (calculee depuis l'instrument, le cout et le financement), `revenus_sens` (calcule depuis les classes
  de revenu), `soc_finalite` (une question oui/non, `soc_egalite` ; la probite passe a l'axe institutions) ;
- trois axes ajoutes : institutions (`inst`), alliances (`inter`), effort de defense (`defense`) ; une question
  `financement` ;
- une seule regle de calcul pour tous les axes : note = 100 x sens x force x ampleur, la force et l'ampleur venant du
  levier et du degre de changement (la portee ne compte que pour l'economie et l'ecologie).

Seconde redaction (2026-11-10, apres le premier essai et un audit externe) :
- un seul jugement « la mesure nomme-t-elle un acte ? » (`a_dispositif`) : sans dispositif, le levier est une
  declaration et la precision une orientation generale (calcules, plus demandes) ; `precision` devient calculee depuis
  `a_dispositif` et une question oui/non `chiffree` ;
- economie en trois aspects juges separement : budget public (`eco_depense`), regles et propriete (`eco_marche`), qui
  gagne et qui paie (`eco_transfert`) ; le pouvoir economique n'est plus melange au transfert de revenus ;
- proteger contre une discrimination : la sanction n'est plus comptee comme de l'ordre, mais le sens ne vient plus que
  de la question sur les libertes (plus de bascule automatique du cote des libertes) ;
- classes de revenu, degre, portee, instrument, cout : la question dit qui ou quoi juger et chaque niveau a un repere.

Redaction des questions (elle compte autant que leur choix) : une question = un jugement rapide et verifiable ; la
question est complete en elle-meme ; les definitions et les exemples sont dans les options, pas dans la consigne ; les
options d'une echelle vont d'un pole a l'autre avec des formulations symetriques ; ce qui releve d'un autre axe est
nomme dans le « non » de la condition. Les memes textes servent a Terra (bareme JSON) et aux modeles de decision
(essai_q2_2027.py).

Conventions de calcul (publiques, a documenter avec la methode) : les options d'une echelle sont equidistantes (-1 a
+1) ; une condition est remplie a partir d'une probabilite de 0,5 ; note = 100 x sens x force x ampleur.
"""
from __future__ import annotations

from typing import Any

import descripteurs_2027 as D
import questionnaire_2027 as Q1

VERSION = "q2"
OUI, NON = "oui", "non"

# --- Conditions : une question oui/non par bloc, sur l'objet de la mesure ------------------------------------------------
CONDITIONS: dict[str, dict[str, str]] = {
    "a_dispositif": {
        "question": "La mesure nomme-t-elle l'acte que l'État accomplirait, de sorte qu'on saurait quoi écrire dans une "
                    "loi, un décret, un budget ou un mandat de négociation ?",
        "oui": "Elle dit ce qui serait créé, modifié, supprimé, financé, interdit, imposé ou refusé : une prestation, un "
               "impôt, une règle, un organisme, un recrutement, un équipement désigné, le rejet d'un texte précis, une "
               "règle précise à obtenir dans une négociation. Un chiffre n'est pas nécessaire.",
        "non": "Elle énonce un objectif, une valeur, une priorité ou un résultat, même chiffré (« atteindre 400 000 "
               "logements », « ramener les prélèvements à 40 % du PIB ») ; ou elle annonce une réforme, un plan, une "
               "stratégie ou un « droit à » sans dire ce qui changerait ; ou elle se borne à « renforcer », « garantir », "
               "« soutenir », « encourager », « défendre »."},
    "a_menages": {
        "question": "Peut-on dire, à la lecture de la mesure, quels particuliers paieraient ou recevraient plus ou moins "
                    "d'argent ?",
        "oui": "Elle change un salaire, une pension, une allocation, une bourse, un impôt ou une cotisation payés par des "
               "particuliers, un prix, un loyer, un tarif, un remboursement, le prix d'un service aujourd'hui payant, ou "
               "les conditions pour toucher une prestation ou obtenir un logement social.",
        "non": "Elle ne touche que des entreprises, des administrations ou des règles ; ou son effet sur le budget des "
               "ménages est indirect ou lointain (croissance, emploi, construction, qualité d'un service, équipement "
               "public ouvert à tous) ; ou elle annonce un objectif fiscal ou social sans dire qui paierait ou recevrait."},
    "a_eco": {
        "question": "La mesure tranche-t-elle un choix de politique économique ou sociale ?",
        "oui": "Elle change les impôts ou les cotisations, la redistribution des revenus ou du patrimoine, le droit du "
               "travail, la régulation d'un marché ou des prix, les aides aux entreprises, la propriété publique ou privée "
               "d'une activité, le niveau d'un service public ou d'une protection sociale (santé, école, retraites, "
               "logement, transports), le nombre d'agents publics ou le volume de la dépense publique.",
        "non": "Son objet est ailleurs : sécurité, justice, défense, immigration, institutions, culture, diplomatie, "
               "mœurs ; ou une règle de sécurité ou de protection des personnes imposée à des entreprises ou à des "
               "services (contenus en ligne, algorithmes, encadrement des enfants) sans but économique ; ou une norme, "
               "une interdiction ou un investissement dont l'objet est de protéger l'environnement, sans changer un "
               "impôt, un prix ni la propriété d'une activité. Le seul fait qu'elle coûte de l'argent ne suffit pas."},
    "a_soc": {
        "question": "La mesure change-t-elle ce que les personnes ont le droit de faire, ou la façon dont l'État les "
                    "contrôle et les sanctionne ?",
        "oui": "Elle touche aux libertés individuelles et publiques, aux mœurs, à la vie privée, à la laïcité, aux "
               "discriminations, à l'ordre public, aux pouvoirs de la police, aux peines ou à la surveillance.",
        "non": "Elle crée ou finance un service, une aide ou un « droit à » une prestation (logement, vacances, formation, "
               "soins) : ce n'est pas une liberté. Ou elle porte seulement sur les moyens ou l'organisation de la police, "
               "de la justice ou de l'administration ; ou sur l'entrée et le séjour des étrangers ; ou sur le contrôle "
               "des élus et des institutions ; ou sur des règles imposées aux entreprises."},
    "a_sov": {
        "question": "La mesure change-t-elle le partage des décisions entre la France et l'Union européenne ou une "
                    "organisation internationale ?",
        "oui": "Elle transfère, partage, reprend ou refuse une compétence, une règle ou une politique commune : traités, "
               "droit européen, budget et politiques de l'Union, accords commerciaux, monnaie, défense commune.",
        "non": "Elle se décide et s'applique en France sans toucher aux règles européennes ou internationales. "
               "Mentionner l'Europe ou une « souveraineté » (industrielle, numérique, alimentaire) ne suffit pas."},
    "a_immigration": {
        "question": "La mesure porte-t-elle sur l'entrée, le séjour, l'asile, l'éloignement ou la naturalisation des "
                    "étrangers ?",
        "oui": "Visas, titres de séjour, régularisation, asile, regroupement familial, contrôles aux frontières, "
               "expulsions, droit du sol, accès à la nationalité.",
        "non": "Elle ne change pas ces règles : elle concerne l'intégration, l'hébergement, l'aide au développement, ou "
               "ne concerne pas les étrangers."},
    "a_droits": {
        "question": "La mesure fait-elle dépendre l'accès à un droit, une prestation, un emploi ou un service de la "
                    "nationalité, du titre de séjour ou de l'ancienneté de résidence ?",
        "oui": "Elle réserve, conditionne, ouvre ou étend un droit selon la nationalité ou le statut : priorité "
               "nationale, délai de résidence pour une allocation, aide médicale des étrangers, droit de vote des "
               "résidents étrangers, emplois fermés ou ouverts aux étrangers.",
        "non": "Elle s'applique à tous de la même façon. Désigner les bénéficiaires par « les Français », « chaque "
               "enfant » ou « les familles » sans exclure personne ne suffit pas."},
    "a_ecolo": {
        "question": "La mesure a-t-elle un effet direct sur l'environnement, le climat, l'énergie ou la biodiversité ?",
        "oui": "Elle change des émissions, une pollution, l'usage des sols, de l'eau ou des ressources, la production ou "
               "la consommation d'énergie, la protection d'espèces ou de milieux.",
        "non": "Son effet sur l'environnement est nul, incertain ou très indirect."},
    "a_institutions": {
        "question": "La mesure change-t-elle qui détient le pouvoir politique, ou comment ce pouvoir est contrôlé ?",
        "oui": "Elle modifie les pouvoirs du Président, du Gouvernement, du Parlement, des juges, des collectivités ou "
               "des autorités indépendantes, le mode de scrutin, le référendum, la participation des citoyens aux "
               "décisions, l'indépendance de la justice ou des médias, la transparence et la probité des élus et des "
               "hauts fonctionnaires.",
        "non": "Elle réorganise des services, fusionne ou supprime des agences chargées d'appliquer une politique, "
               "change des moyens ou des procédures sans déplacer le pouvoir de décision ; ou elle allège des "
               "autorisations ou des normes pour les entreprises ou les particuliers ; ou elle concerne les associations, "
               "les syndicats ou la vie interne d'un parti. Passer par la Constitution ou par un référendum pour adopter "
               "une règle ne suffit pas : c'est l'objet de la règle qui compte."},
    "a_alliances": {
        "question": "La mesure prend-elle position sur les liens militaires ou stratégiques de la France avec d'autres "
                    "puissances ?",
        "oui": "OTAN et son commandement intégré, relation avec les États-Unis, la Russie ou la Chine, défense européenne "
               "commune, soutien militaire ou sanctions décidés avec les alliés (Ukraine, Russie), opérations et bases "
               "militaires à l'étranger, accords de défense, non-alignement.",
        "non": "Elle porte sur l'aide au développement, la francophonie, le commerce, l'ONU et le droit international, "
               "les seuls moyens de l'armée française, ou un conflit où la France n'est pas engagée aux côtés de ses "
               "alliés (reconnaissance d'un État, médiation, aide humanitaire)."},
    "a_defense": {
        "question": "La mesure change-t-elle les moyens militaires de la France ?",
        "oui": "Budget de la défense, effectifs, armement, dissuasion nucléaire, industrie d'armement, réserve, service "
               "militaire, renseignement militaire, cyberdéfense.",
        "non": "Elle porte sur la police, la sécurité civile, la diplomatie ou les anciens combattants sans changer les "
               "moyens des armées."},
}

# --- Questions ---------------------------------------------------------------------------------------------------------
# type : « choix » (options sans ordre), « echelle » (options ordonnees d'un pole a l'autre) ou « oui_non ».
# famille : « moyen » (ce que le texte prevoit reellement) ou « vise » (ce que la mesure vise, meme seulement annonce).


def _q(libelle: str, type_: str, famille: str, question: str, options: dict[str, str],
       condition: str | tuple[str, ...] | None = None) -> dict[str, Any]:
    """`condition` : une condition, ou plusieurs (la question est posee des que l'une d'elles est remplie)."""
    return {"libelle": libelle, "type": type_, "famille": famille, "question": question, "options": options,
            "condition": condition}


def conditions_de(q: dict[str, Any]) -> tuple[str, ...]:
    c = q["condition"]
    return () if not c else (c,) if isinstance(c, str) else tuple(c)


def ouverte(q: dict[str, Any], remplie: Any) -> bool:
    """La question se pose-t-elle ? `remplie(condition)` dit si une condition est remplie."""
    cs = conditions_de(q)
    return not cs or any(remplie(c) for c in cs)


def _ordre(criteres: dict[str, str], *cles: str) -> dict[str, str]:
    return {k: criteres[k] for k in cles}


_LEVIER = {**D.QUESTIONS["levier"]["criteria"],
           "declaration_ou_symbole": "Acte symbolique ou prise de position, sans autre moyen : reconnaissance, "
                                     "commémoration, appel, soutien ou condamnation"}
_COMPENSE = "ou effets qui se compensent"

QUESTIONS: dict[str, dict[str, Any]] = {
    # --- nature de la mesure : toutes les mesures --------------------------------------------------------------------------
    "portee": _q("Portée", "echelle", "moyen",
                 "Combien de personnes ou d'acteurs la mesure concerne-t-elle directement, c'est-à-dire ceux dont les "
                 "droits, les obligations ou les revenus changent dès son application ?",
                 {"individuelle": "Quelques acteurs : une entreprise, un site, un statut rare, quelques milliers de "
                                  "personnes au plus",
                  "ciblee": "Une catégorie délimitée par une condition (ressources, âge, situation, profession, "
                            "territoire) : moins d'un million de personnes environ",
                  "large": "Une grande catégorie ou tout le monde, plus d'un million de personnes : tous les salariés, "
                           "tous les retraités, tous les locataires, un secteur entier, tous les contribuables, toute "
                           "la population"},
                 ("a_menages", "a_eco", "a_ecolo")),
    "chiffree": _q("Engagement chiffré", "oui_non", "moyen",
                   "La mesure cite-t-elle un chiffre qui l'engage : un montant, un nombre, un taux, un seuil, une durée "
                   "ou une échéance ?",
                   {OUI: "`title` ou `description` donnent au moins un montant, un nombre, un taux, un seuil, une durée ou "
                         "une date propres à la mesure",
                    NON: "Aucun chiffre, ou seulement un chiffre de constat ou de contexte (situation actuelle, "
                         "comparaison)"}),
    "degre": _q("Degré de changement", "echelle", "vise",
                "Quel changement la mesure vise-t-elle par rapport à ce qui existe aujourd'hui dans son domaine ? Juge "
                "l'ambition affichée, même si les moyens ne sont pas précisés ; une intention générale qui ne nomme "
                "aucun changement est un ajustement. Dans le doute entre deux niveaux, choisis le plus bas.",
                {"ajustement": "Ajustement : ce qui existe reste en place ; la mesure en change un paramètre (montant, taux, "
                               "seuil, effectifs, moyens, calendrier), l'applique mieux, le prolonge, ou affiche une "
                               "intention générale (« renforcer », « mieux protéger »)",
                 "notable": "Changement notable : crée ou supprime un dispositif, un droit, une obligation, une peine ou un "
                            "organisme, sans toucher aux principes du domaine (nouvelle allocation, taxe sectorielle, "
                            "peines planchers, quota, nouveau service public, suppression d'une agence)",
                 "rupture": "Rupture : met fin, pour tout un secteur ou toute la population, à un principe ou à un système "
                            "en vigueur (nationalisation ou privatisation d'un secteur, sortie d'un traité ou de l'OTAN, fin "
                            "du droit du sol, régularisation générale, retraite par capitalisation, suppression d'un impôt "
                            "majeur, nouvelle République, légalisation ou interdiction générale d'une pratique). Créer un "
                            "dispositif nouveau, même coûteux ou ambitieux, reste un changement notable"}),
    # --- dispositif : seulement si la mesure en decrit un -------------------------------------------------------------------
    "levier": _q("Levier", "choix", "moyen",
                 "Par quel moyen principal la mesure agit-elle ? Choisis celui qui porte l'essentiel de l'effet.",
                 _LEVIER, "a_dispositif"),
    "instrument": _q("Instrument juridique", "choix", "moyen",
                     "Quel texte faut-il au minimum pour appliquer la mesure ? Si elle en exige plusieurs, retiens le plus "
                     "difficile à obtenir.",
                     {"decret_ou_arrete": "Décision du Gouvernement dans le cadre des lois et du budget existants : décret, "
                                          "arrêté, circulaire, organisation des services, programmes scolaires, nomination, "
                                          "audit, plan d'action, vote ou veto de la France dans une instance européenne ou "
                                          "internationale",
                      "loi_ordinaire": "Loi votée par le Parlement : droit, obligation, interdiction, peine, organisme ou "
                                       "statut nouveaux ; règle qui s'impose aux personnes, aux entreprises ou aux "
                                       "collectivités",
                      "loi_de_finances_ou_securite_sociale": "Loi de finances ou de financement de la Sécurité sociale : "
                                                             "impôt, taxe, cotisation, niche fiscale ; dépense nouvelle "
                                                             "importante (prestation créée ou revalorisée, recrutements, "
                                                             "plan d'investissement)",
                      "loi_organique": "Loi organique : fonctionnement des pouvoirs publics, statut des élus et des "
                                       "magistrats, règles des lois de finances",
                      "revision_constitutionnelle": "Révision de la Constitution",
                      "traite_europeen_ou_international": "Accord des partenaires de la France : traité, règle ou budget de "
                                                          "l'Union européenne (commerce, concurrence, monnaie, normes "
                                                          "européennes), accord international"}, "a_dispositif"),
    "cout": _q("Ordre de grandeur budgétaire", "echelle", "moyen",
               "Quel est l'ordre de grandeur de l'effet annuel de la mesure sur les finances publiques (État, "
               "collectivités, Sécurité sociale), une fois en place ? Compte seulement la dépense ou la recette que la "
               "mesure crée elle-même, pas ses conséquences en chaîne. Une dépense nouvelle ou une baisse d'impôt est un "
               "coût ; une hausse d'impôt ou une économie est un gain. Sans montant cité, estime d'après le nombre de "
               "personnes concernées et des dispositifs comparables.",
               {"gain_massif": "Recette ou économie de plus de 10 Md€ par an : hausse d'un grand impôt, recul de l'âge de "
                               "la retraite, baisse générale des dépenses",
                "gain_important": "Recette ou économie de 1 à 10 Md€ par an : impôt sur les grandes fortunes, suppression "
                                  "d'une grande niche fiscale ou d'une prestation",
                "gain_modere": "Recette ou économie de 0,1 à 1 Md€ par an : taxe sectorielle, suppression de plusieurs "
                               "agences",
                "gain_faible": "Recette ou économie de moins de 0,1 Md€ par an : suppression d'un organisme ou d'une "
                               "petite dépense",
                "sans_impact_notable": "Ni dépense ni recette publique nouvelle : norme, interdiction, droit, peine, "
                                       "réorganisation, position diplomatique",
                "cout_faible": "Coût de moins de 0,1 Md€ par an : organisme, étude, expérimentation, aide à quelques "
                               "milliers de personnes",
                "cout_modere": "Coût de 0,1 à 1 Md€ par an : prestation ciblée, quelques milliers de recrutements, plan "
                               "pour un secteur",
                "cout_important": "Coût de 1 à 10 Md€ par an : prestation versée à des millions de personnes, dizaines de "
                                  "milliers de recrutements, baisse d'un impôt important, grand programme d'investissement",
                "cout_massif": "Coût de plus de 10 Md€ par an : retraite à 60 ans, baisse massive de cotisations ou de "
                               "TVA, revenu universel"}, "a_dispositif"),
    "financement": _q("Financement", "echelle", "moyen",
                      "La mesure ou son `passage` disent-ils comment elle serait payée ?",
                      {"non_finance": "Rien n'est dit sur son financement",
                       "evoque": "Un financement est évoqué sans mécanisme vérifiable : croissance attendue, lutte contre "
                                 "la fraude, « économies » non désignées",
                       "designe": "Une recette, une économie ou un redéploiement précis est désigné pour la payer"},
                      "a_dispositif"),
    # --- axes : sens, si la condition de l'axe est remplie -------------------------------------------------------------------
    # Economie : trois aspects juges separement (audit du 2026-11-10). Le niveau du milieu y est une reponse normale :
    # une mesure peut toucher un aspect sans toucher les autres.
    "eco_depense": _q("Budget public", "echelle", "vise",
                      "La mesure augmente-t-elle ou réduit-elle le poids du budget public : dépenses, services publics, "
                      "impôts et cotisations ?",
                      {"augmente": "Plus de dépenses, de services, d'agents publics ou de prestations ; ou plus d'impôts et "
                                   "de cotisations (y compris la fin d'une exonération)",
                       "inchange": "Pas d'effet sur le volume des dépenses ni des prélèvements : règle sans coût, charge "
                                   f"déplacée d'un public à un autre, {_COMPENSE}",
                       "reduit": "Moins de dépenses, de services, d'agents publics ou de prestations ; ou moins d'impôts et "
                                 "de cotisations (y compris une nouvelle exonération)"}, "a_eco"),
    "eco_marche": _q("Règles et propriété", "echelle", "vise",
                     "La mesure renforce-t-elle ou allège-t-elle les règles imposées aux entreprises et aux marchés, ou la "
                     "part du public dans la propriété des activités ?",
                     {"encadre": "Plus de règles ou de propriété publique : obligations des employeurs et droits des "
                                 "salariés dans l'entreprise, prix, loyers ou salaires encadrés, normes et autorisations, "
                                 "nationalisation, monopole ou pôle public",
                      "inchange": "Ne change ni les règles du marché ni la propriété : simple dépense, prestation ou "
                                  f"impôt ; {_COMPENSE}",
                      "liberalise": "Moins de règles ou de propriété publique : droit du travail assoupli, prix ou loyers "
                                    "libérés, normes et autorisations allégées, ouverture à la concurrence, privatisation, "
                                    "délégation au privé"}, "a_eco"),
    "eco_transfert": _q("Qui gagne, qui paie", "echelle", "vise",
                        "La mesure fait-elle gagner un groupe aux dépens d'un autre, entre d'un côté les ménages modestes "
                        "et les salariés, de l'autre les ménages aisés, les détenteurs de capital et les entreprises ? "
                        "Juge l'effet de la mesure, pas la façon dont elle est présentée.",
                        {"vers_modestes_ou_salaries": "Oui, en faveur des ménages modestes ou des salariés : impôt ou charge "
                                                      "sur les plus aisés, le capital ou les entreprises ; hausse de "
                                                      "salaire imposée aux employeurs ; prestation ou aide réservée aux "
                                                      "plus modestes",
                         "neutre": "Non, aucun de ces groupes ne gagne nettement aux dépens de l'autre : service, "
                                   "investissement ou prestation ouverts à tous sans condition de ressources, politique "
                                   "industrielle ou de filière, règle qui s'applique à tous, gagnants et payeurs non "
                                   "désignés",
                         "vers_aises_ou_entreprises": "Oui, en faveur des entreprises, du capital ou des ménages aisés : "
                                                      "baisse de leurs impôts ou de leurs cotisations, subvention ou aide "
                                                      "versée aux entreprises sans contrepartie, ou charge qui pèse "
                                                      "surtout sur les plus modestes (hausse de TVA, franchise, "
                                                      "prestation réduite)"}, "a_eco"),
    "soc_autorite": _q("Autorité", "echelle", "vise",
                       "La mesure allège-t-elle ou renforce-t-elle le contrôle, la surveillance, la sanction ou les "
                       "normes que l'État impose aux personnes ?",
                       _ordre(Q1.QUESTIONS["soc_autorite"]["criteria"], "allege", "inchange", "renforce"), "a_soc"),
    "soc_libertes": _q("Libertés", "echelle", "vise",
                       "La mesure étend-elle ou restreint-elle des libertés ou des droits individuels, y compris ceux "
                       "des minorités ?",
                       _ordre(Q1.QUESTIONS["soc_libertes"]["criteria"], "etend", "inchange", "restreint"), "a_soc"),
    "soc_egalite": _q("Protection contre les discriminations", "oui_non", "vise",
                      "La mesure a-t-elle pour objet principal de protéger des personnes contre des discriminations ou "
                      "des violences liées à ce qu'elles sont ?",
                      {OUI: "Lutte contre le racisme, le sexisme, l'homophobie, les violences faites aux femmes, les "
                            "discriminations liées à l'origine, au handicap ou à la religion, y compris par des sanctions",
                       NON: "Son objet principal est l'ordre public, la sécurité, la délinquance en général, les mœurs ou "
                            "une autre liberté"}, "a_soc"),
    "sov_niveau": _q("Niveau de décision", "echelle", "vise", "Vers quel niveau la mesure déplace-t-elle la décision ?",
                     _ordre(Q1.QUESTIONS["sov_niveau"]["criteria"], "vers_europe_international", "equilibre", "vers_national"),
                     "a_sov"),
    "ouv_sens": _q("Entrée et séjour des étrangers", "echelle", "vise",
                   "La mesure facilite-t-elle ou restreint-elle l'entrée, le séjour, l'asile ou la naturalisation des "
                   "étrangers ?",
                   _ordre(Q1.QUESTIONS["ouv_sens"]["criteria"], "accueil", "inchange", "fermeture"), "a_immigration"),
    "droits_statut": _q("Accès aux droits selon le statut", "echelle", "vise",
                        "Pour les personnes étrangères ou sans la nationalité, la mesure ouvre-t-elle ou ferme-t-elle "
                        "l'accès au droit, à la prestation, à l'emploi ou au service en cause ? Lis le verbe et son effet, "
                        "pas la simple mention des Français.",
                        _ordre(Q1.QUESTIONS["droits_statut"]["criteria"], "universel", "etendu", "inchange", "conditionne",
                               "reserve_nationaux"), "a_droits"),
    "env_sens": _q("Environnement", "echelle", "vise",
                   "La mesure allège-t-elle ou renforce-t-elle la protection de l'environnement, du climat ou de la "
                   "biodiversité ?",
                   _ordre(Q1.QUESTIONS["env_sens"]["criteria"], "allege", "neutre", "protege"), "a_ecolo"),
    "inst_pouvoir": _q("Partage du pouvoir", "echelle", "vise",
                       "La mesure répartit-elle davantage le pouvoir politique, ou le concentre-t-elle ?",
                       {"partage": "Répartit ou contrôle davantage le pouvoir : plus de pouvoirs au Parlement, aux juges, "
                                   "aux collectivités ou aux citoyens (référendum d'initiative citoyenne, proportionnelle, "
                                   "assemblées tirées au sort), indépendance de la justice ou des médias, transparence et "
                                   "règles de probité pour les élus",
                        "equilibre": f"Ne déplace pas le pouvoir, {_COMPENSE}",
                        "concentre": "Concentre le pouvoir ou allège son contrôle : plus de pouvoirs au Président ou au "
                                     "Gouvernement, ordonnances ou référendum décidé par l'exécutif pour passer outre le "
                                     "Parlement ou les juges, recentralisation, limitation du pouvoir des juges ou des "
                                     "autorités indépendantes"}, "a_institutions"),
    "int_alliances": _q("Alliances", "echelle", "vise",
                        "La mesure lie-t-elle davantage la France à ses alliés, ou lui fait-elle prendre ses distances ?",
                        {"alliances": "Lie davantage la France à ses alliés : engagement dans l'OTAN, lien avec les "
                                      "États-Unis, défense européenne commune, soutien militaire à un allié ou à l'Ukraine, "
                                      "sanctions communes, opérations extérieures menées avec eux",
                         "equilibre": f"Maintient les alliances tout en affirmant l'autonomie de la France, {_COMPENSE}",
                         "non_alignement": "Éloigne la France de ses alliés : sortie de l'OTAN ou de son commandement, "
                                           "refus de s'aligner sur les États-Unis, arrêt d'un soutien militaire, levée de "
                                           "sanctions, rapprochement avec la Russie ou la Chine, retrait de bases ou "
                                           "d'opérations extérieures"}, "a_alliances"),
    "def_effort": _q("Effort de défense", "echelle", "vise",
                     "La mesure réduit-elle ou augmente-t-elle les moyens militaires de la France ?",
                     {"reduit": "Réduit les moyens militaires : baisse du budget ou des effectifs, abandon d'un programme "
                                "d'armement, désarmement, réduction de la dissuasion",
                      "inchange": f"Les réorganise sans les augmenter ni les réduire, {_COMPENSE}",
                      "augmente": "Augmente les moyens militaires : hausse du budget ou des effectifs, nouveaux armements, "
                                  "renforcement de la dissuasion, service militaire"}, "a_defense"),
}
# Effet par classe de revenu : memes classes et memes cles que q1 (questionnaire_2027.CLASSES_REVENU). La question dit qui
# juger (les menages de la classe que la mesure touche, pas la classe entiere) et donne un ordre de grandeur a chaque
# niveau : au premier essai, un modele comptait un service ouvert a tous comme un gain, l'autre repondait « pas concernee ».
_EFFET = {"perd_fortement": "Perdent fortement : de l'ordre de 100 € par mois ou plus, ou perte d'une prestation, d'un "
                            "logement ou d'un revenu essentiel",
          "perd": "Perdent modérément : quelques dizaines d'euros par mois, ou un avantage ponctuel",
          "non_concernee": "Pas concernée : aucun ménage de cette classe ne recevrait ni ne paierait rien du fait de la "
                           "mesure ; ou gains et pertes qu'on ne peut pas départager",
          "gagne": "Gagnent modérément : quelques dizaines d'euros par mois, ou un avantage ponctuel",
          "gagne_fortement": "Gagnent fortement : de l'ordre de 100 € par mois ou plus, ou accès à une prestation, à un "
                             "logement ou à un revenu essentiel"}
for _k, (_lib, _def, _pos) in Q1.CLASSES_REVENU.items():
    QUESTIONS[_k] = _q(f"Effet financier : {_lib}", "echelle", "moyen",
                       f"Classe jugée : {_def}. Les ménages de cette classe que la mesure touche directement y "
                       "gagnent-ils ou y perdent-ils du pouvoir d'achat ? Ne juge que ceux qui recevraient ou paieraient "
                       "quelque chose du fait de la mesure (revenu, prestation, impôt, prix, loyer, service devenu gratuit "
                       "ou payant), pas la classe entière. Une mesure ouverte à tous touche aussi cette classe ; une "
                       "mesure réservée à d'autres ne la concerne pas.",
                       dict(_EFFET), "a_menages")

QUESTIONS_SENS = ("eco_depense", "eco_marche", "eco_transfert", "soc_autorite", "soc_libertes", "sov_niveau", "ouv_sens", "droits_statut",
                  "env_sens", "inst_pouvoir", "int_alliances", "def_effort")
# Axes affichables : (question(s) de sens, pole -100, pole +100).
AXES = {"eco": ("Économie", "gauche", "droite"), "soc": ("Société", "libertés", "ordre"),
        "sov": ("Souveraineté", "européen et international", "national"),
        "ouverture": ("Immigration et droits des étrangers", "accueil", "fermeture"),
        "ecolo": ("Écologie", "moins de protection", "plus de protection"),
        "inst": ("Institutions", "pouvoir partagé", "pouvoir concentré"),
        "inter": ("Alliances", "engagement dans les alliances", "non-alignement"),
        "defense": ("Défense", "moins de moyens militaires", "plus de moyens militaires")}

# --- Calcul --------------------------------------------------------------------------------------------------------------
_L = Q1._L
FORCES = {**Q1.FORCES,
          "inst": dict(zip(_L, (.15, .4, .8, .3, .4, .3, .7, .3, .6, .6, .3, .3))),
          "inter": dict(zip(_L, (.15, .15, .6, .3, .6, .4, .6, .3, .7, .6, .4, .3))),
          "defense": dict(zip(_L, (.15, .15, .5, .3, .8, .4, .6, .3, .4, .6, .6, .4)))}
DEGRE = {"ajustement": 0, "notable": 50, "rupture": 100}               # valeur affichee (« rupture »)
DEGRE_FORCE = {"ajustement": 0.0, "notable": .7, "rupture": 1.0}       # force minimale, quel que soit le levier
DEGRE_AMPLEUR = {"ajustement": .2, "notable": .6, "rupture": 1.0}
DECLARATION = {"ajustement": .15, "notable": .5, "rupture": .85}       # une intention ne pese jamais comme un dispositif
AXES_PORTEE = ("eco", "ecolo")       # axes ou le nombre de personnes concernees change l'ampleur
# Portee : posee seulement si la mesure a un public (menages, economie ou ecologie), sinon null. Trois niveaux : « large »
# et « generale » de q1 sont fusionnes (confusion la plus frequente entre modeles, 7,5 points au plus sur une note).
PORTEE = {"individuelle": 0.0, "ciblee": .5, "large": 1.0}
# Economie : sens = 0,5 x budget public + 0,5 x regles et propriete + 0,75 x qui gagne et qui paie, borne a [-1, 1].
# Qui gagne et qui paie compte plus que la taille du budget (q1 : 0,75 pour l'action publique, 0,5 pour la redistribution).
POIDS_ECO = {"eco_depense": .5, "eco_marche": .5, "eco_transfert": .75}
POIDS_SOC = .8                       # q1 : 0,6. Une seule question tranchee ne plafonne plus a 60.
# Niveaux de q1 (0 obstacle majeur, 25 faible, 50 moyenne, 75 elevee, 100 immediate), cales sur ses reponses : une loi
# etait jugee « moyenne » dans 60 a 73 % des cas, « elevee » quand son cout est faible, une revision constitutionnelle
# « obstacle majeur » dans 99 % des cas.
BASE_FAISABILITE = {"decret_ou_arrete": 100, "loi_ordinaire": 50, "loi_de_finances_ou_securite_sociale": 50,
                    "loi_organique": 50, "traite_europeen_ou_international": 25, "revision_constitutionnelle": 0}
COUTS = ("cout_faible", "cout_modere", "cout_important", "cout_massif")


def sens(k: str, valeur: str) -> float:
    """Position d'une option sur son echelle : -1 (premiere option) a +1 (derniere)."""
    options = list(QUESTIONS[k]["options"])
    return -1 + 2 * options.index(valeur) / (len(options) - 1)


def levier(r: dict[str, Any]) -> str:
    """Sans dispositif (`levier` null), la mesure est une declaration."""
    return r.get("levier") or "declaration_ou_symbole"


def precision(r: dict[str, Any]) -> str | None:
    """Precision calculee : chiffree si un chiffre engage la mesure, sinon precise si elle nomme un acte."""
    if r.get("chiffree") is None:
        return None
    return "chiffre" if r["chiffree"] == OUI else "precis" if r.get("levier") else "orientation_generale"


def force(axe: str, r: dict[str, Any]) -> float:
    if levier(r) == "declaration_ou_symbole":
        return DECLARATION[r["degre"]]
    return max(FORCES[axe][levier(r)], DEGRE_FORCE[r["degre"]])


def ampleur(axe: str, r: dict[str, Any]) -> float:
    a = DEGRE_AMPLEUR[r["degre"]]
    if axe in AXES_PORTEE:
        a = (a + PORTEE[r["portee"]]) / 2 if r.get("portee") else a
    return D.AMPLEUR_MIN + (1 - D.AMPLEUR_MIN) * a


def note(axe: str, s: float, r: dict[str, Any]) -> int:
    return round(100 * max(-1.0, min(1.0, s)) * force(axe, r) * ampleur(axe, r))


def faisabilite(r: dict[str, Any]) -> int | None:
    """Faisabilite calculee (0..100), sans question propre : le texte juridique necessaire, un cran de plus pour une loi
    au cout ou au gain faible, un cran de moins pour une rupture qui passe par un traite ou pour un cout massif dont
    le financement n'est pas designe. None si la mesure ne decrit pas de dispositif."""
    base = BASE_FAISABILITE.get(r.get("instrument"))
    if base is None:
        return None
    if base == 50 and r.get("cout") in ("cout_faible", "gain_faible"):
        base += 25
    if r.get("degre") == "rupture" and r.get("instrument") == "traite_europeen_ou_international":
        base -= 25
    if r.get("cout") == "cout_massif" and r.get("financement") != "designe":
        base -= 25
    return max(0, base)


def calculer(r: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Reponses q2 -> valeurs de toutes les dimensions et explications en mots. Une reponse absente ou null = axe non note."""
    cout = r.get("cout")
    v: dict[str, Any] = {"rupture": DEGRE.get(r.get("degre")), "precision": precision(r), "levier": levier(r),
                         "legal_instrument": r.get("instrument"), "cost_estimate": cout,
                         "financement": r.get("financement") if cout in COUTS else None, "feasibility": faisabilite(r),
                         "rights_status": Q1.DROITS.get(r.get("droits_statut"))}
    expl: dict[str, str] = {}
    profil = Q1.profil_revenu(r)
    for axe_revenu, cle in Q1.AXES_REVENU.items():
        v[axe_revenu] = profil[cle] if profil else None
    v["income_direction"] = profil["effet"] if profil else None   # q1 : question revenus_sens
    if profil:
        expl["revenu"] = Q1.explication_revenu(r)
    mots = [D.MOTS["levier"][levier(r)], QUESTIONS["degre"]["options"][r["degre"]].split(" :")[0].lower()]

    def poser(axe: str, s: float, *questions: str) -> None:
        v[axe] = note(axe, s, r)
        expl[axe] = " · ".join([*(f"{QUESTIONS[q]['libelle'].lower()} : {r[q].replace('_', ' ')}" for q in questions), *mots])

    for axe in AXES:
        v[axe] = None
    if all(r.get(q) for q in POIDS_ECO):
        s_eco = sum(p * sens(q, r[q]) for q, p in POIDS_ECO.items())
        if any(sens(q, r[q]) for q in POIDS_ECO):   # trois fois le niveau du milieu : la mesure ne prend pas de direction
            poser("eco", s_eco, *(q for q in POIDS_ECO if sens(q, r[q])))
    if r.get("soc_autorite") and r.get("soc_libertes"):
        a, lib = sens("soc_autorite", r["soc_autorite"]), sens("soc_libertes", r["soc_libertes"])
        if r.get("soc_egalite") != OUI:
            poser("soc", POIDS_SOC * (a + lib), "soc_autorite", "soc_libertes")
        elif lib:   # proteger contre une discrimination : la sanction n'est pas de l'ordre, seul le sens des libertes compte
            poser("soc", POIDS_SOC * lib, "soc_libertes", "soc_egalite")
    # immigration et droits des etrangers : la regle d'entree et de sejour d'abord, sinon l'acces aux droits selon le statut
    if r.get("ouv_sens"):
        poser("ouverture", sens("ouv_sens", r["ouv_sens"]), "ouv_sens")
    elif r.get("droits_statut"):
        poser("ouverture", sens("droits_statut", r["droits_statut"]), "droits_statut")
    for axe, q in (("sov", "sov_niveau"), ("ecolo", "env_sens"), ("inst", "inst_pouvoir"), ("inter", "int_alliances"),
                   ("defense", "def_effort")):
        if r.get(q):
            poser(axe, sens(q, r[q]), q)
    return v, expl
