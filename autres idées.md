# d'autres idées

# GPT SOL

Oui — mais je construirais ce projet comme un **atlas des promesses traçables**, plutôt qu’un « comparateur de candidats notés ». La différence est fondamentale : chaque point doit pouvoir expliquer **ce qui est proposé, d’où cela vient, comment il est évalué et ce qui reste incertain**.

### 1. Divergence sauvage : quelle forme donner au projet ?

- **La galaxie des promesses** : les propositions se placent dans un espace politique ; les portraits des candidats deviennent des filtres, pas les centres de gravité.
- **Le ticket de caisse présidentiel** : chaque mesure affiche son coût, ses bénéficiaires et son financement annoncé. En bas : les dépenses impossibles à additionner sans double compte.
- **Le tribunal des promesses** — piste volontairement dérangeante : chaque proposition comparaît avec ses pièces, ses objections et ses contradictions. Visuellement fort, mais trop accusatoire pour servir d’interface principale.
- **Le collisionneur de programmes** : on masque les noms des candidats, on rapproche les propositions similaires, puis on révèle qui les porte. On découvre des convergences inattendues et des différences derrière des slogans identiques.

**Je retiendrais le collisionneur**, avec une vue « galaxie ». C’est singulier, exploitable et cohérent avec ton idée : **évaluer la mesure indépendamment de son auteur**, puis rendre son contexte politique visible.

---

### 2. Le choix structurant : séparer quatre couches

Ne mélange pas dans une même note :

| Couche | Ce qu’elle contient |
|---|---|
| **Proposition** | Le contenu concret : action, public, montant, calendrier, conditions |
| **Sources** | Programme, discours, interview, amendement, vote |
| **Évaluations** | Positionnement, faisabilité, coût estimé, avec méthode et justification |
| **Contexte candidat** | Candidature, parti, sondages, évolution des priorités |

Cela permet de mettre à jour un sondage sans toucher aux propositions, ou de réviser un chiffrage sans réécrire le programme.

**Une interview peut modifier la visibilité d’une proposition ; elle ne doit pas automatiquement modifier sa faisabilité.**

### 3. Tes dimensions, rendues mesurables

| Dimension | Modélisation recommandée | Précaution |
|---|---|---|
| **Gauche / droite** | Deux axes : économique et socioculturel ; synthèse facultative | Un axe unique écrase les mesures hybrides. Prévoir « non classable » |
| **Importance** | Priorité déclarée + visibilité dans les sources + récurrence | La position dans un PDF n’est qu’un indice faible |
| **Faisabilité** | Évaluations distinctes : juridique, budgétaire, administrative, calendrier | Un financement non précisé n’équivaut pas à une impossibilité |
| **Bénéficiaires** | Conditions de revenus/patrimoine, nationalité/résidence, autres critères | Séparer bénéficiaires directs, personnes éligibles et personnes affectées |
| **Coût / gain** | Dépenses et recettes, annuelles et ponctuelles, horizon et fourchette | « Gain pour l’État » et « gain pour les ménages » ne sont pas la même chose |
| **Intention de vote** | Série datée, liée au candidat et à une hypothèse de scrutin | Ce n’est pas une propriété de la proposition |

Pour les bénéficiaires, conserver les critères détaillés : âge, territoire, profession, situation familiale… Un score synthétique de couverture peut ensuite être calculé **si les données permettent d’estimer la population concernée**.

Pour le coût, distinguer systématiquement :

- **chiffrage du candidat** ;
- **estimation externe** ;
- **évaluation éditoriale du projet** ;
- **absence de chiffrage**.

**Inconnu ne doit jamais devenir zéro.**

### 4. L’unité de base : une proposition atomique, mais contextualisée

Exemple fictif :

> « Revaloriser une prestation de 10 %, sous condition de ressources, dès 2028. »

La fiche normalisée comprendrait :

```text
Identifiant stable
Candidat et version du programme
Intitulé neutre
Citation originale et référence précise
Action et objet
Thème principal et thèmes secondaires
Public, conditions d’éligibilité, exclusions
Montant, calendrier, financement annoncé
Liens vers les propositions associées
Évaluations sourcées et niveau de confiance
Statut de validation
```

Il faut découper les engagements composites, **sans perdre leurs dépendances** : une dépense et la recette censée la financer doivent rester reliées.

