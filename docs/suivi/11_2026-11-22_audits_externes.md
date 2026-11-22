# Suivi : audits externes du site et vérifications du questionnaire q2 (à partir du 2026-11-22)

> Sous-fichier de [SUIVI_PROJET.md](../../SUIVI_PROJET.md) (sommaire et état courant). Précédent : [10](10_2026-11-20_veille_independante.md)

## 2026-11-22 : audits du site par des modèles d'IA

L'utilisateur a soumis le site en ligne (https://atlasdesprogrammes.fr) à plusieurs modèles d'IA : deux analyses ChatGPT et quatre analyses Mammouth. Chacune a été triée ainsi : ce qui est juste, ce qui est faux, ce qui est à faire.

- **Lectures erronées, venues d'une page peu claire, corrigées** (commit 7d9ac31) :
  - le poids 2 de « Société » dans le gauche-droite est expliqué : chacun des deux axes qu'elle réunit pèse 1, autant que l'économie ;
  - le 64e désaccord du comparatif drex-max / Terra est compté (aucun des deux n'avait raison) ;
  - les noms des modèles sont lisibles sans JavaScript ;
  - un lien vers le fichier JSON publié est ajouté dans les références de Coulisses.
- **En-tête de la note q2 mis à jour** (commit 01f68d0) : la note dit que q2 est en production depuis le 2026-11-16.
- **Relecture humaine sur un échantillon aléatoire** confiée à une session séparée : page de saisie de 120 fiches publiée en artifact privé, sur la branche `claude/gracious-grothendieck-481bcb`. Cette branche n'est pas fusionnée et touche aussi `web/constellation_2027.html`.
- **Points récurrents non traités** : « faisabilité » à renommer « obstacle juridique » (proposé par trois audits) ; aucune proposition validée par un humain (`lec.val`) dans l'export.

## 2026-11-22 : critique du questionnaire q2 (ChatGPT) et deux vérifications gratuites

### Ce que dit la critique

- **Confirmé dans le code (`questionnaire_q2_2027.py`)** :
  - **Le degré compte deux fois.** Il fixe une force minimale (`DEGRE_FORCE` dans `force`) et entre aussi dans l'ampleur (`DEGRE_AMPLEUR`). Passer d'« ajustement » à « rupture » multiplie donc une position par environ 3,9 pour une incitation (force 0,4), mais par 1,56 seulement pour une nationalisation.
  - **La portée ne joue que sur l'économie et l'écologie**, et la tranche « ciblée » va de 10 000 à un million de personnes.
  - **Société additionne autorité et libertés** (0,8 chacune). La protection contre les discriminations n'est qu'un indicateur de fréquence.
- **Faux ou déjà traité** :
  - il n'y a pas de mélange entre q1 et q2 : toute la base est en q2, en deux rédactions (v5 et v7, signalées au § 7 de Coulisses) ;
  - le poids 2 de « Société » est le même malentendu, lu cette fois dans la note q2 ;
  - les options « indéterminé » existent déjà.
- **Axes proposés** : une matrice d'incidence sociale (patrimoine, statut, génération, territoire), un axe institutions découpé, le multilatéralisme, la justice sociale de la transition, le numérique, un « q3 ». Ce sont des décisions de l'utilisateur. Toute question nouvelle change la clé du cache et oblige à relire tout le corpus (environ 20 $).

### Vérification 1 : positions sans double comptage du degré

Méthode, gratuite :
- recalcul de toutes les positions depuis les réponses de la base (`base_2027.calculer`, avec `Q2.force` ou `Q2.ampleur` remplacés) ;
- copie de l'export avec les valeurs recalculées ;
- centres des candidats relus par la constellation elle-même, servie depuis un dossier temporaire isolé ;
- le calcul de référence retrouve 95 % des valeurs publiées ; les autres sont des lignes « en révision » ou en attente, laissées telles quelles.

Variantes :
- **A** : le degré ne fixe plus de force minimale ; il ne compte que dans l'ampleur ;
- **B** : le degré garde la force minimale mais sort de l'ampleur ; l'ampleur ne garde que la portée en économie et en écologie, et vaut 1 ailleurs.

**Résultat : l'ordre des candidats tient.**
- Gauche-droite : corrélation de rang de Spearman 0,986 (A) et 0,998 (B) avec le calcul actuel ; 3 places de déplacement au plus (A), 1 place (B).
- Axes simples : corrélation entre 0,95 (contre-pouvoirs, A) et 1.

Ce qui change, c'est l'étirement des extrêmes, dont les mesures sont plus souvent des ruptures :

| Axe | Candidat | Actuel | A | B |
|---|---|---|---|---|
| Gauche-droite | Zemmour | 47,6 | 37,8 | 54 |
| Souveraineté | Dupont-Aignan | 75,9 | 51 | 81,4 |
| Souveraineté | Philippot | 75,1 | 54,3 | 82,3 |
| Immigration | Arthaud | −95,1 | −71,6 | −95,1 |

Moyenne des positions en valeur absolue, mesure par mesure : la variante A les baisse de 2 à 9 points selon l'axe, la variante B les monte de 1 à 11 points.

**À décider** : garder la formule et l'expliquer dans Coulisses, ou adopter une variante. Une variante se recalcule gratuitement, sans rien relire.

### Vérification 2 : les propositions sans axe

**3 705 propositions sur 12 492 (30 %) n'ont de position sur aucun axe.** Par thème : culture 70 %, institutions 58 %, sécurité 47 %, outre-mer 45 %, éducation 44 %, numérique 41 %, international 39 %, santé 24 %.

Ce qui les a exclues, d'après les réponses de la base (une proposition peut avoir plusieurs motifs) :

| Motif | Propositions |
|---|---|
| aucune condition de bloc remplie | 1 906 |
| bloc économie ouvert, mais trois réponses « au milieu » | 1 337 |
| institutions sans effet sur les contre-pouvoirs : contrôle inchangé (dont le RIC), probité, contenu encore à écrire | environ 400 |

Côté levier : 1 800 sont des déclarations sans dispositif.

Relecture d'un échantillon aléatoire de 60 propositions (graine 20261122) :
- **environ 47 sont légitimement sans axe** : déclarations vagues, organisation de l'administration, procédure, simplification ;
- **5 sont des oublis nets** (environ 8 %, soit environ 300 propositions si on extrapole ; intervalle large, de 3 à 18 %) :
  - pauses obligatoires sans perte de salaire en cas de canicule (économie) ;
  - fin des inégalités entre régimes de retraite (économie) ;
  - loi d'urgence pour construire des centres de rétention (immigration) ;
  - coopération « indépendante du bloc euro-atlantique » (alliances) ;
  - consultation libre sans parcours de soins (économie) ;
- **environ 8 sont des cas limites** : hébergement sous juridiction européenne, cour d'assises avec jurys populaires, allègement des contrôles agricoles, critères non académiques des concours, entre autres.

Deux limites tiennent aux règles elles-mêmes, pas aux lecteurs :
- **La condition « société » (`a_soc`) écarte par principe « les moyens ou l'organisation de la police ».** Pour cette raison, « démanteler BAC et BRAV-M » et « recruter 30 000 policiers » n'ont aucun axe. La règle est probablement trop large pour la doctrine de maintien de l'ordre.
- **Aucun axe ne mesure le territoire** : délocalisation d'administrations, commerces dans les villages.

**À décider** :
- publier le taux de propositions sans axe dans Coulisses, avec cette explication (gratuit) ;
- resserrer `a_soc` pour les pouvoirs de la police, ou ajouter un axe territoire : questions nouvelles, donc relecture payante.

Scripts de la vérification (hors dépôt, dossier temporaire de la session) : `variantes.py` et `sans_axe.py`. Rien n'a été modifié dans la base ni dans l'export.
