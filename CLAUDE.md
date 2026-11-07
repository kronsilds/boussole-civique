# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

Pipeline Python (sans framework) qui lit les programmes des candidats à la présidentielle 2027, en extrait des propositions sourcées, les annote à l'aveugle par LLM (OpenRouter, questionnaire `q1`), calcule leurs positions par des formules publiques et produit un JSON lu par la constellation (`web/constellation_2027.html`). Le code est en français (docs, messages, identifiants de données). Guide d'exécution détaillé, source de vérité pour les options CLI : [docs/guide_pipeline_2027.md](docs/guide_pipeline_2027.md). Suivi du projet et décisions : [SUIVI_PROJET.md](SUIVI_PROJET.md).

Le dossier `upstream_repo/` est un **clone git d'un projet tiers** (`coucou123212321232123/presidentielle-2027-comparateur`, app React/Vite statique) : il sert uniquement de source de données (`upstream_repo/public-data/data-v2.json`, liens vers les programmes). Il est ignoré par le dépôt ; la chaîne le met à jour par `git pull --ff-only` ; ne pas y modifier de code. [docs/audit_repo_presidentielle_2027.md](docs/audit_repo_presidentielle_2027.md) et [docs/presidentielle_2027_data_v2_structure.json](docs/presidentielle_2027_data_v2_structure.json) décrivent son bundle.

## Organisation