Prévoir aussi un regroupement en **familles de mesures** : deux candidats peuvent proposer une baisse d’impôt similaire sans avoir les mêmes taux, publics ou conditions.

### 5. Une chaîne de mise à jour robuste

**Sources → instantanés archivés → extraction → propositions candidates → validation → évaluations → publication**

Concrètement :

1. **Registre des sources** : URL, auteur, date, nature, caractère officiel ou secondaire.
2. **Archivage** : conserver chaque version et détecter les changements.
3. **Extraction assistée par IA** : découpage, thèmes, critères, rapprochements.
4. **Validation humaine** : contrôler le sens, les omissions, les doublons et les citations.
5. **Évaluation selon une grille publique**.
6. **Historique des modifications** : montrer ce qui a changé, quand et pourquoi.

L’IA peut suggérer ; **elle ne devrait pas publier seule une note politique ou un verdict juridique**.

Pour les votes parlementaires, enregistrer le texte exact, la date, le votant et la relation avec la proposition. Un vote sur un texte composite ne suffit pas à conclure « contradiction ». Distinguer également le vote personnel du candidat et celui de son groupe.

La source que tu indiques, **programmes-2027.fr**, peut entrer dans ce registre. Sans l’avoir vérifiée ici, je la traiterais comme un point d’entrée à confronter aux documents originaux, pas comme une autorité unique.

### 6. La visualisation : expressive, sans fausse précision

**Vue principale : nuage de propositions**

- X et Y : dimensions sélectionnables.
- Taille : importance, couverture ou montant, lorsque ces données sont comparables.
- Couleur : thème **ou** candidat, au choix.
- Portrait : optionnel, surtout dans les vues filtrées.
- Clic : citation, source, méthode, incertitude, historique.
- Mode **« noms masqués »** : comparer avant de révéler les auteurs.

Quelques règles importantes :

- Les données manquantes apparaissent dans une zone **« non évalué »**, pas au centre du graphique.
- Les coûts négatifs et positifs ne peuvent pas être représentés uniquement par une taille de bulle : il faut aussi distinguer leur sens.
- Afficher une vue en liste accessible, utilisable sur mobile et au clavier.
- Éviter les portraits sur toutes les bulles : ils deviennent vite illisibles.

Pour les emotes, je préférerais des **signaux descriptifs avec légende** :

- ⚖️ obstacle juridique identifié ;
- 🧾 financement non précisé ;
- ⏳ calendrier contesté ;
- ↔️ estimations divergentes.

Éviter « 🤡 infaisable » ou « 💸 coûteux » : ils transforment une analyse contestable en jugement instantané.

### 7. Comment intégrer sondages et prises de parole

Je proposerais trois curseurs indépendants :

1. **Programme officiel** : priorité revendiquée.
2. **Campagne observée** : fréquence et mise en avant dans un corpus documenté.
3. **Cohérence documentée** : relations avec déclarations et votes antérieurs.

L’utilisateur peut modifier leur pondération pour explorer, mais la formule doit rester visible.

Les sondages apparaissent plutôt dans un **bandeau candidat daté**, avec institut, terrain, échantillon et scénario testé. Évite d’agrandir par défaut toutes les propositions d’un candidat populaire : cela confondrait popularité et importance politique.

### 8. Le MVP que je lancerais

**Un thème, quelques candidats, quelques dizaines de propositions, toutes vérifiées.**

Livrables :

- une grille de codage publique ;
- un petit corpus versionné ;
- un nuage interactif et une liste ;
- une fiche détaillée par proposition ;
- une interface de validation ;
- un export ouvert des données.

**Socle technique raisonnable** : PostgreSQL pour les données et leur historique, stockage des documents sources, scripts Python d’ingestion, interface web avec une bibliothèque de visualisation interactive.

Le vrai test du MVP : **une autre personne peut-elle retrouver la source et comprendre — voire contester — chaque évaluation sans te demander d’explication ?**

C’est cette traçabilité, plus que la sophistication du graphique, qui fera la valeur du projet.


# Claude Sonnet

## 1. Divergence sauvage

Quelques pistes volontairement tordues, avant de choisir.

