# Suivi : veille documentaire indépendante (à partir du 2026-11-20)

> Sous-fichier de [SUIVI_PROJET.md](../../SUIVI_PROJET.md) (sommaire et état courant). Précédent : [09](09_2026-11-10_11_questionnaire_q2.md)

## 2026-11-20 : demande et architecture

L'utilisateur veut un système indépendant du dépôt `presidentielle-2027-comparateur`, qui fasse une veille sur les candidats, leurs programmes, déclarations et entretiens. Il a un abonnement BnF donnant accès à la presse quotidienne, à utiliser en lecture humaine, sans fouille de données.

Architecture proposée en quatre phases : [docs/spec_veille_2027.md](../spec_veille_2027.md). Phase 0 acceptée et faite le jour même.

## 2026-11-20 : phase 0, registre local (gratuit)

- Constat : la chaîne ne prenait à l'amont que les candidats, les liens de programme et les 20 thèmes.
- `registre_2027.py` et commande `boussole_2027.py registre plan|importer|reprendre|ecarter`. Fichiers versionnés `donnees/candidats_2027.json` (15 candidats dont 2 probables, 220 liens thématiques, journal) et `donnees/themes_2027.json` (20 thèmes figés), importés de l'amont au commit `acf0562`.
- `update_corpus_2027.charger_donnees` lit le registre ; l'amont n'est plus qu'une veille (pull non bloquant, écarts listés dans `donnees/veille_amont_2027.json`, ignoré par git, jamais appliqués sans `registre reprendre`). `programme_corpus_2027.py` accepte `--registre donnees`.
- Vérification : candidats et thèmes identiques à la lecture de l'amont ; étape 1 de la chaîne rejouée en plan (sources ajoutées comprises) : export identique à l'export courant (12 615 propositions, 0 différence), manifeste inchangé hors horodatages de relecture. 10 tests ajoutés (`tests/test_registre_2027.py`), 332 tests au vert.
- Piège noté dans le guide : `update_corpus_2027.py` lancé seul n'injecte pas `sources_2027.json` et réécrit les rattachements du manifeste sans ces sources (constaté pendant l'essai, manifeste restauré depuis la copie faite avant).

Prochaine étape proposée : phase 1 (flux des sites, YouTube, interventions parlementaires, liste des candidats) avec file de tri dans le tableau de bord (faite en partie le 2026-11-21, ci-dessous).

## 2026-11-21 : décisions de l'utilisateur

