# Review de la notation : questions, axes, calculs d'affichage, et essai d'un modèle de décision

Date : 2026-11-10. Base analysée : 10 850 mesures actives, toutes lues par GPT-6.1 Terra (low, méthode `contexte-v2`).
Rien n'a été modifié dans le questionnaire, les formules, la base ni l'export. Dépense : 0,152 $ (plafond accordé 0,30 $).

## 1. En bref

1. Le questionnaire pose plusieurs fois la même chose. Le « flou » d'une mesure est demandé cinq fois, l'effet sur les revenus deux fois, et l'accès aux droits recoupe presque entièrement l'immigration.
2. L'axe économique mesure surtout la taille de l'action publique : une aide aux entreprises ou une protection commerciale sort légèrement à gauche.
3. Les axes n'ont pas la même échelle (souveraineté et écologie plafonnent à ±85, immigration atteint ±100 dans 22 % des cas), ce qui fausse les axes combinés. L'immigration y compte en plus deux à trois fois.
4. Le centre d'un candidat donne le même poids à un thème noté sur une seule mesure qu'à un thème noté sur quarante. Sur les axes peu fournis, l'écart atteint 28 points (Philippe, société : +26 affiché, +54 en moyenne de ses 61 mesures).
5. 17 % des mesures n'ont de position sur aucun axe : 66 % du thème institutions, 58 % de la culture, 49 % de l'international. Il manque un axe institutions et un axe international.
6. `nace-ai/drex-max` fait jeu égal avec Terra sur les désaccords arbitrés (25 contre 23, 15 ex æquo), se relit à l'identique dans 96 % des cas (Terra : 66 %) et coûte 0,0006 $ par mesure, compléments compris. Il se trompe en revanche sur l'accès aux droits et ne rédige pas de note d'audit.

## 2. Questions : pertinence et doublons

| Question | Constat | Proposition |
|---|---|---|
| `levier`, `precision`, `instrument`, `faisabilite`, `cout` | Le même signal de flou : déclaration 31 %, orientation générale 31 %, instrument non identifiable 33 %, faisabilité non évaluable 31 %, coût indéterminable 49 %. 90 % des mesures ont 0 ou 4 de ces signaux sur 4 (6 926 à zéro, 2 873 à quatre). | Garder `levier` et `precision`. Ne poser `instrument`, `faisabilite` et `cout` qu'aux mesures qui ne sont pas des déclarations. |
| `faisabilite` | Retrouvée à 76 % à partir de `instrument` et `cout` (36 % au hasard). Mélange le juridique et le budgétaire. | La calculer depuis l'instrument (volet juridique), ou la scinder ; ne plus l'afficher comme un axe indépendant. |
| `changement` | 62 % de « réforme significative » : peu discriminant. Cohérence faible avec `degre_rupture` (61 % retrouvé, 51 % au hasard ; 35 « refontes structurelles » classées « ajustement »). | Étendre `degre_rupture` (3 niveaux illustrés) à tous les axes et abandonner `changement` dans les formules. |
| `revenus_sens` | Doublon des cinq questions par classe de revenu : corrélation 0,88 avec `revenu_effet`, retrouvée à 81 %. | Calculer « effet sur les revenus » depuis les classes ; ne plus afficher les deux. |
| `droits_statut` | Quand l'immigration s'applique aussi (135 mesures), 95 % des réponses se déduisent de `ouv_sens`. Valeur propre : 108 mesures hors immigration (priorité nationale, droit de vote des étrangers, allocations). | La garder, mais comme composante de l'immigration (voir § 3), pas comme troisième composante de « société ». |
| `soc_autorite`, `soc_libertes` | 53 % de réponses jumelles (renforce + restreint 37 %, allège + étend 16 %). | Garder ; corriger le plafond (voir § 3). |
| `public_vise` | 16 options, « un secteur » 25 %. N'entre dans aucune formule et n'est pas exporté vers la constellation. Stabilité la plus faible (80 %). | L'exploiter (filtre « qui est visé ») ou la retirer. |
| `cout` | N'agit sur l'ampleur que pour 664 mesures (6 %) ; c'était la question la moins juste en effort low (30 % à l'arbitrage du 6 novembre). | Indicatif seulement ; la sortir de la formule d'ampleur. |

## 3. Axes et formules

