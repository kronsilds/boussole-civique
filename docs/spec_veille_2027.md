# Veille documentaire indépendante (spec)

Objectif : ne plus dépendre du dépôt tiers `coucou123212321232123/presidentielle-2027-comparateur` (« l'amont ») pour savoir qui se présente et où lire ce que chaque candidat propose. L'amont reste une source parmi d'autres.

Principe : **un humain décide de ce qui entre dans le corpus.** La veille détecte et propose ; rien n'est ajouté sans validation. La notation reste aveugle et inchangée.

## Phase 0 : registre local (faite le 2026-11-20)

Ce que la chaîne prenait à l'amont : la liste des candidats (identité, parti, couleur, statut), les liens de programme (`program.main_url` et `thematic_links`) et les 20 thèmes. Le reste du bundle (mesures, glossaire, sondages, HATVP, budgets) ne servait pas.

- `donnees/candidats_2027.json` (versionné) : les candidats, sous la forme d'un candidat de data-v2, plus `origine` (import), `meta` (dates de l'élection, règle d'inclusion, autres déclarés), `ecarts_ecartes` et `journal` (opérations datées : import, reprise, refus).
- `donnees/themes_2027.json` (versionné) : thèmes figés. Changer un id ou un libellé invalide le cache d'extraction ; l'amont ne peut plus le faire à notre insu.
- `registre_2027.py` ; commande `boussole_2027.py registre plan [--pull] [--tout] | importer [--remplacer] | reprendre ID... [--tous-liens] | ecarter ID... [--motif M]`.
- La chaîne (`update_corpus_2027.charger_donnees`) lit le registre. L'amont devient une **veille** : à chaque run, `git pull` (sauf `--no-pull`), puis comparaison avec le registre écrite dans `donnees/veille_amont_2027.json` (ignoré) et résumée dans la console. Un échec du pull, ou l'absence du clone, n'arrête rien.
- Écarts signalés : `candidat_nouveau`, `statut`, `programme` (lien, titre, format ou date du programme principal), `lien_nouveau`, `lien_retire` (applicables par `reprendre`) ; `themes` et `candidat_absent` (signalés seulement, à traiter à la main). Identifiant d'écart stable d'un run à l'autre ; un écart écarté n'est plus signalé.
- Vérifié à l'import : candidats et thèmes identiques à la lecture de l'amont, export de la chaîne identique (12 615 propositions, aucune différence).

Conséquence : un lien ajouté par l'amont n'entre plus de lui-même dans le corpus. Il apparaît comme écart ; `registre reprendre --tous-liens` reprend d'un coup tous les liens nouveaux.

## Phase 1 : veille des sources primaires (gratuit, sans LLM)

Chaque candidat déclare ses flux dans le registre (`veille: [{type: rss|sitemap, url, filtre?}]`). Tout ce qui est détecté arrive dans une **file de tri** du tableau de bord : *Reprendre* (remplit « Ajouter un document », circuit actuel de `sources_2027.json`, où l'on peut aussi choisir un parcours), *Ignorer*.

- **Fait le 2026-11-21** (`veille_2027.py`, `boussole_2027.py veille plan|decouvrir|relever|ignorer`) : sites de campagne et de parti, flux RSS ou Atom et sitemaps (index suivis, 12 sous-sitemaps au plus) ; `decouvrir` lit les liens RSS des pages d'accueil et les sitemaps de robots.txt ; file `donnees/veille_2027.json` (ignorée par git). Premier relevé d'un flux : tout est marqué comme vu, seuls les articles RSS des 14 derniers jours entrent dans la file (la date d'un sitemap ne dit pas ce qui est nouveau). Les pages déjà sources restent surveillées par empreinte.
- Chaînes YouTube : **écartées**, le robots.txt de YouTube interdit `/feeds/videos.xml`. Piste : l'API YouTube Data officielle (clé gratuite, quota). La transcription reste un dépôt manuel.
- Interventions parlementaires des candidats élus : comptes rendus open data de l'Assemblée et du Sénat, Parlement européen (même accès officiel que `votes_2027.py`).
- Liste des candidats : révisions de la page Wikipédia des candidatures (API MediaWiki) ; à partir de février-mars 2027, parrainages publiés par le Conseil constitutionnel, puis liste officielle au Journal officiel.
- Règles de collecte : `robots.txt` respecté, débit limité, identification générique du client.
- À faire : relevé dans la chaîne hebdomadaire (`mise-a-jour --complet`), liste des candidats, interventions parlementaires.

### Candidats qui se retirent

`registre retrait ID --date AAAA-MM-JJ --source URL [--soutien ID] [--note N]` (et `--annuler`) : statut `retire` et bloc `retrait` (date, source, candidat soutenu, statut d'avant) ; la veille ne relève plus ses flux, ses mesures restent dans la base (lectures payées gardées). Seul un retrait officiel compte (annonce du candidat ou décision de son parti), pas une intention : Marine Tondelier reste candidate jusqu'au vote des adhérents des Écologistes (10 au 13 décembre 2026).

Affichage (décidé par l'utilisateur le 2026-11-21, fait) : un candidat retiré est masqué au départ dans la constellation (elle compare les candidats pour qui l'on peut voter), mais reste consultable : la légende le range sous « Candidatures retirées », un clic l'affiche avec une teinte grisée, sa fiche et l'infobulle de la légende donnent la date et le candidat soutenu, le sous-titre le compte à part. L'export reprend `status` et `retrait` (date, soutien, source) du registre à chaque export (`base_2027.statuts_du_registre`), sans attendre une intégration. Aucun transfert de mesures au candidat soutenu : un soutien n'est pas un programme ; un programme commun publié serait une source du candidat soutenu, et le rapprochement ferait le reste.

## Phase 2 : presse, métadonnées seulement

- Veille de titres et de liens (pistes : API GDELT DOC, flux de recherche d'actualités par nom), sans le texte des articles. Elle produit une liste « à lire ».
- Médias en accès libre (service public notamment) : peuvent devenir des sources après tri, comme aujourd'hui.
- Aucune aspiration automatique d'articles de presse.

### Presse lue par la BnF : circuit manuel

Les ressources de presse à distance de la BnF interdisent en général le téléchargement systématique et la fouille automatisée, et les éditeurs de presse ont largement exclu la fouille de textes. Donc :

- aucune automatisation sur la BnF (pas de script, pas de navigateur piloté, même avec la session de l'utilisateur) ;
- l'utilisateur lit, puis dépose une **fiche** depuis le tableau de bord : référence (titre, date, page) et seuls passages où le candidat formule une proposition ;
- seuls ces passages vont au modèle d'extraction, jamais l'article entier ;
- à l'export : la référence et une citation courte (droit de citation), sans lien vers le texte ni texte intégral ; la fiche reste dans un fichier non versionné, hors du paquet publié ;
- conditions de la ressource précise à vérifier par l'utilisateur.

## Phase 3 (option) : pré-tri par LLM

Question du type « cette page contient-elle des propositions ? », plafonnée, désactivée par défaut.

## Décisions de l'utilisateur (2026-11-21)

1. **Déclarations et entretiens traités comme les autres sources** : même extraction, et le rapprochement trie (une proposition déjà dans le programme devient une reprise, une nouvelle entre comme mesure). Pas de rôle à part ni de poids distinct. Rien à changer dans le code : c'est déjà le circuit des sources ajoutées (`tribune`, `video_transcription`…).
2. **Règle d'inclusion : les candidats qui ont un programme.** Précisée par l'utilisateur : **un programme écrit pour l'élection de 2027, pas celui d'une élection passée** (publié par la campagne ou le parti soutien, accessible au public ; des entretiens seuls ne suffisent pas) ; citer 2027 n'est qu'un indice. Recherche du 2026-11-21 : Branco, Philippot, Egger, Kazib et Cazeneuve (« Lettre aux Français » de juillet 2026, sans « 2027 », retenue) entrent au registre le même jour (`registre ajouter`, `origine: registre`) ; leurs documents seront collectés, extraits et lus au prochain run plafonné. Détail dans `programme_recherche` de leur fiche et le [suivi 10](suivi/10_2026-11-20_veille_independante.md). Conséquences :
   - Bertrand (programme « en cours d'élaboration », aucun document) reste au registre sans figurer dans la constellation, comme aujourd'hui ;
   - les 14 autres déclarés encore listés dans `meta.other_declared` (Asselineau, Batho, Polony, Riner…) entrent dès qu'un programme est trouvé (`registre ajouter FICHES.json`) : la phase 1 doit les chercher. Coût indicatif par candidat entrant : extraction environ 0,004 $ par morceau, lecture q2 environ 0,002 $ par mesure, soit environ 1 à 2 $ pour 500 mesures ; plus de candidats rend aussi la constellation plus chargée ;
   - la règle de l'amont (candidats testés dans les sondages) n'est plus suivie ; `meta.inclusion_rule` du registre a été réécrite le 2026-11-21.
3. **Ressource BnF : Europresse** (Cision). Ses conditions publiques n'ont pas été trouvées ; une bibliothèque universitaire indique que son contrat interdit la fouille de textes et le téléchargement massif. Le circuit manuel ci-dessus s'applique donc tel quel : lecture humaine, fiche avec référence et passages choisis, jamais d'article entier transmis au modèle ni publié.
