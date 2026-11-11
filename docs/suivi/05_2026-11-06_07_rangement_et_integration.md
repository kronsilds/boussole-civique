# Suivi : rangement, file de validation et intégration (2026-11-06 et 07)

> Sous-fichier de [SUIVI_PROJET.md](../../SUIVI_PROJET.md) (sommaire et état courant). Précédent : [04](04_2026-11-06_q1_effort_et_chaine.md) · Suivant : [06](06_2026-11-07_contexte_lexique_importance.md)

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
