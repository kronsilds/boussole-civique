"""Sauvegarde des donnees non versionnees du pipeline dans une archive zip datee et verifiee.

Contenu : donnees/ (base, caches des lectures payees, exports, budget, contributions et signalements), corpus_programmes/
(documents, textes, extractions payees) et runs/ (bilans, echantillons figes, relectures). Sur option : logs/ (journaux
des appels) et archives/donnees/ (anciens resultats, dont cache_scores.json). Jamais .env ni les verrous.

  python .\\boussole_2027.py sauvegarder --destination E:\\Sauvegardes\\boussole [--destination AUTRE] [--memoriser] [--garder 8]
  python .\\boussole_2027.py sauvegarder                 # destinations memorisees (donnees/sauvegarde_2027.json)
  python .\\boussole_2027.py sauvegarder --essai          # liste et taille, rien n'est ecrit
  python .\\boussole_2027.py sauvegarder --lister | --verifier ARCHIVE

L'archive est ecrite sous un nom provisoire, relue (controle CRC de chaque fichier, liste et tailles comparees au
manifeste interne `sauvegarde_2027.json`, qui donne aussi l'empreinte SHA-256 de chaque fichier et le commit git), puis
renommee. Avec plusieurs destinations, la premiere recoit l'archive et les suivantes une copie relue de la meme facon ; un
echec sur l'une d'elles est signale sans toucher aux autres. Dans chaque destination, les plus anciennes archives au-dela
de son « garder » ne sont supprimees qu'apres une sauvegarde reussie, et seulement celles dont le nom suit le motif
boussole_sauvegarde_AAAAMMJJ_HHMMSS.zip. Aucun appel reseau (un dossier OneDrive est synchronise par OneDrive lui-meme).

Restauration : extraire l'archive a la racine du projet (explorateur Windows, ou
`python -m zipfile -e archive.zip dossier`), apres avoir mis de cote les fichiers presents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

DOSSIERS = ("donnees", "corpus_programmes", "runs")
DOSSIER_JOURNAUX = "logs"
DOSSIER_ARCHIVES = "archives/donnees"
SUFFIXES_EXCLUS = (".lock", ".tmp", ".partiel")
MANIFESTE = "sauvegarde_2027.json"
CONFIG = Path("donnees") / "sauvegarde_2027.json"
MOTIF = re.compile(r"^boussole_sauvegarde_\d{8}_\d{6}\.zip$")
GARDER_DEFAUT = 8
BLOC = 1024 * 1024


def _exclu(chemin: Path) -> bool:
    nom = chemin.name
    return nom.startswith(".env") or nom.endswith(SUFFIXES_EXCLUS) or chemin.is_symlink()


def fichiers(racine: Path, dossiers: tuple[str, ...]) -> list[Path]:
    """Fichiers a archiver, en chemins relatifs a la racine, tries."""
    resultat: list[Path] = []
    for dossier in dossiers:
        base = racine / dossier
        if not base.is_dir():
            continue
        for chemin in base.rglob("*"):
            if chemin.is_file() and not _exclu(chemin):
                resultat.append(chemin.relative_to(racine))
    return sorted(resultat, key=lambda p: p.as_posix())


def etat_git(racine: Path) -> dict[str, Any] | None:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=racine, capture_output=True, text=True,
                                timeout=20, check=True).stdout.strip()
        modifies = subprocess.run(["git", "status", "--porcelain"], cwd=racine, capture_output=True, text=True,
                                  timeout=60, check=True).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    return {"commit": commit, "fichiers_modifies": len(modifies)}


Destination = tuple[Path, int]  # (dossier, nombre d'archives conservees)


def _entier(valeur: Any, quoi: str) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 1:
        raise ValueError(f"{quoi} : garder doit etre un entier superieur ou egal a 1.")
    return valeur


def lire_config(racine: Path) -> list[Destination]:
    """Destinations memorisees : {"destinations": [{"chemin": ..., "garder": 8}, ...]} (la premiere recoit l'archive,
    les suivantes une copie verifiee)."""
    chemin = racine / CONFIG
    if not chemin.exists():
        return []
    config = json.loads(chemin.read_text(encoding="utf-8"))
    entrees = config.get("destinations") if isinstance(config, dict) else None
    if not isinstance(entrees, list) or not all(isinstance(e, dict) and isinstance(e.get("chemin"), str) for e in entrees):
        raise ValueError(f"{chemin} invalide (attendu : destinations, liste de {{chemin, garder}}).")
    return [(Path(e["chemin"]), _entier(e.get("garder", GARDER_DEFAUT), str(chemin))) for e in entrees]


def ecrire_config(racine: Path, destinations: list[Destination]) -> Path:
    chemin = racine / CONFIG
    chemin.parent.mkdir(parents=True, exist_ok=True)
    contenu = {"destinations": [{"chemin": str(d), "garder": g} for d, g in destinations]}
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return chemin


def _controler_destination(racine: Path, destination: Path, dossiers: tuple[str, ...]) -> list[str]:
    """Refuse une destination dans un dossier archive (l'archive s'inclurait elle-meme) ; avertit si meme disque."""
    destination = destination.resolve()
    for dossier in dossiers:
        if destination.is_relative_to((racine / dossier).resolve()):
            raise ValueError(f"Destination dans un dossier sauvegarde ({dossier}) : choisir un autre dossier.")
    avertissements = []
    if destination.drive.lower() == racine.resolve().drive.lower():
        avertissements.append(f"Destination sur le meme disque que le projet ({destination.drive or '/'}) : "
                              "ne protege pas d'une panne de disque.")
    return avertissements


def verifier(archive: Path) -> dict[str, Any]:
    """Relit l'archive : CRC de chaque fichier, puis liste et tailles comparees au manifeste interne."""
    with zipfile.ZipFile(archive) as z:
        mauvais = z.testzip()
        if mauvais is not None:
            raise ValueError(f"Archive corrompue : {archive.name}, fichier {mauvais}.")
        manifeste = json.loads(z.read(MANIFESTE).decode("utf-8"))
        tailles = {i.filename: i.file_size for i in z.infolist() if i.filename != MANIFESTE}
    attendus = {f["chemin"]: f["taille"] for f in manifeste["fichiers"]}
    if tailles != attendus:
        manquants = sorted(set(attendus) - set(tailles))[:5]
        raise ValueError(f"Archive incomplete : {archive.name} ne correspond pas a son manifeste (ex. {manquants}).")
    return {"archive": str(archive), "fichiers": len(attendus), "octets": sum(attendus.values()),
            "date": manifeste.get("date"), "git": manifeste.get("git")}


