#!/bin/sh
# Premiere installation sur un VPS Debian ou Ubuntu, en root : sh preparer_vps.sh exemple.fr
# Relancer le script est sans danger. Le service demarre au premier envoi du paquet (publier.ps1).
set -eu

DOMAINE=${1:?Usage : preparer_vps.sh exemple.fr}
printf '%s' "$DOMAINE" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' \
  || { echo "Nom de domaine invalide : $DOMAINE" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "A lancer en root." >&2; exit 2; }
ICI=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

apt-get update
apt-get install -y python3 caddy

id boussole >/dev/null 2>&1 || useradd --system --home-dir /srv/boussole --shell /usr/sbin/nologin boussole
install -d -o root -g root -m 755 /srv/boussole /srv/boussole/web
install -d -o boussole -g boussole -m 755 /srv/boussole/donnees

install -o root -g root -m 755 "$ICI/installer_paquet.sh" /usr/local/sbin/boussole-installer
install -o root -g root -m 644 "$ICI/boussole-constellation.service" /etc/systemd/system/boussole-constellation.service
sed "s/__DOMAINE__/$DOMAINE/g" "$ICI/Caddyfile.modele" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

systemctl daemon-reload
systemctl enable boussole-constellation
systemctl enable caddy
systemctl reload-or-restart caddy
echo "VPS pret pour $DOMAINE. Envoyer maintenant le paquet avec publier.ps1."
