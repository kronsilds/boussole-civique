"""Prepare le paquet de la constellation a mettre en ligne : une liste stricte de fichiers, controles avant envoi.

  python .\\paquet_constellation_2027.py           # refuse le paquet si un controle echoue (code 2)
  python .\\paquet_constellation_2027.py --essai   # meme paquet, sans exiger les mentions legales (ne pas publier)

Rien d'autre que FICHIERS ne part : ni .env, ni la base, ni les caches, ni les journaux. Des sources ajoutees, seuls les
liens sont repris (le serveur s'en sert pour refuser un lien deja connu). Aucun appel reseau.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

FICHIERS = ("serveur_constellation_2027.py", "contributions_2027.py", "web/constellation_2027.html",
            "donnees/donnees_interface_2027.json", "web/partage_2027.png")
SOURCES = "donnees/sources_2027.json"
SORTIE = "deploiement/paquet"
INTERDITS = {"chemin local (file://)": rb"file://", "cle OpenRouter": rb"sk-or-[\w-]{8,}",
             "nom de variable secrete": rb"OPENROUTER_API_KEY", "chemin Windows": rb"[A-Za-z]:\\+Users\\+"}


def controler(racine: Path, essai: bool = False) -> list[str]:
    """Liste des raisons de refuser la publication (vide si tout va bien)."""
    erreurs = [f"Fichier manquant : {f}" for f in FICHIERS if not (racine / f).is_file()]
    if erreurs:
        return erreurs
    try:
        export = json.loads((racine / FICHIERS[3]).read_bytes())
    except ValueError as exc:
        return [f"Export illisible : {exc}"]
    if not export.get("proposals") or not export.get("candidates"):
        erreurs.append("Export vide : aucune proposition ou aucun candidat.")
    for f in FICHIERS[2:]:
        contenu = (racine / f).read_bytes()
        erreurs += [f"{nom} trouve dans {f}" for nom, motif in INTERDITS.items() if re.search(motif, contenu)]
    page = (racine / FICHIERS[2]).read_text(encoding="utf-8").casefold()
    if not essai and not all(mot in page for mot in ("mentions légales", "hébergeur")):
        erreurs.append("Mentions legales absentes de la page (titre « Mentions légales » et hébergeur attendus).")
    if not essai and "à compléter" in page:
        erreurs.append(f"Mentions legales incompletes : {page.count('à compléter')} champ(s) « À COMPLÉTER » dans la page.")
    return erreurs


def construire(racine: Path, sortie: Path) -> list[str]:
    """Copie la liste stricte dans `sortie` (videe d'abord) et ecrit les empreintes SHA256SUMS."""
    if sortie.exists():
        shutil.rmtree(sortie)
    for f in FICHIERS:
        (sortie / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(racine / f, sortie / f)
    lu = json.loads((racine / SOURCES).read_text(encoding="utf-8")) if (racine / SOURCES).is_file() else {}
    liens = [{"url": a["url"]} for a in lu.get("ajouts") or [] if str(a.get("url") or "").startswith(("http://", "https://"))]
    (sortie / SOURCES).write_text(json.dumps({"ajouts": liens}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    publies = [*FICHIERS, SOURCES]
    lignes = [f"{hashlib.sha256((sortie / f).read_bytes()).hexdigest()}  {f}\n" for f in publies]
    (sortie / "SHA256SUMS").write_bytes("".join(lignes).encode("ascii"))
    return publies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", type=Path, default=Path("."))
    parser.add_argument("--essai", action="store_true", help="N'exige pas les mentions legales (paquet a ne pas publier)")
    args = parser.parse_args()
    erreurs = controler(args.racine, args.essai)
    if erreurs:
        print("Paquet refuse :")
        for e in erreurs:
            print(f"  - {e}")
        return 2
    sortie = args.racine / SORTIE
    publies = construire(args.racine, sortie)
    taille = sum((sortie / f).stat().st_size for f in publies) / 1e6
    print(f"Paquet pret dans {SORTIE} : {len(publies)} fichiers, {taille:.1f} Mo." + (" ESSAI : ne pas publier." if args.essai else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