- **Économie.** Sens = 0,75 × État + 0,5 × redistribution. 2 744 notes (39 %) ne reposent que sur l'État, à −30 en moyenne. Les 768 mesures « plus d'action publique, au profit des entreprises » (11 %) sortent à −12,5 : rompre les accords de libre-échange −16, préférence européenne dans la défense −15, fonds de relocalisation −14. Une redistribution sans changement de la taille de l'État plafonne à 43.
- **Société.** Sens = 0,6 × autorité + 0,6 × libertés. Une mesure qui ne tranche qu'une question plafonne à 60 (266 mesures, valeur absolue moyenne 22,5 contre 55,6) : un nouveau droit sans effet sur le contrôle ne peut pas dépasser −60, quelle que soit la rupture.
- **Échelles inégales.** Part des notes à ±90 et plus : économie 0,4 %, souveraineté 0 % (maximum 85), écologie 0 % (maximum 85), société 7,2 %, immigration 22,3 %. Valeur absolue moyenne : 37, 45, 51, 42, 62. Société et immigration utilisent `degre_rupture`, les trois autres la portée et le changement.
- **Écologie comptée deux fois à gauche.** Sur les 1 905 mesures notées en économie et en écologie, la corrélation est de −0,72 : une norme environnementale est « plus d'action publique » (gauche), puis l'écologie est ajoutée à gauche dans l'idéologie.
- **Immigration comptée deux à trois fois.** Société et immigration sont corrélées à 0,99 sur les 146 mesures notées sur les deux (12 % des notes société ; Le Pen 19 sur 54, Dupont-Aignan 43 sur 176). L'axe combiné « société » ajoute immigration et accès aux droits à poids égaux : l'immigration pèse environ un tiers du gauche-droite pour 2 % des mesures.
- **Niveau de revenu.** L'échelle met les cadres à 0 (du 60e au 90e centile) et donne le même poids au 1 % le plus riche qu'aux 30 % les plus modestes. `revenu_effet` ne porte que sur les classes concernées : une taxe sur le 1 % vaut −100.

## 4. Calculs d'affichage (constellation)

- **Centre d'un candidat.** Statistique robuste des étoiles, chaque thème pesant selon l'importance moyenne de ses propositions, sans tenir compte du nombre de mesures notées sur l'axe. Étoiles qui reposent sur une ou deux mesures : société 43 %, souveraineté 38 %, immigration 55 %, accès aux droits 72 %, économie 16 %.

  | Candidat, axe | Centre affiché | Moyenne de ses mesures | Mesures |
  |---|---|---|---|
  | Philippe, société | +26 | +54 | 61 |
  | Le Pen, écologie | +28 | +10 | 94 |
  | Retailleau, écologie | −39 | −22 | 123 |
  | Tondelier, société | −30 | −15 | 356 |
  | Dupont-Aignan, société | +35 | +45 | 175 |

  Écart moyen entre les deux calculs : économie 4, société 7,5, souveraineté 6.
- **Correctif testé, gratuit, non appliqué :** multiplier le poids d'un thème par min(1, n/5), n étant ses mesures notées sur l'axe (même idée que la fiabilité des axes combinés). Société : écart maximal 28 → 12, moyen 8,2 → 6,4. Gain faible ailleurs, et l'écologie se dégrade (maximum 17 → 24) : à valider sur la constellation avant de l'adopter.
- **Importance.** La précision vaut 20 points sur une échelle de 15 à 100 : orientation générale 29,9, précis 41,4, chiffré 52,3. Une mesure chiffrée pèse donc 1,75 fois une orientation, alors que les déclarations (31 %) portent souvent les marqueurs. Média et votes étant vides, l'importance se réduit au composite structurel.
- **Mineur.** Une confiance est exportée pour un axe non applicable (`conf.soc = 0,85` avec `soc = null`).

## 5. Ce qui manque

- **Institutions et démocratie** : concentration du pouvoir exécutif ↔ contre-pouvoirs, participation, décentralisation. 468 mesures d'organisation institutionnelle n'ont aucune position, et la probité, retirée de l'axe société, ne va nulle part.
- **International et défense** : alignement atlantique et européen ↔ non-alignement ; effort de défense. L'axe souveraineté ne dit que le niveau de décision.
- **Financement** : la mesure dit-elle comment elle est financée ? Plus utile au lecteur que la faisabilité budgétaire actuelle.

Ces questions iraient dans `Q.COMPLEMENTS` (clé de cache des lectures payées conservée) et ne sont pas ajoutées sans décision.

## 6. Essai de `nace-ai/drex-max` contre GPT-6.1 Terra

**Adaptation** ([decisions_2027.py](../decisions_2027.py), 9 tests) : un modèle de décision ne rédige rien, il rend une probabilité par option. Chaque question q1 devient un choix ; la condition d'un axe devient une question oui/non posée une fois par axe (axe fermé sous 0,5) ; les règles de la consigne sont réparties dans les questions ; les compléments sont posés en même temps. L'API a changé depuis le 5 novembre (`state`, questions en objet) et drex-max refuse plus de 16 questions par appel : deux appels par mesure.

