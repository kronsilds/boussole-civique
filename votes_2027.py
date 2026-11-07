"""Votes parlementaires, phase 1 (docs/spec_votes_2027.md) : import des scrutins officiels et votants suivis.

  python .\\boussole_2027.py votes plan                                   # etat et couverture (gratuit, local)
  python .\\boussole_2027.py votes chercher "Ruffin" --acteurs AMO30.zip  # identifiant officiel (a confirmer a la main)
  python .\\boussole_2027.py votes votant --candidat ruffin --an-acteur PA1234
  python .\\boussole_2027.py votes importer [--legislature 17] [--archive Scrutins.json.zip] [--hors-ligne]

Gratuit, sans modele. Le seul acces reseau est le telechargement de l'archive officielle des scrutins (hote fixe, https,
taille plafonnee, empreinte conservee) ; --archive ou --hors-ligne n'en font aucun. L'archive n'est jamais extraite sur le
disque : ses fichiers sont lus en memoire. Aucun vote n'est rattache a une mesure ici (phase 2 : liens valides par un humain).

Phase 2 (liens vote-mesure) : `Donnees` lit votants, scrutins et liens ; un lien est une decision humaine gardee dans
`donnees/liens_votes_2027.json` (journal en ajout seulement : un lien remplace le precedent pour le meme couple mesure-scrutin,
un retrait est une ligne de plus, rien n'est efface). Il est lie a la version de la mesure et au vote vu au moment de la
validation : si l'un des deux change, il passe « a revoir » et n'est plus exporte tant qu'il n'est pas reconfirme.

La lecture du format officiel est isolee dans `scrutins_de`, `acteurs_de` et `lire_scrutin` : c'est le seul endroit a
ajuster si l'Assemblee change son schema.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import base_2027 as B

HOTE = "data.assemblee-nationale.fr"
URL_SCRUTINS = f"https://{HOTE}/static/openData/repository/{{leg}}/loi/scrutins/{{fichier}}"
FICHIER_SCRUTINS = {"15": "Scrutins_XV.json.zip"}  # les autres legislatures : Scrutins.json.zip (verifie pour la 16e et la 17e)


def url_scrutins(legislature: str) -> str:
    return URL_SCRUTINS.format(leg=legislature, fichier=FICHIER_SCRUTINS.get(str(legislature), "Scrutins.json.zip"))
URL_ACTEURS = (f"https://{HOTE}/static/openData/repository/17/amo/tous_acteurs_mandats_organes_xi_legislature/"
               "AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip")
LIEN_SCRUTIN = "https://www.assemblee-nationale.fr/dyn/{leg}/scrutins/{numero}"
TAILLE_MAX = 120 * 1024 * 1024          # archive telechargee
DECOMPRESSE_MAX = 2 * 1024 ** 3         # somme des fichiers de l'archive (protection contre une archive piegee)
FICHIERS_MAX = 60000
FICHIER_JSON_MAX = 8 * 1024 * 1024
POSITIONS = {"pours": "pour", "contres": "contre", "abstentions": "abstention", "nonVotants": "non_votant"}
VERSION_LECTURE = 2  # a changer quand `lire_scrutin` change : force la relecture des archives deja importees
RE_ACTEUR = re.compile(r"^PA\d{1,9}$")
RELATIONS = ("conforme", "contraire", "partielle", "sans_rapport")  # le texte vote : reprend la mesure, la contredit, la reprend en partie, sans rapport
PORTEES = ("mesure", "article", "amendement", "texte_compose")      # texte_compose : jamais de conclusion de contradiction
PORTEE_PAR_DEFAUT = {"amendement": "amendement", "article": "article", "ensemble": "texte_compose"}
NOTE_MAX, PREUVE_MAX = 500, 800


# --- Outils --------------------------------------------------------------------------------------------------------

def texte(x: Any) -> str | None:
    """Valeur d'un noeud XML converti en JSON : chaine, ou objet {"#text": ...}."""
    if isinstance(x, dict):
        x = x.get("#text")
    return None if x is None else str(x)


def liste(x: Any) -> list[Any]:
    """Un noeud repete peut etre absent, unique (objet) ou multiple (liste)."""
    return [] if x is None else x if isinstance(x, list) else [x]


def votants_de(noeud: Any) -> list[dict[str, Any]]:
    """Votants d'un noeud de decompte : absent (null), objet {"votant": ...} ou liste de ces noeuds (mises au point : [null, null])."""
    out: list[dict[str, Any]] = []
    for n in liste(noeud):
        if isinstance(n, dict):
            out.extend(v for v in liste(n.get("votant")) if isinstance(v, dict))
    return out


