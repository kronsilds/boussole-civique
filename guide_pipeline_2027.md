# Guide d’exécution — pipeline et visualisation 2027

## 0. Parcours recommandé : documents avant scoring

L’ordre est désormais explicite : **collecter les programmes → extraire leurs propositions et thèmes → exporter des propositions sourcées → scorer → stocker et visualiser**. Les fiches du comparateur restent un référentiel distinct, pas un remplacement de la lecture des programmes.

Installer le lecteur PDF (la collecte HTML et le scoring n’ajoutent pas d’autre dépendance) :

```powershell
python -m pip install -r .\requirements.txt
```

### A. Inventorier et collecter les documents

```powershell
python .\programme_corpus_2027.py inventory --repo-dir .\upstream_repo
python .\programme_corpus_2027.py collect --repo-dir .\upstream_repo
```

Ces commandes ne font **aucun appel LLM**. Elles utilisent uniquement les liens explicites des programmes et documents thématiques fournis par la source. Il n’y a pas de crawl automatique d’autres sites. Les fragments comme `#page=10` sont dédupliqués pour ne pas télécharger le même document plusieurs fois.

Le dossier `corpus_programmes` contient :
- `manifest.json` : sources, candidats et thèmes associés, dates, statuts et erreurs.
- `documents` : copies des réponses sources, nommées par empreinte SHA-256.
- `texts` : texte PDF par page ou HTML par section, avec identifiants de segments.
- `extractions` : résultats normalisés de l’extraction LLM, mis en cache.

Les téléchargements à jour sont réutilisés pendant 30 jours. `--refresh` force la vérification des documents sélectionnés ; `--max-age-days N` change le délai. Un document modifié invalide son extraction. Les échecs HTTP et les formats non pris en charge restent explicitement dans le manifest. Les vidéos nécessitent une transcription sourcée, sans extraction inventée. Les PDF sans couche texte demandent un OCR ; les pages sans texte sont signalées et empêchent de déclarer le document entièrement analysé.

#### Corriger les polices et récupérer les pages PDF problématiques

Les messages `fontTools is required...` ne signifient pas nécessairement que le téléchargement a échoué. Certaines polices CFF/Type1 exigent le supplément `fonts` de pypdf, désormais déclaré dans `requirements.txt` :

```powershell
python -m pip install -r .\requirements.txt
python .\programme_corpus_2027.py reparse --repo-dir .\upstream_repo
```

`reparse` relit uniquement les PDF déjà présents dans le corpus : **aucun téléchargement ni appel LLM**. Les textes corrigés sont conservés et seules les extractions devenues obsolètes sont invalidées. Les résultats OCR déjà enregistrés sont conservés lorsque le fichier source est inchangé. Le bilan `pages_pending` indique combien de pages restent signalées.

Le critère local « moins de 40 caractères » est un signal de contrôle, pas un diagnostic certain de scan : une couverture, une page blanche ou un intertitre peuvent aussi être courts. Rien n’est automatiquement déclaré « page blanche vérifiée ».

Pour les pages encore signalées, une étape **séparée et optionnelle** utilise le plugin PDF `file-parser` d’OpenRouter, avec le moteur choisi explicitement. Le moteur par défaut est `mistral-ocr` :

```powershell
python .\programme_corpus_2027.py ocr --repo-dir .\upstream_repo --max-calls 0
```

Cette commande n’autorise **aucun appel payant** ; elle réutilise les annotations en cache et indique le nombre de pages différées. Pour autoriser ensuite jusqu’à cinq nouvelles pages :

```powershell
python .\programme_corpus_2027.py ocr --repo-dir .\upstream_repo --pdf-engine mistral-ocr --max-calls 5
```

Le modèle chat est `OPENROUTER_WEB_MODEL` (ou `--model`). Aucun outil de recherche web n’est demandé. **Une page problématique = au plus une requête**, pour conserver exactement son numéro dans le PDF original. Les autres pages ne sont pas envoyées. La commande accepte aussi `--candidate ID` et `--document-id ID_DU_MANIFEST` pour cibler les documents.

