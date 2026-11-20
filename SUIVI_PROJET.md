# Suivi du projet (journal de reprise)

Fichier central de reprise : à lire en premier pour continuer sans relire l'historique. Le détail daté est découpé en neuf sous-fichiers dans [docs/suivi/](docs/suivi/) ; ce fichier garde l'état courant, les décisions durables, ce qui reste à faire et l'index.

Dernière mise à jour : 2026-11-20 (page « Coulisses » de la constellation ; fiches : statut, lecture par les modèles et repères en mots factuels, étoile à branches des candidats, zone des quartiles ; collecte par navigateur pour les sites à contrôle anti-robot ; sauvegarde des données non versionnées sur E: et OneDrive ; constellation : axes en double retirés, noms et infobulles réécrits pour le grand public, guide de lecture).

## Convention de mise à jour

- Une étape terminée s'ajoute au sous-fichier de sa période. Quand une période devient longue, créer un sous-fichier nommé par dates (`NN_AAAA-MM-JJ_sujet.md`), l'ajouter à l'index ci-dessous et à la chaîne « Précédent / Suivant » des sous-fichiers voisins.
- Mettre à jour ici l'état actuel et la liste « À faire » ; une décision durable va dans « Décisions durables » avec un lien vers son sous-fichier.

## État actuel (2026-11-11)

- **Corpus** : 14 candidats, 188 documents (180 avec propositions), **10 831 propositions publiées** (export du 2026-11-08). Mises à jour par la chaîne `mise-a-jour --complet` (collecte, extraction, intégration, annotation, compléments, calculs, export).
- **Notation** : questionnaire q1 pour toutes les mesures actives, lues avec le passage du document et le lexique (méthode `contexte-v2`, GPT-6.1 Terra, effort low). Compléments `soc_finalite`, `degre_rupture` et `niveau_revenu`. Jev n'est plus utilisé (2026-11-06). Détail : [docs/suivi/04](docs/suivi/04_2026-11-06_q1_effort_et_chaine.md), [06](docs/suivi/06_2026-11-07_contexte_lexique_importance.md), [08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md).
- **Constellation** (`web/constellation_2027.html`) : étoiles candidat × thème, centres axe par axe pondérés par l'importance et la fiabilité des composantes, positions fragiles signalées (fiabilité sous 70 %), pages Avertissement, Méthode, Sources et Contribuer, signalement d'erreur par proposition.
- **Tableau de bord** (`boussole_2027.py tableau-de-bord`, 127.0.0.1:8765) : validation, sources, runs, votes, signalements.
- **Votes à l'Assemblée** : phase 2 (liens vote-mesure posés à la main). Ils n'entrent ni dans la notation, ni dans l'importance, ni dans les positions.
- **Questionnaire q2** : en production depuis la renotation complète du 2026-11-16 (11 054 mesures, 20,91 $) : drex-max et pplx-decider lisent, Terra arbitre la file des désaccords ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
- **Mise à jour du 2026-11-18** : collecte, extraction et intégration faites (19 documents nouveaux, 2 modifiés, 600 propositions rapprochées avec `--forcer` après vérification des sources), puis notation q2 des 380 mesures nouvelles ou modifiées (`annoter --q2 --uids`, 187 arbitrées, 0,88 $) ; 1,14 $ au total. Base : 11 338 mesures dont 284 ajoutées (Philippe 166, Dupont-Aignan 69, Glucksmann 49), toutes notées. Restent : 10 836 mesures lues en `essai-q2-v5` contre 502 en v7 (relecture estimée à 21-32 $, à décider) ; 23 doublons de titre chez Philippe ; 380 mesures modifiées et 137 rapprochements incertains à valider ; 3 liens du RN, en erreur HTTP 307 (contrôle anti-robot Sucuri), collectés le 2026-11-19 par la collecte par navigateur : texte identique à celui déjà intégré (35 mesures actives et notées), rien de nouveau (mise à jour du 2026-11-19, 0,008 $). `donnees/budget_2027.json` ne compte que les runs de la chaîne : ni cette notation ni la renotation du 2026-11-16 n'y figurent, donc `--mensuel` sous-estime la dépense. Attention : 10 929 mesures sont encore lues en `essai-q2-v5` (125 en v7) ; la passe ciblée passe avant les mesures nouvelles, donc un petit `--max-cost` sur la chaîne complète ne lirait pas ces dernières (`--sans-annotation` pour s'arrêter à l'intégration).

