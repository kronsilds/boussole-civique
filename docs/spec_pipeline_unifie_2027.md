# Spécification : pipeline unifié, mises à jour et tableau de bord

Statut (2026-11-06) : **phase 1 faite** : [base_2027.py](base_2027.py), [boussole_2027.py](boussole_2027.py), tests `test_base_2027.py`. Migration réelle : 3 892 mesures. **Tableau de bord fait, avancé depuis la phase 4** : [tableau_de_bord_2027.py](tableau_de_bord_2027.py) + [tableau_de_bord_2027.html](tableau_de_bord_2027.html), tests `test_tableau_de_bord_2027.py`. Les sources ajoutées attendent la phase 5 pour être traitées. **Phase 2 faite** : [rapprochement_2027.py](rapprochement_2027.py), commande `boussole_2027.py integrer`, tests `test_rapprochement_2027.py`. Seuils calibrés à 0,35 et 0,85 (§5.3 ; calibrage dans SUIVI_PROJET.md). **Phase 3 codée** (questionnaire `q1`, spec descripteurs §11 ; [questionnaire_2027.py](questionnaire_2027.py), [annotation_2027.py](annotation_2027.py), commande `boussole_2027.py annoter`) : le pilote et la renotation complète attendent l'accord de l'utilisateur. **Phase 5 faite** : [chaine_2027.py](chaine_2027.py), `boussole_2027.py mise-a-jour --complet`, `planifier` ; tests `test_chaine_2027.py`. Document lié : [spec_descripteurs_2027.md](spec_descripteurs_2027.md).

Écarts de la phase 1 par rapport au texte ci-dessous :
- la mesure garde provisoirement sa fiche historique complète (`proposition`, sans `scoring_context`), qui sert aux calculs et à l'export jusqu'au questionnaire `q1` ;
- les corrections ne portent que sur les réponses des descripteurs ;
- la file reprend les anciennes divergences entre lectures (`divergence_lectures`, priorité basse ; 1 488 mesures), qui disparaîtront avec la renotation `q1` ;
- l'importance structurelle v1 a des poids à recalibrer.

## 0. Décisions déjà prises

- **Une seule méthode pour tout le corpus.** Le corpus est renoté une fois avec le questionnaire unifié (§5.4), environ 3 à 5 $ en batch. Les notes historiques (Jev, révisions, relectures) restent dans les données pour l'audit, mais plus aucune n'est affichée.
- **La note calculée remplace l'ancienne dans l'interface** (spec descripteurs, §8).
- Règles inchangées :
  - aucun appel payant sans plafond explicite ;
  - lecture à l'aveugle (sans le nom du candidat) ;
  - citations retrouvées textuellement dans les sources ;
  - valeur inconnue = `null`, jamais 0 ;
  - ne jamais lire ni afficher `.env` ;
  - ne pas modifier `upstream_repo/`.

## 1. Objectif

Passer de l'initialisation, faite à la main en une dizaine de scripts, à une **mise à jour autonome et répétable**. Quand un candidat publie un document ou fait une annonce, une seule commande :

1. récupère et lit la source ;
2. reconnaît les mesures déjà connues ;
3. note seulement ce qui est nouveau ou modifié ;
4. signale ce qui demande un œil humain ;
5. met l'interface à jour et résume les nouveautés.

Un **tableau de bord local** sert à valider, corriger, retraiter et ajouter des sources.

## 2. Principes

1. **Idempotent** : relancer ne refait et ne repaie rien de ce qui est déjà fait. Le cache est indexé par empreinte, comme aujourd'hui.
2. **Plafonné** : sans `--max-cost`, la commande s'arrête au plan chiffré. Elle a un plafond par run et un plafond mensuel.
3. **L'humain a le dernier mot** : une décision humaine n'est jamais écrasée par un run. Si la mesure change de texte, la décision est marquée « à revoir », pas supprimée.
4. **Traçable** : chaque valeur garde sa provenance (modèle, version du questionnaire, date, ou décision humaine) et son historique.
5. **Une étape = une fonction testable**, enchaînée par un orchestrateur. Pas de fichiers intermédiaires à passer à la main.
6. **Sans framework** : Python standard plus `pypdf`, comme aujourd'hui.