def entier(x: Any) -> int | None:
    try:
        return int(str(texte(x)).strip())
    except (TypeError, ValueError):
        return None


def normaliser(t: Any) -> str:
    s = unicodedata.normalize("NFKD", str(t or "").casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def chemins_votes(c: dict[str, Path]) -> dict[str, Path]:
    return {"votants": c["donnees"] / "votants_2027.json", "scrutins": c["donnees"] / "scrutins_2027.json",
            "liens": c["donnees"] / "liens_votes_2027.json", "brut": c["corpus"] / "votes",
            "acteurs": c["corpus"] / "votes" / "AMO30_acteurs.json.zip"}


# --- Lecture du format officiel ------------------------------------------------------------------------------------

def fichiers_json(archive: Path) -> Iterator[Any]:
    """Contenu JSON de chaque fichier d'une archive, lu en memoire (rien n'est extrait sur le disque)."""
    with zipfile.ZipFile(archive) as z:
        infos = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".json")]
        if len(infos) > FICHIERS_MAX or sum(i.file_size for i in z.infolist()) > DECOMPRESSE_MAX:
            raise ValueError(f"Archive suspecte (trop de fichiers ou trop volumineuse) : {archive.name}")
        for i in infos:
            if i.file_size > FICHIER_JSON_MAX:
                raise ValueError(f"Fichier trop gros dans l'archive : {i.filename}")
            yield json.loads(z.read(i).decode("utf-8-sig"))


def scrutins_de(contenu: Any) -> Iterator[dict[str, Any]]:
    """Scrutins d'un fichier : un fichier par scrutin {"scrutin": {...}}, ou un fichier groupe."""
    if isinstance(contenu, dict):
        if "scrutin" in contenu:
            yield from (s for s in liste(contenu["scrutin"]) if isinstance(s, dict))
        elif "scrutins" in contenu:
            yield from scrutins_de(contenu["scrutins"])
        elif "export" in contenu:
            yield from scrutins_de(contenu["export"])


def acteurs_de(contenu: Any) -> Iterator[dict[str, Any]]:
    """Acteurs d'un fichier : un fichier par acteur {"acteur": {...}}, ou un fichier groupe {"export": {"acteurs": ...}}."""
    if isinstance(contenu, dict):
        if "acteur" in contenu:
            yield from (a for a in liste(contenu["acteur"]) if isinstance(a, dict))
        elif "acteurs" in contenu:
            yield from acteurs_de(contenu["acteurs"])
        elif "export" in contenu:
            yield from acteurs_de(contenu["export"])


def lire_scrutin(s: dict[str, Any], suivis: dict[str, str]) -> dict[str, Any]:
    """Scrutin normalise. `suivis` : identifiant d'acteur -> candidat. Seules les positions des votants suivis sont gardees ;
    les groupes sont gardes en entier (decompte et position majoritaire), leur identifiant est celui de l'organe."""
    leg = texte(s.get("legislature")) or ""
    numero = texte(s.get("numero")) or ""
    type_vote = s.get("typeVote") or {}
    objet = (s.get("objet") or {}).get("libelle") if isinstance(s.get("objet"), dict) else texte(s.get("objet"))
    out = {"id": texte(s.get("uid")), "legislature": leg, "numero": numero, "date": texte(s.get("dateScrutin")),
           "titre": texte(s.get("titre")), "objet": objet,
           "type": {"code": texte(type_vote.get("codeTypeVote")), "libelle": texte(type_vote.get("libelleTypeVote")),
                    "majorite": texte(type_vote.get("typeMajorite"))},
           "sort": texte((s.get("sort") or {}).get("code")),
           "lien": LIEN_SCRUTIN.format(leg=leg, numero=numero) if leg and numero else None,
           "portee_probable": portee_probable(texte(s.get("titre")), objet),
           "groupes": {}, "votes": {}}
    organes = (((s.get("ventilationVotes") or {}).get("organe") or {}).get("groupes") or {})
    for g in liste(organes.get("groupe")):
        ref = texte(g.get("organeRef"))
        vote = g.get("vote") or {}
        d = vote.get("decompteVoix") or {}
        out["groupes"][ref] = {"position": texte(vote.get("positionMajoritaire")), "membres": entier(g.get("nombreMembresGroupe")),
                               "pour": entier(d.get("pour")), "contre": entier(d.get("contre")),
                               "abstention": entier(d.get("abstentions")), "non_votant": entier(d.get("nonVotants"))}
        nominatif = vote.get("decompteNominatif") or {}
        for cle, position in POSITIONS.items():
            for v in votants_de(nominatif.get(cle)):
                acteur = texte(v.get("acteurRef"))
                if acteur in suivis:
                    out["votes"][acteur] = {"position": position, "delegue": texte(v.get("parDelegation")) == "true", "groupe": ref,
                                            # non-votant : MG (membre du gouvernement), PAN (president de l'Assemblee), PSE (president de seance)
                                            **({"cause": texte(v.get("causePositionVote"))} if v.get("causePositionVote") else {})}
    # Mises au point : position que le depute declare avoir voulu donner, publiee apres le scrutin. Le vote enregistre reste
    # tel quel ; l'intention est gardee a cote, jamais a sa place. Un depute absent de toutes les listes (« absent ») peut
    # neanmoins avoir publie une mise au point : cas reel du fichier de la 17e legislature.
    for cle, position in POSITIONS.items():
        for v in votants_de((s.get("miseAuPoint") or {}).get(cle)):
            acteur = texte(v.get("acteurRef"))
            if acteur in suivis:
                out["votes"].setdefault(acteur, {"position": "absent", "delegue": False, "groupe": None})["mise_au_point"] = position
    return out


