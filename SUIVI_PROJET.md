# Suivi du projet (journal de reprise)

Fichier central de reprise : à lire en premier pour continuer sans relire l'historique. Le détail daté est découpé en onze sous-fichiers dans [docs/suivi/](docs/suivi/) ; ce fichier garde l'état courant, les décisions durables, ce qui reste à faire et l'index.

Dernière mise à jour : 2026-11-23 (revue critique d'Opus triée : domaines de la société et de l'Europe dans la v8, limites et fréquence nette dans la constellation ; v8 du q2 arrêtée ; audits externes du site triés et page Coulisses précisée ; critique du q2 vérifiée : sans le double comptage du degré l'ordre des candidats tient, 30 % des propositions sans axe dont environ 8 % d'oublis ; cinq candidats ajoutés au registre puis extraits, intégrés et notés en q2 : Branco, Cazeneuve, Egger, Kazib, Philippot, 1 249 mesures actives, 3,13 $ ; candidats retirés masqués au départ dans la constellation ; veille indépendante, phase 1 : flux RSS et sitemaps des sites des candidats, file de tri au tableau de bord, statut « retiré », recherche des programmes des 19 autres déclarés ; phase 0 : registre local des candidats et des thèmes, l'amont devient une veille ; page « Coulisses » de la constellation ; fiches : statut, lecture par les modèles et repères en mots factuels, étoile à branches des candidats, zone des quartiles ; collecte par navigateur pour les sites à contrôle anti-robot ; sauvegarde des données non versionnées sur E: et OneDrive ; constellation : axes en double retirés, noms et infobulles réécrits pour le grand public, guide de lecture ; références extérieures de validation vérifiées).

## Convention de mise à jour

- Une étape terminée s'ajoute au sous-fichier de sa période. Quand une période devient longue, créer un sous-fichier nommé par dates (`NN_AAAA-MM-JJ_sujet.md`), l'ajouter à l'index ci-dessous et à la chaîne « Précédent / Suivant » des sous-fichiers voisins.
- Mettre à jour ici l'état actuel et la liste « À faire » ; une décision durable va dans « Décisions durables » avec un lien vers son sous-fichier.

## État actuel (2026-11-11)

- **Corpus** : 14 candidats, 188 documents (180 avec propositions), **10 831 propositions publiées** (export du 2026-11-08). Mises à jour par la chaîne `mise-a-jour --complet` (collecte, extraction, intégration, annotation, compléments, calculs, export).
- **Notation** : questionnaire q1 pour toutes les mesures actives, lues avec le passage du document et le lexique (méthode `contexte-v2`, GPT-6.1 Terra, effort low). Compléments `soc_finalite`, `degre_rupture` et `niveau_revenu`. Jev n'est plus utilisé (2026-11-06). Détail : [docs/suivi/04](docs/suivi/04_2026-11-06_q1_effort_et_chaine.md), [06](docs/suivi/06_2026-11-07_contexte_lexique_importance.md), [08](docs/suivi/08_2026-11-07_09_votes_publication_revenus.md).
- **Constellation** (`web/constellation_2027.html`) : étoiles candidat × thème, centres axe par axe pondérés par l'importance et la fiabilité des composantes, positions fragiles signalées (fiabilité sous 70 %), pages Avertissement, Méthode, Sources et Contribuer, signalement d'erreur par proposition.
- **Tableau de bord** (`boussole_2027.py tableau-de-bord`, 127.0.0.1:8765) : validation, sources, runs, votes, signalements.
- **Votes à l'Assemblée** : phase 2 (liens vote-mesure posés à la main). Ils n'entrent ni dans la notation, ni dans l'importance, ni dans les positions.
- **Sources des candidats** (2026-11-20) : registre local `donnees/candidats_2027.json` et `donnees/themes_2027.json` ; le dépôt amont n'est plus qu'une veille dont les écarts sont listés, pas appliqués (`registre plan`, `registre reprendre`). Veille des sites (2026-11-21) : 32 flux RSS et sitemaps déclarés dans le registre (20 candidats au registre depuis l'ajout de cinq le même jour), `veille relever` remplit la file de tri de l'onglet Sources (`donnees/veille_2027.json`) ([10](docs/suivi/10_2026-11-20_veille_independante.md)).
- **Questionnaire q2** : en production depuis la renotation complète du 2026-11-16 (11 054 mesures, 20,91 $) : drex-max et pplx-decider lisent, Terra arbitre la file des désaccords ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
- **Mise à jour du 2026-11-18** : collecte, extraction et intégration faites (19 documents nouveaux, 2 modifiés, 600 propositions rapprochées avec `--forcer` après vérification des sources), puis notation q2 des 380 mesures nouvelles ou modifiées (`annoter --q2 --uids`, 187 arbitrées, 0,88 $) ; 1,14 $ au total. Base : 11 338 mesures dont 284 ajoutées (Philippe 166, Dupont-Aignan 69, Glucksmann 49), toutes notées. Restent : 10 836 mesures lues en `essai-q2-v5` contre 502 en v7 (relecture estimée à 21-32 $, à décider) ; 23 doublons de titre chez Philippe ; 380 mesures modifiées et 137 rapprochements incertains à valider ; 3 liens du RN, en erreur HTTP 307 (contrôle anti-robot Sucuri), collectés le 2026-11-19 par la collecte par navigateur : texte identique à celui déjà intégré (35 mesures actives et notées), rien de nouveau (mise à jour du 2026-11-19, 0,008 $). `donnees/budget_2027.json` ne compte que les runs de la chaîne : ni cette notation ni la renotation du 2026-11-16 n'y figurent, donc `--mensuel` sous-estime la dépense. Attention : 10 790 mesures sont encore lues en `essai-q2-v5` (1 844 en v7 au 2026-11-22) ; la passe ciblée passe avant les mesures nouvelles, donc la chaîne complète avec un `--max-cost` dépense d'abord sur cette relecture non décidée (arrivé le 2026-11-21 : 0,35 $ arrêtés, en cache). Pour un run hebdomadaire : `mise-a-jour --complet --sans-annotation --max-cost X`, puis `annoter --q2 --uids FICHIER` sur les seules mesures sans lecture q2 de leur version (lecteurs `--lecteurs-seuls`, arbitre en `--batch-submit`), puis `mise-a-jour`.

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
- **2026-11-20** : système de veille indépendant du dépôt amont ; l'amont devient une source de veille parmi d'autres ; un humain valide tout ce qui entre dans le corpus ; presse lue par la BnF en lecture humaine seulement, sans fouille ([10](docs/suivi/10_2026-11-20_veille_independante.md)).
- **2026-11-21** : déclarations et entretiens traités comme les autres sources, le rapprochement trie ; inclusion des candidats qui ont un programme écrit pour l'élection de 2027 (pas celui d'une élection passée ; citer 2027 n'est qu'un indice) ; Branco, Philippot, Egger, Kazib et Cazeneuve ajoutés au registre ; candidats retirés masqués au départ et consultables dans la constellation ; ressource BnF : Europresse, en lecture humaine ; phase 1 de la veille lancée ([10](docs/suivi/10_2026-11-20_veille_independante.md)).

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
11. **Mise en ligne** (préparée le 2026-11-18, rien de publié) : serveur adapté au proxy, paquet à liste stricte, scripts `deploiement/` et guide [docs/mise_en_ligne_2027.md](docs/mise_en_ligne_2027.md). Choix du 2026-11-21 : VPS IONOS S+ (1 vCore, 2 Go, centre de données UE, AlmaLinux 9 imposé par IONOS : scripts de `deploiement/` rendus compatibles `dnf`, Python 3.12, firewalld, SELinux, connexion en root sans sudo), domaine `atlasdesprogrammes.fr`, éditeur anonyme (particulier non professionnel, identité communiquée à l'hébergeur). Mentions légales complètes (contact@atlasdesprogrammes.fr, IONOS SARL) : le paquet est accepté. **En ligne le 2026-11-21 sur https://atlasdesprogrammes.fr** (VPS IPv4 seulement, accès `ssh atlas` par clé dédiée `id_ed25519_boussole`) : certificat Let's Encrypt, HTTP redirigé, en-têtes de sécurité, fichiers sensibles en 404, export compressé (2,5 Mo) et revalidé (304), service et Caddy actifs, SELinux en mode strict. Restent : couper la connexion SSH par mot de passe, retirer les ports Plesk 8443 et 8447 du pare-feu IONOS, file d'attente du serveur Python (5 connexions par défaut) à agrandir avant un pic de trafic.
12. **Références extérieures** (vérifiées le 2026-11-20) : Chapel Hill 2024 reste la seule référence d'experts récente ; V-Party, ParlGov et euandi écartés. À vérifier depuis un navigateur : codage de la France 2022 (NUPES en un seul programme ?) et 2024 dans MARPOR. À décider : test de stabilité sur les programmes 2022 des candidats qui reviennent (payant) ; Manifestoberta en local comme second regard sur les thèmes. Embeddings essayés le 2026-11-21 pour le rapprochement : aucun gain, lexical gardé ; recherche sémantique essayée le même jour : nettement meilleure que les mots exacts (qwen3-embedding-8b avec consigne), à décider pour le site (API ou modèle local) ; prototype dans le tableau de bord (onglet Mesures, « Par le sens ») : basculé le 2026-11-21 sur l'API (qwen3-embedding-8b, clé dédiée dans `.env.recherche` à créer par l'utilisateur, plafond mensuel), modèle local Qwen3-Embedding-0.6B int8 en secours ; votes à mesurer ([09](docs/suivi/09_2026-11-10_11_questionnaire_q2.md)).
13. **Veille indépendante** : phases 0 et 1 (flux des sites, file de tri, retrait) faites. Fait le 2026-11-21 : Branco, Cazeneuve, Egger, Kazib et Philippot au registre (`registre ajouter`) ; extraits, intégrés et notés en q2 les 21-22 novembre (Branco 822 mesures actives, Philippot 190, Cazeneuve 138, Egger 78, Kazib 21 ; 3,13 $, détail dans le [suivi 10](docs/suivi/10_2026-11-20_veille_independante.md)) ; candidats retirés masqués au départ dans la constellation. À surveiller : vote des adhérents des Écologistes sur le ralliement de Tondelier (10 au 13 décembre), puis `registre retrait` s'il est officiel ; accès au site de Révolution permanente (403 le 21 au matin, collecte passée ensuite). Reste de la phase 1 : liste des candidats (Wikipédia, parrainages), interventions parlementaires, relevé dans la chaîne hebdomadaire ([10](docs/suivi/10_2026-11-20_veille_independante.md), [spec](docs/spec_veille_2027.md)).
14. **Audits et formule q2** (2026-11-22), à décider :
    - degré compté deux fois (force minimale et ampleur) : garder la formule et l'expliquer dans Coulisses, ou la changer. L'ordre des candidats tient dans les deux variantes essayées ; seul l'étirement des extrêmes change. Recalcul gratuit ;
    - fait le 2026-11-22 (commit a1d2c2b) : taux de propositions sans axe publié dans Coulisses et dans la fiche d'un candidat, avec la dispersion, la part lue en v5 et la sensibilité du gauche – droite aux poids ;
    - **v8 du q2, arrêtée le 2026-11-23** ([docs/spec_q2_v8_2027.md](docs/spec_q2_v8_2027.md)) :
      - retenus : condition « société » élargie à la doctrine de la police et à la vie en ligne (les effectifs restent hors de l'axe), question du domaine institutionnel (décentralisation, mode de scrutin), question du statut des ménages touchés (agriculteurs à part) ; après la revue critique d'Opus, questions du domaine de l'axe société et de l'objet de l'axe Europe ou nation (commerce à part), à la place du multilatéralisme (15 questions sur 16 dans la passe) ;
      - écartés : petites entreprises séparées des ménages aisés, option « effets contradictoires » (une limite pour chacun dans Coulisses, faite) ;
      - lecture dans la même passe ciblée que la relecture v5 → v7, environ 25 à 30 $ en bornes prudentes, plan gratuit d'abord ;
      - suite : fusion de la branche de relecture humaine et ses 120 fiches, code de la v8, étalons, essai plafonné ;
    - fait le 2026-11-23 : « faisabilité » renommée « obstacle juridique » dans la constellation et le libellé de l'export (champ `feasibility` et échelle inchangés) ;
    - revue critique d'Opus triée le 2026-11-23 (chiffres reproduits sur l'export par son script). Fait le même jour :
      - phrase de la page Méthode sur la lecture à l'aveugle corrigée ;
      - quatre limites ajoutées dans Coulisses ;
      - fréquence nette de l'environnement, de la défense et des contre-pouvoirs dans la fiche d'un candidat ;
      - dimensions de revenu marquées expérimentales.
      
      À décider plus tard :
      - sensibilité aux constantes de la formule ;
      - seuil de fiabilité de 10 notes ;
      - référence humaine indépendante (2 ou 3 codeurs, environ 300 mesures) ;
      - test de la lecture à l'aveugle par fausse attribution (payant) ;
    - fusionner la branche de relecture humaine `claude/gracious-grothendieck-481bcb` (elle touche aussi `web/constellation_2027.html`).

    Détail : [11](docs/suivi/11_2026-11-22_audits_externes.md).

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
| [10](docs/suivi/10_2026-11-20_veille_independante.md) | à partir du 2026-11-20 | Veille documentaire indépendante : architecture, registre local des candidats et des thèmes (phase 0), flux des sites et file de tri, retrait, recherche des programmes (phase 1) |
| [11](docs/suivi/11_2026-11-22_audits_externes.md) | à partir du 2026-11-22 | Audits externes du site (ChatGPT, Mammouth) et corrections de la page, critique du q2 vérifiée : degré compté deux fois, propositions sans axe |

## Journal (démarrage)

Entrées détaillées dans [docs/suivi/01](docs/suivi/01_2026-11-04_05_corpus_et_scoring_jev.md#journal). Les suivantes sont dans les sous-fichiers de leur période.

- 2026-11-04 : pipeline de corpus, OCR, extraction des 14 candidats, règles d'attribution, mise à jour amont.
- 2026-11-05 : `precision_loop_2027.py`, `selection_scoring_2027.py`, `update_corpus_2027.py`, premier run complet de corpus.
