# Spécification : décrire les propositions plutôt que les noter

Statut : **projet, étape 1 (gratuite)**. Rien n'est branché dans la chaîne et aucun appel n'est fait. Formules et cas types : [descripteurs_2027.py](descripteurs_2027.py), [test_descripteurs_2027.py](test_descripteurs_2027.py).

## 1. Pourquoi

- **Notes en paliers.** Quand on demande un nombre adossé à des repères décrits, le modèle choisit le repère le plus proche. Avec 5 repères, GPT met 33 mesures sur 60 exactement à −50 ; avec 9 repères, 20 à −25 (pilote du 2026-11-06).
- **Note opaque.** Un « −50 » ne dit pas pourquoi. L'interface ne peut pas expliquer la place d'une étoile autrement qu'avec un chiffre.
- **Rien pour 829 propositions sur 3 892** (surtout institutions et sécurité), qui n'ont aucun axe idéologique. Rien non plus pour rapprocher deux mesures de candidats différents, à part le thème.

## 2. Principe

1. On pose au modèle des **questions factuelles à choix**, à l'aveugle comme aujourd'hui : quel levier, quel public, quelle portée, et pour l'économie, dans quel sens.
2. La note de l'axe est **calculée par une formule publique** à partir de ces réponses. Le modèle ne donne plus de nombre.
3. Les **descripteurs communs** (levier, public, portée) sont posés pour toutes les propositions. Les **questions de sens** ne le sont que si l'axe s'applique : on garde les conditions actuelles (`has_eco`…). Le coût d'une mesure de sécurité ne la rend toujours pas « de gauche ».
4. L'interface montre d'abord les mots (« plus d'action publique · vers les modestes · contrôle des prix · portée large »), le chiffre en dernier.

## 3. Ce qui existe déjà (à réutiliser, pas à reposer)

| Dimension | Couverture | Usage dans le nouveau schéma |
|---|---|---|
| `rupture` (ampleur du changement, 4 niveaux) | 3 892 | **réutilisée** comme « changement » dans l'ampleur ; varie bien par mesure (0 à 100), même si elle départage peu les candidats (45 à 63) |
| `cost_estimate` (ordre de grandeur budgétaire) | 3 892 | **réutilisée** dans l'ampleur |
| `has_eco`, `has_soc`, … (conditions d'application) | 3 892 | **inchangées** : décident si les questions de sens sont posées |
| `legal_instrument` | 3 892 | inchangé (faisabilité) ; complète le levier |
| `rights_income` (part de la population, revenus) | 1 300 | à terme remplaçable par `portee`, qui vaut pour toutes les mesures |
| `income_direction` (sens de l'effet sur les revenus) | 1 293 | inchangé ; proche de `eco_distrib` mais différent (sens pour les personnes concernées, pas progressivité) |
| `horizon` | 3 892 | peu informatif (presque toujours « non précisé ») ; hors sujet ici |
| `eco` (note demandée) | 1 687 | **remplacée** par la note calculée |
| `soc`, `sov`, `ouverture`, `ecolo` | 284 à 1 285 | inchangés dans un premier temps (voir §7) |

## 4. Nouvelles questions

### Descripteurs communs (toutes les propositions)

**`levier`** : principal moyen d'action, celui qui porte l'essentiel de l'effet.
déclaration ou symbole · étude ou rapport · organisation des institutions · incitation · dépense ou service public · impôt ou cotisation · obligation ou interdiction · contrôle des prix ou des revenus · contrôle et sanction · allègement de règles · propriété publique · transfert au privé.

**`public_vise`** : public principalement visé, en bien ou en mal.
toute la population · ménages modestes · classes moyennes · ménages aisés · jeunes ou étudiants · retraités ou âgés · salariés · indépendants, PME, agriculteurs · grandes entreprises ou finance · un secteur · étrangers · auteurs d'infractions · agents ou administrations · élus ou institutions · États ou Union européenne · aucun identifiable.

**`portee`** : nombre de personnes ou d'acteurs directement concernés.
individuelle (quelques acteurs) · ciblée (catégorie sous condition) · large (grande catégorie, secteur entier) · générale (toute la population ou l'économie).

### Questions de sens de l'axe économique (si `has_eco`)

**`eco_etat`** : la mesure augmente, laisse inchangé ou réduit le poids de l'action publique dans l'économie (dépense, prélèvements, règles imposées au marché, propriété publique).

**`eco_distrib`** : la mesure déplace revenus, patrimoine ou pouvoir économique vers les modestes ou les salariés, de façon neutre, ou vers les entreprises, le capital ou les aisés.

Ces deux questions séparent ce que l'ancien barème mélangeait (taille de l'État et redistribution). Elles rendent visibles les cas où les deux divergent : une baisse de TVA sur les produits de première nécessité réduit l'action publique **et** redistribue vers les modestes.

## 5. Formule de l'axe économique

```
sens    = borné à [-1, 1] de  0,75 × état + 0,5 × distribution
          (état : augmente -1, inchangé 0, diminue +1 ; distribution : vers modestes -1, neutre 0, vers aisés +1)
force   = poids du levier (tableau ci-dessous)
ampleur = 0,55 + 0,45 × moyenne(portée, changement)
          portée : individuelle 0, ciblée 1/3, large 2/3, générale 1
          changement : le plus grand de rupture/100 et du budget (faible 0, modéré 1/3, important 2/3, massif 1)
eco     = arrondi(100 × sens × force × ampleur)
```

| Levier | Force |
|---|---|
| déclaration ou symbole, étude ou rapport | 0,15 |
| organisation des institutions | 0,25 |
| incitation, contrôle et sanction | 0,40 |
| allègement de règles | 0,65 |
| dépense ou service public, obligation ou interdiction | 0,70 |
| impôt ou cotisation | 0,75 |
| contrôle des prix ou des revenus | 0,85 |
| propriété publique, transfert au privé | 1,00 |

**Déclarations** (correctif du pilote) : une orientation seulement annoncée garde son sens. La consigne demande le sens de l'orientation même sans moyen précisé ; le levier reste « déclaration ». Sa force va de 0,15 à 0,85 selon l'ampleur du changement visé (`rupture`), sans tenir compte d'un montant annoncé. Ainsi « mettre fin au système capitaliste » donne −85, « Socialisme au programme » −52 et un objectif de désendettement +24.

Lecture : le **sens** dit de quel côté va la mesure. La **force** dit à quel point le moyen choisi pèse sur l'économie : nationaliser pèse plus que subventionner. L'**ampleur** module selon le nombre de personnes concernées et l'importance du changement. Une mesure minime garde 55 % de la force de son levier.

### Cas types (calculés, tests verts)

| Mesure | Repère attendu (barème à 9) | Calcul | Explication affichée |
|---|---|---|---|
| Collectivisation : expropriation des grands groupes | −100 | **−100** | plus d'action publique · vers les modestes · propriété publique · portée générale |
| Blocage du prix des carburants | −75 | **−79** | plus d'action publique · vers les modestes · contrôle des prix ou des revenus · portée générale |
| SMIC à 2 200 € | −75 | **−74** | plus d'action publique · vers les modestes · contrôle des prix ou des revenus · portée large |
| Soins remboursés à 100 % | −75 | **−70** | plus d'action publique · vers les modestes · dépense ou service public · portée générale |
| Nationalisation d'une seule entreprise | −75 | **−54** | plus d'action publique · sans effet redistributif · propriété publique · portée très limitée |
| ISF renforcé sur les gros patrimoines | −50 | **−58** | plus d'action publique · vers les modestes · impôt ou cotisation · portée ciblée |
| Fonds public de 500 Md€ pour le climat | −50 | **−52** | plus d'action publique · sans effet redistributif · dépense ou service public · portée générale |
| Gratuité du permis pour les moins de 25 ans | −25 | **−37** | plus d'action publique · sans effet redistributif · dépense ou service public · portée ciblée |
| Sanctionner l'intérim abusif | −25 | **−30** | plus d'action publique · vers les modestes · contrôle et sanction · portée large |
| Subvention à la réindustrialisation | discutable | **−15** | plus d'action publique · vers les aisés ou les entreprises · dépense ou service public · portée large |
| Crédit d'impôt rénovation énergétique | 0 | **0** | action publique inchangée · sans effet redistributif · incitation · portée large |
| Rapport sur la fiscalité des héritages | 0 | **0** | action publique inchangée · sans effet redistributif · étude ou rapport · portée large |
| Baisse de TVA sur les produits de première nécessité | discutable | **+17** | moins d'action publique · vers les modestes · impôt ou cotisation · portée générale |
| Simplification administrative pour les PME | +25 | **+37** | moins d'action publique · sans effet redistributif · allègement de règles · portée large |
| Suppression de 100 000 postes de fonctionnaires | +50 | **+46** | moins d'action publique · sans effet redistributif · dépense ou service public · portée large |
| Assouplir le licenciement | +50 | **+53** | moins d'action publique · vers les aisés ou les entreprises · allègement de règles · portée large |
| Suppression des droits de succession | +75 | **+65** | moins d'action publique · vers les aisés ou les entreprises · impôt ou cotisation · portée large |
| Privatiser la SNCF | +75 | **+69** | moins d'action publique · sans effet redistributif · transfert au privé · portée large |
| Baisse générale et forte des charges | +75 | **+75** | moins d'action publique · vers les aisés ou les entreprises · impôt ou cotisation · portée générale |
| Privatisations massives et flat tax | +100 | **+100** | moins d'action publique · vers les aisés ou les entreprises · transfert au privé · portée générale |

20 cas, 19 valeurs différentes, tous à moins d'un repère (25 points) de l'attendu. Les écarts les plus nets : nationaliser une seule entreprise (−54 au lieu de −75, parce que la portée est très limitée) et la simplification pour les PME (+37 au lieu de +25).

## 6. Croisements rendus possibles

- **Mesures comparables** : même levier et même public, quel que soit le candidat (toutes les hausses du salaire minimum, tous les contrôles de prix, toutes les baisses d'impôts pour les entreprises). Leur portée et leur ampleur se comparent directement.
- **Méthode de gouvernement**, sans clivage gauche-droite : répartition des leviers par candidat (part d'interdictions, d'incitations, de dépense, de réformes institutionnelles, de simples déclarations). Elle vaut aussi pour les 829 propositions sans axe idéologique.
- **Qui est visé** : répartition des publics par candidat (modestes, entreprises, étrangers, auteurs d'infractions…).
- **Contrôle de cohérence** : une ancienne note eco très éloignée de la note calculée signale une mesure à relire, dans un sens ou dans l'autre.

## 7. Extension aux autres axes (plus tard, après validation sur eco)

Même schéma : une ou deux questions de sens propres à l'axe, combinées aux mêmes force, portée et ampleur, avec des poids de levier propres à chaque axe. Exemple pour l'axe société : sens « élargit les libertés et droits / neutre / renforce contrôle, sanction ou norme » ; contrôle et sanction, obligation ou interdiction pèseraient lourd, une incitation peu. Les poids de levier dépendent de l'axe : « contrôle et sanction » pèse peu en économie et beaucoup en société.

## 8. Décisions (utilisateur, 2026-11-06)

1. **Taille de l'État et redistribution restent deux questions distinctes**, avec les poids 0,75 / 0,5. Les cas où elles divergent (baisse de TVA sur les produits de première nécessité +17, subvention à l'industrie −15) sont assumés : la formule les rend explicites au lieu de les cacher dans un chiffre.
2. **Leviers ambigus : accepté, à surveiller.** Mesure du pilote : le levier change dans 2 relectures sur 30 (93 % de stabilité), entre déclaration et organisation des institutions, puis entre sanction et organisation des institutions. Pas de levier secondaire pour l'instant.
3. **`portee` remplace `rights_income`** à la généralisation : pas de doublon. `rupture` est conservée tant qu'elle sert d'ampleur du changement.
4. **Affichage : la note calculée remplace la note eco actuelle** dans l'interface. On n'affiche pas les deux, pour éviter la confusion. L'ancienne note reste dans les données (`score_details`) pour l'audit.

## 9. Pilote proposé (étape 2, payante, accord requis)

- **Échantillon** : les 60 mesures du pilote eco9 (comparaison directe) et 40 mesures d'autres thèmes (institutions, sécurité, Europe, immigration, culture) pour les descripteurs communs.
- **Double lecture** de 30 mesures pour mesurer la stabilité de chaque question.
- **Modèle** : GPT-6.1 Terra medium, en appel direct, à l'aveugle, avec un schéma JSON strict. Environ 130 lectures de 3 à 5 questions, **≈ 0,10 $**.
- **Critères de réussite** :
  - stabilité : au moins 80 % de réponses identiques par question en double lecture ;
  - moins de paliers : plus de valeurs distinctes qu'avec le barème à 9 repères, sans pic au-dessus de 20 % ;
  - accord : note calculée à moins de 25 points de la note eco9 pour au moins 75 % des mesures, et écarts relus un par un ;
  - lisibilité : explications relues sur 20 mesures.
- **Généralisation** si concluant : 3 892 propositions pour les descripteurs communs, 1 687 pour les questions de sens, de l'ordre de 1 à 2 $ en batch.

**Résultat du pilote (2026-11-06, 0,146 $)** : stabilité de 80 à 93 % ; 41 valeurs distinctes, pic à 9 % ; accord de 85 % avec le barème à 9 repères après le correctif des déclarations. Concluant.

## 10. Généralisation (préparée)

Script : [descripteurs_corpus_2027.py](descripteurs_corpus_2027.py) (tests : `test_descripteurs_corpus_2027.py`). Les cinq questions sont posées pour les 3 892 propositions en un batch OpenRouter, avec la consigne corrigée ; les 25 lectures corrigées du pilote sont réutilisées. Estimation : 155 requêtes, ≈ 1,93 $.

1. `python .\descripteurs_corpus_2027.py` : plan.
2. `python .\descripteurs_corpus_2027.py --batch-submit --max-cost 2.50` : envoi (payant, non annulable).
3. `python .\descripteurs_corpus_2027.py --batch-collect` : récupération (gratuite).
4. `python .\descripteurs_corpus_2027.py --out .\donnees_descripteurs_2027.json` : données enrichies. On y trouve `descripteurs` (levier, public visé, portée) et `axes.eco` calculé. `score_details.eco` contient l'explication, la formule et l'ancienne note (`previous_value`). L'idéologie composite et les étiquettes sont recalculées.

Restera ensuite le branchement : l'export et l'interface lisent ce fichier, la constellation affiche l'explication en mots, et la portée remplace `rights_income`, y compris dans l'étiquette « Ultra-ciblé ».


## 11. Questionnaire unifié `q1` (phase 3 du pipeline unifié)

Code : [questionnaire_2027.py](questionnaire_2027.py) (questions, formules, étiquettes) et [annotation_2027.py](annotation_2027.py) (requête à l'aveugle, cache, appel direct ou batch). Commande : `boussole_2027.py annoter`. Tests : `test_questionnaire_2027.py`.

**17 questions à choix, une seule lecture par mesure :**

| Question | Posée | Sert à |
|---|---|---|
| `levier`, `public_vise`, `portee` | toujours | force et ampleur de chaque axe ; croisements |
| `changement` (4 niveaux) | toujours | ampleur ; remplace la note `rupture` (0 / 33 / 67 / 100) |
| `precision` (chiffré / précis / orientation générale) | toujours | importance structurelle ; étiquette « Effet d'annonce » |
| `instrument`, `cout` | toujours | faisabilité, étiquettes « Licorne » et « Gouffre », ampleur |
| `faisabilite` (5 niveaux + non évaluable) | toujours | faisabilité (0 à 100) |
| `eco_etat`, `eco_distrib` | si l'axe économique s'applique | axe économique (formule du §5) |
| `soc_autorite`, `soc_libertes` | si l'axe société s'applique | axe société : sens = 0,6 × autorité + 0,6 × libertés (borné) |
| `sov_niveau` | si l'axe souveraineté s'applique | axe souveraineté |
| `ouv_sens` | si l'axe immigration s'applique | axe immigration |
| `env_sens` | si l'axe écologie s'applique | axe écologie |
| `droits_statut` (5 niveaux) | si l'accès aux droits dépend du statut | accès aux droits (0 à 100) |
| `revenus_sens` (5 niveaux) | si la mesure touche aux revenus | effet sur les revenus (−100 à 100) |

**Formule commune :** axe = 100 × sens × force du levier × ampleur. La force du levier dépend de l'axe : contrôle et sanction pèse 0,8 pour la société et 0,4 pour l'économie ; une obligation ou interdiction pèse 0,85 pour l'écologie. Les tables sont dans `FORCES`. Une déclaration prend sa force de l'ampleur du changement visé, sur tous les axes.

**Retirés :** horizon (décision du 2026-11-06) et part de la population concernée (`rights_income`, remplacée par la portée). **Calculées au lieu d'être devinées par le modèle :** les étiquettes « Licorne » (révision constitutionnelle ou traité), « Gouffre » (coût massif), « Ultra-ciblé » (portée individuelle) et « Effet d'annonce » (déclaration ou orientation générale). Les étiquettes « Censure » et « Consensus » ne sont plus produites.

**Cas types** (tests) : 12 mesures sur les cinq axes, toutes à moins de 25 points de la valeur attendue. Exemples : perpétuité réelle +62, légaliser le cannabis −60, fin du droit du sol +65, sortie de l'UE +80, défense européenne −74, interdiction des voitures thermiques +85, suppression des ZFE −60.

**Coût estimé avant pilote :** environ 0,0025 $ par mesure en appel direct (moitié en batch). Pilote de 100 mesures : environ 0,25 $ ; corpus complet en batch : environ 4,90 $.

### 11.1 Complément `soc_finalite` (2026-11-06)

Défaut constaté après le batch q1 : les deux questions de l'axe société (autorité, libertés) ne disent pas au profit de qui ni contre qui s'exerce l'autorité ; toute sanction était rangée côté « ordre » (probité des élus, lutte contre les discriminations).

Question complémentaire, posée seulement si l'axe société s'applique : **au nom de quoi la mesure agit-elle ?**

| Réponse | Effet sur l'axe société |
|---|---|
| `droits_egalite` : égalité, lutte contre les discriminations, droits des minorités (une sanction de ces atteintes compte ici) | côté libertés : sens = −min(1 ; 0,6 × autorité + 0,6 × libertés, en valeur absolue) |
| `ordre_securite` : ordre public, sécurité, répression, autorité, normes morales ou identitaires (y compris l'alourdissement des peines au nom des victimes) | formule inchangée |
| `probite_pouvoirs` : contrôle des élus, de l'administration, de la justice ou des entreprises (probité, transparence, corruption, lobbying) | axe société non applicable |
| `autre` (mœurs, vie privée, fin de vie, laïcité, expression…) | formule inchangée |

Rangée dans `questionnaire_2027.COMPLEMENTS`, hors du questionnaire principal, pour ne pas changer la clé de cache des 3 892 lectures déjà payées. Posée à part (`boussole_2027.py annoter --complement soc_finalite`) aux mesures annotées dont l'axe société s'applique, et à la suite du questionnaire principal pour les nouvelles mesures. Corrigeable dans le tableau de bord comme les autres réponses.

### 11.2 Complément `degre_rupture` (2026-11-06)

Défaut constaté : les mesures migratoires radicales étaient rabotées (suppression du droit du sol +55 contre +97 avec l'ancien barème ; Le Pen, Attal et Philippe au même niveau, +52, sur l'immigration). Le modèle répond « réforme significative » à presque toutes les mesures migratoires, et la portée « ciblée » réduit l'ampleur alors qu'une mesure migratoire vise par définition une catégorie.

Question : **degré de rupture avec le cadre juridique et les principes actuels** — `ajustement` / `notable` (durcissement ou assouplissement dans le cadre existant) / `rupture` (abolition, création ou renversement d'un principe : droit du sol, peine de mort, dépénalisation, arrêt de l'immigration, régularisation générale, préférence nationale, sortie d'une convention). Posée aux mesures dont l'axe immigration s'applique, ou l'axe société (hors probité et hors finalité jugée non applicable).

Formule, pour les axes société et immigration seulement : force = max(force du levier ; 0 / 0,7 / 1) et ampleur = 0,55 + 0,45 × (0,2 / 0,6 / 1) selon le degré ; la portée n'intervient plus. Cas types : droit du sol +100, regroupement familial durci +62, procédure accélérée +45, régularisation générale −100, peine de mort +100, recrutement de policiers +34.

### 11.3 Idéologie (axe gauche-droite général)

Composantes : économie (poids 1), société (2), souveraineté (0,5, national à droite), écologie (0,5, protection à gauche), réglables dans « Plus de réglages ». Le centre d'un candidat sur un axe combiné (idéologie, société) est la combinaison de ses centres sur chaque composante, et non plus la moyenne de ses étoiles : sinon les thèmes notés sur une seule composante, le plus souvent l'économie, l'emportaient.
