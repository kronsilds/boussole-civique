# Suivi : comparaison de modèles et relecture complète (2026-11-07 et 08)

> Sous-fichier de [SUIVI_PROJET.md](../../SUIVI_PROJET.md) (sommaire et état courant). Précédent : [06](06_2026-11-07_contexte_lexique_importance.md) · Suivant : [08](08_2026-11-07_09_votes_publication_revenus.md)

## Comparaison de modèles : GPT-6.1 Terra (low) / GPT-6 Luna (high) (2026-11-07, 0,20 $)

- Script `comparer_modeles_2027.py` : les deux modèles lisent les mêmes mesures avec la méthode de production (passage, lexique, même consigne). Rapport : `runs/comparaison_modeles_2027.{json,md}`.
- Échantillon : 100 mesures, soit les 70 du premier essai (50 en confiance basse, 20 avec un mot ambigu) et 30 mesures représentatives tirées au hasard (graine 2027, 2 ou 3 par candidat).
- `contexte_2027.requete` : `max_tokens` dépend désormais de l'effort (low inchangé à 12 000, high 48 000).
- Coût réel par mesure : Terra low 0,0028 $, Luna high 0,0007 $ (4 fois moins cher). Luna high est lent : environ 10 minutes pour 100 mesures en appel direct.
- Accord complet sur les questions de sens : 37 sur 100 (confiance basse 8/50, mot ambigu 13/20, représentatif 16/30). Les questions descriptives s'accordent de 56 % (faisabilité) à 82 %.
- Nature des 106 écarts de sens :
  - « indéterminé » : 33 chez Terra seul, 6 chez Luna seul ;
  - applicabilité (axe noté d'un seul côté) : 31 fois Luna note un axe que Terra juge non applicable, 13 fois l'inverse ;
  - valeurs différentes : 23, dont 6 directions opposées.
- Mesures représentatives : sur l'axe économique, l'écart absolu moyen est de 9 points et le biais moyen de +2 (Luna moins Terra) ; les autres axes sont trop peu notés pour conclure.
- Lecture humaine des directions opposées : partage (Luna plus juste sur les prix agricoles de Ruffin et la politique industrielle de Glucksmann ; Terra sur l'échelle européenne des « champions européens » et sur Frontex). Luna attribue parfois des axes de façon excessive (écologie pour une remise en cause des traités, revenus pour un non-remplacement de fonctionnaires).
- Conclusion provisoire : pas de gagnant net sur la qualité, Luna 4 fois moins cher. Il manque une base de bruit (relecture du même modèle) pour savoir si 37 % d'accord est faible.

### Bruit de chaque modèle et ajout de Luna low (2026-11-07, 0,40 $)

- `comparer_modeles_2027.py` accepte plusieurs candidats (`--candidat a:effort b:effort`) et `--repetitions 2` : chaque modèle relit les mêmes mesures (même requête, clé de cache distincte). `relire_direct` prend un coût estimé par modèle.
- Coûts réels pour 100 mesures : Terra low 0,28 $ ; Luna high 0,075 $ ; Luna low entre 0,017 et 0,030 $. Terra low ne raisonne presque pas (316 jetons de raisonnement pour 100 mesures), contre 94 000 pour Luna high.
- Accord complet sur le sens, sur 100 mesures (dont 30 représentatives) :

| Paire | Sens identique | Représentatives | Écart éco moyen |
|---|---|---|---|
| Terra low / Terra low (bruit) | 66 | 25/30 | 7,6 |
| Luna high / Luna high (bruit) | 46 (sur 98) | 19/30 | 7,4 |
| Luna low / Luna low (bruit) | 45 | 17/30 | 8,5 |
| Terra low / Luna high | 37 | 16/30 | 12,2 |
| Terra low / Luna low | 27 | 12/30 | 16,0 |
| Luna high / Luna low | 38 | 14/30 | 11,6 |

- Lecture :
  - Terra low est le plus constant ; Luna, à tout effort, se contredit d'une lecture à l'autre une fois sur deux en moyenne sur cet échantillon difficile.
  - Une bonne partie de l'écart entre Terra et Luna vient du bruit de Luna. Il reste un écart propre aux modèles : 12 à 16 points sur l'axe économique entre modèles, contre 7 à 8 points pour un même modèle.
  - L'effort high n'apporte presque rien à Luna en constance (46 contre 45).
  - Constance n'est pas justesse : Terra emploie souvent « indéterminé » (36 à 40 mesures sur cet échantillon difficile), et ce choix répété aide son accord avec lui-même.
- Recommandation : garder Terra low pour la relecture complète (13,82 $ en batch), plus stable mesure par mesure. Luna high (environ 3,50 $) ne se justifierait que si le budget primait.

### GPT-6.1 Sol low et Claude Sonnet 5.5 low, valeurs extrêmes douteuses (2026-11-07, 1,92 $)

- Échantillon élargi à 130 mesures : groupe « extreme_douteux » de 30 mesures, avec une valeur d'au moins ±90 sur un axe que leur thème note dans moins de 15 % des cas (62 dans la base), plus le cas signalé m-ruffin-0110 (colonie notée 100 sur « fermeture »). L'échantillon est figé dans `runs/echantillon_comparaison_2027.json`.
- Une seule lecture par modèle (choix de l'utilisateur : pas de mesure de stabilité pour Sol et Sonnet).
- Sonnet : l'API Anthropic refuse `enum` avec `type: [string, null]` ; `contexte_2027.schema_anyof` le réécrit en `anyOf`, pour les modèles Anthropic seulement. Les requêtes OpenAI et les clés de cache sont inchangées.
- Coût par mesure : Sol 0,0059 $, Sonnet 0,0088 $ (environ 2,2 fois plus de jetons d'entrée en français). Sonnet : 120 mesures sur 130, le dernier lot ayant été coupé par le plafond.
- Accord complet sur le sens : Terra/Sol 67 sur 130 ; Luna/Sol 52 ; Terra/Luna 48 ; Sol/Sonnet 35 sur 120 ; Luna/Sonnet 30 ; Terra/Sonnet 29.
- Sonnet se distingue : 3 « indéterminé » seulement (Terra 40) ; confiance plus basse (0,80, contre 0,90 à 0,92) ; il note plus d'axes que Terra (écologie, souveraineté, revenus), il n'en note pas moins.
- Valeurs extrêmes douteuses :
  - les ±100 « Société » de l'ancienne lecture q1 sont ramenés vers ±50 à 60 par la lecture avec contexte, quel que soit le modèle ;
  - accès aux droits : les trois modèles OpenAI lisent « chaque enfant français » comme « réservé aux nationaux » (Ruffin colonie, Ticket culturel, Capital nouveau-né, Fonds France, à +100 avec une confiance de 0,89 à 0,98) ;
  - Sonnet seul juge ces mesures non applicables, tout en gardant +100 pour la priorité nationale et les allocations réservées aux foyers français ;
  - lecture symétrique côté « universel » (−100 pour Assurance maladie universelle, Accès aux services publics à 30 minutes) chez tous les modèles lus.
- Conclusion :
  - l'erreur sur « Français » vient de la question plus que du modèle, et Sol n'apporte rien de plus que Terra pour 2 fois le prix ;
  - Sonnet lit mieux l'intention sur ce point, mais diverge beaucoup des autres ailleurs, pour environ 40 $ en batch sur la relecture complète ;
  - piste suivante : préciser la question d'accès aux droits (restriction seulement si la nationalité ou le titre de séjour est une condition explicite ; « universel » seulement si l'accès s'ouvre au-delà du statut), puis la tester avec Terra sur l'échantillon.

### Question d'accès aux droits précisée (méthode contexte-v2), Qwen et DeepSeek (2026-11-07, 0,57 $)

- Consigne `contexte_2027.LECTURE_DROITS`, demandée par l'utilisateur : lire le verbe et l'effet, pas la simple mention des Français.
  - Restreindre, réserver, conditionner, donner la priorité aux nationaux : l'accès se ferme.
  - Garantir, offrir ou financer « à chaque Français » : null, sauf condition de nationalité ou de titre de séjour, ou exclusion explicite.
  - « Universel » ou « étendu » seulement si l'accès s'ouvre au-delà du statut.
- La méthode passe en `contexte-v2` ; `a_relire` relit toute mesure lue avec une autre méthode. Relecture complète : 9 900 mesures, estimation 14,85 $ en batch. Anciens rapports archivés dans `runs/comparaison_modeles_2027_contexte_v1.*`.
- Terra low v2 sur les 130 mesures (0,36 $) :
  - faux « réservé aux nationaux » corrigés : Ruffin colonie, Ticket culturel, Médiathèque, Capital nouveau-né et Fonds France passent à non applicable ;
  - vrais extrêmes gardés à +100 : priorité nationale, allocations réservées aux foyers français (+50 en v1), logement social réservé, fléchage vers les acteurs français ;
  - « universel » gardé quand le texte le dit : services publics « sans condition de nationalité » (Mélenchon), logement « à toute résidente et tout résident » (Roussel). Sécurité sociale unique passe à non applicable ; Assurance maladie universelle reste à universel (confiance 0,76) ;
  - ailleurs, rien de mesurable : sens identique entre v1 et v2 sur 79 mesures sur 130 (24 sur 30 représentatives), ce qui correspond au bruit propre de Terra (66 sur 100, 25 sur 30).
- Qwen 3.8 Flash et DeepSeek V4.1 Flash : échec. Ils ignorent l'effort low et raisonnent jusqu'à la limite de 12 000 jetons par lot ; Qwen n'a rendu aucune réponse et DeepSeek un seul lot sur 13 (0,21 $ perdus).

### Relecture complète en contexte-v2 (2026-11-07 et 08, 12,54 $)

- Terra low, contexte-v2, 9 900 mesures en 3 batchs de 330 lots (plafond total 16 $ accordé par l'utilisateur) : 4,04 $, 4,05 $, 4,31 $, aucun lot en échec. L'estimation (4,95 $ par batch) était un peu haute.
- Compléments (plafond 0,20 $) : soc_finalite 203 mesures (0,104 $), degre_rupture 85 mesures (0,036 $ ; 188 prévues avant que soc_finalite ne soit relu). Coût réel par lot d'environ 0,01 $, au-dessus de l'estimation : le premier run a dépassé son plafond de 0,0006 $.
- Mise à jour avec `--changement-methode` : les 180 signalements « axe perdu ou gagné » et « déplacement fort » nés de la relecture (surtout des axes gagnés : eco 133, ecolo 53) ne sont pas des changements de programme et sortent de la file. Une mise à jour sans cette option après une relecture voulue les recrée.
- File après relecture : confiance basse 68 (25 avant), mesures modifiées 247, rapprochements incertains 82.
- Effet sur les candidats (moyenne brute des mesures, avant puis après, non pondérée par thème) : économie stable à moins de 4 points sauf Zemmour (+6). Plus forts déplacements : ouverture Glucksmann −30 → −51, Villepin +32 → +49 ; souveraineté Arthaud −15 → +6, Zemmour +42 → +25, Lisnard +1 → +15, Mélenchon −3 → +11 ; société Ruffin +46 → +30, Arthaud −53 → −65.
