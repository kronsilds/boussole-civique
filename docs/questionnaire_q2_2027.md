# Questionnaire q2 : mise au point, centres des candidats, doublons

> **État au 2026-11-22 : le questionnaire q2 est en production depuis la renotation complète du 2026-11-16** (base en `meta.questionnaire = "q2"`, lecture par drex-max et pplx-decider, arbitrage des litiges par gpt-6.1-terra : [lecture_q2_2027.py](../lecture_q2_2027.py), [arbitrage_q2_2027.py](../arbitrage_q2_2027.py)). La suite de cette note est le journal de sa mise au point, écrit pendant l'essai : les mentions « à l'essai » ou « production en q1 » y décrivent la situation d'alors. Méthode publiée et à jour : page Coulisses de la constellation.

Date : 2026-11-10. Suite de [review_notation_2027.md](review_notation_2027.md). À cette date, la production restait en q1 : rien de ce qui suit n'était appliqué à la base ni à l'export, sauf le poids des thèmes dans le centre d'un candidat (§ 1, page de la constellation).

Code : [questionnaire_q2_2027.py](../questionnaire_q2_2027.py) (questions et formules), [essai_q2_2027.py](../essai_q2_2027.py) (formats Terra et modèles de décision, essai comparatif), `tests/test_q2_2027.py`.

## 1. Centre d'un candidat : importance d'abord, nombre ensuite

Poids d'un thème sur un axe = importance moyenne de ses propositions × racine du nombre de celles qui sont notées sur cet axe. L'importance reste celle du programme (place dans le document, reprises, propositions proches) ; un thème quatre fois plus fourni pèse deux fois plus. Modifié dans `web/constellation_2027.html` (`themeWeight`).

Simulation sur l'export (56 couples candidat × axe d'au moins 10 mesures) :

| Poids du thème | Poids des étoiles à 1 ou 2 mesures | Déplacement moyen du centre si on retire une mesure | Part du premier thème |
|---|---|---|---|
| Avant : importance moyenne seule | 34 % | 4,2 points (16 au plus) | 14 % |
| Importance × min(1, n/5) | 15 % | 2,2 (9 au plus) | 20 % |
| **Importance × √n (retenu)** | 17 % | 2,1 (12 au plus) | 25 % |
| Importance × log2(1 + n) | 18 % | 2,5 (12 au plus) | 22 % |
| Importance × √N, N = toutes les mesures du thème | 30 % | 4,0 (19 au plus) | 19 % |
| Par mesure (le nombre seul) | 8 % | 0,7 (8 au plus) | 39 % |

- Compter toutes les mesures du thème (N), et non celles qui sont notées sur l'axe, ne corrige rien : un thème de quarante mesures dont une seule parle d'immigration pèserait quarante sur l'immigration.
- Effet : Philippe, société +26 → +58 ; Dupont-Aignan, société +35 → +49 ; Tondelier, société −30 → −20 ; Retailleau, écologie −39 → −32. Sept centres sur 56 bougent de plus de 10 points.
- Non tranché : l'importance contient 20 points de précision sur 100 (une mesure chiffrée pèse 1,75 fois une orientation générale), ce qui n'est ni la place ni la reprise dans le programme.

## 2. Les doublons améliorent-ils la notation ? Non

Mesuré sur les 9 917 mesures lues deux fois par Terra (q1 sans le passage, puis avec).

- **Pas de gain de fiabilité.** Chaque signal de flou est retrouvé à l'identique dans 92,0 à 93,3 % des cas (kappa 0,82 à 0,85) ; le composite des quatre aussi (92,8 %, kappa 0,84). Un modèle de texte écrit toutes ses réponses d'un seul jet : ses erreurs vont ensemble, les moyenner n'apporte rien.
- **Pas de détection d'erreur.** Quand les quatre signaux se contredisent, une réponse de sens change à la relecture dans 43,5 % des cas, contre 41,5 % quand ils concordent. La confiance déclarée prédit bien mieux : 58 % de changements sous 0,7, 20 % au-dessus de 0,85.
- **Revenus.** `revenus_sens` et les cinq classes de revenu ne s'opposent que 30 fois sur 2 296, et ce sont alors deux questions différentes : l'une regarde les bénéficiaires, l'autre aussi ceux qui paient (prix planchers agricoles). q2 pose la question une fois, en disant de compter ce que chaque classe reçoit et ce qu'elle paie.
- **Ce qui sert** : une seconde lecture indépendante. Un autre modèle, ou un modèle de décision, qui répond à chaque question sans voir les autres.

## 3. Ce qui change de q1 à q2

