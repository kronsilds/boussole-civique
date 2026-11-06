Je prépare l'architecture complète de votre projet, inspecte la source `programmes-2027.fr` et génère un prototype fonctionnel de pipeline et de visualisation interactive.
Je nettoie rapidement l'espace de fichiers générés avant de vous présenter la conception complète et les livrables.
Voici une proposition d’architecture complète pour ce projet, accompagnée de **trois livrables directement exploitables** (une application interactive autonome en HTML/JS, le schéma de données JSON normalisé et le script Python d’ingestion et de scoring).

Conformément à votre approche créative, commençons par ouvrir le champ des possibles avant d’ancrer la solution technique.

---

### 1. Phase de divergence sauvage (angles de design & concepts)

Si l’on refuse le traditionnel « tableau comparatif des programmes » que la presse publie à chaque élection, voici 4 pistes radicales pour penser votre outil :

1. **Le Crash-Test Gravitationnel (Physique des promesses)** : Les propositions sont des corps célestes. Plus une mesure coûte cher et manque de faisabilité constitutionnelle, plus elle subit une gravité négative qui la tire vers le « fond de l'écran » (le trou noir des promesses oubliées). Seules les mesures financées et votées à l'Assemblée flottent en apesanteur.
2. **L'IRM d'Hypocrisie Parlementaire (Piste dérangeante)** : Au lieu d'afficher ce que le candidat promet, le graphique affiche par défaut **l'écart cognitif** entre la promesse écrite et les votes réels de son groupe à l'Assemblée nationale. Plus la divergence est grande, plus la bulle du candidat se déforme, clignote ou « transpire » visuellement jusqu'à devenir fantomatique (opacité indexée sur la sincérité législative).
3. **Le Tamagotchi Budgétaire (Piste absurde)** : L'utilisateur sélectionne son profil (revenu, nationalité) et adopte un avatar citoyen. En cliquant sur les bulles de propositions de différents candidats, l'avatar grossit, s'endette, perd des services publics ou gagne du pouvoir d'achat, pendant qu'un compteur d'alerte du Conseil Constitutionnel hurle des sirènes dès qu'on dépasse 3 mesures inconstitutionnelles.
4. **Le « Scanner d’Anomalies & d'Angles Morts » (L'Observatoire Balistique)** : On dissocie totalement le candidat de son étiquette. Les propositions sont projetées sur une matrice où l'on traque les **transfuges idéologiques** (ex. : une mesure économiquement très à gauche portée par un candidat de droite, ou inversement) et où l'on **recalcule en temps réel la gravité politique** d'une mesure en croisant sa place dans le PDF officiel, son temps d'antenne en interview et les votes réels au Parlement.

---

### 2. La proposition retenue et rendue exploitable : L'Observatoire Balistique & le « Score de Sincérité Dynamique »

