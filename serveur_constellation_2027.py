"""Serveur de la constellation : publie seulement la page et l'export ; recoit les sources et erreurs signalees par le public.

  python .\\serveur_constellation_2027.py                         # http://127.0.0.1:8000/
  python .\\serveur_constellation_2027.py --reseau                # aussi depuis le telephone (meme reseau)
  python .\\serveur_constellation_2027.py --sans-contributions    # lecture seule stricte
  python3 serveur_constellation_2027.py --proxy                  # en ligne, derriere le proxy HTTPS local (docs/mise_en_ligne_2027.md)

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
import gzip
import hashlib
import ipaddress
import json
import re
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
DELAI = 30           # secondes sans activite avant de couper une connexion
BLOC = 64 * 1024     # envoi par blocs : le delai s'applique a chaque bloc, un visiteur lent n'est pas coupe
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def adresse_client(pair: str, transmise: str | None, proxy: bool) -> str:
    """Adresse qui sert a limiter le debit. L'en-tete X-Forwarded-For n'est cru que derriere le proxy local, et seule sa
    derniere valeur (ajoutee par ce proxy) compte ; une adresse IPv6 est ramenee a son reseau /64."""
    texte = pair
    try:
        if proxy and transmise and ipaddress.ip_address(pair).is_loopback:
            texte = transmise.rsplit(",", 1)[-1].strip()
        ip = ipaddress.ip_address(texte)
    except ValueError:
        return pair
    if ip.version == 6 and ip.ipv4_mapped is None:
        return str(ipaddress.ip_network((ip, 64), strict=False))
    return str(ip.ipv4_mapped or ip) if ip.version == 6 else str(ip)


def accepte_gzip(valeur: str | None) -> bool:
    for partie in (valeur or "").lower().split(","):
        nom, _, params = partie.partition(";")
        if nom.strip() == "gzip":
            return not re.fullmatch(r"\s*q=0(\.0*)?\s*", params)
    return False


class Publication:
    """Fichiers publies gardes en memoire, bruts et compresses, relus seulement quand ils changent sur le disque."""

    def __init__(self, racine: Path):
        self.racine = racine
        self.verrou = threading.Lock()
        self.fichiers: dict[str, dict] = {}

    def lire(self, chemin: str) -> dict | None:
        fichier = self.racine / FICHIERS[chemin][0]
        if not fichier.is_file():
            return None
        etat = fichier.stat()
        cle = (etat.st_mtime_ns, etat.st_size)
        with self.verrou:
            entree = self.fichiers.get(chemin)
            if not entree or entree["cle"] != cle:
                brut = fichier.read_bytes()
                etag = hashlib.sha256(brut).hexdigest()[:24]
                entree = {"cle": cle, "brut": brut, "gzip": gzip.compress(brut, 6, mtime=0), "etag": etag}
                self.fichiers[chemin] = entree
            return entree

    def prechauffer(self) -> None:
        for chemin in FICHIERS:
            self.lire(chemin)


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
            data = CT.lire_json(export, {}) or {}
            ajouts = (CT.lire_json(sources, {}) or {}).get("ajouts") or []
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


def fabriquer_handler(racine: Path, contributions: bool = True, proxy: bool = False):
    depot = Contributions(racine) if contributions else None
    publication = Publication(racine)

    class Handler(BaseHTTPRequestHandler):
        timeout = DELAI

        def version_string(self):  # ne dit pas la version de Python
            return "Boussole"

        def log_message(self, fmt, *args):  # journal discret : aucune adresse IP n'est ecrite
            pass

        def _envoyer(self, status: int, data: bytes, type_: str, corps: bool = True, entetes: dict | None = None) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", type_)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache" if status in (200, 304) else "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                for nom, valeur in (entetes or {}).items():
                    self.send_header(nom, valeur)
                self.end_headers()
                if corps:
                    vue = memoryview(data)
                    for debut in range(0, len(vue), BLOC):
                        self.wfile.write(vue[debut:debut + BLOC])
            except (ConnectionError, TimeoutError):  # visiteur parti ou bloque
                self.close_connection = True

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
            entree = publication.lire(chemin) if chemin in FICHIERS else None
            if entree is None:
                return self._envoyer(404, "Introuvable.".encode("utf-8"), "text/plain; charset=utf-8", corps)
            type_ = FICHIERS[chemin][1]
            compresse = accepte_gzip(self.headers.get("Accept-Encoding"))
            etag = f'"{entree["etag"]}{"-gz" if compresse else ""}"'
            entetes = {"ETag": etag, "Vary": "Accept-Encoding"}
            if chemin == PAGE:
                entetes["Content-Security-Policy"] = CSP
            connus = [e.strip().removeprefix("W/") for e in (self.headers.get("If-None-Match") or "").split(",")]
            if etag in connus:  # export regenere a chaque run : le navigateur revalide, sans tout retelecharger
                self.send_response(304)
                for nom, valeur in entetes.items():
                    self.send_header(nom, valeur)
                self.send_header("Cache-Control", "no-cache")
                return self.end_headers()
            if compresse:
                entetes["Content-Encoding"] = "gzip"
            self._envoyer(200, entree["gzip" if compresse else "brut"], type_, corps, entetes)

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
                adresse = adresse_client(self.client_address[0], self.headers.get("X-Forwarded-For"), proxy)
                return self._json(envoi(corps, adresse))
            except (ConnectionError, TimeoutError):
                self.close_connection = True
            except PermissionError as exc:
                return self._json({"erreur": str(exc)}, 429)
            except RuntimeError as exc:
                return self._json({"erreur": str(exc)}, 503)
            except (ValueError, KeyError) as exc:
                return self._json({"erreur": str(exc).strip("'")}, 400)

    Handler.publication = publication
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", default=".")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reseau", action="store_true", help="Ecoute aussi sur le reseau local")
    parser.add_argument("--sans-contributions", action="store_true",
                        help="Refuse les sources proposees et les erreurs signalees (lecture seule stricte)")
    parser.add_argument("--proxy", action="store_true",
                        help="Derriere un proxy HTTPS sur cette machine : limite le debit par visiteur (X-Forwarded-For)")
    args = parser.parse_args()
    if args.proxy and args.reseau:
        parser.error("--proxy et --reseau sont incompatibles : derriere un proxy, le serveur n'ecoute que sur 127.0.0.1.")
    racine = Path(args.racine)
    handler = fabriquer_handler(racine, not args.sans_contributions, args.proxy)
    try:
        serveur = ThreadingHTTPServer(("0.0.0.0" if args.reseau else "127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"Erreur serveur constellation : {exc}")
        return 2
    handler.publication.prechauffer()
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
