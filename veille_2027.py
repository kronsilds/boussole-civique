"""Veille des sources primaires (phase 1 : docs/spec_veille_2027.md). Gratuit, sans LLM.

  python .\\boussole_2027.py veille plan                          # flux declares et file de tri (sans reseau)
  python .\\boussole_2027.py veille decouvrir [ID...] [--ecrire]  # cherche les flux RSS et sitemaps des sites
  python .\\boussole_2027.py veille relever [ID...] [--jours N]   # releve les flux, ajoute les nouveautes a la file
  python .\\boussole_2027.py veille ignorer ID... --motif M       # retire des elements de la file

Chaque candidat du registre (`donnees/candidats_2027.json`) declare ses flux dans `veille` :
`[{"type": "rss"|"sitemap", "url": ..., "filtre": "regex facultative sur l'URL", "note": ...}]`.
Un relevé lit chaque flux et range les pages jamais vues dans la file de tri `donnees/veille_2027.json`
(ignoree par git). Rien n'entre dans le corpus de soi-meme : le tableau de bord (onglet Sources) reprend un element dans
« Ajouter un document » ou l'ignore. Au premier releve d'un flux, tout ce qu'il contient est marque comme vu ; seuls les
articles d'un flux RSS dates des N derniers jours (14 par defaut) vont dans la file (la date de modification d'un sitemap
change a chaque refonte du site : elle ne dit pas ce qui est nouveau). Les candidats retires (`status: retire`) ne sont
plus releves.

YouTube : son robots.txt interdit le flux public des chaines (/feeds/videos.xml) ; il n'est pas releve. Piste si besoin :
l'API YouTube Data officielle (cle gratuite, quota). Les transcriptions restent un depot manuel.

Collecte : robots.txt respecte, une requete par seconde et par hote, client identifie de facon generique, taille lue
plafonnee. Seules les URL http(s) sont suivies.
"""
from __future__ import annotations

import re
import time
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import base_2027 as B
import contributions_2027 as CT
import registre_2027 as R

FORMAT = 1
TYPES_FLUX = ("rss", "sitemap")
STATUTS = ("en_attente", "ajoutee", "ignoree")
MOTIFS_IGNORER = ("hors sujet", "sans proposition", "doublon", "autre")
AGENT = "boussole-civique-veille/1.0 (veille documentaire ; robots.txt respecte)"
TAILLE_MAX = 25_000_000
MAX_VUS = 20_000            # URL retenues par flux (les plus anciennes sont oubliees au-dela)
MAX_SOUS_SITEMAPS = 12
JOURS_DEFAUT = 14
PAUSE = 1.0
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

Lecteur = Callable[[str], bytes]


# --- Reseau -------------------------------------------------------------------------------------------------------

class Client:
    """Lecture polie : robots.txt, pause par hote, taille plafonnee. `lire(url)` rend les octets ou leve une erreur."""

    def __init__(self, pause: float = PAUSE):
        self.pause, self._robots, self._dernier = pause, {}, {}

    def _brut(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "fr"})
        with urllib.request.urlopen(req, timeout=25) as r:
            corps = r.read(TAILLE_MAX + 1)
        if len(corps) > TAILLE_MAX:
            raise ValueError(f"reponse trop grosse (> {TAILLE_MAX // 1_000_000} Mo)")
        return corps

    def _attendre(self, hote: str) -> None:
        reste = self._dernier.get(hote, 0) + self.pause - time.monotonic()
        if reste > 0:
            time.sleep(reste)
        self._dernier[hote] = time.monotonic()

    def autorise(self, url: str) -> bool:
        p = urlparse(url)
        origine = f"{p.scheme}://{p.netloc}"
        if origine not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._attendre(p.netloc)
                rp.parse(self._brut(origine + "/robots.txt").decode("utf-8", "replace").splitlines())
            except Exception:
                rp.parse([])  # robots.txt absent ou illisible : rien d'interdit
            self._robots[origine] = rp
        return self._robots[origine].can_fetch(AGENT, url)

    def robots_sitemaps(self, url: str) -> list[str]:
        p = urlparse(url)
        self.autorise(url)
        return list(self._robots[f"{p.scheme}://{p.netloc}"].site_maps() or [])

    def lire(self, url: str) -> bytes:
        if not re.match(r"^https?://", url):
            raise ValueError("URL http(s) attendue")
        if not self.autorise(url):
            raise PermissionError("interdit par robots.txt")
        self._attendre(urlparse(url).netloc)
        return self._brut(url)