1. **Le Cimetière des promesses.** Chaque proposition est une pierre tombale. Plus elle est infaisable, plus elle est enfoncée dans le sol. Les promesses mises en avant sont des mausolées, les reléguées de simples croix en bois.
2. **Le Zoo des candidats.** Chaque candidat est un animal, et ses propositions sont des excréments classés par taille. Drôle, mais peu lisible.
3. **La Bourse de la Promesse.** Chaque proposition est une action cotée. Le cours dépend de la faisabilité, le volume de l'importance. Un krach survient quand le Conseil constitutionnel tousse.
4. **Le Système solaire programmatique.** Chaque candidat est une étoile dont la masse est son intention de vote. Les propositions sont des planètes en orbite. La distance au soleil mesure l'importance, la couleur le positionnement gauche/droite. Les planètes infaisables sont des *planètes gelées*, les coûteuses des *géantes gazeuses*.
5. **Le Buffet à volonté (la piste dérangeante).** Chaque proposition est un plat servi à une table. La largeur des ayants droit se lit à la taille de la table : tout le monde, ou seulement les riches, ou seulement les Français. Les convives exclus regardent à travers la vitre. Le gain ou le coût devient l'addition. C'est inconfortable, parce qu'on voit littéralement qui est exclu de quoi.

## 2. Proposition retenue : **« La Table des exclus »**

Je la garde parce que votre dimension « largeur des ayants droit », avec ses deux axes revenus et nationalité, est la plus originale de votre cahier des charges et celle que les visualisations classiques traitent mal.

Pour rester exploitable, le concept devient un **mode de vue parmi d'autres**. Le cœur reste un nuage de bulles configurable, et la « Table » est une vue alternative où chaque proposition est représentée par un disque divisé en deux demi-anneaux :
- **anneau revenus** : plein si universel, partiel s'il est réservé à une tranche ;
- **anneau nationalité** : plein si ouvert à tous, partiel s'il est réservé aux nationaux.

On voit donc d'un coup d'œil qui est invité et qui reste dehors.

---

## 3. Architecture exploitable

### Pipeline en 5 étapes
```
collecte → extraction/normalisation → notation → stockage → visualisation
 (scraper)     (LLM + schéma)         (LLM + règles)  (JSON/SQLite)   (web)
```

### Stack
- **Collecte et notation** : Python (httpx, BeautifulSoup, pdfplumber), LLM avec sortie JSON contrainte.
- **Stockage** : fichiers JSON/YAML versionnés dans Git, un par candidat. C'est le plus simple à mettre à jour et à relire en diff, et on peut générer un SQLite si besoin.
- **Visualisation** : site statique (Svelte ou JS vanilla avec D3.js ou Observable Plot), hébergé gratuitement sur GitHub Pages.
- **Mise à jour** : une commande `make update` et une GitHub Action planifiée.

### Arborescence
```
programmes2027/
├── data/
│   ├── candidats.yaml        # nom, parti, photo, % sondage (historisé)
│   ├── themes.yaml           # thèmes + pictos
│   ├── propositions/<candidat>.json
│   ├── interviews/<candidat>.json   # pondérations
│   └── seuils.yaml           # règles des emotes
├── pipeline/
│   ├── 1_collect.py
│   ├── 2_extract.py
│   ├── 3_score.py
│   └── rubrics/              # grilles de notation écrites
├── web/                      # visualisation
└── Makefile
```

### Schéma d'une proposition
```json
{
  "id": "lfi-sante-012",
  "candidat": "slug",
  "theme": "sante",
  "titre": "Court résumé normalisé",
  "texte_source": "citation exacte",
  "source_url": "...",
  "position_programme": 3,
  "scores": {
    "gauche_droite": {"valeur": -0.6, "confiance": 0.7, "justification": "..."},
    "importance": {"valeur": 0.8, "justification": "en une / page 4 / annexe"},
    "faisabilite": {
      "financement": 0.4,
      "constitutionnalite": 0.9,
      "tags": ["reforme_constitutionnelle", "financement_flou"]
    },
    "ayants_droit": {
      "global": 0.35,
      "revenus": 0.2,
      "nationalite": 1.0
    },
    "cout_gain": {"milliards_eur_an": -12.5, "fiabilite_chiffrage": "estime"}
  },
  "ponderation_interviews": [
    {"source": "France Inter 2026-09-12", "coef": 1.3, "note": "répétée 4 fois"}
  ],
  "valide_humain": false,
  "date_maj": "2026-11-03"
}
```

