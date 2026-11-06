#!/usr/bin/env python3
"""Pipeline modulaire d'ingestion et de pré-scoring pour le prototype 2027.

Les propositions d'entrée doivent venir de sources explicites. Le scoring heuristique
sert au tri, jamais à présenter une mesure comme vérifiée. Le scoring LLM est facultatif,
compatible OpenAI, nécessite une clé fournie par l'utilisateur et doit être revu humainement.
Le bundle public du comparateur est la source par défaut; les photos restent des URL d’origine et ne sont pas téléchargées localement.
"""
from __future__ import annotations
import argparse, hashlib, html.parser, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from llm_logging_2027 import LLMJournal, LLMLogError, scoring_snapshot
from programme_corpus_2027 import with_corpus_evidence
from scoring_context_2027 import (
    AXES_DIMENSIONS, DEFAULT_WEB_MAX_TOKENS, DIMENSIONS, ScoringAPIError, WebResponseError, context_warnings, digest,
    importance_evidence, load_context, normalize_web_model, number, parse_json_object,
    proposal_context, request_json, reusable_web_result, review_issues, review_queue, update_importance,
    utc_now, web_cache_key, web_reassess,
)

# ── Configuration LLM : les clés sont fournies uniquement par l'environnement. ──
LLM_PROVIDER = "openrouter"
LLM_MODEL = ""
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 32000
LLM_TIMEOUT_SECONDS = 90
SOURCE_JSON_DOWNLOAD_URL = "https://raw.githubusercontent.com/coucou123212321232123/presidentielle-2027-comparateur/main/public-data/data-v2.json"  # Endpoint data-v2 réellement chargé actuellement par le JS du site

# Les modèles se règlent dans .env : OPENROUTER_SCORING_MODEL et OPENROUTER_WEB_MODEL.
# Les anciens connecteurs restent configurables via LLM_PROVIDER, LLM_MODEL et LLM_API_BASE_URL.

THEME_LABELS = {
    "economie": "Économie et pouvoir d'achat", "fiscalite": "Fiscalité", "emploi": "Emploi et travail",
    "retraites": "Retraites", "energie": "Énergie", "ecologie": "Écologie et climat",
    "agriculture": "Agriculture", "logement": "Logement", "sante": "Santé", "education": "Éducation",
    "securite": "Sécurité et justice", "immigration": "Immigration et asile", "institutions": "Institutions et démocratie",
    "europe": "Europe", "international": "International et défense", "numerique": "Numérique et IA",
    "culture": "Culture et médias", "outre_mer": "Outre-mer", "services_publics": "Services publics et territoires",
    "famille": "Famille et société"
}
THEMES = {**{k:v for k,v in THEME_LABELS.items()}, **{re.sub(r'[^a-z]','',v.lower()):v for v in THEME_LABELS.values()}}

TAGS = ["🦄 Licorne constitutionnelle", "💸 Gouffre budgétaire", "⚖️ Censure Conseil Constitutionnel", "🎯 Ultra-ciblé", "📢 Effet d'annonce", "🤝 Consensus caché"]

