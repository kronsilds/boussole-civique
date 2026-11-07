"""Serveur de la constellation : publie seulement la page et l'export, rien d'autre du dossier.

  python .\\serveur_constellation_2027.py            # http://127.0.0.1:8000/
  python .\\serveur_constellation_2027.py --reseau   # aussi depuis le telephone (meme reseau)

Remplace « python -m http.server », qui publiait tout le dossier (.env, journaux, base, caches). Lecture seule :
la page web/constellation_2027.html et donnees/donnees_interface_2027.json ; toute autre adresse repond 404.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PAGE = "/web/constellation_2027.html"
FICHIERS = {  # adresse publiee -> (chemin relatif a la racine, type)
    PAGE: ("web/constellation_2027.html", "text/html; charset=utf-8"),
    "/donnees/donnees_interface_2027.json": ("donnees/donnees_interface_2027.json", "application/json; charset=utf-8"),
}


def fabriquer_handler(racine: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Boussole/1"

        def log_message(self, fmt, *args):  # journal discret
            pass

        def _servir(self, corps: bool) -> None:
            chemin = urlparse(self.path).path
            if chemin in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", PAGE)
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if chemin not in FICHIERS or not (racine / FICHIERS[chemin][0]).is_file():
                data = b"Introuvable."
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if corps:
                    self.wfile.write(data)
                return
            fichier, type_ = FICHIERS[chemin]
            data = (racine / fichier).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")  # export regenere a chaque run
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if corps:
                self.wfile.write(data)

        def do_GET(self):
            self._servir(True)

        def do_HEAD(self):
            self._servir(False)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", default=".")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reseau", action="store_true", help="Ecoute aussi sur le reseau local (lecture seule)")
    args = parser.parse_args()
    racine = Path(args.racine)
    try:
        serveur = ThreadingHTTPServer(("0.0.0.0" if args.reseau else "127.0.0.1", args.port), fabriquer_handler(racine))
    except OSError as exc:
        print(f"Erreur serveur constellation : {exc}")
        return 2
    print(f"Constellation : http://127.0.0.1:{args.port}/  (Ctrl+C pour arreter)", flush=True)
    if args.reseau:
        from tableau_de_bord_2027 import adresses_reseau
        for ip in adresses_reseau():
            print(f"  sur le reseau : http://{ip}:{args.port}/", flush=True)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
