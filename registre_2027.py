"""Registre local des candidats et des themes (veille independante, phase 0 : docs/spec_veille_2027.md).

  python .\\boussole_2027.py registre plan [--pull]          # etat du registre et ecarts avec le depot amont (gratuit)
  python .\\boussole_2027.py registre importer [--remplacer]  # amorce depuis data-v2.json (une seule fois)
  python .\\boussole_2027.py registre reprendre ID... | --tous-liens   # reprend des ecarts de l'amont dans le registre
  python .\\boussole_2027.py registre ecarter ID... [--motif M]       # ne plus signaler ces ecarts
  python .\\boussole_2027.py registre ajouter FICHES.json [--source URL]   # candidats tenus a la main (absents de l'amont)

La chaine lit la liste des candidats et leurs liens de programme dans `donnees/candidats_2027.json`, et les themes dans
`donnees/themes_2027.json` (versionnes, tenus a la main ou par `reprendre`). Le depot amont n'est plus qu'un flux de veille :
a chaque run, ses differences avec le registre sont listees dans `donnees/veille_amont_2027.json` (ignore par git), rien
n'est applique sans `reprendre`. S'il disparait, la chaine continue.

Format : un candidat garde la forme d'un candidat de data-v2 (id, first_name, last_name, party, party_short, color,
status, program{main_url, title, format, published_date, thematic_links[]}, ...), pour que l'inventaire du corpus, les
sources ajoutees et l'export restent inchanges. Les themes sont figes : changer un id ou un libelle invalide le cache
d'extraction (programme_corpus_2027.extraction_key).
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

import base_2027 as B

FORMAT = 1
CHAMPS_PROGRAMME = ("main_url", "title", "format", "published_date")
CHAMPS_STATUT = ("status", "status_note", "status_source_url", "declaration_date")
CHAMPS_META = ("election", "inclusion_rule", "inclusion_sources", "other_declared")
TYPES_APPLICABLES = ("candidat_nouveau", "statut", "programme", "lien_nouveau", "lien_retire")
NOTE_THEMES = ("Themes figes : changer un id ou un libelle invalide le cache d'extraction (tout le corpus serait "
               "reextrait). Les 20 themes viennent de l'amont (import du registre).")


# --- Lecture et ecriture ------------------------------------------------------------------------------------------

def fichier_amont(repo_dir: Path) -> Path:
    return repo_dir / "public-data" / "data-v2.json"


def lire_amont(repo_dir: Path) -> dict[str, Any] | None:
    chemin = fichier_amont(repo_dir)
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


def commit_amont(repo_dir: Path) -> str | None:
    try:
        fait = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=False)
    except OSError:
        return None
    if fait.returncode:
        return None
    return fait.stdout.strip() or None


def lire_registre(c: dict[str, Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    registre, themes = B.lire_json(c["candidats"]), B.lire_json(c["themes"])
    if registre is None or themes is None:
        manque = c["candidats"] if registre is None else c["themes"]
        raise ValueError(f"Registre absent ({manque.name}) : lancer « python .\\boussole_2027.py registre importer ».")
    if registre.get("format") != FORMAT or themes.get("format") != FORMAT:
        raise ValueError(f"Format de registre inconnu (attendu {FORMAT}).")
    ids = [str(x.get("id")) for x in registre.get("candidates", [])]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("Registre : identifiants de candidats vides ou en double.")
    if not themes.get("themes"):
        raise ValueError("Registre : aucun theme.")
    return registre, themes


def charger(c: dict[str, Path]) -> dict[str, Any]:
    """Donnees de la chaine (forme de pipeline_scoring_2027.adapt_v2_bundle) lues dans le registre local."""
    from pipeline_scoring_2027 import adapt_v2_bundle
    registre, themes = lire_registre(c)
    bundle = {"version": 2, "themes": copy.deepcopy(themes["themes"]), "candidates": copy.deepcopy(registre["candidates"]),
              "measures": {}, "meta": copy.deepcopy(registre.get("meta", {}))}
    data = adapt_v2_bundle(bundle)
    for cle in ("repository", "adapter_note", "source_generated_at", "source_version"):
        data["meta"].pop(cle, None)
    data["meta"]["source_candidats"] = "registre local (donnees/candidats_2027.json)"
    data["_source_format"] = "registre_2027"
    data.pop("_source_generated_at", None)
    return data


def journaliser(registre: dict[str, Any], action: str, **detail: Any) -> None:
    registre.setdefault("journal", []).append({"le": B.maintenant(), "action": action, **detail})


def importer(c: dict[str, Path], remplacer: bool = False) -> dict[str, Any]:
    """Amorce le registre depuis le depot amont (data-v2.json local, sans reseau)."""
    existants = [p.name for p in (c["candidats"], c["themes"]) if p.exists()]
    if existants and not remplacer:
        raise ValueError(f"Registre deja present ({', '.join(existants)}) : rien n'est ecrase. "
                         "--remplacer reprend tout depuis l'amont (les modifications locales seraient perdues ; "
                         "le fichier est versionne).")
    amont = lire_amont(c["amont"])
    if amont is None:
        raise ValueError(f"{fichier_amont(c['amont'])} absent : rien a importer.")
    origine = {"source": "amont", "fichier": "upstream_repo/public-data/data-v2.json", "commit": commit_amont(c["amont"]),
               "genere_le": amont.get("generated_at"), "importe_le": B.maintenant()}
    candidats = [copy.deepcopy(x) for x in amont.get("candidates", []) if isinstance(x, dict) and x.get("id")]
    registre = {"format": FORMAT, "origine": origine,
                "meta": {k: copy.deepcopy(amont.get("meta", {}).get(k)) for k in CHAMPS_META if k in amont.get("meta", {})},
                "candidates": candidats, "ecarts_ecartes": [], "journal": []}
    journaliser(registre, "importer", candidats=len(candidats), commit=origine["commit"])
    themes = {"format": FORMAT, "note": NOTE_THEMES, "origine": origine, "themes": copy.deepcopy(amont.get("themes", []))}
    B.ecrire_json(c["themes"], themes)
    B.ecrire_json(c["candidats"], registre)
    return {"candidats": len(candidats), "themes": len(themes["themes"]),
            "liens": sum(len(liens_de(x)) for x in candidats), "commit": origine["commit"]}


# --- Comparaison avec l'amont -------------------------------------------------------------------------------------

def liens_de(candidat: dict[str, Any]) -> list[dict[str, Any]]:
    return list((candidat.get("program") or {}).get("thematic_links") or [])


def url_canonique(url: Any) -> str:
    return urldefrag(str(url or ""))[0]


def id_ecart(type_: str, candidat: str | None, cle: Any) -> str:
    brut = json.dumps([type_, candidat, cle], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:10]


def nom_de(candidat: dict[str, Any]) -> str:
    return " ".join(x for x in (candidat.get("first_name"), candidat.get("last_name")) if x) or str(candidat.get("id"))


def ecarts(registre: dict[str, Any], themes: dict[str, Any], amont: dict[str, Any]) -> list[dict[str, Any]]:
    """Differences entre l'amont et le registre, du point de vue « que propose l'amont » (aucune n'est appliquee)."""
    trouves: list[dict[str, Any]] = []

    def ajouter(type_: str, candidat: str | None, cle: Any, **detail: Any) -> None:
        trouves.append({"id": id_ecart(type_, candidat, cle), "type": type_, "candidat": candidat, **detail})

    locaux = {str(t.get("id")): t.get("label") for t in themes.get("themes", [])}
    distants = {str(t.get("id")): t.get("label") for t in amont.get("themes", []) if isinstance(t, dict)}
    if locaux != distants:
        ajouter("themes", None, sorted(distants.items()),
                ajoutes=sorted(set(distants) - set(locaux)), retires=sorted(set(locaux) - set(distants)),
                renommes=sorted(k for k in set(locaux) & set(distants) if locaux[k] != distants[k]),
                note="Non applicable automatiquement : changer les themes reextrait tout le corpus.")
    reg = {str(x["id"]): x for x in registre.get("candidates", [])}
    amo = {str(x["id"]): x for x in amont.get("candidates", []) if isinstance(x, dict) and x.get("id")}
    for cid in sorted(set(amo) - set(reg)):
        x = amo[cid]
        ajouter("candidat_nouveau", cid, cid, nom=nom_de(x), statut=x.get("status"), liens=len(liens_de(x)),
                source=x.get("status_source_url"))
    for cid in sorted(set(reg) - set(amo)):
        if reg[cid].get("origine") == "registre":
            continue  # candidat ajoute localement (registre ajouter) : son absence de l'amont est normale
        ajouter("candidat_absent", cid, cid, nom=nom_de(reg[cid]),
                note="Absent de l'amont (retire de sa liste ?). Non applicable : changer le statut a la main si besoin.")
    for cid in sorted(set(reg) & set(amo)):
        r, a = reg[cid], amo[cid]
        if r.get("status") != a.get("status"):
            ajouter("statut", cid, a.get("status"), avant=r.get("status"), apres=a.get("status"),
                    note_amont=a.get("status_note"), source=a.get("status_source_url"))
        pr, pa = r.get("program") or {}, a.get("program") or {}
        avant = {k: pr.get(k) for k in CHAMPS_PROGRAMME}
        apres = {k: pa.get(k) for k in CHAMPS_PROGRAMME}
        if avant != apres:
            ajouter("programme", cid, apres, avant=avant, apres=apres)
        lr = {url_canonique(l.get("url")): l for l in liens_de(r)}
        la = {url_canonique(l.get("url")): l for l in liens_de(a)}
        for url in sorted(set(la) - set(lr)):
            ajouter("lien_nouveau", cid, url, lien=la[url])
        for url in sorted(set(lr) - set(la)):
            ajouter("lien_retire", cid, url, lien=lr[url])
    ecartes = set(registre.get("ecarts_ecartes") or [])
    for e in trouves:
        e["ecarte"] = e["id"] in ecartes
    return trouves


def veiller_amont(c: dict[str, Path], pull: bool) -> dict[str, Any]:
    """Met a jour le clone amont si demande (un echec n'arrete rien), compare au registre, ecrit veille_amont_2027.json."""
    resume: dict[str, Any] = {"le": B.maintenant(), "pull": None, "commit": None, "ecarts": []}
    if not fichier_amont(c["amont"]).exists():
        resume["pull"] = "depot amont absent : pas de veille amont"
        return resume
    if pull:
        from update_corpus_2027 import git_pull
        try:
            resume["pull"] = git_pull(c["amont"])
        except (OSError, RuntimeError) as exc:
            resume["pull"] = f"echec de la mise a jour de l'amont ({exc}) : comparaison avec la copie locale"
    registre, themes = lire_registre(c)
    amont = lire_amont(c["amont"]) or {}
    resume.update(commit=commit_amont(c["amont"]), genere_le=amont.get("generated_at"),
                  ecarts=ecarts(registre, themes, amont))
    B.ecrire_json(c["veille_amont"], resume)
    return resume


def resume_ecarts(liste: list[dict[str, Any]]) -> str:
    actifs = [e for e in liste if not e.get("ecarte")]
    if not actifs:
        return "aucun ecart a examiner"
    compte: dict[str, int] = {}
    for e in actifs:
        compte[e["type"]] = compte.get(e["type"], 0) + 1
    return f"{len(actifs)} ecart(s) a examiner (" + ", ".join(f"{k} {v}" for k, v in sorted(compte.items())) + \
        ") : « boussole_2027.py registre plan »"


# --- Reprise et refus ---------------------------------------------------------------------------------------------

def appliquer(registre: dict[str, Any], amont: dict[str, Any], ecart: dict[str, Any]) -> None:
    """Reprend un ecart de l'amont dans le registre (modifie `registre` en place)."""
    t, cid = ecart["type"], ecart["candidat"]
    if t not in TYPES_APPLICABLES:
        raise ValueError(f"Ecart {ecart['id']} ({t}) : non applicable automatiquement. {ecart.get('note', '')}".strip())
    amo = {str(x["id"]): x for x in amont.get("candidates", []) if isinstance(x, dict) and x.get("id")}
    if t == "candidat_nouveau":
        registre["candidates"].append(copy.deepcopy(amo[cid]))
        return
    cand = next(x for x in registre["candidates"] if str(x["id"]) == cid)
    if t == "statut":
        for k in CHAMPS_STATUT:
            if k in amo[cid]:
                cand[k] = copy.deepcopy(amo[cid][k])
    elif t == "programme":
        prog = cand.setdefault("program", {})
        prog.update(copy.deepcopy(ecart["apres"]))
    elif t == "lien_nouveau":
        cand.setdefault("program", {}).setdefault("thematic_links", []).append(copy.deepcopy(ecart["lien"]))
    elif t == "lien_retire":
        url = url_canonique(ecart["lien"].get("url"))
        prog = cand.get("program") or {}
        prog["thematic_links"] = [l for l in liens_de(cand) if url_canonique(l.get("url")) != url]


def reprendre(c: dict[str, Path], ids: list[str], tous_liens: bool = False) -> list[dict[str, Any]]:
    registre, themes = lire_registre(c)
    amont = lire_amont(c["amont"])
    if amont is None:
        raise ValueError("Depot amont absent : rien a reprendre.")
    liste = ecarts(registre, themes, amont)
    par_id = {e["id"]: e for e in liste}
    inconnus = [i for i in ids if i not in par_id]
    if inconnus:
        raise ValueError(f"Ecart(s) inconnu(s) ou deja repris : {', '.join(inconnus)} (relancer « registre plan »).")
    choisis = [par_id[i] for i in ids]
    if tous_liens:
        choisis += [e for e in liste if e["type"] == "lien_nouveau" and not e["ecarte"] and e not in choisis]
    for e in choisis:
        appliquer(registre, amont, e)
    for e in choisis:
        journaliser(registre, "reprendre", ecart=e["id"], type=e["type"], candidat=e["candidat"],
                    url=(e.get("lien") or {}).get("url"), commit=commit_amont(c["amont"]))
    if choisis:
        B.ecrire_json(c["candidats"], registre)
    return choisis


def ecarter(c: dict[str, Path], ids: list[str], motif: str | None = None) -> int:
    registre, _ = lire_registre(c)
    deja = registre.setdefault("ecarts_ecartes", [])
    nouveaux = [i for i in ids if i not in deja]
    deja.extend(nouveaux)
    for i in nouveaux:
        journaliser(registre, "ecarter", ecart=i, motif=motif)
    if nouveaux:
        B.ecrire_json(c["candidats"], registre)
    return len(nouveaux)


# --- Retrait d'un candidat ---------------------------------------------------------------------------------------

def cle_nom(nom: Any) -> str:
    """Nom sans accents ni casse ni ponctuation, pour rapprocher une fiche d'une ligne des autres declares."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(nom or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


def ajouter_candidat(c: dict[str, Path], fiches: list[dict[str, Any]], source: str | None = None) -> list[str]:
    """Ajoute des candidats tenus a la main (absents de l'amont), marques `origine: registre` ; chacun quitte la liste des
    autres declares (`meta.other_declared`, rapprochement par le nom). L'ajout est gratuit : l'extraction et la lecture
    de ses documents sont payees au run plafonne suivant. Tout est verifie avant d'ecrire (rien n'est ecrit sur une erreur)."""
    import re
    registre, themes = lire_registre(c)
    ids = {str(x["id"]) for x in registre["candidates"]}
    ids_themes = {str(t["id"]) for t in themes["themes"]}
    noms = {}
    for f in fiches:
        cid = str(f.get("id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", cid):
            raise ValueError(f"Identifiant invalide : {cid!r} (minuscules, chiffres, tirets).")
        if cid in ids:
            raise ValueError(f"Candidat deja present : {cid}")
        for champ in ("first_name", "last_name", "party", "party_short", "status"):
            if not f.get(champ):
                raise ValueError(f"{cid} : champ {champ} manquant.")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(f.get("color") or "")):
            raise ValueError(f"{cid} : couleur #RRGGBB attendue.")
        if not re.match(r"^https?://", str(f.get("status_source_url") or "")):
            raise ValueError(f"{cid} : status_source_url (URL qui atteste la candidature) attendue.")
        programme = f.get("program") or {}
        liens = [programme.get("main_url")] + [l.get("url") for l in programme.get("thematic_links", [])]
        if not programme.get("main_url") or not all(re.match(r"^https?://", str(u or "")) for u in liens):
            raise ValueError(f"{cid} : program.main_url et les liens thematiques doivent etre des URL http(s).")
        inconnus = {l.get("theme") for l in programme.get("thematic_links", [])} - ids_themes
        if inconnus:
            raise ValueError(f"{cid} : themes inconnus {sorted(map(str, inconnus))}.")
        ids.add(cid)
        noms[cid] = cle_nom(f"{f['first_name']} {f['last_name']}")
    autres = registre.get("meta", {}).get("other_declared") or []
    for f in fiches:
        cid = str(f["id"])
        fiche = {**copy.deepcopy(f), "origine": "registre"}
        retire_de = [o for o in autres if cle_nom(o.get("name")) == noms[cid]]
        for o in retire_de:
            autres.remove(o)
            fiche.setdefault("programme_recherche", o.get("programme_recherche"))
        registre["candidates"].append(fiche)
        journaliser(registre, "candidat_ajoute", candidat=cid, nom=f"{f['first_name']} {f['last_name']}",
                    programme=(f.get("program") or {}).get("main_url"), source=source,
                    retire_des_autres_declares=bool(retire_de))
    registre["candidates"].sort(key=lambda x: str(x["id"]))
    B.ecrire_json(c["candidats"], registre)
    return [str(f["id"]) for f in fiches]


def retrait(c: dict[str, Path], cid: str, date: str | None = None, source: str | None = None,
            soutien: str | None = None, note: str | None = None, annuler: bool = False) -> dict[str, Any]:
    """Candidat qui se retire (statut « retire », date, source, candidat soutenu) ; --annuler retablit le statut d'avant.
    Seul un retrait officiel compte (annonce du candidat ou decision de son parti), pas une intention."""
    import re
    registre, _ = lire_registre(c)
    cand = next((x for x in registre["candidates"] if str(x["id"]) == cid), None)
    if cand is None:
        raise ValueError(f"Candidat inconnu : {cid}")
    if annuler:
        if cand.get("status") != "retire":
            raise ValueError(f"{cid} n'est pas retire.")
        avant = (cand.get("retrait") or {}).get("statut_avant") or "declare"
        cand["status"] = avant
        ancien = cand.pop("retrait", None)
        journaliser(registre, "retrait_annule", candidat=cid, statut=avant, retrait=ancien)
    else:
        if cand.get("status") == "retire":
            raise ValueError(f"{cid} est deja retire (--annuler d'abord pour corriger).")
        if not (date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
            raise ValueError("Date du retrait au format AAAA-MM-JJ.")
        if not (source and re.match(r"^https?://", source)):
            raise ValueError("Source du retrait : URL http(s) attendue.")
        ids = {str(x["id"]) for x in registre["candidates"]}
        if soutien and (soutien not in ids or soutien == cid):
            raise ValueError(f"Candidat soutenu inconnu : {soutien}")
        cand["retrait"] = {"date": date, "source_url": source, "soutien": soutien or None, "note": note or None,
                           "statut_avant": cand.get("status")}
        cand["status"] = "retire"
        journaliser(registre, "retrait", candidat=cid, date=date, soutien=soutien, source=source)
    B.ecrire_json(c["candidats"], registre)
    return cand


# --- Commande -----------------------------------------------------------------------------------------------------

def decrire(e: dict[str, Any]) -> str:
    t = e["type"]
    if t in ("lien_nouveau", "lien_retire"):
        l = e["lien"]
        detail = f"{l.get('url')}  [{l.get('theme') or '-'}] {l.get('title') or ''}"
    elif t == "statut":
        detail = f"{e['avant']} -> {e['apres']}  {e.get('source') or ''}"
    elif t == "programme":
        detail = ", ".join(f"{k}: {e['avant'].get(k)} -> {e['apres'].get(k)}" for k in CHAMPS_PROGRAMME
                           if e["avant"].get(k) != e["apres"].get(k))
    elif t == "candidat_nouveau":
        detail = f"{e['nom']} ({e['statut']}, {e['liens']} liens)  {e.get('source') or ''}"
    elif t == "themes":
        detail = f"ajoutes {e['ajoutes']}, retires {e['retires']}, renommes {e['renommes']}"
    else:
        detail = e.get("nom") or ""
    return f"{e['id']}  {t:<16} {e['candidat'] or '-':<15} {detail}{'  (ecarte)' if e.get('ecarte') else ''}"


def executer(c: dict[str, Path], args: Any) -> int:
    if args.action == "importer":
        r = importer(c, args.remplacer)
        print(f"Registre ecrit : {r['candidats']} candidats, {r['liens']} liens thematiques, {r['themes']} themes "
              f"(amont {str(r['commit'] or '?')[:7]}) -> {c['candidats'].name}, {c['themes'].name}.")
        return 0
    if args.action == "plan":
        registre, themes = lire_registre(c)
        statuts: dict[str, int] = {}
        for x in registre["candidates"]:
            statuts[str(x.get("status"))] = statuts.get(str(x.get("status")), 0) + 1
        liens = sum(len(liens_de(x)) for x in registre["candidates"])
        print(f"Registre : {len(registre['candidates'])} candidats {statuts}, {liens} liens thematiques, "
              f"{len(themes['themes'])} themes ; {len(registre.get('journal', []))} operation(s) au journal.")
        veille = veiller_amont(c, args.pull)
        print(f"Amont : {veille['pull'] or 'copie locale (sans --pull)'} ; commit {str(veille['commit'] or '?')[:7]}.")
        visibles = [e for e in veille["ecarts"] if args.tout or not e["ecarte"]]
        for e in visibles:
            print("  " + decrire(e))
        print(resume_ecarts(veille["ecarts"]).split(" : ")[0] + ".")
        if any(not e["ecarte"] for e in veille["ecarts"]):
            print("Reprendre : « registre reprendre ID... » (ou --tous-liens) ; ne plus signaler : « registre ecarter ID... ».")
        return 0
    if args.action == "reprendre":
        if not args.ids and not args.tous_liens:
            raise ValueError("Indiquer des identifiants d'ecart ou --tous-liens.")
        faits = reprendre(c, args.ids, args.tous_liens)
        for e in faits:
            print("  repris " + decrire(e))
        print(f"{len(faits)} ecart(s) repris dans {c['candidats'].name} ; pris en compte au prochain run de la chaine.")
        return 0
    if args.action == "ecarter":
        n = ecarter(c, args.ids, args.motif)
        print(f"{n} ecart(s) ecarte(s) : ils ne sont plus signales.")
        return 0
    if args.action == "ajouter":
        fiches = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
        fiches = fiches if isinstance(fiches, list) else [fiches]
        faits = ajouter_candidat(c, fiches, args.source)
        print(f"{len(faits)} candidat(s) ajoute(s) au registre : {', '.join(faits)}. Gratuit ; leurs documents seront "
              "collectes, extraits et lus au prochain run plafonne (mise-a-jour --complet --max-cost X).")
        return 0
    if args.action == "retrait":
        cand = retrait(c, args.id, args.date, args.source, args.soutien, args.note, args.annuler)
        if args.annuler:
            print(f"Retrait de {args.id} annule : statut {cand['status']}.")
        else:
            r = cand["retrait"]
            print(f"{args.id} retire le {r['date']}" + (f", soutient {r['soutien']}" if r["soutien"] else "") +
                  " ; ses flux ne sont plus releves, ses mesures restent dans la base.")
        return 0
    raise ValueError(f"Action inconnue : {args.action}")