# ── Questions atomiques TypeSafe (Jev / System One) regroupées au même endroit ──
TYPESAFE_QUESTIONS: dict[str, dict[str, Any]] = {
    "ideology": {
        "type": "score",
        "instructions": "Quelle est l'orientation politique et socio-économique de la mesure décrite dans `title` et `description` ?",
        "criteria": [
            "Rupture anticapitaliste, expropriation, réquisition, abolition du profit privé ou collectivisation",
            "Gauche redistributive ou écologie interventionniste : hausse des salaires et prestations, taxation accrue du capital ou des hauts revenus, extension des services publics ou normes environnementales contraignantes",
            "Mesure technique, institutionnelle neutre, transpartisane ou équilibrant incitations économiques et régulation publique",
            "Droite libérale ou conservatrice : baisse des impôts et charges, réduction des dépenses publiques, flexibilité du travail, fermeté pénale ou régalienne",
            "Droite radicale ou identitaire : priorité nationale, restriction drastique de l'immigration et du droit du sol, remise en cause des traités européens",
        ],
    },
    "has_feasibility": {
        "type": "noul",
        "instructions": "Le texte dans `title` et `description` énonce-t-il une action publique suffisamment identifiable pour juger sa faisabilité juridique, institutionnelle ou budgétaire ?",
        "criteria": {
            "true": "La proposition décrit un dispositif législatif, réglementaire, constitutionnel, fiscal ou budgétaire identifiable",
            "false": "Le texte est un simple constat ou slogan trop vague pour identifier l'instrument d'action publique",
        },
    },
    "feasibility": {
        "type": "score",
        "instructions": "Quel est le degré de faisabilité juridique, constitutionnelle et budgétaire de la mesure dans `title` et `description` ?",
        "criteria": [
            "Obstacle majeur : exige une révision constitutionnelle lourde, une rupture des traités européens ou un financement massif sans mécanisme crédible",
            "Faisabilité faible : risque élevé de censure par le Conseil constitutionnel, conflit direct avec le droit européen ou coût majeur non financé",
            "Faisabilité moyenne : nécessite une loi ordinaire ou de finances d'ampleur avec arbitrage budgétaire ou négociation sociale complexe",
            "Faisabilité élevée : mesure législative ou budgétaire classique compatible avec la Constitution et les engagements européens",
            "Faisabilité immédiate : mesure réglementaire, décret, circulaire ou ajustement paramétrique directement applicable par l'exécutif",
        ],
    },
    "has_rights_income": {
        "type": "noul",
        "instructions": "La proposition dans `title` et `description` affecte-t-elle les revenus, prestations sociales, impôts des ménages ou l'accès financier à un droit ou service ?",
        "criteria": {
            "true": "La mesure modifie des salaires, pensions, allocations, impôts, tarifs ou conditions financières d'accès pour une catégorie de personnes ou l'ensemble de la population",
            "false": "La mesure porte uniquement sur l'organisation administrative, la diplomatie, les institutions ou la comptabilité des entreprises sans effet direct sur les droits ou revenus des ménages",
        },
    },
    "rights_income": {
        "type": "score",
        "instructions": "Quelle part de la population est concernée par l'effet de la mesure dans `title` et `description` sur les revenus ou l'accès financier, que cet effet soit favorable ou défavorable ?",
        "criteria": [
            "Micro-catégorie : une profession, un statut rare ou un petit groupe de personnes",
            "Catégorie ciblée sous conditions strictes de ressources, d'âge, de situation ou de profession",
            "Catégorie large de ménages, de salariés, de retraités, de locataires ou de contribuables",
            "Majorité des ménages ou des travailleurs",
            "Toute la population, sans condition de ressources ni de statut",
        ],
    },
    "income_direction": {
        "type": "score",
        "instructions": "Quel est le sens de l'effet de la mesure dans `title` et `description` sur les revenus ou l'accès financier des personnes concernées ?",
        "criteria": [
            "Baisse forte des revenus ou suppression d'un droit, d'une prestation ou d'un accès financier pour les personnes concernées",
            "Baisse modérée, condition d'accès plus stricte ou contribution supplémentaire demandée aux personnes concernées",
            "Effet financier neutre, mixte ou compensé pour les personnes concernées",
            "Hausse modérée d'un revenu, d'une prestation ou d'un accès financier",
            "Hausse forte de revenus ou création d'un nouveau droit financier",
        ],
    },
    "has_rights_status": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` ouvre-t-elle ou conditionne-t-elle l'accès à des droits, prestations, emplois ou services selon la nationalité, le titre de séjour, l'ancienneté de résidence ou le statut juridique des personnes ?",
        "criteria": {
            "true": "La mesure réserve, conditionne, étend ou universalise un droit selon la nationalité, le séjour, la résidence ou le statut juridique",
            "false": "La mesure s'applique de la même façon à tous, sans critère de nationalité, de séjour ou de statut",
        },
    },
    "rights_status": {
        "type": "score",
        "instructions": "Qui la mesure dans `title` et `description` inclut-elle ou exclut-elle de l'accès aux droits, parmi les personnes présentes sur le territoire ?",
        "criteria": [
            "Droits réservés aux nationaux : préférence nationale pour l'emploi, le logement ou les prestations, suppression de droits pour les étrangers",
            "Droits conditionnés plus strictement : titre de séjour, ancienneté de résidence ou de cotisation exigée, contreparties obligatoires",
            "Conditions d'accès inchangées ou ajustement technique",
            "Droits étendus à des personnes jusqu'ici exclues : étrangers résidents, personnes sans statut stable, nouveaux statuts",
            "Droits universels pour toute personne résidente, sans condition de nationalité ni de statut",
        ],
    },
    "has_eco": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` a-t-elle pour objet un choix de politique économique, ou un effet direct sur l'économie : niveau ou répartition des impôts et cotisations, redistribution des revenus ou du patrimoine, droit du travail, régulation des marchés ou de la concurrence, place de l'État ou du privé dans l'économie, niveau des services publics économiques et sociaux (santé, éducation, protection sociale, transports, logement) ? Le seul coût d'une mesure de sécurité, de justice, de défense, de culture ou d'organisation des institutions ne suffit pas : il relève de la faisabilité et de l'ordre de grandeur budgétaire (`cost_estimate`).",
    },
    "eco": {
        "type": "score",
        "instructions": "Quelle orientation économique traduit la mesure dans `title` et `description` ?",
        "criteria": [
            "Collectivisation : nationalisations larges, expropriation, réquisition ou abolition du profit privé",
            "Redistribution : taxation accrue du capital ou des hauts revenus, hausse des salaires ou prestations, extension des services publics, régulation renforcée des marchés",
            "Mesure mixte, équilibrant intervention publique et incitations de marché",
            "Baisse d'impôts ou de charges, réduction des dépenses publiques, flexibilité du travail ou allègement des réglementations",
            "Libéralisation radicale : privatisations massives, suppression d'impôts majeurs ou démantèlement de protections sociales",
        ],
    },
    "has_soc": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` touche-t-elle aux libertés individuelles, aux mœurs, à l'ordre public, à la justice pénale, à l'identité ou à la laïcité ?",
    },
    "soc": {
        "type": "score",
        "instructions": "Quelle orientation sociétale traduit la mesure dans `title` et `description` ?",
        "criteria": [
            "Extension forte des libertés et droits individuels : dépénalisation, nouveaux droits civils, garanties fortes face à l'État",
            "Libéralisme culturel modéré : lutte contre les discriminations, droits des minorités, justice tournée vers la réinsertion",
            "Ajustement équilibré ou technique sans orientation morale marquée",
            "Ordre et autorité renforcés : fermeté pénale, valeurs traditionnelles, contrôle accru",
            "Restriction forte des libertés individuelles au nom de l'ordre, de la norme ou de l'identité",
        ],
    },
    "has_sov": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` touche-t-elle au partage du pouvoir de décision entre la France et l'Union européenne ou les organisations internationales : traités, règles et politiques européennes, accords commerciaux, défense commune ?",
    },
    "sov": {
        "type": "score",
        "instructions": "À quel niveau la mesure dans `title` et `description` place-t-elle la décision : national, ou européen et international ?",
        "criteria": [
            "Intégration supranationale : transfert de compétences à l'Union européenne, fédéralisme, vote à la majorité, ouverture commerciale large",
            "Coopération européenne renforcée : politiques communes, préférence européenne, capacités européennes partagées",
            "Équilibre entre décision nationale et coopération européenne ou internationale",
            "Reprise d'autonomie nationale : dérogations aux règles européennes, refus d'accords commerciaux, protection commerciale nationale",
            "Rupture : sortie ou désobéissance aux traités, primauté du droit national sur le droit européen",
        ],
    },
    "has_ouverture": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` touche-t-elle aux flux de personnes et aux frontières : entrée et séjour des étrangers, asile, regroupement familial, naturalisation, droit du sol, contrôles aux frontières ?",
    },
    "ouverture": {
        "type": "score",
        "instructions": "Quelle position sur l'accueil des personnes étrangères traduit la mesure dans `title` et `description` ?",
        "criteria": [
            "Ouverture large : régularisations, accueil élargi, voies légales d'immigration, naturalisation facilitée",
            "Ouverture encadrée : intégration renforcée, accès facilité au séjour ou au travail pour certaines catégories",
            "Ajustement équilibré ou technique des règles d'entrée, de séjour ou d'asile",
            "Contrôle renforcé : durcissement du séjour, de l'asile, du regroupement familial ou de la naturalisation, expulsions facilitées",
            "Fermeture : arrêt de l'immigration, fin du droit du sol, fermeture des frontières, expulsions massives",
        ],
    },
    "has_ecolo": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` a-t-elle un effet identifiable sur l'environnement, le climat, l'énergie ou la biodiversité ?",
    },
    "ecolo": {
        "type": "score",
        "instructions": "Quelle priorité environnementale traduit la mesure dans `title` et `description` ?",
        "criteria": [
            "Priorité à la production contre l'environnement : suppression de normes environnementales, relance des énergies fossiles",
            "Allègement ou report de contraintes environnementales",
            "Effet environnemental neutre ou équilibré",
            "Renforcement de la protection de l'environnement par incitations, investissements ou normes",
            "Transition contraignante : interdictions, sobriété imposée, priorité absolue au climat et à la biodiversité",
        ],
    },
    "rupture": {
        "type": "score",
        "instructions": "Quelle est l'ampleur du changement que la mesure dans `title` et `description` introduit par rapport au droit et aux pratiques existants ?",
        "criteria": [
            "Statu quo, ajustement d'un paramètre ou prolongation d'un dispositif existant",
            "Extension ou modification modérée d'un dispositif existant",
            "Réforme significative d'un dispositif ou d'une politique publique",
            "Refonte structurelle, abrogation ou création d'une institution ou d'un système",
        ],
    },
    "legal_instrument": {
        "type": "choice",
        "instructions": "Quel est le texte juridique minimal nécessaire pour mettre en œuvre la mesure dans `title` et `description` ? La politique commerciale, la concurrence et la monnaie relèvent de l'Union européenne.",
        "criteria": {
            "decret_ou_arrete": "Décret, arrêté, circulaire ou décision de l'exécutif sans loi nouvelle",
            "loi_ordinaire": "Loi ordinaire votée par le Parlement",
            "loi_de_finances_ou_securite_sociale": "Loi de finances ou loi de financement de la sécurité sociale (impôts, taxes, crédits, cotisations)",
            "loi_organique": "Loi organique (fonctionnement des pouvoirs publics, statut des élus, lois de finances)",
            "revision_constitutionnelle": "Révision de la Constitution",
            "traite_europeen_ou_international": "Négociation ou modification d'un traité ou d'une règle européenne ou internationale",
            "non_identifiable": "Intention trop vague pour identifier un instrument juridique",
        },
    },
    "horizon": {
        "type": "choice",
        "instructions": "Dans quel délai la mesure dans `title` et `description` produirait-elle ses effets, d'après le texte ou de façon raisonnablement implicite ?",
        "criteria": {
            "immediat_moins_1_an": "Effet en moins d'un an",
            "mandat_1_a_5_ans": "Effet pendant le quinquennat, entre un et cinq ans",
            "long_terme_plus_5_ans": "Effet au-delà de cinq ans",
            "non_precise": "Délai impossible à déterminer",
        },
    },
    "cost_estimate": {
        "type": "choice",
        "instructions": "Quel ordre de grandeur de coût ou de gain budgétaire annuel net (État, collectivités et Sécurité sociale), en régime de croisière, implique la mesure dans `title` et `description` ? Estimation indicative fondée sur le dispositif décrit : montant cité, nombre de bénéficiaires, effectifs, comparaison avec des dispositifs connus. Ne pas attribuer le budget global du candidat à la mesure. Une hausse d'impôt ou une économie est un gain ; une dépense nouvelle ou une baisse d'impôt est un coût.",
        "criteria": {
            "sans_impact_notable": "Norme, interdiction, réorganisation ou mesure symbolique sans effet budgétaire notable",
            "cout_faible": "Coût net inférieur à 0,1 Md€ par an",
            "cout_modere": "Coût net de 0,1 à 1 Md€ par an",
            "cout_important": "Coût net de 1 à 10 Md€ par an",
            "cout_massif": "Coût net supérieur à 10 Md€ par an",
            "gain_faible": "Économie ou recette nette inférieure à 0,1 Md€ par an",
            "gain_modere": "Économie ou recette nette de 0,1 à 1 Md€ par an",
            "gain_important": "Économie ou recette nette de 1 à 10 Md€ par an",
            "gain_massif": "Économie ou recette nette supérieure à 10 Md€ par an",
            "indeterminable": "Dispositif trop vague pour estimer un ordre de grandeur",
        },
    },
    "programme_importance": {
        "type": "score",
        "instructions": "Quelle est l'importance de cette mesure dans le programme dont elle est tirée ? Appuie-toi sur les signaux structurels de `scoring_context.evidence` (élément de `source_kind` signal_structurel, champ `values` : position en % du document, section de synthèse ou de priorités, nombre de passages et de documents, formulations proches, propositions connexes sur le même sujet et poids du thème dans le programme) et sur la citation. Ni la précision, ni le coût, ni la seule position ne prouvent la mise en avant : combine plusieurs signaux. La mesure est jugée sans connaître le candidat. Ne pas déduire cette importance de la seule formulation.",
        "criteria": [
            "Mention secondaire ou ponctuelle, simple piste de réflexion isolée",
            "Proposition sectorielle ou prise de position générale dans une déclaration ou un entretien",
            "Engagement programmatique précis et structurant issu d'un document officiel ou d'un discours majeur",
            "Mesure phare, chiffrée ou emblématique au cœur du projet présidentiel du candidat",
        ],
    },
    "media_importance": {
        "type": "score",
        "instructions": "Quel est le degré de saillance médiatique de cette mesure précise d'après les reprises et entretiens datés fournis dans `scoring_context.evidence` ? Ne pas l'inférer de la seule notoriété du thème ou du candidat.",
        "criteria": [
            "Mesure très technique à faible résonance dans le débat grand public",
            "Sujet sectoriel débattu principalement par les acteurs professionnels concernés",
            "Proposition saillante régulièrement reprise dans les médias nationaux",
            "Mesure marqueur à très forte visibilité médiatique et politique nationale",
        ],
    },
    "budget_direction": {
        "type": "choice",
        "instructions": "Si un montant explicitement annuel est mentionné dans `cost`, `description` ou un extrait budgétaire rattaché à cette proposition, quel est le sens de cet impact sur le solde budgétaire public annuel ? Ne pas attribuer le budget global du candidat à cette mesure.",
        "criteria": {
            "net_cost": "Dépense publique nouvelle, investissement public ou baisse d'impôts/cotisations qui dégrade le solde public (coût net)",
            "net_saving_or_revenue": "Économie budgétaire, réduction de dépenses ou hausse de recettes fiscales/sociales qui améliore le solde public (gain net)",
            "not_annual_budget": "Aucun chiffrage budgétaire annuel de l'État ou simple indicateur non budgétaire (ex: niveau du SMIC, âge légal)",
        },
    },
    "tag_licorne": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` exige-t-elle une révision constitutionnelle ou une sortie des traités européens très difficile à réunir politiquement ?",
    },
    "tag_gouffre": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` entraîne-t-elle une dépense publique massive ou une perte de recettes de plusieurs dizaines de milliards d'euros par an sans financement précisé ?",
    },
    "tag_censure": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` présente-t-elle un risque élevé de censure par le Conseil constitutionnel (atteinte au droit de propriété sans indemnité, rupture d'égalité constitutionnelle ou atteinte aux droits fondamentaux) ?",
    },
    "tag_cible": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` vise-t-elle un secteur économique, une profession ou un sous-groupe très spécifique plutôt que l'ensemble de la population ?",
    },
    "tag_annonce": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` relève-t-elle d'une déclaration d'intention générale ou d'un slogan sans mécanisme opérationnel ni chiffrage précis ?",
    },
    "tag_consensus": {
        "type": "noul",
        "instructions": "La mesure dans `title` et `description` fait-elle l'objet d'un large consensus transpartisan entre gauche, centre et droite ?",
    },
}

TYPESAFE_TAG_KEYS = [
    ("tag_licorne", TAGS[0]),
    ("tag_gouffre", TAGS[1]),
    ("tag_censure", TAGS[2]),
    ("tag_cible", TAGS[3]),
    ("tag_annonce", TAGS[4]),
    ("tag_consensus", TAGS[5]),
]

# Questions non posées à Jev (doublons, décision du 2026-11-05) : l'idéologie est la moyenne des axes eco/soc/sov,
# l'importance programmatique vient du corpus, la saillance médiatique n'a pas de preuves, et trois tags sont déduits.
JEV_SKIPPED = frozenset({'ideology','programme_importance','media_importance','tag_licorne','tag_cible','tag_annonce'})
# Axes notés par Jev : (question, borne basse, borne haute, question d'applicabilité ou None).
JEV_AXES = (('eco',-100,100,'has_eco'),('soc',-100,100,'has_soc'),('sov',-100,100,'has_sov'),
            ('ouverture',-100,100,'has_ouverture'),('ecolo',-100,100,'has_ecolo'),('income_direction',-100,100,'has_rights_income'),('rupture',0,100,None))
JEV_CHOICE_AXES = ('legal_instrument','horizon','cost_estimate')
IDEOLOGY_COMPONENTS = ('eco','soc','ouverture','rights_status')  # sov (niveau de décision) n'est ni de gauche ni de droite
CIBLE_MAX_BREADTH = 15      # rights_income (ampleur) <= 15 : micro-catégorie
LICORNE_INSTRUMENTS = frozenset({'revision_constitutionnelle','traite_europeen_ou_international'})

JEV_MAX_QUESTIONS = 100

IDEOLOGY_RATIONALE=('Moyenne des axes applicables : économie, sociétal, ouverture et accès aux droits '
                    '(rights_status ramené à -100..100, droits réservés aux nationaux = +100).')

def ideology_component(proposal: dict[str,Any], key: str) -> int | None:
    """Composante gauche/droite signée (-100 gauche .. +100 droite)."""
    if key == 'rights_status':
        value=proposal.get('rights_status')
        return round((50-value)*2) if number(value) else None
    return (proposal.get('axes') or {}).get(key)

def jev_questions() -> dict[str,dict[str,Any]]:
    return {k:v for k,v in TYPESAFE_QUESTIONS.items() if k not in JEV_SKIPPED}

def derive_fields(proposal: dict[str,Any], tag_probabilities: dict[str,float | None] | None = None,
                  tag_threshold: float=0.7) -> dict[str,Any]:
    """Champs déduits des axes (format Jev à axes) : idéologie gauche/droite, tags déduits, importance.

    Rappelé après la révision pour que l'idéologie et les tags suivent les valeurs révisées.
    """
    axes=proposal.get('axes')
    if not isinstance(axes,dict):
        return proposal
    details=proposal.setdefault('score_details',{})
    parts=[(ideology_component(proposal,k),(details.get(k) or {}).get('confidence')) for k in IDEOLOGY_COMPONENTS]
    valid=[(v,c) for v,c in parts if number(v)]
    if valid:
        confs=[c for _,c in valid if number(c)]
        proposal['ideology']=round(sum(v for v,_ in valid)/len(valid))
        details['ideology']={'status':'derived','confidence':round(sum(confs)/len(confs),2) if confs else None,
                             'method':'axes-composite','components':{k:ideology_component(proposal,k) for k in IDEOLOGY_COMPONENTS},
                             'rationale':IDEOLOGY_RATIONALE}
    else:
        proposal['ideology']=None
        details['ideology']={'status':'derived','confidence':None,'method':'axes-composite',
                             'rationale':'Aucun axe gauche/droite ne s’applique (économie, sociétal, ouverture, accès aux droits).'}
    typesafe=proposal.setdefault('typesafe_details',{})
    probabilities=dict(tag_probabilities if tag_probabilities is not None else typesafe.get('tag_probabilities') or {})
    derived={
        TAGS[0]:axes.get('legal_instrument') in LICORNE_INSTRUMENTS,
        TAGS[3]:number(proposal.get('rights_income')) and proposal['rights_income'] <= CIBLE_MAX_BREADTH,
        TAGS[4]:proposal.get('precision') == 'orientation_generale',
    }
    for label,flag in derived.items():
        probabilities[label]=1.0 if flag else 0.0
    typesafe['tag_probabilities']=probabilities
    typesafe['derived_tags']={'licorne':'instrument juridique','cible':f'ampleur <= {CIBLE_MAX_BREADTH}',
                              'annonce':'precision = orientation_generale'}
    proposal['threshold_tags']=[label for label in TAGS if number(probabilities.get(label)) and probabilities[label] >= tag_threshold]
    update_importance(proposal)
    return proposal

AXIS_LABELS = {
    'eco':('Orientation économique','redistribution / collectivisation','libéralisation'),
    'soc':('Orientation sociétale','libertés individuelles','ordre et autorité'),
    'sov':('Niveau de décision','intégration européenne et internationale','décision nationale, sortie des traités'),
    'ouverture':('Accueil des personnes étrangères','ouverture large','fermeture'),
    'ecolo':('Priorité environnementale','production avant environnement','transition contraignante'),
    'income_direction':('Effet sur les revenus des personnes concernées','baisse ou restriction','hausse ou nouveau droit'),
    'rupture':('Ampleur du changement','statu quo','refonte structurelle'),
    'rights_income':('Ampleur des personnes concernées (effet financier)','micro-catégorie','toute la population'),
    'rights_status':('Accès aux droits selon la nationalité ou le statut','réservé aux nationaux','universel pour les résidents'),
    'feasibility':('Faisabilité juridique et budgétaire','obstacle majeur','applicable immédiatement'),
    'legal_instrument':('Instrument juridique minimal',None,None),
    'horizon':('Horizon d’effet (indicatif)',None,None),
    'cost_estimate':('Ordre de grandeur budgétaire (estimé, indicatif)',None,None),
}

def dimensions_schema() -> dict[str,Any]:
    """Description des dimensions stockées, pour l'interface : chemin du champ, bornes, niveaux, règles de calcul.

    Les axes sont stockés bruts ; l'idéologie et les tags déduits sont des valeurs par défaut que l'affichage peut
    recalculer avec ses propres pondérations (moyenne sur les seuls axes non nuls).
    """
    out: dict[str,Any]={}
    for dim,(label,low,high) in AXIS_LABELS.items():
        q=TYPESAFE_QUESTIONS[dim]
        path=f'axes.{dim}' if dim in AXES_DIMENSIONS else dim
        entry: dict[str,Any]={'label':label,'field':path,'question':q['instructions']}
        if q['type'] == 'choice':
            entry.update(type='category',options=q['criteria'])
        else:
            lo,hi=AXES_DIMENSIONS.get(dim) or DIMENSIONS[dim]
            levels=q['criteria']
            entry.update(type='scale',range=[lo,hi],low_label=low,high_label=high,
                         anchors={str(round(lo+i*(hi-lo)/(len(levels)-1))):lvl for i,lvl in enumerate(levels)})
        gate={'feasibility':'has_feasibility','rights_income':'has_rights_income','rights_status':'has_rights_status',
              'income_direction':'has_rights_income','eco':'has_eco','soc':'has_soc','sov':'has_sov','ouverture':'has_ouverture',
              'ecolo':'has_ecolo'}.get(dim)
        if gate:
            entry['null_means']='non applicable : '+TYPESAFE_QUESTIONS[gate]['instructions']
        out[dim]=entry
    out['ideology']={'label':'Gauche / droite (valeur par défaut)','field':'ideology','type':'derived','range':[-100,100],
                     'formula':'moyenne à poids égaux des composantes non nulles ; rights_status signé = (50 - rights_status) x 2',
                     'components':list(IDEOLOGY_COMPONENTS),
                     'not_left_right':['sov','ecolo','rupture','income_direction'],
                     'suggested_compass':{'x':{'label':'Économie','components':['eco']},
                                          'y':{'label':'Culturel (sociétal, ouverture, accès aux droits)',
                                               'components':['soc','ouverture','rights_status']}},
                     'suggested_candidate_weights':{'eco':1/3,'culturel':2/3},
                     'aggregation_note':'Par candidat : moyenne de chaque axe sur ses propositions applicables, puis pondération des axes.'}
    out['importance']={'label':'Importance','field':'importance','type':'derived','range':[0,100],
                       'formula':'moyenne pondérée des composantes non nulles de importance_sources (programme .5, media .25, votes .25)',
                       'components':{'programme':'composite structurel du corpus (position, poids du thème, répétition)',
                                     'media':'saillance médiatique (non mesurée : null)','votes':'cohérence des votes (saisie manuelle)'}}
    out['budget_net_bn_year']={'label':'Solde budgétaire annuel (Md€/an)','field':'budget_net_bn_year','type':'scale',
                               'range':[None,None],'note':'uniquement si un montant explicitement annuel est cité ; coût négatif'}
    out['cost_estimate']['note']=('Estimation d’ordre de grandeur, jamais un montant publié : ne pas l’additionner au solde '
                                  '(ticket de caisse : « non chiffré, ordre de grandeur estimé »). indeterminable ≠ zéro.')
    out['precision_llm']={'label':'Précision de la proposition','field':'precision_llm','type':'scale','range':[0,100],
                          'categories_field':'precision'}
    out['threshold_tags']={'label':'Signaux','field':'threshold_tags','type':'tags','options':TAGS,
                           'derived':{'licorne':'instrument constitutionnel ou traité','cible':f'rights_income <= {CIBLE_MAX_BREADTH}',
                                      'annonce':'precision = orientation_generale'}}
    out['_interface']={'user_selects_axes':True,
                       'selectable_axes':[k for k,v in out.items() if v.get('type') in {'scale','derived','category'}],
                       'note':'L’utilisateur choisit les axes affichés (X, Y, taille, couleur) et les poids des composites ; '
                              'afficher les effectifs (n) par candidat et par axe, faibles sur ouverture, sociétal et accès aux droits.'}
    out['_per_dimension_details']=('score_details.<dimension> : status, confidence (Jev calibrée), method '
                                   '(jev-calibrated | revision-chat | corpus-structure | axes-composite), jev_value et '
                                   'disagreement si révisé ; revision.note : note d’audit de la seconde lecture.')
    return out

def scoring_rubric() -> dict[str,Any]:
    result: dict[str,Any]={}
    for dimension,(lo,hi) in DIMENSIONS.items():
        question=TYPESAFE_QUESTIONS.get(dimension,TYPESAFE_QUESTIONS['budget_direction'])
        criteria=question.get('criteria',[])
        result[dimension]={'instructions':question['instructions'],'range':[lo,hi],'criteria':criteria}
        if isinstance(criteria,list):
            result[dimension]['anchors']=[
                {'score':round(lo+i*(hi-lo)/max(len(criteria)-1,1)),'meaning':label}
                for i,label in enumerate(criteria)]
    return result

def load_env_file(path: Path) -> None:
    """Charge une configuration locale littérale, sans remplacer l'environnement existant."""
    if not path.exists():
        return
    allowed={'LLM_PROVIDER','LLM_API_BASE_URL','LLM_MODEL','TYPESAFE_API_KEY',
             'LLM_API_KEY','OPENROUTER_API_KEY','OPENROUTER_MODEL',
             'OPENROUTER_SCORING_MODEL','OPENROUTER_WEB_MODEL'}
    values: dict[str,str]={}
    for line_number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):
            continue
        match=re.fullmatch(r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
        if not match:
            raise ValueError(f'Configuration {path.name}, ligne {line_number}: format NOM=valeur attendu.')
        key,value=match.groups()
        if key not in allowed or key in values:
            raise ValueError(f'Configuration {path.name}, ligne {line_number}: variable inconnue ou dupliquée.')
        value=value.strip()
        if value.startswith(("'",'"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'Configuration {path.name}, ligne {line_number}: guillemets non fermés.')
            value=value[1:-1]
        values[key]=value
    for key,value in values.items():
        os.environ.setdefault(key,value)

class TextExtractor(html.parser.HTMLParser):
    """Extraction rudimentaire de texte et de liens depuis les pages de campagne."""
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self._href=None
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag == 'a' and attrs.get('href'): self._href=attrs['href']
    def handle_endtag(self, tag):
        if tag == 'a': self._href=None
    def handle_data(self, data):
        text=' '.join(data.split())
        if text:
            self.parts.append(text)
            if self._href: self.links.append((text,self._href))

def fetch_html(url: str, timeout: int=20) -> str:
    req=urllib.request.Request(url, headers={'User-Agent':'Boussole2027-prototype/0.1 (research; contact the site owner)'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset=response.headers.get_content_charset() or 'utf-8'
        return response.read().decode(charset, errors='replace')

def inspect_site(url: str) -> dict[str,Any]:
    """Inventorie titre, descriptions, liens, scripts et JSON-LD; pas de scraping agressif."""
    source=fetch_html(url); parser=TextExtractor(); parser.feed(source)
    title=re.search(r'<title[^>]*>(.*?)</title>',source,re.I|re.S)
    descriptions=re.findall(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',source,re.I)
    scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)',source,re.I)
    return {'url':url,'title':re.sub(r'\s+',' ',title.group(1)).strip() if title else None,
            'descriptions':descriptions,'scripts':scripts,'links':[{'label':a,'href':b} for a,b in parser.links],
            'text_excerpt':' '.join(parser.parts)[:1800], 'note':'HTML inspecté au moment de la requête; les pages dynamiques peuvent nécessiter un connecteur dédié.'}

def download_source_json(destination: Path, url: str=SOURCE_JSON_DOWNLOAD_URL) -> Path:
    """Télécharge une copie locale de data-v2.json vers le chemin demandé."""
    req=urllib.request.Request(url,headers={'User-Agent':'Boussole2027-prototype/0.1','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as res:
        payload=res.read()
    # Contrôle élémentaire avant d’écrire le fichier téléchargé.
    obj=json.loads(payload.decode('utf-8'))
    if not isinstance(obj,dict): raise ValueError('La source téléchargée ne contient pas un objet JSON.')
    destination.write_bytes(payload)
    return destination

def adapt_v2_bundle(obj: dict[str,Any]) -> dict[str,Any]:
    """Map the repository's actual public-data v2 bundle without inventing scoring values."""
    if not (isinstance(obj.get('candidates'),list) and isinstance(obj.get('measures'),dict)):
        raise ValueError('Le bundle v2 doit contenir candidates[] et measures{}.')
    theme_records = {str(t.get('id')): t for t in obj.get('themes',[]) if isinstance(t,dict)}
    candidates=[]
    for c in obj['candidates']:
        if not isinstance(c,dict): continue
        name=' '.join(x for x in (c.get('first_name'),c.get('last_name')) if x).strip()
        photo=c.get('photo') if isinstance(c.get('photo'),dict) else None
        candidates.append({
            'id':c.get('id'),'name':name or c.get('id','Inconnu'),'intentions_vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'first_name':c.get('first_name'),
            'last_name':c.get('last_name'),'movement':c.get('party','Non renseigné'),'party_short':c.get('party_short'),
            'color':c.get('color') or '#657b73','position':c.get('position'),'status':c.get('status'),
            'initials':''.join(part[:1] for part in name.split()[:3]).upper() or '??',
            'photo':photo,'photo_url':photo.get('url') if photo else None,
            'photo_author':photo.get('author') if photo else None,'photo_license':photo.get('license') if photo else None,
            'photo_commons_page':photo.get('commons_page') if photo else None,
            'program':c.get('program'),'main_axes':c.get('main_axes',[]),
            'main_axes_source_url':c.get('main_axes_source_url'),'source_url':c.get('position_source_url')
        })
    proposals=[]
    for cid, rows in obj['measures'].items():
        for row in rows if isinstance(rows,list) else []:
            if not isinstance(row,dict): continue
            tid=row.get('theme'); tr=theme_records.get(str(tid),{})
            proposal=dict(row)
            proposal.update({'candidate_id':cid,'theme_id':tid,'theme':tr.get('label') or THEME_LABELS.get(str(tid),str(tid or 'Non classé')),
                'theme_icon':tr.get('icon'),'importance':None,'importance_sources':{'programme':None,'media':None,'votes':None},
                'ideology':None,'feasibility':None,'rights_income':None,'rights_status':None,'budget_net_bn_year':None,
                'threshold_tags':[],'source_note':'Donnée d’origine du comparateur, sans score calculé par ce pipeline.'})
            proposals.append(proposal)
    return {'meta':{**obj.get('meta',{}),'source_generated_at':obj.get('generated_at'),'source_version':obj.get('version'),
        'repository':'https://github.com/coucou123212321232123/presidentielle-2027-comparateur',
        'adapter_note':'Bundle v2: scores absents laissés à null.'},'candidates':candidates,'proposals':proposals,
        'themes':obj.get('themes',[]),'context':obj.get('context',{}),'budgets':obj.get('budgets',{}),
        '_source_format':'presidentielle-2027-comparateur/public-data/data-v2.json',
        '_source_generated_at':obj.get('generated_at')}

def scoring_fingerprint(proposal: dict[str,Any]) -> str:
    return content_hash(proposal)

def content_hash(proposal: dict[str,Any]) -> str:
    """SHA-256 fingerprint of the proposal evidence that drives scoring."""
    relevant={k:v for k,v in proposal.items() if k not in {'importance','importance_sources','ideology','feasibility',
        'rights_income','rights_status','budget_net_bn_year','threshold_tags','source_note','confidence','rationale',
        'typesafe_details','score_details','web_review','scoring_fingerprint','content_hash','llm_scored_at','pipeline',
        'axes','revision','selection'}}  # selection : marqueur d'affichage, sans effet sur le scoring
    relevant['documented_votes']=(proposal.get('importance_sources') or {}).get('votes')
    raw=json.dumps(relevant,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def cached_scored_rows(path: Path) -> dict[str,dict[str,Any]]:
    """Read differential cache records, keyed by proposal ID and validated by content_hash."""
    if not path.exists():
        return {}
    try:
        prior=json.loads(path.read_text(encoding='utf-8'))
        entries=prior.get('measures') if isinstance(prior,dict) else None
        if isinstance(entries,dict) and all(isinstance(v,dict) and isinstance(v.get('content_hash'),str) and isinstance(v.get('scored'),dict) for v in entries.values()):
            return entries
    except (OSError,ValueError,TypeError) as exc:
        raise ValueError(f'Cache de scores illisible: {path} ({exc})') from exc
    raise ValueError(f'Cache de scores invalide: {path}')

def save_scored_cache(path: Path, entries: dict[str,dict[str,Any]]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    payload={'version':1,'hash_algorithm':'sha256','measures':entries}
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def ingest_json(path: Path) -> dict[str,Any]:
    obj=json.loads(path.read_text(encoding='utf-8'))
    if isinstance(obj,dict) and isinstance(obj.get('measures'),dict) and obj.get('version') == 2:
        return adapt_v2_bundle(obj)
    if 'example_dataset' in obj: obj=obj['example_dataset']
    elif isinstance(obj.get('examples'),list) and obj['examples']: obj=obj['examples'][0]
    if isinstance(obj,dict) and isinstance(obj.get('candidates'),list) and isinstance(obj.get('measures'),dict):
        candidates=[]
        for c in obj['candidates']:
            if not isinstance(c,dict): continue
            name=' '.join(x for x in (c.get('first_name'),c.get('last_name')) if x)
            candidates.append({'id':c.get('id'),'name':name or c.get('id','Inconnu'),'movement':c.get('party','Non renseigné'),'color':c.get('color') or '#657b73','camp':None,'intentions_vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'initials':''.join(part[:1] for part in name.split()[:3]).upper() or '??','source_url':c.get('position_source_url'),'status':c.get('status')})
        proposals=[]
        for cid, rows in obj['measures'].items():
            for row in rows if isinstance(rows,list) else []:
                if isinstance(row,dict):
                    proposals.append({'id':row.get('id'),'title':row.get('title'),'theme':THEMES.get(re.sub(r'[^a-z]','',str(row.get('theme','')).lower()),'Institutions'),'candidate_id':cid,'importance_sources':{'programme':None,'media':None,'votes':None},'threshold_tags':[],'source_note':'Source originale conservée; scores non évalués. '+str(row.get('source_title') or ''),'source_url':row.get('source_url'),'source_type':row.get('source_type'),'source_date':row.get('source_date'),'description':row.get('description')})
        obj={'meta':{**obj.get('meta',{}),'source_generated_at':obj.get('generated_at')},'candidates':candidates,'proposals':proposals}
    if not isinstance(obj,dict) or not isinstance(obj.get('candidates'),list) or not isinstance(obj.get('proposals'),list):
        raise ValueError('Le JSON doit comporter candidates[] et proposals[] (ou example_dataset).')
    return obj

def ingest_url(url: str) -> dict[str,Any]:
    """Lit un endpoint JSON public explicitement fourni; ne devine pas d'API."""
    req=urllib.request.Request(url,headers={'User-Agent':'Boussole2027-prototype/0.1','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as res: obj=json.loads(res.read().decode('utf-8'))
    if not isinstance(obj,dict): raise ValueError('La source URL doit fournir un objet JSON.')
    # Format de production du dépôt comparateur 2027 : thèmes/candidats/mesures/sources.
    if isinstance(obj.get('measures'),dict) and obj.get('version') == 2:
        return adapt_v2_bundle(obj)
    if isinstance(obj.get('example_dataset'),dict): obj=obj['example_dataset']
    if isinstance(obj.get('candidates'),list) and isinstance(obj.get('proposals'),list): return obj
    if isinstance(obj.get('candidates'),list) and isinstance(obj.get('measures'),dict):
        # Explicit mapping for the observed public data-v2 bundle. Unknown quantitative
        # fields remain null: do not infer ideology, feasibility, cost, or vote intent.
        mapped=[]
        for c in obj['candidates']:
            if not isinstance(c,dict): continue
            name=' '.join(x for x in (c.get('first_name'),c.get('last_name')) if x)
            mapped.append({'id':c.get('id'),'name':name or c.get('id','Inconnu'),'movement':c.get('party','Non renseigné'),'color':c.get('color') or '#657b73','camp':None,'intentions_vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'vote_pct':c.get('intentions_vote_pct',c.get('vote_pct')),'initials':''.join((part[:1] for part in name.split()[:3])).upper() or '??','source_url':c.get('position_source_url'),'status':c.get('status')})
        measures=[]
        for cid, rows in obj['measures'].items():
            for row in (rows if isinstance(rows,list) else []):
                if not isinstance(row,dict): continue
                theme=THEMES.get(re.sub(r'[^a-z]','',str(row.get('theme','')).lower()),'Institutions')
                measures.append({'id':row.get('id'),'title':row.get('title'),'theme':theme,'candidate_id':cid,
                  'ideology':None,'importance':None,'importance_sources':{'programme':None,'media':None,'votes':None},
                  'feasibility':None,'rights_income':None,'rights_status':None,'budget_net_bn_year':None,
                  'threshold_tags':[],'source_note':'Source originale conservée; scores non évalués. '+str(row.get('source_title') or ''),
                  'source_url':row.get('source_url'),'source_type':row.get('source_type'),'source_date':row.get('source_date'),'description':row.get('description')})
        return {'meta':{**obj.get('meta',{}),'source_generated_at':obj.get('generated_at'),'adapter_note':'Mapped from public data-v2; unsupported scores intentionally left null.'},'candidates':mapped,'proposals':measures,'_source_format':'programmes-2027.fr public data-v2'}
    if isinstance(obj.get('candidates'),list) and isinstance(obj.get('proposals'),list): return obj
    raise ValueError('Format JSON non reconnu. Ajoutez un adaptateur de source auditable.')

def apply_overrides(data: dict[str,Any], path: Path) -> dict[str,Any]:
    """Apply documented, sourceable poll and Assembly-vote inputs from a local JSON file."""
    overrides=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(overrides,dict): raise ValueError('--overrides doit contenir un objet JSON.')
    candidates={str(c.get('id')):c for c in data.get('candidates',[]) if c.get('id') is not None}
    proposals={str(p.get('id')):p for p in data.get('proposals',[]) if p.get('id') is not None}
    for cid, values in overrides.get('candidates',{}).items():
        if cid not in candidates: raise ValueError(f'Identifiant candidat inconnu dans --overrides: {cid}')
        if not isinstance(values,dict): raise ValueError(f'Override candidat {cid} doit être un objet.')
        value=values.get('intentions_vote_pct',values.get('vote_pct'))
        if value is not None:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=100: raise ValueError(f'intentions_vote_pct de {cid} doit être un nombre de 0 à 100.')
            candidates[cid]['intentions_vote_pct']=value; candidates[cid]['vote_pct']=value
    for pid, values in overrides.get('proposals',{}).items():
        if pid not in proposals: raise ValueError(f'Identifiant proposition inconnu dans --overrides: {pid}')
        if not isinstance(values,dict): raise ValueError(f'Override proposition {pid} doit être un objet.')
        scores=values.get('importance_sources',{})
        if not isinstance(scores,dict): raise ValueError(f'importance_sources de {pid} doit être un objet.')
        if 'votes' in scores:
            value=scores['votes']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=100: raise ValueError(f'importance_sources.votes de {pid} doit être un nombre de 0 à 100.')
            current=proposals[pid].get('importance_sources')
            if not isinstance(current,dict): current={}
            proposals[pid]['importance_sources']={**current,'votes':value}
    data.setdefault('meta',{})['manual_overrides_file']=path.name
    data['meta']['manual_overrides_note']='Valeurs saisies manuellement; vérifier et documenter les sources de sondage/votes avant publication.'
    return data

def apply_selection(data: dict[str,Any], path: Path) -> dict[str,Any]:
    """Filtre les propositions sur une sélection et y joint la précision (label et note LLM), dans l'ordre d'entrée."""
    selected={str(s['id']):s for s in json.loads(path.read_text(encoding='utf-8'))['selected']}
    proposals=[{**p,**{k:selected[str(p.get('id'))][k] for k in ('precision','precision_llm','selection') if k in selected[str(p.get('id'))]}}
               for p in data['proposals'] if str(p.get('id')) in selected]
    missing=len(selected)-len(proposals)
    if missing:
        raise ValueError(f'Sélection {path}: {missing} identifiant(s) absent(s) des propositions d’entrée.')
    return {**data,'proposals':proposals}

def norm_text(s: str) -> str: return re.sub(r'\s+',' ',str(s or '')).strip()
def heuristic_score(p: dict[str,Any]) -> dict[str,Any]:
    """Met à l'échelle les scores déjà documentés, sans inférer d'affirmations politiques."""
    q=dict(p); refs=q.get('importance_sources') or {}
    if all(isinstance(refs.get(k),(int,float)) for k in ('programme','media','votes')):
        q['importance']=round(sum(refs[k]*w for k,w in zip(('programme','media','votes'),(.5,.25,.25))))
    else:
        q.setdefault('importance',None)
    if q.get('theme') not in set(THEMES.values()):
        key=re.sub(r'[^a-z]','',norm_text(q.get('theme','')).lower())
        q['theme']=THEMES.get(key,q.get('theme','Institutions'))
    q['title']=norm_text(q.get('title') or q.get('text') or q.get('measure') or 'Proposition à qualifier')
    q.setdefault('threshold_tags',[]); q.setdefault('source_note','Source à vérifier et renseigner.')
    q.setdefault('ideology',None); q.setdefault('importance_sources',{'programme':None,'media':None,'votes':None})
    q.setdefault('feasibility',None); q.setdefault('rights_income',None); q.setdefault('rights_status',None)
    q.setdefault('budget_net_bn_year',None)
    # Keeps unknown data null: no fabricated cost, feasibility or rights estimates.
    return q

def extract_explicit_budget_bn(proposal: dict[str,Any]) -> float | None:
    """Extrait uniquement un montant explicitement exprimé en milliards d'euros dans `cost.label` ou `description`."""
    cost_obj=proposal.get('cost')
    texts: list[str]=[]
    if isinstance(cost_obj,dict) and cost_obj.get('label'):
        texts.append(str(cost_obj['label']))
    elif isinstance(cost_obj,str):
        texts.append(cost_obj)
    if proposal.get('description'):
        texts.append(str(proposal['description']))
    for item in (proposal.get('scoring_context') or {}).get('evidence',[]):
        if proposal.get('id') is not None and item.get('proposal_id') == proposal['id'] and 'budget_net_bn_year' in item.get('dimensions',[]):
            texts.append(item['text'])
    pattern=re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:Md€|milliards?\s+d[\'’]euros?|Md\s*€)'
                       r'\s*(?:/an\b|par an\b|annuels?\b|chaque année\b)',re.I)
    for t in texts:
        m=pattern.search(t)
        if m:
            try:
                return float(m.group(1).replace(',','.'))
            except ValueError:
                pass
    return None

def _build_decisions_questions(prefix: str='', item_ref: str='') -> list[dict[str,Any]]:
    """Convertit TYPESAFE_QUESTIONS au format `/v1/decisions` (avec préfixe optionnel pour le batching)."""
    out: list[dict[str,Any]]=[]
    scope_prefix=f"Concernant uniquement la proposition `{item_ref}` : " if item_ref else ""
    for name, q in jev_questions().items():
        qname=f"{prefix}{name}" if prefix else name
        qtype=q['type']
        instructions=scope_prefix + q['instructions'] + " Respecte `scoring_context.rules` et les sources datées du contexte pertinent."
        criteria=q.get('criteria')
        if qtype == 'noul':
            if isinstance(criteria,dict) and criteria.get('true') and criteria.get('false'):
                instructions=f"{instructions} (Oui: {criteria['true']}. Non: {criteria['false']}.)"
            out.append({'name':qname,'type':'predicate','instructions':instructions})
        elif qtype == 'score':
            levels=[{'label':str(lvl)} for lvl in (criteria or [])]
            out.append({'name':qname,'type':'score','instructions':instructions,'levels':levels})
        elif qtype == 'choice':
            choices=[{'value':str(k),'label':str(v)} for k,v in (criteria or {}).items()]
            out.append({'name':qname,'type':'choice','instructions':instructions,'choices':choices})
    return out

def _parse_jev_proposal_answers(proposal: dict[str,Any], answers: dict[str,dict[str,Any]], model_name: str,
                                noul_gate: float=0.4, tag_threshold: float=0.7) -> dict[str,Any]:
    """Applique les réponses calibrées Jev d'une proposition aux champs cibles du schéma."""
    if not isinstance(answers,dict) or any(not isinstance(answer,dict) for answer in answers.values()):
        raise ValueError('Réponses Jev invalides: objets attendus.')
    def confidence_of(ans: dict[str,Any]) -> float | None:
        value=ans.get('confidence')
        if value is None:
            return None
        if not number(value) or not 0 <= value <= 1:
            raise ValueError('Confiance Jev hors plage.')
        return float(value)

    def score_scaled(qid: str, lo: float, hi: float) -> tuple[int | None, float | None, str]:
        ans=answers.get(qid) or {}
        raw_score=ans.get('score')
        if raw_score is None:
            return None, None, 'Réponse Jev absente'
        criteria=TYPESAFE_QUESTIONS[qid]['criteria']
        top_idx=max(len(criteria)-1,1)
        if not number(raw_score) or not 0 <= raw_score <= top_idx:
            raise ValueError(f'Score Jev hors plage: {qid}')
        conf=confidence_of(ans)
        norm=raw_score/top_idx
        scaled=round(lo+norm*(hi-lo))
        best_lvl=round(raw_score)
        return scaled, conf, str(criteria[best_lvl])

    def noul_val(qid: str) -> float | None:
        ans=answers.get(qid) or {}
        value=ans.get('probability',ans.get('noul'))
        if value is None:
            return None
        if not number(value) or not 0 <= value <= 1:
            raise ValueError(f'Probabilité Jev hors plage: {qid}')
        return float(value)

    # Format à axes (questions de jev_questions()) ou ancien format (idéologie unique, importances, 6 tags) : le cache
    # historique et les réponses anciennes restent lisibles.
    axes_format=any(k in answers for k in ('has_eco','eco','legal_instrument','horizon','rupture'))
    status_labels={'missing_answer':'Réponse Jev absente','missing_applicability':'Évaluabilité non renseignée',
                   'insufficient_evidence':'Preuves insuffisantes dans le contexte fourni',
                   'not_applicable':'Dimension jugée non applicable par Jev'}
    details: dict[str,dict[str,Any]]={}
    values: dict[str,Any]={}

    def gated_score(qid: str, lo: float, hi: float, gate_id: str | None) -> None:
        value,conf,label=score_scaled(qid,lo,hi)
        status='scored' if value is not None else 'missing_answer'
        if gate_id:
            probability=noul_val(gate_id)
            if probability is None:
                value,conf,status=None,None,'missing_applicability'
            elif probability < noul_gate:
                value,conf=None,1-probability
                status='insufficient_evidence' if qid == 'feasibility' else 'not_applicable'
            elif conf is not None:
                conf=min(conf,probability)
        if qid in {'programme_importance','media_importance'} and not importance_evidence(proposal,qid):
            value,conf,status=None,None,'insufficient_evidence'
        values[qid]=value
        details[qid]={'status':status,'confidence':conf,'method':'jev-calibrated','model':model_name,
                      'rationale':label if status == 'scored' else status_labels[status]}

    gates={'feasibility':'has_feasibility','rights_income':'has_rights_income','rights_status':'has_rights_status'}
    for qid,lo,hi in (
        ('ideology',-100,100),('feasibility',0,100),('rights_income',0,100),
        ('rights_status',0,100),('programme_importance',0,100),('media_importance',0,100)
    ):
        if axes_format and qid in JEV_SKIPPED:
            continue
        gated_score(qid,lo,hi,gates.get(qid))
    axes: dict[str,Any]={}
    if axes_format:
        values.update(ideology=None,programme_importance=None,media_importance=None)
        details['programme_importance']={'status':'not_requested','confidence':None,'method':'corpus-structure',
                                         'model':None,'rationale':'Non demandé à Jev : composite structurel du corpus.'}
        details['media_importance']={'status':'not_requested','confidence':None,'method':None,'model':None,
                                     'rationale':'Non demandé : aucune preuve médiatique datée fournie.'}
        for qid,lo,hi,gate_id in JEV_AXES:
            gated_score(qid,lo,hi,gate_id)
            axes[qid]=values.pop(qid)
        for qid in JEV_CHOICE_AXES:
            ans=answers.get(qid) or {}
            options=TYPESAFE_QUESTIONS[qid]['criteria']
            choice=ans.get('choice')
            if choice is not None and choice not in options:
                raise ValueError(f'Choix Jev inconnu: {qid}')
            axes[qid]=choice
            details[qid]={'status':'scored' if choice is not None else 'missing_answer',
                          'confidence':confidence_of(ans) if choice is not None else None,
                          'method':'jev-calibrated','model':model_name,
                          'rationale':options[choice] if choice is not None else status_labels['missing_answer'],
                          'probabilities':ans.get('probabilities')}

    explicit_bn=extract_explicit_budget_bn(proposal)
    budget_answer=answers.get('budget_direction') or {}
    budget_choice=budget_answer.get('choice')
    if explicit_bn is not None and budget_choice == 'net_cost':
        budget_net_bn_year=-abs(explicit_bn)
    elif explicit_bn is not None and budget_choice == 'net_saving_or_revenue':
        budget_net_bn_year=abs(explicit_bn)
    else:
        budget_net_bn_year=None
    budget_status='scored' if budget_net_bn_year is not None else (
        'no_annual_amount' if axes_format and explicit_bn is None else 'insufficient_evidence')
    details['budget_net_bn_year']={
        'status':budget_status,
        'confidence':confidence_of(budget_answer) if budget_net_bn_year is not None else None,
        'method':'jev-direction-explicit-amount','model':model_name,
    }
    tag_probabilities={label:noul_val(qid) for qid,label in TYPESAFE_TAG_KEYS if not (axes_format and qid in JEV_SKIPPED)}
    tags=[label for label,prob in tag_probabilities.items() if prob is not None and prob >= tag_threshold]
    evaluability_keys=('feasibility','rights_income','rights_status')+(('eco','soc','sov','ouverture','ecolo') if axes_format else ())

    scored={
        **{k:values[k] for k in ('ideology','feasibility','rights_income','rights_status')},
        'budget_net_bn_year':budget_net_bn_year,
        'importance_sources':{'programme':values['programme_importance'],'media':values['media_importance'],
                              'votes':(proposal.get('importance_sources') or {}).get('votes')},
        'threshold_tags':tags,
        'score_details':details,
        'typesafe_details':{
            'model':model_name,
            'evaluability':{qid:noul_val('has_'+qid) for qid in evaluability_keys},
            'tag_probabilities':tag_probabilities,
        },
    }
    result={**proposal,**scored}
    if axes_format:
        result['axes']=axes
        derive_fields(result,tag_probabilities,tag_threshold)
    conf_values=[d['confidence'] for d in details.values() if d['status'] == 'scored' and d['confidence'] is not None]
    avg_confidence=round(sum(conf_values)/len(conf_values),2) if conf_values else None
    src_title=proposal.get('source_title') or proposal.get('source_type') or 'Source non précisée'
    result['source_note']=f"Pré-évaluation Jev ({model_name}) sur source « {src_title} » et contexte daté (confiance moy. {avg_confidence})."
    result['confidence']=avg_confidence
    result['rationale']=f"Idéologie: {details['ideology']['rationale']}. Faisabilité: {details['feasibility']['rationale']}."
    update_importance(result)
    return apply_structural_importance(result)

def apply_structural_importance(result: dict[str,Any]) -> dict[str,Any]:
    """Importance programmatique = composite structurel du corpus (décision du 2026-11-05), reproductible et sans LLM.

    La note du modèle est conservée dans score_details pour comparaison ; sans signal structurel, elle reste en place.
    """
    for item in (result.get('scoring_context') or {}).get('evidence',[]):
        if not isinstance(item,dict) or item.get('source_kind') != 'signal_structurel':
            continue
        structural=(item.get('values') or {}).get('importance_structurelle') or {}
        if not number(structural.get('score')):
            continue
        sources=dict(result.get('importance_sources') or {})
        details=dict(result.get('score_details') or {})
        previous=details.get('programme_importance') or {}
        details['programme_importance']={
            'status':'scored','confidence':1.0,'method':'corpus-structure','model':None,
            'rationale':'Composite structurel : position {position}, thème {theme}, répétition {repetition}.'.format(
                **{k:structural.get(k) for k in ('position','theme','repetition')}),
            'components':{k:structural.get(k) for k in ('position','theme','repetition')},
            'model_value':sources.get('programme'),'model_status':previous.get('status'),
            'model_confidence':previous.get('confidence'),
        }
        sources['programme']=structural['score']
        result['importance_sources']=sources
        result['score_details']=details
        update_importance(result)
        break
    return result

def is_openrouter_jev_model(model: str) -> bool:
    return bool(re.fullmatch(r'~?typesafe/jev-(?:latest|\d[\w.-]*)',model))

def _jev_api_settings(endpoint: str, model: str) -> tuple[str,str,bool]:
    base=endpoint.rstrip('/')
    parsed=urlparse(base)
    host=parsed.hostname or ''
    if host == 'openrouter.ai' or host.endswith('.openrouter.ai'):
        effective_model=model
        if model in {'jev','jev-latest',''}:
            effective_model='~typesafe/jev-latest'
        elif model.startswith('jev-'):
            effective_model='typesafe/'+model
        url=parsed._replace(path='/api/alpha/decisions',query='',fragment='').geturl()
        return url,effective_model,True
    native=host == 'typesafe.ai' or host.endswith('.typesafe.ai') or base.endswith('/systemone')
    suffix='/systemone' if native else '/decisions'
    effective_model=model if model.startswith('jev') else 'jev-latest' if native else 'jev'
    return base if base.endswith(suffix) else base+suffix,effective_model,native

BLIND_NAMES: set[str] = set()
BLIND_STATE_KEYS = ('id','theme','title','description','precision','source_type','source_date','source_page','indicator','cost')

def set_blind_names(candidates: list[dict[str,Any]]) -> None:
    """Noms de candidats et de partis à masquer dans les textes envoyés au modèle (mesure jugée sans étiquette)."""
    BLIND_NAMES.clear()
    for c in candidates or []:
        for key in ('last_name','party','party_short','name','movement'):  # pas de prénom seul : « Marine », « Éric » sont aussi des mots courants
            value=str(c.get(key) or '').strip()
            if len(value) >= 3:
                BLIND_NAMES.add(value)
        full=f"{c.get('first_name','')} {c.get('last_name','')}".strip()
        if len(full) >= 3:
            BLIND_NAMES.add(full)

def blind_text(text: Any) -> Any:
    if not isinstance(text,str) or not BLIND_NAMES:
        return text
    pattern='|'.join(re.escape(n) for n in sorted(BLIND_NAMES,key=len,reverse=True))
    return re.sub(r'(?<!\w)(?:'+pattern+r')(?!\w)','[le candidat]',text,flags=re.I)

def blind_state(proposal: dict[str,Any]) -> dict[str,Any]:
    """État envoyé au modèle : la mesure et le contexte France, sans identité ni couleur du candidat.

    Retirés : candidate_id, titre/URL de la source, bloc programme (titre, URL, axes du candidat), budget global du
    candidat, plans de documents, URL et empreintes des extraits. Conservés : texte de la mesure, citation, signaux de
    position/répétition (valeurs), faits France par thème et finances publiques.
    """
    state={k:proposal[k] for k in BLIND_STATE_KEYS if proposal.get(k) is not None}
    for key in ('title','description'):
        if key in state:
            state[key]=blind_text(state[key])
    context=proposal.get('scoring_context')
    if isinstance(context,dict):
        evidence=[]
        for item in context.get('evidence') or []:
            kept={k:item[k] for k in ('id','proposal_id','theme_id','dimensions','text','values','source_date','page','heading','source_kind')
                  if item.get(k) is not None}
            kept['text']=blind_text(kept.get('text'))
            if 'heading' in kept:
                kept['heading']=blind_text(kept['heading'])
            evidence.append(kept)
        corpus=context.get('programme_corpus') or {}
        state['scoring_context']={
            **{k:context[k] for k in ('rules','france_checked_at','theme_facts','public_finances') if k in context},
            'evidence':evidence,
            'corpus_complete':not corpus.get('coverage') or all(c.get('complete') for c in corpus['coverage'])}
    return state

def typesafe_score_batch(proposals: list[dict[str,Any]], endpoint: str, model: str, api_key: str,
                         timeout: int=LLM_TIMEOUT_SECONDS, noul_gate: float=0.4, tag_threshold: float=0.7,
                         *, journal: LLMJournal | None = None) -> list[dict[str,Any]]:
    """Score un lot (<= 100 questions au total) en une seule requête Jev."""
    if not proposals:
        return []
    if len(proposals) == 1:
        return [typesafe_score(proposals[0],endpoint,model,api_key,timeout=timeout,noul_gate=noul_gate,tag_threshold=tag_threshold,journal=journal)]
    url,effective_model,use_native_typesafe=_jev_api_settings(endpoint,model)
    items={f"prop_{i}":blind_state(p) for i,p in enumerate(proposals)}
    headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json','Accept':'application/json','User-Agent':'Boussole2027-prototype/0.2'}
    if use_native_typesafe:
        batch_questions_dict: dict[str,dict[str,Any]]={}
        for i, p in enumerate(proposals):
            item_ref=f"prop_{i} ({p.get('id','')})"
            for qname, q in jev_questions().items():
                qc=dict(q)
                qc['instructions']=f"Concernant uniquement la proposition `{item_ref}` : {q['instructions']} Respecte `scoring_context.rules` et les sources datées du contexte pertinent."
                batch_questions_dict[f"p{i}__{qname}"]=qc
        payload: dict[str,Any]={'model':effective_model,'state':items,'questions':batch_questions_dict}
    else:
        batch_questions_list: list[dict[str,Any]]=[]
        for i, p in enumerate(proposals):
            item_ref=f"prop_{i} ({p.get('id','')})"
            batch_questions_list.extend(_build_decisions_questions(prefix=f"p{i}__",item_ref=item_ref))
        payload={'model':effective_model,'input':json.dumps(items,ensure_ascii=False),'questions':batch_questions_list}
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=headers)
    result=request_json(req,timeout,journal=journal,stage='primary',proposal_ids=[str(p.get('id')) for p in proposals])
    raw_answers=result.get('answers')
    if isinstance(raw_answers,list):
        flat_answers={str(item.get('name')):item for item in raw_answers if isinstance(item,dict) and item.get('name')}
    elif isinstance(raw_answers,dict):
        flat_answers=raw_answers
    else:
        raise ValueError('Réponse Jev batch invalide: champ `answers` manquant.')
    model_name=str(result.get('model',effective_model))
    scored_list: list[dict[str,Any]]=[]
    for i, p in enumerate(proposals):
        prefix=f"p{i}__"
        sub_answers={k[len(prefix):]:v for k,v in flat_answers.items() if k.startswith(prefix)}
        scored_list.append(_parse_jev_proposal_answers(p,sub_answers,model_name,noul_gate=noul_gate,tag_threshold=tag_threshold))
    return scored_list

def typesafe_score(proposal: dict[str,Any], endpoint: str, model: str, api_key: str,
                   timeout: int=LLM_TIMEOUT_SECONDS, noul_gate: float=0.4, tag_threshold: float=0.7,
                   *, journal: LLMJournal | None = None) -> dict[str,Any]:
    """Scoring Jev via Decisions OpenRouter, System One TypeSafe ou Decisions CheaperInference."""
    url,effective_model,use_native_typesafe=_jev_api_settings(endpoint,model)
    state=blind_state(proposal)
    headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json','Accept':'application/json','User-Agent':'Boussole2027-prototype/0.2'}
    if use_native_typesafe:
        questions={name:{**q,'instructions':q['instructions']+" Respecte `scoring_context.rules` et les sources datées du contexte pertinent."}
                   for name,q in jev_questions().items()}
        payload: dict[str,Any]={'model':effective_model,'state':state,'questions':questions}
    else:
        state_text='\n'.join(f"{k}: {json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}" for k,v in state.items())
        payload={'model':effective_model,'input':state_text,'questions':_build_decisions_questions()}
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=headers)
    result=request_json(req,timeout,journal=journal,stage='primary',proposal_ids=[str(proposal.get('id'))])
    raw_answers=result.get('answers')
    if isinstance(raw_answers,list):
        answers={str(item.get('name')):item for item in raw_answers if isinstance(item,dict) and item.get('name')}
    elif isinstance(raw_answers,dict):
        answers=raw_answers
    else:
        raise ValueError('Réponse Jev invalide: champ `answers` manquant.')
    return _parse_jev_proposal_answers(proposal,answers,str(result.get('model',effective_model)),noul_gate=noul_gate,tag_threshold=tag_threshold)

def llm_score(proposal: dict[str,Any], endpoint: str, model: str, api_key: str,
              provider: str=LLM_PROVIDER, temperature: float=LLM_TEMPERATURE,
              max_tokens: int=LLM_MAX_TOKENS, timeout: int=LLM_TIMEOUT_SECONDS,
              *, journal: LLMJournal | None = None) -> dict[str,Any]:
    """Structured scoring via TypeSafe Jev (System One), OpenAI-compatible chat API or Anthropic Messages API."""
    provider=provider.lower().strip()
    if provider in {'typesafe','jev'} or (provider == 'openrouter' and is_openrouter_jev_model(model)):
        return typesafe_score(proposal,endpoint,model,api_key,timeout=timeout,journal=journal)
    prompt=('Tu es assistant de pré-analyse pour une base électorale. Analyse uniquement le texte/source fourni. '
      'N’invente aucune source, promesse, estimation juridique ou budgétaire. Si une information manque, renvoie null. '
      'Retourne du JSON strict avec ideology (-100..100), feasibility (0..100 ou null), rights_income (0..100 ou null), '
      'rights_status (0..100 ou null), budget_net_bn_year (Md€/an, coût négatif/gain positif ou null), '
      'importance_sources {programme,media,votes}, threshold_tags (sous-ensemble des tags autorisés), source_note, confidence, rationale. '
      'Ajoute score_details pour chaque dimension ideology, feasibility, rights_income, rights_status, programme_importance, '
      'media_importance, budget_net_bn_year : {status: scored|not_applicable|insufficient_evidence, confidence: 0..1 ou null, rationale: texte}. '
      'Respecte scoring_context.rules ; sans preuve d’importance programmatique ou médiatique, laisse ces sous-scores à null. '
      'Le score est ton application du barème aux faits cités, pas un nombre devant figurer dans une source. '
      'Barème partagé: '+json.dumps(scoring_rubric(),ensure_ascii=False)+'. '
      'Traite les notes comme des évaluations préliminaires à révision humaine. Tags: '+', '.join(TAGS)+'.\nEntrée: '+json.dumps(blind_state(proposal),ensure_ascii=False))
    if provider == 'anthropic':
        url=endpoint.rstrip('/')+'/messages'
        payload={'model':model,'temperature':temperature,'max_tokens':max_tokens,
                 'system':'Réponds avec un objet JSON strict, sans bloc Markdown.',
                 'messages':[{'role':'user','content':prompt}]}
        headers={'x-api-key':api_key,'anthropic-version':'2023-06-01','Content-Type':'application/json'}
    elif provider in {'openrouter','openai','mistral','mammouth'}:
        url=endpoint.rstrip('/')+'/chat/completions'
        payload={'model':model,'temperature':temperature,'max_tokens':max_tokens,
                 'messages':[{'role':'user','content':prompt}]}
        if provider == 'openrouter':
            payload['response_format']={'type':'json_object'}
        headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'}
    else:
        raise ValueError('LLM_PROVIDER doit être openrouter, typesafe (ou jev), openai, mistral, mammouth ou anthropic.')
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers)
    result=request_json(req,timeout,journal=journal,stage='primary',proposal_ids=[str(proposal.get('id'))])
    finish_reason=None
    if provider == 'anthropic':
        finish_reason=result.get('stop_reason')
        content=''.join(block.get('text') or '' for block in result.get('content',[]) if isinstance(block,dict) and block.get('type')=='text')
    else:
        choice=(result.get('choices') or [{}])[0]
        finish_reason=choice.get('finish_reason')
        msg=choice.get('message') or {}
        content=msg.get('content')
    if not isinstance(content,str) or not content.strip():
        raise ValueError(f'Réponse LLM vide (finish_reason={finish_reason}); augmentez LLM_MAX_TOKENS.')
    scored=parse_json_object(content,'Réponse LLM')
    if not isinstance(scored.get('importance_sources'),dict):
        raise ValueError('Réponse LLM invalide: objet de scores et importance_sources requis.')
    scored={k:v for k,v in scored.items() if k in {
        'ideology','feasibility','rights_income','rights_status','budget_net_bn_year',
        'importance_sources','threshold_tags','source_note','confidence','rationale','score_details'}}
    details=scored.get('score_details')
    if not isinstance(details,dict) or set(details) != set(DIMENSIONS):
        raise ValueError('Réponse LLM invalide: score_details requis pour chaque dimension.')
    for dimension,(lo,hi) in DIMENSIONS.items():
        value=scored['importance_sources'].get(dimension.split('_')[0]) if dimension in {'programme_importance','media_importance'} else scored.get(dimension)
        if value is not None and (not number(value) or (lo is not None and not lo <= value <= hi)):
            raise ValueError(f'Score hors plage: {dimension}')
        detail=details[dimension]
        if not isinstance(detail,dict) or detail.get('status') not in {'scored','not_applicable','insufficient_evidence'}:
            raise ValueError(f'Statut LLM invalide: {dimension}')
        if detail['status'] == 'not_applicable' and dimension not in {'rights_income','rights_status'}:
            raise ValueError(f'Dimension LLM non applicable invalide: {dimension}')
        if value is not None and detail['status'] != 'scored':
            raise ValueError(f'Score et statut LLM incohérents: {dimension}')
        conf=detail.get('confidence')
        if conf is not None and (not number(conf) or not 0 <= conf <= 1):
            raise ValueError(f'Confiance LLM hors plage: {dimension}')
        if dimension in {'programme_importance','media_importance'} and not importance_evidence(proposal,dimension):
            scored['importance_sources'][dimension.split('_')[0]]=None
            detail.update(status='insufficient_evidence',confidence=None)
        detail.update(method='chat-self-reported',model=model)
    budget=scored.get('budget_net_bn_year')
    if budget is not None:
        explicit=extract_explicit_budget_bn(proposal)
        if explicit is None or abs(budget) != abs(explicit):
            raise ValueError('Budget LLM sans montant annuel explicite rattaché à la mesure.')
    if not isinstance(scored.get('threshold_tags'),list) or any(tag not in TAGS for tag in scored['threshold_tags']):
        raise ValueError('Réponse LLM: tags non autorisés.')
    scored['importance_sources']['votes']=(proposal.get('importance_sources') or {}).get('votes')
    result={**proposal,**scored}
    update_importance(result)
    return apply_structural_importance(result)

def scoring_configuration(args: argparse.Namespace) -> tuple[str,bool,str,str]:
    if args.limit < 0: raise ValueError('--limit doit être positif ou nul.')
    max_batch=max(1,min(6,JEV_MAX_QUESTIONS//len(jev_questions())))
    if args.batch_size is None: args.batch_size=max_batch
    if not 1 <= args.batch_size <= max_batch: raise ValueError(f'--batch-size doit être compris entre 1 et {max_batch} (limite API de {JEV_MAX_QUESTIONS} questions par requête, {len(jev_questions())} questions par proposition).')
    if not 0 <= args.confidence_threshold <= 1: raise ValueError('--confidence-threshold doit être entre 0 et 1.')
    if args.context_max_age_days < 1: raise ValueError('--context-max-age-days doit être positif.')
    if args.web_max_calls < 0: raise ValueError('--web-max-calls doit être positif ou nul.')
    if args.web_max_tokens < 1: raise ValueError('--web-max-tokens doit être positif.')
    if args.web_fallback and not args.llm: raise ValueError('--web-fallback nécessite --llm pour une première lecture.')
    provider=str(args.provider or LLM_PROVIDER).lower().strip()
    endpoints={'openrouter':'https://openrouter.ai/api/v1','typesafe':'https://api.cheaperinference.com/v1',
               'jev':'https://api.cheaperinference.com/v1','openai':'https://api.openai.com/v1',
               'mistral':'https://api.mistral.ai/v1','mammouth':'https://api.mammouth.ai/v1',
               'anthropic':'https://api.anthropic.com/v1'}
    if provider not in endpoints:
        raise ValueError(f'Fournisseur LLM inconnu: {provider}')
    if args.endpoint is None:
        args.endpoint=endpoints[provider] if provider == 'openrouter' else os.getenv('LLM_API_BASE_URL') or endpoints[provider]
    if args.model is None:
        args.model=(os.getenv('OPENROUTER_SCORING_MODEL') or os.getenv('LLM_MODEL') or LLM_MODEL) if provider == 'openrouter' else (
            os.getenv('LLM_MODEL') or ('jev' if provider in {'typesafe','jev'} else LLM_MODEL))
    if args.web_model is None:
        args.web_model=os.getenv('OPENROUTER_WEB_MODEL') or os.getenv('OPENROUTER_MODEL','')
    if args.web_model.strip().endswith(':online'):
        print('AVERTISSEMENT: le suffixe :online est obsolète et retiré ; recherche via openrouter:web_search.',file=sys.stderr)
    args.web_model=normalize_web_model(args.web_model)
    if args.llm and not args.model.strip():
        variable='OPENROUTER_SCORING_MODEL' if provider == 'openrouter' else 'LLM_MODEL'
        raise ValueError(f'Modèle de scoring absent ; définir {variable} ou --model.')
    jev_scoring=provider in {'typesafe','jev'} or (provider == 'openrouter' and is_openrouter_jev_model(args.model))
    if args.web_fallback and is_openrouter_jev_model(args.web_model):
        raise ValueError('Le modèle web doit être un modèle chat compatible outils ; Jev Decisions ne fait pas de recherche web.')
    web_key=os.getenv('OPENROUTER_API_KEY','').strip()
    if args.web_fallback and (not web_key or not args.web_model.strip()):
        raise ValueError('--web-fallback nécessite OPENROUTER_API_KEY et OPENROUTER_WEB_MODEL (ou --web-model).')
    if provider == 'openrouter':
        key=web_key
    elif provider in {'typesafe','jev'}:
        key=(os.getenv('TYPESAFE_API_KEY') or os.getenv('LLM_API_KEY') or '').strip()
    else:
        key=(os.getenv('LLM_API_KEY') or '').strip()
    placeholder=not key or bool(re.search(r'(?i)(your[_ -]?api[_ -]?key|replace[_ -]?me|placeholder|insert[_ -]?key|xxx+|<.*key.*>)',key))
    if args.llm and placeholder:
        variable='OPENROUTER_API_KEY' if provider == 'openrouter' else 'TYPESAFE_API_KEY ou LLM_API_KEY' if provider in {'typesafe','jev'} else 'LLM_API_KEY'
        raise ValueError(f'Clé API LLM absente ou placeholder ; définir {variable}.')
    return provider,jev_scoring,key,web_key

def main():
    try:
        load_env_file(Path(__file__).with_name('.env'))
    except (OSError,ValueError) as exc:
        print(f'Erreur de configuration: {exc}',file=sys.stderr)
        return 2
    ap=argparse.ArgumentParser(description=__doc__)
    src=ap.add_mutually_exclusive_group();src.add_argument('--input',type=Path,help='JSON local (dont le bundle v2 public du dépôt)');src.add_argument('--url',help='URL explicitement fournie vers un endpoint JSON');src.add_argument('--repo-dir',type=Path,help='Dossier du dépôt cloné; lit public-data/data-v2.json localement')
    ap.add_argument('--inspect-site',metavar='URL',help='Inspecte une page HTML (titre, scripts et liens), sans extraire de mesures automatiquement')
    ap.add_argument('--download-data-v2',nargs='?',const=Path('data-v2.json'),type=Path,metavar='FICHIER',help='Télécharge la source publique data-v2.json (défaut: ./data-v2.json) puis quitte')
    ap.add_argument('--source-json-url',default=SOURCE_JSON_DOWNLOAD_URL,help='URL JSON source (défaut: endpoint data-v2 actuellement utilisé par le site)')
    ap.add_argument('--overrides',type=Path,help='JSON local d’overrides sourcés: candidats.intentions_vote_pct et propositions.importance_sources.votes')
    ap.add_argument('--sync-repo',nargs='?',const=Path('./upstream_repo'),default=None,type=Path,metavar='DOSSIER',help='Synchroniser le clone Git indiqué (défaut si option seule: ./upstream_repo)')
    ap.add_argument('--fetch-remote',action='store_true',help='Télécharger directement le JSON brut GitHub (ignoré avec --sync-repo)')
    ap.add_argument('--out','--output',dest='out',type=Path,default=Path('donnees_2027.json'),help='Fichier JSON de sortie (défaut: donnees_2027.json)')
    ap.add_argument('--cache-file',type=Path,default=Path('cache_scores.json'),help='Cache LLM différentiel SHA-256 (défaut: cache_scores.json)')
    ap.add_argument('--llm-log-file',type=Path,help='Journal JSONL des résultats et décisions (défaut avec --llm : fichier horodaté dans logs)')
    ap.add_argument('--context-file',type=Path,default=Path('contexte_scoring_2027.json'),help='Snapshot source et extraits locaux sourcés')
    ap.add_argument('--refresh-context',action='store_true',help='Réactualiser le snapshot source en conservant les extraits locaux')
    ap.add_argument('--context-max-age-days',type=int,default=30,help='Délai de révision du contexte et du cache web (défaut: 30 jours)')
    ap.add_argument('--review-queue',type=Path,default=Path('scoring_review_queue.json'),help='File JSON des dimensions à compléter')
    ap.add_argument('--confidence-threshold',type=float,default=0.65,help='Seuil par dimension déclenchant la révision (0..1, défaut: 0.65)')
    ap.add_argument('--web-fallback',action='store_true',help='Autoriser les secondes lectures web payantes via OpenRouter')
    ap.add_argument('--web-model',help='Modèle de recherche (OPENROUTER_WEB_MODEL), utilisant l’outil openrouter:web_search')
    ap.add_argument('--web-max-calls',type=int,default=10,help='Plafond de nouvelles requêtes web par exécution (défaut: 10)')
    ap.add_argument('--web-max-tokens',type=int,default=DEFAULT_WEB_MAX_TOKENS,help='Budget de sortie par requête web, raisonnement inclus (défaut: 8192)')
    ap.add_argument('--llm','--use-llm',dest='llm',action='store_true',help='Activer le scoring LLM facultatif ; clé commune OPENROUTER_API_KEY avec OpenRouter')
    ap.add_argument('--allow-legacy-scoring',action='store_true',help='Autoriser explicitement le scoring historique sans corpus documentaire collecté')
    ap.add_argument('--provider',default=os.getenv('LLM_PROVIDER',LLM_PROVIDER),help='Fournisseur: openrouter (défaut), typesafe (Jev), openai, mistral, mammouth ou anthropic')
    ap.add_argument('--endpoint',help='Remplacer l’endpoint du fournisseur sélectionné')
    ap.add_argument('--model',help='Modèle de scoring (OPENROUTER_SCORING_MODEL avec OpenRouter)')
    ap.add_argument('--batch-size',type=int,default=None,help='Taille de lot pour Jev/TypeSafe (défaut : le maximum permis par 100 questions/requête, au plus 6)')
    ap.add_argument('--limit',type=int,default=0,help='Limiter le nombre de propositions (0 = toutes)')
    ap.add_argument('--selection',type=Path,help='Ne garder que les propositions de cette sélection (selection_precision_2027.json) et leur joindre la précision')
    args=ap.parse_args()
    cache: dict[str,dict[str,Any]]={}
    journal: LLMJournal | None = None
    try:
        provider,jev_scoring,key,web_key=scoring_configuration(args)
        repo_dir=args.repo_dir
        if args.sync_repo is not None:
            if repo_dir is not None and args.sync_repo != Path('./upstream_repo') and repo_dir != args.sync_repo:
                raise ValueError('Utilisez soit --repo-dir DOSSIER --sync-repo, soit --sync-repo DOSSIER; les dossiers doivent correspondre.')
            repo_dir=args.sync_repo if args.sync_repo != Path('./upstream_repo') or repo_dir is None else repo_dir
        effective_sync=args.sync_repo is not None
        if args.download_data_v2 is not None:
            path=download_source_json(args.download_data_v2,args.source_json_url)
            print(f'Téléchargé {SOURCE_JSON_DOWNLOAD_URL} vers {path} ({path.stat().st_size} octets)')
            return 0
        if args.inspect_site:
            print(json.dumps(inspect_site(args.inspect_site),ensure_ascii=False,indent=2));return 0
        if args.input: data=ingest_json(args.input)
        elif args.url: data=ingest_url(args.url)
        elif effective_sync:
            import subprocess
            assert repo_dir is not None
            if not repo_dir.exists():
                repo_dir.parent.mkdir(parents=True,exist_ok=True)
                subprocess.run(['git','clone','https://github.com/coucou123212321232123/presidentielle-2027-comparateur.git',str(repo_dir)],check=True,capture_output=True,text=True)
            elif not (repo_dir/'.git').exists():
                raise ValueError(f'--sync-repo requiert un clone Git dans {repo_dir}; ce dossier existe mais ne contient pas .git.')
            else:
                subprocess.run(['git','-C',str(repo_dir),'pull','--ff-only'],check=True,capture_output=True,text=True)
            local=repo_dir/'public-data'/'data-v2.json'
            if not local.exists(): raise ValueError(f'Bundle introuvable: {local}')
            data=ingest_json(local)
            try: data['meta']['source_commit']=subprocess.check_output(['git','-C',str(repo_dir),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
            except Exception: pass
        elif args.fetch_remote or args.repo_dir is None:
            data=ingest_url(args.source_json_url)
        elif args.repo_dir:
            local=args.repo_dir/'public-data'/'data-v2.json'
            if not local.exists(): raise ValueError(f'Bundle introuvable: {local}')
            data=ingest_json(local)
            try:
                import subprocess
                data['meta']['source_commit']=subprocess.check_output(['git','-C',str(args.repo_dir),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
            except Exception: pass
        else:
            bundled=Path(__file__).with_name('schema_et_donnees_exemple.json')
            data=ingest_json(bundled) if bundled.exists() else {'meta':{},'candidates':[],'proposals':[]}
        if args.overrides: data=apply_overrides(data,args.overrides)
        if args.selection: data=apply_selection(data,args.selection)
        set_blind_names(data.get('candidates',[]))
        if args.llm:
            uncollected=sum(not p.get('source_evidence') for p in data['proposals'][:args.limit or None])
            if uncollected and not args.allow_legacy_scoring:
                raise ValueError(f'{uncollected} propositions sans document collecté. Exécuter programme_corpus_2027.py collect, extract puis export ; '
                                 'utiliser ensuite --input propositions_programmes_2027.json. --allow-legacy-scoring autorise explicitement l’ancien mode.')
            if uncollected:
                print(f'AVERTISSEMENT: ancien mode autorisé pour {uncollected} propositions sans corpus ; les liens seuls ne prouvent pas le contenu des programmes.',file=sys.stderr)
        snapshot=load_context(data,args.context_file,args.refresh_context)
        warnings=context_warnings(snapshot,args.context_max_age_days)
        for warning in warnings:
            print(f'AVERTISSEMENT: {warning}',file=sys.stderr)
        rows=[{**p,'scoring_context':with_corpus_evidence(p,proposal_context(p,snapshot))} for p in data['proposals'][:args.limit or None]]
        llm_enabled=args.llm
        out=[heuristic_score(p) for p in rows]
        reused=0; scored=0
        primary_failures=0
        cache=cached_scored_rows(args.cache_file) if llm_enabled else {}
        if llm_enabled or args.llm_log_file is not None:
            journal=LLMJournal(args.llm_log_file,secrets=(key,web_key))
            journal.write('run_start',provider=provider,scoring_model=args.model,web_model=args.web_model,
                          llm_enabled=llm_enabled,web_enabled=args.web_fallback,
                          proposal_count=len(rows),web_max_calls=args.web_max_calls,
                          web_max_tokens=args.web_max_tokens,confidence_threshold=args.confidence_threshold)
            print(f'Journal LLM : {journal.path}')

        def log_result(stage: str, source: str, proposal: dict[str,Any], error: str | None = None) -> None:
            if journal:
                journal.write('assessment',stage=stage,source=source,proposal_id=proposal.get('id'),
                              candidate_id=proposal.get('candidate_id'),error=error,result=scoring_snapshot(proposal))

        pending_batch: list[tuple[int,dict[str,Any],str]]=[]

        def flush_jev_batch() -> None:
            nonlocal scored,primary_failures
            if not pending_batch:
                return
            batch_props=[item[1] for item in pending_batch]
            try:
                scored_batch=typesafe_score_batch(batch_props,args.endpoint,args.model,key,journal=journal)
                if len(scored_batch) != len(pending_batch):
                    raise ValueError('Réponse Jev: nombre de propositions incohérent.')
                now_iso=utc_now().isoformat()
                for (idx, _, fp), sq in zip(pending_batch,scored_batch):
                    sq['content_hash']=fp; sq['scoring_fingerprint']=fp; sq['llm_scored_at']=now_iso
                    cache[str(sq.get('id'))]={'content_hash':fp,'scored':sq}
                    out[idx]=sq
                    scored+=1
                    log_result('primary','api',sq)
                save_scored_cache(args.cache_file,cache)
            except (OSError,ValueError,KeyError,urllib.error.URLError,json.JSONDecodeError) as exc:
                if journal:
                    journal.write('primary_batch_error',proposal_ids=[p.get('id') for p in batch_props],error=str(exc))
                print(f"AVERTISSEMENT: lot Jev en échec ({exc}); repli proposition par proposition.",file=sys.stderr)
                for idx, q_item, fp in pending_batch:
                    try:
                        sq=llm_score(q_item,args.endpoint,args.model,key,provider=provider,journal=journal)
                        sq['content_hash']=fp; sq['scoring_fingerprint']=fp
                        sq['llm_scored_at']=utc_now().isoformat()
                        cache[str(sq.get('id'))]={'content_hash':fp,'scored':sq}
                        out[idx]=sq
                        scored+=1
                        log_result('primary','api',sq)
                    except (OSError,ValueError,KeyError,urllib.error.URLError,json.JSONDecodeError) as sub_exc:
                        primary_failures+=1
                        log_result('primary','error',q_item,str(sub_exc))
                        print(f"AVERTISSEMENT: scoring LLM impossible pour {q_item.get('id','(sans id)')}; score heuristique conservé ({sub_exc}).",file=sys.stderr)
                        out[idx]=q_item
                save_scored_cache(args.cache_file,cache)
            pending_batch.clear()

        for idx, p in enumerate(rows):
            q=out[idx]
            fingerprint=digest({'policy':4 if jev_scoring else 3,'evidence':content_hash(p),'provider':provider,
                                'endpoint':args.endpoint,'model':args.model,
                                'questions':jev_questions() if jev_scoring else TYPESAFE_QUESTIONS})
            previous=cache.get(str(p.get('id')))
            if llm_enabled and previous and previous.get('content_hash') == fingerprint:
                out[idx]=previous['scored']; reused+=1
                log_result('primary','cache',out[idx])
            elif llm_enabled and jev_scoring and args.batch_size > 1:
                pending_batch.append((idx,q,fingerprint))
                if len(pending_batch) >= args.batch_size:
                    flush_jev_batch()
            elif llm_enabled:
                try:
                    q=llm_score(q,args.endpoint,args.model,key,provider=provider,journal=journal)
                    q['content_hash']=fingerprint; q['scoring_fingerprint']=fingerprint
                    q['llm_scored_at']=utc_now().isoformat()
                    cache[str(p.get('id'))]={'content_hash':fingerprint,'scored':q}
                    scored+=1
                    log_result('primary','api',q)
                except (OSError,ValueError,KeyError,urllib.error.URLError,json.JSONDecodeError) as exc:
                    primary_failures+=1
                    log_result('primary','error',q,str(exc))
                    print(f"AVERTISSEMENT: scoring LLM impossible pour {p.get('id','(sans id)')}; score heuristique conservé ({exc}).",file=sys.stderr)
                out[idx]=q
            else:
                out[idx]=q
                log_result('primary','normalization',q)
        if pending_batch:
            flush_jev_batch()
        web_calls=0
        web_reused=0
        web_review_candidates=sum(bool(review_issues(q,args.confidence_threshold)) for q in out)
        web_deferred_by_limit=0
        web_skipped_disabled=0
        web_errors=0
        web_applied_dimensions=0
        web_abstained_dimensions=0
        web_rejected_dimensions=0
        web_low_confidence_dimensions=0
        if llm_enabled:
            primary_api_calls=journal.request_counts.get('primary',0) if journal else 0
            print(f'Scoring principal : cache={reused}, nouvelles évaluations={scored}, erreurs={primary_failures}, appels API={primary_api_calls}.')
            state='activée' if args.web_fallback else 'désactivée'
            print(f'File web : {web_review_candidates} propositions à compléter ; recherche {state}, plafond={args.web_max_calls} nouveaux appels.')
        if journal:
            journal.write('web_plan',review_candidates=web_review_candidates,enabled=args.web_fallback,max_calls=args.web_max_calls)
        for idx,q in enumerate(out):
            entry=cache.get(str(q.get('id')),{})
            fingerprint=q.get('content_hash')
            cached_web=reusable_web_result(entry,fingerprint,args.web_model,args.confidence_threshold,args.context_max_age_days,args.web_max_tokens,rubric=scoring_rubric()) if fingerprint else None
            if cached_web is not None:
                out[idx]=cached_web
                web_reused+=1
                log_result('web','cache',cached_web)
                continue
            # La lecture web ne couvre que les dimensions historiques ; les axes sont révisés par revision_2027.py.
            issues=[i for i in review_issues(q,args.confidence_threshold) if i['dimension'] in DIMENSIONS]
            if not issues:
                if journal:
                    journal.write('web_skipped',proposal_id=q.get('id'),reason='no_review_needed')
                continue
            if not args.web_fallback:
                web_skipped_disabled+=1
                if journal:
                    journal.write('web_skipped',proposal_id=q.get('id'),reason='web_disabled',
                                  dimensions=[item['dimension'] for item in issues])
                continue
            if web_calls >= args.web_max_calls:
                web_deferred_by_limit+=1
                if journal:
                    journal.write('web_skipped',proposal_id=q.get('id'),reason='call_limit',
                                  dimensions=[item['dimension'] for item in issues])
                continue
            web_calls+=1
            print(f"[web {web_calls}/{args.web_max_calls}] {q.get('id')} : {len(issues)} dimensions, modèle {args.web_model}")
            if journal:
                journal.write('web_selected',proposal_id=q.get('id'),issues=issues,attempt=web_calls)
            try:
                enriched=web_reassess(q,issues,args.web_model,web_key,args.confidence_threshold,max_tokens=args.web_max_tokens,journal=journal,rubric=scoring_rubric())
                enriched['web_review']['cache_key']=web_cache_key(fingerprint or content_hash(q),args.web_model,args.confidence_threshold,args.web_max_tokens,rubric=scoring_rubric())
                out[idx]=enriched
                review=enriched['web_review']
                search=review.get('search_activity') or {}
                search_label={'performed':'effectuée','not_performed':'non effectuée','unknown':'non renseignée'}.get(str(search.get('status')),'non renseignée')
                print(f"  Recherche web : {search_label} ; recherches déclarées par le fournisseur={search.get('web_search_requests')}.")
                accepted=len(review.get('accepted_dimensions',[]))
                abstained=len(review.get('abstained_dimensions',[]))
                rejected=len(review.get('rejected_dimensions',{}))
                low_confidence=sum(assessment.get('value') is not None and dimension not in review.get('accepted_dimensions',[])
                                   for dimension,assessment in review.get('assessments',{}).items())
                web_applied_dimensions+=accepted
                web_abstained_dimensions+=abstained
                web_rejected_dimensions+=rejected
                web_low_confidence_dimensions+=low_confidence
                log_result('web','api',enriched)
                print(f'  Résultat : notes appliquées={accepted}, abstentions={abstained}, sous le seuil={low_confidence}, dimensions refusées={rejected}.')
                for dimension,reason in review.get('rejected_dimensions',{}).items():
                    print(f"AVERTISSEMENT: complément web refusé pour {q.get('id')}, dimension {dimension} ({reason}); première lecture conservée pour cette dimension.",file=sys.stderr)
                if fingerprint and entry:
                    entry['web_scored']=enriched
                    save_scored_cache(args.cache_file,cache)
            except (OSError,ValueError,KeyError,urllib.error.URLError) as exc:
                web_errors+=1
                print(f"AVERTISSEMENT: seconde lecture web impossible pour {q.get('id')} ({exc}); première lecture conservée.",file=sys.stderr)
                review: dict[str,Any]={'status':'error','model':args.web_model,'error':str(exc)}
                if isinstance(exc,WebResponseError):
                    review['response']=exc.details
                out[idx]={**q,'web_review':review}
                log_result('web','error',out[idx],str(exc))
        if llm_enabled: save_scored_cache(args.cache_file,cache)
        queue=review_queue(out,args.confidence_threshold)
        summary={'primary_reused':reused,'primary_scored':scored,'primary_failures':primary_failures,
                 'primary_api_calls':journal.request_counts.get('primary',0) if journal else 0,
                 'web_review_candidates':web_review_candidates,'web_calls':web_calls,'web_reused':web_reused,
                 'web_api_calls':journal.request_counts.get('web',0) if journal else 0,
                 'web_deferred_by_limit':web_deferred_by_limit,'web_skipped_disabled':web_skipped_disabled,
                 'web_errors':web_errors,'web_applied_dimensions':web_applied_dimensions,
                 'web_abstained_dimensions':web_abstained_dimensions,'web_rejected_dimensions':web_rejected_dimensions,
                 'web_low_confidence_dimensions':web_low_confidence_dimensions,'review_remaining':len(queue)}
        args.review_queue.parent.mkdir(parents=True,exist_ok=True)
        args.review_queue.write_text(json.dumps({'generated_at':utc_now().isoformat(),'confidence_threshold':args.confidence_threshold,
            'proposal_count':len(queue),'proposals':queue},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        result={'meta':{**data.get('meta',{}),'pipeline':'pipeline_scoring_2027.py','scoring_mode':'llm-human-review-required' if llm_enabled else 'heuristic-normalization-only','llm_provider':provider if llm_enabled else None,'llm_incremental':bool(llm_enabled),'llm_reused_unchanged':reused,'llm_scored_new_or_changed':scored,
            'context_file':str(args.context_file),'context_retrieved_at':snapshot['retrieved_at'],'context_warnings':warnings,
            'review_queue_file':str(args.review_queue),'review_proposal_count':len(queue),'confidence_threshold':args.confidence_threshold,
            **summary,'llm_log_file':str(journal.path) if journal else None,
            'web_max_tokens':args.web_max_tokens,'note':'Nuls conservés lorsque l’information est inconnue; scores LLM à valider humainement.'},'dimensions_schema':dimensions_schema(),'candidates':data['candidates'],'themes':data.get('themes',[]),'proposals':out}
        args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if journal:
            journal.write('run_summary',**summary)
        if llm_enabled:
            print(f'Bilan web : nouveaux appels={web_calls}, cache={web_reused}, erreurs={web_errors}, en attente du plafond={web_deferred_by_limit}, recherche désactivée={web_skipped_disabled}.')
            print(f'Dimensions web nouvelles : appliquées={web_applied_dimensions}, abstentions={web_abstained_dimensions}, sous le seuil={web_low_confidence_dimensions}, refusées={web_rejected_dimensions}.')
            print(f'File de révision restante : {len(queue)} propositions (y compris les recherches sans preuve suffisante).')
        print(f"Écrit {args.out}: {len(result['candidates'])} candidats, {len(out)} propositions; mode {result['meta']['scoring_mode']}" + (f" ({provider}); LLM réutilisé={reused}, scoré={scored}" if llm_enabled else ''))
        return 0
    except (ScoringAPIError,LLMLogError) as e:
        if cache:
            save_scored_cache(args.cache_file,cache)
        if journal and not isinstance(e,LLMLogError):
            try:
                journal.write('run_error',error_type=type(e).__name__,error=str(e))
            except LLMLogError as log_exc:
                print(f'Erreur journal LLM : {log_exc}',file=sys.stderr)
        category='journal LLM' if isinstance(e,LLMLogError) else 'API LLM'
        print(f'Erreur {category} : {e}. Traitement arrêté ; scores déjà calculés conservés dans le cache.',file=sys.stderr)
        return 2
    except (OSError,ValueError,KeyError,urllib.error.URLError,json.JSONDecodeError) as e:
        if journal:
            try:
                journal.write('run_error',error_type=type(e).__name__,error=str(e))
            except LLMLogError as log_exc:
                print(f'Erreur journal LLM : {log_exc}',file=sys.stderr)
        print(f'Erreur pipeline: {e}',file=sys.stderr);return 2
    finally:
        if journal:
            journal.close()
if __name__=='__main__':
    try:
        reconf_out=getattr(sys.stdout,'reconfigure',None)
        if callable(reconf_out): reconf_out(encoding='utf-8')
        reconf_err=getattr(sys.stderr,'reconfigure',None)
        if callable(reconf_err): reconf_err(encoding='utf-8')
    except (OSError,ValueError):
        pass
    raise SystemExit(main())
