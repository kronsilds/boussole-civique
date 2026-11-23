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
  - ~~les options « indéterminé » existent déjà~~ : erreur corrigée le 2026-11-23. L'option existait en q1 ; le q2 l'a remplacée par les conditions oui/non, et une mesure aux effets opposés reçoit le niveau du milieu. La critique est donc juste sur ce point (voir [spec v8](../spec_q2_v8_2027.md), B3).
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

## 2026-11-22 : suites gratuites dans la constellation (commit a1d2c2b)

- Fiche d'un candidat : part de propositions sans position (et moyenne des candidats), part lue avec l'ancienne rédaction (v5), « Écologie et revenus » à partir de 5 cas, dispersion sur les axes affichés, étendue du gauche – droite selon cinq lectures des poids (lectures fragiles exclues).
- Réglages : cinq lectures toutes faites des poids du gauche – droite.
- Coulisses : degré compté deux fois (§ 4), tableau des rangs selon les poids (§ 5), propositions sans position, choix sur la démocratie directe et « qui paie la transition » (§ 7).

## 2026-11-23 : liste des changements d'une v8, à arbitrer

Rédigée dans [docs/spec_q2_v8_2027.md](../spec_q2_v8_2027.md), avec les volumes comptés sur la base du jour (12 634 mesures lues en q2). Rien n'est écrit dans le code.