## 3. Constat sur l'existant

| Brique | État | Devenir |
|---|---|---|
| `programme_corpus_2027.py` (collecte, texte, OCR, extraction, export) | incrémental par empreinte de document | **gardé** : étapes Sources et Extraction |
| `update_corpus_2027.py` (pull amont → collecte → OCR → extraction → export, plafond) | autonome sur le début de chaîne | **absorbé** par l'orchestrateur |
| `pipeline_scoring_2027.py` (Jev), `revision_2027.py`, `relecture_ciblee_2027.py`, `axes_2027.py` | quatre passes, quatre modèles | **remplacés** par l'annotation unifiée ; conservés en archive pour relire les caches |
| `selection_scoring_2027.py`, `precision_loop_2027.py` | choisissaient quoi noter, pour économiser | **retirés** : on note tout ; la sélection d'affichage est calculée gratuitement |
| `descripteurs_2027.py` (formules), `descripteurs_corpus_2027.py` | nouvelle méthode | **gardés** : cœur des étapes Annotation et Calculs |
| `export_interface_2027.py` | export allégé | **gardé**, enrichi (nouveautés, explications) |
| `scoring_context_2027.py`, `llm_logging_2027.py` | utilitaires | **gardés** |

Quatre manques :
- pas d'orchestrateur ;
- pas de rapprochement : l'identifiant d'une mesure vient de son titre et de sa description écrits par le modèle, donc une mesure redite ailleurs devient un doublon ;
- pas de mémoire des décisions humaines ;
- pas de vue des nouveautés.

## 4. Modèle de données

### 4.1 Fichiers

| Fichier | Contenu | Écrit par |
|---|---|---|
| `corpus_programmes/` | documents, textes, OCR, extractions (inchangé) | Sources, Extraction |
| `sources_2027.json` | sources ajoutées à la main, URL remplacées ou exclues (remplace `sources_surcharges.json`) | tableau de bord, humain |
| `base_2027.json` | **source de vérité** : candidats, thèmes, mesures avec versions, annotations, calculs, file | orchestrateur |
| `decisions_2027.json` | décisions humaines, en ajout seulement | tableau de bord |
| `cache_annotation_2027.json` | réponses du questionnaire par empreinte | Annotation |
| `cache_rapprochement_2027.json` | verdicts de l'arbitre de rapprochement | Rapprochement |
| `runs/AAAA-MM-JJ_HHMM.json` + `.md` | bilan de chaque run (coûts, nouveautés, alertes) | orchestrateur |
| `donnees_interface_2027.json`, `nouveautes_2027.json` | export pour la constellation | Export |
| `sauvegardes/base_2027_*.json` | 5 dernières versions de la base | orchestrateur |

### 4.2 Une mesure dans `base_2027.json`

```json
{
  "uid": "m-roussel-0412",
  "candidate_id": "roussel", "theme_id": "logement",
  "statut": "active",
  "versions": [
    {"n": 1, "date": "2026-10-12", "title": "...", "description": "...", "empreinte": "…",
     "sources": [{"document_id": "…", "page": 14, "quote": "…", "source_kind": "programme"}]}
  ],
  "annotation": {"version_questionnaire": "q1", "modele": "openai/gpt-6.1-terra", "date": "…",
                 "reponses": {"levier": "depense_ou_service", "eco_etat": "augmente", "…": "…"},
                 "confiances": {"levier": 0.9, "…": 0.0}, "note": "…"},
  "calculs": {"eco": -58, "soc": null, "…": null, "ideologie": -58, "importance": 62,
              "explications": {"eco": "plus d'action publique · vers les modestes · dépense ou service public · portée large"},
              "etiquettes": ["…"], "affichage": "n8"},
  "file": [{"motif": "nouvelle_mesure", "depuis": "2026-11-12"}],
  "decisions": ["d-000183"],
  "historique": {"corpus_id": "corpus-…", "notes_initialisation": {"eco": {"valeur": -50, "methode": "jev"}}}
}
```

