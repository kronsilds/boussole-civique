"""Serveur de la constellation : publie seulement la page et l'export ; recoit les sources et erreurs signalees par le public.

  python .\\serveur_constellation_2027.py                         # http://127.0.0.1:8000/
  python .\\serveur_constellation_2027.py --reseau                # aussi depuis le telephone (meme reseau)
  python .\\serveur_constellation_2027.py --sans-contributions    # lecture seule stricte

Remplace « python -m http.server », qui publiait tout le dossier (.env, journaux, base, caches). En lecture : la page
web/constellation_2027.html et donnees/donnees_interface_2027.json ; toute autre adresse repond 404.
Seules ecritures (fermees par --sans-contributions) :
- POST /api/contribution (page « Contribuer ») ajoute un lien a donnees/contributions_2027.json, a valider dans l'onglet
  Sources du tableau de bord ; aucun lien propose n'est ouvert par le serveur ;
- POST /api/signalement (fiche d'une proposition) ajoute une erreur signalee a donnees/signalements_2027.json, a traiter
  dans l'onglet Signalements du tableau de bord.
Aucune donnee personnelle gardee (l'adresse IP ne sert qu'a limiter le debit, en memoire).
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import contributions_2027 as CT

PAGE = "/web/constellation_2027.html"
EXPORT = "donnees/donnees_interface_2027.json"
FICHIERS = {  # adresse publiee -> (chemin relatif a la racine, type)
    PAGE: ("web/constellation_2027.html", "text/html; charset=utf-8"),
    "/donnees/donnees_interface_2027.json": (EXPORT, "application/json; charset=utf-8"),
}
CONTRIBUTIONS = "donnees/contributions_2027.json"
SIGNALEMENTS = "donnees/signalements_2027.json"
SOURCES = "donnees/sources_2027.json"
TAILLE_MAX = 8 * 1024
DEBIT = {"source": ((600, 5), (86400, 20)),          # (fenetre en secondes, depots au plus) par adresse
         "signalement": ((600, 10), (86400, 40))}


class Contributions:
    """Validation et enregistrement des liens proposes et des erreurs signalees ; candidats, liens connus et
    propositions publiees lus dans l'export et les ajouts (relus seulement quand ces fichiers changent)."""

    def __init__(self, racine: Path):
        self.racine = racine
        self.verrou = threading.Lock()
        self.depots: dict[tuple[str, str], deque[float]] = {}
        self._cache: tuple[tuple[float, float], set[str], set[str], dict[str, dict]] | None = None

    def _connus(self) -> tuple[set[str], set[str], dict[str, dict]]:
        export, sources = self.racine / EXPORT, self.racine / SOURCES
        cle = tuple(f.stat().st_mtime if f.exists() else 0.0 for f in (export, sources))
        if not self._cache or self._cache[0] != cle:
            data = CT.B.lire_json(export, {}) or {}
            ajouts = (CT.B.lire_json(sources, {}) or {}).get("ajouts") or []
            liens = {CT.normaliser_url(u) for u in [*(s.get("url") for s in data.get("sources") or []),
                                                    *(a.get("url") for a in ajouts)] if u}
            props = {r["id"]: {k: r.get(k) for k in ("title", "c", "maj", "v")} for r in data.get("proposals") or []}
            self._cache = (cle, {c["id"] for c in data.get("candidates") or []}, liens, props)
        return self._cache[1], self._cache[2], self._cache[3]

    def _debit(self, genre: str, adresse: str) -> deque[float]:
        maintenant, regles = time.monotonic(), DEBIT[genre]
        file = self.depots.setdefault((genre, adresse), deque())
        while file and maintenant - file[0] > regles[-1][0]:
            file.popleft()
        for fenetre, maxi in regles:
            if sum(maintenant - t <= fenetre for t in file) >= maxi:
                raise PermissionError("Trop d'envois depuis cette connexion : réessayez plus tard.")
        if len(self.depots) > 10000:  # memoire bornee : on oublie les adresses inactives
            for a in [a for a, f in self.depots.items() if not f or maintenant - f[-1] > 86400]:
                del self.depots[a]
        return file

    def deposer(self, corps: dict, adresse: str) -> dict:
        with self.verrou:
            if corps.get("site_web"):  # champ piege, invisible pour un humain : robot, rien n'est enregistre
                return {"ok": True}
            file = self._debit("source", adresse)
            candidats, connus, _ = self._connus()
            entree = CT.valider(corps, candidats)
            e = CT.deposer(self.racine / CONTRIBUTIONS, entree, connus)
            file.append(time.monotonic())
            return {"ok": True, "id": e["id"]}

    def signaler(self, corps: dict, adresse: str) -> dict:
        with self.verrou:
            if corps.get("site_web"):
                return {"ok": True}
            file = self._debit("signalement", adresse)
            entree = CT.valider_signalement(corps, self._connus()[2])
            e = CT.deposer_signalement(self.racine / SIGNALEMENTS, entree)
            file.append(time.monotonic())
            return {"ok": True, "id": e["id"]}


