# Suivi du projet (journal de reprise)

Fichier de reprise : à lire en premier pour continuer sans relire la conversation. À mettre à jour à chaque étape terminée.
Dernière mise à jour : 2026-11-07 (interface constellation ; lecture avec contexte généralisable).

## État du corpus (fait)

- Extraction complète des 14 candidats avec `anthropic/claude-haiku-5.5` (modèle par défaut dans `.env` via `OPENROUTER_WEB_MODEL`). Coût total d'extraction ≈ 4 $.
- Dernier export : `propositions_programmes_2027.json` = **10 776 propositions** sourcées (export partiel).
- Propositions par candidat : Tondelier 3 227, Roussel 1 006, Retailleau 1 020, Dupont-Aignan 925, Le Pen 849, Attal 744, Ruffin 728, Mélenchon 629, Lisnard 590, Villepin 583, Glucksmann 357, Philippe 237, Zemmour 63, Arthaud 55. Bertrand : aucun document dans le corpus (l'amont lui prête 33 mesures).
- Lacunes connues et acceptées : page vidéo de Philippe sur les retraites (`c28fc22f…`, transcription requise, hors pipeline) ; pages sans texte = photos ou pages blanches (confirmé par OCR et en image, 40 pages sans texte restantes).
- Exclusions (`sources_surcharges.json`) : contre-budget RN 2026 exclu ; lien Glucksmann remplacé par `projet-placepublique-acte1.pdf`.
- Règles d'attribution retenues : un document rattaché à un seul candidat lui est attribué (« nous » inclus) ; rejet par proposition (citation inexacte, thème/candidat inconnu), correspondance tolérante des citations, doublons fusionnés à l'export.

## Outils construits

- `programme_corpus_2027.py` : inventory/collect/reparse/ocr/extract/export (+ `--max-tokens`, `--max-download-mib`, surcharges de sources).
- `update_corpus_2027.py` : mise à jour automatisée (pull amont, collecte, plan chiffré, OCR + extraction avec relances réseau et budget `--max-cost`, export, bilan qualité). Sans `--max-cost`, aucun appel payant. Documenté dans `guide_pipeline_2027.md`.
- Correctif important : un HTML dont seul le bruit brut change (jeton Cloudflare) garde son empreinte et ses extractions (`collect`).
- Tests : `python -m unittest -v test_programme_corpus_2027 test_pipeline_scoring_2027 test_update_corpus_2027` (112 tests OK).

## Analyses déjà faites

- Contrôle qualité : Tondelier (3 227) = volume réel (programme de ~200 pages), pas de gonflement. Roussel : 13 morceaux vides légitimes (doctrine, analyse).
- Écart avec l'amont (1 295 mesures) : l'amont **sélectionne** ~5 mesures par thème et par candidat (médiane 5, max 12, 20 thèmes) ; notre extraction est **exhaustive** (médiane 18 par thème et candidat, max 407). Rapport nous/amont : 1,5 (Arthaud) à 28 (Tondelier), lié à la taille du document.
- Biais de volume : réel pour la visualisation (une bulle par proposition) et pour toute statistique brute. `pipeline_scoring_2027.py` ne fait pas d'agrégation par candidat (le biais n'y est ni introduit ni corrigé).

## Décisions de l'utilisateur