- **`uid` stable** : il est attribué à la première apparition et n'est jamais réutilisé. À la migration, chaque `corpus-…` actuel reçoit un `uid`, et la correspondance est gardée dans `historique.corpus_id`.
- **Statuts** :
  - `active` ;
  - `non_reprise` : la source a disparu ou le candidat ne la reprend plus. On la garde, signalée ;
  - `remplacee` : fusionnée dans une autre ;
  - `rejetee` : décision humaine.
- **Versions** : une mesure précisée ou modifiée garde ses versions. L'annotation porte sur la dernière.

### 4.3 Une décision dans `decisions_2027.json`

```json
{"id": "d-000183", "date": "2026-11-12T10:04", "auteur": "local", "uid": "m-roussel-0412", "version": 1,
 "type": "correction", "champ": "levier", "valeur": "controle_prix_ou_revenus", "motif": "tarif réglementé"}
```

| Type | Effet |
|---|---|
| `validation` | la mesure sort de la file ; figée tant que sa version ne change pas |
| `correction` | remplace une réponse du questionnaire ; les calculs sont refaits |
| `rejet` | `statut = rejetee` (pas une mesure, hors sujet, mauvaise attribution), avec un motif |
| `fusion` | `uid` A → B : sources et versions réunies, A passe en `remplacee` |
| `separation` | une mesure mélangeant deux engagements est scindée ; le second reçoit un nouvel `uid` |
| `retraiter` | réannotation demandée au prochain run |
| `note` | commentaire libre, sans effet |

Règle : une décision s'applique à la **version** de la mesure pour laquelle elle a été prise. Si une nouvelle version apparaît, la décision passe « à revoir » dans la file. Elle n'est ni appliquée en silence, ni perdue.

## 5. Étapes du pipeline

Chaque étape lit la base et écrit la base. Pour chacune, l'orchestrateur sait estimer le coût avant d'agir.

### 5.1 Sources (gratuit)

- Dépôt amont : `git pull`, puis liens de programmes (comportement actuel de `update_corpus_2027.py`).
- `sources_2027.json` : sources ajoutées depuis le tableau de bord. Pour chacune : URL ou fichier déposé, candidat, type (`programme`, `entretien`, `discours`, `communique`, `tribune`, `video_transcription`), date de publication, ajoutée par, date d'ajout. Les URL remplacées et exclues y sont reprises.
- Collecte et texte : fonctions actuelles (téléchargement plafonné, empreinte de texte, OCR si besoin et autorisé).
- Une source dont le texte n'a pas changé n'est pas retraitée.

### 5.2 Extraction (payant, plafonné)

- Seulement pour les documents nouveaux ou dont le texte a changé. Fonctions actuelles, cache par morceau.
- Le type de source accompagne l'extraction, car un entretien contient moins de mesures et plus de déclarations.
- La citation doit être retrouvée textuellement, sinon la mesure est rejetée automatiquement et comptée dans le bilan.

### 5.3 Rapprochement (gratuit, sauf arbitrage)

Pour chaque mesure extraite d'une source nouvelle ou modifiée, on cherche une mesure existante **du même candidat** :

1. **Pré-tri gratuit** : texte normalisé (minuscules, sans accents ni mots vides) de titre, description et citation. On calcule un score de similarité, la moyenne de `difflib.SequenceMatcher` et d'un Jaccard sur les mots, contre les mesures du même thème, puis de tous les thèmes si rien n'est trouvé.
2. **Décision selon les seuils** (à calibrer en phase 2 sur les doublons déjà connus du corpus) :
   - au-dessus de 0,85, ou citation identique → **même mesure** : la source est ajoutée, pas de nouvelle version ;
   - entre 0,5 et 0,85 → **arbitrage** par un modèle chat sur la paire. Verdicts possibles : `meme`, `precisee` (même engagement, plus de détails), `modifiee` (engagement changé, par exemple un montant), `differente`. Coût infime, en cache ;
   - en dessous de 0,5 → **nouvelle mesure**.
