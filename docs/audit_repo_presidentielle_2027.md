# Dépôt présidentiel 2027 — audit technique et intégration

**État observé :** 3 novembre 2026. **Clone shallow**, `bc092b396f653a9e788f4c45a02c1baeb67d6722` (2026-11-03T09:45:15Z). **244 fichiers suivis** dans ce commit. Ce rapport décrit l’état du snapshot, susceptible de changer sur `main`.

## Structure générale (tous les fichiers suivis)

La liste complète, fichier par fichier, est fournie dans `presidentielle_2027_repo_manifest.txt`. Les répertoires de premier niveau et leur rôle :

- `.github/` : formulaires d’issues et workflows de Pages, desktop, élections/parrainages, votes et veille quotidienne.
- `.claude/` : configuration d’environnement de lancement.
- `electron/` : lanceur Electron et icônes de bureau.
- `public/` : favicon, manifeste, service worker, preuve d’indexation, images Open Graph pour l’accueil, les 15 candidats, les 20 thèmes et les votes.
- `public-data/` : bundles JSON v2 et compatibilité v1.
- `research/` : fiches de recherche candidates (15), dossiers approfondis/changements et contre-vérifications, procédure/schéma, propositions archivées, votes/explications, veille et source de parrainages.
- `scripts/` : export/validation, fusion recherche/votes, veille, contrôle de liens, génération d’images, fetch d’open data, pages de partage.
- `src/` : application React/TypeScript, composants/pages, données éditoriales, mesures par candidat, utilitaires et styles.
- Racine : `README.md`, `package.json`/lock, `index.html`, configurations TypeScript/Vite, `.gitignore` et rapport de liens.

### Arborescence fonctionnelle

```text
.github/{ISSUE_TEMPLATE,workflows}
electron/
public/{og/}
public-data/
research/{candidates,deep,parrainages,pending/done,votes/explications,watch}
scripts/{lib}
src/{components,data/measures,lib,pages}
```

### Données, thèmes et visuels constatés

- 15 profils, identifiants `arthaud`, `attal`, `bertrand`, `dupont-aignan`, `glucksmann`, `le-pen`, `lisnard`, `melenchon`, `philippe`, `retailleau`, `roussel`, `ruffin`, `tondelier`, `villepin`, `zemmour`.
- Chaque profil de `public-data/data-v2.json` a une couleur et un `photo` Wikimedia `{url, commons_page, author, license}`; c’est le format consommé dans `CandidateAvatar.tsx`. Les images du dossier `public/og/` sont des images de partage (pas les portraits réutilisés dans la fiche candidate).
- 20 thèmes canoniques (`id`, `label`, `short`, `icon`, `description`, `indicators[]`), icônes Lucide répertoriées dans `ThemeIcon.tsx` : Économie, Fiscalité, Emploi, Retraites, Énergie, Écologie, Agriculture, Logement, Santé, Éducation, Sécurité, Immigration, Institutions, Europe, International, Numérique, Culture, Outre-mer, Services publics, Famille.
- 1 295 mesures réparties par identifiant candidat, avec intitulé/description, thème, type/précision de source, lien/titre/date/page, indicateur facultatif, coût facultatif, vérification/ajout. Elles ne contiennent pas de champs natifs de « faisabilité », de score idéologique ou d’importance composite.
- Les autres sections du bundle v2 sont `link_status` (607 entrées), changelog (7), glossaire (80), scrutins (115), explications de votes (115), calendrier, parrainages, temps de parole, contexte, budgets, HATVP et résultats. Le schéma complet inféré à partir du JSON réel (types, structures, champs optionnels) est joint dans `presidentielle_2027_data_v2_structure.json`.

### Applications et automatisations repérées

- App statique Vite/React/TypeScript; les workflows republient Pages après changement, construisent les releases desktop, récupèrent parrainages/temps de parole et votes, et produisent un rapport de surveillance des pages de candidats.
- Le bundle v2 est généré par `scripts/export-data.ts` à partir de `src/data/*`, puis validé avec le schéma Zod (`src/data/schema.ts`). `src/data/remote.ts` montre que la version desktop peut vérifier une mise à jour à distance. La surveillance `watch-sources` crée un rapport de changements : elle ne fait pas le scoring des mesures.
- Mise à jour LLM avec décision éditoriale : le dépôt archive les changements puis demande validation indépendante; le scoring automatique n’est pas un flux upstream du site et le pipeline ajouté n’écrit/publie rien dans le dépôt.

## État complet de `public-data/data-v2.json`

Version `{data['version']}`, generated_at `{data['generated_at']}`, bundle {structure['snapshot']['bundle_bytes']:,} octets. Forme racine (types et volumes) :