**Protocole** : les 130 mesures de l'échantillon figé (50 en confiance basse, 20 à mot ambigu, 30 extrêmes douteux, 30 représentatives), mêmes éléments que Terra (proposition, passage, lexique, à l'aveugle), deux lectures drex-max. Commande : `python .\comparer_modeles_2027.py --candidat nace-ai/drex-max:decisions --rapport comparaison_decisions_2027 --max-cost X`.

| | drex-max | Terra low |
|---|---|---|
| Coût par mesure | 0,0006 $, compléments compris | 0,0028 $ en direct, 0,0013 $ en batch, compléments en plus |
| Durée | 1,3 s par mesure | batch jusqu'à 24 h |
| Même sens à la relecture | 124 sur 129 (96 %) | 66 sur 100 (mesure du 7 novembre) |
| « Indéterminé » | 18 mesures | 44 mesures |
| Note d'audit | aucune | oui |

- **Accord complet sur le sens entre les deux** : 46 sur 130 (représentatives 14 sur 30). Pour mémoire, Terra / Luna high 37 sur 100, Terra / Sol 67 sur 130, Terra / Sonnet 29 sur 120.
- **Nature des 168 réponses de sens différentes** (sur 1 170) : 95 fois Terra note et drex-max juge l'axe non applicable, 19 fois l'inverse, 22 « indéterminé » chez Terra, 25 écarts d'intensité, **4 directions opposées**. Baisser le seuil des conditions ne rapproche pas les deux.
- **Axes calculés, compléments compris** : économie, écart moyen 18 points, 51 sur 68 à moins de 25 points, 3 signes opposés ; souveraineté 17 ; immigration 7 ; écologie 10.
- **Confiance** : celle de drex-max prédit l'accord avec Terra (97 sur 100 au-dessus de 0,8 ; 34 sur 64 sous 0,4). Celle de Terra discrimine moins (91 % au-dessus de 0,8, 68 % entre 0,6 et 0,8).
- **Questions descriptives** : accord de 56 % (faisabilité) à 77 % (changement), non arbitré. drex-max répond plus souvent « portée générale » (53 contre 26), « déclaration » (57 contre 41) et « sans impact budgétaire » (38 contre 17).

**Arbitrage de 64 désaccords sur 123**, étiquettes A/B tirées au hasard, verdicts écrits avant lecture de la clé (`runs/arbitrage_decisions_2027_*`) :

| Type de désaccord | drex-max plus juste | Terra plus juste | Ex æquo |
|---|---|---|---|
| Terra note, drex-max « non applicable » (26) | 13 | 5 | 8 |
| drex-max note, Terra « non applicable » (14) | 2 | 9 | 3 |
| « Indéterminé » d'un côté (12) | 4 | 6 | 2 |
| Intensité (8) | 4 | 2 | 2 |
| Directions opposées (4) | 2 | 1 | 0 (1 : aucun) |
| **Total (64)** | **25** | **23** | **15** |

- drex-max applique moins souvent les axes économie et société, et a le plus souvent raison (audit de modèles d'IA, médiathèque, algorithmes des plateformes notés en économie par Terra).
- drex-max échoue sur l'accès aux droits : 7 désaccords sur 8 donnés à Terra. Il relit « tous les Français » comme une préférence nationale (ticket culturel, Fonds France), l'erreur que la consigne `contexte-v2` avait corrigée chez Terra.
- Limites : un seul arbitre (Claude), qui connaissait les habitudes de chaque modèle (aveugle imparfait), sans le passage sous les yeux, sur la moitié des désaccords. L'accord avec Terra n'est pas une mesure de justesse.

## 7. Recommandations

1. **Gratuit, affichage** : tenir compte du nombre de mesures par thème dans le centre (à valider), retirer l'axe « effet sur les revenus » en double, regrouper immigration et accès aux droits en une seule composante de l'axe société, ramener les axes à une échelle commune avant de les combiner.
2. **Décisions de notation** : sortir la précision de l'importance ; revoir le poids État / redistribution ou afficher les deux séparément ; lever le plafond à 60 des mesures de pures libertés.
3. **drex-max, sans remplacer Terra** : seconde lecture systématique de tout le corpus (environ 6,60 $ en appel direct), pour envoyer en file de validation les seuls désaccords de sens et corriger l'applicabilité des axes économie et société. La question d'accès aux droits reste à Terra.
4. **Nouveaux axes** (institutions, international) : les tester d'abord en compléments avec drex-max sur un échantillon ; trois questions de plus coûtent environ 0,0003 $ par mesure.