3. `precisee` ou `modifiee` → nouvelle version de la mesure, réannotée. `modifiee` entre dans la file avec le motif `mesure_modifiee`.
4. Une mesure `active` dont toutes les sources ont disparu, ou qui n'apparaît pas dans un document remplaçant explicitement le précédent (nouvelle version du programme), passe en `non_reprise` et entre dans la file. Elle n'est jamais supprimée automatiquement.

### 5.4 Annotation (payant, plafonné)

**Questionnaire unifié** (version `q1`, à spécifier en phase 3 à partir de spec descripteurs §4 et §7), posé à l'aveugle en un seul passage par mesure :

- descripteurs communs : `levier`, `public_vise`, `portee` ;
- pour chaque axe, sa condition d'application et une ou deux questions de sens :
  - `eco` : `eco_etat`, `eco_distrib` ;
  - `soc` : libertés ou ordre ;
  - `sov` : niveau de décision ;
  - `ouverture` : accueil ou fermeture ;
  - `ecolo` : priorité environnementale ;
  - `rights_status` : accès aux droits selon la nationalité ou le statut ;
- dimensions à choix : `legal_instrument`, `cost_estimate`, ampleur du changement (4 niveaux, ex-`rupture`), faisabilité (5 niveaux), précision (`chiffre` / `precis` / `orientation_generale`).

Fonctionnement :
- **Mode** : appel direct sous 200 mesures à annoter (résultat immédiat), batch au-delà (moitié prix ; le run se termine « en attente » et le suivant récupère).
- **Cache** : clé = version du questionnaire + modèle + texte aveugle de la mesure. Changer de version du questionnaire réannote tout. C'est une décision explicite, chiffrée par `plan`.
- **À annoter** : mesures nouvelles, nouvelles versions, mesures marquées `retraiter`, ou annotation d'une version antérieure du questionnaire.
- **Hors questionnaire** : `media_importance` et `votes` restent des surcharges sourcées, jamais devinées.

### 5.5 Calculs (gratuit)

- Notes d'axe par formule (`descripteurs_2027.py`, étendu aux autres axes).
- Idéologie composite.
- Importance : signaux structurels de position, section et répétitions. Calcul gratuit proposé à la place de la note LLM actuelle, voir §10.
- Étiquettes : « Licorne » (instrument juridique), « Ultra-ciblé » (portée individuelle ou ciblée), « Effet d'annonce » (levier déclaration ou précision « orientation générale »).
- Sélection d'affichage (`n8` / thème complet), recalculée à chaque run.
- Les corrections humaines sont appliquées **avant** les calculs : une réponse corrigée change la note.

### 5.6 Contrôles et file (gratuit)

Motifs d'entrée dans la file, avec une priorité :