def portee_probable(titre: str | None, objet: str | None) -> str:
    """Indice gratuit pour l'humain (jamais un verdict) : ce sur quoi porte le scrutin."""
    t = normaliser(f"{titre or ''} {objet or ''}")
    if "motion de censure" in t:
        return "motion"
    if "amendement" in t:
        return "amendement"
    if re.search(r"\barticle\b", t):
        return "article"
    if re.search(r"\bl ensemble\b|\bensemble du\b|\bensemble de la\b", t):
        return "ensemble"
    return "inconnue"


# --- Votants -------------------------------------------------------------------------------------------------------

def lire_votants(chemin: Path) -> dict[str, Any]:
    return B.lire_json(chemin, {"votants": {}})


def ajouter_votant(chemin: Path, candidat: str, an_acteur: str, candidats: set[str] | None = None, note: str | None = None) -> dict[str, Any]:
    if candidats is not None and candidat not in candidats:
        raise ValueError(f"Candidat inconnu : {candidat}")
    if not RE_ACTEUR.match(an_acteur or ""):
        raise ValueError("Identifiant d'acteur attendu au format PA suivi de chiffres (ex. PA1592).")
    data = lire_votants(chemin)
    pris = next((k for k, v in data["votants"].items() if v["an_acteur"] == an_acteur and k != candidat), None)
    if pris:
        raise ValueError(f"{an_acteur} est deja attribue a {pris}.")
    data["votants"][candidat] = {"an_acteur": an_acteur, "confirme_le": B.maintenant(), **({"note": note} if note else {})}
    B.ecrire_json(chemin, data)
    return data["votants"][candidat]


def chercher_acteurs(archive: Path, nom: str, limite: int = 15) -> list[dict[str, Any]]:
    """Acteurs dont le nom contient tous les mots demandes : identifiant, nom, naissance, mandats a l'Assemblee.
    Plusieurs reponses = homonymes : la personne se confirme a la main avant `votes votant`."""
    mots = normaliser(nom).split()
    if not mots:
        raise ValueError("Nom vide.")
    trouves = []
    for contenu in fichiers_json(archive):
        for a in acteurs_de(contenu):
            ident = ((a.get("etatCivil") or {}).get("ident") or {})
            complet = normaliser(f"{texte(ident.get('prenom')) or ''} {texte(ident.get('nom')) or ''}")
            if all(m in complet.split() for m in mots):
                mandats = [m for m in liste((a.get("mandats") or {}).get("mandat")) if texte(m.get("typeOrgane")) == "ASSEMBLEE"]
                trouves.append({"an_acteur": texte(a.get("uid")), "nom": f"{texte(ident.get('prenom'))} {texte(ident.get('nom'))}",
                                "naissance": texte(((a.get("etatCivil") or {}).get("infoNaissance") or {}).get("dateNais")),
                                "mandats_assemblee": [{"legislature": texte(m.get("legislature")), "debut": texte(m.get("dateDebut")),
                                                       "fin": texte(m.get("dateFin"))} for m in mandats]})
    return sorted(trouves, key=lambda x: x["nom"])[:limite]


# --- Import --------------------------------------------------------------------------------------------------------