Nous avons retenu et développé la **4e piste enrichie de la 2e (l'IRM parlementaire)**. 

Pourquoi ? Parce que le vrai problème des comparateurs politiques classiques est qu'ils prennent le programme papier au pied de la lettre. Une proposition mise en page 48 d'un PDF pour rassurer un électorat, jamais mentionnée en interview et contredite par les votes des députés à l'Assemblée n'a pas la même « réalité politique » qu'une mesure phare martelée au 20h.

#### Les 3 innovations clés intégrées à votre prototype :

1. **La formule d'Importance Pondérée en temps réel (Curseurs dynamiques)** :
   Au lieu d'une note d'importance fixe, chaque proposition possède 3 sous-scores (0 à 100) que l'utilisateur peut pondérer en direct avec des curseurs :
   $$\text{Importance Réelle} = \frac{(w_{\text{prog}} \times S_{\text{programme}}) + (w_{\text{media}} \times S_{\text{interviews}}) + (w_{\text{an}} \times S_{\text{votes AN}})}{w_{\text{prog}} + w_{\text{media}} + w_{\text{an}}}$$
   *Vous voulez voir uniquement ce que les candidats défendent vraiment aux micros et dans l'hémicycle ? Mettez le curseur « Programme écrit » à 0 % et montez « Interviews » et « Votes AN » à 100 % : le nuage de points se réorganise instantanément.*

2. **Le double axe d'Ayants-droit (Matrice d'inclusion)** :
   Chaque mesure est scorée séparément sur :
   - **Ciblage Revenus / Patrimoine** (`0` = ultra-ciblé ménages modestes ou très hauts patrimoines $\rightarrow$ `100` = universel sans condition de ressources).
   - **Critère de Nationalité** (`0` = strictement réservé aux nationaux / condition d'ancienneté $\rightarrow$ `100` = universel tous résidents).

3. **Le détecteur d'anomalies et d'émotes de seuilsautomatiques** :
   Dès qu'une mesure franchit certains seuils dans la base de données, l'interface lui attache des badges visuels immédiats :
   - 🚨 **Alerte Constitutionnelle / UE** (`faisabilite < 35` ou tag `inconstitutionnel_potentiel` / `contraire_droit_ue`)
   - 💸 **Gouffre budgétaire** (`cout_gain_milliards <= -15 Md€/an`)
   - 💰 **Jackpot budgétaire** (`cout_gain_milliards >= +15 Md€/an`)
   - 👻 **Angle mort médiatique** (`score_programme >= 70` mais `score_interview <= 30` : écrit dans le programme mais jamais assumé en interview)
   - ⚡ **Grand écart Parlement** (`|score_programme - score_votes_an| >= 45` : le candidat promet l'inverse de ce que son camp vote à l'Assemblée)
   - 🔀 **Transfuge idéologique** (mesure de gauche portée par un candidat de droite, ou inversement).

---

### 3. Ce que nous avons découvert sur votre source (`programmes-2027.fr`)

En inspectant techniquement le site `https://programmes-2027.fr/`, une excellente nouvelle est apparue pour la maintenabilité de votre projet :
- Le site n'enferme pas ses données dans du HTML complexe : il charge directement un fichier statique structuré accessible publiquement sur **`https://programmes-2027.fr/data-v2.json`**.
- Ce fichier contient déjà l'arbre des candidats (`candidates`), les catégories thématiques et les propositions (`measures`) avec leurs sources et URLs.
- **Implication pour votre pipeline** : Vous n'avez même pas besoin d'un scraper fragile qui casse à chaque changement de design. Votre script Python télécharge directement `data-v2.json`, extrait les nouvelles mesures par simple diff d'identifiant (`id`), et ne passe au crible du LLM que les **nouvelles** propositions ajoutées !

---

### 4. Architecture du Système & Mise à jour continue ("Zero-Friction")

Pour que le projet soit ultra-facile à mettre à jour jusqu'en avril 2027 :

```
[programmes-2027.fr/data-v2.json]  +  [Nouveaux PDF / Interviews / Datan.fr (Votes AN)]
                        │
                        ▼
         ┌──────────────────────────────┐
         │   pipeline_scoring_2027.py   │  (Script Python fourni)
         └──────────────────────────────┘
           1. Récupère data-v2.json sans casser les notes existantes
           2. Découpe et normalise par thème (Économie, Régalien, Écologie...)
           3. Pré-évalue les dimensions via LLM (Structured Output JSON)
                        │
                        ▼
         ┌──────────────────────────────┐
         │ schema_et_donnees_exemple.json│  (Base de données JSON plate / Git)
         └──────────────────────────────┘
           • Modifiable à la main ou via l'éditeur intégré au dashboard
           • Contient un bloc séparé pour les % d'intentions de vote (sondages)
                        │
                        ▼
         ┌──────────────────────────────┐
         │visualisation_programmes_2027 │  (Application Web autonome fournie)
         └──────────────────────────────┘
```

#### Comment enrichir automatiquement les votes à l'Assemblée et les interviews ?
- **Votes à l'Assemblée (`score_votes_an`)** : Vous pouvez croiser avec l'API/OpenData de **Datan.fr** ou **NosDéputés.fr** qui synthétisent les votes par groupe parlementaire sur les textes clés (budget, immigration, retraites, écologie).
- **Sondages (`intentions_vote_pct`)** : Stockés uniquement dans l'objet `candidats` en haut du fichier JSON. Mettre à jour un sondage IFOP/Ipsos prend **15 secondes** (une seule valeur par candidat à changer) et redimensionne toutes les bulles de propositions si vous choisissez « Intention de vote » comme taille de bulle (axe Z).

---

### 5. Présentation des 3 fichiers livrés

1. **`visualisation_programmes_2027.html` (Le Dashboard interactif complet)**
   - **Ouvrez-le directement dans n'importe quel navigateur** (aucun serveur requis).
   - **Sélecteurs d'axes X, Y et Taille de bulle (Z)** : Croisez librement *Spectre Gauche/Droite*, *Faisabilité*, *Coût/Gain (Md€)*, *Importance pondérée*, *Largeur des ayants-droit (Revenus ou Nationalité)* et *% d'Intentions de vote*.
   - **Double mode d'affichage des bulles** : Basculez entre la **trombine stylisée du candidat + picto du thème + émote de seuil**, le mode Avatar seul ou Thème seul.
   - **Simulateur de pondération en direct** : Jouez avec les 3 curseurs (*Programme écrit*, *Interviews*, *Votes Assemblée*) pour voir les bulles monter ou descendre.
   - **Radar d'anomalies** : Un bouton filtre en un clic les mesures qui contiennent un loup (inconstitutionnelles, gouffres financiers, angles morts médiatiques ou transfuges idéologiques).
   - **Éditeur JSON embarqué** : Cliquez sur n'importe quelle bulle pour inspecter ses sources, ou modifiez un score / un sondage directement dans l'interface pour voir le graphique se mettre à jour instantanément, puis exportez votre JSON mis à jour.
   *(Note : les 22 propositions et scores pré-chargés dans la démo sont des données illustratives de test conçues pour démontrer tous les cas de figure extrêmes).*

2. **`schema_et_donnees_exemple.json` (Le contrat de données & JSON Schema)**
   - Contient à la fois le **JSON Schema strict (`$defs`)** pour valider vos données et le jeu de données normalisé.
   - Sépare proprement les métadonnées des `candidats` (dont `intentions_vote_pct`), le référentiel des `themes`, les règles de `seuils_emotes` et la liste des `propositions`.

3. **`pipeline_scoring_2027.py` (Le moteur d'ingestion et d'évaluation)**
   - Contient l'adaptateur `import_programmes_2027_json` calibré sur la structure réelle de `programmes-2027.fr/data-v2.json`.
   - Intègre le **Prompt Système d'évaluation multi-dimensionnelle** prêt à être branché sur une API LLM (OpenAI / Anthropic / Mistral) pour noter de façon reproductible une nouvelle mesure sur vos 7 dimensions tout en séparant faits vérifiés et estimations.