- Déclarations et entretiens : traités comme les autres sources (même extraction) ; le rapprochement trie (reprise d'une mesure du programme ou mesure nouvelle). Rien à changer dans le code.
- Inclusion : les candidats qui ont un programme. Définition confirmée par l'utilisateur le même jour : **il y a programme si le document parle explicitement de 2027** (publié par la campagne ou le parti soutien ; des entretiens seuls ne suffisent pas). Bertrand reste hors constellation ; les 19 autres déclarés de `meta.other_declared` sont à chercher en phase 1 (environ 1 à 2 $ par candidat de 500 mesures, extraction et lecture q2).
- BnF : Europresse. Conditions publiques introuvables ; une bibliothèque universitaire indique que son contrat interdit fouille de textes et téléchargement massif : circuit manuel de la spec maintenu.

## 2026-11-21 : phase 1 (gratuit, sans LLM)

L'utilisateur lance la phase 1 et pose une question : que faire des candidats qui cèdent leur place (Marine Tondelier, prête à rallier Mélenchon) ?

**Recherche des programmes des 19 autres déclarés** (recherche web, puis lecture des sites officiels ; les agrégateurs du type ÉlyséeScope ou votons-2027.fr ne comptent pas). Résultat noté dans `meta.other_declared[].programme_recherche` du registre (date, résultat, lien, note) :

| Résultat | Candidats |
|---|---|
| Programme qui cite 2027 | Juan Branco (« Le Projet 2027 », 845 mesures), Florian Philippot (« Projet pour la France », édition 2026-2027, 19 p.), Clara Egger (programme présidentielle 2027, 28 p.), Anasse Kazib (articles « Anasse 2027 : … », pas de document unique) |
| Cas limite | Bernard Cazeneuve : « Lettre aux Français » du 15 juillet 2026 (86 p., propositions p. 77), qui ne cite jamais 2027 |
| Rien qui compte | Asselineau (programme 2027 « publié prochainement »), Batho (texte d'orientation sans propositions), Becht, Bouamrane, Durif, Labib, Lalanne, Markovic, Mathieu, Mikolajczak, Mlekuz, Platret, Polony, Riner (programme annoncé pour plus tard) |

Les quatre ne sont pas ajoutés au registre : leur entrée déclenche une extraction et une lecture payantes au prochain run plafonné. Décision attendue de l'utilisateur.

**Règle d'inclusion** du registre réécrite (`meta.inclusion_rule`, ancienne règle gardée au journal).

**Veille des sites** : `veille_2027.py` et commande `boussole_2027.py veille plan|decouvrir|relever|ignorer`.
- Champ `veille` d'un candidat du registre : flux RSS ou sitemap (`filtre` facultatif). `veille decouvrir --ecrire` a trouvé et déclaré 25 flux pour 13 candidats (liens RSS des pages d'accueil, sitemaps de robots.txt) ; aucun flux utilisable pour Arthaud et Zemmour.
- `veille relever` : robots.txt respecté, une requête par seconde et par hôte, taille plafonnée ; au premier relevé tout est marqué comme vu, seuls les articles RSS des 14 derniers jours entrent dans la file (la date d'un sitemap change à chaque refonte) ; un même titre sur le site du candidat et celui du parti ne compte qu'une fois ; repli tolérant pour un RSS au XML invalide (republicains.fr). Premier relevé : 26 flux, 34 nouveautés, dont la présentation du projet économique 2027 de Dupont-Aignan et les plans pauvreté et enfance de LFI.
- File de tri dans l'onglet Sources du tableau de bord (et carte à l'accueil) : *Reprendre* remplit « Ajouter un document » (l'élément passe « ajouté » à l'enregistrement), *Ignorer* avec un motif. Vérifié dans le navigateur (reprise remplie, aucune erreur).
- YouTube écarté : son robots.txt interdit `/feeds/videos.xml`. Piste : l'API YouTube Data officielle (clé gratuite). Lutte ouvrière : son flux RSS dépasse 25 Mo, retiré.

**Retrait d'un candidat** : `registre retrait ID --date --source [--soutien ID] [--note] | --annuler` ; statut `retire`, bloc `retrait` (date, source, candidat soutenu, statut d'avant), journal. Un candidat retiré n'est plus relevé ; ses mesures restent dans la base. Seul un retrait officiel compte : Tondelier reste candidate jusqu'au vote des adhérents (10 au 13 décembre 2026). Affichage dans la constellation : décidé et fait le même jour (ci-dessous).

Tests : `tests/test_veille_2027.py` (9), 341 tests au vert.

## 2026-11-21 : cinq candidats ajoutés, affichage des retirés

Décisions de l'utilisateur : la règle vise **les programmes de la prochaine élection, pas les anciens** (citer 2027 n'est qu'un indice) ; ajouter Branco, Philippot, Egger et Kazib ; accepter Cazeneuve (« Lettre aux Français ») ; candidats retirés masqués au départ et consultables.