- Racine : `boussole_2027.py` (point d'entrée unique) et les modules actifs `*_2027.py`.
- `tests/` : tests ; `web/` : constellation et page du tableau de bord ; `docs/` : guide, spécifications, notes.
- `donnees/` : entrées versionnées (`sources_surcharges.json`, `sources_2027.json`, `decisions_2027.json`) et sorties ignorées par git (`base_2027.json`, `donnees_interface_2027.json`, caches, états de batch, budget). Tous les chemins viennent de `boussole_2027.chemins()` (relatifs à `--racine`).
- `archives/` : ancienne chaîne (Jev puis seconde lecture, descripteurs, boucle de précision) dans `archives/code/`, anciennes pages, anciens résultats (`archives/donnees/`, dont `cache_scores.json`) et pilotes. Ne pas l'utiliser pour le pipeline courant.
- Dossiers de travail ignorés : `corpus_programmes/`, `logs/`, `runs/`, `sauvegardes/`, `planification/`.

## Commandes

Python 3.10+, dépendance unique `pypdf[fonts]` (`python -m pip install -r requirements.txt`). Shell : PowerShell.

```powershell
# Tests (aucun appel réseau/payant : API simulées)
python -m unittest discover -s tests
python -m unittest discover -s tests -p "test_base_2027.py"      # un fichier

# Pipeline unifié
python .\boussole_2027.py plan                                       # état (gratuit)
python .\boussole_2027.py mise-a-jour                                # calculs -> file -> export -> bilan (gratuit)
python .\boussole_2027.py mise-a-jour --complet                      # chaîne complète en plan (collecte gratuite, aucun appel payant)
python .\boussole_2027.py mise-a-jour --complet --max-cost 1 --mensuel 5   # chaîne complète plafonnée
python .\boussole_2027.py annoter [--complement soc_finalite|degre_rupture | --contexte] [--max-cost X | --batch-submit --max-cost X | --batch-collect]
python .\boussole_2027.py tableau-de-bord                            # http://127.0.0.1:8765

# Constellation (lecture seule : la page et l'export, rien d'autre) : http://localhost:8000/
python .\serveur_constellation_2027.py [--reseau]
# Ne jamais servir le dossier avec « python -m http.server » : il publierait .env, les journaux et la base.
```

## Architecture

- [boussole_2027.py](boussole_2027.py) : orchestrateur (`plan`, `migrer`, `integrer`, `annoter`, `mise-a-jour`, `etape`, `decision`, `file`, `planifier`, `tableau-de-bord`) et `chemins()`.
- [base_2027.py](base_2027.py) : base unique (`donnees/base_2027.json`, uid stables `m-<candidat>-<n>`, versions, statuts), décisions humaines (`donnees/decisions_2027.json`, jamais écrasées par un run), calculs, file de validation, export, bilan, importance structurelle (sans LLM).
- [chaine_2027.py](chaine_2027.py) : chaîne complète (sources ajoutées, collecte et extraction via [update_corpus_2027.py](update_corpus_2027.py), intégration, annotation, compléments, étapes gratuites), plafonds par run et mensuel.
- [questionnaire_2027.py](questionnaire_2027.py) (questions, formules, idéologie), [annotation_2027.py](annotation_2027.py) (requêtes, cache, application), [descripteurs_2027.py](descripteurs_2027.py) (formule eco et vocabulaire repris par q1).
- [contexte_2027.py](contexte_2027.py) : méthode standard de notation, le questionnaire q1 lu avec le passage du document et le lexique (`annoter --contexte [--tous]`) ([lexique_2027.py](lexique_2027.py), `donnees/lexique_2027.json`) ; réponse « indéterminé » aux questions de sens (`Q.normaliser`).
- [rapprochement_2027.py](rapprochement_2027.py) : rapprochement des mesures d'un nouvel export (pré-tri gratuit, arbitrage LLM plafonné).
- [tableau_de_bord_2027.py](tableau_de_bord_2027.py) + `web/tableau_de_bord_2027.html` : tableau de bord local (127.0.0.1).
- [commun_2027.py](commun_2027.py) : masquage des noms (annotation à l'aveugle), identifiant court, batch OpenRouter.
- [programme_corpus_2027.py](programme_corpus_2027.py) : sous-commandes `inventory/collect/reparse/ocr/extract/export`, dans `corpus_programmes/` (cache par empreinte : relancer ne repaie rien ; un document modifié invalide son extraction).
- [pipeline_scoring_2027.py](pipeline_scoring_2027.py), [scoring_context_2027.py](scoring_context_2027.py), [export_interface_2027.py](export_interface_2027.py) : fonctions reprises par le pipeline (ingestion, champs dérivés, schéma des dimensions, requêtes HTTP, format compact de l'export). La CLI de `pipeline_scoring_2027.py` (scoring Jev) appartient à l'ancienne chaîne.
- [votes_2027.py](votes_2027.py) : votes parlementaires, phases 1 et 2. Phase 1 (`boussole_2027.py votes plan|chercher|votant|importer`) : import gratuit des scrutins officiels de l'Assemblée (`donnees/scrutins_2027.json`, ignoré) pour les votants déclarés (`donnees/votants_2027.json`, versionné). Seul accès réseau : l'archive officielle (hôte fixe, https, taille plafonnée) ; `--archive` et `--hors-ligne` n'en font aucun. Phase 2 : liens vote-mesure posés à la main dans l'onglet « Votes » du tableau de bord (classe `Donnees`, journal en ajout seulement `donnees/liens_votes_2027.json`, versionné, lié à la version de la mesure et au vote vu), exportés en `proposals[].votes` et affichés dans la fiche d'une proposition de la constellation (masqués en noms masqués). Les votes n'entrent ni dans la notation (aveugle) ni dans l'importance ni dans les positions ; ne pas les y brancher sans décision (spec §3, §6). Spec : [docs/spec_votes_2027.md](docs/spec_votes_2027.md).
- [llm_logging_2027.py](llm_logging_2027.py) : journal JSONL complet des appels dans `logs/` (clés masquées).

## Configuration

`.env` (chargé automatiquement, valeurs littérales, pas de commentaire en fin de ligne, ignoré par git ; modèle dans `.env.example`) : `OPENROUTER_API_KEY`, `OPENROUTER_SCORING_MODEL`, `OPENROUTER_WEB_MODEL`. Le modèle d'extraction de la chaîne est figé sur celui du corpus (changer : `--modele-extraction`). Ne jamais lire ni afficher `.env`.

## Règles et pièges non évidents

- **Aucun appel payant par défaut** : sans `--max-cost` (chaîne, annotation, intégration) ou `--max-calls` (corpus), tout est en plan. Ne les activer que sur demande explicite de l'utilisateur, avec un plafond.
- Un batch OpenRouter n'est pas annulable et réserve le pire cas (`max_tokens` dépend de l'effort).
- Les valeurs inconnues restent `null` (jamais 0) ; coût annuel chiffré uniquement à partir d'un montant explicitement annuel.
- Les citations extraites doivent être retrouvées textuellement dans les segments collectés ; l'OCR ne retient que les annotations du parseur (`type: file`), jamais la transcription du modèle.
- Les erreurs HTTP permanentes (400/401/402/403/404/422) arrêtent le run avec code 2 en conservant le cache.
- Les compléments du questionnaire sont hors `Q.QUESTIONS` pour garder la clé de cache des lectures payées ; ne pas y ajouter de question sans décision explicite.
- Ne pas écraser `archives/donnees/cache_scores.json` (cache Jev historique).