def empreinte_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(url: str, destination: Path, taille_max: int = TAILLE_MAX, ouvrir=urllib.request.urlopen) -> dict[str, Any]:
    """Telecharge l'archive officielle : https, hote fixe (y compris apres redirection), taille plafonnee, ecriture atomique."""
    def verifier(u: str) -> None:
        p = urlparse(u)
        if p.scheme != "https" or p.hostname != HOTE:
            raise ValueError(f"Adresse refusee (https et {HOTE} seulement) : {u}")
    verifier(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(destination.suffix + ".tmp")
    total = 0
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "boussole-2027 (donnees ouvertes)"})
    with ouvrir(req, timeout=60) as r:
        verifier(r.geturl())
        annonce = int(r.headers.get("Content-Length") or 0)
        if annonce > taille_max:
            raise ValueError(f"Archive trop volumineuse : {annonce} octets (maximum {taille_max}).")
        with temporaire.open("wb") as f:
            for bloc in iter(lambda: r.read(1 << 20), b""):
                total += len(bloc)
                if total > taille_max:
                    f.close()
                    temporaire.unlink(missing_ok=True)
                    raise ValueError("Archive trop volumineuse : telechargement interrompu.")
                h.update(bloc)
                f.write(bloc)
    if not zipfile.is_zipfile(temporaire):
        temporaire.unlink(missing_ok=True)
        raise ValueError("Le fichier telecharge n'est pas une archive zip.")
    temporaire.replace(destination)
    return {"url": url, "taille": total, "sha256": h.hexdigest()}


def importer(c: dict[str, Path], legislature: str, archive: Path | None = None, hors_ligne: bool = False,
             telecharge=telecharger) -> dict[str, Any]:
    """Importe les scrutins d'une legislature. Idempotent : archive inchangee et votants inchanges = rien n'est reecrit."""
    v = chemins_votes(c)
    votants = lire_votants(v["votants"])["votants"]
    if not votants:
        raise ValueError("Aucun votant : declarer d'abord `votes votant --candidat … --an-acteur PA…`.")
    suivis = {x["an_acteur"]: cand for cand, x in votants.items()}
    stockee = v["brut"] / f"Scrutins_L{legislature}.json.zip"
    source: dict[str, Any] = {}
    if archive:
        if not archive.exists():
            raise ValueError(f"Archive introuvable : {archive}")
        stockee = archive
    elif hors_ligne:
        if not stockee.exists():
            raise ValueError(f"Pas d'archive stockee ({stockee}) : lancer sans --hors-ligne pour la telecharger.")
    else:
        source = telecharge(url_scrutins(legislature), stockee)
    empreinte = source.get("sha256") or empreinte_fichier(stockee)
    ancien = B.lire_json(v["scrutins"], {"meta": {"sources": {}}, "scrutins": {}})
    meta_ancienne = (ancien["meta"].get("sources") or {}).get(legislature) or {}
    if (meta_ancienne.get("sha256") == empreinte and meta_ancienne.get("suivis") == sorted(suivis)
            and meta_ancienne.get("version_lecture") == VERSION_LECTURE):
        return {"etat": "inchange", "legislature": legislature, "sha256": empreinte}
    nouveaux: dict[str, Any] = {}
    total = 0
    for contenu in fichiers_json(stockee):
        for s in scrutins_de(contenu):
            total += 1
            r = lire_scrutin(s, suivis)
            if not r["id"]:
                raise ValueError("Scrutin sans identifiant : le format officiel a change, ajuster `lire_scrutin`.")
            if r["votes"]:
                nouveaux[r["id"]] = r
    # Rectifications : une position publiee qui change entre deux imports invalide les liens deja valides (spec, §9).
    rectifications = []
    for sid, anc in ancien["scrutins"].items():
        if anc.get("legislature") != legislature or sid not in nouveaux:
            continue
        for acteur, vote in anc["votes"].items():
            neuf = nouveaux[sid]["votes"].get(acteur)
            if neuf and (neuf["position"], neuf.get("mise_au_point")) != (vote["position"], vote.get("mise_au_point")):
                rectifications.append({"scrutin": sid, "acteur": acteur, "avant": vote["position"], "apres": neuf["position"],
                                       "mise_au_point_avant": vote.get("mise_au_point"), "mise_au_point_apres": neuf.get("mise_au_point")})
    scrutins = {k: x for k, x in ancien["scrutins"].items() if x.get("legislature") != legislature}
    scrutins.update(nouveaux)
    sources = {**ancien["meta"].get("sources", {}), legislature: {
        "url": source.get("url") or str(stockee), "sha256": empreinte, "taille": source.get("taille") or stockee.stat().st_size,
        "scrutins_total": total, "scrutins_suivis": len(nouveaux), "suivis": sorted(suivis), "version_lecture": VERSION_LECTURE,
        "importe_le": B.maintenant()}}
    B.ecrire_json(v["scrutins"], {"meta": {**ancien["meta"], "sources": sources, "rectifications": rectifications[:200],
                                           "licence": "Licence ouverte (Assemblee nationale, data.assemblee-nationale.fr)"},
                                  "scrutins": dict(sorted(scrutins.items()))}, compact=True)
    return {"etat": "importe", "legislature": legislature, "scrutins_total": total, "scrutins_suivis": len(nouveaux),
            "rectifications": len(rectifications), "sha256": empreinte}