def lister(destination: Path) -> list[dict[str, Any]]:
    if not destination.is_dir():
        return []
    return [{"archive": p.name, "octets": p.stat().st_size} for p in sorted(destination.iterdir()) if MOTIF.match(p.name)]


def _rotation(destination: Path, garder: int) -> list[str]:
    anciennes = [p for p in sorted(destination.iterdir()) if MOTIF.match(p.name)]
    for p in anciennes[:-garder]:
        p.unlink()
    return [p.name for p in anciennes[:-garder]]


def copier(archive: Path, destination: Path, garder: int) -> dict[str, Any]:
    """Copie verifiee de l'archive dans une autre destination (nom provisoire, relecture, renommage, rotation)."""
    destination.mkdir(parents=True, exist_ok=True)
    taille = archive.stat().st_size
    if shutil.disk_usage(destination).free < taille:
        raise OSError(f"Place insuffisante dans {destination} ({taille // 2**20} Mio necessaires).")
    finale = destination / archive.name
    provisoire = finale.with_name(finale.name + ".partiel")
    try:
        shutil.copyfile(archive, provisoire)
        verifier(provisoire)
        os.replace(provisoire, finale)
    finally:
        provisoire.unlink(missing_ok=True)
    return {"destination": str(destination), "archive": str(finale), "supprimees": _rotation(destination, garder)}


def _normaliser(destinations: Path | list[Path] | list[Destination], garder: int) -> list[Destination]:
    if isinstance(destinations, Path):
        destinations = [destinations]
    resultat = [(d, garder) if isinstance(d, Path) else (Path(d[0]), _entier(d[1], str(d[0]))) for d in destinations]
    if not resultat:
        raise ValueError("Aucune destination.")
    _entier(garder, "--garder")
    return resultat


