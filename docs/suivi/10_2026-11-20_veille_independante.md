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

À décider (voir la spec) : poids des déclarations et entretiens, règle d'inclusion des candidats, ressource BnF utilisée. Prochaine étape proposée : phase 1 (flux des sites, YouTube, interventions parlementaires, liste des candidats) avec file de tri dans le tableau de bord.