# --- Noms des groupes ----------------------------------------------------------------------------------------------

def completer_noms_groupes(c: dict[str, Path]) -> int:
    """Libelle et sigle des groupes vus dans les scrutins, lus dans le fichier officiel des organes (archive AMO30 stockee,
    sans reseau). Renvoie le nombre de groupes ajoutes ; sans archive, les groupes restent connus par leur identifiant."""
    v = chemins_votes(c)
    donnees = B.lire_json(v["scrutins"])
    if not donnees or not v["acteurs"].exists():
        return 0
    connus = donnees["meta"].setdefault("groupes_noms", {})
    voulus = {ref for s in donnees["scrutins"].values() for ref in s["groupes"]} - set(connus)
    if not voulus:
        return 0
    with zipfile.ZipFile(v["acteurs"]) as z:
        for i in z.infolist():
            nom = Path(i.filename).stem
            if "/organe/" in i.filename and nom in voulus and i.file_size <= FICHIER_JSON_MAX:
                o = json.loads(z.read(i).decode("utf-8-sig")).get("organe") or {}
                connus[nom] = {"libelle": texte(o.get("libelle")), "abrege": texte(o.get("libelleAbrege")), "couleur": texte(o.get("couleurAssociee"))}
    B.ecrire_json(v["scrutins"], donnees, compact=True)
    return len({k for k in connus if k in voulus})


# --- Liens vote-mesure (phase 2) -----------------------------------------------------------------------------------