| | q1 | q2 |
|---|---|---|
| Applicabilité d'un axe | `applies_if`, réponse null, « indéterminé » | 11 conditions oui/non, décidées avant les questions du bloc |
| Flou | 5 questions (déclaration, orientation générale, instrument non identifiable, faisabilité non évaluable, coût indéterminable) | un seul jugement, la condition `a_dispositif` (« la mesure nomme-t-elle l'acte que l'État accomplirait ? ») ; levier, instrument, coût et financement seulement s'il y a un dispositif ; sans dispositif, le levier est une déclaration |
| Précision | question à 3 options | calculée : chiffrée si `chiffree` (oui/non), sinon précise s'il y a un dispositif, sinon orientation générale |
| Économie | action publique, redistribution | trois aspects jugés séparément : budget public (`eco_depense`), règles et propriété (`eco_marche`), qui gagne et qui paie (`eco_transfert`) |
| Ampleur | `changement` (62 % de « réforme significative »), `degre_rupture` pour société et immigration | `degre` (ajustement, notable, rupture) pour toutes les mesures |
| Faisabilité | question à 6 options | calculée : texte juridique nécessaire, coût, financement (identique à la réponse q1 dans 59 % des cas, à un niveau près dans 91 % ; deux modèles ne s'accordent qu'à 56 % sur la question q1) |
| Revenus | `revenus_sens` et 5 classes | 5 classes |
| Société | autorité, libertés, finalité à 4 options ; une finalité « droits et égalité » bascule la note du côté des libertés | autorité, libertés, `soc_egalite` (oui/non) : quand la mesure protège contre une discrimination, la sanction n'est pas comptée comme de l'ordre et le sens vient de la seule question sur les libertés ; la probité passe aux institutions |
| Retirées | | `public_vise` (jamais utilisée ni exportée) |
| Ajoutées | | `financement`, `chiffree`, `inst_pouvoir`, `int_alliances`, `def_effort` |

Le tableau décrit la seconde rédaction (§ 6). La première, celle de l'essai du § 5, posait encore `levier` et `precision` à toutes les mesures et jugeait l'économie en deux questions (`eco_etat`, `eco_distrib`).

Trois axes de plus : **institutions** (pouvoir partagé ↔ concentré), **alliances** (engagement dans les alliances ↔ non-alignement), **défense** (moins ↔ plus de moyens militaires). L'accès aux droits selon le statut alimente l'axe immigration quand la mesure ne touche pas à l'entrée ni au séjour.

**Une seule règle de calcul** : note = 100 × sens × force × ampleur.

- sens : position de l'option sur son échelle, les options étant équidistantes de −1 à +1 ; économie = 0,5 × budget public + 0,5 × règles et propriété + 0,75 × qui gagne et qui paie, borné à ±1, et non notée si les trois réponses sont au milieu (première rédaction : 0,5 × action publique + 0,75 × redistribution ; q1 : 0,75 et 0,5) ; société = 0,8 × autorité + 0,8 × libertés (q1 : 0,6 et 0,6) ;
- force : celle du levier, au moins 0,7 pour un changement notable et 1 pour une rupture ; une déclaration vaut 0,15, 0,5 ou 0,85 selon le degré, jamais 1 ;
- ampleur : 0,55 + 0,45 × degré (0,2, 0,6 ou 1), la portée comptant pour moitié en économie et en écologie seulement.

Conventions à publier avec la méthode : options équidistantes sur chaque échelle, condition remplie à partir d'une probabilité de 0,5, formule ci-dessus. Ce sont des choix, pas des résultats.