def sauvegarder(racine: Path, destinations: Path | list[Path] | list[Destination], *, garder: int = GARDER_DEFAUT,
                journaux: bool = False, archives: bool = False, essai: bool = False,
                horodatage: str | None = None) -> dict[str, Any]:
    """Ecrit, verifie et renomme l'archive dans la premiere destination, puis en fait une copie verifiee dans chacune
    des suivantes ; dans chaque destination, supprime les plus anciennes archives au-dela de son `garder`.
    Un echec dans une destination secondaire est rapporte (copies[...]["erreur"]) sans annuler les autres."""
    cibles = _normaliser(destinations, garder)
    destination, garder = cibles[0]
    dossiers = DOSSIERS + ((DOSSIER_JOURNAUX,) if journaux else ()) + ((DOSSIER_ARCHIVES,) if archives else ())
    avertissements: list[str] = []
    for d, _ in cibles:
        avertissements += [a for a in _controler_destination(racine, d, dossiers) if a not in avertissements]
    if len(cibles) > 1:  # au moins une copie hors du disque du projet : l'avertissement n'a plus lieu d'etre
        hors = [d for d, _ in cibles if d.resolve().drive.lower() != racine.resolve().drive.lower()]
        if hors:
            avertissements = []
    liste = fichiers(racine, dossiers)
    if not liste:
        raise ValueError(f"Rien a sauvegarder sous {racine.resolve()} ({', '.join(dossiers)}).")
    total = sum((racine / f).stat().st_size for f in liste)
    rapport: dict[str, Any] = {"destination": str(destination), "dossiers": list(dossiers), "fichiers": len(liste),
                               "octets_sources": total, "avertissements": avertissements,
                               "copies_prevues": [str(d) for d, _ in cibles[1:]]}
    if essai:
        par_dossier: dict[str, int] = {}
        for f in liste:
            par_dossier[f.parts[0]] = par_dossier.get(f.parts[0], 0) + (racine / f).stat().st_size
        return {**rapport, "essai": True, "octets_par_dossier": par_dossier}
    destination.mkdir(parents=True, exist_ok=True)
    libre = shutil.disk_usage(destination).free
    if libre < total:  # pire cas : rien ne se compresse (PDF, images)
        raise OSError(f"Place insuffisante sur la destination : {libre // 2**20} Mio libres, {total // 2**20} Mio a copier.")
    stamp = horodatage or datetime.now().strftime("%Y%m%d_%H%M%S")
    finale = destination / f"boussole_sauvegarde_{stamp}.zip"
    if finale.exists():
        raise ValueError(f"{finale} existe deja.")
    provisoire = finale.with_name(finale.name + ".partiel")
    entrees, disparus = [], []
    try:
        with zipfile.ZipFile(provisoire, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for relatif in liste:
                source = racine / relatif
                try:
                    info = zipfile.ZipInfo.from_file(source, relatif.as_posix())
                    info.compress_type = zipfile.ZIP_DEFLATED
                    empreinte = hashlib.sha256()
                    taille = 0
                    with open(source, "rb") as lecture, z.open(info, "w", force_zip64=True) as ecriture:
                        while bloc := lecture.read(BLOC):
                            empreinte.update(bloc)
                            ecriture.write(bloc)
                            taille += len(bloc)
                except FileNotFoundError:  # fichier temporaire retire entre la liste et la lecture
                    disparus.append(relatif.as_posix())
                    continue
                entrees.append({"chemin": relatif.as_posix(), "taille": taille, "sha256": empreinte.hexdigest()})
            manifeste = {"version": 1, "date": datetime.now().isoformat(timespec="seconds"), "racine": str(racine.resolve()),
                         "dossiers": list(dossiers), "git": etat_git(racine), "fichiers": entrees}
            z.writestr(MANIFESTE, json.dumps(manifeste, ensure_ascii=False, indent=1))
        controle = verifier(provisoire)
        os.replace(provisoire, finale)
    finally:
        provisoire.unlink(missing_ok=True)
    supprimees = _rotation(destination, garder)
    copies = []
    for autre, garder_autre in cibles[1:]:
        try:
            copies.append(copier(finale, autre, garder_autre))
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            copies.append({"destination": str(autre), "erreur": str(exc)})
    return {**rapport, "archive": str(finale), "octets_archive": finale.stat().st_size, "fichiers": controle["fichiers"],
            "disparus": disparus, "supprimees": supprimees, "copies": copies, "verifiee": True}


def resume_texte(rapport: dict[str, Any]) -> str:
    lignes = []
    if rapport.get("essai"):
        lignes.append(f"Essai : {rapport['fichiers']} fichiers, {rapport['octets_sources'] / 2**20:.0f} Mio a archiver vers "
                      f"{rapport['destination']}"
                      + (f", copie vers {', '.join(rapport['copies_prevues'])}" if rapport["copies_prevues"] else "")
                      + " (rien n'est ecrit).")
        lignes += [f"  {d} : {o / 2**20:.0f} Mio" for d, o in sorted(rapport["octets_par_dossier"].items())]
    else:
        lignes.append(f"Sauvegarde verifiee : {rapport['archive']} ({rapport['fichiers']} fichiers, "
                      f"{rapport['octets_sources'] / 2**20:.0f} Mio -> {rapport['octets_archive'] / 2**20:.0f} Mio).")
        if rapport["supprimees"]:
            lignes.append(f"  Anciennes archives supprimees : {', '.join(rapport['supprimees'])}")
        for copie in rapport["copies"]:
            if "erreur" in copie:
                lignes.append(f"  COPIE ECHOUEE vers {copie['destination']} : {copie['erreur']}")
            else:
                lignes.append(f"  Copie verifiee : {copie['archive']}"
                              + (f" (supprimees : {', '.join(copie['supprimees'])})" if copie["supprimees"] else ""))
        if rapport["disparus"]:
            lignes.append(f"  Fichiers disparus pendant la copie (ignores) : {', '.join(rapport['disparus'][:5])}")
    lignes += [f"  ATTENTION : {a}" for a in rapport["avertissements"]]
    return "\n".join(lignes)


def executer(c: dict[str, Path], args: argparse.Namespace, Verrou: Any) -> int:
    """Commande `boussole_2027.py sauvegarder`."""
    racine = Path(args.racine)
    if args.verifier:
        print(json.dumps(verifier(Path(args.verifier)), ensure_ascii=False, indent=1))
        return 0
    if args.destination:
        garder = args.garder or GARDER_DEFAUT
        destinations = [(Path(d), garder) for d in args.destination]
    else:
        destinations = [(d, args.garder or g) for d, g in lire_config(racine)]
    if not destinations:
        raise ValueError("Aucune destination : --destination DOSSIER, repetable (ajouter --memoriser pour la garder "
                         f"dans {CONFIG}).")
    if args.lister:
        for destination, _ in destinations:
            archives = lister(destination)
            print(f"{len(archives)} archive(s) dans {destination}.")
            for a in archives:
                print(f"  {a['archive']}  {a['octets'] / 2**20:.0f} Mio")
        return 0
    if args.memoriser:
        print(f"Destination(s) memorisee(s) dans {ecrire_config(racine, destinations)} : "
              + ", ".join(f"{d} (garder {g})" for d, g in destinations))
    if args.essai:
        print(resume_texte(sauvegarder(racine, destinations, journaux=args.journaux, archives=args.archives, essai=True)))
        return 0
    # Pas d'ecriture de la base ni de run de la chaine pendant la copie
    with Verrou(c["verrou_chaine"], args.force_verrou), Verrou(c["verrou"], args.force_verrou):
        rapport = sauvegarder(racine, destinations, journaux=args.journaux, archives=args.archives)
    print(resume_texte(rapport))
    return 2 if any("erreur" in copie for copie in rapport["copies"]) else 0


def apres_chaine(racine: Path) -> bool | None:
    """Sauvegarde de fin de `mise-a-jour --complet` (verrou de la chaine deja tenu). None : pas de destination
    memorisee ; False : echec (signale, sans perdre le travail du run)."""
    try:
        destinations = lire_config(racine)
        if not destinations:
            print("   Pas de sauvegarde : aucune destination memorisee "
                  "(boussole_2027.py sauvegarder --destination DOSSIER --memoriser).")
            return None
        rapport = sauvegarder(racine, destinations)
        print(resume_texte(rapport))
        return not any("erreur" in copie for copie in rapport["copies"])
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"   SAUVEGARDE ECHOUEE : {exc}")
        return False