# --- Lecture des flux ---------------------------------------------------------------------------------------------

def date_iso(texte: str | None) -> str | None:
    """Date d'un flux (RFC 822, ISO 8601 ou AAAA-MM-JJ) en AAAA-MM-JJ ; None si illisible."""
    if not texte:
        return None
    texte = texte.strip()
    try:
        return parsedate_to_datetime(texte).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", texte)
    return m.group(1) if m else None


def _txt(el: ET.Element | None) -> str | None:
    return " ".join("".join(el.itertext()).split()) or None if el is not None else None


def lire_rss_tolerant(corps: bytes) -> list[dict[str, Any]]:
    """Repli pour un flux RSS au XML invalide (prefixe non declare...) : lecture des <item> par expressions."""
    texte = corps.decode("utf-8", "replace")
    items = []
    for bloc in re.findall(r"<item\b.*?</item>", texte, re.S | re.I):
        def champ(nom: str) -> str | None:
            m = re.search(rf"<{nom}\b[^>]*>(.*?)</{nom}>", bloc, re.S | re.I)
            if not m:
                return None
            val = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", m.group(1).strip(), flags=re.S)
            return " ".join(unescape(re.sub(r"<[^>]+>", " ", val)).split()) or None
        items.append({"url": champ("link") or champ("guid"), "titre": champ("title"), "date": date_iso(champ("pubDate"))})
    return [x for x in items if x["url"] and re.match(r"^https?://", x["url"])]


def lire_rss(corps: bytes) -> list[dict[str, Any]]:
    """Elements d'un flux RSS 2.0 ou Atom : url, titre, date (repli tolerant si le XML est invalide)."""
    try:
        racine = ET.fromstring(corps)
    except ET.ParseError:
        items = lire_rss_tolerant(corps)
        if items:
            return items
        raise
    items = []
    for it in racine.iter("item"):
        lien = _txt(it.find("link")) or _txt(it.find("guid"))
        items.append({"url": lien, "titre": _txt(it.find("title")), "date": date_iso(_txt(it.find("pubDate")))})
    for e in racine.iter(ATOM + "entry"):
        liens = e.findall(ATOM + "link")
        lien = next((l.get("href") for l in liens if l.get("rel", "alternate") == "alternate"), None)
        lien = lien or (liens[0].get("href") if liens else None)
        date = _txt(e.find(ATOM + "published")) or _txt(e.find(ATOM + "updated"))
        items.append({"url": lien, "titre": _txt(e.find(ATOM + "title")), "date": date_iso(date)})
    return [x for x in items if x["url"] and re.match(r"^https?://", x["url"])]