Simulation des formules de la première rédaction sur les réponses q1 de la base (indicative : `degre` est déduit de `changement` quand `degre_rupture` manque ; elle ne peut pas être refaite pour les trois questions d'économie, que q1 ne posait pas) :

| Axe | Part des notes à ±90 et plus, q1 → q2 | Maximum q1 → q2 | Corrélation q1 / q2 |
|---|---|---|---|
| Économie | 0,4 % → 1,8 % | 100 → 100 | 0,91 |
| Société | 7,2 % → 6,2 % | 100 → 100 | 0,98 |
| Souveraineté | 0 % → 13,8 % | 85 → 100 | 0,95 |
| Immigration | 22,3 % → 13,5 % | 100 → 100 | 0,98 |
| Écologie | 0 % → 4,4 % | 85 → 100 | 0,92 |

En économie, 641 mesures changent de signe : les 768 « plus d'action publique au profit des entreprises » passent de −12,5 à +12,4 en moyenne, les 75 « moins d'action publique au profit des modestes » (défiscalisation des heures supplémentaires, crédit d'impôt des foyers modestes) de +13,6 à −13,3. L'ordre des candidats ne change pas, à trois candidats de gauche près, séparés d'un point.

## 4. Rédaction des questions

Règles tirées de la documentation des modèles de décision (TypeSafe, OpenRouter) et des erreurs relevées en q1 :

1. **Une question, un jugement rapide et vérifiable.** Ce qui dépend de plusieurs facteurs est découpé, et la combinaison se fait dans la formule.
2. **La question est complète en elle-même.** Un modèle de décision répond à chaque question sans voir les autres ni une consigne générale : chaque question dit ce qu'elle juge (`title`, `description`, `passage`).
3. **Les définitions sont dans les options**, avec des exemples concrets, pas dans la consigne.
4. **Pas d'option « autre », « indéterminé », « non identifiable ».** Elles prennent de la probabilité aux vraies options. Une question oui/non placée avant dit si le bloc s'applique.
5. **Le « non » d'une condition nomme les cas voisins** et l'axe dont ils relèvent (« sur l'entrée et le séjour des étrangers », « le seul fait qu'elle coûte de l'argent ne suffit pas », « désigner les bénéficiaires par « les Français » sans exclure personne ne suffit pas »).
6. **Les échelles vont d'un pôle à l'autre**, avec des formulations symétriques et un milieu réservé aux effets qui se compensent.
7. **Deux familles** : ce que le texte prévoit réellement (levier, portée, précision, instrument, coût, financement, revenus) et ce que la mesure vise, même seulement annoncé (degré, questions d'axe).

Formats, à partir des mêmes textes :

- **Terra** : consigne, barème JSON, lots de 10 ; il répond d'abord aux 11 conditions (true/false), puis aux 24 questions (null si la condition est fausse), avec une confiance par question et une note d'audit ;
- **drex-max et pplx-decider-v1.2** : une mesure par appel, trois appels de 16 questions au plus ; condition = `noul`, échelle = `score`, choix = `choice` ; la condition est fausse sous 0,5 ; les probabilités brutes sont gardées (le seuil se change sans repayer).

## 5. Essai sur 170 mesures (0,94 $ sur un plafond de 1,50 $)

**Protocole.** Les 130 mesures de l'échantillon figé des comparaisons, plus 40 mesures sans aucun axe en q1 tirées dans les thèmes institutions et international (`runs/echantillon_q2_2027.json`). Mêmes éléments pour tous : proposition, passage, lexique, à l'aveugle. Un premier tour avec les deux modèles de décision (0,13 $) a servi à corriger cinq questions (ménages, institutions, redistribution, action publique, portée) ; le tour final a relu les 170 mesures avec les trois modèles. Commande : `python .\essai_q2_2027.py --repetitions 2 --max-cost X`. Rapport : `runs/essai_q2_2027.{json,md}`.

| | Terra low | drex-max | pplx-decider-v1.2 |
|---|---|---|---|
| Mesures lues | 170 | 170 | 168 |
| Coût par mesure | 0,0036 $ | 0,0006 $ | 0,0002 $ |
| Même réponse à la relecture | non mesuré | 48 mesures sur 49 | 8 sur 8 |
| Note d'audit | oui | non | non |
| Seul contre les deux autres (1 848 réponses de sens) | 74 | 32 | 30 |

Les trois modèles donnent la même réponse à 1 700 questions de sens sur 1 848 (92 %) ; ils sont d'accord sur tout le sens d'une mesure 79 fois sur 168.

**Terra et drex-max s'accordent mieux qu'en q1** (mêmes 130 mesures) :

| | q1 | q2 |
|---|---|---|
| Accord complet sur le sens | 46 sur 130 | 67 sur 130 |
| Groupe représentatif | 14 sur 30 | 22 sur 30 |
| Réponses de sens différentes | 168 sur 1 170 (14 %) | 104 sur 1 430 (7 %) |
| Désaccords d'applicabilité | 114 (95 d'un côté, 19 de l'autre) | 71 (33 et 38) |
| « Indéterminé » d'un seul côté | 22 | 0 (la réponse n'existe plus) |
| Directions opposées | 4 | 8, toutes avec une confiance d'au plus 0,57 chez l'un des deux |

- Les deux modèles de décision s'accordent entre eux sur 115 mesures sur 168 ; avec Terra, 97 sur 170 (drex-max) et 90 sur 168 (pplx-decider).
- Conditions : accord Terra / drex-max de 86 % (`a_dispositif`) à 99 % (`a_immigration`) ; sur l'accès aux droits, 167 sur 170, et plus aucune mesure « pour tous les Français » lue comme une préférence nationale.
- Quand deux modèles notent le même axe, ils donnent presque toujours le même sens : action publique 56 sur 63, société 14 ou 15 sur 16, souveraineté 21 sur 23, institutions 15 sur 15, alliances 3 sur 3, défense 8 sur 9.
- La confiance prédit l'accord : celle de Terra (132 sur 140 au-dessus de 0,8, 12 sur 27 entre 0,4 et 0,6) comme celle de drex-max (105 sur 109 et 26 sur 46 sous 0,4).

**Nouveaux axes.** Sur les 40 mesures qui n'avaient aucun axe, 20 en reçoivent un avec Terra, 23 avec drex-max. J'ai relu les 38 mesures que Terra ou drex-max placent sur un nouvel axe : 33 réponses acceptables pour Terra, 31 pour drex-max, aucune direction inversée. Les erreurs sont des axes ouverts à tort : une règle inscrite dans la Constitution ou soumise à référendum prise pour une question de pouvoir (« Interdiction constitutionnelle du confinement »), une déréglementation lue comme un partage du pouvoir (« Retour à une liberté d'actions plutôt qu'aux autorisations », les trois modèles), une mesure industrielle comptée comme effort de défense (« Protection des brevets de défense »). L'axe alliances ne reçoit que 3 à 6 mesures sur 170 : la reconnaissance de la Palestine, l'aide au développement ou les sanctions hors alliances n'y entrent pas, par construction.

**Ce qui reste faible.**

- **Classes de revenu** : 8 accords sur 18 entre Terra et drex-max. Terra répond « gagne » pour toutes les classes dès qu'une mesure peut profiter à un ménage de chaque classe (bourses au mérite) ; les modèles de décision répondent « pas concernée ». La question doit dire si l'on juge la classe dans son ensemble.
- **Redistribution** : 45 accords sur 63 (Terra / drex-max), contre 56 sur 69 entre les deux modèles de décision.
- **Questions de moyen** : levier 73 %, portée 68 %, instrument 76 %, coût 72 % d'accord entre Terra et drex-max ; comparable à q1, non arbitré.
- **Stabilité de pplx-decider** : 8 relectures seulement, la limite de débit de Perplexity ayant coupé les appels enchaînés (trois passes pour lire 168 mesures). drex-max a rendu des 429 « Model busy » passagers. Un passage sur tout le corpus demanderait des pauses et des reprises.
- **Limites de l'essai** : cinq questions ont été corrigées sur le même échantillon avant le tour final ; je suis le seul arbitre des nouveaux axes ; l'accord entre modèles n'est pas une mesure de justesse.

## 6. Seconde rédaction : corrections et audit (1,29 $ sur un plafond de 1,50 $)

Les faiblesses du § 5 ont été reprises une à une, en tenant compte d'un audit externe des questions. Les chiffres du § 5 décrivent la première rédaction ; ceux-ci la seconde (`METHODE = "essai-q2-v2"`).

**Ce qui a changé.**

| Faiblesse | Cause trouvée | Correction |
|---|---|---|
| Classes de revenu | la question ne disait pas qui juger dans la classe | « les ménages de cette classe que la mesure touche directement », repères de montant (environ 100 € par mois), condition `a_menages` réécrite |
| Redistribution | la consigne réservait le milieu aux effets qui se compensent ; une seule question mêlait budget, règles et transferts | trois aspects jugés à part (`eco_depense`, `eco_marche`, `eco_transfert`), le milieu y est une réponse normale |
| Levier, précision | trois questions répétaient le même jugement (y a-t-il un dispositif ?) | un seul jugement `a_dispositif` ; sans dispositif, levier = déclaration et précision = orientation générale, calculés ; `chiffree` oui/non |
| Instrument, coût | pas de règle de départage ; effets indirects et montants inconnus | « retiens le plus difficile à obtenir » ; repères par niveau, effets directs seulement |
| Axe alliances | condition trop étroite, échantillon sans mesures d'alliance | condition élargie (liens militaires ou stratégiques), groupe de 15 mesures tirées par mots-clés |
| Limites de l'essai | questions corrigées sur l'échantillon qui les juge ; un seul arbitre | 80 mesures neuves jamais vues pendant la mise au point ; 24 étalons écrits à la main (`donnees/etalons_q2_2027.json`, 109 réponses attendues, **à valider par une personne**) |
| Stabilité de pplx-decider | 429 de Perplexity | pause d'une seconde et reprises (10, 30, 60 s) : 274 mesures lues deux fois sans échec |

**Audit externe : ce qui est repris, ce qui ne l'est pas.** Les fichiers livrés par l'audit (`*_v2.py`, `regression_v2*`) ne sont pas adoptés : `essai_q2_2027_v2` plante sur les modèles de décision (`KeyError 'eco_etat'`, huit questions jamais posées) et ses huit témoins sont fictifs.

| Proposition de l'audit | Décision | Raison |
|---|---|---|
| Scinder `eco_distrib` (transfert, pouvoir) et `eco_etat` (dépense, marché) | repris en trois questions | « marché » et « pouvoir » se recouvrent (règles, propriété, pouvoir des salariés) |
| Scinder `sov_niveau` en Europe et alliances | écarté | l'axe alliances (`int_alliances`) existe déjà ; le doubler sous `a_sov` compterait deux fois |
| Fin de la bascule automatique vers les libertés | repris | une protection contre une discrimination sans effet sur les libertés n'est plus notée sur l'axe société (modifie une décision antérieure du projet, à l'essai seulement) |
| Remettre `soc_finalite` et `degre_rupture` | écarté | doublons de `soc_egalite` et de `degre` |
| Revenus : « ne déduis pas d'effet non écrit » | écarté | une hausse du SMIC n'écrit pas qui gagne ; repris : pouvoir d'achat, gains et pertes qu'on ne peut pas départager |
| Exemples symétriques pour le degré | repris | |
| Items témoins | repris, avec de vraies mesures du corpus | |
| Publier les conventions | repris | docstring du questionnaire et § 3 |
| Moyenne à poids égaux en économie | écarté | qui gagne pèse plus que la taille de l'État (0,5 / 0,5 / 0,75), décision déjà prise |

**Protocole.** 274 mesures : les 170 de la mise au point, 80 neuves (50 représentatives, 15 alliances, 15 ménages ; `runs/echantillon_q2_2027.json`, clé `neuf`), 24 étalons. Les deux modèles de décision ont tout lu, et relu les 80 neuves ; Terra a lu les 80 neuves, les étalons et 69 mesures de la mise au point (budget). Une première formulation de la « rupture » faisait monter drex-max d'un cran (16 cas) : elle a été resserrée et tout a été relu. Rapport : `runs/essai_q2_2027.{json,md}` ; première rédaction : `runs/essai_q2_v1.{json,md}`.

**Résultats.**

- **Étalons** : 109 réponses attendues sur 109 pour chacun des trois modèles.
- **Stabilité (80 mesures neuves relues)** : drex-max, même sens sur 80 mesures sur 80 ; pplx-decider, 78 sur 80.
- **Échantillon neuf contre mise au point** (drex-max / pplx-decider, accord complet sur le sens) : 51 sur 80 (64 %) contre 114 sur 170 (67 %). Les corrections ne sont pas ajustées à l'échantillon qui les a inspirées.
- **Trois modèles, mesures neuves** : 875 réponses de sens unanimes sur 960 (91 %) ; seul contre les deux autres : Terra 38, drex-max 26, pplx-decider 15.

| Accord drex-max / pplx-decider | Première rédaction (170) | Seconde, mise au point (170) | Seconde, neuf (80) |
|---|---|---|---|
| Instrument | 83 sur 102 | 74 sur 79 | 43 sur 47 |
| Coût | 82 sur 102 | 67 sur 79 (74 à un niveau près) | 40 sur 47 (46) |
| Levier | 138 sur 168 | 66 sur 79 | 40 sur 47 |
| Classes de revenu (cinq questions) | 12 à 18 sur 21 | 10 à 12 sur 13 | 8 à 10 sur 10 |
| Économie | 62 sur 69 et 56 sur 69 | 73, 68 et 69 sur 78 | 34, 40 et 38 sur 41 |
| Notes d'économie de signes opposés | 4 | 1 | 0 |
| Alliances : notées par les deux, même sens | 5 sur 5 | 7 sur 8 | 10 sur 10 |
| Degré | 146 sur 168 | 141 sur 170 | 68 sur 80 |
| Portée | 132 sur 168 | 120 sur 170 (144 à un niveau près) | 58 sur 80 (73) |
| `a_dispositif` | 157 sur 168 | 152 sur 170 | 73 sur 80 |

- **Alliances** : sur les 80 mesures neuves, 9 à 12 mesures notées selon le modèle (3 à 6 sur 170 avant), toujours dans le même sens quand deux modèles les notent.

**Ce qui reste faible.**

- **L'accord d'ensemble n'a pas monté** : sur les mêmes mesures, accord complet sur le sens 115 → 113 (drex-max / pplx-decider, avec douze questions de sens au lieu de onze), 51 → 47 (Terra / drex-max, 69 mesures), 46 → 47 (Terra / pplx-decider).
- **Terra et les classes de revenu** : 5 ou 6 accords sur 11 avec drex-max sur les mesures neuves. Terra répond encore pour toutes les classes (« SMIC à 1 600 euros » : gain fort jusqu'aux très hauts revenus ; « Expulsion des étrangers délinquants » : perte forte pour les cinq classes). Les deux modèles de décision, eux, s'accordent. La correction vaut pour eux, pas pour Terra en effort bas.
- **Terra et les transferts** : 29 accords sur 40 avec drex-max (38 sur 41 entre modèles de décision) ; jamais de sens opposé, toujours « neutre » contre un côté (retraite à 65 ans, extinction du DALO).
- **Portée** : en recul. « Générale » contre « large » 12 fois sur 80, « générale » contre « individuelle » 6 fois (pplx-decider).
- **Degré** : pas mieux qu'avant ; il entre dans la force de tous les axes, d'où des écarts de note plus grands en souveraineté et en institutions quand le sens est le même.
- **`a_dispositif`** : drex-max est plus strict que pplx-decider (23 mesures sur 250 où seul pplx-decider voit un dispositif) et que Terra.
- **Limites** : les étalons sont de moi et non validés ; l'accord entre modèles n'est toujours pas une mesure de justesse ; Terra n'a lu que 69 des 170 mesures de la mise au point.

**Suite de l'audit (2026-11-11) : axe gauche-droite et « GAL/TAN ».** Trois fichiers mis à jour ont été lus, sans être exécutés ni adoptés (le script de non-régression remplace `base_2027`, `annotation_2027` et d'autres modules par des coquilles vides et lit ses sources dans un dossier absent d'ici). Vérification de chaque affirmation dans le code du dépôt :

| Affirmation | Constat |
|---|---|
| Deux formules gauche-droite coexistent | Vrai dans le code, sans effet : celle de `pipeline_scoring_2027.derive_fields` est remplacée par `Q.ideologie` pour toute mesure annotée (`base_2027.py`), soit les 10 850 mesures actives |
| Le sens gauche-droite n'est documenté que dans le code | Faux : `docs/spec_descripteurs_2027.md` § 11.3, page Méthode de la constellation, poids réglables dans « Plus de réglages » |
| L'écologie à gauche et la souveraineté dans le composite sont discutables | Fondé, et déjà relevé dans `docs/review_notation_2027.md` (écologie comptée deux fois à gauche, immigration deux à trois fois). C'est un choix à trancher, pas une erreur |
| q2 ne définit pas de composite | Vrai et voulu : le composite se calcule sur les axes, hors du questionnaire ; q2 rend les mêmes axes, la formule s'y applique telle quelle |
| `soc_egalite` n'entre pas dans le calcul | Vrai pour le fichier de l'audit, faux ici : la question est utilisée depuis la première rédaction |
| Le repli de l'accès aux droits vers l'axe immigration n'est pas documenté | Fondé pour q2 : sans réponse sur l'entrée et le séjour, `droits_statut` donne la note d'immigration, puis compte une seconde fois dans le composite société. En q1 ce repli n'existe pas. À régler avant tout branchement |

Deux défauts du questionnaire de l'audit, qui confirment de ne pas l'adopter :

- **Souveraineté = moyenne de l'Europe et des alliances.** Son propre témoin « Défense européenne renforcée et retrait du commandement intégré de l'OTAN » sort à 0 : les deux réponses s'annulent (le rapport l'explique à tort par des réponses « inchangé »). Un quota d'immigration passe de +100 à +50 parce que les alliances ne bougent pas.
- **Société.** Le correctif garde la bascule automatique (délit antidiscrimination : −80) que le même audit proposait de supprimer et que la seconde rédaction a supprimée (non noté si les libertés ne changent pas). Les deux règles se défendent ; il faut en choisir une (point 3 ci-dessous).

**Ce que changerait la proposition** (gauche-droite = économie et société seulement, souveraineté et écologie à part), simulé sur la base, centre d'une composante = moyenne pondérée par l'importance, approximation de la constellation : le centre gauche-droite d'un candidat bouge de 7 points en moyenne, 21 au plus (Philippe +23 → +44, Attal +7 → +24, Villepin −10 → +1, Arthaud −62 → −73) ; l'ordre change peu aux extrêmes, davantage au centre. Les candidats pro-européens et favorables à la protection de l'environnement glissent à droite : c'est l'effet attendu du retrait de deux composantes aujourd'hui comptées à gauche. La constellation offre déjà les axes économie et société séparés et des poids réglables ; mettre les poids de la souveraineté et de l'écologie à 0 par défaut suffit à appliquer la proposition.

**Portée, troisième rédaction (2026-11-11, 0,25 $ sur un plafond de 0,35 $, `METHODE = "essai-q2-v3"`).** Le désaccord venait des mesures sans public (diplomatie, défense, institutions : « Garanties de sécurité pour l'Ukraine » lue « générale » par un modèle, « individuelle » par l'autre) et de la frontière entre « large » et « générale ». Deux corrections : la portée n'est posée que si la mesure a un public (`a_menages`, `a_eco` ou `a_ecolo` ; une question peut désormais dépendre de plusieurs conditions, `Q2.conditions_de`, `Q2.ouverte`), sinon elle reste `null` ; trois niveaux au lieu de quatre (« large » = une grande catégorie ou tout le monde ; `Q2.PORTEE` = 0 / 0,5 / 1). Relecture des 274 mesures par les deux modèles de décision : accord sur la portée 120 sur 170 → 76 sur 85 (89 %) sur la mise au point, 58 sur 80 → 41 sur 47 (87 %) sur les mesures neuves ; étalons 109 sur 109 ; accord complet sur le sens inchangé (114 sur 170 et 51 sur 80) ; degré 146 sur 170 et 69 sur 80. Terra n'a pas été relu avec cette rédaction. Conséquence d'affichage si q2 était adopté : « Personnes concernées » serait vide pour les mesures sans public (en q1, 3 125 mesures sur 10 850 reçoivent une portée sans note en économie ou en écologie ni effet sur les revenus).

**Les axes sont-ils les bons ? (2026-11-11, base q1, 10 850 mesures, gratuit).**

| Axe | Mesures notées | Centres des candidats | Écart-type entre candidats |
|---|---|---|---|
| Économie | 7 098 (65 %) | −67 à +42 | 29 |
| Société | 1 268 (11 %) | −29 à +54 | 30 |
| Immigration | 238 (2 %) | −55 à +72 | 55 |
| Souveraineté | 1 278 (11 %) | −43 à +46 | 30 |
| Écologie | 2 440 (22 %) | −22 à +54 | 26 |

- Tous les axes départagent les candidats ; 1 834 mesures (16 %) n'ont aucun axe.
- Redondance : société et immigration sont corrélées à 0,99 sur les 146 mesures notées sur les deux (0,98 entre centres de candidats) ; économie et écologie à −0,72 ; économie et souveraineté à 0,02. Économie et société sont distinctes mesure par mesure (0,16) mais rangent les candidats dans le même ordre (0,93).
- Sujets cités par l'audit (mots-clés) : contre-pouvoirs et élites, 354 mesures dont 164 sans aucun axe (46 %) ; numérique et IA, 593 dont 115 sans axe ; bioéthique, famille, natalité, 77 dont 3 sans axe. Seul le premier est un manque, que l'axe institutions de q2 vise. Un axe « anti-élites » distinct n'est pas retenu : il se lit dans le ton d'un discours, pas dans une mesure jugée à l'aveugle.

**Comparaison avec le Chapel Hill Expert Survey 2024** (positions des partis selon des experts ; `CHES_2024_final_v2.csv`, chesdata.eu ; Rovny et al., *Electoral Studies*, 2025). Neuf candidats ont un parti dans l'enquête (Glucksmann rattaché au PS). Accord des classements (Spearman), calculé par la constellation avec ses propres centres : gauche-droite 0,90 (8 candidats), économie 0,97 (9), société 0,76 (8), immigration 0,89 (6), souveraineté contre intégration européenne 0,79 (8), écologie 0,70 (9). Écarts : sur la société, Philippe (+62) et Attal (+45) sortent plus « ordre » que Retailleau (+28), à l'inverse des experts ; en écologie, les candidats favorables à la protection plafonnent tous vers +50. La page Méthode de la constellation affiche cette comparaison (section « Comparaison avec une référence extérieure », fonction `comparaisonChes`, valeurs de l'enquête dans la constante `CHES`).

**L'axe institutions sur les mesures de contre-pouvoirs (2026-11-11, 0,28 $ sur un plafond de 0,30 $).** 299 mesures repérées par mots-clés (juges, médias, référendum, lobbies, syndicats, haute fonction publique), hors des autres échantillons, dont 156 sans aucun axe en q1 ; groupe figé sous `themes.theme_contre_pouvoirs` de `runs/echantillon_q2_2027.json`, lu seulement avec `--groupes theme_contre_pouvoirs` ; rapport `runs/essai_q2_contre_pouvoirs.{json,md}`.

- **Couverture** : sur les 156 mesures sans axe, 87 (drex-max) et 80 (pplx-decider) reçoivent une note d'institutions ; 61 % et 57 % ont au moins un axe en q2. Celles qui restent sans axe portent sur les moyens ou l'organisation de la justice (« Recrutement de magistrats et greffiers », « Simplifier le code de procédure pénale »), à raison.
- **Accord** : quand les deux modèles ouvrent l'axe (102 mesures), même réponse 94 fois (92 %), deux sens opposés. La condition est moins sûre : 34 mesures ouvertes par un seul modèle, 29 fois drex-max (médias, exécution des peines).
- **Un axe déséquilibré** : 87 notes « pouvoir partagé » pour 12 « pouvoir concentré ». Les programmes proposent presque toujours de partager ou de contrôler le pouvoir ; l'axe sépare surtout ceux qui le proposent beaucoup de ceux qui n'en parlent pas.
- **Par candidat** (moyenne des notes, à titre indicatif) : Ruffin −55, Mélenchon −49, Tondelier −46, Dupont-Aignan −34, Le Pen −32, Glucksmann −30, Lisnard −21, Retailleau −11, Attal −4, Philippe +15, Villepin +18. La gauche, le RN et Dupont-Aignan sont du même côté, le bloc central de l'autre : c'est le clivage « peuple contre élites » que l'audit croyait absent. Sur les sept candidats comparables, l'ordre suit celui de la dimension `people_v_elite` de Chapel Hill (accord des classements 0,88 ; seuil du hasard à sept candidats : 0,79).
- **Erreurs relevées** : le référendum pris pour un partage du pouvoir quel que soit son objet (« Premier référendum européen pour créer les États-Unis d'Europe » : −100) ; « Référendum d'initiative présidentielle pour lancer la Constituante » noté +100 par un modèle et −100 par l'autre ; « Neutralité politique des magistrats » lue comme un partage. La règle « passer par un référendum ne suffit pas » n'est pas toujours suivie.

**Institutions, troisième rédaction (2026-11-11, 0,134 $ sur un plafond de 0,15 $).** Corrections des deux réserves ci-dessus :

| Correction | Où |
|---|---|
| Probité et transparence comptées à part, hors axe | question `inst_objet` (pouvoir / probité / contenu inconnu), valeur calculée `probite` |
| Deux axes au lieu d'un : démocratie directe (`direct`) et contre-pouvoirs (`inst`) | questions `inst_direct` et `inst_controle` ; le niveau du milieu veut dire « aspect non touché » et ne donne pas de note, comme pour l'économie |
| Seule une procédure durable compte comme démocratie directe ; un référendum ponctuel est jugé sur son objet | option « inchangé » de `inst_direct`, « non » de `a_institutions` |
| Effet qui dépend d'un contenu encore à écrire (nouvelle Constitution) : pas de note | option `contenu_inconnu` de `inst_objet` |
| Peines et procédure pénale (juge de l'application des peines) renvoyées à la société | « non » de `a_institutions` |

Treize étalons ajoutés (37 en tout, 141 réponses attendues, toujours à valider). Relecture des 136 mesures du groupe `theme_institutions` (celles où au moins un modèle ouvrait l'axe à l'essai précédent, dont les 13 étalons) par drex-max et pplx-decider ; un groupe thématique demandé est désormais lu en entier, étalons compris. Rapport `runs/essai_q2_institutions.{json,md}`.

- **Référendum corrigé** : les référendums ponctuels (« États-Unis d'Europe », « appartenance à l'UE », retraites, collectivité unique) ne reçoivent plus de note d'institutions ; la Constituante est « contenu inconnu » pour les deux modèles. Étalons : 28/31 (drex-max), 30/31 (pplx-decider). Écarts : le juge de l'application des peines n'est pas rattaché à la société (les deux), « Se libérer des contraintes des juges » non ouvert par drex-max.
- **Probité** : 20 mesures sorties de l'axe (lobbying, pantouflage, conflits d'intérêts), même réponse pour 18.
- **Contre-pouvoirs moins déséquilibré** : 81 notes « renforcés » pour 33 « affaiblis » (sur les mêmes mesures, l'ancien axe donnait 194 « partagé » pour 29 « concentré »). Ordre indicatif : Tondelier −44, Glucksmann −34, Mélenchon −26, Ruffin −23, Retailleau −11, Le Pen −11, Lisnard +13, Villepin +48, Dupont-Aignan +50, Philippe +54 (2 à 39 notes par candidat). Accord avec Chapel Hill sur 7 candidats : indépendance de la justice 0,61, pouvoir exécutif 0,43 ; trop peu de notes pour conclure.
- **Démocratie directe à sens unique** : 42 notes sur 42 « plus de décision directe ». Personne ne propose d'en retirer ; le centre (+66 pour presque tous) ne dit rien. Seule la fréquence départage : rapportée à la taille du programme, Lisnard 9,5 notes pour 1 000 mesures, Le Pen 3,8, Dupont-Aignan et Ruffin 3,4, puis Glucksmann, Mélenchon, Villepin, Attal ; Philippe, Retailleau, Zemmour 0. Accord avec `people_v_elite` : 0,50 (9 candidats), faible.
- **Nouvelle ambiguïté, le RIC** : drex-max le lit souvent comme un affaiblissement des contre-pouvoirs (il permet de passer outre le Parlement), pplx-decider comme « inchangé » ; même réponse sur `inst_controle` 77 fois sur 89 (94 sur 102 avant). La rédaction donne prise aux deux lectures : « affaiblit » cite le vote qui passe outre le Parlement, « inchangé » la procédure citoyenne qui ne retire rien au Parlement.
- **Condition** : médias (financement de l'audiovisuel public, concentration) ouverts par drex-max seul ; 21 mesures ouvertes par drex-max seul, 8 par pplx-decider seul.

**Suite (2026-11-11, accord utilisateur, 0 appel, `METHODE = "essai-q2-v5"`)** :
- **RIC** : un référendum ou une initiative à la main des citoyens (RIC, référendum obligatoire, pétition) est « inchangé » pour les contre-pouvoirs, même s'il permet de voter une loi sans le Parlement ; il ne les affaiblit que s'il sert à annuler une décision des juges ou du Conseil constitutionnel. « Affaiblit » ne cite plus que le référendum décidé par l'exécutif pour contourner le Parlement. Deux étalons l'attendent (RIC législatif, référendum obligatoire).
- **Démocratie directe et probité deviennent des indicateurs de fréquence**, pas des axes : `calculer` donne `democratie_directe` (« etend » / « recule ») et `probite` (vrai / faux), `Q2.frequences` les compte par candidat pour 1 000 mesures de son programme (une mesure qui retire de la décision directe compte en moins). Il ne reste qu'un axe institutions, les contre-pouvoirs. L'affichage dans la constellation n'est pas fait (q2 n'y est pas branché).
- **Vérification (accord utilisateur, 0,134 $ sur un plafond de 0,15 $, rapport `runs/essai_q2_institutions_v5.{json,md}`)** : les RIC et référendums d'initiative citoyenne ne comptent plus comme un affaiblissement des contre-pouvoirs (Mélenchon, Ruffin, Dupont-Aignan, Lisnard : note retirée) ; restent « affaiblis » les cas voulus : passer outre une censure du Conseil constitutionnel, se libérer des juges, référendums décidés par l'exécutif (Villepin), recours au référendum contre un blocage européen (drex-max seul). Même réponse sur `inst_controle` 83 fois sur 91 (77 sur 89 avant), plus aucun signe opposé, écart moyen 6,7 points (9,8 avant) ; 81 notes « renforcés » pour 22 « affaiblis ». Étalons : 30/33 (drex-max), 32/33 (pplx-decider), les deux étalons du RIC conformes ; écarts inchangés (juge de l'application des peines, « Se libérer des contraintes des juges » pour drex-max).
- **Contre-pouvoirs par candidat** (indicatif, 2 à 38 notes) : Ruffin −67, Mélenchon −44, Tondelier −43, Glucksmann −34, Retailleau −11, Le Pen −11, Roussel −10, Lisnard +8, Dupont-Aignan +10, Villepin +48, Philippe +54. Accord avec Chapel Hill sur 7 candidats : 0,43 (indépendance de la justice), 0,39 (pouvoir exécutif) ; trop peu de notes pour conclure.
- **Fréquences** (sur les seules 136 mesures relues, pas sur tout le programme) : démocratie directe, pour 1 000 mesures, Lisnard 9,5, Le Pen 3,8, Dupont-Aignan 3,4, Ruffin 2,7 à 4,0, Glucksmann 2,8, Mélenchon 2,1 à 2,8, Villepin 1,8, Attal 1,4, Roussel 1,1, Tondelier 0,3, Arthaud, Philippe, Retailleau, Zemmour 0 ; les deux modèles donnent presque les mêmes chiffres. Probité : Ruffin 15 à 16, Glucksmann 2,8, Mélenchon 2,1, Tondelier 1,4, les autres 0 dans cet échantillon. Accord de la démocratie directe avec `people_v_elite` : 0,50 (9 candidats).

## 7. Ce qu'il resterait à décider

1. **Adopter q2 en production** (fait : renotation complète du 13 au 16 novembre 2026, 20,91 $) : toutes les mesures seraient à relire (clé de cache nouvelle). Terra en direct : environ 42 $ pour 10 850 mesures (0,0039 $ par mesure), moitié moins en batch ; drex-max 7,80 $ ; pplx-decider 2,20 $. Avant cela : valider les étalons et faire arbitrer par une personne un échantillon des désaccords (portée, degré, revenus).
2. **Qui lit** : Terra seul comme aujourd'hui, ou Terra et un modèle de décision, les désaccords de sens allant en file de validation (35 à 37 mesures sur 80 sur l'échantillon neuf). Pour les classes de revenu, la seconde rédaction ne tient qu'avec un modèle de décision.
3. **Société** : **décidé le 2026-11-11** : la règle q2 est gardée sur l'axe (la sanction d'une discrimination n'est pas de l'ordre, le sens vient des libertés, pas de note si les libertés ne changent pas), et la protection contre les discriminations devient un indicateur de fréquence (`antidiscrimination`, compté dans `Q2.frequences` pour 1 000 mesures, que la mesure soit notée sur l'axe ou non). **Indicateur affiché dès maintenant** dans la fiche d'un candidat de la constellation, à partir de la finalité q1 `droits_egalite` (377 mesures) ; l'axe société q1 garde sa bascule jusqu'au passage à q2.
6. **Gauche-droite** (production, indépendant de q2) : **décidé le 2026-11-11, les poids actuels sont gardés** (économie 1, société 2, souveraineté 0,5, écologie 0,5 ; réglables par le lecteur).
7. **Accès aux droits en q2** : **décidé le 2026-11-11, solution A** : l'accès aux droits selon le statut (nationalité, titre de séjour, ancienneté de résidence) fait partie de l'axe immigration, qui devient « étrangers : entrée, séjour et droits » (repli quand la mesure ne touche pas à l'entrée ni au séjour) ; il ne compte plus à part dans le composite société (`Q2.ideologie`). `rights_status` reste exporté pour l'affichage. **Appliqué aussi en production (q1) le 2026-11-11** : `Q.calculer` reprend l'accès aux droits sur l'axe immigration quand `ouv_sens` ne s'applique pas (106 mesures de plus, 343 en tout), `Q.ideologie` et la constellation ne le comptent plus à part (poids « Accès aux droits » retiré des réglages).
4. **Affichage** : les trois nouveaux axes, la faisabilité calculée et le financement supposent des changements dans l'export et la constellation, non faits.
5. **Importance** : retirer ou non les 20 points de précision.
