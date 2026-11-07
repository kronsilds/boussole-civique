# Spécification : votes parlementaires (conception, rien n'est codé)

Statut : conception du 2026-11-07 ; phases 1 et 2 codées dans [votes_2027.py](../votes_2027.py) (import, votants, liens vote-mesure ; tests sur fixtures). Schéma confirmé sur les vrais fichiers le 2026-11-07 (§2). Elle prolonge [spec_pipeline_unifie_2027.md](spec_pipeline_unifie_2027.md) (§5.4 : « `media_importance` et `votes` restent des surcharges sourcées, jamais devinées »).

## 1. Objet et limites

Joindre aux mesures des programmes les votes réels des candidats à l'Assemblée nationale, pour répondre à une question que le programme seul ne peut pas poser : **ce candidat a-t-il voté comme il le promet ?**

Ce que la fonction ne fait pas :
- elle ne déduit aucun vote d'un programme, ni aucune mesure d'un vote ;
- elle ne rattache jamais seule un scrutin à une mesure : un humain valide chaque lien ;
- elle n'entre pas dans la notation à l'aveugle (questionnaire `q1`) : les votes ne sont jamais envoyés aux modèles qui notent une mesure ;
- elle ne remplace pas la valeur « inconnu » par 0 : sans vote lié, le résultat reste `null`.

## 2. Ce qui est établi sur les sources

Vérifié le 2026-11-07 :
- l'Assemblée nationale publie les scrutins publics en données ouvertes sous Licence ouverte, au format JSON et XML (pas de CSV), avec la position de chaque député. Pour la 17e législature : `http://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip` (et `.xml.zip`). Les deux fichiers sont recréés régulièrement (horodatage du jour de la consultation).
- Datan.fr et NosDéputés.fr rediffusent ces données (statistiques par groupe, fiches de députés) ; elles servent à vérifier, pas de source primaire.

Confirmé sur les fichiers réels (Scrutins 17e : 9 759 scrutins, un fichier JSON par scrutin ; AMO30 : 14 056 fichiers, un par acteur ou organe) :
- schéma lu par `lire_scrutin`, `acteurs_de` et `chercher_acteurs` (sans modification de fond) ;
- le lien officiel `https://www.assemblee-nationale.fr/dyn/17/scrutins/<numéro>` répond ;
- les scrutins des 16e et 15e législatures sont importés avec le même code : `repository/16/loi/scrutins/Scrutins.json.zip` (10,1 Mo) et, pour la 15e, `repository/15/loi/scrutins/Scrutins_XV.json.zip` (9,2 Mo, nom différent).

