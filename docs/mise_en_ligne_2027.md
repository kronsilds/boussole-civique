# Mettre la constellation en ligne

Architecture : un VPS Debian ou Ubuntu, Caddy pour le HTTPS, et `serveur_constellation_2027.py` en service local sur le port 8000. Le pipeline, la base, les caches, `.env` et le tableau de bord restent sur le PC.

Les scripts de `deploiement/` n'ont pas encore été exécutés sur un vrai VPS : vérifier chaque étape au premier passage.

## Avant la première publication

1. Louer un VPS (1 à 2 Go de mémoire, Debian 12+, Ubuntu 24.04+ ou AlmaLinux 9+) avec un accès SSH par clé, en `root` ou avec un utilisateur autorisé à utiliser `sudo`. Sur AlmaLinux, la préparation installe Python 3.12 (le Python 3.9 du système est trop ancien), Caddy depuis le dépôt COPR du projet Caddy, et ouvre HTTP et HTTPS dans firewalld.
2. Acheter un nom de domaine et faire pointer son enregistrement DNS `A` (et `AAAA` si le VPS a une adresse IPv6) vers le VPS.
3. Ouvrir les ports 22, 80 et 443 dans le pare-feu de l'hébergeur.
4. Compléter la page **Mentions légales** de `web/constellation_2027.html` (`#mentions`) : éditeur, contact et hébergeur. Le paquet est refusé tant qu'il reste un champ « À COMPLÉTER ».

## Publier

Première fois (prépare le VPS, puis publie) :

```powershell
.\deploiement\publier.ps1 -Hote utilisateur@serveur -Domaine exemple.fr
```

Mises à jour, après `mise-a-jour` :

```powershell
.\deploiement\publier.ps1 -Hote utilisateur@serveur
```

Le script construit le paquet (`paquet_constellation_2027.py`), l'envoie et l'installe. L'installation vérifie les empreintes, redémarre le service et revient à la version précédente si le service ne répond pas. Les contributions déjà reçues ne sont pas touchées.

Le paquet contient huit fichiers : le serveur, `contributions_2027.py`, la page, l'export, l'image d'aperçu des partages, les liens des sources ajoutées, `robots.txt` et `sitemap.xml`. Il est refusé si l'export est vide ou illisible, ou si la page ou l'export contient un chemin local ou une clé.

L'image d'aperçu (`web/partage_2027.png`, 1200 × 630, balises Open Graph et Twitter de la page) se redessine avec `.\deploiement\image_partage.ps1` : champ d'étoiles décoratif aux couleurs des candidats, sans position réelle ni nom. Les réseaux sociaux gardent l'ancien aperçu en cache ; après un changement, le rafraîchir avec leur outil de débogage (Facebook : Sharing Debugger ; LinkedIn : Post Inspector).

## Référencement

- La page est servie à la racine du site, son adresse canonique (`<link rel="canonical">`). Le paquet est refusé sans cette adresse ; il en tire `robots.txt` (tout est ouvert sauf `/api/`) et `sitemap.xml` (date de l'export).
- Données structurées dans la page : `WebSite` et `Dataset` (l'export JSON est déclaré comme téléchargement, ce qui rend le jeu de données visible dans Google Dataset Search).
- Une fois en ligne : déclarer le site dans Google Search Console et Bing Webmaster Tools (validation du domaine par un enregistrement DNS TXT chez le registraire), puis y soumettre `https://<domaine>/sitemap.xml`. Le Rich Results Test de Google vérifie les données structurées.
- Limite : la constellation est une page unique, ses pages (`#methode`, `#sources`…) ne sont pas indexées séparément, et les propositions sont dessinées par JavaScript depuis l'export.

## Traiter les contributions du public

Les sources proposées et les erreurs signalées arrivent sur le VPS, alors que le tableau de bord tourne sur le PC :

```powershell
.\deploiement\synchroniser.ps1 -Hote utilisateur@serveur   # avant de traiter : récupère les nouveaux dépôts
python .\boussole_2027.py tableau-de-bord
.\deploiement\synchroniser.ps1 -Hote utilisateur@serveur   # après : renvoie les décisions
```

La fusion se rejoue sans effet. Une décision l'emporte sur « en attente ». Deux entrées différentes sous le même identifiant, ou deux décisions opposées, arrêtent la fusion sans rien écrire. Pour éviter ces conflits, ne pas déposer de contributions de test sur le PC : lancer le serveur local avec `--sans-contributions`.

Ces deux fichiers n'existent que sur le VPS et le PC : les sauvegarder avec `donnees/`.

## Ce que fait le serveur en ligne

- `--proxy` : limite les envois par visiteur d'après l'adresse transmise par Caddy, crue seulement si la connexion vient de la machine elle-même. Une adresse IPv6 compte pour son réseau /64.
- Compression gzip en mémoire (l'export passe de 23,6 à 2,1 Mo) et revalidation par `ETag` : un visiteur qui revient ne retélécharge pas un export inchangé.
- Connexions inactives coupées après 30 secondes ; en-têtes de sécurité (CSP, `nosniff`, pas de référent).
- Aucun journal d'accès, ni dans le serveur ni dans Caddy, conformément à la page Avertissement. Vérifier aussi les journaux éventuels de l'hébergeur.

## Commandes utiles sur le VPS

```sh
systemctl status boussole-constellation
journalctl -u boussole-constellation -n 50
sudo systemctl restart boussole-constellation
```
