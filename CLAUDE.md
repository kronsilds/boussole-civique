# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vue d'ensemble

Pipeline Python (sans framework) qui lit les programmes des candidats à la présidentielle 2027, en extrait des propositions sourcées, les fait scorer par LLM (OpenRouter) et produit un JSON consommé par une page HTML de visualisation. Le code est en français (docs, messages, identifiants de données). Le guide d'exécution détaillé, source de vérité pour les options CLI, est [guide_pipeline_2027.md](guide_pipeline_2027.md).

Le dossier `upstream_repo/` est un **clone git d'un projet tiers** (`coucou123212321232123/presidentielle-2027-comparateur`, app React/Vite statique) : il sert uniquement de source de données (`upstream_repo/public-data/data-v2.json`, liens vers les programmes). Il n'est pas versionné ici (le répertoire racine n'est pas un dépôt git) ; ne pas y modifier de code. [audit_repo_presidentielle_2027.md](audit_repo_presidentielle_2027.md) et [presidentielle_2027_data_v2_structure.json](presidentielle_2027_data_v2_structure.json) décrivent son bundle.

## Commandes

Python 3.10+, dépendance unique `pypdf[fonts]` (`python -m pip install -r requirements.txt`). Shell : PowerShell.

```powershell
# Tests (aucun appel réseau/payant : API simulées)
python -m unittest -v test_programme_corpus_2027 test_pipeline_scoring_2027
python -m unittest -v test_pipeline_scoring_2027.NomClasse.nom_test   # un seul test

# Parcours documentaire (ordre : collecter -> extraire -> exporter -> scorer)
python .\programme_corpus_2027.py inventory|collect|reparse --repo-dir .\upstream_repo      # sans LLM
python .\programme_corpus_2027.py ocr --repo-dir .\upstream_repo --max-calls 0              # OCR optionnel (payant si >0)
python .\programme_corpus_2027.py extract --repo-dir .\upstream_repo --candidate arthaud --max-documents 1 --max-calls 3
python .\programme_corpus_2027.py export --repo-dir .\upstream_repo --out .\propositions_programmes_2027.json [--allow-partial]
python .\pipeline_scoring_2027.py --input .\propositions_programmes_2027.json --llm --context-file .\contexte_programmes_2027.json --cache-file .\cache_programmes_2027.json --out .\donnees_programmes_2027.json

# Visualisation : servir le dossier puis ouvrir visualisation_programmes_2027.html (donnees_2027.json chargé via HTTP, pas file://)
python -m http.server 8000
```

## Architecture

- [programme_corpus_2027.py](programme_corpus_2027.py) : sous-commandes `inventory/collect/reparse/ocr/extract/export`. Écrit dans `corpus_programmes/` (`manifest.json`, `documents/` nommés par SHA-256, `texts/`, `ocr/`, `extractions/`). Tout est mis en cache par empreinte : relancer une commande ne repaie pas ce qui est déjà fait ; un document modifié invalide son extraction.
- [pipeline_scoring_2027.py](pipeline_scoring_2027.py) : ingestion (`--input/--url/--repo-dir/--sync-repo`), adaptation du bundle v2 (`adapt_v2_bundle`), scoring Jev Decisions ou modèle chat, seconde lecture web optionnelle, file de révision (`scoring_review_queue.json`), cache différentiel (`cache_scores.json`), écriture de `donnees_2027.json`.
- [scoring_context_2027.py](scoring_context_2027.py) : snapshot de contexte réutilisable (`contexte_scoring_2027.json`, indicateurs France, budgets, extraits `evidence` datés) transmis à chaque scoring.
- [boussole_2027.py](boussole_2027.py) + [base_2027.py](base_2027.py) : pipeline unifié en cours de construction ([spec_pipeline_unifie_2027.md](spec_pipeline_unifie_2027.md)). `base_2027.json` est la source de vérité (uid stables `m-<candidat>-<n>`, versions, statuts), avec les décisions humaines dans `decisions_2027.json`, jamais écrasées par un run. Les étapes gratuites (calculs, file, export, bilan) régénèrent `donnees_interface_2027.json`. `boussole_2027.py integrer` intègre un nouvel export avec rapprochement des mesures ([rapprochement_2027.py](rapprochement_2027.py) ; arbitrage payant seulement avec `--max-cost`). Tableau de bord local : `boussole_2027.py tableau-de-bord`. Chaîne complète : `boussole_2027.py mise-a-jour --complet [--max-cost X --mensuel Y]` ([chaine_2027.py](chaine_2027.py)) ; annotation par le questionnaire q1 et ses compléments ([questionnaire_2027.py](questionnaire_2027.py), [annotation_2027.py](annotation_2027.py)).
- [llm_logging_2027.py](llm_logging_2027.py) : journal JSONL complet des appels dans `logs/` (clés masquées, dossier ignoré par git).
- Données : `donnees_2027.json` (sortie lue par le HTML ; la version jointe peut être un exemple synthétique), `schema_et_donnees_exemple.json`.
- Les deux gros fichiers `.py` ont chacun leurs tests (`test_*.py`) avec données synthétiques et répertoires temporaires.

## Configuration

`.env` (chargé automatiquement par le pipeline, valeurs littérales, pas de commentaire en fin de ligne, ignoré par git ; modèle dans `.env.example`) : `OPENROUTER_API_KEY`, `OPENROUTER_SCORING_MODEL` (chat JSON ou Jev Decisions comme `~typesafe/jev-latest`), `OPENROUTER_WEB_MODEL` (extraction des documents et seconde lecture web ; sans suffixe `:online`). Ne jamais lire ni afficher `.env`.

## Règles et pièges non évidents

- **Aucun appel payant par défaut** : `--llm` autorise le scoring, `--max-calls` (défaut 0) autorise l'extraction/OCR, `--web-fallback` + `--web-max-calls` autorisent la recherche web. Ne les activer que sur demande explicite de l'utilisateur.
- Le scoring sans corpus documentaire est bloqué sauf `--allow-legacy-scoring` (sinon relance ~1 295 recherches à partir des anciennes fiches).
- Jev Decisions (`/api/alpha/decisions`) et modèles chat (`/api/v1/chat/completions`) sont routés automatiquement ; `typesafe/jev-router` n'est pas un modèle de décisions. Jev ne peut pas servir de modèle web.
- Les valeurs inconnues restent `null` (jamais 0) ; coût annuel chiffré uniquement à partir d'un montant explicitement annuel ; sondages et votes parlementaires ne sont jamais déduits (overrides sourcés via `--overrides`).
- Les citations extraites doivent être retrouvées textuellement dans les segments collectés ; l'OCR ne retient que les annotations du parseur (`type: file`), jamais la transcription du modèle.
- Les erreurs HTTP permanentes (400/401/402/403/404/422) arrêtent le run avec code 2 en conservant le cache ; code 2 aussi pour une extraction incomplète.
- Ne pas écraser `cache_scores.json` (cache Jev historique) ; utiliser un `--cache-file` distinct pour les propositions documentaires.