## Décisions durables

Décisions de départ de l'utilisateur, conservées telles quelles dans [docs/suivi/01](docs/suivi/01_2026-11-04_05_corpus_et_scoring_jev.md#décisions-de-lutilisateur).

Décisions datées depuis le 2026-11-05 :

- **2026-11-05** : importance structurelle utilisée directement comme importance programmatique, sans LLM ([01](docs/suivi/01_2026-11-04_05_corpus_et_scoring_jev.md)).
- **2026-11-05** : axe économique réservé aux mesures à objet économique ou à effet direct sur l'économie ; le seul coût d'une mesure régalienne relève de la faisabilité ; estimation de coût indicative, jamais additionnée ([02](docs/suivi/02_2026-11-05_constellation_revision_arbitrage.md)).
- **2026-11-06** : une seule méthode pour tout le corpus (q1) ; publication immédiate avec badge « non relue », sauf mesure modifiée ou rapprochement douteux ([03](docs/suivi/03_2026-11-06_constellation_descripteurs_pipeline.md)).
- **2026-11-06** : effort low pour les batchs (coût et qualité comparables à medium) ; aucun appel payant sans plafond explicite ([04](docs/suivi/04_2026-11-06_q1_effort_et_chaine.md)).
- **2026-11-06** : la file de validation ne retient que les questions qui fixent le sens d'une position ; pas de seconde lecture automatique ([05](docs/suivi/05_2026-11-06_07_rangement_et_integration.md)).
- **2026-11-07** : poids des thèmes dans un centre = importance moyenne de leurs propositions ; lexique par candidat affiché comme information, pas utilisé pour annoter ([06](docs/suivi/06_2026-11-07_contexte_lexique_importance.md)).
- **2026-11-07** : votes hors notation, importance et positions ; chaque lien vote-mesure est validé par un humain ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
- **2026-11-09** : niveau de revenu traité en trois axes ; la portée remplace `rights_income` ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
- **2026-11-10** : centre d'un candidat pondéré par l'importance moyenne × racine du nombre de mesures notées sur l'axe ; précision non prise en compte dans l'importance (non tranché) ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
- **2026-11-11** : poids du gauche-droite gardés (économie 1, société 2, souveraineté 0,5, écologie 0,5) ; la proposition de l'audit de les retirer n'est pas retenue ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
- **2026-11-16** : arbitre q2 = vrai arbitrage (litiges seuls, lectures A/B anonymes avec leurs probabilités ; réponse, confiance et raison) au lieu d'un troisième lecteur ; quatre groupes de questions réécrits, relus par une passe ciblée ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
- **2026-11-11** : l'accès aux droits selon le statut fait partie de l'axe immigration (« Étrangers : accueil et droits ») et ne compte plus à part dans le composite société, appliqué dès q1 ; protection contre les discriminations comptée en indicateur de fréquence (fiche candidat), règle q2 sur l'axe société au passage à q2 ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).

## À faire (état au 2026-11-11)

