#!/bin/sh
# Premiere installation sur un VPS Debian, Ubuntu ou AlmaLinux/Rocky 9+, en root : sh preparer_vps.sh exemple.fr
# Relancer le script est sans danger. Le service demarre au premier envoi du paquet (publier.ps1).
set -eu

DOMAINE=${1:?Usage : preparer_vps.sh exemple.fr}
printf '%s' "$DOMAINE" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' \
  || { echo "Nom de domaine invalide : $DOMAINE" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "A lancer en root." >&2; exit 2; }
ICI=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 caddy tar
  PYTHON=$(command -v python3)
elif command -v dnf >/dev/null 2>&1; then
  # AlmaLinux 9 : python3 y est en 3.9, le serveur demande 3.10+ ; Caddy vient du depot COPR officiel du projet Caddy.
  dnf install -y 'dnf-command(copr)' python3.12 tar
  dnf copr enable -y @caddy/caddy
  dnf install -y caddy
  PYTHON=$(command -v python3.12)
else
  echo "Systeme non pris en charge (ni apt-get ni dnf)." >&2; exit 2
fi
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' \
  || { echo "Python 3.10 ou plus recent requis ($PYTHON)." >&2; exit 2; }
ln -sf "$PYTHON" /usr/local/bin/boussole-python

id boussole >/dev/null 2>&1 || useradd --system --home-dir /srv/boussole --shell /usr/sbin/nologin boussole
install -d -o root -g root -m 755 /srv/boussole /srv/boussole/web
install -d -o boussole -g boussole -m 755 /srv/boussole/donnees

install -o root -g root -m 755 "$ICI/installer_paquet.sh" /usr/local/sbin/boussole-installer
install -o root -g root -m 644 "$ICI/boussole-constellation.service" /etc/systemd/system/boussole-constellation.service
install -d -m 755 /etc/caddy
sed "s/__DOMAINE__/$DOMAINE/g" "$ICI/Caddyfile.modele" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

# Pare-feu local (AlmaLinux) : HTTP et HTTPS pour Caddy. Le pare-feu de l'hebergeur reste a ouvrir dans son espace client.
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=http --add-service=https
  firewall-cmd --reload
fi
# SELinux : autorise un Caddy confine a joindre le serveur local (sans effet si Caddy ne l'est pas).
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
  setsebool -P httpd_can_network_connect 1
fi

systemctl daemon-reload
systemctl enable boussole-constellation
systemctl enable caddy
systemctl reload-or-restart caddy
echo "VPS pret pour $DOMAINE. Envoyer maintenant le paquet avec publier.ps1."