def lire_sitemap(corps: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(pages, sous-sitemaps) d'un sitemap ou d'un index de sitemaps."""
    racine = ET.fromstring(corps)
    def entrees(balise: str) -> list[dict[str, Any]]:
        return [{"url": _txt(u.find(SITEMAP + "loc")), "titre": None, "date": date_iso(_txt(u.find(SITEMAP + "lastmod")))}
                for u in racine.iter(SITEMAP + balise) if _txt(u.find(SITEMAP + "loc"))]
    return entrees("url"), entrees("sitemap")


def relever_flux(flux: dict[str, Any], lire: Lecteur) -> tuple[str, list[dict[str, Any]]]:
    """(nature lue : « rss » ou « sitemap », elements)."""
    if flux.get("type") not in TYPES_FLUX:
        raise ValueError(f"type de flux inconnu : {flux.get('type')}")
    corps = lire(flux["url"])
    # Le contenu decide (un robots.txt annonce parfois un flux RSS comme sitemap) : urlset/sitemapindex ou RSS/Atom.
    nature = "sitemap" if re.search(rb"<(?:\w+:)?(?:urlset|sitemapindex)\b", corps[:5000]) else "rss"
    if nature == "sitemap":
        items, sous = lire_sitemap(corps)
        # Index : les sous-sitemaps les plus recents d'abord, en nombre limite.
        for s in sorted(sous, key=lambda x: x["date"] or "", reverse=True)[:MAX_SOUS_SITEMAPS]:
            items += lire_sitemap(lire(s["url"]))[0]
    else:
        items = lire_rss(corps)
    if flux.get("filtre"):
        motif = re.compile(flux["filtre"])
        items = [x for x in items if motif.search(x["url"])]
    return nature, items


# --- Etat et file de tri ------------------------------------------------------------------------------------------

def lire_etat(chemin: Path) -> dict[str, Any]:
    data = B.lire_json(chemin) or {}
    data.setdefault("format", FORMAT)
    data.setdefault("flux", {})
    data.setdefault("elements", [])
    return data


def titre_cle(titre: str | None) -> str:
    return re.sub(r"\W+", " ", (titre or "").lower()).strip()


def cle_flux(candidat: str, url: str) -> str:
    return f"{candidat}|{url}"


def urls_connues(c: dict[str, Path], registre: dict[str, Any]) -> set[str]:
    """Liens deja dans le registre ou parmi les sources ajoutees : jamais proposes a nouveau."""
    connues = set()
    for cand in registre.get("candidates", []):
        prog = cand.get("program") or {}
        connues |= {CT.normaliser_url(u) for u in [prog.get("main_url"), *(l.get("url") for l in R.liens_de(cand))] if u}
    for s in (B.lire_json(c["sources"], {"ajouts": []}) or {}).get("ajouts", []):
        if s.get("url"):
            connues.add(CT.normaliser_url(s["url"]))
    return connues


def releve(c: dict[str, Path], ids: list[str] | None = None, jours: int = JOURS_DEFAUT, lire: Lecteur | None = None,
           aujourd_hui: str | None = None) -> dict[str, Any]:
    """Releve les flux des candidats (tous, ou `ids`) ; ajoute les nouveautes a la file. Un flux en erreur n'arrete rien."""
    registre, _ = R.lire_registre(c)
    candidats = [x for x in registre["candidates"] if not ids or x["id"] in ids]
    inconnus = set(ids or []) - {x["id"] for x in candidats}
    if inconnus:
        raise ValueError(f"Candidat(s) inconnu(s) : {', '.join(sorted(inconnus))}")
    lire = lire or Client().lire
    jour = aujourd_hui or B.maintenant()[:10]
    seuil = (datetime.fromisoformat(jour) - timedelta(days=jours)).date().isoformat()
    connues = urls_connues(c, registre)
    bilan: dict[str, Any] = {"le": B.maintenant(), "flux": 0, "erreurs": [], "nouveaux": 0, "ignores_retires": []}
    resultats: list[tuple[dict[str, Any], dict[str, Any], tuple[str, list[dict[str, Any]]] | Exception]] = []
    for cand in candidats:
        if cand.get("status") == "retire":
            if cand.get("veille"):
                bilan["ignores_retires"].append(cand["id"])
            continue
        for flux in cand.get("veille") or []:
            try:
                resultats.append((cand, flux, relever_flux(flux, lire)))
            except Exception as exc:  # reseau, XML, robots : noter et continuer
                resultats.append((cand, flux, exc))
    with CT.Verrou(c["veille"]):
        etat = lire_etat(c["veille"])
        deja = {CT.normaliser_url(e["url"]) for e in etat["elements"]}
        # Meme article sur le site du candidat et sur celui du parti : un seul element (meme candidat, meme titre).
        titres = {(e["candidat"], titre_cle(e.get("titre"))) for e in etat["elements"] if titre_cle(e.get("titre"))}
        for cand, flux, res in resultats:
            bilan["flux"] += 1
            k = cle_flux(cand["id"], flux["url"])
            suivi = etat["flux"].setdefault(k, {"candidat": cand["id"], "type": flux["type"], "url": flux["url"],
                                                "vus": [], "premier_releve": None})
            suivi["releve_le"] = bilan["le"]
            if isinstance(res, Exception):
                suivi["statut"] = f"erreur : {type(res).__name__} {str(res)[:160]}"
                bilan["erreurs"].append(f"{cand['id']} {flux['url']} : {suivi['statut']}")
                continue
            nature, items = res
            premier = suivi["premier_releve"] is None
            vus = set(suivi["vus"])
            nouveaux = []
            for it in items:
                u = CT.normaliser_url(it["url"])
                if u in vus:
                    continue
                vus.add(u)
                suivi["vus"].append(u)
                recent = nature == "rss" and bool(it["date"]) and it["date"] >= seuil
                cle_titre = (cand["id"], titre_cle(it["titre"]))
                if u in connues or u in deja or (premier and not recent) or (cle_titre[1] and cle_titre in titres):
                    continue
                deja.add(u)
                if cle_titre[1]:
                    titres.add(cle_titre)
                nouveaux.append(it)
            suivi["vus"] = suivi["vus"][-MAX_VUS:]
            suivi.update(statut="ok", nature=nature, elements=len(items), premier_releve=suivi["premier_releve"] or bilan["le"])
            for it in sorted(nouveaux, key=lambda x: x["date"] or ""):
                etat["elements"].append({"id": CT._numero(etat["elements"], "v"), "candidat": cand["id"],
                                         "flux": flux["type"], "flux_url": flux["url"], "url": it["url"],
                                         "titre": it["titre"], "date": it["date"], "detecte_le": bilan["le"],
                                         "statut": "en_attente"})
                bilan["nouveaux"] += 1
        etat["dernier_releve"] = {k: v for k, v in bilan.items() if k != "le"} | {"le": bilan["le"]}
        B.ecrire_json(c["veille"], etat)
    return bilan


def traiter(c: dict[str, Path], vid: str, statut: str, **champs: Any) -> dict[str, Any]:
    """Element de la file : « ajoutee » (source_id) ou « ignoree » (motif)."""
    if statut not in STATUTS[1:]:
        raise ValueError("Statut inconnu.")
    if statut == "ignoree" and champs.get("motif") not in MOTIFS_IGNORER:
        raise ValueError(f"Motif requis : {', '.join(MOTIFS_IGNORER)}.")
    with CT.Verrou(c["veille"]):
        etat = lire_etat(c["veille"])
        for e in etat["elements"]:
            if e["id"] == vid:
                if e.get("statut") != "en_attente":
                    raise ValueError("Deja traite.")
                e.update(statut=statut, traitee_le=B.maintenant(), **champs)
                B.ecrire_json(c["veille"], etat)
                return e
    raise KeyError(f"Element de veille inconnu : {vid}")


def en_attente(c: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Elements en attente, par identifiant (pour verifier une reprise depuis le tableau de bord)."""
    return {e["id"]: e for e in lire_etat(c["veille"])["elements"] if e.get("statut") == "en_attente"}


# --- Decouverte des flux ------------------------------------------------------------------------------------------

def _origine(url: str | None) -> str | None:
    if not url or not re.match(r"^https?://", url):
        return None
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def decouvrir_candidat(cand: dict[str, Any], client: Client) -> list[dict[str, Any]]:
    """Propose des flux : liens RSS/Atom declares par le site, sitemaps de robots.txt (ou /sitemap.xml)."""
    trouves: list[dict[str, Any]] = []
    sites = []
    for u in (cand.get("website"), (cand.get("program") or {}).get("main_url")):
        o = _origine(u)
        if o and o not in sites:
            sites.append(o)

    def ajouter(type_: str, url: str, note: str) -> None:
        if url and not any(t["url"] == url for t in trouves):
            trouves.append({"type": type_, "url": url, "note": note})

    for o in sites:
        try:
            html = client.lire(o + "/").decode("utf-8", "replace")
            for balise in re.findall(r"<link\b[^>]*>", html, re.I):
                if re.search(r"rel=[\"']?alternate", balise, re.I) and re.search(r"(rss|atom)\+xml", balise, re.I):
                    href = re.search(r"href=[\"']([^\"']+)", balise, re.I)
                    if href and "comments" not in href.group(1):
                        ajouter("rss", urljoin(o + "/", unescape(href.group(1))), f"flux declare par {o}")
        except Exception:
            pass
        sitemaps = [s for s in client.robots_sitemaps(o + "/") if _origine(s) == o]
        if not sitemaps:
            for chemin in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
                try:
                    corps = client.lire(o + chemin)
                    if b"<urlset" in corps[:2000] or b"<sitemapindex" in corps[:2000]:
                        sitemaps.append(o + chemin)
                        break
                except Exception:
                    continue
        for s in sitemaps[:2]:
            ajouter("sitemap", s, f"sitemap de {o}")
    return trouves


def decouvrir(c: dict[str, Path], ids: list[str] | None, ecrire: bool, client: Client | None = None) -> dict[str, list]:
    registre, _ = R.lire_registre(c)
    client = client or Client()
    propositions: dict[str, list] = {}
    for cand in registre["candidates"]:
        if (ids and cand["id"] not in ids) or cand.get("status") == "retire":
            continue
        declares = {f["url"] for f in cand.get("veille") or []}
        propositions[cand["id"]] = [f for f in decouvrir_candidat(cand, client) if f["url"] not in declares]
    if ecrire and any(propositions.values()):
        registre, _ = R.lire_registre(c)  # relu : la decouverte a pris du temps
        for cand in registre["candidates"]:
            nouveaux = propositions.get(cand["id"]) or []
            if nouveaux:
                cand.setdefault("veille", []).extend({"type": f["type"], "url": f["url"]} for f in nouveaux)
                R.journaliser(registre, "veille_flux", candidat=cand["id"], flux=[f["url"] for f in nouveaux])
        B.ecrire_json(c["candidats"], registre)
    return propositions


# --- Commande -----------------------------------------------------------------------------------------------------

def executer(c: dict[str, Path], args: Any) -> int:
    if args.action == "plan":
        registre, _ = R.lire_registre(c)
        etat = lire_etat(c["veille"])
        for cand in registre["candidates"]:
            flux = cand.get("veille") or []
            marque = " (retire : non releve)" if cand.get("status") == "retire" else ""
            print(f"{cand['id']:<15} {len(flux)} flux{marque}")
            for f in flux:
                s = etat["flux"].get(cle_flux(cand["id"], f["url"])) or {}
                print(f"    {f['type']:<8} {f['url']}  [{s.get('statut') or 'jamais releve'}"
                      f"{', ' + str(s.get('elements')) + ' elements' if s.get('elements') is not None else ''}]")
        attente = [e for e in etat["elements"] if e.get("statut") == "en_attente"]
        print(f"File de tri : {len(attente)} element(s) en attente (onglet Sources du tableau de bord).")
        for e in attente[-20:]:
            print(f"  {e['id']}  {e['candidat']:<15} {e['date'] or '?':<10} {e['url']}  {e.get('titre') or ''}")
        return 0
    if args.action == "decouvrir":
        props = decouvrir(c, args.ids or None, args.ecrire)
        for cid, liste in props.items():
            print(f"{cid}: " + ("aucun flux nouveau" if not liste else ""))
            for f in liste:
                print(f"    {f['type']:<8} {f['url']}  ({f['note']})")
        n = sum(len(v) for v in props.values())
        print(f"{n} flux {'ajoute(s) au registre' if args.ecrire else 'propose(s) ; --ecrire les ajoute au registre'}.")
        return 0
    if args.action == "relever":
        b = releve(c, args.ids or None, args.jours)
        for e in b["erreurs"]:
            print("  " + e)
        if b["ignores_retires"]:
            print(f"  candidats retires non releves : {', '.join(b['ignores_retires'])}")
        print(f"{b['flux']} flux releve(s), {len(b['erreurs'])} en erreur ; {b['nouveaux']} nouveaute(s) dans la file.")
        return 0
    if args.action == "ignorer":
        for vid in args.ids:
            traiter(c, vid, "ignoree", motif=args.motif)
        print(f"{len(args.ids)} element(s) ignore(s).")
        return 0
    raise ValueError(f"Action inconnue : {args.action}")