Selon la [documentation PDF OpenRouter](https://openrouter.ai/docs/guides/overview/multimodal/pdfs), Mistral OCR coûte 2 USD / 1 000 pages, **plus le coût du modèle** (tarification région US différente). `--pdf-engine cloudflare-ai` utilise un parsing annoncé gratuit, mais le modèle reste facturé. Le moteur `native` n’est pas utilisé ici : il ne fournit pas les annotations de texte réutilisables nécessaires au corpus.

Le texte retenu est exclusivement celui des annotations structurées `type: file` du **parseur**, jamais la transcription ou les connaissances que le modèle pourrait générer dans sa réponse. Ces annotations sont conservées sous `corpus_programmes\ocr`, par empreinte du document, page et moteur, et réutilisées même si le modèle change. Si l’inférence échoue après le parsing mais fournit `error.metadata.file_annotations`, le texte du parseur peut être récupéré avec un avertissement explicite, sans nouvelle requête.

La provenance `source_method: openrouter:mistral-ocr`, les empreintes des annotations et le numéro de page original accompagnent les citations. L’OCR reste une transcription potentiellement imparfaite à contrôler. Les balises d’enveloppe `<file name="...">` ne sont pas du texte documentaire ; une réponse contenant seulement ces balises, de la ponctuation ou aucun texte est mise en cache pour éviter de payer plusieurs fois, mais la page demeure à vérifier et l’export ne prétend pas être complet. Aucun repli vers une transcription inventée n’est effectué.

Après récupération, relancer `extract` puis `export` pour que les nouvelles propositions utilisent le texte corrigé. Les erreurs 404, les PDF chiffrés ou les fichiers non téléchargés parce qu’ils dépassent 25 Mio ne sont pas résolus par cette étape.

Pour démarrer sur un seul candidat et un seul document :

```powershell
python .\programme_corpus_2027.py collect --repo-dir .\upstream_repo --candidate arthaud --max-documents 1
```

### B. Extraire et classer les propositions

Le modèle d’extraction est celui de `OPENROUTER_WEB_MODEL` dans `.env`, conformément au choix de réutiliser ce modèle. Il est ici appelé **sans outil de recherche web** : il lit les textes déjà collectés. `--model NOM` peut le remplacer pour cette étape. Jev Decisions reste réservé aux évaluations.

```powershell
python .\programme_corpus_2027.py extract --repo-dir .\upstream_repo --candidate arthaud --max-documents 1 --max-calls 3
```

`--max-calls` est une autorisation explicite de dépenses, par morceaux de document ; son défaut est **0**. Un long programme nécessite plusieurs morceaux. Relancer la même commande réutilise les morceaux déjà extraits et poursuit les suivants, sans payer à nouveau pour les mêmes textes/modèle/paramètres.

Le modèle doit produire des engagements atomiques attribués à un candidat connu, un thème normalisé, une description et une citation continue exacte dans un segment fourni. Aucun score n’est demandé. Les citations, identifiants, thèmes et longueurs sont contrôlés localement. Un texte tronqué, une citation inventée ou une attribution hors liste ne sont pas acceptés. Cette vérification prouve la présence du texte cité, pas la justesse de son interprétation : une relecture reste nécessaire.

Les réponses brutes et résultats validés figurent dans le journal LLM. Les documents indisponibles et les morceaux restant à traiter sont comptabilisés explicitement ; le code de sortie 2 indique une extraction incomplète. Aucun appel de rattrapage non demandé n’est ajouté.

### C. Exporter le jeu de propositions documentées

```powershell
python .\programme_corpus_2027.py export --repo-dir .\upstream_repo --candidate arthaud --max-documents 1 --out .\propositions_programmes_2027.json
```

L’export normal exige que tous les documents référencés des candidats sélectionnés soient disponibles et tous leurs morceaux traités. Pour un essai limité (notamment `--max-documents`) ou des pages nécessitant un contrôle/OCR, ajouter **explicitement** `--allow-partial`. Le résultat signale alors sa couverture incomplète, document par document, y compris les documents non sélectionnés ; il ne prétend pas contenir un programme intégral.

Chaque proposition conserve :
- un identifiant déterministe distinct des anciennes fiches ;
- `candidate_id`, `theme_id`, titre et description ;
- `source_evidence` : citation, URL, page/section, empreinte du document et positions dans le texte collecté ;
- `programme_context` : structure des documents HTML, couverture des morceaux et pages non lues.

Les doublons stricts de titre/description/candidat/thème sont regroupés avec leurs preuves ; les ressemblances sémantiques ne sont pas fusionnées automatiquement. Une absence de proposition extraite ne provoque jamais un repli silencieux sur les 1 295 fiches anciennes. Les données existantes ne sont pas écrasées.

### D. Scorer et stocker, sans recherche web par défaut

```powershell
python .\pipeline_scoring_2027.py --input .\propositions_programmes_2027.json --llm --context-file .\contexte_programmes_2027.json --cache-file .\cache_programmes_2027.json --out .\donnees_programmes_2027.json
```

Les citations collectées et la couverture documentaire sont effectivement transmises à Jev. Les modèles chat et la seconde lecture web reçoivent désormais le **même barème complet**, avec définitions et ancrages numériques, plutôt que seulement les noms des dimensions et les notes précédentes. Une source n’a pas à publier une note : le modèle applique le barème aux faits qu’il cite.

**Importance programmatique** : pour les propositions documentaires, `importance_sources.programme` est le composite structurel calculé à l’export (`values.importance_structurelle.score` du signal `signal_structurel` : position 0,4, poids du thème 0,4, répétition 0,2), reproductible et sans LLM. La note du modèle est gardée pour comparaison dans `score_details.programme_importance.model_value` (méthode `corpus-structure`). Sans signal structurel, la note du modèle reste utilisée.

**Questions Jev (format à axes, depuis le 2026-11-05)** : 22 questions par proposition, lots de 4 (limite de 100 questions par requête ; `--batch-size` par défaut = maximum permis). Axes dans `proposal.axes` : `eco`, `soc`, `sov`, `ecolo`, `income_direction` (-100..100, null si non applicable selon la question `has_*`), `rupture` (0..100), `legal_instrument` et `horizon` (catégories). `rights_income` mesure désormais la seule **ampleur** des personnes concernées ; le sens est dans `axes.income_direction`. Non demandés à Jev (doublons) : l'idéologie, déduite comme moyenne des axes `eco`/`soc`/`sov` applicables (statut `derived`) ; l'importance programmatique (composite structurel) ; la saillance médiatique (`not_requested`) ; trois tags déduits (licorne = instrument constitutionnel ou traité, ultra-ciblé = ampleur ≤ 15, effet d'annonce = précision `orientation_generale`). `--selection selection_precision_2027.json` ne garde que les propositions retenues et leur joint la précision. Les réponses à l'ancien format restent lisibles.

**Seconde lecture Haiku (`revision_2027.py`)** : relit, à l'aveugle et sans web, les dimensions Jev sous le seuil de confiance (`--threshold`, défaut 0,65), avec le même barème, et ajoute une note d'audit. Le modèle ne voit pas la note Jev. La valeur révisée remplace la note Jev (gardée dans `score_details.<dim>.jev_value`) ; une note concordante est confirmée, une divergence (> 25 % de l'échelle, changement d'applicabilité ou de catégorie) part en relecture humaine (`revision.disagreements`, raison `disagreement` dans la file). La confiance déclarée par le modèle chat n'est pas utilisée. L'horizon est indicatif (jamais révisé ni signalé) ; pour l'instrument juridique, seule une divergence de classe compte (exécutif / loi / Constitution-traité / non identifiable). Sans `--max-cost`, plan seul.

Règle d'arbitrage (2026-11-05) : quand la seconde lecture dit « non applicable » face à une note Jev, elle l'emporte sans relecture humaine (`score_details.<dim>.resolution`), sauf pour la faisabilité. Les relectures déjà payées avec l'ancienne définition d'applicabilité restent réutilisées (`--no-legacy-cache` pour les ignorer).

**Relecture ciblée (`relecture_ciblee_2027.py`)** : après la seconde lecture, relit à l'aveugle l'axe économique des propositions hors thèmes économiques (définition resserrée : le seul coût d'une mesure de sécurité, justice, défense, culture ou institutions ne suffit plus) et estime pour toutes l'ordre de grandeur budgétaire `axes.cost_estimate` (sans impact notable, coût ou gain < 0,1 / 0,1–1 / 1–10 / > 10 Md€ par an, indéterminable). `cost_estimate` est indicatif : jamais additionné au solde, distinct du montant publié `budget_net_bn_year`. Modèle chat avec effort de raisonnement et schéma JSON strict ; mode batch OpenRouter à moitié prix (asynchrone, sous 24 h, **non annulable** : le plafond porte sur l'estimation avant envoi).

```powershell
python .\revision_2027.py --input .\scores_jev_etendu_2027.json --out .\donnees_revision_2027.json --review-queue .\revision_humaine_2027.json --max-cost 0.01
python .\relecture_ciblee_2027.py --input .\donnees_revision_2027.json --out .\donnees_programmes_2027.json --model openai/gpt-6.1-terra --batch-submit --max-cost 1.60
python .\relecture_ciblee_2027.py --input .\donnees_revision_2027.json --out .\donnees_programmes_2027.json --model openai/gpt-6.1-terra --batch-collect
python .\relecture_ciblee_2027.py --input .\donnees_revision_2027.json --out .\donnees_programmes_2027.json --review-queue .\revision_humaine_2027.json --model openai/gpt-6.1-terra --max-cost 0.10
```

La dernière commande écrit les sorties depuis le cache et ne relance en direct que les lots échoués (dans le plafond) ; si tout est en cache, elle écrit sans appel même avec `--max-cost 0`. Changer une question Jev (ici `has_eco` et l'ajout de `cost_estimate`) modifie l'empreinte Jev : un prochain run Jev recalcule toutes les propositions (≈ 0,6 $).

**Fichier final** : `dimensions_schema` décrit chaque dimension stockée (libellé, chemin du champ, bornes, ancres ou options, formule des valeurs déduites) ; l'interface peut recalculer l'idéologie et l'importance avec ses propres poids.

```powershell
python .\pipeline_scoring_2027.py --input .\propositions_programmes_2027.json --selection .\selection_precision_2027.json --llm --context-file .\contexte_programmes_2027.json --cache-file .\cache_programmes_2027.json --review-queue .\revision_jev_2027.json --out .\scores_jev_2027.json
python .\revision_2027.py --input .\scores_jev_2027.json --out .\donnees_programmes_2027.json --review-queue .\revision_humaine_2027.json --max-cost 1.0
```

Le scoring sans documents collectés est **bloqué par défaut**, avant tout appel LLM. `--allow-legacy-scoring` permet explicitement de réutiliser l’ancien parcours pour comparaison, avec un avertissement. Cette protection évite de relancer involontairement 1 295 recherches à partir des seules fiches.

Le cache Jev historique n’est pas supprimé. Les nouvelles propositions documentaires ont leurs propres identifiants et un cache recommandé distinct. La modification du barème transmis invalide les anciennes évaluations chat/web concernées ; elle ne force pas le recalcul des scores Jev des fiches inchangées en mode historique.

Les résultats sont compatibles avec la visualisation existante : copier le jeu validé vers son fichier d’entrée seulement après contrôle. Les sondages et les votes parlementaires restent des données distinctes à joindre explicitement ; ils ne sont pas déduits des programmes.

## 1. Prérequis et fichiers

Python 3.10+ et accès Internet pour télécharger les données du dépôt. Le nouveau parcours documentaire utilise `pypdf`, déclaré dans `requirements.txt`. Gardez les modules Python du projet dans le même dossier. Le pipeline écrit par défaut `donnees_2027.json` dans le dossier courant, chargé par la page via HTTP. Les sections historiques ci-dessous restent disponibles pour comparaison ; leurs commandes de scoring sans corpus demandent désormais `--allow-legacy-scoring`.

> **À noter :** le fichier `donnees_2027.json` joint ici est un jeu d’exemple synthétique créé pour tester l’interface. Il n’est pas le bundle GitHub réel. Lancez les commandes ci-dessous pour générer votre JSON à partir de la source à jour.

### Configuration locale des clés

Le fichier [.env](./.env) est prêt à remplir à côté du pipeline. Il est chargé automatiquement à chaque lancement, sans paquet supplémentaire et quel que soit le répertoire courant. Le modèle sans secret est conservé dans [.env.example](./.env.example). Si le fichier local est absent :

```powershell
Copy-Item .\.env.example .\.env
```

Tout passe désormais par OpenRouter par défaut, avec seulement trois variables :

```dotenv
OPENROUTER_API_KEY=
OPENROUTER_SCORING_MODEL=
OPENROUTER_WEB_MODEL=
```

- `OPENROUTER_API_KEY` : une clé commune aux deux étapes.
- `OPENROUTER_SCORING_MODEL` : modèle de première évaluation, soit un modèle chat compatible JSON, soit Jev Decisions (par exemple `~typesafe/jev-latest` ou `typesafe/jev-1.14`). Aucun modèle payant n’est choisi à votre place.
- `OPENROUTER_WEB_MODEL` : modèle chat réutilisé pour extraire les documents déjà collectés (sans recherche) et, sur option séparée, pour une seconde lecture web avec outils. Utiliser un identifiant sans suffixe `:online`.

Laisser le modèle web vide si cette option n’est pas utilisée. Aucun appel LLM n’est activé par le seul chargement du fichier : `--llm` autorise le scoring, `--web-fallback` autorise en plus les nouveaux appels web.

Le pipeline choisit automatiquement l’API adaptée, avec la même clé OpenRouter :
- **Jev Decisions** (`~typesafe/jev-latest`, `typesafe/jev-1.14`, etc.) : `https://openrouter.ai/api/alpha/decisions`, avec `state` et un dictionnaire de questions typées. Les réponses et confiances Jev sont conservées.
- **Modèle chat**, pour le scoring ou la recherche : `https://openrouter.ai/api/v1/chat/completions`.

L’alias `~typesafe/jev-latest` est bien un modèle de décisions valide, même s’il n’apparaît pas dans le catalogue général des modèles chat. Ne pas le confondre avec `typesafe/jev-router`, qui est un routeur de modèles chat et ne remplace pas Jev Decisions. Documentation : [Jev sur OpenRouter](https://openrouter.ai/docs/guides/community/jev).

Les variables déjà définies dans PowerShell ou le système ont priorité sur le fichier ; `--model` et `--web-model` ont priorité sur leurs variables respectives. Pour compatibilité, `LLM_MODEL` reste un alias de scoring de moindre priorité et `OPENROUTER_MODEL` un alias historique du modèle web. Les connecteurs directs restent disponibles via `LLM_PROVIDER` / `--provider`, avec leurs anciennes variables de clé et d’endpoint ; ils ne sont plus nécessaires pour l’utilisation OpenRouter. Une ancienne valeur `LLM_API_BASE_URL` n’altère pas l’endpoint OpenRouter par défaut.

Format : une variable `NOM=valeur` par ligne ; commentaires sur une ligne commençant par `#`. Les guillemets simples ou doubles peuvent entourer toute la valeur. Les valeurs sont littérales : aucune interpolation, commande, expansion `$VARIABLE` ou interprétation des antislashs. Ne pas ajouter de commentaire en fin de ligne après une valeur. Une ligne invalide ou une variable inconnue/dupliquée provoque une erreur sans afficher sa valeur.

Le fichier local est exclu par [.gitignore](./.gitignore). Ne jamais partager ce fichier ni ajouter de vraies clés dans le modèle.

Après l’avoir rempli, tester sur trois propositions :

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring --limit 3
```

Cette commande effectue des appels OpenRouter payants et écrit les sorties habituelles. Pour seulement vérifier que le programme démarre, sans traitement ni appel réseau :

```powershell
python .\pipeline_scoring_2027.py --help
```

## 2. Exécuter et mettre à jour depuis la source GitHub

**Option simple — source publique actuelle, sans clone :**

```bash
cd /chemin/vers/le/dossier-de-la-visualisation
python3 pipeline_scoring_2027.py
```

Le pipeline lit par défaut le bundle `data-v2.json` publié sur GitHub et écrit `donnees_2027.json` dans ce dossier. À chaque ré-exécution il télécharge la version courante. Pour utiliser une URL JSON différente :

```bash
python3 pipeline_scoring_2027.py --url 'https://exemple.org/donnees.json' --out donnees_2027.json
```

**Option clone Git — synchroniser puis traiter la copie locale :**

```bash
python3 pipeline_scoring_2027.py --sync-repo ./upstream_repo --output donnees_2027.json
```

Si le dossier n’existe pas, le pipeline le clone; s’il existe déjà et contient un dépôt Git, il exécute `git pull --ff-only`. Autre forme équivalente, avec un clone déjà présent :

```bash
python3 pipeline_scoring_2027.py --repo-dir /chemin/vers/presidentielle-2027-comparateur --sync-repo --out donnees_2027.json
```

`--sync-repo` seul utilise `./upstream_repo`. Si Git refuse le fast-forward, résoudre d’abord l’état du clone manuellement; le pipeline ne force pas la mise à jour. Pour récupérer directement le bundle brut distant sans clone, utilisez `--fetch-remote` (ou laissez la source distante par défaut).

## 3. Mettre à jour intentions de vote ou données de votes parlementaires

Le pipeline ne télécharge ni ne déduit de sondages ou de votes nominatifs de l’Assemblée. Il faut apporter des valeurs vérifiées et sourcées. Créez un JSON d’override, par exemple `mises_a_jour.json` :

```json
{
  "candidates": {
    "philippe": { "intentions_vote_pct": 17.5 }
  },
  "proposals": {
    "M01": { "importance_sources": { "votes": 91 } }
  }
}
```

Remplacez `philippe` et `M01` par des identifiants existant dans le JSON source. Pour les vérifier, ouvrez `donnees_2027.json` et recherchez `candidates[].id` et `proposals[].id`. `intentions_vote_pct` est un pourcentage (0–100). `importance_sources.votes` est une appréciation numérique de 0 à 100 pour la composante « cohérence des votes »; ce n’est pas un compte brut de scrutins. Documentez les sources dans vos données de travail et contrôlez chaque valeur avant partage. Les identifiants inconnus ou nombres hors plage arrêtent le pipeline avec une erreur.

Relancez avec l’override :

```bash
python3 pipeline_scoring_2027.py --overrides mises_a_jour.json --out donnees_2027.json
```

En mode clone, combinez les options :

```bash
python3 pipeline_scoring_2027.py --repo-dir /chemin/vers/presidentielle-2027-comparateur --sync-repo --overrides mises_a_jour.json --out donnees_2027.json
```

Les surcharges sont appliquées au bundle de la source à chaque exécution : conservez le fichier d’override et réappliquez-le après mise à jour. `importance_sources.votes` agit dans la pondération de l’importance affichée; les scores absents demeurent absents.

## 4. Charger / voir le résultat

1. Placez `donnees_2027.json` dans le même dossier que `visualisation_programmes_2027.html`.
2. Depuis ce dossier, lancez `python -m http.server 8000`, puis ouvrez `http://localhost:8000/visualisation_programmes_2027.html` dans un navigateur.
3. La page charge automatiquement `./donnees_2027.json` et confirme le nombre de candidats et propositions. Les valeurs manquantes ne sont pas inventées et les propositions sans chiffres pour les axes sélectionnés ne sont pas tracées.

L’import manuel n’est plus proposé. Après avoir régénéré `donnees_2027.json`, actualisez la page pour charger sa nouvelle version. En ouverture directe `file://`, un message indique comment lancer le serveur HTTP. Si le fichier est absent, invalide ou inaccessible, l’erreur est affichée et la démonstration intégrée reste explicitement signalée.

## 5. Options CLI exactes

- `-h`, `--help` : afficher l’aide.
- `--input FICHIER` : ingérer un JSON local; mutuellement exclusif avec `--url` et `--repo-dir`.
- `--url URL` : ingérer un endpoint JSON explicite.
- `--repo-dir DOSSIER` : lire `DOSSIER/public-data/data-v2.json`.
- `--sync-repo [DOSSIER]` : synchroniser le clone indiqué (ou `./upstream_repo` si le chemin est omis); clone le dépôt si le dossier n’existe pas, sinon fait `git pull --ff-only`. Fonctionne aussi avec `--repo-dir DOSSIER --sync-repo`.
- `--inspect-site URL` : afficher titre, métadonnées, scripts, liens et extrait textuel d’une page HTML; n’extrait pas automatiquement des mesures.
- `--download-data-v2 [FICHIER]` : télécharger le JSON source puis quitter; chemin par défaut `data-v2.json`.
- `--source-json-url URL` : remplacer l’URL JSON source par défaut (utilisée par téléchargement et ingestion distante par défaut).
- `--fetch-remote` : sélectionner explicitement la source GitHub raw distante (ignoré si `--sync-repo` est fourni).
- `--overrides FICHIER` : appliquer les changements de sondage et de score de votes décrits ci-dessus.
- `--out FICHIER`, `--output FICHIER` : alias pour la destination; par défaut `donnees_2027.json` dans le répertoire courant.
- `--limit N` : traiter au plus N propositions; 0 signifie toutes; les nombres négatifs sont refusés.
- `--llm`, `--use-llm` : demander une pré-évaluation LLM facultative (OpenRouter par défaut, clé commune `OPENROUTER_API_KEY` et modèle `OPENROUTER_SCORING_MODEL`). Une clé absente/placeholder ou un modèle absent provoque une erreur explicite. Aucun LLM n’est utilisé par défaut. Ne pas inscrire les clés dans le code.
- `--allow-legacy-scoring` : autoriser explicitement des évaluations sans `source_evidence` issu du corpus collecté. Inutile dans le nouveau parcours documentaire ; non activé par défaut.
- `--provider NOM` : choisir le fournisseur (`openrouter` par défaut, `typesafe` / `jev`, `openai`, `mistral`, `mammouth` ou `anthropic`). OpenRouter route automatiquement les modèles Jev de décisions vers `/api/alpha/decisions` et les modèles chat vers `/api/v1/chat/completions`. Le connecteur direct historique `typesafe` utilise `/v1/decisions` (CheaperInference) ou `/v1/systemone` (API TypeSafe native).
- `--batch-size N` : nombre de propositions regroupées dans chaque requête Jev, y compris via OpenRouter (de `1` à `6`, défaut `6`, soit 96 questions simultanées sous la limite API de 100 questions par requête). Le cache est sauvegardé après chaque lot. Les modèles chat restent évalués proposition par proposition.
- `--cache-file FICHIER` : cache différentiel LLM SHA-256; par défaut `cache_scores.json`. Les scores sont réutilisés seulement si la mesure, son contexte pertinent, les votes documentés, les questions et la configuration de scoring n’ont pas changé. Les anciens scores sans contexte sont donc recalculés une fois. Un cache illisible provoque une erreur, pas une nouvelle campagne d’appels silencieuse.
- `--llm-log-file FICHIER` : choisir le journal JSONL local. Avec `--llm`, un journal horodaté est créé automatiquement dans `logs` si cette option est omise. Un chemin explicite est utilisé en ajout, avec un identifiant distinct par exécution.
- `--endpoint URL`, `--model NOM` : remplacer l’endpoint du fournisseur et le modèle de scoring configurés.
- `--context-file FICHIER` : snapshot du contexte, par défaut `contexte_scoring_2027.json`, créé au premier traitement.
- `--refresh-context` : reconstruire le snapshot depuis la source ingérée en conservant les extraits locaux.
- `--context-max-age-days N` : délai de révision du snapshot et validité des secondes lectures web (défaut : 30 jours). Le dépassement du délai du contexte produit un avertissement, sans téléchargement supplémentaire.
- `--review-queue FICHIER` : liste des propositions et dimensions à compléter, par défaut `scoring_review_queue.json`, réécrite à chaque traitement.
- `--confidence-threshold X` : seuil par dimension (0–1, défaut : 0,65). Les scores absents, confiances absentes et confiances sous le seuil alimentent la file.
- `--web-fallback` : autoriser de nouvelles requêtes payantes OpenRouter après la première lecture (`--llm` requis). Désactivé par défaut.
- `--web-model NOM` : modèle OpenRouter, configurable par `OPENROUTER_WEB_MODEL` (ou l’ancien alias `OPENROUTER_MODEL`). Obligatoire pour les nouveaux appels web ; la recherche utilise l’outil serveur, pas une variante `:online`. Un ancien suffixe `:online` est retiré avec avertissement.
- `--web-max-calls N` : plafond de nouvelles requêtes web par exécution (défaut : 10 ; 0 pour aucun appel). Une requête traite les dimensions à compléter d’une proposition et autorise au plus une recherche, avec cinq résultats au maximum. Ce plafond ne constitue pas un budget monétaire.
- `--web-max-tokens N` : budget de sortie par requête web (défaut : 8 192 tokens). Le raisonnement du modèle consomme aussi ce budget ; ce n’est pas uniquement la taille du JSON visible. Ce plafond est distinct du nombre d’appels.

Sans `--input`, `--url`, `--repo-dir` ni `--sync-repo`, la source JSON distante configurée par défaut est utilisée (`--fetch-remote` l’explicite). Les erreurs d’ingestion/validation arrêtent le traitement; les valeurs inconnues restent nulles.

## 6. Contexte réutilisable et révision mensuelle

Le bundle v2 contient déjà des indicateurs France datés et sourcés (`context`), des budgets globaux (`budgets`), les axes prioritaires et les métadonnées des programmes des candidats. L’adaptateur les conserve désormais. Le snapshot local isole leur cadence de révision de celle des propositions.

Chaque proposition reçoit un `scoring_context` limité à son thème, aux finances publiques, au programme et au budget de son candidat, ainsi qu’aux extraits locaux correspondant à ses identifiants. Le même contexte est transmis à Jev en mode unitaire ou batch, sur les deux API, et aux autres fournisseurs.

**Limites importantes :**
- Les programmes PDF/web ne sont pas téléchargés ni analysés automatiquement. Un lien, un numéro de page, une proposition précise ou chiffrée ne prouvent pas à eux seuls son importance dans le programme.
- Le sous-score programme exige des axes prioritaires sourcés ou un extrait pertinent ; le sous-score média exige des observations documentées. Sinon, ils restent `null`, même si le modèle propose un chiffre.
- Les données du comparateur restent des informations de source, pas des faits vérifiés indépendamment par ce pipeline.
- `retrieved_at` date la copie locale, pas une validation des indicateurs. Les dates de publication et de vérification de la source restent visibles. Réactualiser le snapshot ne réactualise pas artificiellement la date de révision des extraits.
- Les intentions de vote n’entrent pas dans le scoring : elles restent une donnée candidate distincte, mise à jour par override sourcé. Les votes parlementaires restent une composante documentée indépendante ; aucun vote n’est attribué automatiquement à une proposition.

Pour ajouter des éléments durables, modifier la liste `evidence` du snapshot créé au premier lancement :

```json
{
  "id": "priorite-p0",
  "proposal_id": "IDENTIFIANT_REEL",
  "candidate_id": "IDENTIFIANT_CANDIDAT",
  "theme_id": "economie",
  "dimensions": ["programme_importance"],
  "text": "Bref extrait ou constat sourcé indiquant explicitement la priorité donnée à la mesure, avec sa page ou sa section.",
  "source_url": "https://exemple.org/programme.pdf#page=3",
  "source_date": "2026-10-15",
  "reviewed_at": "2026-11-03",
  "review_interval_days": 30
}
```

Les trois identifiants de portée sont facultatifs ; lorsqu’ils sont présents, ils doivent tous correspondre à la proposition. Les dimensions autorisées sont `ideology`, `feasibility`, `rights_income`, `rights_status`, `programme_importance`, `media_importance` et `budget_net_bn_year`. Chaque extrait exige un identifiant unique, une URL HTTP(S), des dates au jour près et un texte de 1 à 4 000 caractères. Pour un chiffrage budgétaire local, `proposal_id` est obligatoire pour l’extraction du montant : un budget global ne doit jamais être attribué à toutes les mesures.

Cadence recommandée :
- **À chaque exécution** : nouvelles propositions, changements de texte, file de révision.
- **Mensuellement** : rafraîchir la source, contrôler indicateurs France, cadre juridique et chiffrages ; corriger les extraits et leur `reviewed_at` après contrôle réel.
- **À la publication d’un programme** : réactualiser immédiatement axes, statut et extraits, sans attendre la prochaine échéance.
- **Plus fréquemment si nécessaire** : interviews, scrutins et sondages, avec dates et sources distinctes.

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring --refresh-context
```

Cette commande lit le clone présent ; ajouter `--sync-repo` pour le synchroniser auparavant. Une simple nouvelle date de récupération, sans changement du contexte pertinent, n’invalide pas tous les scores.

## 7. Scores incomplets et seconde lecture web optionnelle

Les réponses Jev manquantes restent `null` : elles ne sont plus converties en zéro ou en idéologie extrême. `score_details` conserve le statut, la confiance et la méthode par dimension. La confiance moyenne reste informative ; elle ne masque pas un axe peu fiable. Une dimension d’ayants droit clairement non applicable est exclue de la file ; une applicabilité incertaine y reste.

Le coût/gain n’est chiffré qu’à partir d’un montant explicitement annuel rattaché à la mesure (ex. `20 Md€/an`, `2 milliards d’euros par an`). Les budgets quinquennaux, montants de salaire et budgets globaux ne sont pas convertis en coût annuel de la proposition.

Première lecture et inspection de la file, sans recherche web supplémentaire (les variables sont déjà renseignées dans `.env`) :

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring
```

Autoriser ensuite au plus cinq nouvelles secondes lectures :

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring --web-fallback --web-max-calls 5
```

Choisir un modèle OpenRouter disponible acceptant le mode JSON et les outils. Les variantes `:online` et le plugin `web` sont dépréciés : le pipeline utilise désormais `tools: [{"type": "openrouter:web_search", ...}]`. L’exécution de l’outil et le retour des résultats au modèle sont gérés par OpenRouter, sans boucle d’outils côté client.

Le moteur Exa est sélectionné explicitement pour faire respecter les limites `max_uses: 1`, `max_results: 5` et `max_total_results: 5` ; certains moteurs natifs ignorent ces plafonds. Le modèle peut ne pas effectuer de recherche ; sans citations issues de la réponse du service, aucune nouvelle valeur non nulle n’est acceptée. Aucun repli vers le mécanisme déprécié n’est effectué si l’outil échoue.

Les requêtes transmettent la proposition et son contexte sourcé à OpenRouter : n’ajouter aucun contenu privé aux extraits. L’API des outils serveur est encore en bêta. Documentation : [outil serveur de recherche web OpenRouter](https://openrouter.ai/docs/guides/features/server-tools/web-search).

**Vérifier si une recherche a réellement eu lieu :** `usage.server_tool_use_details.web_search_requests` est le compteur de recherches fourni par le service, conservé dans la réponse API brute du journal. Le pipeline le restitue dans `web_review.search_activity`, avec `tool_calls_requested` et `tool_calls_executed` lorsqu’ils sont présents, et l’affiche dans la console :
- `performed` : le fournisseur annonce au moins une recherche.
- `not_performed` : le fournisseur annonce zéro recherche ; aucune nouvelle note non nulle n’est alors acceptée comme résultat web.
- `unknown` : ce compteur n’a pas été fourni ou est invalide. Ce n’est ni une preuve de recherche ni une preuve d’absence de recherche. Les citations restent contrôlées et la relecture humaine nécessaire.

La simple présence de `tools` dans la requête, de citations dans un texte ou d’une phrase « j’ai recherché » ne prouve pas l’exécution de l’outil. Même un appel confirmé ne permet pas de mesurer la part des connaissances internes du modèle dans sa réponse. L’étape d’extraction documentaire, elle, ne demande aucun outil web : elle doit s’appuyer sur les textes collectés et sur des citations retrouvées localement.

La seconde lecture :
1. Ne demande que les dimensions absentes ou insuffisamment confiantes, dans l’ordre des propositions de la source.
2. N’applique une valeur que si elle respecte les plages, atteint le seuil et cite une URL effectivement présente dans les annotations de recherche renvoyées par OpenRouter, avec une preuve textuelle.
3. Conserve les résultats initiaux dans `web_review.initial_assessments` et dans le cache primaire ; les évaluations, citations, dates et justifications web restent dans `web_review`.
4. Ne modifie ni les autres dimensions, ni les tags de la première lecture, ni les votes renseignés manuellement. L’importance agrégée est recalculée sur les composantes disponibles.
5. Valide les dimensions indépendamment : un axe refusé ne fait plus perdre les compléments valides des autres axes. La première lecture est conservée pour chaque axe refusé et celui-ci reste dans la file ; un avertissement précise sa dimension et sa cause.

Une abstention explicite (`value: null`, `confidence: null`) est valide et ne modifie aucun score. Une note non nulle exige toujours une confiance numérique entre 0 et 1, une preuve textuelle et des URLs effectivement présentes dans les citations de recherche. Les pourcentages, chaînes de caractères ou confiances manquantes ne sont pas convertis en nombres. Une URL simplement présente dans le contexte, mais absente des annotations de recherche, ne suffit pas pour accepter une nouvelle note web.

`web_review.status` distingue les réponses `completed` et `partial`. `accepted_dimensions`, `abstained_dimensions` et `rejected_dimensions` indiquent ce qui a été appliqué, laissé inconnu ou refusé. `assessments` ne contient que les évaluations validées ; les évaluations refusées sont décrites par leurs erreurs, pas réinjectées comme des scores. Si aucune dimension n’est valide, la seconde lecture reste en erreur, avec ses métadonnées de diagnostic, et la première lecture est conservée intégralement.

Avec **Jev Decisions via OpenRouter**, la première lecture conserve les confiances issues des distributions de réponses Jev, comme avec le connecteur direct. Elles n’attestent pas à elles seules la vérité d’une évaluation politique : les seuils restent à valider sur des exemples relus humainement. Avec un **modèle chat**, les confiances sont déclaratives et non calibrées, comme celles de la seconde lecture web. Elles ne sont pas directement comparables aux confiances Jev ni entre modèles. Une citation prouve sa présence dans la réponse du service, pas la validité de l’interprétation du modèle. Toute évaluation reste à valider humainement.

Le cache distingue première lecture et complément web. Un complément encore valide est réutilisable même sans `--web-fallback` ; cette option n’autorise que les **nouveaux** appels. Il expire après le délai configuré et est invalidé si le contexte, la première lecture, le modèle web explicitement sélectionné ou le seuil changent. Les lectures web infructueuses mais valides sont aussi mises en cache pour éviter de répéter des recherches sans preuve. Une réponse partielle conserve en cache ses dimensions valides et la liste explicite des refus ; les axes refusés restent à revoir et ne sont pas marqués comme résolus. Les erreurs réseau et réponses entièrement invalides ne sont pas mises en cache comme des évaluations. Le plafond compte également les tentatives en échec.

La migration vers l’outil serveur invalide uniquement l’ancien cache des compléments web, pas celui de la première lecture. La configuration de l’outil est incluse dans l’empreinte des nouveaux compléments.

Le budget de sortie web entre également dans son empreinte de cache. Le pipeline demande des justifications compactes pour éviter les réponses inutilement longues. Un objet JSON complet entouré d’un bloc Markdown `json` est accepté, mais aucune réparation de JSON tronqué ni extraction approximative dans du texte libre n’est tentée. Les mêmes règles de lecture JSON sont utilisées pour les modèles chat de première lecture.

Sans appel LLM, le pipeline continue de normaliser les données et génère la file de révision, mais n’invente aucun score. Les fichiers de sortie restent compatibles avec la visualisation existante ; les nouvelles métadonnées d’audit ne changent pas ses axes.

## 8. Vérifier sans appels payants

```powershell
python -m unittest -v test_programme_corpus_2027 test_pipeline_scoring_2027
```

Les tests utilisent des données synthétiques, des répertoires temporaires et des API simulées : contexte et invalidation du cache, absence de réponse/confiance, applicabilité, budgets annuels, transmission unitaire/batch/native, preuves web, erreurs et plafonnement des appels.

### Dépanner une erreur HTTP

Le pipeline affiche le message JSON renvoyé par le fournisseur, sans afficher la clé API. Les erreurs HTTP permanentes (notamment 400, 401, 402, 403, 404 et 422) arrêtent immédiatement le traitement avec un code de sortie 2, au lieu de répéter la même requête sur toutes les propositions. Les scores déjà calculés sont sauvegardés dans le cache ; les fichiers de résultat existants ne sont pas remplacés par des scores vides. Les erreurs réseau ou HTTP transitoires conservent le comportement de repli signalé.

Exemple : si OpenRouter répond qu’un modèle est un « decisions model » et demande `/api/alpha/decisions`, il ne faut pas changer de modèle. Utiliser cette version du pipeline, qui reconnaît automatiquement les identifiants Jev et emploie la bonne API. Jev ne peut pas être choisi comme modèle de recherche web : cette seconde étape exige un modèle chat compatible outils.

Si une seconde lecture web est interrompue, l’avertissement indique désormais `finish_reason`, `native_finish_reason`, le budget et la consommation de tokens, ainsi que l’identifiant de réponse OpenRouter. Ces métadonnées sont aussi conservées dans `web_review.response`, y compris en cas d’échec, sans copier le contenu brut de la réponse ni les clés API.

Avec `finish_reason=length` / `native_finish_reason=max_output_tokens`, le JSON a pu être coupé parce que le raisonnement et la réponse dépassent ensemble le budget. Les scores Jev restent conservés ; aucune valeur n’est tirée d’une réponse incomplète. Le budget par défaut est passé de 4 096 à 8 192 tokens. Si le modèle nécessite davantage, augmenter explicitement le plafond, par exemple :

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring --web-fallback --web-max-calls 5 --web-max-tokens 12288
```

Le cache Jev existant est réutilisé : il n’est pas nécessaire de changer son nom ni de tout recalculer. Aucun nouvel appel automatique de rattrapage n’est ajouté ; le plafond d’appels reste respecté. Les réponses web invalides ne sont pas mises en cache comme des évaluations réussies.

## 9. Voir exactement ce que font les LLM

Chaque exécution avec `--llm` affiche le chemin d’un journal JSONL, par exemple `logs\llm_20261103T220000Z_ab12cd34.jsonl`. Chaque ligne est un événement JSON complet, écrit immédiatement :

- `run_start` : modèles, seuils et plafonds retenus.
- `assessment`, `source: cache` : résultats réutilisés, sans nouvel appel au modèle. Une ancienne réponse API brute absente du cache ne peut pas être reconstituée.
- `api_request` : identifiant local de la requête, étape `primary` ou `web`, propositions concernées, modèle, endpoint sans paramètres d’URL, réglages et nombre de questions. Les en-têtes et prompts ne sont pas copiés.
- `api_response` : réponse JSON complète du fournisseur, comprenant les réponses Jev ou le texte/JSON du modèle chat, citations, consommation, coût et motif de fin lorsque le service les fournit. Si le corps HTTP n’est pas du JSON valide, son texte est conservé comme diagnostic.
- `api_error` : erreur HTTP ou réseau, avec le corps d’erreur disponible.
- `assessment`, `source: api` : résultats validés après interprétation, scores, justifications, abstentions et refus par dimension.
- `assessment`, `source: error` : résultat initial conservé et cause de l’échec.
- `web_selected` / `web_skipped` : sélection ou absence d’appel, avec la raison `call_limit`, `web_disabled` ou `no_review_needed`.
- `run_summary` : bilan de la file, du cache, des appels et des notes réellement appliquées. Une exécution interrompue par une erreur fatale termine par `run_error` plutôt que par un faux bilan de succès.

Les clés connues et les champs d’authentification sont masqués ; aucun en-tête HTTP n’est journalisé. Les journaux peuvent néanmoins contenir des extraits de documents, des raisonnements ou des textes renvoyés par le fournisseur : les garder locaux et les relire avant partage. Le dossier `logs` est exclu de Git. Un chemin personnalisé situé ailleurs n’est pas automatiquement ignoré. Une erreur d’ouverture ou d’écriture du journal arrête le traitement explicitement au lieu de poursuivre des appels sans trace.

Pour avoir un nom fixe, puis suivre les événements dans une autre fenêtre PowerShell :

```powershell
python .\pipeline_scoring_2027.py --repo-dir .\upstream_repo --llm --allow-legacy-scoring --web-fallback --web-max-calls 5 --llm-log-file .\logs\llm.jsonl
```

```powershell
Get-Content -LiteralPath .\logs\llm.jsonl -Encoding UTF8 -Wait
```

Pour lire uniquement les bilans :

```powershell
Get-Content -LiteralPath .\logs\llm.jsonl -Encoding UTF8 |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.event -eq 'run_summary' } |
    Format-List
```

**La taille de la file n’est pas le nombre d’appels autorisés.** Par exemple, avec 1 295 propositions à compléter, aucun complément en cache et `--web-max-calls 5`, le pipeline fait au plus cinq nouvelles recherches et en laisse 1 290 en attente du plafond. Une réponse web peut être valide mais s’abstenir ou rester sous le seuil : elle ne crée alors aucune nouvelle note. La file restante peut donc toujours contenir 1 295 propositions.

Le bilan console distingue désormais scoring principal, nouveaux appels web, compléments en cache, erreurs, attente due au plafond, abstentions, notes sous le seuil et dimensions appliquées/refusées. Ces compteurs sont aussi dans les métadonnées de sortie. Une requête Jev en lot peut traiter jusqu’à six propositions : le nombre d’appels API est donc distinct du nombre de propositions scorées. Augmenter `--web-max-calls` autorise plus d’appels payants ; le journal ne modifie pas ce plafond.

## Mise à jour automatisée (`update_corpus_2027.py`)

Une seule commande enchaîne : `git pull` d'`upstream_repo` → collecte (documents non vérifiés depuis `--max-age-days`, 7 par défaut) → relecture locale → **plan chiffré** → OCR → extraction avec relances réseau → export partiel → bilan qualité par candidat (alertes de densité).

```powershell
python .\update_corpus_2027.py                  # plan seul : rien de payant, estimation du coût
python .\update_corpus_2027.py --max-cost 1.0   # autorise jusqu'à 1 $ (OCR + extraction, budget partagé)
python .\update_corpus_2027.py --no-pull --candidate lisnard --max-cost 0.2
```

- Le modèle vient de `OPENROUTER_WEB_MODEL` (`.env`) ; `--model` le remplace. Changer de modèle ou d'instruction invalide tout le cache : décision explicite.
- Sans `--max-cost`, aucun appel payant. Le budget est converti en nombre d'appels (`--cost-per-call`, 0,004 $ par défaut) puis le coût réel est relu dans le journal `logs/`.
- Erreurs réseau (DNS, timeout, connexion coupée) : 3 relances avec attente croissante (`--retries`, `--retry-wait`) ; les morceaux déjà extraits ne sont jamais repayés.
- Un document dont seul le HTML brut varie (jeton anti-bot, horodatage) mais dont le texte est identique garde son empreinte et ses extractions.
- À traiter à la main : documents indisponibles ou sans texte (liens morts → `sources_surcharges.json`, vidéos), changement de modèle/instruction, scoring payant.

## Pipeline unifié (`boussole_2027.py`, phase 1)

Spécification : `spec_pipeline_unifie_2027.md`. La phase 1 couvre la base unique, les décisions humaines et les étapes gratuites. Les étapes payantes restent pour l'instant dans leurs scripts : `update_corpus_2027.py` pour les sources et l'extraction, `descripteurs_corpus_2027.py` pour l'annotation.

```powershell
# Créer ou mettre à jour la base (uid stables, versions, statuts) puis calculs, file, export et bilan
python .\boussole_2027.py migrer --input .\donnees_programmes_2027.json --selection .\selection_etendue_2027.json

python .\boussole_2027.py plan                         # état de la base, file, batch en cours (gratuit)
python .\boussole_2027.py mise-a-jour                  # calculs -> file -> export -> bilan (gratuit)
python .\boussole_2027.py etape export                 # une étape seule
python .\boussole_2027.py file --motif nouvelle_mesure --limit 20

# Décisions humaines (decisions_2027.json, liées à la version courante de la mesure)
python .\boussole_2027.py decision --uid m-roussel-0412 --type validation
python .\boussole_2027.py decision --uid m-roussel-0412 --type correction --champ levier --valeur controle_prix_ou_revenus
python .\boussole_2027.py decision --uid m-roussel-0412 --type rejet --motif "pas une mesure"
python .\boussole_2027.py decision --uid m-roussel-0412 --type fusion --cible m-roussel-0007
```

- `base_2027.json` est la source de vérité, avec 5 sauvegardes dans `sauvegardes/`. `donnees_interface_2027.json` (identifiants `m-<candidat>-<n>`) et `nouveautes_2027.json` sont régénérés à chaque run. Bilans dans `runs/`.
- Relancer `migrer` avec une nouvelle sortie de scoring garde les `uid`, les décisions et la file. Une mesure absente devient `non_reprise`. Une mesure au texte changé reçoit une nouvelle version, et l'ancienne reste publiée jusqu'à validation.
- Importance : calcul structurel gratuit (mesures proches, redites, précision, position), qui remplace la note LLM.
- Un verrou (`.boussole.lock`) empêche deux runs simultanés ; `--force-verrou` seulement si un run précédent a planté.

### Tableau de bord local

```powershell
python .\boussole_2027.py tableau-de-bord          # puis ouvrir http://127.0.0.1:8765
python .\tableau_de_bord_2027.py --port 8766        # équivalent, autre port
```

- **Accueil** : file par motif, mesures par statut, nouveautés du dernier export, batch en cours (état lu localement), dernier bilan. Le bouton **Appliquer** lance la mise à jour gratuite (calculs, file, export, bilan) pour reporter les décisions dans la constellation.
- **À valider** : file triée par priorité, filtres par motif, candidat et thème. La fiche montre la citation, le lien vers la source à la bonne page, la position sur chaque axe (avec l'ancienne note eco), les réponses du questionnaire en listes déroulantes (corriger recalcule la note aussitôt), les mesures proches pour fusionner et l'historique des décisions. Raccourcis : `J` / `K` pour la suivante ou la précédente, `V` pour valider.
- **Mesures** : recherche plein texte, filtres, mêmes fiches.
- **Sources** : ajout d'un document par URL ou fichier (PDF, HTML, TXT, DOCX, 50 Mo maximum, copié dans `corpus_programmes/depots/`) avec candidat, type et date. Les ajouts sont enregistrés dans `sources_2027.json` avec le statut « en attente » ; leur collecte et leur extraction arrivent avec la phase 5.
- **Runs** : historique des bilans.
- Sécurité : écoute seulement sur 127.0.0.1, refuse un autre hôte, exige un en-tête propre à la page pour toute écriture, refuse d'écrire pendant un run. Ne lit jamais `.env`. Aucun appel payant n'est possible depuis la page.

### Intégrer un nouvel export avec rapprochement (phase 2)

Pour un export complet ou partiel (par exemple un seul nouveau document) issu de `programme_corpus_2027.py export` :

```powershell
python .\boussole_2027.py integrer --input .\nouvel_export.json --plan              # pré-tri gratuit, rien n'est écrit
python .\boussole_2027.py integrer --input .\nouvel_export.json --max-cost 0.10     # arbitre les paires douteuses (payant, plafonné)
python .\boussole_2027.py integrer --input .\nouvel_export.json --sans-arbitrage    # paires douteuses -> « rapprochement incertain »
python .\boussole_2027.py integrer --input .\programme_v2.json --remplace ANCIEN_DOC=NOUVEAU_DOC
```

- Identifiant corpus déjà connu (y compris un alias d'une ancienne extraction) : simple mise à jour.
- Inconnu : comparaison aux mesures du même candidat.
  - Citation qui chevauche une mesure existante, ou similarité ≥ 0,85 : même mesure (source ajoutée).
  - Similarité < 0,35 : nouvelle mesure, publiée avec le badge « non relue ».
  - Entre les deux : arbitrage par un modèle (environ 0,0005 $ par paire), qui conclut à même mesure, précisée (nouvelle version, sans relecture), modifiée (nouvelle version, l'ancienne reste publiée jusqu'à validation) ou différente.
  - Sans arbitrage, ou verdict à moins de 70 % de confiance : nouvelle mesure « rapprochement incertain », non publiée. Dans le tableau de bord, choisir « Même mesure → fusionner » ou « Mesure distincte → valider ».
- Une mesure dont tous les documents sont couverts par l'export (ou remplacés) sans être retrouvée passe en « non reprise ».
- Les textes nouveaux ou modifiés sont marqués `a_annoter`. Leurs positions seront recalculées par l'annotation (phase 3).


### Annoter avec le questionnaire unifié `q1` (phase 3)

```powershell
python .\boussole_2027.py annoter                                                    # plan : mesures à annoter, coût estimé
python .\boussole_2027.py annoter --pilote .\pilotes\pilote_descripteurs_2027.json --max-cost 0.35   # pilote, appel direct
python .\boussole_2027.py annoter --uid m-roussel-0412 --max-cost 0.05               # une mesure
python .\boussole_2027.py annoter --batch-submit --max-cost 6                        # tout le corpus en batch (non annulable)
python .\boussole_2027.py annoter --batch-collect                                    # récupération gratuite, puis application
```

- Mesures à annoter : celles sans annotation `q1`, celles au texte nouveau ou modifié (`a_annoter`, après un rapprochement), et celles pour lesquelles un retraitement a été demandé après la dernière annotation. Un retraitement force une nouvelle lecture.
- Après application, toutes les notes de la mesure sont recalculées depuis les réponses : axes, faisabilité, accès aux droits, effet sur les revenus, instrument, coût, étiquettes. Les explications en mots passent dans l'export (`expl`). Les anciennes annotations restent dans `historique`.
- Les déplacements dus à ce changement de méthode ne sont pas signalés dans la file (même effet que `--changement-methode`).
- Dans le tableau de bord, les 17 réponses sont corrigeables ; corriger une réponse recalcule aussitôt toutes les notes concernées.

### Compléments du questionnaire (`--complement`)

```powershell
python .\boussole_2027.py annoter --complement soc_finalite --effort low                    # plan
python .\boussole_2027.py annoter --complement soc_finalite --effort low --max-cost 0.60    # appel direct
python .\boussole_2027.py annoter --complement soc_finalite --effort low --batch-submit --max-cost 0.40
python .\boussole_2027.py annoter --complement soc_finalite --effort low --batch-collect
```

Une question ajoutée après coup n'est posée qu'aux mesures déjà annotées et concernées : pour `soc_finalite`, celles dont l'axe société s'applique. Cache propre (`cache_complements_2027.json`). Après chaque `annoter` sur de nouvelles mesures, relancer les compléments.

### Chaîne complète en une commande (phase 5)

```powershell
python .\boussole_2027.py mise-a-jour --complet                          # collecte (gratuite) et plan, aucun appel payant
python .\boussole_2027.py mise-a-jour --complet --max-cost 1 --mensuel 5  # chaîne complète plafonnée
python .\boussole_2027.py planifier --jour lundi --heure 07:00 --max-cost 1 --mensuel 5   # prépare la tâche hebdomadaire
```

Ordre des étapes :
1. Dépôt amont et sources ajoutées au tableau de bord (URL ou fichier déposé), collecte, OCR, extraction.
2. Intégration des seuls documents nouveaux ou modifiés (`base.meta.documents_integres` ; au premier passage, le corpus actuel sert d'amorce), avec rapprochement.
3. Annotation q1.
4. Compléments `soc_finalite` puis `degre_rupture`.
5. Calculs, file, export, bilan.

- Le plafond `--max-cost` couvre toute la chaîne, chaque étape recevant ce qui reste ; `--mensuel` le réduit d'après `budget_2027.json`.
- Arrêt de sécurité au-delà de 300 propositions nouvelles d'un coup (relancer avec `--forcer` après vérification).
- Codes de sortie : 0 terminé, 1 arrêt de sécurité, 2 erreur, 3 plafond atteint (relancer : tout est en cache).
- `planifier` écrit `planification/boussole_hebdo.cmd` et affiche la commande `schtasks` à lancer soi-même ; sortie dans `runs/planifie.log`.
- Sans `--complet`, `mise-a-jour` ne fait que les étapes gratuites (bouton « Appliquer » du tableau de bord).
