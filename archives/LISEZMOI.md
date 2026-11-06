# Archives

Ancien code et anciens résultats, gardés pour l'historique (rangement du 2026-11-06). Rien ici n'est utilisé par le pipeline courant (`boussole_2027.py`).

- `code/` : ancienne chaîne et ses tests.
  - `axes_2027.py` : notation directe des axes.
  - `revision_2027.py` : seconde lecture des notes Jev peu fiables.
  - `relecture_ciblee_2027.py` : relecture eco et coût.
  - `descripteurs_corpus_2027.py`, `pilote_descripteurs_2027.py` : annotation par descripteurs, remplacée par le questionnaire `q1`.
  - `selection_scoring_2027.py`, `precision_loop_2027.py`, `renotation_eco_2027.py`.

  Les fonctions encore utiles ont été reprises dans `commun_2027.py`. Pour relancer un script archivé, le recopier à la racine : il importe les modules actifs.
- `pages/` : anciennes pages (`visualisation_programmes_2027.html`, `exemples_idees_2027.html`).
- `donnees/` :
  - versionnés : contextes de scoring et sélections ;
  - ignorés par git : anciens résultats, caches et états de batch, dont `cache_scores.json`, le cache Jev historique, à ne pas écraser.
- `pilotes/` (ignoré par git) : rapports des pilotes et comparaisons d'effort.
