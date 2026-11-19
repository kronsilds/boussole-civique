"""Contributions du public depuis la constellation, traitees au tableau de bord : sources proposees et erreurs signalees.

Le serveur de la constellation n'ecrit que deux fichiers, ignores par git et sans donnee personnelle (ni adresse IP,
ni contact) :
- donnees/contributions_2027.json : liens proposes. Le tableau de bord en reprend un dans « Ajouter un document » (la
  source rejoint donnees/sources_2027.json et la chaine complete la traite) ou le refuse. Aucune requete reseau ici :
  un lien n'est ouvert qu'apres validation humaine, par la collecte.
- donnees/signalements_2027.json : erreurs signalees sur une proposition publiee (extraction, notation ou autre),
  avec une motivation. Le relecteur corrige la mesure (decisions habituelles) puis marque le signalement « corrige »,
  ou l'ecarte avec un motif. Un signalement ne modifie jamais la base par lui-meme.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Module autonome (bibliotheque standard seulement) : le serveur en ligne n'embarque ni la base ni le pipeline.

TYPES_SOURCE = ("programme", "entretien", "discours", "communique", "tribune", "video_transcription", "autre")
LIMITES = {"url": 600, "titre": 200, "note": 1000}
MAX_EN_ATTENTE = 300   # au-dela, le depot est refuse jusqu'a ce que le tableau de bord en traite
STATUTS = ("en_attente", "acceptee", "refusee")


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lire_json(path: Path, defaut: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else defaut


def ecrire_json(path: Path, data: Any) -> None:
    """Ecriture atomique : fichier temporaire puis renommage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


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
    if cand is not None and (not isinstance(cand, str) or cand not in candidats):
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


def lire(chemin: Path, cle: str = "contributions") -> dict[str, Any]:
    return lire_json(chemin, None) or {cle: []}


def _numero(items: list[dict[str, Any]], prefixe: str) -> str:
    n = max((int(c["id"].split("-")[1]) for c in items if re.fullmatch(prefixe + r"-\d+", c.get("id", ""))), default=0) + 1
    return f"{prefixe}-{n:04d}"


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
        entree = {"id": _numero(items, "c"), **entree, "deposee_le": maintenant(), "statut": "en_attente"}
        items.append(entree)
        ecrire_json(chemin, data)
    return entree


def traiter(chemin: Path, cid: str, statut: str, *, cle: str = "contributions", statuts: tuple[str, ...] = STATUTS,
            **champs: Any) -> dict[str, Any]:
    """Passe une entree en attente a un statut final : contribution « acceptee » (champ source_id) ou « refusee »
    (champ motif) ; signalement « corrige » ou « ecarte » (cle="signalements", statuts=STATUTS_SIGNALEMENT)."""
    if statut not in statuts[1:]:
        raise ValueError("Statut inconnu.")
    with Verrou(chemin):
        data = lire(chemin, cle)
        for c in data[cle]:
            if c["id"] == cid:
                if c.get("statut") != "en_attente":
                    raise ValueError("Deja traite.")
                c.update(statut=statut, traitee_le=maintenant(), **champs)
                ecrire_json(chemin, data)
                return c
    raise KeyError(f"Entree inconnue : {cid}")


# --- Signalements d'erreur ----------------------------------------------------------------------------------------

CATEGORIES = ("extraction", "annotation", "autre")
DETAILS = {  # precision facultative choisie dans la constellation
    "extraction": ("absente", "deformee", "pas_une_proposition", "theme", "candidat", "doublon"),
    "annotation": ("eco", "soc", "ouverture", "rights_status", "sov", "ecolo", "income_direction", "rights_income",
                   "rupture", "feasibility", "importance", "precision", "instrument", "cout"),
    "autre": (),
}
LIBELLES_DETAILS = {
    "absente": "absente du document", "deformee": "mal résumée ou déformée", "pas_une_proposition": "pas une proposition",
    "theme": "mauvais thème", "candidat": "mauvais candidat ou mauvaise source", "doublon": "doublon",
    "eco": "économie", "soc": "libertés", "ouverture": "accueil des étrangers", "rights_status": "accès aux droits",
    "sov": "niveau de décision", "ecolo": "environnement", "income_direction": "effet sur les revenus",
    "rights_income": "personnes concernées", "rupture": "ampleur du changement", "feasibility": "faisabilité",
    "importance": "importance", "precision": "précision", "instrument": "instrument juridique", "cout": "budget",
}
MOTIVATION = (10, 1500)        # caracteres
MAX_SIGNALEMENTS = 1000        # en attente, tous confondus
MAX_PAR_MESURE = 20            # en attente, pour une meme proposition
STATUTS_SIGNALEMENT = ("en_attente", "corrige", "ecarte")