- `version` — int: 2
- `generated_at` — str: 2026-11-02T05:18:04.929Z
- `meta` — object[6 keys]
- `themes` — array[20]
- `candidates` — array[15]
- `measures` — object[15 keys]
- `link_status` — object[607 keys]
- `changelog` — array[7]
- `glossary` — array[80]
- `votes` — object[4 keys]
- `vote_explanations` — array[115]
- `calendar` — object[4 keys]
- `parrainages` — object[8 keys]
- `speaking_time` — object[5 keys]
- `context` — object[2 keys]
- `budgets` — object[3 keys]
- `hatvp` — object[4 keys]
- `results` — object[1 keys]

La structure champ par champ, y compris les tableaux imbriqués et les champs parfois absents, est annexée dans le JSON de structure. `public-data/data.json` porte les mêmes sections, mais `version: 1`; il sert de compatibilité et l’export précise que ses indicateurs sont aplatis au premier indicateur dans les anciennes mesures.

## Modifications des livrables précédents

### `pipeline_scoring_2027.py`
- Ajout d’un adaptateur spécifique au schéma de production du dépôt (pas seulement le format générique de démonstration): lecture locale via `--repo-dir`, URL publique via `--url`, ou `--input` du JSON v2.
- Option `--sync-repo` pour un `git pull --ff-only` explicite avant lecture; aucune synchronisation implicite ni écriture dans le clone.
- Préserve les identifiants de candidats et de thèmes, libellés/icônes de thèmes, `indicator`, coûts et métadonnées source. Expose l’URL, l’auteur/licence, la page Commons, la couleur et les informations de programme pour chaque candidat.
- Les valeurs absentes de l’amont (idéologie, importance, faisabilité, droits et impact budgétaire annuel) restent nulles; aucune mesure factuelle n’est remplacée par le jeu synthétique HTML.
- Avec `--llm`, conserve dans le fichier `--out` la sortie du précédent run et son SHA-256 du contenu de mesure/source. À chaque exécution, seules les propositions nouvelles ou modifiées sont envoyées au LLM; celles inchangées réutilisent leur score. Il faut conserver le même fichier de sortie pour garder ce cache. Le secret API demeure nécessaire, via `LLM_API_KEY`.

Exemples d’usage :

```bash
python pipeline_scoring_2027.py --repo-dir ./presidentielle-2027-comparateur --out scores.json
python pipeline_scoring_2027.py --repo-dir ./presidentielle-2027-comparateur --sync-repo --llm --out scores.json
# ou lire directement le paquet amont
python pipeline_scoring_2027.py --url https://raw.githubusercontent.com/coucou123212321232123/presidentielle-2027-comparateur/main/public-data/data-v2.json --out scores.json
```

### `visualisation_programmes_2027.html`
- Ajout d’un mode distinct « Ouvrir le comparateur réel », qui télécharge le bundle v2 brut à la demande; le graphique préexistant demeure explicitement une démonstration synthétique et les deux jeux ne sont pas mélangés.
- Le panneau réel propose recherche texte, filtres candidats/thèmes, portraits Wikimedia (attribution/licence en infobulle), couleurs du dépôt, icônes/labels de thèmes, description et source, indicateurs/coûts présents, et lien du programme de référence.
- Explique que les scores comparatifs absents du schéma ne sont pas calculés. Si la récupération échoue, le panneau l’indique sans montrer de propositions fictives comme données réelles.

## Vérifications effectuées

- Clone et inventaire des fichiers suivis; lecture du README, des définitions du schéma, du pipeline d’export, des composants avatar/thème et des workflows.
- Adaptateur exécuté sur le clone: échantillon de 5 lignes; sortie correctement structurée et montrant 15 profils, 20 thèmes, photo/licence/couleur et champs de source.
- Test unitaire hors ligne du cache LLM avec fonction simulée : 1 295 nouvelles mesures scorées à l’initialisation, 1 295 réutilisées au rerun inchangé, puis exactement 1 mesure rescannée après modification d’une mesure.
- `py_compile` réussi; `node --check` réussi pour le nouveau JavaScript HTML; JSON de démonstration intégré toujours valide (22 mesures fictives).

## Limites et notes

- Le passage « Le but de mon site est différent, mais on peut s’appuyer… » ne figure pas dans les messages de continuité fournis ici (qui sont vides). Je ne peux donc pas établir si ce message a été tronqué ni reconstituer sa suite.
- Le mode HTML a besoin du réseau et de l’accès navigateur au `raw.githubusercontent.com`; le fichier est conçu pour être servi par HTTP(S), et le comportement `file://` dépend des restrictions CORS du navigateur.
- Le score LLM n’a pas été exécuté contre un fournisseur réel (pas de clé/API demandée ou fournie); son caractère incrémental a été testé avec un mock. Les notes générées par un LLM exigent une révision humaine et ne sont pas des valeurs publiées par le dépôt.
- Aucun des scripts du dépôt n’a été modifié, et aucune donnée n’a été poussée vers GitHub.