def fabriquer_handler(racine: Path, contributions: bool = True):
    depot = Contributions(racine) if contributions else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "Boussole/1"

        def log_message(self, fmt, *args):  # journal discret
            pass

        def _envoyer(self, status: int, data: bytes, type_: str, corps: bool = True) -> None:
            self.send_response(status)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache" if status == 200 else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if corps:
                self.wfile.write(data)

        def _json(self, data: dict, status: int = 200) -> None:
            self._envoyer(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _servir(self, corps: bool) -> None:
            chemin = urlparse(self.path).path
            if chemin in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", PAGE)
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if chemin == "/api/contributions" and corps:
                return self._json({"ouvertes": depot is not None, "types": list(CT.TYPES_SOURCE),
                                   "signalements": depot is not None})
            if chemin not in FICHIERS or not (racine / FICHIERS[chemin][0]).is_file():
                return self._envoyer(404, "Introuvable.".encode("utf-8"), "text/plain; charset=utf-8", corps)
            fichier, type_ = FICHIERS[chemin]
            self._envoyer(200, (racine / fichier).read_bytes(), type_, corps)  # export regenere a chaque run : no-cache

        def do_GET(self):
            self._servir(True)

        def do_HEAD(self):
            self._servir(False)

        def do_POST(self):
            chemin = urlparse(self.path).path
            if chemin not in ("/api/contribution", "/api/signalement") or depot is None:
                return self._json({"erreur": "Introuvable."}, 404)
            # En-tete propre a la page et corps JSON : un formulaire d'un autre site ne peut pas deposer a la place du visiteur.
            if self.headers.get("X-Boussole") != "1" or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json({"erreur": "Requête refusée."}, 403)
            try:
                taille = int(self.headers.get("Content-Length") or 0)
                if not 0 < taille <= TAILLE_MAX:
                    raise ValueError("Requête vide ou trop grosse.")
                corps = json.loads(self.rfile.read(taille))
                if not isinstance(corps, dict):
                    raise ValueError("Requête invalide.")
                envoi = depot.deposer if chemin == "/api/contribution" else depot.signaler
                return self._json(envoi(corps, self.client_address[0]))
            except PermissionError as exc:
                return self._json({"erreur": str(exc)}, 429)
            except RuntimeError as exc:
                return self._json({"erreur": str(exc)}, 503)
            except (ValueError, KeyError) as exc:
                return self._json({"erreur": str(exc).strip("'")}, 400)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", default=".")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reseau", action="store_true", help="Ecoute aussi sur le reseau local")
    parser.add_argument("--sans-contributions", action="store_true",
                        help="Refuse les sources proposees et les erreurs signalees (lecture seule stricte)")
    args = parser.parse_args()
    racine = Path(args.racine)
    try:
        serveur = ThreadingHTTPServer(("0.0.0.0" if args.reseau else "127.0.0.1", args.port),
                                      fabriquer_handler(racine, not args.sans_contributions))
    except OSError as exc:
        print(f"Erreur serveur constellation : {exc}")
        return 2
    print(f"Constellation : http://127.0.0.1:{args.port}/  (Ctrl+C pour arreter)", flush=True)
    print("Contributions : " + ("fermees." if args.sans_contributions
                                 else f"ouvertes, enregistrees dans {CONTRIBUTIONS} et {SIGNALEMENTS}."), flush=True)
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