def valider_signalement(corps: dict[str, Any], propositions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """`propositions` : lignes de l'export par uid ; titre et valeur affichee sont repris de l'export, pas du client."""
    uid = corps.get("uid")
    if not isinstance(uid, str) or uid not in propositions:
        raise ValueError("Proposition inconnue : la page n'est peut-être plus à jour, rechargez-la.")
    cat = corps.get("categorie")
    if cat not in CATEGORIES:
        raise ValueError("Choisissez le type d'erreur.")
    detail = corps.get("detail") or None
    if detail is not None and detail not in DETAILS[cat]:
        raise ValueError("Précision inconnue pour ce type d'erreur.")
    motif = corps.get("motif")
    motif = " ".join(motif.split()) if isinstance(motif, str) else ""
    if not MOTIVATION[0] <= len(motif) <= MOTIVATION[1]:
        raise ValueError(f"Expliquez l'erreur en {MOTIVATION[0]} à {MOTIVATION[1]} caractères.")
    p = propositions[uid]
    affiche = (p.get("v") or {}).get(detail) if detail in DETAILS["annotation"] else None
    return {"uid": uid, "categorie": cat, "detail": detail, "motif": motif, "titre": p.get("title"),
            "candidate_id": p.get("c"), "maj": p.get("maj"), "valeur_affichee": affiche}


def deposer_signalement(chemin: Path, entree: dict[str, Any]) -> dict[str, Any]:
    with Verrou(chemin):
        data = lire(chemin, "signalements")
        items = data["signalements"]
        attente = [x for x in items if x.get("statut") == "en_attente"]
        if any(x["uid"] == entree["uid"] and x["motif"].casefold() == entree["motif"].casefold() for x in items):
            raise ValueError("Ce signalement a déjà été envoyé. Merci !")
        if len(attente) >= MAX_SIGNALEMENTS or sum(x["uid"] == entree["uid"] for x in attente) >= MAX_PAR_MESURE:
            raise RuntimeError("Trop de signalements en attente de relecture : réessayez dans quelques jours.")
        entree = {"id": _numero(items, "e"), **entree, "deposee_le": maintenant(), "statut": "en_attente"}
        items.append(entree)
        ecrire_json(chemin, data)
    return entree


# --- Synchronisation entre le serveur en ligne (depots du public) et le tableau de bord local (traitements) ---------

CLES_NATURELLES = {"contributions": lambda x: normaliser_url(x["url"]),
                   "signalements": lambda x: (x["uid"], x["motif"].casefold())}


def fusionner(chemin: Path, autres: list[dict[str, Any]], cle: str) -> dict[str, int]:
    """Ajoute a `chemin` les entrees de `autres` ; un statut final l'emporte sur « en_attente ». Rejouable sans effet.
    Deux entrees differentes sous le meme identifiant, ou deux decisions opposees : ValueError, rien n'est ecrit."""
    naturelle = CLES_NATURELLES[cle]
    with Verrou(chemin):
        data = lire(chemin, cle)
        ici = {x["id"]: x for x in data[cle]}
        naturels = {naturelle(x): x["id"] for x in data[cle]}
        ajouts, decisions = [], []
        for x in autres:
            y = ici.get(x["id"])
            if naturels.get(naturelle(x), x["id"]) != x["id"] or (y is not None and naturelle(y) != naturelle(x)):
                raise ValueError(f"Conflit sur {x['id']} : entrees differentes, rien n'est fusionne.")
            if y is None:
                ajouts.append(x)
            elif x.get("statut") != y.get("statut"):
                if y.get("statut") == "en_attente":
                    decisions.append(x)
                elif x.get("statut") != "en_attente":
                    raise ValueError(f"Conflit sur {x['id']} : decisions opposees, rien n'est fusionne.")
        if ajouts or decisions:
            ici.update({x["id"]: x for x in [*ajouts, *decisions]})
            data[cle] = sorted(ici.values(), key=lambda x: int(x["id"].split("-")[1]))
            ecrire_json(chemin, data)
    return {"ajouts": len(ajouts), "decisions": len(decisions)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fusionne deux fichiers de contributions ou de signalements.")
    sous = parser.add_subparsers(dest="commande", required=True)
    f = sous.add_parser("fusionner")
    f.add_argument("--depuis", type=Path, required=True)
    f.add_argument("--dans", type=Path, required=True)
    f.add_argument("--cle", choices=tuple(CLES_NATURELLES), required=True)
    args = parser.parse_args()
    try:
        bilan = fusionner(args.dans, lire(args.depuis, args.cle)[args.cle], args.cle)
    except (ValueError, KeyError, RuntimeError) as exc:
        print(f"Erreur : {exc}")
        return 2
    print(f"{args.cle} : {bilan['ajouts']} ajout(s), {bilan['decisions']} decision(s) reprise(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