- **`registre ajouter FICHES.json [--source]`** (`registre_2027.ajouter_candidat`) : fiche au format du registre, vérifiée avant toute écriture (identifiant, champs, couleur, URL de la candidature et des documents, thèmes) ; marquée `origine: registre` (pas signalée comme absente de l'amont) ; retirée de `meta.other_declared` (rapprochement par le nom), sa `programme_recherche` suit ; journal `candidat_ajoute`. `meta.inclusion_rule` réécrite (journal `regle_inclusion`).
- Fiches ajoutées (vérifiées le 2026-11-21, photos non renseignées) :

| Candidat | Document collecté | Note |
|---|---|---|
| Juan Branco (Les Ruches) | page « Le Projet 2027 » de ruches.org (texte intégral, 845 mesures) | le PDF « La Voie » n'est pas collecté (mêmes mesures) |
| Bernard Cazeneuve (La Convention) | « Lettre aux Français », PDF du 15 juillet 2026 | déclaration au Figaro le 28 avril 2026 |
| Clara Egger (Solution démocratique) | programme présidentielle 2027, PDF du 4 novembre 2026 | candidature du 20 avril 2026 |
| Anasse Kazib (Révolution permanente) | trois articles « Anasse 2027 : … » (28 heures, élus révocables, expropriation de Total) | pas de document unique ; les suivants viendront par la veille |
| Florian Philippot (Les Patriotes) | « Projet pour la France » 2026-2027, PDF du 30 septembre 2026 | candidature du 9 mai 2026 |

- Veille : 7 flux ajoutés (sitemaps de ruches.org et la-convention.fr, RSS et sitemap de solutiondemocratique.fr et les-patriotes.fr, RSS de revolutionpermanente.fr filtré sur « Anasse|Kazib ») ; premier relevé : 4 nouveautés. Le site de Révolution permanente a répondu 403 à tous les clients après quelques requêtes (blocage probablement temporaire) : si la collecte du corpus échoue aussi, l'hôte peut passer par le navigateur (`navigateur` de `donnees/sources_surcharges.json`).
- Coût : rien n'est payé à l'ajout ; extraction et lecture q2 au prochain `mise-a-jour --complet --max-cost X` (ordre de grandeur : 1 à 2 $ pour 500 mesures, Branco seul en a environ 845).
- **Affichage des retirés** : l'export porte `status` et, pour un retiré, `retrait` (date, soutien, source), relus dans le registre à chaque export (`base_2027.statuts_du_registre`). Constellation : retirés masqués au départ, rangés sous « Candidatures retirées » dans la légende, « Tous » n'affiche que les candidats en lice, un clic affiche un retiré avec une teinte grisée ; infobulle et fiche : « Candidature retirée le …, soutien : … » ; sous-titre : « (et N candidatures retirées) ». Vérifié dans le navigateur sur une copie de l'export où Tondelier est marquée retirée (aucune erreur de console).
- Tests : `tests/test_veille_2027.py` (ajout, vérification avant écriture, écart d'amont, statut et retrait exportés) ; 351 tests passent.

## 2026-11-21 et 22 : extraction et notation des cinq candidats (plafond 5 $ donné par l'utilisateur)

| Étape | Résultat | Coût |
|---|---|---|
| `mise-a-jour --complet --max-cost 5` | collecte (7 documents nouveaux, 40 modifiés : pages de Dupont-Aignan, Lisnard, Philippe, Ruffin, Villepin ; le PDF archivé de LFI en erreur), extraction de 117 morceaux, puis arrêt de sécurité (2 653 propositions à rapprocher, code 1) | 0,51 $ |
| relance `--forcer --max-cost 4.49` | intégration : 1 291 mesures nouvelles, 1 026 identiques, 48 modifiées, 31 précisées, 324 non reprises, 5 incertaines | 0,13 $ |
| même run, lecture q2 | **erreur** : la chaîne lit d'abord la passe ciblée des 10 534 mesures encore en v5 (relecture v5 → v7 non décidée), avant les nouvelles ; arrêtée à la main après environ 1 080 mesures de drex-max (en cache, utiles si la relecture est décidée) | 0,35 $ |
| `annoter --q2 --lecteurs-seuls --uids` (1 378 mesures sans lecture q2 de leur version) | drex-max complet ; pplx-decider arrêté par une coupure réseau à 1 h 23 (3 échecs de suite) puis repris sur les 419 restantes | 1,47 $ |
| `annoter --q2 --batch-submit --max-cost 2.5` puis `--batch-collect` | Terra arbitre les 684 litiges en batch (69 requêtes, environ 50 minutes) | 0,68 $ |
| `mise-a-jour`, `sauvegarder` | calculs, file, export ; archive vérifiée sur E: et OneDrive | 0 |

- Total : **3,13 $** sur les 5 $. `donnees/budget_2027.json` ne compte que le premier run (0,51 $) : le run arrêté à la main et les commandes `annoter` n'y sont pas.
- Mesures actives des nouveaux candidats dans l'export : Branco 822, Philippot 190, Cazeneuve 138, Egger 78, Kazib 21 (le rapprochement a fondu les doublons d'extraction). Base : 12 634 mesures (12 105 actives, 529 non reprises), toutes lues en q2 ; 1 844 en méthode v7, 10 790 encore en v5.
- Bilan qualité de l'extraction : densité élevée chez Branco (56 propositions par morceau, page très dense), faible chez Kazib (3 articles courts). Le site de Révolution permanente, en 403 le matin, a été collecté normalement au run.
- File de validation : nouvelles mesures 8 742, divergences de lecture 2 099, confiance basse 1 727, non reprises 529, modifiées 454, rapprochements incertains 142.
- Leçon : tant que la relecture v5 → v7 n'est pas décidée, ne pas laisser la chaîne complète annoter avec un `--max-cost` (voir `SUIVI_PROJET.md`, mise à jour du 2026-11-18).