### Échelles à fixer
- **Gauche/droite** : -1 à +1, évalué sur la proposition seule et jugé selon une grille (rôle de l'État, redistribution, ordre et sécurité, immigration, libertés), pas selon l'étiquette du candidat.
- **Importance** : calculée par formule, pas à l'intuition : emplacement (une, première page, corps, annexe) × espace occupé × présence dans le résumé du candidat × coefficient interviews.
- **Faisabilité** : deux sous-scores (financement, constitutionnalité) plus des tags comme `inconstitutionnel_probable`, `besoin_europe` ou `sans_chiffrage`.
- **Ayants droit** : trois valeurs de 0 à 1 (global, revenus, nationalité), pour pouvoir afficher chacune séparément.
- **Coût/gain** : en milliards d'euros par an, avec une mention de fiabilité (chiffré par le candidat, estimé par nous, inconnu).

### Visualisation
- Menus déroulants pour choisir X, Y et la taille des bulles, parmi les 5 dimensions plus l'intention de vote.
- Chaque bulle porte le **visage du candidat** en bordure et le **picto du thème** au centre.
- **Emotes à seuils**, définies dans `seuils.yaml` pour pouvoir les modifier sans toucher au code :
  - 💀 infaisable (faisabilité < 0.2)
  - 💸 coûteux (> 20 Md€/an)
  - ⚖️ risque constitutionnel
  - 🎁 gain net
  - 🕳️ non chiffré
- **Filtres** par candidat, thème et tag.
- **Intention de vote** : option pour dimensionner ou pondérer les bulles par le pourcentage du candidat, avec un historique des sondages dans `candidats.yaml`.
- **Pondération interviews** : un curseur « poids des interviews » de 0 à 100 % qui recalcule l'importance en direct.

### Pour faciliter les mises à jour
1. Chaque proposition garde sa citation et son URL source, donc tout est vérifiable.
2. Le drapeau `valide_humain` permet de relire les notations du LLM avant publication.
3. Les grilles de notation sont versionnées, ce qui permet de re-noter en masse quand elles changent.
4. Un `make update` ne retraite que les programmes dont le contenu a changé (comparaison de hash).

### Points de vigilance
- **Neutralité** : la notation gauche/droite et la faisabilité sont contestables. Il faut publier les grilles, afficher la confiance et la justification de chaque note, et idéalement croiser deux passes de notation.
- **Droit et sources** : vérifier les conditions de réutilisation de programmes-2027.fr avant de scraper.
- **Sondages** : citer l'institut et la date, et utiliser une moyenne plutôt qu'un seul sondage.

---

## Prochaine étape

Je peux lancer la phase 1 : récupérer le contenu de programmes-2027.fr, voir sa structure et la liste réelle des candidats, puis produire le squelette du dépôt avec le schéma et un premier candidat de bout en bout pour valider les échelles de notation. Voulez-vous que je commence ainsi, ou préférez-vous d'abord ajuster le schéma ou les échelles ?



# Deepseek v4.1 flash

Je pars sur une divergence large puis je construis un prototype réellement exploitable (schéma de données normalisé, jeu de démonstration, et la visualisation interactive). Ça demande quelques minutes de travail machine.
J'ai poussé la divergence à fond, gardé une piste franchement malsaine, puis resserré sur une seule idée que j'ai rendue utilisable. Le prototype est prêt : schéma normalisé, 70 propositions de démonstration, la visualisation interactive, la grille de notation et le gabarit de saisie.

---

## 1. Phase de divergence sauvage (10 pistes, non filtrées)

1. **Le tapis roulant** : chaque proposition est un colis sur un convoyeur qui avance de gauche à droite ; sa position physique = son spectre, et les colis lourds (chers) font grincer le tapis.
2. **Le vivarium** : un aquarium où chaque proposition est une bulle qui monte, et la vitesse de remontée = faisabilité. Les bulles infaisables coulent et s'accumulent au fond, en tas visibles.
3. **La carte météo** : propositions comme systèmes nuageux, coût = précipitations, constitutionnalité = anticyclone.
4. **Le pentathlon** : chaque proposition est un athlète noté par 6 juges ; on voit les désaccords entre juges (variance inter-annotateurs).
5. **Le jeu de cartes à collectionner** : chaque proposition est une carte avec stats, rareté et un dos de carte zombie pour les promesses recyclées.
6. **L'échelle de Richter électorale** : amplitude = coût, profondeur = faisabilité, épicentre = thème.
7. **Le chantier de construction** : la proposition est un bâtiment ; le coût est le nombre d'étages, la constitutionnalité le permis de construire. Les infaisables restent en grue.
8. **La partition musicale** : chaque thème est une portée, hauteur = spectre, durée = importance. On *entend* un programme.
9. **Le cimetière** : les promesses 2017/2022 jamais appliquées sont des tombes qu'on peut déterrer — morbide et pourtant extrêmement parlant.
10. **(la plus dérangeante) Le collier de dents** : chaque candidat·e est un visage central ; ses propositions sont des dents plantées sur un fil, et la taille de la dent = ampleur des ayants droit. Plus la proposition est restrictive (réservée aux nationaux, aux riches), plus la dent est pointue et tournée vers l'intérieur — le visage se referme littéralement sur lui-même. On peut *voir* un programme xénophobe ou élitiste prendre la forme d'une mâchoire qui se referme.

---

## 2. La piste retenue : le **Vivarium Électoral**

Pourquoi elle : elle est la seule qui encode les 6 dimensions **sans jamais mentir sur l'incertitude**, elle rend la dimension « ayants droit » physiquement lisible (bulle qui se rétracte), et elle est techniquement réalisable en pur SVG/JS hors ligne. La piste du collier de dents était la plus forte en charge émotionnelle, mais elle confondait le score avec le jugement moral — je l'ai écartée pour ne pas transformer l'outil en machine à condamner. Le vivarium garde l'idée (la bulle se referme sur les ayants droit) sans le côté tribunal.

**Ce qui a été construit :**

- **3 sélecteurs d'axes** : tu choisis n'importe quelle dimension en X, en Y et en taille de bulle (spectre, importance, faisabilité financement, faisabilité constitutionnelle, ayants droit/revenus, ayants droit/nationalité, coût net en Md€), avec inversion d'axe et normalisation automatique. 2 dimensions → nuage de points ; 3 → bulles.
- **Bulles-trombines** : couleur par candidat, initiales dans la bulle, picto de thème. 14 thèmes normalisés (fiscalité, travail, retraites, immigration, écologie, sécurité, santé, éducation, institutions, Europe, défense, numérique, logement, social).
- **Emojis-seuils** posés sur les bulles, avec légende : 💀 faisabilité < 3 · 💸 coût > 20 Md€ · 🐘 constitutionnalité < 3 · 🧟 promesse zombie (déjà faite en 2017/2022, jamais appliquée) · 📦 mesure importée (testée ailleurs, résultat connu). Le statut « zombie » est le vrai bijou de l'outil : c'est souvent l'axe le plus révélateur politiquement, et il est invisible dans 99 % des comparateurs de programmes.
- **Interaction** : tooltip complet au survol, panneau de détail au clic (verbatim source, toutes les valeurs, statut, indice de confiance), filtres par candidat / thème / statut, mode « zombie seulement », recherche texte, compteur, réinitialisation. Animation de flottaison désactivable.

**Le pipeline en 4 étapes est documenté dans le README, avec la grille de barème explicite** — ce que veut dire 0, 5 et 10 pour chaque dimension. C'est la partie que la plupart des projets de ce genre bâclent : la notation « importance dans le programme » ou « faisabilité » est irrémédiablement subjective, donc le schéma prévoit un champ `confiance` (0–1) par proposition, et le README recommande un double-codage avec calcul d'écart inter-annotateurs avant publication.

**Un point important sur les données** : le jeu livré est un jeu de **démonstration**, avec des candidat·e·s fictifs archétypaux (social-libéral, souverainiste, écolo-radical, etc.) et des valeurs cohérentes entre elles — une proposition très coûteuse y a bien une faisabilité financement basse. Je n'ai délibérément attribué **aucune position à aucune personnalité réelle** : inventer des positions pour de vraies personnes serait de la désinformation pure. Tu remplis le gabarit CSV fourni, tu remplaces les candidats fictifs par les vrais, et tu rebranches les données.

**Limite à connaître** : la page embarque les données en dur pour fonctionner en double-clic depuis ton disque, donc modifier le JSON seul ne met pas la page à jour — il faut régénérer ou brancher le CSV. C'est le prix de l'autonomie totale sans serveur.

Dis-moi si tu veux que je passe à l'étape suivante : importateur CSV → JSON automatique, ou le mode « collier de dents » en vue alternative pour comparer les programmes sur la seule dimension des ayants droit.