Découvert dans les fichiers, et pris en compte :
- **Mises au point** : dans 1 734 scrutins sur 9 759 (18 %), des députés ont publié la position qu'ils voulaient donner. Elle est gardée à côté du vote enregistré (`mise_au_point`), jamais à sa place.
- **Absent** : un député peut n'apparaître dans aucune liste nominative et pourtant avoir une mise au point ; sa position est `absent`, pas `non_votant`.
- **Non-votant** : `causePositionVote` donne la cause (MG membre du gouvernement, PAN président de l'Assemblée, PSE président de séance), gardée dans `cause` : ce n'est pas une abstention.
- **Délégation** : `parDelegation` est gardé (`delegue`).

Non vérifié :
- les équivalents pour le Sénat et le Parlement européen. Le jeu agrégé de data.gouv.fr qui les réunit est un travail tiers, dont les résumés ne sont pas officiels : ne pas s'en servir comme source.

## 3. Décisions à trancher d'abord

| # | Question | Recommandation |
|---|---|---|
| 1 | Que mesure « votes » ? Aujourd'hui `importance_sources.votes` (poids .25) est une composante de l'**importance**. Or un vote contre une mesure ne dit pas qu'elle est peu importante, il dit que le candidat la contredit. | Deux notions séparées. **Cohérence** (nouvelle, §6) : le candidat vote-t-il comme il le promet ? **Importance** : on garde la composante `votes` à `null` et on ne l'alimente que plus tard, avec un signal différent (mesure portée par le candidat : amendement ou proposition de loi qu'il signe). |
| 2 | Législatures | 17e d'abord, 16e ensuite (même format). Les mesures du programme 2027 se comparent à des votes récents ; au-delà, trop de textes ont changé. |
| 3 | Vote du groupe | Affiché, **jamais compté** dans la cohérence du candidat (discipline de groupe ≠ choix personnel, vote par délégation compris). |
| 4 | Sénat et Parlement européen | Hors périmètre de la phase 1 (Retailleau a siégé au Sénat, Glucksmann au Parlement européen). Même modèle de données, sources officielles à vérifier une par une. |
| 5 | Qui a des votes ? | Ne pas le décider à la main : le fichier `votants` (§4) le dit. Un candidat sans mandat à l'Assemblée affiche « pas de vote à l'Assemblée », distinct de « aucun vote lié ». |

## 4. Données

Tous les chemins viennent de `boussole_2027.chemins()`. Entrées versionnées, comme `decisions_2027.json` : jamais écrasées par un run.

- **`donnees/votants_2027.json`** (versionné, saisi puis validé) : par candidat, son identifiant officiel d'acteur.
  `{ "votants": { "ruffin": { "an_acteur": "PA…", "confirme_le": "…" } } }`
  Les mandats et les groupes ne sont pas saisis : ils se lisent dans les scrutins eux-mêmes (le groupe est celui sous lequel le député figure **à la date du vote**). La recherche nom → identifiant (`votes chercher`, dans le fichier officiel des acteurs) **propose**, un humain confirme ; les homonymes sont montrés avec leur naissance et leurs mandats.
- **`donnees/scrutins_2027.json`** (ignoré par git, recréé) : seulement ce qui sert. Par scrutin : `id`, législature, date, titre, objet, type (ordinaire, solennel, motion, amendement, article, ensemble d'un texte), résultat, lien officiel. Par votant suivi : sa position (`pour`, `contre`, `abstention`, `non_votant`), un drapeau `delegue` et le groupe de l'époque. Un indice gratuit `portee_probable` (motion, amendement, article, ensemble, inconnue) aide l'humain, sans jamais valoir verdict. Par groupe : répartition des positions. Le fichier brut téléchargé est conservé dans `corpus_programmes/votes/` avec son empreinte SHA-256 (même principe que le cache par empreinte du corpus).
- **`donnees/liens_votes_2027.json`** (versionné) : un lien est une décision humaine.
  `{ "id": "lv-000001", "type": "lien", "uid": "m-ruffin-12", "version": 2, "scrutin": "…", "relation": "conforme|contraire|partielle|sans_rapport", "portee": "mesure|article|amendement|texte_compose", "preuve": "passage du texte voté", "note": "…", "vote_vu": { "position": "pour", "mise_au_point": null, "delegue": false }, "date": "…", "auteur": "local", "origine": "humain|suggestion_validee" }`
  Réalisé en phase 2 : journal **en ajout seulement** (`{"journal": [...]}`). Un lien remplace le précédent pour le même couple mesure-scrutin ; un retrait est une ligne `{"type": "retrait", "lien": "lv-…"}`, rien n'est effacé. Le champ `votant` est abandonné : seul le vote du candidat se relie, le groupe reste un contexte affiché (décision 3).
  Même règle que les décisions : lié à la **version** de la mesure **et** au vote vu (`vote_vu`). Si la mesure change, ou si l'Assemblée rectifie le vote (position, mise au point, délégation), le lien passe « à revoir » (`mesure_modifiee`, `vote_rectifie`, `vote_absent`) et n'est plus exporté tant qu'il n'est pas reconfirmé. Cet état est calculé à la lecture, il n'entre pas dans la file des mesures (liste « Liens » de l'onglet Votes, compteur sur l'accueil).

## 5. Étapes du pipeline

1. **Import (gratuit, réseau)** : `boussole_2027.py votes importer [--legislature 17]`. Télécharge l'archive officielle (hôte fixe, taille plafonnée, empreinte), la décompresse, ne garde que les scrutins où un votant suivi a une position. Relancer sans changement de fichier ne refait rien.
2. **Suggestions (gratuit)** : pour chaque mesure d'un candidat qui a des votes, pré-tri lexical (le même outil de normalisation et de similarité que [rapprochement_2027.py](rapprochement_2027.py)) entre le titre et la description de la mesure et le titre et l'objet des scrutins, restreint aux scrutins que ce candidat a votés. Résultat : une liste ordonnée, jamais un lien.
3. **Arbitrage (optionnel, payant, plafonné)** : `boussole_2027.py votes arbitrer --max-cost X`. Un modèle lit la mesure et l'objet du scrutin, **sans nom de candidat ni de groupe**, et répond : le texte voté contient la mesure, la contredit, la contient en partie ou n'a pas de rapport, avec le passage qui le prouve. Sortie : une suggestion triée pour l'humain. Les citations doivent être retrouvées textuellement, comme pour l'extraction. Comme tout appel payant du projet : en plan par défaut, `plan` affiche l'estimation, rien sans plafond explicite.
4. **Validation (humain, tableau de bord)** : §7.
5. **Calcul et export (gratuit)** : §6. Intégré à `mise-a-jour` après `file` et avant `export`.

## 6. Calculs

Rien n'est calculé à partir d'un lien non validé.

Par mesure, sur les liens `votant = candidat` et `portee ≠ texte_compose` :
- vote `pour` sur un texte qui contient la mesure → conforme ; `contre` → contraire ;
- vote `contre` sur un texte qui contredit la mesure → conforme (vote cohérent avec la promesse) ; `pour` → contraire ;
- `abstention` → 50 ; `non_votant` et `delegue` → ignorés (absence ≠ désaccord) ;
- `partielle` compte demi-poids ; `sans_rapport` n'entre pas dans le calcul.

Un vote sur un **texte composite** (budget, loi omnibus) est affiché mais ne conclut jamais « contradiction » : `portee = texte_compose` est exclue du calcul, par règle écrite ici et non par réglage.

Par étoile (candidat × thème) : part des mesures liées dont le vote est conforme, avec le nombre de mesures liées ; `null` s'il n'y en a aucune. Fiabilité : comme pour les axes (pleine à partir de 10 mesures liées), l'étoile reste « fragile » en dessous.

Export (`donnees_interface_2027.json`, format compact) : `proposals[].votes` = liste courte `[scrutin, date, titre, position, relation, votant, lien]`, plus un axe `coherence_votes` (0 à 100, `null`) par mesure. Les positions de vote sont des données publiques nominatives d'élus : source citée (Assemblée nationale, Licence ouverte), jamais de commentaire généré.

## 7. Tableau de bord (nouvel onglet « Votes »)

Même principes que le reste : rien de payant d'ici, chaque geste est une décision gardée.
- **Votants** : par candidat, identifiants et mandats proposés, à confirmer. Couverture visible : scrutins votés, scrutins liés.
- **À relier** : file des suggestions, les plus solides d'abord. Une fiche montre côte à côte la mesure (citation, source) et le scrutin (titre, objet, lien officiel, position du candidat, répartition du groupe). Boutons : *Conforme*, *Contraire*, *En partie*, *Sans rapport*, liste « portée », case « le texte voté est composite ». **Valider** enregistre le lien.
- **Dans la fiche d'une mesure** : bloc « Votes liés » (liste, retrait d'un lien) et « Ajouter un vote » (recherche par mot dans les scrutins du candidat).
- **Accueil** : compteurs (scrutins importés, suggestions en attente, liens validés) et date du dernier import.

## 8. Constellation

- Fiche d'une proposition : bloc « Votes » (date, intitulé, position, lien officiel). Masqué en mode « noms masqués », comme la source : une position de vote identifie le candidat.
- Fiche d'une étoile : curseur « Cohérence des votes » avec décompte, ouvrable comme les autres axes (liste des mesures liées, voir [constellation_2027.html](../web/constellation_2027.html)).
- Réglages : le curseur « Votes (non renseigné) » du groupe Importance disparaît tant que la décision 1 n'est pas prise pour l'importance ; la cohérence devient un axe ou un halo au choix.
- Légende de lecture : un candidat sans mandat à l'Assemblée est signalé « pas de vote à l'Assemblée ».

## 9. Pièges à traiter explicitement

- **Homonymes** et changements de groupe en cours de législature : le groupe se lit à la date du scrutin.
- **Non-votant ≠ abstention** ; vote par délégation : la position publiée est celle du délégant, pas un choix du député.
- **Scrutin sur un amendement ou un article** (précis) ≠ vote sur l'ensemble du texte (composite) : `portee` le distingue ; un texte peut être adopté malgré un article contraire.
- **Mesure du programme ≠ texte de loi** : une mesure peut être un objectif sans texte. « Sans rapport » est une réponse normale ; la majorité des mesures n'aura aucun lien.
- **Candidat sans mandat** : aucune donnée, aucun score.
- **Réévaluation** : un lien est à revoir si la mesure change de version ou si le fichier officiel rectifie une position (le diff d'import le signale).

## 10. Phasage et tests

| Phase | Contenu | Coût |
|---|---|---|
| 1 | `votes_2027.py` : import, schéma figé sur un vrai fichier, `votants_2027.json`, commandes `votes importer`, `votes plan` ; tests sur un extrait de scrutins en fixture (aucun réseau) | gratuit |
| 2 | Liens manuels : onglet « Votes » (liste, fiche, ajout, retrait), `liens_votes_2027.json`, export `proposals[].votes`, bloc dans la fiche de la constellation | gratuit, **fait** (2026-11-07). Écart avec §7 : pas de file de suggestions (phase 3) ; la recherche par mots dans les scrutins du candidat sert de point d'entrée, depuis l'onglet Votes ou depuis la fiche d'une mesure |
| 3 | Pré-tri lexical (gratuit) puis arbitrage LLM plafonné, journal des appels dans `logs/` | plafonné |
| 4 | Calcul de cohérence, axe constellation, décision sur l'importance (décision 1) | gratuit |

Tests à écrire avec chaque phase : homonyme, non-votant, délégation, texte composite sans conclusion, changement de groupe, lien invalidé par une nouvelle version de mesure, import idempotent, archive tronquée, absence de nom de candidat dans la requête d'arbitrage.

## 11. Sources

- [Scrutins de l'Assemblée nationale (données ouvertes)](https://data.assemblee-nationale.fr/travaux-parlementaires/votes)
- [Datan : questions et licence](https://datan.fr/faq)
- [Nos Parlementaires sur data.gouv.fr](https://www.data.gouv.fr/organizations/nos-parlementaires)
