# Comparateur et « Et moi ? » : pistes propres à l'Atlas (2026-11-23)

Point de départ : France-Vote (et les comparateurs du même genre) posent 40 questions fixes et y placent les candidats par une lecture éditoriale. L'Atlas a autre chose : plus de 12 000 propositions citées mot pour mot, chacune lue à l'aveugle par deux modèles (sens sur les axes, ampleur, levier, financement, obstacle juridique, ménages touchés, confiance par question), une importance dans le programme, un index sémantique (`donnees/index_recherche_2027.*`), un mode noms masqués et des liens vers les votes. Les pistes ci-dessous partent de ce matériau. Rien n'est décidé.

## Comparateur

1. **Les sujets viennent des programmes, pas d'une liste de questions.** Pour deux candidats, chaque proposition de A est rapprochée de la plus proche de B par le sens (index sémantique, calcul fait une fois à l'export, aucun coût à l'affichage). On obtient quatre colonnes, chacune avec les citations :
   - même sujet, même sens (les réponses aux axes vont dans le même sens) ;
   - même sujet, sens opposé ;
   - seul A en parle ;
   - seul B en parle.
   L'index trouve un sujet, pas une position : le sens vient des réponses du questionnaire, jamais de l'embedding. Le seuil de proximité se règle sur un échantillon relu à la main.
2. **Comparer la manière, pas seulement la direction.** Une « signature » par candidat : part des propositions qui interdisent, incitent ou investissent ; ampleur du changement ; part avec un obstacle juridique ; financement désigné, évoqué ou absent ; ménages touchés. Exemple de lecture : deux candidats proches sur l'axe économique, l'un par la loi, l'autre par la dépense. Aucun comparateur à questions fixes ne peut le montrer.
3. **Recouvrement plutôt qu'écart des centres.** Sur un thème, part des propositions de A qui tombent dans la zone des quartiles de B. Deux centres proches peuvent cacher des programmes qui ne se recouvrent pas, et l'inverse.
4. **Duel à l'aveugle.** Deux programmes présentés comme A et B sur un thème, propositions appariées ; le lecteur se fait une idée, puis lève les noms. Prolonge le mode noms masqués.
5. **Ce qu'il propose, ce qu'il a voté.** Pour les parlementaires, chaque proposition liée à un vote (liens posés à la main, phase 2 des votes) est mise à côté du vote.

Le comparateur peut s'appuyer sur les paramètres d'adresse (`comparer=a,b`) : un duel se partage par son lien.

## « Et moi ? »

1. **Juger de vraies propositions, à l'aveugle.** Au lieu de questions abstraites, le lecteur lit des propositions réelles (citation, noms masqués) et répond : d'accord, pas d'accord, sans avis (et « important pour moi »). Sa position se calcule avec les formules publiques, à partir des réponses du questionnaire des propositions approuvées et rejetées. Il apparaît comme sa propre étoile dans la constellation, puis les noms se lèvent : « vous avez approuvé 14 propositions : 5 de X, 4 de Y… ».
   - Tirage : stratifié par candidat (chacun autant de propositions, quelle que soit la longueur de son programme), par axe et par thème, parmi les propositions importantes où les deux lecteurs sont d'accord. Graine publiée, méthode décrite dans Coulisses.
   - Version adaptative : la proposition suivante est choisie là où la position du lecteur est la plus incertaine, ou là où les candidats divergent le plus. Une quinzaine de réponses peuvent suffire.
   - Le résultat ne désigne pas « votre candidat » : il montre les programmes dont on approuve le plus de propositions, axe par axe et thème par thème, avec les citations.
2. **Placer son étoile soi-même.** Mode rapide : le lecteur pose son point sur les deux axes affichés, thème par thème, et voit les étoiles proches.
3. **Ses priorités.** Le lecteur pèse les thèmes qui comptent pour lui ; les centres des candidats sont recalculés avec ces poids.

Communs aux trois : tout se calcule dans le navigateur, rien n'est envoyé ni gardé côté serveur ; le résultat peut s'écrire dans l'adresse pour être partagé ; mention « ni un sondage au sens de la loi du 19 juillet 1977, ni une consigne de vote ».

## Ordre proposé

Pour « Et moi ? », la piste 1, d'abord sans le tirage adaptatif. Pour le comparateur, les pistes 1 et 2 : la première demande un calcul à l'export (l'index existe ; les mesures nouvelles demandent leur vecteur, par l'API plafonnée ou le modèle local), la seconde ne demande que l'export actuel.