- **Recommandés** :
  - condition « société » élargie à la doctrine de la police et aux règles de la vie en ligne (154 mesures sur la police et 52 sur les plateformes sans note société) ; seule `a_soc` est à relire, les réponses « Autorité » et « Libertés » sont déjà en cache ;
  - question nouvelle sur le domaine institutionnel (décompte et indicateurs décentralisation et mode de scrutin, pas d'axe) ;
  - question nouvelle sur le statut des ménages touchés (1 067 mesures avec un profil de revenu).
- **Facultatif** : multilatéralisme en indicateur (164 mesures, dont 68 sans aucun axe et 72 déjà sur Europe ou nation).
- **Déconseillés** :
  - petites entreprises séparées des ménages aisés (environ 50 mesures sur 438, pour une relecture de `eco_transfert` sur environ 5 500) ;
  - option « effets contradictoires » (365 notes à 0 au plus, environ 3 %).
- **Sans relecture, plus tard** :
  - poids des déclarations, le plus grand biais de forme mesuré (42 % des mesures ; de 25 % chez Branco à 74 % chez Arthaud ; vérifier d'abord `a_dispositif` sur la relecture humaine) ;
  - degré compté deux fois ;
  - plafond de l'économie ;
  - portée sur les autres axes ;
  - faisabilité à renommer « obstacle juridique ».
- **Coût** : questions v8 lues dans la même passe ciblée que la relecture v5 → v7, environ 25 à 30 $ en bornes prudentes (21 $ pour la seule relecture v5 → v7). Il faut figer les textes v7, comme ceux de la v5, pour garder les 1 844 lectures v7.
- Script des comptages, hors dépôt : `chiffres_v8.py` (dossier temporaire de la session).

### Décisions du 2026-11-23 et suites gratuites

- L'utilisateur retient les recommandations de la note v8 :
  - A1 (condition société, effectifs de la police hors de l'axe), A2 (domaine institutionnel) et A3 (statut des ménages) sont retenus ;
  - B1 (multilatéralisme) est retenu en indicateur, puisque la passe a la place (15 questions sur 16) ;
  - B2 et B3 sont écartés.
- Coulisses, § 7 : deux limites ajoutées.
  - « Qui gagne, qui paie » met les entreprises dans un seul camp.
  - Effets opposés et absence d'effet se confondent. La part des positions à 0 est recalculée depuis l'export : 4 % (369 sur 10 484), 25 % en défense et 20 % en alliances.
- « Faisabilité » devient « Obstacle juridique » :
  - dans la constellation : titre de l'axe, pôles « Obstacle majeur » et « Aucun obstacle », niveaux de « Majeur » à « Aucun », pages Méthode et Coulisses avec la mention de l'ancien nom ;
  - dans le libellé de `feasibility_q2` de l'export.

  Le champ `feasibility` et l'échelle ne changent pas : 0 pour une révision de la Constitution, 100 pour un décret.
- Vérifié : 359 tests OK ; page servie en local, aucune erreur console, menus et textes à jour. Le libellé de l'export ne sera pris en compte qu'au prochain export.

## 2026-11-23 : revue critique d'Opus, triée et suivie

L'utilisateur a fourni une revue critique d'Opus (document Claude Docs) et son script de vérification `verifier_constellation.py` (bibliothèque standard seulement, lit l'export, n'écrit rien). La revue porte sur le commit 65e9ae5 du 22 novembre, donc avant 7d9ac31, 01f68d0, a9198a2, a7957c1 et a1d2c2b, et sur l'export du 22 novembre à 19 h 57 UTC, le même que l'export local.

- **Le script reproduit tous les chiffres de la revue.** Il s'arrête sur la console Windows à la section 4 (caractère « − ») ; il passe avec `python -X utf8`.
- **Juste et vérifié** :
  - validation : 37 étalons écrits par une IA et non validés, un seul relecteur, arbitre pas meilleur que drex-max seul sur les cas relus, degré disputé dans 13,3 % des mesures, portée et classes de revenu faibles sur les cas disputés (chiffres de nos notes, [09](09_2026-11-10_11_questionnaire_q2.md)) ;
  - état publié : 86 % des mesures lues en v5, 68 % « non relue » ;
  - cas types retrouvés avec la formule du code : une cantine gratuite pour tous vaut −32, la même aide réservée aux modestes −56 ; en société, une déclaration vaut 10 en ajustement et 85 en rupture ;
  - axes mêlés :
    - société : 366 notes côté ordre, dont 142 hors du thème sécurité (protections, identité, devoirs civiques) ;
    - contre-pouvoirs : 36 % des notes portent sur les collectivités (repérage par mots-clés) ;
    - Europe ou nation : les accords commerciaux sont dans le « oui » de `a_sov`, environ 83 notes ;
  - axes à sens unique : environnement 85 % contre 6 %, contre-pouvoirs 67 % contre 16 %, défense 32 % contre 6 % ;
  - Le Pen (+37) est moins du côté de l'ordre qu'Attal (+42), Philippe (+51) et Retailleau (+52) ;
  - revenus : les cinq classes pèsent pareil, alors qu'elles couvrent 30, 30, 30, 9 et 1 % des ménages ;
  - H1 réfutée par la revue elle-même : les déclarations tassent les centres vers le milieu, surtout à gauche, sauf Philippe (+8, et +25 sans les déclarations).
- **Faux, dépassé ou nuancé** :
  - la carte est déjà en deux dimensions par défaut (économie × société) ;
  - la sensibilité aux poids est publiée depuis a1d2c2b ; celle aux constantes manque toujours ;
  - l'identité n'est pas absente : les interdictions identitaires sont notées « ordre ». Seule l'identité sans contrainte manque ;
  - la politique de filière comptée « plus d'État » n'est pas un biais : l'axe mesure l'intervention ;
  - la limite du masquage était déjà dans Coulisses, mais la page Méthode la contredisait (« ne peut pas corriger ») ;
  - régler les poids sur Chapel Hill rendrait la comparaison circulaire : c'est notre seul contrôle externe ;
  - la fréquence nette vaut le centre (0,91 contre 0,90 sur 8 candidats), elle ne fait pas mieux : on l'affiche en complément.
- **Décisions de l'utilisateur (« Oui, applique-les », mes recommandations)** :
  - v8 ([spec](../spec_q2_v8_2027.md)) :
    - A4 (`soc_domaine`) et A5 (`sov_objet`) remplacent le multilatéralisme ; la passe compte 15 questions sur 16 ;
    - agriculteurs séparés des indépendants dans A3 ;
    - chiffres de la revue ajoutés à C1 ;
    - variantes C7 à C9 (société par domaine, Europe sans le commerce, contre-pouvoirs sans la décentralisation), à décider après la relecture.
  - Constellation, fait le même jour :
    - Méthode : la phrase sur la lecture à l'aveugle dit que le masquage retire le nom, pas le contenu, et qu'aucun test ne mesure encore cet effet ; Coulisses le dit aussi ;
    - Coulisses, § 7 : quatre limites ajoutées (milieu des axes proche de la politique actuelle ; aide ciblée notée plus à gauche que l'aide universelle ; axe des libertés mêlé, part recalculée depuis l'export, 39 % soit 142 sur 366 ; commerce dans Europe ou nation). Part des collectivités dans les contre-pouvoirs ajoutée ; déséquilibre des trois axes à sens unique recalculé depuis l'export ;
    - fiche d'un candidat : fréquence nette de l'environnement, de la défense et des contre-pouvoirs, pour 1 000 propositions, avec la moyenne des candidats. Exemple : Tondelier, environnement +196 (moyenne +72) ;
    - les trois dimensions de revenu sont marquées « expérimental » dans les menus et à côté des curseurs, avec la raison au survol.
  - À décider plus tard :
    - sensibilité aux constantes (recalcul gratuit) ;
    - seuil de fiabilité de 10 notes (la défense de Le Pen compte comme fiable avec 10 notes) ;
    - référence humaine indépendante : 2 ou 3 codeurs, environ 300 mesures, alpha de Krippendorff ;
    - test de la lecture à l'aveugle par fausse attribution (payant).
- Vérifié : 359 tests OK ; page servie en local (configuration `boussole-verif`, port 8010), aucune erreur console. Les chiffres affichés retrouvent ceux du script.

## 2026-11-23 au soir : publication et fusion de la relecture

- Mise à jour gratuite (`mise-a-jour`) : aucune mesure ajoutée, retirée ou modifiée (12 492 propositions). Page vérifiée en local, puis publiée sur le VPS (`publier.ps1 -Hote root@atlas`) à 22 h 16 ; le site sert la nouvelle page (limites, fréquence nette, revenus expérimentaux, « Obstacle juridique »). Sous PowerShell 5.1, le message « Connection closed » de ssh fait échouer le script alors que l'installation a réussi : vérifier le site plutôt que le code de sortie.
- Aperçu des partages (balises Open Graph et Twitter, `web/partage_2027.png`) et installateur livré avec chaque paquet : commit 79d1d84.
- Branche de relecture humaine tirée au hasard (`claude/gracious-grothendieck-481bcb`) fusionnée : commit 3294eef. Conflit dans `web/constellation_2027.html` résolu en gardant les deux côtés (limites du § 7 et tableau de sensibilité ; emplacement des taux de la relecture). La limite « Relecture humaine partielle » distingue désormais le relecteur unique des désaccords de l'échantillon tiré au hasard, relu à deux (chaque fiche par une seule personne). 371 tests OK, page sans erreur console.
- La page de relecture (artifact) n'est pas touchée par la fusion : ses fichiers et ses réponses vivent dans l'artifact. Republication de la constellation repoussée après la relecture, à la demande de l'utilisateur. Branche `pipeline-unifie` poussée sur `origin`.

## 2026-11-23 : review DeepSeek, triée

Conversation partagée (chat.deepseek.com) : analyse critique du dépôt et du site. DeepSeek n'a lu qu'une partie de `questionnaire_q2_2027.py` (« le fichier se termine brusquement ») ; plusieurs manques signalés existent déjà.

- **Juste, déjà traité ou prévu** : axe société composite (A4 de la v8, limite dans Coulisses) ; commerce et politique industrielle (A5 ; une aide à une filière compte sur « règles et propriété ») ; validation humaine (relecture de 120 fiches tirées au hasard, en cours) ; robustesse (sensibilité aux poids publiée en a1d2c2b, deux lecteurs comparés ; constantes à décider) ; attraction vers le centre et biais des modèles (Coulisses, chiffres de la revue d'Opus).
- **Faux ou dépassé** :
  - démocratie participative « noyée » : `inst_direct` est une question à part, comptée en fréquence, hors contre-pouvoirs ;
  - genre et discriminations « absents » : `soc_egalite` (protection contre les discriminations) existe ;
  - dette et financement : `financement` dit si la mesure est non financée, évoquée ou désignée ; une trajectoire de déficit se juge sur un programme, pas sur une phrase ;
  - méthode écologique : `levier` distingue interdiction, incitation, investissement ; nucléaire ou renouvelables écarté dans la v8 (étiquette de domaine) ;
  - axes territoire, genre, position sociale : examinés et écartés dans la v8, motifs écrits ;
  - éducation, santé, culture : des thèmes, pas des clivages ; leurs mesures sont placées sur les axes ;
  - importance qui favoriserait les programmes longs : note de 0 à 100 par proposition (`importance_structurelle`), qui ne pèse qu'à l'intérieur d'un programme ; les redites (20 %) sont un signal voulu ;
  - consignes à publier : questionnaire q2 complet en annexe des Coulisses, code public.
- **Seule idée neuve** : test de reformulation (même question, autres mots ; payant), ajouté à « à décider plus tard » avec le test d'attribution fictive. Aucun changement à la v8 ni au site.