| Motif | Priorité |
|---|---|
| `mesure_modifiee` (engagement changé) | haute |
| `decision_a_revoir` (nouvelle version d'une mesure déjà décidée) | haute |
| `rapprochement_incertain` (arbitre peu confiant) | haute |
| `deplacement_fort` (un axe bouge de plus de 25 points entre deux versions ou deux annotations) | moyenne |
| `axe_perdu_ou_gagne` (condition d'axe inversée) | moyenne |
| `nouvelle_mesure` | moyenne |
| `confiance_basse` (une réponse de sens sous 0,5 : `Q.QUESTIONS_SENS`, pas les questions d'ampleur) | basse |
| `non_reprise` | basse |

Une mesure validée sort de la file tant que sa version ne change pas.

### 5.7 Export (gratuit)

- `donnees_interface_2027.json` : uniquement des notes calculées, avec explications en mots, statut, date de dernière modification et badge « nouvelle » ou « modifiée ».
- `nouveautes_2027.json` : depuis le run précédent, les mesures ajoutées, modifiées et non reprises, et les étoiles déplacées de plus de 10 points. La constellation peut en tirer un panneau « Quoi de neuf ».
- Ce qui est publié dépend de la règle de publication (§10, question 1).

### 5.8 Bilan de run (gratuit)

`runs/…json` et un résumé `.md` lisible :
- sources nouvelles ou modifiées ;
- mesures extraites, rapprochées, nouvelles, modifiées, non reprises ;
- coût réel par étape, et cumul du mois ;
- taille de la file par motif ;
- alertes : erreurs réseau, citations introuvables, plafond atteint.

## 6. Orchestrateur `boussole_2027.py`

```text
python .\boussole_2027.py plan                      # gratuit : ce qui serait fait et combien ça coûterait
python .\boussole_2027.py mise-a-jour --max-cost 1  # chaîne complète, plafonnée
python .\boussole_2027.py etape <nom> [...]         # une étape seule (sources, extraction, rapprochement, annotation, calculs, file, export)
python .\boussole_2027.py batch                     # état ou récupération d'un batch en attente (gratuit)
python .\boussole_2027.py renoter --questionnaire q2 --max-cost 5   # réannotation complète, explicite
python .\boussole_2027.py migrer                    # une fois : base_2027.json depuis les données actuelles
python .\boussole_2027.py tableau-de-bord           # lance le serveur local
```

Comportement :
- **Verrou** (`.boussole.lock`) : deux runs ne tournent jamais en même temps.
- **Plafonds** : `--max-cost` par run, plus un plafond mensuel dans `budget_2027.json`, calculé sur le coût réel des journaux. Le run s'arrête proprement à la limite, cache conservé.
- **Codes de sortie** :
  - 0 : terminé ;
  - 1 : en attente d'un batch ;
  - 2 : erreur permanente ou étape incomplète (comportement actuel pour 400/401/402/403/404/422) ;
  - 3 : plafond atteint.
- **Sauvegarde** de la base avant écriture (rotation sur 5) ; écriture atomique (fichier temporaire, puis renommage).
- **Reprise** : un run interrompu reprend à la première étape inachevée, puisque chaque étape est idempotente.

## 7. Tableau de bord local

**Technique** :
- `tableau_de_bord_2027.py` : serveur `http.server`, écoute **uniquement sur 127.0.0.1**, sans dépendance.
- `tableau_de_bord_2027.html` : page statique, même design que la constellation (variables de couleur, clair et sombre).
- La page ne lit jamais `.env` et n'affiche aucune clé.
- Elle écrit seulement dans `decisions_2027.json` et `sources_2027.json`, plus les demandes de run.

**API JSON** :

| Route | Rôle |
|---|---|
| `GET /api/etat` | dernier run, coûts du mois, batch en cours, taille de la file |
| `GET /api/file?motif=&candidat=&theme=` | file de validation |
| `GET /api/mesure/<uid>` | fiche complète (versions, sources, réponses, calculs, décisions) |
| `GET /api/mesures?q=&candidat=&theme=&statut=` | recherche |
| `GET /api/sources`, `GET /api/runs` | listes |
| `POST /api/decision` | ajoute une décision ; renvoie la mesure recalculée (calculs gratuits, immédiats) |
| `POST /api/source` | ajoute, remplace ou exclut une source (URL ou fichier déposé, stocké dans `corpus_programmes/depots/`) |
| `POST /api/run` | `plan` sans condition ; `mise-a-jour` seulement avec un plafond saisi et une confirmation |

**Vues** :
1. **Accueil** : état, nouveautés depuis le dernier run, file par motif, coûts du mois sur le plafond, batch en cours, boutons « Plan » et « Mettre à jour… » (plafond demandé).
2. **À valider** : liste filtrable, triée par priorité, avec des raccourcis clavier (V valider, R rejeter, J/K suivant/précédent). La fiche montre :
   - la citation surlignée et le lien vers la source à la bonne page ;
   - les réponses en listes déroulantes : changer une réponse recalcule la note et l'explication aussitôt ;
   - l'historique des versions ;
   - les mesures proches du même candidat, pour fusionner ;
   - l'ancienne et la nouvelle position sur chaque axe.
3. **Mesures** : recherche plein texte, filtres, actions groupées (retraiter, rejeter).
4. **Sources** : liste par candidat (date, type, état, nombre de mesures), ajout d'une URL ou d'un fichier, exclusion, remplacement.
5. **Runs** : historique, bilans `.md`, coûts réels par étape.

## 8. Automatisation

- **Planification** : tâche planifiée Windows (`schtasks`), hebdomadaire, par exemple le lundi à 7 h. Elle lance `boussole_2027.py mise-a-jour --max-cost 1` avec un plafond mensuel de 5 $. Le plafond est fixé par l'utilisateur lors de la mise en place.
- **Coût récurrent attendu** : un nouveau document de programme coûte environ 0,3 $ d'extraction, plus environ 0,001 $ par mesure annotée ; un entretien, quelques centimes. Une semaine sans annonce coûte 0 $.
- **Sortie** : bilan `.md` dans `runs/`, et file mise à jour pour le tableau de bord. La notification (courriel, téléphone) est hors périmètre de la v1.
- **Arrêt de sécurité** : erreur permanente, plafond atteint, ou plus de 300 mesures nouvelles d'un coup (probable changement de format ou de source). Le run s'arrête au plan et attend une validation manuelle.

## 9. Migration depuis l'initialisation

1. Récupérer le batch des descripteurs, écrire `donnees_descripteurs_2027.json` et brancher la note eco calculée. Étape en cours.
2. `migrer` : construire `base_2027.json` depuis les données actuelles. `uid` attribués, version 1 = texte actuel, notes d'initialisation rangées dans `historique`, réponses des descripteurs reprises. Gratuit.
3. Calibrer les seuils de rapprochement sur le corpus actuel : les quasi-doublons écartés par `selection_scoring_2027.py` servent d'exemples. Gratuit.
4. Spécifier le questionnaire `q1` (extension des descripteurs aux autres axes), puis lancer un pilote d'environ 100 mesures (environ 0,15 $).
5. Renoter tout le corpus avec `q1` en batch (environ 3 à 5 $, accord requis). Les réponses eco des descripteurs sont reprises si le questionnaire `q1` les contient à l'identique.
6. Archiver les scripts d'initialisation dans `archives/` (Jev, révision, relecture, axes, sélection, précision). Les caches sont gardés.

## 10. Décisions (utilisateur, 2026-11-06)

1. **Publication** : une mesure de motif `nouvelle_mesure` ou `confiance_basse` apparaît tout de suite, avec un badge « non relue ». Une mesure `mesure_modifiee` ou `rapprochement_incertain` garde sa version publiée précédente jusqu'à validation, parce qu'une erreur fausserait une position existante.
2. **Importance** : calculée gratuitement à partir des signaux structurels (position dans le document, section de synthèse, répétitions, nombre de sources). Elle remplace la note LLM, qui sature.
3. **Horizon** : retiré du questionnaire `q1` ; l'ancienne valeur reste dans `historique`.
4. **Fréquence** : hebdomadaire pour l'instant, à accélérer plus tard. Le tableau de bord doit permettre d'**ajouter un document à tout moment** (URL ou fichier déposé), puis de lancer une mise à jour plafonnée.
5. **Validation** : un seul validateur en v1 (`auteur = "local"`) ; le format permet d'en ajouter plus tard.

## 11. Phasage

| Phase | Contenu | Coût |
|---|---|---|
| 1 | Base unique, migration, décisions humaines, orchestrateur des étapes gratuites (calculs, file, export, bilan) | 0 $ |
| 2 | Rapprochement (pré-tri, arbitre, versions, non reprise) et calibrage | centimes |
| 3 | Questionnaire `q1` : spécification, pilote, renotation complète | ≈ 0,15 $ + 3 à 5 $ |
| 4 | Tableau de bord : d'abord validation et sources, puis mesures et runs | 0 $ |
| 5 | Orchestrateur complet (sources, extraction, annotation, batch) et planification | 0 $ (puis récurrent faible) |

**Tests** : chaque étape a ses tests synthétiques, sans réseau. Un **test de bout en bout** simule deux runs : le second ajoute un document contenant une mesure redite, une mesure modifiée et une nouvelle. On vérifie que :
- les `uid` restent stables ;
- les versions sont correctes ;
- la file contient les bons motifs ;
- une décision prise entre les deux runs est conservée ;
- une décision sur une mesure modifiée passe « à revoir ».
