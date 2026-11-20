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

Chaque candidat déclare ses flux dans le registre (champ à ajouter, par exemple `veille: [{type, url}]`). Tout ce qui est détecté arrive dans une **file de tri** du tableau de bord : *Ajouter comme source* (circuit actuel de `sources_2027.json`), *Suivre* (parcours), *Ignorer*.

- Sites de campagne et de parti : `sitemap.xml` (`lastmod`) et flux RSS ou Atom ; les pages déjà sources sont déjà surveillées par empreinte.
- Chaînes YouTube : flux RSS public par chaîne (`/feeds/videos.xml?channel_id=`), sans clé. La transcription reste un dépôt manuel.
- Interventions parlementaires des candidats élus : comptes rendus open data de l'Assemblée et du Sénat, Parlement européen (même accès officiel que `votes_2027.py`).
- Liste des candidats : révisions de la page Wikipédia des candidatures (API MediaWiki) ; à partir de février-mars 2027, parrainages publiés par le Conseil constitutionnel, puis liste officielle au Journal officiel.
- Règles de collecte : `robots.txt` respecté, débit limité, identification générique du client.

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

## Décisions ouvertes

1. Poids des déclarations et entretiens : comme le programme, ou rôle `declaration` distinct (badge, compté comme reprise s'il rejoint une mesure du programme) ?
2. Règle d'inclusion des candidats : celle de l'amont (déclarés ou probables testés dans les sondages) ou une règle propre ?
3. Ressource BnF utilisée (Europresse, PressReader ou autre), pour en lire les conditions.
