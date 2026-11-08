"""Contributions du public : liens vers des sources proposes depuis la constellation, valides au tableau de bord.

Le serveur de la constellation n'ecrit que ce fichier (donnees/contributions_2027.json, ignore par git) : une entree
par lien propose, sans donnee personnelle (ni adresse IP, ni contact). Le tableau de bord la reprend dans le formulaire
« Ajouter un document » (la source rejoint alors donnees/sources_2027.json et la chaine complete la traite) ou la
refuse. Aucune requete reseau ici : un lien n'est ouvert qu'apres validation humaine, par la collecte.
"""
from __future__ import annotations

import ipaddress
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import base_2027 as B

TYPES_SOURCE = ("programme", "entretien", "discours", "communique", "tribune", "video_transcription", "autre")
LIMITES = {"url": 600, "titre": 200, "note": 1000}
MAX_EN_ATTENTE = 300   # au-dela, le depot est refuse jusqu'a ce que le tableau de bord en traite
STATUTS = ("en_attente", "acceptee", "refusee")


def normaliser_url(url: str) -> str:
    """Cle de comparaison : schema et hote en minuscules, sans « www. », sans fragment ni barre finale."""
    s = urlsplit(url.strip())
    hote = (s.hostname or "").lower().removeprefix("www.")
    chemin = s.path.rstrip("/")
    return f"{hote}{chemin}" + (f"?{s.query}" if s.query else "")


def _texte(corps: dict[str, Any], cle: str) -> str | None:
    valeur = corps.get(cle)
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise ValueError(f"Champ « {cle} » invalide.")
    valeur = " ".join(valeur.split())
    if len(valeur) > LIMITES[cle]:
        raise ValueError(f"Champ « {cle} » trop long ({LIMITES[cle]} caractères au plus).")
    return valeur or None


def verifier_url(url: str | None) -> str:
    if not url:
        raise ValueError("Lien manquant.")
    if re.search(r"\s", url):
        raise ValueError("Le lien ne doit pas contenir d'espace.")
    s = urlsplit(url)
    if s.scheme not in ("http", "https") or not s.hostname:
        raise ValueError("Lien http(s) attendu, par exemple https://exemple.fr/programme.pdf.")
    if s.username or s.password:
        raise ValueError("Lien avec identifiants refusé.")
    hote = s.hostname.lower()
    try:
        ipaddress.ip_address(hote)
    except ValueError:
        pass
    else:
        raise ValueError("Donner l'adresse d'un site (nom de domaine), pas une adresse IP.")
    if "." not in hote or hote == "localhost" or hote.endswith((".local", ".localhost", ".internal", ".lan")):
        raise ValueError("Adresse de site public attendue.")
    return url


def valider(corps: dict[str, Any], candidats: set[str]) -> dict[str, Any]:
    """Entree propre a enregistrer, ou ValueError avec un message lisible par le public."""
    url = verifier_url(_texte(corps, "url"))
    cand = corps.get("candidate_id") or None
    if cand is not None and cand not in candidats:
        raise ValueError("Candidat inconnu.")
    type_ = corps.get("type") or None
    if type_ is not None and type_ not in TYPES_SOURCE:
        raise ValueError("Type de source inconnu.")
    date = corps.get("date") or None
    if date is not None and not (isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
        raise ValueError("Date au format AAAA-MM-JJ.")
    return {"url": url, "candidate_id": cand, "type": type_, "titre": _texte(corps, "titre"), "date": date,
            "note": _texte(corps, "note")}


class Verrou:
    """Verrou de fichier entre processus (serveur de la constellation et tableau de bord ecrivent le meme fichier)."""

    def __init__(self, chemin: Path, attente: float = 5.0, perime: float = 30.0):
        self.f, self.attente, self.perime = chemin.with_name(chemin.name + ".lock"), attente, perime

    def __enter__(self):
        self.f.parent.mkdir(parents=True, exist_ok=True)
        fin = time.monotonic() + self.attente
        while True:
            try:
                os.close(os.open(self.f, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.f.stat().st_mtime > self.perime:  # verrou abandonne par un processus arrete
                        self.f.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > fin:
                    raise RuntimeError("Enregistrement momentanément impossible : réessayez dans un instant.") from None
                time.sleep(.05)

    def __exit__(self, *exc):
        self.f.unlink(missing_ok=True)


def lire(chemin: Path) -> dict[str, Any]:
    return B.lire_json(chemin, None) or {"contributions": []}


def deposer(chemin: Path, entree: dict[str, Any], connues: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
    """Ajoute une contribution validee. `connues` : liens deja dans le corpus ou les sources ajoutees (normalises)."""
    cle = normaliser_url(entree["url"])
    if cle in connues:
        raise ValueError("Cette source figure déjà dans le corpus ou parmi les sources ajoutées. Merci !")
    with Verrou(chemin):
        data = lire(chemin)
        items = data["contributions"]
        if any(normaliser_url(c["url"]) == cle for c in items):
            raise ValueError("Ce lien a déjà été proposé. Merci !")
        if sum(c.get("statut") == "en_attente" for c in items) >= MAX_EN_ATTENTE:
            raise RuntimeError("Trop de propositions en attente de relecture : réessayez dans quelques jours.")
        n = max((int(c["id"].split("-")[1]) for c in items if re.fullmatch(r"c-\d+", c.get("id", ""))), default=0) + 1
        entree = {"id": f"c-{n:04d}", **entree, "deposee_le": B.maintenant(), "statut": "en_attente"}
        items.append(entree)
        B.ecrire_json(chemin, data)
    return entree


def traiter(chemin: Path, cid: str, statut: str, **champs: Any) -> dict[str, Any]:
    """Passe une contribution en attente a « acceptee » (champ source_id) ou « refusee » (champ motif)."""
    if statut not in STATUTS[1:]:
        raise ValueError("Statut inconnu.")
    with Verrou(chemin):
        data = lire(chemin)
        for c in data["contributions"]:
            if c["id"] == cid:
                if c.get("statut") != "en_attente":
                    raise ValueError("Contribution deja traitee.")
                c.update(statut=statut, traitee_le=B.maintenant(), **champs)
                B.ecrire_json(chemin, data)
                return c
    raise KeyError(f"Contribution inconnue : {cid}")