1. **Q2** : fait, q2 remplace q1 (renotation complète approuvée et faite le 2026-11-16) ; qui lit : drex-max, puis pplx-decider, Terra sur la file `Q2.motifs_arbitrage` ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
2. **Q2** : renotation complète faite le 2026-11-16 (lecteurs 10,62 $, arbitre en six batchs 10,29 $). Questions réécrites le 2026-11-16 (`degre`, `portee`, `a_menages`, classes de revenu, `soc_autorite`, `soc_libertes` ; méthode `essai-q2-v6`), passe ciblée, nouvel arbitre (litiges seuls, raison affichée) et masquage enrichi prêts : à lancer sur accord, d'abord sur les 93 mesures de la relecture (`--uids`, environ 0,30 $, puis `relecture_q2_2027.py evaluer`), puis tout le corpus. Restent ensuite : vérifier à la main les lectures divergentes et les réponses à confiance basse (à recompter après le nouvel arbitrage, aujourd'hui 1 957 et 1 581) ; non-reprises de Philippe (pages redirigées vers `/programme`), densité d'Arthaud ; commit ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
3. **Audit** : sort des fichiers `*_v2*` reçus de l'audit (`essai_q2_2027_v2.py` plante sur les modèles de décision). À supprimer si l'utilisateur le confirme ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
4. **Importance** : décider si la précision (20 points) entre dans l'importance ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
5. **Votes** : phase 3 (pré-tri lexical des suggestions, arbitrage LLM plafonné), phase 4 (cohérence, axe de la constellation, décision sur l'importance), Sénat et Parlement européen. Choix à confirmer sur la mise au point ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
6. **Mélenchon** (état du 2026-11-08) : 155 mesures « non reprises » à examiner, 94 rapprochements incertains et 75 mesures à confiance basse dans le tableau de bord ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
7. **Sources** : ajouter les documents de Retailleau sur l'immigration et la sécurité (composante immigration fragile). À vérifier, non confirmé ([05](docs/suivi/05_2026-11-06_07_rangement_et_integration.md)).
8. **Chaîne hebdomadaire** : enregistrer la tâche planifiée (commande `schtasks` affichée par `boussole_2027.py planifier`, non exécutée). À confirmer ([04](docs/suivi/04_2026-11-06_q1_effort_et_chaine.md)).
9. **Constellation** : vérifier visuellement les libellés des bandes de revenu ; infobulle sur écran étroit ; autres candidats non estompés quand la vue est cadrée sur un candidat ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
10. **Arthaud** : densité faible signalée (3,1 propositions par morceau) ([08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md)).
11. **Mise en ligne** (préparée le 2026-11-18, rien de publié) : serveur adapté au proxy, paquet à liste stricte, scripts `deploiement/` et guide [docs/mise_en_ligne_2027.md](docs/mise_en_ligne_2027.md). Restent : choisir le VPS et le domaine, écrire les mentions légales (le paquet est refusé sans elles), essayer les scripts sur un vrai VPS.

## Index des sous-fichiers

| Fichier | Période | Contenu |
|---|---|---|
| [01](docs/suivi/01_2026-11-04_05_corpus_et_scoring_jev.md) | 2026-11-04 et 05 | Journal de démarrage, corpus, sélection, audit et corrections du scoring Jev, axes, runs, extension aux thèmes culturels |
| [02](docs/suivi/02_2026-11-05_constellation_revision_arbitrage.md) | 2026-11-05 | Première constellation, révisions v2 et étendue, arbitrage aveugle Jev / Haiku, axe économique resserré |
| [03](docs/suivi/03_2026-11-06_constellation_descripteurs_pipeline.md) | 2026-11-06 | Refonte visuelle, descripteurs factuels, pipeline unifié, base et tableau de bord, rapprochement des mesures |
| [04](docs/suivi/04_2026-11-06_q1_effort_et_chaine.md) | 2026-11-06 | Questionnaire q1 (pilotes, batch, comparaison low / medium / high), centre des marges, axe gauche-droite, chaîne complète |
| [05](docs/suivi/05_2026-11-06_07_rangement_et_integration.md) | 2026-11-06 et 07 | Rangement du dépôt, file de validation, positions fragiles, intégration des propositions restantes |
| [06](docs/suivi/06_2026-11-07_contexte_lexique_importance.md) | 2026-11-07 | Axes pondérés par la fiabilité, essais de contexte et de lexique, relecture contextuelle, importance moyenne |
| [07](docs/suivi/07_2026-11-07_08_comparaison_modeles.md) | 2026-11-07 et 08 | Comparaison de modèles (Terra, Luna, Sol, Sonnet, Qwen, DeepSeek), accès aux droits précisé, relecture complète en contexte-v2 |
| [08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md) | 2026-11-07 à 09 | Votes à l'Assemblée, constellation (survols, marges, fiche), parcours des pages, pages publiques et contributions, signalements, niveau de revenu |
| [09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md) | 2026-11-10 et 11 | Review de la notation, modèle de décision drex-max, centre des candidats, questionnaire q2 (essais, étalons, institutions, portée), audit externe |

## Journal (démarrage)

Entrées détaillées dans [docs/suivi/01](docs/suivi/01_2026-11-04_05_corpus_et_scoring_jev.md#journal). Les suivantes sont dans les sous-fichiers de leur période.

- 2026-11-04 : pipeline de corpus, OCR, extraction des 14 candidats, règles d'attribution, mise à jour amont.
- 2026-11-05 : `precision_loop_2027.py`, `selection_scoring_2027.py`, `update_corpus_2027.py`, premier run complet de corpus.