- Visualisation en **constellation** : afficher les thèmes (étoiles) avec moyenne des scores des propositions et écart-type comme halo ; zoom pour ouvrir les propositions d'un thème. Même nombre d'éléments par candidat.
- Sélection des propositions à scorer : **par précision** (l'importance est un axe à scorer, pas un critère de sélection).
- Cible : environ 10 à 15 propositions par thème et par candidat (≈ 1 400 au lieu de 10 776).
- Garder les 20 thèmes (les changer invalide le cache d'extraction) ; couche d'affichage possible en ~8 familles (économie/travail, social/santé, écologie/énergie, sécurité/justice, institutions/Europe…), à valider.
- Aucun appel payant sans plafond explicite de l'utilisateur.

## À faire (dans l'ordre)

1. ~~Sélection par précision~~ FAIT : `selection_scoring_2027.py` (heuristique gratuite, quasi-doublons écartés) → `selection_scoring_2027.json`. Résultats : 12 par thème = 2 623 propositions ; 8 = 1 842 ; 6 = 1 426 (Arthaud et Zemmour gardent presque tout : 41 et 59). Limite : l'heuristique favorise les chiffres ; elle classe à tort en « orientation générale » des mesures concrètes sans chiffre (ex. « Normes sanitaires identiques pour les produits importés »). Le choix final du N (6, 8 ou 12) reste à faire avec l'utilisateur ; la précision pourra être re-scorée par LLM comme dimension.
2. **Décision (2026-11-05) : N=8 par thème**, précision ajoutée au scoring avec boucle de pioche (si heuristique et LLM divergent trop dans un groupe, on pioche d'autres propositions). FAIT côté code : `precision_loop_2027.py` (+ tests) = étape séparée qui note la précision 0-100 par LLM (lots de 20, cache `cache_precision_2027.json`), pioche (moitié ordre heuristique, moitié hasard) tant que l'écart moyen > `--tolerance` 25, sélectionne les 8 plus précises selon le LLM → `selection_precision_2027.json`. Plan complet : 261 groupes, 1 842 propositions au tour 1, 93 appels ≈ 1,1 $ (+ jusqu'à 50 % pour les tours suivants). Choix volontaire : la précision n'est PAS dans `DIMENSIONS` du scoring existant (couplage Jev/validation/HTML en ~15 endroits) ; elle est fusionnée ensuite. **Pilote fait (Retailleau + Arthaud, 169 propositions, 11 appels, 0,012 $ soit ~0,001 $/appel, 0 erreur)** : LLM cohérent, divergence due à l'heuristique (nombres en lettres « six mois », unité « habitants » non reconnus) → heuristique corrigée (`NUMBER_UNIT`). Le run complet coûterait ~0,1-0,2 $ (le plan affiche encore 1,1 $ car `--cost-per-call` vaut 0,012 par défaut : l'abaisser à ~0,002). **Run complet FAIT (2026-11-05)** : 89 appels, 0,104 $, 0 erreur, 3 tours, 46 propositions piochées en plus, 21 groupes/261 encore en forte divergence (>25). Sortie `selection_precision_2027.json` : 1 842 propositions retenues (878 précis, 780 chiffré, 184 orientation générale) ; précision moyenne par candidat de 34 (Arthaud) à 73 (Tondelier). Prochaine étape : lire `pipeline_scoring_2027.py`, estimer et scorer ces 1 842 propositions (plafond à fixer).
2b. ~~Lire `pipeline_scoring_2027.py`~~ FAIT (voir Audit) ; corrections proposées : problèmes 1 et 2 d'abord, puis pilote de scoring (--limit ~30). Ancien libellé : pour estimer le coût du scoring de la sélection (aucun appel payant avant accord et plafond).
3. Maquette de la visualisation constellation sur données de test (précautions : effectifs faibles affichés via luminosité/taille, thème sans proposition = inconnu et jamais 0, ne pas sommer le budget par thème, moyenne pondérée par l'importance avec option simple).
4. Scoring payant de la sélection (plafond à fixer), puis intégration optionnelle dans `update` (`--score-max-cost`).
5. Points ouverts : Arthaud signalée « densité faible » (prose militante, à vérifier) ; Bertrand sans document ; Philippe retraites (vidéo).

## Audit du pipeline de scoring (2026-11-05, lecture + essai à blanc, 0 appel)

- Le modèle de scoring configuré est un **Jev Decisions** : seules comptent les `TYPESAFE_QUESTIONS` (16 questions par proposition, lots de 1 à 6 propositions), pas le prompt chat.
- Compatibilité : la sélection (1 842 propositions, fichier d'entrée filtré + `precision_llm`) passe à blanc dans `pipeline_scoring_2027.py` (14 candidats). `precision_llm` est conservée.
- **Problème 1 (importance circulaire)** : `programme_corpus_2027.py` (~l.838) déclare chaque citation extraite comme preuve de `programme_importance` ; `importance_evidence()` devient donc toujours vrai et l'importance est jugée à partir de la seule citation + `main_axes` génériques de l'amont → saturation probable vers « engagement précis et structurant » (~67). À corriger : retirer `programme_importance` des dimensions de la citation et fournir de vraies preuves (répétition dans plusieurs documents/sections, présence dans un résumé ou « mesures phares », rattachement aux axes du candidat).
- **Problème 2 (contexte envoyé)** : état Jev ≈ 13,6 Ko par proposition (jusqu'à 45 Ko) à cause de `scoring_context.programme_corpus` (plans de tous les documents du candidat, jusqu'à 38 Ko pour Dupont-Aignan) et de `public_finances` même hors thèmes économiques. Inutile pour noter une mesure : à réduire au seul document source.
- **Problème 3 (media_importance)** : aucun extrait médiatique daté (`evidence` médias = 0) → `media_importance` restera nulle pour tout le monde ; l'importance finale = programme seul (votes aussi nuls).
- **Problème 4 (questions)** : `rights_income` mélange direction (restriction/extension) et ampleur (micro-catégorie/universel) ; l'idéologie range en « neutre » (0) tout ce qui n'est pas économique/identitaire (institutions, culture) ce qui réduira les écarts-types de la constellation ; `tag_annonce` recoupe la précision (6 tags oui/non ajoutés par proposition, 10 questions sans eux).
- Coût du scoring Jev : tarif non connu → pilote obligatoire (`--limit`) avant de fixer un plafond.

## Corrections du scoring faites le 2026-11-05 (0 appel payant, 126 tests OK)

- **Problème 1 corrigé** : la citation n'est plus déclarée preuve de `programme_importance` ; `with_corpus_evidence` ajoute un élément `signal_structurel` avec un champ `values` (position_pct, page, page_count, section_synthese, passages, documents, formulations_proches). L'export calcule la position de chaque citation dans son document et un compteur de formulations proches (même candidat et thème, titres Jaccard > 0,6 ; 428 propositions répétées dans plusieurs documents sur 10 776).
- **Contexte allégé** : plus de plans de documents ni d'empreintes ; `programme_context` ne garde que les documents cités ou problématiques. Les règles (`CONTEXT_RULES`) et la question `programme_importance` autorisent maintenant la position comme indice combiné (jamais seule).
- **Mesure atomique et aveugle** : `blind_state()` (pipeline_scoring_2027.py) retire candidate_id, titre/URL de source, bloc programme (dont main_axes), budget du candidat, URL/empreintes des extraits, et masque noms de famille et partis dans titre, description, citation et en-têtes (pas les prénoms seuls). Appliqué aux chemins Jev (unitaire et lot) et chat. Contexte France (theme_facts, public_finances) conservé. État envoyé : 4,8 Ko en médiane (avant 13,6 Ko ; max 6,3 Ko contre 45 Ko). 0 nom restant sur les 1 842 états. Conséquence assumée : plus de rattachement aux axes du candidat pour l'importance (remplacé par les signaux structurels).
- Idées d'axes supplémentaires proposées à l'utilisateur (à trancher) : scinder l'idéologie (économique, sociétal, souveraineté/Europe, éventuellement écologie) avec « non applicable » possible ; instrument juridique requis (catégoriel) ; horizon temporel ; ampleur de la rupture avec le droit existant. Chaque axe ajoute des questions par proposition : pilote de coût obligatoire.

## Axes, importance structurelle et tarif Jev (2026-11-05, 0 appel payant, 136 tests OK)

- **Tarif Jev 1.14** (API publique OpenRouter `/models/typesafe/jev-1.14/endpoints`) : 0,042 $ par million de tokens d'entrée, 0 en sortie. Scoring Jev des 1 842 propositions (état anonymisé 4,8 Ko + 16 questions ≈ 4,5 k tokens) ≈ 0,35 $. Haiku 5.5 : 0,10 $/M entrée, 0,50 $/M sortie. La page web `openrouter.ai/typesafe/jev-1.14` renvoie 404 à WebFetch mais 200 à curl avec un User-Agent navigateur.
- **Importance structurelle** (`structural_importance`, programme_corpus_2027.py) : combinaison position (début haut, creux au milieu, remontée en fin, bonus section de synthèse), poids du thème chez le candidat normalisé par le nombre de thèmes couverts + insistance (propositions connexes), répétition. Poids 0,4 / 0,4 / 0,2 (hypothèse à valider). Score 13 à 69 (écart-type 11), moyennes par candidat 33-36, sauf Arthaud 44 et Zemmour 43 (documents courts). Propositions connexes = ≥ 2 mots significatifs partagés et Jaccard > 0,1 (médiane 1, 42 % à zéro). Valeurs dans `values.importance_structurelle` du signal de position envoyé au modèle. À décider : utiliser ce composite directement comme `importance_sources.programme` (reproductible, sans LLM) ou le moyenner avec la note Jev.
- **Nouveaux axes** : `axes_2027.py` (+ tests), étape séparée en lots de 10, modèle chat, anonymisée : idéologie économique / sociétale / souveraineté / écologie (-100..100, null si non applicable), instrument juridique requis (catégorie), horizon d'effet (catégorie), ampleur de la rupture (0..100), droits financiers scindés en direction (-100..100) et ampleur des bénéficiaires (0..100), plus une note d'audit. Plan complet : 1 842 propositions, 185 appels ≈ 0,56 $ (cache `cache_axes_2027.json`, sortie `axes_2027.json`). Pilote : `--limit 30`. Les axes ne sont pas dans le pipeline Jev (couplage trop fort) ; à fusionner à la fin avec la précision (`selection_precision_2027.json`) et les scores Jev.
- **Reste à faire** : ~~pilotes Jev et axes~~ FAITS (voir section suivante), runs complets, étape de fusion des trois sorties, puis visualisation constellation. Plafonds à fixer par l'utilisateur.

## Décision importance + pilotes Jev et axes (2026-11-05, 0,013 $ au total, 137 tests OK)

- **Décision utilisateur** : l'importance structurelle est utilisée **directement** comme importance programmatique. Code : `apply_structural_importance()` (pipeline_scoring_2027.py), appelée en sortie des chemins Jev et chat ; la note du modèle reste dans `score_details.programme_importance.model_value` (méthode `corpus-structure`, confiance 1,0, donc hors file de révision). Test ajouté, guide mis à jour.
- **Échantillon pilote** : `pilotes/selection_pilote_2027.json` et `pilotes/propositions_pilote_2027.json` = 30 propositions de la sélection, 14 candidats (2-3 chacun), 20 thèmes, graine 2027.
- **Pilote Jev** (commande : `--input pilotes/propositions_pilote_2027.json --llm --limit 30 --context-file contexte_programmes_2027.json --cache-file cache_programmes_2027.json --review-queue pilotes/revision_pilote_jev_2027.json --out pilotes/scores_pilote_jev_2027.json`) : 5 appels, **0,0065 $**, 0 erreur. Idéologie 30/30 (−53 à +66, gauche négative), faisabilité 26/30, droits revenus 16/30, droits statut 4/30, budget 0/30 (aucun montant annuel explicite). Importance structurelle vs note Jev : corrélation 0,63 (Jev plus dispersée, ET 18 contre 11). Défaut de l'axe idéologique unique : « fin des négociations de libre-échange » (Ruffin) classée +66 (droite), confiance 0,45. File de révision : 30/30 car `media_importance` et `budget_net_bn_year` sont toujours vides (structurel, pas un problème de scoring) ; faisabilité en confiance basse 16/30.
- **Pilote axes** (`axes_2027.py --selection pilotes/selection_pilote_2027.json --out pilotes/axes_pilote_2027.json --max-cost 0.05`) : 3 appels, **0,0068 $**, 0 erreur. Les axes scindés corrigent le cas Ruffin (éco −20, souveraineté +50). Remplissage : éco 27/30, souveraineté 15, sociétal 5, écologie 6, rupture 30, droits financiers 14. Horizon « non précisé » pour 15/30 (axe peu informatif). Points discutables : instrument « décret » pour l'arrêt des négociations de libre-échange (compétence UE), Roussel « Amérique latine via l'outre-mer » souveraineté −50 / traité.
- **Extrapolation des runs complets (1 842)** : Jev ≈ 0,40 $, axes ≈ 0,42 $. En attente d'accord et de plafond.
- Pistes : retirer de la file de révision les dimensions structurellement vides (média, budget) ; préciser dans le prompt axes que la politique commerciale relève de l'UE (instrument traité).

## Jev pour tout noter, Haiku pour réviser (2026-11-05, décision utilisateur, 147 tests OK)

- **Constat** : 7 des 16 questions Jev faisaient doublon avec `axes_2027.py` (corrélations 0,8 à 0,87 sur le pilote). Décision : une seule notation Jev avec les axes, puis seconde lecture Haiku ciblée sur les notes à confiance basse.
- **Code** : `pipeline_scoring_2027.py` (22 questions Jev : axes `eco/soc/sov/ecolo` avec question d'applicabilité, `rupture`, `income_direction`, `legal_instrument`, `horizon` ; `rights_income` = ampleur seule ; `JEV_SKIPPED` = idéologie, importances, 3 tags ; `derive_fields()` = idéologie moyenne eco/soc/sov + tags déduits ; `--selection` ; lots de 4). `scoring_context_2027.py` (`AXES_DIMENSIONS`, file sans les dimensions vides par construction, raison `disagreement`). Nouveau `revision_2027.py` (+ `test_revision_2027.py`). `axes_2027.py` conservé (le script de révision importe ses fonctions d'anonymisation), mais n'est plus une étape du parcours. Guide section D mis à jour.
- **Pilote Jev à axes** (30 propositions, `pilotes/scores_pilote_jev_axes_2027.json`) : 8 appels, **0,008 $**, 0 erreur. Accord avec les axes Haiku du premier pilote : éco 0,89, sociétal 0,84, souveraineté 0,71, écologie 0,92, rupture 0,79, direction des revenus 0,89 ; instrument 20/30 identiques, horizon 22/30. Horizon « non précisé » 23/30 (axe peu informatif). Idéologie composite vs ancienne idéologie Jev : 0,79. Les 30 propositions ont au moins une note à confiance basse (3,6 en moyenne : rupture 20, instrument 18, horizon 15, faisabilité 14).
- **Pilote révision Haiku** (`pilotes/scores_pilote_revises_2027.json`) : 7 appels, **0,013 $** (un lot rejeté puis refait après correctif : une dimension omise ne fait plus échouer le lot). Confiance déclarée par Haiku presque toujours entre 0,4 et 0,6, donc non utilisable : le critère retenu est l'accord entre les deux lectures. 106 dimensions relues, **34 divergences** : horizon 11/15, instrument 9/18, faisabilité 4/19, droits revenus 3/9, sociétal 3/6, rupture 2/20, éco 0/3. **21/30 propositions** ont au moins une divergence ; 15 sans l'horizon, 11 sans l'horizon ni l'instrument. Notes d'audit pertinentes et anonymes ; Haiku corrige de vraies erreurs (libre-échange = traité UE, droits fondamentaux = révision constitutionnelle).
- **Extrapolation à 1 842** : Jev ≈ 0,49 $, révision ≈ 0,82 $ (mon estimation précédente de 0,1-0,2 $ était fausse : toutes les propositions ont au moins une note à revoir). File humaine ≈ 1 300 propositions si l'on garde horizon et instrument fin.
- **Décisions (2026-11-05)** : horizon gardé à titre indicatif, jamais révisé ni signalé (`INDICATIVE_DIMENSIONS`) ; instrument juridique : divergence seulement si la classe change (exécutif / loi / Constitution-traité / non identifiable, `INSTRUMENT_CLASSES`). Schéma de données libre (nouvelle interface prévue) : le fichier final garde tous les axes bruts (`axes`, `score_details`, `revision`) et un bloc `dimensions_schema` (libellés, chemins, bornes, ancres, options, formules) ; `ideology` et les tags déduits ne sont que des valeurs par défaut que l'affichage peut recalculer avec ses pondérations (moyenne sur les axes non nuls). Plafonds : Jev 0,70 $, révision 1,10 $. Point à surveiller : l'idéologie moyenne atténue les mesures mixtes (taxation des transferts Le Pen : éco −46, sociétal +36, souveraineté +38 → +9).

## Runs complets et découpage de la souveraineté (2026-11-05)

- **Run Jev v1** (format à axes, 22 questions) : 1 842 propositions, 0 erreur, **0,486 $** (deux étapes : 300 puis le reste). Copie : `pilotes/scores_jev_2027_v1.json`. Moyennes par candidat plausibles (Arthaud −55 … Zemmour +41) mais souveraineté mal définie : Le Pen +16, Retailleau −2 ; l'axe mélangeait niveau de décision (national/européen) et ouverture/fermeture, avec des erreurs de lecture confiantes (VIGINUM −54, « Dépendances capacitaires » −42).
- **Révision v1** lancée sur le run Jev v1 (plafond 1,10 $) ; sortie remplacée par la v2, mais son cache reste valable pour les dimensions inchangées.
- **Décision utilisateur** : séparer la souveraineté ; garder `rights_status` mais le recentrer. Nouvelles questions (24, lots de 4) :
  - `sov` = **niveau de décision** national ↔ européen/international, commerce inclus (le protectionnisme de gauche n'est pas une fermeture culturelle) ;
  - `ouverture` (nouveau) = **flux et frontières** (entrée, séjour, asile, naturalisation, droit du sol) ;
  - `rights_status` = **accès aux droits des personnes présentes** (réservé aux nationaux ↔ universel) : distingue souveraineté inclusive (gauche) et excluante (droite).
- **Idéologie par défaut** = moyenne des composantes non nulles `eco`, `soc`, `ouverture`, `rights_status` signé ((50 − v) × 2) ; `sov` exclu (ni gauche ni droite). L'utilisateur estime que l'idéologie se joue surtout sur les marqueurs sociétaux : `dimensions_schema.ideology` propose une boussole à deux axes (X économie ; Y culturel = sociétal, ouverture, accès aux droits) et des poids par défaut par candidat économie 1/3, culturel 2/3, modifiables dans l'interface.
- **Contrôle** sur 42 propositions sensibles (0,012 $, `pilotes/scores_controle_souverainete.json`) : immigration → `ouverture`, préférence nationale → `rights_status` bas (Allocations familiales réservées : idéologie +73) ; CETA (Ruffin) : niveau national +48, idéologie −40 (au lieu de +2). Reste : VIGINUM −48 sur le niveau de décision. Le Pen et Retailleau ont réellement des mesures de coopération européenne (PIIEC, champions européens, Buy European).
- **Run Jev v2** FAIT : 1 842 propositions, 0 erreur, **0,514 $** (`scores_jev_2027.json`, 24 questions).
- **Révision v1 interrompue** (fin de session) après 0,324 $ : 27 lots en échec sur 173 appels, JSON mal formé par Haiku (liste et dictionnaire mélangés, une dimension sans confiance) ; aucune réponse tronquée (max_tokens 6 000, toutes `stop`). Correctif : analyse tolérante (dimension ou proposition invalide écartée et laissée en file), `reviews` sous forme de dictionnaire accepté, lot illisible relancé une fois proposition par proposition ; code de sortie 2 seulement s'il reste des propositions non relues. 152 tests OK.
- **Révision v2** lancée sur Jev v2 : 1 814 propositions, 6 066 dimensions, 298 en cache, 304 appels prévus ; plafond 0,75 $ (total révision ≤ 1,10 $ avec la v1).

## Comparaison Jev v1 / v2 (2026-11-05, gratuit)

- Idéologie par défaut par candidat quasi inchangée (écart-type des moyennes 27,1 → 27,0) : la moyenne par proposition reste dominée par `eco` (92 % des propositions). Le gain apparaît en agrégeant **par axe** :
  - culturel (moyenne de soc, ouverture, accès aux droits signé) : Zemmour +67, Le Pen +40, Dupont-Aignan +35, Philippe +33, Lisnard +29 … Glucksmann −25, Tondelier −33, Mélenchon −39, Roussel −42, Arthaud −68 ;
  - niveau de décision : Dupont-Aignan +52, Ruffin +16, Le Pen +2 (mesures de coopération industrielle européenne retenues), Attal −56, Glucksmann −40, Philippe −39.
- Limites : effectifs faibles (ouverture : 88 propositions au total, Arthaud 2, Ruffin 0) ; biais de sélection (8 plus précises par thème) : Retailleau ouverture −21 car ses propositions retenues sont des visas « talents tech » ; `rights_status` capte des statuts professionnels (Ruffin, travailleurs essentiels lus comme conditionnement), notes à faible confiance donc en révision. Pistes : noter les axes culturels sur toutes les propositions des thèmes concernés ; restreindre `has_rights_status` à nationalité/séjour si le bruit persiste après révision.
- **Décision interface** : l'utilisateur choisit les axes (X, Y, taille, couleur) et les poids des composites ; afficher les effectifs. `dimensions_schema._interface.selectable_axes` liste les axes.

## Extension aux thèmes culturels complets (2026-11-05, validée, plafond 1,60 $)

- Constat : N=8 limite le scoring (pas l'extraction). Sur les axes culturels, l'erreur sur la moyenne d'un candidat est d'environ ±18 avec 8 propositions contre ±8 avec 40 (écart-type ~50) ; la sélection par précision écarte les marqueurs identitaires moins chiffrés. N=10 jugé marginal.
- Décision : noter **en entier** les 6 thèmes culturels (immigration, sécurité, famille, institutions, Europe, culture), quasi-doublons écartés. `selection_scoring_2027.py --base selection_precision_2027.json --out selection_etendue_2027.json` (`extend_selection`, + test) : 1 842 de base (`selection: n8`) + **2 050** ajoutées (`selection: theme_complet`, précision heuristique) = **3 892**. Le marqueur `selection` est joint par `--selection` et exclu de l'empreinte (le cache des 1 842 reste valable).
- Règles d'usage : moyennes (jamais de somme), pondération par l'importance structurelle, formulations répétées fusionnées ; l'affichage peut se limiter à `n8`, les moyennes utilisent l'ensemble.
- Plafonds : Jev 0,75 $ (prévu ~0,59 $), révision 0,85 $ (prévu ~0,68 $). Étape 1 Jev (400 lignes) : 202 en cache, 198 notées, 0,0566 $. Run complet lancé → `scores_jev_etendu_2027.json`, puis révision étendue (cache de la révision v2 réutilisé).

## Nouvelle interface : constellation (2026-11-05, première version)

- Décisions utilisateur : une étoile = candidat × thème ; **branches = écart-type** sur X et Y ; **halo = 3e axe** au choix ; luminosité = effectif (pâle sous 10 propositions) ; couleurs de parti par candidat ; fonctions : mode noms masqués, poids des composites, vue en liste accessible, fiche détaillée ; HTML + JS sans dépendance.
- `export_interface_2027.py` : export allégé (`donnees_interface_2027.json`, 6 Mo pour 3 892 propositions ; marqueur `n8`/`theme_complet` pris dans `selection_etendue_2027.json`, car les lignes reprises du cache n'ont pas ce champ). À relancer sur la sortie révisée : `python export_interface_2027.py --input donnees_programmes_2027.json --selection selection_etendue_2027.json`.
- `constellation_2027.html` (servir le dossier : `python -m http.server`) : axes X/Y/halo sélectionnables (dont composites culturel et gauche/droite recalculés dans le navigateur avec les poids), moyenne pondérée par l'importance (option), centre de chaque candidat (moyenne de ses étoiles à poids égaux), échelle ajustée, zoom sur une étoile (propositions, taille = importance), fiche (citation, source et page, notes par axe avec confiance, méthode Jev/révisé, divergences, note d'audit), liste des étoiles sans valeur (jamais placées à 0), vue en liste triable (étoiles ou propositions, recherche), mode noms masqués (lettres et couleurs redistribuées, sources et noms masqués), thème clair/sombre, mode « comparer 3 candidats » (couleurs distinctes validées, autres en gris).
- Couleurs de parti : échouent au contrôle daltonisme et même en vision normale (RET/LIS, 14 couleurs) → identité portée aussi par la légende, les codes à 3 lettres, l'infobulle, la mise en avant au survol et le mode comparaison.
- Vérifiée dans un navigateur (Playwright) : vue générale, zoom, fiche, liste, sombre + masqué, mobile 390 px sans défilement horizontal.
- À faire : réexporter après la révision ; regroupement possible des 20 thèmes en ~8 familles ; intentions de vote (non renseignées) ; animation du zoom.

## Résultats révision v2 et retours interface (2026-11-05)

- **Révision v2** (1 842 de base) : 1 812/1 814 relues, 2 non relues, **0,674 $** (174 relances une par une, 41 lots illisibles, 27 dimensions écartées). Total révision v1 + v2 = 0,998 $ (plafond 1,10 $). Copie : `pilotes/donnees_programmes_v2_1842.json`.
- Divergences Jev/Haiku (part des dimensions relues) : sociétal 54 %, accès aux droits 38 %, instrument 37 %, économie 36 %, droits revenus 25 %, ouverture 24 %, écologie 17 %, faisabilité 15 %, niveau de décision 15 %, rupture 10 %. **947 propositions sur 1 842** ont au moins une divergence (file humaine : 967) : trop pour une relecture complète ; à prioriser (importance, ampleur de l'écart, axes affichés) ou arbitrer autrement.
- **Recentrage** : écart-type des moyennes entre candidats > dispersion interne d'une étoile (éco 28,4 vs 18,8 ; culturel 37,5 vs 25,3), les axes discriminent ; mais la moyenne est tirée vers le centre par des mesures atypiques (culturel, moyenne → médiane : Retailleau +18 → +36, Glucksmann −17 → −34, Tondelier −25 → −41, Le Pen +39 → +50) ; seules 6 % des propositions dépassent ±50 sur l'économie. Interface : statistique au choix, **moyenne robuste** par défaut (20 % extrêmes de chaque côté écartés ; la médiane pure s'aligne sur les niveaux −50/0/+50), branches = quartiles ; médiane et moyenne ± σ en option.
- **Retours interface traités** : curseurs dans la fiche (piste, pôles, valeur, confiance, méthode, anneau = note Jev initiale, badge divergence) et dans le détail d'une étoile (bande = quartiles) ; infobulle en grille alignée (valeur, axe, effectif) ; pictos de thème (emoji) sur les étoiles, la légende, les infobulles, le fil d'Ariane et la fiche (case à cocher) ; zoom animé (520 ms, transformation du tracé + axes interpolés, désactivé si « réduire les animations ») ; paramètre `?data=fichier.json` (local uniquement) pour tester un autre export.
- **Révision étendue** lancée sur `scores_jev_etendu_2027.json` (3 892 ; 1 812 en cache, ~2 022 à relire, plafond 0,85 $) → `donnees_programmes_2027.json`, puis réexport de l'interface.
- Note d'audit tronquée à 220 caractères en plein mot (`parse_reviews`) : l'interface ajoute « … » ; à corriger dans `revision_2027.py` (coupure au mot) pour les prochains runs.

## Révision étendue terminée au plafond (2026-11-05)

- `donnees_programmes_2027.json` = 3 892 propositions (Jev à axes + révision Haiku). Révision étendue : **0,849 $, plafond 0,85 $ atteint** ; 3 625/3 834 relues, **209 non relues** (dont 5 échecs) qui gardent leur note Jev ; 183 relances une par une, 54 lots illisibles. Divergences : 2 117 propositions ; file humaine restante `revision_humaine_2027.json` : 2 356.
- Interface réexportée : `donnees_interface_2027.json` (7,2 Mo, 3 892 propositions, notes révisées).
- Dépenses du 2026-11-05 : Jev ≈ 1,61 $ (pilotes 0,015 ; v1 0,486 ; contrôle 0,012 ; v2 0,514 ; extension 0,586), axes Haiku (pilote) 0,007 $, révision ≈ 1,86 $ (pilote 0,013 ; v1 0,324 ; v2 0,674 ; étendue 0,849). Total ≈ 3,5 $.
- Fin de révision (2026-11-05) : les 209 restantes relues pour 0,035 $ (39 appels, 3 lots JSON invalides rattrapés un par un). Bilan : 3 834/3 834 relues, 2 230 avec divergence, file humaine restante 2 262. Export interface régénéré. Sauvegarde avant run : `pilotes/donnees_programmes_2027_avant_reste.json`.
- Piste coût : variante OpenRouter `:batch` (Batch API, `POST /api/v1/batches`, asynchrone ≤ 24 h, ~50 % du prix : Haiku 5.5 à 0,05/0,25 $ par M tokens au lieu de 0,10/0,50). Pertinent pour une future révision complète ; non implémenté (demande soumission + attente + relance des réponses invalides en second lot).
- Le coût de la révision dépasse les estimations à cause des relances (JSON mal formé ~13 % des lots). Pistes : sortie structurée imposée (schéma JSON) ou lots de 3 ; terminer les 209 restantes ≈ 0,08 $ (accord requis).

## Journal

- 2026-11-04 : pipeline de corpus lancé, OCR, extraction des 14 candidats (Haiku), règles d'attribution, tolérance des citations, surcharges de sources, Retailleau (PDF volumineux), mise à jour amont, étape 4A/4B.
- 2026-11-05 : `precision_loop_2027.py` + tests (plan seul testé, 0 appel).
- 2026-11-05 : journal de reprise + mémoire écrits ; `selection_scoring_2027.py` et ses tests (6 tests OK).
- 2026-11-04/05 : lacunes traitées (OCR de 18 pages), `update_corpus_2027.py` créé et testé, correctif des empreintes HTML, restauration du manifeste (51 documents), premier run complet (0,044 $), analyse de l'écart avec l'amont, décisions de visualisation.

## Arbitrage aveugle Jev / Haiku (2026-11-05)

Deux échantillons disjoints de 100 propositions en divergence (stratifiés par dimension, graine 2027), 323 couples proposition × dimension, notes présentées A/B en ordre aléatoire à 8 arbitres Claude (sous-agents, aucun appel OpenRouter). Résultats : `pilotes/arbitrage_jev_haiku_2027.json`.
- Global : Haiku plus juste 68 %, Jev 24 %, les deux 5 %, aucune 2 %. Stable entre échantillons (A 69/25, B 67/23).
- Applicabilité (205 cas) : quand Haiku dit « non applicable » et Jev donne une valeur, Haiku a raison 96 % (eco, soc, rights_income, income_direction, rights_status) ; Jev note l'économie de mesures de sécurité, laïcité, probité (|valeur| moyenne 22, médiane −19 : bruit tiré à gauche). Quand Jev dit null et Haiku donne une valeur : 50/50 (faisabilité : Haiku ; effets sur les revenus : Jev).
- Intensité (58) et instrument juridique (60) : plus partagé (Jev 31-38 %, Haiku 43-47 %, « les deux » 12-17 %) ; décret vs loi souvent ambigu.
- Confiance Jev : ≥ 0,50 → Jev gagne 33 % ; 0,30-0,50 → 15 % ; < 0,30 → 8 %.
- Biais possible : arbitre de la même famille que Haiku ; les cas d'applicabilité sont toutefois nets.
- Pistes : trancher automatiquement en faveur de Haiku les divergences « Haiku non applicable » (1 504 couples ; la file passerait de 2 230 à 1 474 propositions) ; vérifier le filtre d'applicabilité de Jev sur les notes non révisées (eco applicable à 69 % en sécurité, 94 % en culture).
- Contre-vérification GPT-6.1 Terra (OpenRouter, raisonnement medium, sortie JSON stricte, mêmes 8 lots) : 0,196 $ (plafond 0,60 $). Haiku 60 %, Jev 31 %, les deux 5 %, aucune 4 %. Même verdict que les arbitres Claude sur 81 % des couples (applicabilité 90 %, instrument 70 %, intensité 59 %). « Haiku non applicable » : Haiku a raison 94 % (134/143). « Jev non applicable » : GPT donne raison à Jev 66 % (Claude 50 %) ; faisabilité et instrument juridique ≈ à égalité. Résultats : `pilotes/arbitrage_jev_haiku_gpt_2027.json` ; script : scratchpad `arbitrage_openrouter.py`.
- Règle appliquée (`revision_2027.RESOLVE_NOT_APPLICABLE`) : seconde lecture « non applicable » face à une note Jev → tranché pour la seconde lecture, sans relecture humaine (`score_details[dim].resolution = "non_applicable_seconde_lecture"`), sauf faisabilité. Régénéré depuis le cache (0 appel) : propositions en divergence 2 230 → 1 487, file humaine 2 262 → 1 519. Sauvegardes `pilotes/*_avant_regle_na.json`. Interface réexportée. 154 tests OK.
- Contrôle des notes Jev confiantes non relues (eco/soc, 100 propositions, 112 notes, arbitres Claude, gratuit ; `pilotes/controle_jev_non_relu_2027.json`) : soc juste 97 % ; eco juste 95 % dans les thèmes économiques mais seulement 60 % ailleurs (40 % « non applicable », sécurité 41 %, institutions 40 %), malgré une confiance Jev moyenne de 0,79. Quand l'axe s'applique, la valeur Jev est bonne (0 écart, 6,6 pts en moyenne). Les notes contestées valent −36 en moyenne : une mesure de moyens (police, justice, armée) est lue comme « extension des services publics » = redistribution.
- Cause : `has_eco` liste « dépense publique » ; Jev applique donc l'axe à toute mesure coûteuse. Question de définition à trancher. Biais : l'invite des arbitres précisait qu'un coût public ne suffit pas « sauf si le barème le dit » (résultat dépendant de l'interprétation ; 45 % des cas jugés « limites »). 1 178 notes eco Jev non relues hors thèmes économiques. Sensibilité (borne haute, en les retirant toutes) : Retailleau +6 → +14, Philippe +4 → +11, Dupont-Aignan −16 → −7, Villepin −26 → −18, Attal −9,5 → −3,5, Tondelier −38 → −31, Zemmour +36 → +27.

## Axe économique resserré et ordre de grandeur budgétaire (2026-11-05)

- Décision utilisateur : l'axe eco est réservé aux mesures dont l'objet est économique ou qui ont un effet direct sur l'économie (impôts, redistribution, droit du travail, régulation, place de l'État, niveau des services publics économiques et sociaux : santé, éducation, protection sociale, transports, logement). Le seul coût d'une mesure de sécurité, justice, défense, culture ou institutions relève de la faisabilité et du coût.
- Nouveau champ `axes.cost_estimate` (question à choix, aussi posée à Jev à l'avenir) : sans_impact_notable, cout_/gain_ faible (< 0,1 Md€/an), modere (0,1–1), important (1–10), massif (> 10), indeterminable. Indicatif, jamais additionné (mode « ticket de caisse » : « non chiffré, ordre de grandeur estimé »). Affiché dans la fiche détail de la constellation.
- Code : `has_eco` reformulé ; `revision_2027.py` (`LEGACY_GATE_INSTRUCTIONS`, `cached_review`, `review_payload`, `parse_completion`, `payload_hook`) ; nouveau `relecture_ciblee_2027.py` (+ `test_relecture_ciblee_2027.py`, mode batch) ; `scoring_context_2027.py` (`SECOND_READING_METHODS`, cost_estimate indicatif) ; export et interface. 163 tests OK. Sauvegardes `pilotes/*_avant_cout.py`.
- Chaîne : `revision_2027.py` → `donnees_revision_2027.json` (Haiku, 0 appel, 1 314 relectures retrouvées sous l'ancienne définition) → `relecture_ciblee_2027.py` → `donnees_programmes_2027.json`.
- Haiku 5.5 : aucun niveau de raisonnement demandé (défaut OpenRouter) ; il raisonne quand même (≈ 2/3 des tokens de sortie).
- Pilotes GPT-6.1 Terra medium (direct) : 2 × 50 propositions, 0,074 $, 0 réponse illisible ; ≈ 0,00074 $/proposition → 2,5 $ en direct pour tout. Option B retenue : batch OpenRouter (moitié prix).
- Batch envoyé : `batch-1793916929-VYW4Ph01bUfAdOhbdki3`, 155 requêtes, 3 842 propositions, estimation 1,42 $ (plafond 1,60 $ sur l'estimation, batch non annulable). État : `relecture_batch_2027.json`. Terminé en ≈ 2 h 10 : 155/155 lots, 0 échec, 0 dimension rejetée, **coût réel 0,91 $** (+ 0,074 $ de pilotes).
- Résultats (`donnees_programmes_2027.json`, écrit depuis le cache, 0 appel ; sauvegarde `pilotes/donnees_programmes_2027_avant_relecture.json`) : sur 1 528 notes eco hors thèmes économiques, 775 deviennent « non applicable » (`resolution = non_applicable_relecture`), 12 divergences seulement. Sécurité 310 → 34 notes eco, institutions 263 → 66, culture 186 → 73, international 67 → 29, immigration 98 → 57 ; Europe et famille gardent l'essentiel (198/243, 162/197). File humaine 1 519 → 1 513. Interface réexportée.
- Effet sur les centres (moyenne pondérée par l'importance, eco) : bien plus faible que la borne haute prévue. Philippe +3,8 → +8,9, Dupont-Aignan −17,2 → −13,5, Attal −11,4 → −8,2, Ruffin −36,5 → −39,6, Tondelier −38,3 → −36,3 ; autres < 2 pts (Retailleau +8,1 inchangé, Zemmour +35,4). Idéologie composite : Dupont-Aignan +13,3 → +23,6, Attal +9,3 → +13,9, Tondelier −31,7 → −27,5.
- `cost_estimate` (3 892) : sans impact notable 1 191, indéterminable 927, coût faible 733 / modéré 465 / important 303 / massif 40, gain faible 57 / modéré 76 / important 87 / massif 13 ; confiance médiane 0,74. Sur les 23 montants publiés, ≈ 8 estimations s'en écartent avec un motif (ex. 200 Md€ de commande publique « réorientés, pas dépensés en plus » ; 100 Md€ de fraude « part récupérable non précisée ») : l'interface affiche les deux.
- Correctif : `relecture_ciblee_2027.py` écrit désormais les sorties quand tout est en cache, sans exiger `--max-cost` ni clé. 163 tests OK.

## Refonte visuelle de la constellation (2026-11-06, 0 appel payant)

- Retours utilisateur traités dans `constellation_2027.html` : chiffres relégués à la fin (infobulle, fiche) ; libellés qualitatifs par axe (`UI` : pôles « Gauche / Droite », « Liberté, ouverture / Ordre, fermeture », bandes calées sur les ancres, nuances « plutôt ») ; confiance en mots (peu sûr, assez sûr, confiant, très confiant) ; graduations chiffrées supprimées.
- Zoom = caméra sur une scène fixe : fond, repères et étoiles restent attachés à leurs valeurs (plus de recalcul d'échelles qui faisait perdre l'orientation) ; zoom au même facteur sur les deux axes ; transition fluide 650 ms ; glisser pour se déplacer, Ctrl + molette, boutons − / + / Recadrer.
- Fond coloré par axe (dégradé pâle vers chaque pôle : rouge à gauche, bleu à droite ; sarcelle « liberté » en bas, ocre « ordre » en haut) et nom des quatre zones au bord extérieur.
- Branches (quartiles) remplacées par un nuage pointillé orienté (covariance pondérée autour de l'étoile, ≈ moitié des propositions) affiché au survol et au zoom ; au zoom, chaque proposition est reliée à l'étoile (centre de gravité) et les autres étoiles s'effacent. Propositions de même note disposées en tournesol (aucune valeur déplacée).
- Survol d'un thème dans la légende = même effet que pour un candidat (étoiles du thème mises en avant avec le nom du candidat) ; survol d'un candidat = liens de ses étoiles vers son centre.
- Réglages secondaires regroupés dans « Plus de réglages ». Three.js écarté : ~150 étoiles et quelques dizaines de points se rendent sans saccade en SVG, qui garde texte net, accessibilité clavier et zéro dépendance.
- **Vide à gauche (Arthaud ↔ Mélenchon)** : artefact de l'échelle `eco`, pas de l'affichage. Les notes collent aux ancres : 42-52 % des mesures de Roussel, Mélenchon, Tondelier, Ruffin, Glucksmann sont à −50 (« redistribution ») et presque aucune sous −60 (Arthaud seule, 54 %) ; l'ancre −100 = collectivisation, rien entre les deux. Centres : Arthaud −79, les cinq autres −39 à −45. L'axe `rupture` ne départage pas non plus (46-56). Correctif possible (payant, après le batch, accord requis) : ancres intermédiaires ±75 (« rupture : nationalisations ciblées, contrôle des prix, forte hausse du SMIC, planification ») et ±25 dans la question eco, puis renotation eco seule. Note ajoutée dans le panneau « Lire la constellation ».
- Mesure après le batch (2026-11-06, 0 appel, 1 687 notes eco affichées) : le vide reste. Centres robustes : Arthaud −73, Roussel −45, Mélenchon −43, Ruffin −42, Glucksmann −41, Tondelier −40 (cinq candidats en 5,5 pts). Chez ces cinq, la relecture GPT tasse moins sur −50 que Jev (34 % des notes entre −55 et −45 contre 58 %) mais nuance vers le centre (−40, −30), jamais vers −75 : 2 % des notes sous −60 dans les deux cas. Le batch ne relisait que l'applicabilité hors thèmes économiques ; les mesures économiques gardent leurs notes Jev/révision. Correctif ±75/±25 toujours en attente d'accord.
- Pilote préparé, **non lancé** (accord et plafond requis) : `renotation_eco_2027.py` (+ `test_renotation_eco_2027.py`, 5 tests). Barème eco à 9 repères (−100 collectivisation, −75 intervention forte ou rupture : nationalisation ciblée, contrôle des prix, forte hausse du SMIC, planification…, −50 redistribution, −25 correctif social modéré, 0, +25 allègement ciblé, +50, +75 libéralisation forte, +100) défini dans le script : la question partagée `ps.TYPESAFE_QUESTIONS["eco"]` n'est pas modifiée (sinon les clés de cache des relectures payées changent). Échantillon reproductible (graine 2027) de 60 mesures affichées des thèmes économiques : 8 par candidat de gauche resserré, 4 Arthaud, 2 pour chacun des autres. Bras témoin `eco5` (même modèle, barème actuel) pour séparer l'effet des repères de celui du modèle. GPT-6.1 Terra medium en appel direct, 120 notations, 6 appels, estimation 0,09 $. N'écrit que `pilotes/pilote_eco9_2027.json` et `cache_eco9_2027.json`. Lancement : `python .\renotation_eco_2027.py --max-cost 0.15`.
- **Pilote eco à 9 repères lancé** (2026-11-06, accord utilisateur, plafond 0,15 $, **coût réel 0,057 $**, 120/120 notes ; `pilotes/pilote_eco9_2027.json`). Résultats sur 60 mesures :
  - Le tassement vient bien du barème : avec 5 repères, GPT met 33/60 mesures exactement à −50 (plus que Jev). Avec 9 repères : 13 à −50, 20 à −25, 7 entre −60 et −75, 2 à −100.
  - Gauche : part des mesures ≤ −60 = Roussel 50 % (fonds de 500 Md€, 200 000 logements publics/an, sécurité emploi-formation, soins à 100 %), Mélenchon 12 % (blocage du prix des carburants), Ruffin 14 % (protections douanières), Tondelier et Glucksmann 0 %. Les mesures ciblées et modestes passent à −25 (tarification sociale de l'eau, gratuité du permis, pénibilité ; jugements relus, cohérents).
  - Effet sur les moyennes : les mesures fortes partent à gauche et les modestes vers le centre, donc les centres bougent peu (Roussel −49 → −41, Tondelier −47 → −39, Mélenchon −38 → −34, Ruffin −44 → −34, Glucksmann −28 → −21, Arthaud −78 → −92, eco5 → eco9). Le vide avec Arthaud demeure (il est réel) ; la différence entre candidats de gauche apparaît surtout dans la forme du nuage de propositions. 8 mesures par candidat : trop peu pour conclure sur les centres.
  - Généralisation possible : 1 687 notes eco, ≈ 0,40 $ en batch (≈ 0,80 $ en direct). Demande d'intégrer le barème eco9 dans la chaîne (décision sur la question partagée et le cache). Non décidé.

## Descripteurs factuels et note eco calculée (2026-11-06, étape 1, 0 appel)

- Décision utilisateur : décomposer la notation en questions factuelles à choix, réutilisables pour croiser les propositions et pour les autres thèmes.
- Spécification : `spec_descripteurs_2027.md`. Formules et cas types : `descripteurs_2027.py` + `test_descripteurs_2027.py` (6 tests). Non branché dans la chaîne.
- Nouvelles questions : `levier` (12 options), `public_vise` (16), `portee` (4) pour toutes les propositions ; `eco_etat` (augmente / inchangé / diminue) et `eco_distrib` (vers modestes / neutre / vers aisés ou entreprises) si `has_eco`. Réutilise `rupture` et `cost_estimate`.
- Formule : eco = 100 × sens × force du levier × ampleur ; sens = 0,75 × état + 0,5 × distribution (borné) ; ampleur = 0,55 + 0,45 × moyenne(portée, max(rupture, budget)). 20 cas types : 19 valeurs distinctes, tous à moins de 25 points du repère attendu.
- Questions ouvertes : poids état / distribution (TVA sur produits de première nécessité +17, subvention industrielle −15), levier ambigu (tarification sociale −58 ou −41), remplacement de `rights_income` par `portee`, affichage pendant la transition.
- Étape 2 proposée (accord requis) : pilote de 100 mesures (60 du pilote eco9 + 40 hors économie), 30 en double lecture, ≈ 0,10 $.
- Étape 2 préparée, **non lancée** (accord et plafond requis) : `pilote_descripteurs_2027.py` (+ `test_pilote_descripteurs_2027.py`, 7 tests ; 18 tests avec descripteurs et eco9). 100 mesures (les 60 du pilote eco9 + 8 par thème : institutions, sécurité, Europe, immigration, culture ; graine 2027), 30 relues une seconde fois dans d'autres lots. Cinq questions à choix, schéma JSON strict ; `eco_etat` et `eco_distrib` à null si `has_eco` n'est pas rempli. Rapport : stabilité par question, paliers (valeurs distinctes, part du pic), accord avec eco9 et plus gros écarts, cohérence avec la condition eco actuelle, répartitions, moyennes par candidat. GPT-6.1 Terra medium, 130 lectures, 7 appels, estimation 0,10 $. N'écrit que `pilotes/pilote_descripteurs_2027.json` et `cache_descripteurs_2027.json`. Lancement : `python .\pilote_descripteurs_2027.py --max-cost 0.20`.
- **Pilote descripteurs lancé** (2026-11-06, accord utilisateur, plafond 0,20 $, **coût réel 0,118 $**, 130/130 lectures ; `pilotes/pilote_descripteurs_2027.json`) :
  - Stabilité en double lecture (30 mesures) : levier 93 %, distribution 93 %, portée 90 %, état 87 %, public visé 80 % (le plus faible : « toute la population » / « aucun identifiable », « ménages aisés » / « grandes entreprises »).
  - Paliers : 35 valeurs distinctes sur 65 notes calculées, contre 9 pour eco9 ; pic à 0 (17 %) contre −25 (37 %) pour eco9.
  - Accord avec eco9 : 81 % des mesures à moins de 25 points (objectif 75 % atteint). Écart systématique : dépense sociale ciblée (pénibilité, leasing social, tarification sociale de l'eau) à −52/−54 contre −25. Avec AMPLEUR_MIN 0,45 : accord 85 %, mais les candidats bougent peu.
  - **Défaut principal** : les orientations seulement déclarées perdent leur sens. Mettre fin au capitalisme passe à 0, Socialisme au programme et Lutte de classe sont hors axe, et avec eux 11 mesures à 0 (objectifs sans moyen précisé). Cause : la consigne disait « décris ce que la mesure fait, pas l'intention affichée », et une déclaration ne pèse que 0,15. Effet : Arthaud tombe à −45 en moyenne sur l'échantillon.
  - Applicabilité de l'axe eco : 9 mesures notées aujourd'hui sont jugées hors axe (presque toutes déjà null en eco9), 1 dans l'autre sens ; « une norme créée, deux supprimées » manquée.
  - Répartition des leviers sur 100 mesures : dépense 28, obligation 15, déclaration 13, organisation des institutions 13, allègement 12, sanction 7. La vue « méthode de gouvernement » est donc exploitable.
  - Correctif proposé (non fait) : la question de sens porte sur l'orientation même annoncée (le levier reste le moyen réel) ; force d'une déclaration tirée de l'ambition du changement (rupture) ; relecture des seules mesures concernées (≈ 20, ≈ 0,02 $).
- **Décisions utilisateur sur les questions ouvertes** (spec §8) : (1) taille de l'État et redistribution restent deux questions distinctes, poids 0,75 / 0,5 conservés ; (2) leviers ambigus acceptés, à surveiller (pilote : 93 % de stabilité, pas de levier secondaire) ; (3) `portee` remplacera `rights_income` à la généralisation, pas de doublon ; (4) l'interface affichera uniquement la note eco calculée, l'ancienne restant dans `score_details` pour l'audit. Correctif des orientations déclarées toujours en attente d'accord.
- **Correctif des orientations déclarées** (2026-11-06, accord utilisateur, plafond 0,05 $, **coût réel 0,028 $** ; total pilote descripteurs 0,146 $) :
  - Consigne v2 (`pilote_descripteurs_2027.INSTRUCTIONS`, la v1 reste pour le cache) : levier et portée = moyen réel ; questions de sens = orientation même seulement annoncée, et un objectif économique déclaré remplit la condition eco.
  - Formule : force d'une déclaration = 0,15 → 0,85 selon `rupture` seule. Le budget en était d'abord une composante, ce qui faisait monter l'ajustement de 25 Md€ de Mélenchon à +64 ; il est retiré.
  - Mode `--correctif` : relit les 25 mesures concernées (déclarations, sens nul ou axe perdu) ; le rapport garde la première lecture pour comparaison. 16 tests (descripteurs + pilote).
  - Résultats : Mettre fin au capitalisme 0 → −85 ; Socialisme au programme hors axe → −52 ; Une norme créée, deux supprimées hors axe → +45 ; désendettement 0 → +24. Pic à 0 : 17 % → 9 % ; 41 valeurs distinctes ; accord eco9 81 % → 85 %. Moyennes sur l'échantillon (8 à 10 mesures, indicatives) : Arthaud −74, Roussel −47, Tondelier −40, Ruffin −36, Glucksmann −28, Mélenchon −23.
  - Restent hors axe, sans doute à bon droit : Lutte de classe, Mobilisation du monde du travail, ports nationaux. Écart assumé : dépense sociale ciblée à −54 au lieu de −25.
  - Prochaine étape possible : généraliser (3 892 propositions pour les descripteurs communs, 1 687 et plus pour les questions de sens ; de l'ordre de 1 à 2 $ en batch), brancher la note calculée dans l'export et l'interface, et remplacer `rights_income` par `portee`.
- **Généralisation préparée, non lancée** (accord et plafond requis) : `descripteurs_corpus_2027.py` (+ `test_descripteurs_corpus_2027.py`, 6 tests ; 190 tests du projet OK). Étapes : plan → `--batch-submit --max-cost 2.50` → `--batch-collect` (gratuit) → `--out donnees_descripteurs_2027.json`. 3 892 propositions, 25 lectures corrigées du pilote réutilisées (cache partagé `cache_descripteurs_2027.json`), 155 requêtes, estimation 1,93 $ en batch. Écrit `descripteurs`, `axes.eco` calculé et `score_details.eco` (explication, formule, `previous_value`), puis recalcule l'idéologie composite et les étiquettes (`ps.derive_fields`). Essai réel sur les 25 lectures en cache, sortie dans le dossier temporaire : correct (Mettre fin au capitalisme −85, ancienne note −100 conservée). `relecture_ciblee_2027.batch_submit/batch_collect` acceptent désormais `make_body`, `parse` et `key_fn` (défauts inchangés). Branchement export/interface et remplacement de `rights_income` par `portee` : étape suivante.
- **Batch descripteurs envoyé** (2026-11-06 10:56, accord utilisateur, plafond 2,50 $ sur l'estimation) : `batch-1793958941-OUlVV9u8ddYpHsjy42Py`, 155 requêtes, 3 867 propositions, estimation 1,93 $, non annulable. État : `descripteurs_batch_2027.json`. Suite : `python .\descripteurs_corpus_2027.py --batch-collect` (gratuit, résultats sous 24 h ; le précédent a pris ≈ 2 h 10), puis `--out .\donnees_descripteurs_2027.json`.

## Pipeline unifié et tableau de bord (2026-11-06, spécification, 0 appel)

- Demande utilisateur : unifier les pipelines pour suivre les annonces des candidats au fil de l'eau, viser l'autonomie (automatisation), et disposer d'un petit tableau de bord pour valider, retraiter et ajouter.
- **Décision utilisateur** : une seule méthode pour tout le corpus. Renotation complète avec le questionnaire unifié (≈ 3 à 5 $ en batch, accord et plafond requis le moment venu) ; notes d'initialisation conservées pour l'audit, plus affichées.
- Spécification : `spec_pipeline_unifie_2027.md`.
  - Base unique `base_2027.json` : `uid` stable, versions, statuts `active` / `non_reprise` / `remplacee` / `rejetee`.
  - Décisions humaines dans `decisions_2027.json`, en ajout seulement et liées à une version ; une nouvelle version les passe « à revoir ».
  - Étapes : sources → extraction → rapprochement (nouveau : pré-tri gratuit, puis arbitre LLM entre 0,5 et 0,85) → annotation unifiée `q1` (directe sous 200 mesures, batch au-delà) → calculs → file à motifs → export avec nouveautés → bilan de run.
  - Orchestrateur `boussole_2027.py` : plan, mise-a-jour, etape, batch, renoter, migrer, tableau-de-bord ; verrou, plafonds par run et par mois, sauvegardes.
  - Tableau de bord local (127.0.0.1, `http.server`) : accueil, à valider, mesures, sources, runs.
  - Tâche planifiée hebdomadaire.
- Phasage : 1 base, migration, décisions et étapes gratuites (0 $) ; 2 rapprochement ; 3 questionnaire `q1` (pilote ≈ 0,15 $ + renotation) ; 4 tableau de bord ; 5 orchestrateur complet et planification.
- Questions ouvertes (spec §10) : règle de publication (immédiate avec badge, ou après validation selon le motif), importance calculée sans LLM, retrait de l'horizon, fréquence, validation à plusieurs.
- **Décisions utilisateur (spec §10)** : publication immédiate avec badge « non relue », sauf mesure modifiée ou rapprochement douteux (version précédente gardée jusqu'à validation) ; importance calculée sans LLM ; horizon retiré de `q1` ; mises à jour hebdomadaires, avec ajout de documents possible à tout moment depuis le tableau de bord ; un seul validateur.
- **Phase 1 faite** (0 appel) :
  - Code : `base_2027.py` (migration, décisions, calculs, importance structurelle, file à motifs, export, nouveautés, bilan) et `boussole_2027.py` (plan, migrer, mise-a-jour, etape, decision, file ; verrou, écriture atomique, 5 sauvegardes). Tests : `test_base_2027.py` (12, dont deux runs de bout en bout) ; 202 tests du projet OK.
  - Migration réelle depuis `donnees_programmes_2027.json` + `selection_etendue_2027.json` : 3 892 mesures, `base_2027.json` (54 Mo, sans `scoring_context`).
  - `donnees_interface_2027.json` régénéré : seuls `imp` / `imp_src` (importance structurelle, quartiles 27/35/44 contre 29/36/44) et `maj` changent, plus les identifiants `m-<candidat>-<n>`. Sauvegarde : `pilotes/donnees_interface_2027_avant_base.json`. Constellation vérifiée dans le navigateur (140 étoiles, zoom, aucune erreur).
  - File : 1 488 `divergence_lectures` (héritées, priorité basse).
  - Documentation : guide (section « Pipeline unifié »), `CLAUDE.md`, `.gitignore` (sauvegardes, verrou), `.claude/launch.json` (serveur `boussole` sur le port 8000).
- Quand le batch des descripteurs sera récupéré : `descripteurs_corpus_2027.py --out donnees_descripteurs_2027.json`, puis `boussole_2027.py migrer --input donnees_descripteurs_2027.json --selection selection_etendue_2027.json`. Les `uid` sont gardés et les explications eco passent dans l'export (`expl`).
- **Tableau de bord fait** (demande utilisateur, avancé depuis la phase 4, 0 appel) :
  - Code : `tableau_de_bord_2027.py` (serveur `http.server` sur 127.0.0.1, API JSON) et `tableau_de_bord_2027.html` (vues accueil, à valider, mesures, sources, runs ; design de la constellation, clair et sombre, mobile sans défilement horizontal). Commande : `boussole_2027.py tableau-de-bord`.
  - Fonctions : décisions depuis la fiche (validation, correction d'une réponse avec note recalculée aussitôt, rejet motivé, fusion vers une mesure proche, retraitement, note) ; bouton « Appliquer » (mise à jour gratuite en tâche de fond) ; ajout de documents par URL ou fichier vers `sources_2027.json` et `corpus_programmes/depots/`, statut « en attente » jusqu'à la phase 5.
  - Sécurité : hôte local seulement, en-tête obligatoire pour écrire, écriture refusée pendant un run, aucun appel payant possible, `.env` jamais lu.
  - Tests : `test_tableau_de_bord_2027.py` (5) ; 207 tests du projet OK. Correctif : `executer` date chaque calcul (`meta.calcule_le`) pour compter les décisions pas encore appliquées.
  - Vérifié dans le navigateur sur les vraies données, en lecture seule (aucune décision réelle créée). Course entre deux rendus corrigée par un jeton de vue. Libellé « avant : … » ajouté pour l'ancienne note eco.
  - `.claude/launch.json` : configuration `tableau-de-bord` (port 8765, ou un autre si occupé).
- **Phase 2 faite : rapprochement des mesures** (0 appel payant) :
  - Code : `rapprochement_2027.py` et commande `boussole_2027.py integrer --input <export> [--plan | --max-cost X | --sans-arbitrage] [--remplace ANCIEN=NOUVEAU]`.
  - Fonctionnement : pré-tri gratuit (citation qui chevauche, puis similarité texte = moyenne d'un ratio de séquence et d'un Jaccard sur les mots), arbitre LLM pour les paires douteuses (même / précisée / modifiée / différente, à l'aveugle, en cache, plafonné, environ 0,0005 $ par paire), alias d'identifiants corpus, versions (`nature`), non-reprise par documents couverts ou remplacés. Les mesures d'un même export sont aussi rapprochées entre elles.
  - **Calibrage** sur 56 passages extraits plusieurs fois (2 745 mesures d'anciennes extractions comparées à toute la base du candidat ; vérité = citations qui se chevauchent) : bonne mesure en tête 98,5 % ; seuils retenus 0,85 (même mesure, 0,6 % d'erreurs) et 0,35 (nouvelle mesure, 2,9 % de doublons créés), 23 % de paires à arbitrer dans ce pire cas.
  - Règles : version « précisée » sans relecture ; « modifiée » → motif `mesure_modifiee` (ancienne version publiée) ; sans verdict ou confiance < 0,7 → motif `rapprochement_incertain`, non publiée avant validation ou fusion.
  - Tableau de bord : bloc « Doublon possible » avec les boutons Même mesure → fusionner, Mesure distincte → valider, Voir la mesure existante. Vérifié sur une base de démonstration (fusion testée), jamais sur les vraies décisions.
  - Performance : index des citations et index inversé des mots, élagage du ratio de séquence. Plan sur l'export complet d'extraction (10 776 propositions, 6 884 inconnues) en 2 min (contre plus de 10 au départ), environ 18 ms par proposition. Résultat informatif : 243 redites, 1 167 à arbitrer, 5 474 nouvelles parmi les propositions non retenues à la sélection (rien n'a été intégré).
  - Bugs corrigés en route : plafond d'arbitrage non cumulatif quand le coût réel n'est pas encore dans le journal ; mesures créées repérées par leur date (fragile) au lieu d'un suivi explicite.
  - Tests : `test_rapprochement_2027.py` (7) ; 214 tests du projet OK.
  - Note : un run interrompu brutalement laisse le verrou `.boussole.lock` ; `--force-verrou` après vérification.


## Phase 3 : questionnaire unifié q1 (2026-11-06)

- **Batch descripteurs récupéré** (gratuit) : 155/155 lots, 3 866 descriptions plus 25 du pilote, une manquante ; **coût réel 1,57 $** (estimation 1,93 $). `donnees_descripteurs_2027.json` écrit, puis intégré par `boussole_2027.py migrer` (uid conservés ; sauvegarde de l'export : `pilotes/donnees_interface_2027_avant_descripteurs.json`).
  - Corpus entier : 1 616 notes eco (1 687 avant), 183 deviennent non applicables, 112 apparaissent ; 136 valeurs distinctes ; 16 % à 0, des mesures jugées vraiment mixtes ou neutres (« inchangé · neutre »).
  - Positions eco (moyenne robuste, avant → après) : Arthaud −73 → −69, Roussel −45 → −44,5, Mélenchon −43 → −41,5, Ruffin −42 → −38, Glucksmann −41 → −37, Tondelier −40 → −35, Villepin −33 → −22, Zemmour +49 → +44. L'écart entre les cinq candidats de gauche passe de 5,5 à 10 points.
  - Leviers sur 3 891 mesures : dépense 896, organisation des institutions 783, déclaration 773, contrôle et sanction 347, obligation 296, allègement 292, étude 192, prélèvement 155, incitation 75, contrôle des prix 54, propriété publique 17, transfert au privé 11.
- Nouvelle option `--changement-methode` (migrer, mise-a-jour, etape) : une renotation voulue ne remplit pas la file de « déplacement fort » ni d'« axe perdu ou gagné ». La file, qui comptait environ 600 entrées de ce type après l'intégration, a été nettoyée ; elle garde 1 478 divergences héritées et 62 confiances basses.
- **Code q1** (0 appel) :
  - `questionnaire_2027.py` : 17 questions à choix, formules des cinq axes avec des forces de levier propres à chaque axe, correspondances (changement → rupture, faisabilité, accès aux droits, revenus), étiquettes calculées.
  - `annotation_2027.py` : requête à l'aveugle (identifiant envoyé sans nom de candidat), schéma strict, cache, appel direct par lots de 10 sous plafond cumulatif, batch via `relecture_ciblee`, compteur de reprise pour forcer une relecture.
  - `boussole_2027.py annoter` : plan, `--pilote`, `--uid`, `--max-cost`, `--batch-submit` / `--batch-collect`.
  - `base_2027.appliquer_q1` : toutes les notes recalculées depuis les réponses, corrections humaines comprises (les 17 questions sont corrigeables) ; explications de tous les axes dans l'export.
  - Tableau de bord adapté (libellés, « non concerné » pour les questions conditionnelles, explications par axe) ; vérifié dans le navigateur.
  - Tests : `test_questionnaire_2027.py` (10) ; 224 tests du projet OK.
- **Plans (aucun appel)** : pilote de 100 mesures (`--pilote pilotes/pilote_descripteurs_2027.json`) estimé à 0,25 $ en direct ; corpus complet (3 892) estimé à 4,87 $ en batch. Estimation à affiner avec le coût réel du pilote.
- En attente : accord pour le pilote (plafond proposé 0,35 $), puis pour la renotation complète.
- **Pilote q1 lancé** (2026-11-06, accord utilisateur, plafond 0,35 $, **coût réel 0,251 $**, soit 0,0025 $ par mesure comme estimé ; 100/100 mesures, 10 lots, 0 échec ; bilan `runs/2026-11-06_1508.md`) :
  - Accord avec la lecture des descripteurs (autre consigne, autre passage) : levier 75 %, public visé 84 %, portée 87 %, action publique 89 %, redistribution 86 %.
  - Applicabilité cohérente avec les anciennes notes : économie 73 → 71, société 22 → 18, souveraineté 15 → 14, immigration 9 → 8, écologie 29 → 25 mesures.
  - Accord à moins de 25 points avec les anciennes notes : économie 75 %, souveraineté 77 %, écologie 68 %, immigration 62 %, société 50 % (écart moyen 25). Valeurs bien réparties (économie : 36 valeurs distinctes sur 71, pic à 0 de 9).
  - Confiances < 0,5 : 15 mesures (surtout `changement` et `eco_distrib`).
  - **Défaut trouvé** : la consigne rangeait `changement` parmi les questions sur le moyen réellement prévu ; 19 déclarations sur 23 répondaient donc « statu quo », et leur force retombait à 0,15. Exemples : Mettre fin au capitalisme −100 → −6 (éco), Socialisme au programme −70 → −12, Rénovation thermique massive +50 → +12 (écologie), Pause sur Schengen +44 → +10 (immigration). C'est le même défaut que dans le pilote des descripteurs, réapparu par un autre chemin.
  - **Correctif** (0 appel) : `changement` et les questions de sens décrivent ce que la mesure vise, même seulement annoncé (avec exemples génériques), et ne valent « inchangé », « neutre » ou « statu quo » que si c'est réellement le cas. La question `changement` est reformulée. La consigne changeant, la clé de cache change aussi : les 100 mesures du pilote sont à relire (environ 0,25 $). Les annotations du premier passage restent dans la base jusque-là.
  - Écarts société relus : en partie une question de force (dépense sociale ciblée, par exemple contraception gratuite −65 → −19) ; « 20 000 places en structures adaptées » passe de −30 à +19, discutable.
- En attente : accord pour relancer le pilote avec la consigne corrigée (plafond proposé 0,35 $).
- **Question utilisateur : resserrement eco vers le centre** (descripteurs, 1 504 mesures notées avant et après) : réel mais modéré. |eco| moyen 38,4 → 35,1 ; écart-type des centres des candidats 32,0 → 30,1 ; étendue 121 → 112 ; ordre conservé. Les notes ne sont pas rabotées uniformément : 600 se rapprochent du centre, 445 s'en éloignent, celles au-delà de ±50 passent de 371 à 415. Causes : mesures mixtes à 0 (16 %) au lieu d'un rangement par défaut à −50, et plafond d'une mesure marquée sur un seul critère. Recommandation : ne pas toucher aux notes, cadrer l'affichage sur les étoiles (réglage existant de la constellation).
- **Pilote q1, second passage avec la consigne corrigée** (accord utilisateur, plafond 0,35 $, **coût réel 0,252 $** ; 0,503 $ pour les deux passages ; modèle `openai/gpt-6.1-terra`, raisonnement medium, appels directs ; réponses du premier passage gardées dans `pilotes/pilote_q1_passage1.json`) :
  - Déclarations corrigées : `changement` des 23 déclarations = réforme significative 15, refonte structurelle 4, extension modérée 4 (19 « statu quo » avant). Mettre fin au capitalisme −6 → −85 (éco), Socialisme au programme −12 → −85, Pause sur Schengen +10 → +53 (société, souveraineté, immigration), Rénovation thermique massive +12 → +85 (écologie).
  - **Plus de resserrement** (|valeur| moyenne : ancien / passage 1 / passage 2) : économie 40,9 / 33,7 / 39,7 ; souveraineté 42,3 / 38,5 / 46,5 ; immigration 55,9 / 39,8 / 57,8 ; écologie 51,1 / 40,1 / 50,9 ; société 52,1 / 39,8 / 44,9. L'ampleur du changement visé remonte l'ampleur de toutes les mesures, ce qui compense l'effet relevé par l'utilisateur.
  - Accord à moins de 25 points avec les anciennes notes : économie 78 %, souveraineté 92 %, immigration 100 %, écologie 85 %, société 50 % (les anciens extrêmes, −93 ou +89, sont modérés quand la portée est ciblée ; une seule inversion de sens sur 14, « 20 000 places en structures adaptées », cas ambigu).
  - Stabilité entre les deux passages (même texte, consigne retouchée) : questions de sens 86 à 99 %, levier 89 %, portée 81 %, coût 78 %, changement 66 % (c'est la question modifiée).
  - Poids des déclarations comparé aux mesures concrètes (|valeur| moyenne) : économie 37,6 / 38,6, société 39,7 / 43,4, souveraineté 46,5 / 46,4, immigration 57,7 / 57,8 ; écologie 65,6 / 48,0 sur 5 déclarations seulement, à surveiller sur le corpus complet.
  - Conclusion : pilote concluant. Renotation complète estimée à 4,87 $ en batch (0,00125 $ par mesure). Accord utilisateur requis, plafond proposé 6 $.

## Constellation : étoiles et propositions notées sur un seul axe (2026-11-06, 0 appel)

- Question utilisateur : beaucoup d'étoiles ou de propositions ne sont pas placées parce qu'un des deux axes ne les concerne pas ; est-ce que ça fausse le graphique ?
- Diagnostic (axes par défaut économie × société, données des descripteurs) :
  - la position d'une étoile était correcte (chaque coordonnée calculée avec toutes les propositions concernées par cet axe) ;
  - une étoile n'était dessinée que si son thème touche aux deux axes : 142 placées, 99 notées en économie seulement (fiscalité, emploi, logement…), 12 en société seulement, 8 sur aucun des deux ;
  - **le centre d'un candidat n'utilisait que les étoiles dessinées** : sa position économique ignorait ses thèmes économiques. Écarts jusqu'à 10 points : Arthaud −85 → −76 (éco) et −71 → −82 (société), un seul thème placé sur dix ; Philippe −4 → +2 et +24 → +32 ; Tondelier −33 → −38 ; Glucksmann −23 → −30 (société) ; Zemmour +49 → +45 et +75 → +68 ;
  - au zoom, les propositions notées sur un seul axe n'étaient pas dessinées, alors qu'elles comptent dans la position de l'étoile.
- **Correctifs** (`constellation_2027.html`) :
  - centre calculé axe par axe sur toutes les étoiles concernées par chaque axe (chaque thème compte autant) ; l'infobulle donne le nombre de thèmes par axe ;
  - deux bandes de marge (26 px) : sous le graphique pour l'axe horizontal seul, à gauche pour l'axe vertical seul. Les étoiles notées sur un seul axe y sont placées à leur valeur ; au zoom, les propositions sur un seul axe aussi. Infobulles explicatives ; clic vers la fiche ;
  - cadrage de la vue d'ensemble et du zoom étendu aux valeurs en marge ; repères de l'axe horizontal décalés sous la bande ;
  - aucune valeur inventée pour l'axe manquant (règle « inconnu = null ») ;
  - carte « Non placé » : nombre d'étoiles ou de propositions en marge, liste de celles qui ne relèvent d'aucun des deux axes ;
  - aide « Lire la constellation » : paragraphe « Marges » ; l'ancienne note sur le regroupement à −50, devenue inexacte avec la note eco calculée, est retirée.
- Vérifié dans le navigateur : 142 étoiles placées, 111 en marge, 14 centres ; zoom Tondelier · famille (19 placées, 84 en marge, 15 hors axes) ; centre d'Arthaud −76 / −82 conforme au calcul ; mobile sans défilement horizontal ; aucune erreur.

## Comparaison GPT-6.1 Terra effort low / medium sur le questionnaire q1 (2026-11-06)

- Demande utilisateur : essayer l'effort de raisonnement « low », annoncé moins cher, avant le batch complet.
- Code (0 appel) : l'effort entre dans la clé de cache de l'annotation, sauf « medium », pour que le cache existant reste valable (`annotation_2027.cle`) ; nouvelle option `boussole_2027.py annoter --effort low --comparer medium`, qui écrit un rapport sans rien appliquer à la base (`annotation_2027.comparer`). Collecte d'un batch avec l'effort enregistré dans son état. 10 tests OK.
- **Run** (accord utilisateur, plafond 0,30 $, **coût réel 0,223 $**, 100 mesures du pilote, 10 lots, 0 échec ; rapport `pilotes/comparaison_low_medium.json`).
- **Coût** : low 0,223 $ contre medium 0,252 $, soit −11 % seulement. Tokens produits 29 834 contre 35 512, dont raisonnement 171 contre 5 646 : le raisonnement ne pesait que 16 % ; l'essentiel est la réponse (17 réponses et leur confiance par mesure). Corpus complet en batch : environ 4,35 $ en low contre 4,87 $ en medium.
- **Qualité** (low comparé à medium, mêmes textes, même consigne) : accord par question de 73 % (coût) à 100 % (immigration) ; levier 89 %, public visé 90 %, portée 87 %, sens économiques 91 %, société 96 %, souveraineté 93 %, écologie 99 %. Axes calculés (écart moyen ; part à moins de 25 points) : économie 5,0 ; 93 % — société 0,7 ; 100 % — immigration 3 ; 100 % — écologie 2 ; 100 % — faisabilité 3,8 ; 99 % — revenus 5,8 ; 88 % — souveraineté 16 ; 69 % (4 mesures ambiguës sur 13 basculent entre « équilibre » et « national » ou « Europe »). Applicabilité identique dans 94 à 100 % des cas.
- Écarts économiques notables, sans direction systématique : Compensation intégrale des normes agricoles +55 (low) / 0 (medium), Conditions aux investissements de plus de 100 M€ −54 / −14, Gratuité ciblée dans les transports −30 / −72.
- Lecture : l'écart entre low et medium est du même ordre que celui entre deux lectures medium (stabilité 86 à 99 % sur les questions de sens). Pas de perte de qualité mesurable, mais un gain faible.
- Piste d'économie plus forte, non testée : demander une seule confiance globale et la liste des questions hésitantes au lieu de 17 confiances (sortie plus courte d'environ un tiers ?). Pilote nécessaire.
- En attente : choix de l'effort pour le batch complet (accord et plafond requis).
- **Effort high** (demande utilisateur ; plafond 0,50 $, **coût réel 0,362 $**, soit +44 % par rapport à medium ; 100 mesures, 0 échec ; rapport `pilotes/comparaison_high_medium.json`) : comparé à medium, écart moyen économie 5,2 (93 % à moins de 25 points), société 12,3 (80 %), souveraineté 11,1 (86 %), immigration 5,4, écologie 4,7, faisabilité 6,9, revenus 4,3.
- **Arbitrage à l'aveugle des désaccords** (Claude, gratuit, comme pour le contrôle des notes Jev) : 61 mesures où les trois lectures diffèrent de plus de 10 points sur un axe ou n'appliquent pas les mêmes axes ; 153 réponses en désaccord, présentées sous les étiquettes A/B/C dans un ordre aléatoire par mesure (`pilotes/arbitrage_a_juger.md`), jugées avant lecture de la correspondance (`pilotes/arbitrage_cles.json`) ; verdicts dans `pilotes/arbitrage_verdicts.json` ; 6 réponses jugées indécidables, exclues.
  - **Réponses justes sur les 147 jugées** : low 65 %, medium 59 %, high 52 %. Par type : questions de sens low 76 % / medium 59 % / high 47 % ; moyens (levier, portée, changement) 70 / 63 / 43 % ; faisabilité 62 / 54 / 50 % ; **ordre de grandeur budgétaire 30 / 57 / 78 %** (seul domaine où le raisonnement paie).
  - High est le plus souvent seul contre les deux autres (66 fois, juste 14 fois, soit 21 %), contre low 39 fois (12 justes) et medium 38 fois (6 justes). Erreurs sur les questions de sens : high 11 axes appliqués à tort, 17 mauvais sens, 8 axes oubliés ; medium 10 / 11 / 7 ; low 7 / 9 / 0. Lecture : plus de raisonnement, plus d'inférences que le texte ne porte pas.
  - Limites : un seul arbitre, et seulement les désaccords (environ 9 % des réponses ; les trois efforts répondent pareil au reste). En absolu, l'écart entre efforts porte sur 1 à 2 % de l'ensemble des réponses.
- Coût total des comparaisons : low 0,223 $ + high 0,362 $ = 0,585 $.
- Recommandation : batch complet en **low** (le moins cher, le meilleur sur les désaccords), environ 4,35 $ ; l'ordre de grandeur budgétaire, indicatif et jamais additionné, en pâtit un peu. Option : relire seulement `cout` en high plus tard.
- **Batch q1 complet envoyé en effort low** (2026-11-06 17:33, accord utilisateur, plafond 5,50 $ sur l'estimation) : `batch-1793982794-qk5pXy2YTDgqXHXYr9jU`, 380 requêtes, 3 792 mesures, estimation 4,74 $ (calée sur medium ; coût réel attendu plus bas), non annulable. État : `annotation_batch_2027.json`.
  - Avant l'envoi : les 100 mesures du pilote ont reçu leurs réponses low déjà en cache (gratuit), pour que tout le corpus soit noté avec le même effort.
  - Premier envoi refusé par OpenRouter, sans frais : il réserve le pire cas (31,65 $ avec 32 000 tokens de sortie par lot) et le solde disponible était de 18,43 $. Plafond de sortie ajusté à l'effort dans `annotation_2027.requete` (low 10 000, medium 16 000, high 32 000 ; environ 3 000 mesurés par lot en low).
  - **Récupération (gratuite) : `python .\boussole_2027.py annoter --batch-collect --effort low`**. L'effort est indispensable : il fait partie de la clé de cache utilisée pour appliquer les réponses. Ensuite `mise-a-jour` si besoin ; la renotation ne signale pas les déplacements (changement de méthode).
- **Batch q1 récupéré et appliqué** (2026-11-06) : 380/380 lots, 0 échec, 3 791 mesures ; **coût réel 3,94 $** (estimation 4,74 $). La mesure manquante (m-roussel-0236, réponse invalide) a été annotée en direct pour 0,008 $. **Corpus entier en q1 low : 3 892 / 3 892.** Sauvegarde de l'export précédent : `pilotes/donnees_interface_2027_avant_q1.json`. Bilan `runs/2026-11-06_1810.md`.
  - File : les 1 478 divergences héritées disparaissent ; 650 « confiance basse », surtout sur coût (244), ampleur du changement (144), redistribution (104), public visé (87). En ne retenant que les questions de sens : 191 mesures. Proposition : restreindre le motif aux questions de sens (gratuit, non fait).
  - Distributions (export avant q1 → après) : économie 1 617 → 1 712 notes, |v| 34,3 → 37,0, dispersion des centres 30,2 → 30,9 ; société 1 280 → 1 062, |v| 44,9 → 35,3, **dispersion 37,9 → 24,0** ; immigration |v| 48,3 → 49,9 ; souveraineté 47,0 → 43,1 ; écologie 42,2 → 47,2.
  - Déclarations et mesures concrètes équilibrées (|v| moyen) : économie 32,6 / 38,2, société 28,5 / 37,4, souveraineté 42,3 / 43,6, immigration 44,0 / 52,0, écologie 48,8 / 46,6.
  - Centres économiques (moyenne robuste pondérée, axe par axe) : Arthaud −74, Roussel −50, Mélenchon −43, Tondelier −42, Ruffin −37, Glucksmann −37, Villepin −23, Dupont-Aignan −16, Attal −10, Philippe 0, Le Pen +7, Retailleau +12, Lisnard +29, Zemmour +39.
  - **Défaut de l'axe société** : les deux questions (autorité, libertés) ne disent pas au profit de qui ni contre qui s'exerce l'autorité ; toute sanction est rangée côté « ordre ». Exemples : Ruffin +6 → +51 (13 de ses 18 mesures sociétales portent sur la probité des élus, notées environ +60) ; « Crimes de haine et thérapies de conversion au niveau européen » (Glucksmann) −55 → +69 ; Glucksmann −26 → −7, Tondelier −24 → −11, Roussel −40 → −21.
  - Règle gratuite testée et écartée : exclure de l'axe société les mesures dont le public visé est élus, administrations ou grandes entreprises (214 mesures). Trop grossière : elle retire aussi de vraies mesures pénales (« Modifier la loi Taubira », réservistes en patrouille) et ne règle pas la protection contre les discriminations.
  - Correctif proposé (accord requis) : question complémentaire `soc_finalite` (droits et égalité / ordre et sécurité / probité et contrôle des pouvoirs / autre), posée seulement aux ~1 060 mesures notées sur l'axe société. Droits et égalité : sanction comptée côté libertés ; probité : axe société non applicable ; sinon formule actuelle. Environ 0,5 $ en batch low.
- Constellation vérifiée avec les données q1 : 109 étoiles placées, 145 en marge, 14 centres, aucune erreur.
- **Complément `soc_finalite` préparé, non lancé** (0 appel) : question « au nom de quoi la mesure agit-elle ? » (droits et égalité / ordre et sécurité / probité et contrôle des pouvoirs / autre), posée seulement aux mesures dont l'axe société s'applique.
  - Formule : droits et égalité → côté libertés même pour une sanction ; probité → axe société non applicable ; ordre et autre → formule inchangée. Cas types : crimes de haine −69, sanctions de la Haute Autorité de probité hors axe, peines planchers pour violences faites aux femmes +62, cannabis −60.
  - Code : `questionnaire_2027.COMPLEMENTS` et `TOUTES` (question hors du questionnaire principal pour garder la clé de cache des lectures payées, vérifié : 100/100 lectures du pilote retrouvées) ; `annotation_2027` (complément : rubrique, schéma, cache `cache_complements_2027.json`, appel direct par lots de 20, batch, application) ; `boussole_2027.py annoter --complement soc_finalite` ; confiance d'axe calculée sur les seules questions posées ; corrections et tableau de bord sur `TOUTES`. 13 tests du questionnaire ; 227 tests du projet OK.
  - Plan : 1 065 mesures, 54 lots ; environ 0,43 $ en appel direct (résultat immédiat) ou 0,21 $ en batch. Accord requis.
- **Complément `soc_finalite` lancé** (2026-11-06, accord utilisateur, plafond 0,60 $, **coût réel 0,42 $**, appel direct, 54 lots, 1 065 / 1 065 mesures, 0 échec ; export précédent : `pilotes/donnees_interface_2027_avant_finalite.json` ; bilan `runs/2026-11-06_1832.md`).
  - Finalités : ordre et sécurité 535, droits et égalité 203, autre 154, axe non applicable (null) 122, probité et contrôle des pouvoirs 51.
  - **Règle ajoutée** (gratuite, réversible, `questionnaire_2027.calculer`) : un complément répondu « null » retire la mesure de l'axe société ; la lecture ciblée prime sur la première (exemples : « Recrutement de magistrats » −20, « Conditionner l'immigration au travail » +53, qui relève de l'axe immigration). Notes société : 1 062 → 889. Test ajouté ; 227 tests OK.
  - **Effet** (moyenne robuste pondérée, axe par axe ; avant q1 → q1 seul → q1 + finalité) : dispersion des centres société 37,9 → 24,0 → 29,3 ; composite société (société + immigration + droits) 38,7 → 34,6 → 39,7. Centres société : Arthaud −49, Roussel −36, Mélenchon −35, Tondelier −20, Glucksmann −20, Villepin −10, Retailleau +27, Le Pen +37, Attal +38, Lisnard +39, Philippe +43, Dupont-Aignan +44, Zemmour +88.
  - **Ruffin reste à +50** : 14 mesures de probité sortent de l'axe ; il ne reste que 4 mesures sociétales, toutes des sanctions contre des dirigeants ou des fraudeurs (TIG pour les responsables, sanctions doublées des gains illégaux), classées « ordre » par le modèle. Position sociétale fragile, non représentative : son programme aborde très peu les libertés et l'ordre. Ces 4 mesures sont corrigeables au tableau de bord (finalité « probité »).
  - Relecture d'un échantillon : classements cohérents (droits : changement de mention de sexe, antitsiganisme, loi-cadre contre les violences sexistes ; ordre : mandat de dépôt, narcotrafic, passeurs ; accompagnement des victimes côté droits ou autre, valeurs modérées). Valeur trop faible relevée : référendum sur la peine de mort pour meurtres d'enfants +15 (déclaration de portée ciblée).
- **Coût total de la phase 3** : batch q1 3,94 $ + mesure manquante 0,008 $ + complément 0,42 $ = 4,37 $ (plus pilotes et comparaisons : 0,25 + 0,25 + 0,22 + 0,36 $).

## Axe gauche-droite général : Le Pen trop au centre (2026-11-06)

- Question utilisateur : sur l'axe « Idéologie », Le Pen était à +8, moins à droite qu'Attal ou Philippe. Demande : corriger le calcul, préparer une question sur le degré de rupture, et intégrer les autres axes à caractère idéologique.
- Diagnostic : (1) son programme économique est réellement centriste (126 mesures : 38 à gauche, 39 au centre, 49 à droite ; électricité −30 à 40 %, abrogation de la réforme des retraites contre donations exonérées, pacte Dutreil, privatisation de l'audiovisuel) ; (2) l'idéologie, calculée mesure par mesure puis thème par thème, était noyée par l'économie (14 thèmes économiques sur 20) ; (3) les mesures migratoires radicales étaient rabotées (droit du sol +55 contre 97 ; Le Pen, Attal et Philippe à +52 sur l'immigration), parce que le modèle répond « réforme significative » à presque tout et que la portée « ciblée » réduit l'ampleur.
- **Fait (gratuit)**, dans `constellation_2027.html` : idéologie = économie 1, société 2, souveraineté 0,5 (national à droite), écologie 0,5 (protection à gauche), poids réglables ; centres des axes combinés = combinaison des centres du candidat par composante (`COMPOSITES`, `centreOf`). Résultat vérifié dans le navigateur : Arthaud −51, Roussel −42, Tondelier −40, Mélenchon −36, Glucksmann −34, Villepin −19, Attal +9, Retailleau +10, Ruffin +10, Philippe +19, Dupont-Aignan +24, Lisnard +29, **Le Pen +30**, Zemmour +55.
- **Préparé, non lancé** : complément `degre_rupture` (ajustement / notable / rupture), pour les axes société et immigration ; la portée ne joue plus, et une rupture pèse au maximum. Cas types : droit du sol +100, peine de mort +100, régularisation générale −100, regroupement familial durci +62. Code : `questionnaire_2027` (COMPLEMENTS, DEGRE_FORCE, DEGRE_AMPLEUR), `annotation_2027.CONDITIONS_COMPLEMENT`, `boussole_2027.py annoter --complement degre_rupture`. 3 tests ; 230 tests OK. Plan : 982 mesures, 50 lots, environ 0,39 $ en appel direct. Accord requis.
- **Complément `degre_rupture` lancé** (2026-11-06, accord utilisateur, plafond 0,60 $, **coût réel 0,38 $**, appel direct, 50 lots, 982 / 982, 0 échec ; export précédent `pilotes/donnees_interface_2027_avant_degre.json` ; bilan `runs/2026-11-06_1953.md`). Degrés : ajustement 465, notable 423, rupture 94. Suppression du droit du sol (Le Pen, Dupont-Aignan) +100, préférence nationale +100 (société), peine de mort +100.
  - Immigration (centres, avant → après) : Le Pen 57 → 78, Lisnard 59 → 79, Zemmour 58 → 82, Philippe 55 → 77, Attal 48 → 53, Dupont-Aignan 36 → 41 ; Arthaud −72 → −100, Mélenchon −49 → −57, Roussel −50 → −57.
  - **Constellation (idéologie / société, vérifié dans le navigateur)** : Arthaud −60 / −67, Roussel −43 / −46, Tondelier −40 / −34, Mélenchon −37 / −45, Glucksmann −35 / −29, Villepin −20 / −8, Ruffin +11 / +40, Attal +11 / +48, Retailleau +12 / +12, Philippe +23 / +58, Dupont-Aignan +26 / +43, **Le Pen +35 / +57**, Lisnard +35 / +52, Zemmour +61 / +77.
  - **Lacune de corpus : Retailleau** est à −37 sur l'immigration et +12 en société, parce que ses documents (IA, agriculture, éducation, production, famille, logement) ne contiennent aucun volet immigration ou sécurité : ses 4 mesures migratoires portent sur l'attraction de talents (visa « Talents Tech »). À combler en ajoutant ses documents sur l'immigration et la sécurité (tableau de bord, Sources ; traitement en phase 5). Ruffin : même fragilité en société (4 mesures).
- **Intégration au pipeline général (question utilisateur)** : calculs (formules q1, compléments, règle de la finalité vide, corrections humaines), constellation (centres axe par axe, marges, idéologie à quatre composantes) et tableau de bord sont intégrés et s'appliquent à chaque mise à jour. Reste manuel (phase 5) : enchaînement en une commande (collecte et extraction → `integrer` → `annoter` → `annoter --complement soc_finalite` → `annoter --complement degre_rupture`, dans cet ordre), traitement des documents ajoutés au tableau de bord, alignement du calcul Python de l'idéologie (`pipeline_scoring_2027.IDEOLOGY_COMPONENTS`, encore eco, soc, ouverture, droits) sur celui de la constellation, tâche planifiée hebdomadaire.

## Phase 5 : chaîne complète et planification (2026-11-06, 0 appel payant)

- Question utilisateur : le pipeline de `boussole_2027.py` ne contient-il pas tout ? Réponse : une commande par étape, mais ni la collecte et l'extraction (restées dans `update_corpus_2027.py`) ni l'enchaînement.
- **Code** :
  - `chaine_2027.py` et `boussole_2027.py mise-a-jour --complet [--max-cost X] [--mensuel Y] [--no-pull] [--candidate C] [--forcer]` : sources (dépôt amont et sources ajoutées au tableau de bord) → collecte, OCR, extraction (`update_corpus_2027.run`, avec deux points d'accroche optionnels : `transformer` et `resume`) → intégration des seuls documents nouveaux ou modifiés (`base.meta.documents_integres`, amorce au premier passage) → annotation q1 → compléments `soc_finalite` puis `degre_rupture` → calculs, file, export, bilan.
  - Plafond partagé entre les étapes ; plafond mensuel (`budget_2027.json`) ; arrêt de sécurité au-delà de 300 propositions nouvelles (`--forcer`) ; verrou de chaîne (`.boussole_chaine.lock`) ; codes 0 / 1 / 2 / 3.
  - Sources du tableau de bord : injectées comme liens du candidat, avec leur type et leur date ; fichiers déposés acceptés (`programme_corpus_2027.depot_url`, seulement sous `corpus_programmes/depots/`) ; statut mis à jour (traitée / en attente / erreur).
  - Idéologie Python alignée sur la constellation (`questionnaire_2027.ideologie`, mêmes composantes et poids).
  - `boussole_2027.py planifier` : écrit `planification/boussole_hebdo.cmd` et affiche la commande `schtasks` (non exécutée : modification de la configuration Windows laissée à l'utilisateur).
  - Tests : `test_chaine_2027.py` (6) ; 236 tests du projet OK.
- **Essai réel en mode plan** (`--complet --no-pull`, 0 $) : 153 documents vérifiés, 0 nouveau, 0 modifié, 1 indisponible connu (vidéo de Philippe sur les retraites) ; **amorce : 134 documents considérés comme intégrés** ; rien à annoter ; export régénéré. Sauvegarde de la base avant l'essai : `pilotes/base_2027_avant_chaine.json`.
- Reste à faire par l'utilisateur : enregistrer la tâche planifiée (commande affichée par `planifier`). Lacune de corpus connue : documents immigration et sécurité de Retailleau (à ajouter au tableau de bord).
- **Mise à jour du dépôt amont vérifiée** (question utilisateur) : la chaîne lance `git pull --ff-only origin main` sur `upstream_repo` (désactivable par `--no-pull`, que le script hebdomadaire n'utilise pas). Le clone avait 4 commits de retard ; il est à jour (`be1a4c4`, 2026-11-06). Ces commits (veille des pages, parrainages, temps de parole) n'apportent **aucun document de programme nouveau ou modifié** (collecte : 0 nouveau, 0 modifié).
- **Deux défauts corrigés dans la chaîne** (0 appel) :
  - « Document extrait » se jugeait sur le marqueur `complete` du manifeste, faux dès qu'une page est sans texte (photos, pages blanches) : 19 documents extraits (plans de Mélenchon, livrets de Ruffin, bouclier social de Tondelier, contre-budget RN 2027…) n'étaient pas reconnus. Nouveau critère `chaine_2027.extrait` : extraction du texte actuel et tous les morceaux traités. Rattrapage : un document extrait dont la base contient déjà des mesures est inscrit au registre (153 documents désormais). Sans cela, leurs propositions écartées à la sélection seraient revenues comme nouvelles.
  - **Modèle d'extraction figé sur celui du corpus** (`chaine_2027.modele_du_corpus`, aujourd'hui `anthropic/claude-haiku-5.5` pour les 153 documents). Le plan affichait 603 morceaux à extraire (environ 2,41 $) parce que `OPENROUTER_WEB_MODEL` désigne désormais `openai/gpt-6.1-terra` : le cache d'extraction dépend du modèle, et l'extraction aurait refait tout le corpus en propositions reformulées. Changer de modèle demande `--modele-extraction`. Vérifié : 0 morceau à extraire avec le modèle du corpus (604 avec GPT-6.1 Terra).
  - Tests : 2 ajoutés ; 238 tests du projet OK.

## Rangement, archives, file de validation et positions fragiles (2026-11-06, 0 appel payant)

- **Nouvelle organisation** (commit `567c950`) :
  - `tests/` : 179 tests, `python -m unittest discover -s tests` ;
  - `web/` : constellation et page du tableau de bord ;
  - `docs/` : guide, spécifications, audit, notes ;
  - `donnees/` : base, export, caches, budget et sources ;
  - `archives/` : ancienne chaîne Jev puis seconde lecture, descripteurs, boucle de précision, anciennes pages, anciens résultats et pilotes (voir `archives/LISEZMOI.md`).

  Constellation : http://localhost:8000/web/constellation_2027.html (serveur lancé à la racine).
- **Chemins** centralisés dans `boussole_2027.chemins()`. Les données non versionnées sont dans `donnees/` : la base fait environ 65 Mo. Pour une sauvegarde complète, copier `donnees/` et `corpus_programmes/`. `decisions_2027.json` et `sources_2027.json` y restent versionnés.
- **Module commun** : `commun_2027.py` reprend les fonctions encore empruntées à l'ancien code (masquage des noms, identifiant court, batch OpenRouter). Aucun module actif n'importe plus l'archive.
- **Ancienne chaîne retirée de la base** : les 3 892 mesures sont en q1. Une correction n'est donc possible que sur une annotation q1.
- **Défaut corrigé** : relancer `migrer` sur une base existante aurait effacé les annotations q1. Désormais, l'annotation est gardée et un texte changé est marqué `a_annoter`.
- **Vérifications** :
  - export identique avant et après le rangement (3 892 mesures, 0 différence) ;
  - constellation et tableau de bord vérifiés dans le navigateur.
- **Jev n'est plus utilisé** (question utilisateur) : chaque mesure reçoit le questionnaire q1 d'un seul modèle (GPT-6.1 Terra, low). Les cas peu fiables vont dans la file de validation humaine ; il n'y a pas de seconde lecture automatique.
- **File de validation** : `confiance_basse` ne compte plus que les questions qui fixent le sens d'une position (`Q.QUESTIONS_SENS` : eco_etat, eco_distrib, soc_autorite, soc_libertes, soc_finalite, sov_niveau, ouv_sens, env_sens, droits_statut, revenus_sens). Le doute sur le coût, le changement ou le public visé ne change que l'ampleur. Résultat : **192 mesures à relire au lieu de 657**.
- **Positions fragiles** (constellation) : un centre qui repose sur moins de 10 mesures sur l'un des axes s'affiche avec un cercle en pointillés et « ? » après le nom. Pour un axe combiné, c'est la composante la moins fournie qui compte. L'infobulle la nomme, avec son nombre de mesures.
  - Vue par défaut (économie × culturel) : 7 centres fragiles.
    - Arthaud : 2 mesures société.
    - Zemmour : 3 mesures immigration.
    - Villepin : 3 mesures immigration.
    - Ruffin : 3 mesures société, aucune sur l'immigration.
    - Retailleau : 4 mesures immigration.
    - Roussel : 4 mesures immigration.
    - Mélenchon : 9 mesures immigration.
  - La composante immigration du corpus est mince.
- **Restent à faire (utilisateur)** :
  - ajouter les documents immigration et sécurité de Retailleau (tableau de bord, onglet Sources) ;
  - enregistrer la tâche planifiée (commande `schtasks` affichée par `planifier`) ;
  - (fait le 2026-11-07) intégration des propositions restantes du corpus.

## Intégration des propositions restantes du corpus (2026-11-07, 7,02 $)

- **Intégration** (`integrer --input donnees/propositions_programmes_2027.json --max-cost 1`), arbitrage 0,58 $ :
  - 5 926 mesures nouvelles ;
  - 440 redites rattachées à des mesures existantes ;
  - 188 mesures précisées ;
  - 248 mesures modifiées (ancienne version publiée jusqu'à validation) ;
  - 82 rapprochements incertains (non publiés avant décision) ;
  - 0 non reprise.
- **Annotation q1** en deux batchs (GPT-6.1 Terra, low) : 3 500 mesures pour 3,64 $ (4,38 $ estimés), puis 2 574 pour 2,67 $ (3,22 $ estimés). Aucun lot en échec.
- **Compléments** en appel direct : `soc_finalite` 347 mesures (0,13 $), `degre_rupture` 242 mesures (0,09 $).
- **Total 7,02 $.** La base compte 9 900 mesures. L'export en publie 9 818 :
  - 5 960 avec le badge « non relue » ;
  - 244 en révision (ancienne version affichée) ;
  - 3 614 sans badge.
- **File** : 6 008 nouvelles mesures, 685 en confiance basse (sens), 247 mesures modifiées, 82 rapprochements incertains.
- **Pourquoi si peu de mesures « société » parmi les nouvelles** (311 sur 6 074) : la sélection initiale gardait tous les thèmes régaliens (sécurité, immigration, institutions, famille, culture, Europe). Les propositions restantes relèvent surtout de l'économie, de l'éducation, de l'écologie et de la santé. Aucune mesure immigration nouvelle : les positions fragiles sur cette composante restent.
- **Centres idéologie (avant → après)** :
  - Arthaud −60 → −60 ;
  - Roussel −43 → −42 ;
  - Mélenchon −37 → −42 ;
  - Tondelier −40 → −38 ;
  - Glucksmann −35 → −37 ;
  - Villepin −20 → −6 ;
  - Attal +11 → +8 ;
  - Ruffin +11 → +10 ;
  - Retailleau +12 → +11 ;
  - Philippe +23 → +22 ;
  - Dupont-Aignan +26 → +18 ;
  - Le Pen +35 → +30 ;
  - Lisnard +35 → +32 ;
  - Zemmour +61 → +60.
- **Centres fragiles** (économie × culturel) :
  - Arthaud : accès aux droits, 1 mesure ;
  - Ruffin : accès aux droits, 2 mesures ;
  - Villepin : accès aux droits, 2 mesures ;
  - Zemmour : immigration, 3 mesures ;
  - Retailleau : immigration, 4 mesures ;
  - Roussel : immigration, 5 mesures ;
  - Mélenchon : immigration, 9 mesures.

  Sur un axe combiné, une composante très mince pèse autant qu'une composante fournie. C'est la piste suivante : pondérer chaque composante par son nombre de mesures.
- **Tableau de bord** : mode réseau `--reseau` (lien à jeton, cookie), configuration `tableau-de-bord-reseau` sur le port 8780 (commit `0924e75`).

## Axes combinés pondérés par la fiabilité des composantes (2026-11-07, 0 appel)

- Le centre d'un candidat sur un axe combiné (culturel, idéologie) pondère chaque composante par son poids réglé **multiplié par sa fiabilité**, égale à min(1, n/10), où n est le nombre de mesures notées sur la composante. Auparavant, une composante notée sur une ou deux mesures pesait autant qu'une composante fournie.
- Position fragile = fiabilité sous 70 % : moins de 7 mesures sur un axe simple, moyenne pondérée des fiabilités des composantes sur un axe combiné. L'infobulle donne la fiabilité et la composante la moins fournie.
- Effets, culturel (avant → après) : Retailleau +15 → +27, Ruffin +39 → +45, Villepin +20 → +15 ; les autres bougent de 0 à 2 points.
- Effets, idéologie (avant → après) : Ruffin +10 → −8, Villepin −6 → −17, Retailleau +11 → +16, Arthaud −60 → −66, Zemmour +60 → +58 ; les autres bougent de 0 à 1 point.
- Fragiles (économie × culturel) :
  - Arthaud 20 % ;
  - Ruffin 23 % ;
  - Villepin 50 % ;
  - Zemmour 60 %.

  Mélenchon, Roussel et Retailleau ne le sont plus.

## Essai : passage du document et option « indéterminé » (2026-11-07, 0,14 $)

- Script `pilote_contexte_2027.py` : relecture q1 (GPT-6.1 Terra, low) avec le passage du document autour de la citation (environ 1 200 caractères avant et après, noms masqués) et une réponse « indéterminé » aux questions de sens. Rien n'est appliqué à la base ; rapport dans `runs/pilote_contexte_2027.{json,md}`.
- Coût réel 0,0028 $ par mesure (estimation 0,0018) : le plafond de 0,15 $ a arrêté l'essai après les 50 mesures en confiance basse. Les 20 mesures à mots ambigus ne sont **pas lues**.
- Résultats sur 50 mesures en confiance basse (sens) :
  - doute levé pour 49 (réponse sûre ou « indéterminé ») ;
  - sens changé pour 18 (24 réponses, dont 11 sur la question qui était douteuse) ; `sov_niveau` est la question qui change le plus (7) ;
  - « indéterminé » pour 41 mesures (78 réponses, dont 41 sur des questions jugées sûres avant) ;
  - un axe retiré pour 32 mesures, déplacement d'au moins 25 points pour 35.
- Lecture : le passage aide souvent. Exemples plausibles : étiquetage de l'origine (Ruffin) passe vers le national ; réforme des certificats d'économie d'énergie (Tondelier) passe à gauche avec le détail du passage ; relance de la construction (Dupont-Aignan) passe plus à droite (allègement des normes). Mais « indéterminé » est trop utilisé : il retire des axes à des mesures dont le sens est net (« Prix rémunérateurs pour les producteurs », écologie de « 400 000 logements »). Le modèle confond encore manque de moyens et manque de direction. Certains changements de `sov_niveau` sont discutables (Retailleau « porter le combat à Bruxelles » +48 → −47).
- À suivre : reformuler « indéterminé » (direction absente, pas moyens absents), relire les mêmes 50, lire les 20 mesures à mots ambigus. Une synthèse globale du programme comme contexte n'est pas recommandée (lève l'aveugle, effet de halo, couche d'interprétation non auditable).

### Essai v2 : « indéterminé » reformulé, et mots ambigus (2026-11-07, 0,19 $)

- Nouvelle définition : « indéterminé » est réservé à une direction absente ou contradictoire, jamais à des moyens, un coût ou un périmètre manquants. Rapport v1 gardé dans `runs/pilote_contexte_2027_v1.*`.
- 50 mesures en confiance basse :
  - « indéterminé » pour 24 mesures (31 réponses, contre 78 en v1) ;
  - doute levé pour 50 ;
  - sens changé pour 25 ;
  - axe retiré pour 24, souvent parce que le passage montre que l'axe ne s'applique pas (revalorisation salariale sans dimension ordre/libertés, porte-avions sans dimension écologique), plus rarement par « indéterminé ».
- 20 mesures à mots ambigus, sans doute déclaré : sens changé pour 5, déplacement d'au moins 25 points pour 7, aucun axe retiré. Les 13 autres sont stables.
  - Corrections plausibles :
    - « Laïcité à l'école et lutte contre les sectes » (Glucksmann) : société +51 → 0, liberté de conscience et répression ciblée ;
    - « Guerre intransigeante contre le séparatisme » (Attal) : 0 → +48, sanctions et fermetures ;
    - « Faire sauter le verrou des recours contre les discriminations » (Attal) : −24 → −57.
  - Changement discutable : « Chèque-éducation gagé par les bourses » (Lisnard) : économie 0 → −46.
  - Conclusion : le vocabulaire n'est pas lu de façon systématique, mais le contexte corrige environ un quart des mesures vagues à mots ambigus.
- Piste retenue par l'utilisateur : un **lexique par candidat**. Définitions des termes ambigus, citées mot pour mot dans ses documents, jointes aux mesures qui emploient ces termes, sans nom.

### Lexique par candidat et essai avec lexique (2026-11-07, 0,16 $)

- `lexique_2027.py` : recherche gratuite des phrases qui emploient 15 termes ambigus dans les documents de chaque candidat (laïcité, souveraineté, liberté, mérite, simplification, protection, sécurité, assimilation, intégration, identité, écologie, justice sociale, démocratie, autorité, valeur travail), puis choix par le modèle, par numéro, d'au plus deux phrases par terme (0,08 $). Chaque entrée est une citation exacte avec son document et sa page, noms masqués. Résultat : `donnees/lexique_2027.json`, versionné, de 3 termes (Zemmour) à 14 (Dupont-Aignan) par candidat.
- Exemple : « laïcité » se lit « appliquée sans accommodement » chez Retailleau, « le droit de croire, de ne pas croire ou de ne plus croire » chez Tondelier.
- Essai `pilote_contexte_2027.py --lexique` sur les 28 mesures de l'échantillon qui emploient un terme du lexique (0,08 $) : 7 lectures diffèrent de celle avec le passage seul. Les écarts sont mineurs (« indéterminé » ou « neutre », intensité, applicabilité) et ne relèvent pas d'une désambiguïsation visible. Les cas nets (laïcité de Glucksmann, séparatisme d'Attal) étaient déjà corrigés par le passage.
- Conclusion : le passage local fait l'essentiel ; le lexique n'apporte pas de gain mesurable à l'annotation sur cet échantillon. Il reste utile comme information affichée (« ce que le candidat entend par… ») dans la fiche du tableau de bord et dans la constellation.

## Relecture contextuelle des 684 mesures en confiance basse (2026-11-07, 1,91 $)

- Code (commit `c7a581d`) :
  - `contexte_2027.py` (passage, lexique en source secondaire, « indéterminé » réservé à une direction absente) ;
  - `boussole_2027.py annoter --contexte` ;
  - étape 3b de la chaîne complète, entre l'annotation et les compléments ;
  - `Q.normaliser` : « indéterminé » est neutre dans une paire dont l'autre question est tranchée, sinon l'axe n'est pas calculé ;
  - correction vers « indéterminé » permise au tableau de bord ; « indéterminé » n'est pas un doute dans la file ;
  - 6 tests (188 au total).
- Run :
  - 684 mesures relues, 69 lots, 0 échec, 1,8953 $ (2,05 $ estimés), dont 98 mesures avec une entrée du lexique ;
  - compléments : `soc_finalite` 12 mesures, `degre_rupture` 8 mesures (0,01 $).
- Effets :
  - sens changé pour 304 mesures ;
  - « indéterminé » pour 370 mesures, surtout `eco_distrib` (215) et `eco_etat` (199) ;
  - axes retirés : économie 100, écologie 42, souveraineté 33, société 7, immigration 2 ;
  - axes gagnés : écologie 28, souveraineté 17, société 14, économie 13, immigration 3.
- File : la confiance basse passe de 685 à **25 mesures** ; 247 mesures modifiées, 82 rapprochements incertains ; 6 008 nouvelles mesures, publiées avec le badge.
- Centres : 7 points au plus d'écart.
  - Le Pen : société +57 → +62.
  - Dupont-Aignan : souveraineté +37 → +43.
  - Lisnard : souveraineté +9 → +2.
  - Retailleau : idéologie +16 → +18.
  - Fragiles inchangés (Arthaud, Ruffin, Villepin, Zemmour).

## Interface de la constellation et généralisation de la lecture avec contexte (2026-11-07, 0 appel)

- Constellation (commit `47192b6`) :
  - infobulles : chiffres dans le cadre ; dans les marges, l'axe non applicable est affiché ;
  - thème ouvert : « Autres candidats sur ce thème » (actif par défaut), vue cadrée ou vue du thème ;
  - marges élargies au survol, marques étalées ;
  - graphique fixe au défilement (deux colonnes), hauteur ajustée à la fenêtre ;
  - fiche : signaux en haut avec précision et importance (aide au survol), infobulle des curseurs (lecture en mots et confiance), « non applicable » en gris.
- Généralisation demandée par l'utilisateur, pour que toutes les propositions soient notées avec les mêmes règles et les mêmes éléments (commit `68c4078`) :
  - `annoter --contexte --tous` (appel direct ou batch) ;
  - la chaîne lit désormais les mesures nouvelles ou modifiées directement avec le contexte (étape 3), q1 seul en secours.
- Plan : 9 216 mesures à lire (1 287 avec lexique), estimation 27,65 $ en direct ou 13,82 $ en batch. Non lancé, en attente du plafond de l'utilisateur.
- Tant que ce n'est pas fait, la chaîne hebdomadaire plafonnée consacrerait son budget à cette relecture, petit à petit.