def vue_du_vote(vote: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ce que le lien a vu au moment de sa validation : si cela change (rectification officielle), le lien est a revoir."""
    return None if not vote else {"position": vote["position"], "mise_au_point": vote.get("mise_au_point"), "delegue": vote["delegue"]}


def liens_actifs(journal: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Dernier etat de chaque couple (mesure, scrutin) : un lien remplace le precedent, un retrait l'annule."""
    actifs: dict[tuple[str, str], dict[str, Any]] = {}
    for e in journal:
        cle = (e["uid"], e["scrutin"])
        if e["type"] == "lien":
            actifs[cle] = e
        elif e["type"] == "retrait":
            actifs.pop(cle, None)
    return actifs


class Donnees:
    """Votants, scrutins et liens en memoire, recharges quand un fichier change sur le disque."""

    def __init__(self, c: dict[str, Path]):
        self.c, self.v = c, chemins_votes(c)
        self._mt: tuple = ()
        self.recharger(force=True)

    def _horodatage(self) -> tuple:
        return tuple(self.v[k].stat().st_mtime_ns if self.v[k].exists() else 0 for k in ("votants", "scrutins", "liens"))

    def recharger(self, force: bool = False) -> None:
        mt = self._horodatage()
        if not force and mt == self._mt:
            return
        self.votants = lire_votants(self.v["votants"])["votants"]
        d = B.lire_json(self.v["scrutins"], {"meta": {"sources": {}}, "scrutins": {}})
        self.meta, self.scrutins = d["meta"], d["scrutins"]
        self.journal = B.lire_json(self.v["liens"], {"journal": []})["journal"]
        self.acteur_de = {cand: x["an_acteur"] for cand, x in self.votants.items()}
        self._norm: dict[str, str] = {}
        self._mt = mt

    # --- lecture ---------------------------------------------------------------------------------------------------
    def groupe(self, ref: str | None) -> dict[str, Any]:
        n = (self.meta.get("groupes_noms") or {}).get(ref) or {}
        return {"ref": ref, "libelle": n.get("libelle"), "abrege": n.get("abrege") or ref}

    def vote(self, candidat: str, sid: str) -> dict[str, Any] | None:
        s = self.scrutins.get(sid)
        return (s or {}).get("votes", {}).get(self.acteur_de.get(candidat) or "")

    def etat(self, candidats: dict[str, str]) -> dict[str, Any]:
        par: dict[str, Counter] = {k: Counter() for k in self.votants}
        for s in self.scrutins.values():
            for cand, acteur in self.acteur_de.items():
                if acteur in s["votes"]:
                    par[cand][s["legislature"]] += 1
        sources = self.meta.get("sources") or {}
        return {"votants": [{"candidat": k, "nom": candidats.get(k, k), "an_acteur": self.acteur_de[k], "scrutins": dict(sorted(par[k].items())),
                             "total": sum(par[k].values())} for k in sorted(self.votants, key=lambda x: candidats.get(x, x))],
                "sans_votant": sorted((k for k in candidats if k not in self.votants), key=lambda x: candidats.get(x, x)),
                "legislatures": {k: {"scrutins_total": x.get("scrutins_total"), "scrutins_suivis": x.get("scrutins_suivis"), "importe_le": x.get("importe_le")}
                                 for k, x in sorted(sources.items())},
                "rectifications": len(self.meta.get("rectifications") or []), "licence": self.meta.get("licence")}

    def _texte(self, sid: str) -> str:
        if sid not in self._norm:
            s = self.scrutins[sid]
            self._norm[sid] = normaliser(f"{s.get('titre') or ''} {s.get('objet') or ''}")
        return self._norm[sid]

    def resume(self, sid: str, candidat: str) -> dict[str, Any]:
        s, vote = self.scrutins[sid], self.vote(candidat, sid) or {}
        return {"id": sid, "date": s["date"], "legislature": s["legislature"], "titre": s["titre"], "portee_probable": s["portee_probable"],
                "type": (s["type"] or {}).get("libelle"), "position": vote.get("position"), "mise_au_point": vote.get("mise_au_point"),
                "delegue": vote.get("delegue"), "cause": vote.get("cause"), "groupe": self.groupe(vote.get("groupe"))["abrege"] if vote else None}

    def chercher(self, candidat: str, q: str = "", legislature: str | None = None, portee: str | None = None,
                 position: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """Scrutins que ce candidat a votes : les plus recents d'abord, ou, avec des mots, les plus proches d'abord."""
        acteur = self.acteur_de.get(candidat)
        if not acteur:
            raise ValueError("Ce candidat n'a pas de votes importes (voir `votes votant`).")
        mots = list(dict.fromkeys(w for w in normaliser(q).split() if len(w) > 2))
        trouves: list[tuple[float, str, str]] = []
        for sid, s in self.scrutins.items():
            vote = s["votes"].get(acteur)
            if not vote or (legislature and s["legislature"] != legislature) or (portee and s["portee_probable"] != portee) \
                    or (position and vote["position"] != position):
                continue
            score = 1.0
            if mots:
                t = set(self._texte(sid).split())
                score = sum(m in t for m in mots) / len(mots)
                if score < (1.0 if len(mots) < 3 else .6):
                    continue
            trouves.append((score, s["date"] or "", sid))
        trouves.sort(key=lambda x: (x[1], x[2]), reverse=True)  # le plus recent d'abord
        trouves.sort(key=lambda x: -x[0])                        # puis le plus proche des mots (tri stable)
        deja = Counter(sid for (_, sid) in liens_actifs(self.journal))
        return {"total": len(trouves), "items": [{**self.resume(sid, candidat), "liens": deja.get(sid, 0)} for _, _, sid in trouves[offset:offset + limit]]}

    def detail(self, sid: str, candidat: str) -> dict[str, Any]:
        if sid not in self.scrutins:
            raise KeyError(sid)
        s, vote = self.scrutins[sid], self.vote(candidat, sid)
        g = self.groupe((vote or {}).get("groupe"))
        collectif = (s["groupes"].get((vote or {}).get("groupe")) or {}) if vote else {}
        groupes = sorted(({**self.groupe(ref), **x} for ref, x in s["groupes"].items()), key=lambda x: -(x.get("membres") or 0))
        return {"id": sid, "date": s["date"], "legislature": s["legislature"], "numero": s["numero"], "titre": s["titre"], "objet": s["objet"],
                "type": (s["type"] or {}).get("libelle"), "majorite": (s["type"] or {}).get("majorite"), "sort": s["sort"], "lien": s["lien"],
                "portee_probable": s["portee_probable"], "portee_par_defaut": PORTEE_PAR_DEFAUT.get(s["portee_probable"]),
                "vote": vote, "groupe": {**g, **collectif} if vote else None, "groupes": groupes}

    # --- liens -----------------------------------------------------------------------------------------------------
    def etat_lien(self, e: dict[str, Any], mesure: dict[str, Any] | None) -> tuple[str, list[str]]:
        raisons = []
        if mesure is None or len(mesure["versions"]) != e["version"]:
            raisons.append("mesure_modifiee")
        vote = self.vote(mesure["candidate_id"], e["scrutin"]) if mesure else None
        if vote is None:
            raisons.append("vote_absent")
        elif vue_du_vote(vote) != e.get("vote_vu"):
            raisons.append("vote_rectifie")
        return ("a_revoir" if raisons else "ok"), raisons

    def enrichir(self, e: dict[str, Any], mesures: dict[str, Any]) -> dict[str, Any]:
        m = mesures.get(e["uid"])
        s = self.scrutins.get(e["scrutin"]) or {}
        vote = self.vote(m["candidate_id"], e["scrutin"]) if m else None
        etat, raisons = self.etat_lien(e, m)
        g = (s.get("groupes") or {}).get((vote or {}).get("groupe")) or {}
        return {"id": e["id"], "uid": e["uid"], "titre_mesure": m["versions"][-1]["title"] if m else None, "candidat": m["candidate_id"] if m else None,
                "theme": m["theme_id"] if m else None, "date_lien": e["date"], "version": e["version"], "relation": e["relation"], "portee": e["portee"],
                "note": e.get("note"), "preuve": e.get("preuve"), "etat": etat, "raisons": raisons,
                "scrutin": {"id": e["scrutin"], "date": s.get("date"), "titre": s.get("titre"), "lien": s.get("lien"), "legislature": s.get("legislature"),
                            "type": (s.get("type") or {}).get("libelle")},
                "vote": vote, "groupe": {**self.groupe((vote or {}).get("groupe")), "position": g.get("position")} if vote else None}

    def liens(self, mesures: dict[str, Any], candidat: str | None = None, etat: str | None = None, uid: str | None = None,
              scrutin: str | None = None) -> list[dict[str, Any]]:
        out = []
        for (u, sid), e in liens_actifs(self.journal).items():
            if (uid and u != uid) or (scrutin and sid != scrutin):
                continue
            r = self.enrichir(e, mesures)
            if (candidat and r["candidat"] != candidat) or (etat and r["etat"] != etat):
                continue
            out.append(r)
        return sorted(out, key=lambda r: r["date_lien"], reverse=True)

    def ajouter_lien(self, mesure: dict[str, Any], sid: str, relation: str, portee: str, note: str | None = None,
                     preuve: str | None = None, auteur: str = "local") -> dict[str, Any]:
        self.recharger()
        if relation not in RELATIONS:
            raise ValueError(f"Relation : {', '.join(RELATIONS)}.")
        if portee not in PORTEES:
            raise ValueError(f"Portee : {', '.join(PORTEES)}.")
        if sid not in self.scrutins:
            raise ValueError("Scrutin inconnu.")
        vote = self.vote(mesure["candidate_id"], sid)
        if vote is None:
            raise ValueError("Ce candidat n'a pas de position enregistree dans ce scrutin : rien a relier.")
        note, preuve = (note or "").strip(), (preuve or "").strip()
        if len(note) > NOTE_MAX or len(preuve) > PREUVE_MAX:
            raise ValueError(f"Note : {NOTE_MAX} caracteres au plus ; passage du texte vote : {PREUVE_MAX}.")
        e = {"id": f"lv-{len(self.journal) + 1:06d}", "type": "lien", "date": B.maintenant(), "auteur": auteur, "uid": mesure["uid"],
             "version": len(mesure["versions"]), "scrutin": sid, "relation": relation, "portee": portee,
             **({"note": note} if note else {}), **({"preuve": preuve} if preuve else {}), "vote_vu": vue_du_vote(vote), "origine": "humain"}
        self._ecrire(e)
        return e

    def retirer_lien(self, lien_id: str, auteur: str = "local") -> dict[str, Any]:
        self.recharger()
        e = next((x for x in liens_actifs(self.journal).values() if x["id"] == lien_id), None)
        if e is None:
            raise KeyError(lien_id)
        r = {"id": f"lv-{len(self.journal) + 1:06d}", "type": "retrait", "date": B.maintenant(), "auteur": auteur, "uid": e["uid"],
             "scrutin": e["scrutin"], "lien": lien_id}
        self._ecrire(r)
        return r

    def _ecrire(self, entree: dict[str, Any]) -> None:
        self.journal.append(entree)
        B.ecrire_json(self.v["liens"], {"journal": self.journal})
        self._mt = self._horodatage()

    # --- export ----------------------------------------------------------------------------------------------------
    def pour_export(self, mesures: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Liens a jour seulement (un lien a revoir n'est pas publie ; « sans rapport » non plus), en cles courtes."""
        out: dict[str, list[dict[str, Any]]] = {}
        for r in self.liens(mesures):
            if r["etat"] != "ok" or r["relation"] == "sans_rapport":
                continue
            s, v, g = r["scrutin"], r["vote"], r["groupe"] or {}
            out.setdefault(r["uid"], []).append({
                "s": s["id"], "d": s["date"], "t": (s["titre"] or "")[:220], "p": v["position"], "mp": v.get("mise_au_point"),
                "dl": bool(v["delegue"]), **({"ca": v["cause"]} if v.get("cause") else {}), "g": g.get("abrege"), "gp": g.get("position"),
                "r": r["relation"], "po": r["portee"], "u": s["lien"]})
        for rows in out.values():
            rows.sort(key=lambda x: x["d"] or "", reverse=True)
        return out


# --- Plan (lecture locale) -----------------------------------------------------------------------------------------

def plan(c: dict[str, Path], candidats: dict[str, str] | None = None) -> dict[str, Any]:
    v = chemins_votes(c)
    votants = lire_votants(v["votants"])["votants"]
    donnees = B.lire_json(v["scrutins"], {"meta": {"sources": {}}, "scrutins": {}})
    par_votant: dict[str, Counter] = {k: Counter() for k in votants}
    portees = Counter()
    for s in donnees["scrutins"].values():
        for cand, x in votants.items():
            vote = s["votes"].get(x["an_acteur"])
            if vote:
                par_votant[cand][vote["position"]] += 1
                par_votant[cand]["delegue"] += int(vote["delegue"])
                par_votant[cand]["mise_au_point"] += int("mise_au_point" in vote)
                portees[s["portee_probable"]] += 1
    sans = sorted(k for k in (candidats or {}) if k not in votants)
    return {"votants": {k: {"an_acteur": votants[k]["an_acteur"], "scrutins": sum(n for p, n in par_votant[k].items() if p != "delegue"),
                            **{p: par_votant[k][p] for p in ("pour", "contre", "abstention", "non_votant", "delegue", "mise_au_point")}} for k in votants},
            "sans_votant": sans, "scrutins_importes": len(donnees["scrutins"]), "portees_probables": dict(portees),
            "sources": donnees["meta"].get("sources", {}), "rectifications": len(donnees["meta"].get("rectifications") or [])}


# --- Ligne de commande ---------------------------------------------------------------------------------------------

def noms_candidats(c: dict[str, Path]) -> dict[str, str]:
    if not c["base"].exists():
        return {}
    return {x["id"]: x.get("name") or x["id"] for x in (B.lire_json(c["base"]) or {}).get("candidates", [])}


def executer(c: dict[str, Path], args: Any) -> int:
    v = chemins_votes(c)
    if args.action == "plan":
        p = plan(c, noms_candidats(c))
        print(json.dumps(p, ensure_ascii=False, indent=1))
        if p["sans_votant"]:
            print("\nSans votant declare (pas de mandat a l'Assemblee connu, ou identifiant a chercher) : " + ", ".join(p["sans_votant"]))
        return 0
    if args.action == "chercher":
        trouves = chercher_acteurs(Path(args.acteurs) if args.acteurs else v["acteurs"], args.nom)
        print(json.dumps(trouves, ensure_ascii=False, indent=1))
        if len(trouves) != 1:
            print(f"\n{len(trouves)} reponse(s) : confirmer la bonne personne (naissance, mandats) avant `votes votant`.")
        return 0
    if args.action == "votant":
        r = ajouter_votant(v["votants"], args.candidat, args.an_acteur, set(noms_candidats(c)) or None, args.note)
        print(f"Votant enregistre : {args.candidat} = {r['an_acteur']}. Relancer `votes importer` pour lire ses votes.")
        return 0
    if args.action == "importer":
        with verrou_run(c):
            r = importer(c, str(args.legislature), Path(args.archive) if args.archive else None, args.hors_ligne)
            r["groupes_nommes"] = completer_noms_groupes(c)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    raise ValueError(f"Action inconnue : {args.action}")


def verrou_run(c: dict[str, Path]):
    import boussole_2027 as BO
    return BO.Verrou(c["verrou"])
