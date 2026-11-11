# Suivi : contexte, lexique et importance (2026-11-07)

> Sous-fichier de [SUIVI_PROJET.md](../../SUIVI_PROJET.md) (sommaire et état courant). Précédent : [05](05_2026-11-06_07_rangement_et_integration.md) · Suivant : [07](07_2026-11-07_08_comparaison_modeles.md)

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

## Poids des thèmes dans le centre d'un candidat : importance moyenne (2026-11-07, 0 appel)

- Décision de l'utilisateur : le contenu compte plus que la quantité. Avec « Pondérer par l'importance » (par défaut), chaque proposition pèse selon son importance dans son thème (importance/50), et chaque thème pèse selon **l'importance moyenne** de ses propositions, pas selon leur nombre. Décoché, tout compte autant.
- Effet sur l'idéologie (thèmes égaux → importance moyenne, propositions pondérées dans les deux cas) :
  - Dupont-Aignan +18 → +25 ;
  - Le Pen +32 → +35 ;
  - Zemmour +59 → +61 ;
  - Roussel −42 → −40 ;
  - les autres bougent de 0 à 1 point.
- Effet sur l'axe culturel :
  - Dupont-Aignan +44 → +55 ;
  - Arthaud −68 → −82 (position fragile) ;
  - Mélenchon −49 → −46 ;
  - Zemmour +76 → +78.
