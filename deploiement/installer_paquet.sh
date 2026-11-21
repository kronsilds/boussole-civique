#!/bin/sh
# Installe un paquet sur le VPS (root) : verifie les empreintes, remplace les fichiers, redemarre, revient en arriere si le
# service ne repond pas. Les contributions et signalements de donnees/ ne sont jamais touches.
set -eu

ARCHIVE=${1:?Usage : boussole-installer paquet.tgz}
RACINE=/srv/boussole
SERVICE=boussole-constellation
FICHIERS="serveur_constellation_2027.py contributions_2027.py web/constellation_2027.html donnees/donnees_interface_2027.json donnees/sources_2027.json"

ARRIVEE=$(mktemp -d "$RACINE/.arrivee.XXXXXX")
PRECEDENT=$(mktemp -d "$RACINE/.precedent.XXXXXX")
trap 'rm -rf "$ARRIVEE" "$PRECEDENT"' EXIT

tar -xzf "$ARCHIVE" -C "$ARRIVEE" --no-same-owner
(cd "$ARRIVEE" && sha256sum --check --quiet --strict SHA256SUMS)

repond() {
  /usr/local/bin/boussole-python - <<'FIN'
import time, urllib.request
for _ in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/web/constellation_2027.html", timeout=3).read()
        raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(1)
FIN
}

for f in $FICHIERS; do
  [ -f "$ARRIVEE/$f" ] || { echo "Paquet incomplet : $f" >&2; exit 2; }
  if [ -f "$RACINE/$f" ]; then
    mkdir -p "$PRECEDENT/$(dirname "$f")"
    cp -p "$RACINE/$f" "$PRECEDENT/$f"
  fi
done

for f in $FICHIERS; do
  chown root:root "$ARRIVEE/$f"
  chmod 644 "$ARRIVEE/$f"
  mv -f "$ARRIVEE/$f" "$RACINE/$f"
done

systemctl restart "$SERVICE"
if repond; then
  echo "Paquet installe, service en ligne."
  exit 0
fi

echo "Le service ne repond pas : retour a la version precedente." >&2
for f in $FICHIERS; do
  if [ -f "$PRECEDENT/$f" ]; then mv -f "$PRECEDENT/$f" "$RACINE/$f"; fi
done
systemctl restart "$SERVICE" || true
exit 1
