"""Tableau de bord local du pipeline unifie (spec_pipeline_unifie_2027.md, section 7).

  python .\\tableau_de_bord_2027.py            # http://127.0.0.1:8765
  python .\\boussole_2027.py tableau-de-bord   # equivalent

Ecoute uniquement sur 127.0.0.1. Ecrit seulement decisions_2027.json, sources_2027.json et les fichiers deposes
(corpus_programmes/depots/). Ne lit jamais .env. Le seul run lancable depuis la page est la mise a jour gratuite
(calculs, file, export, bilan) ; aucun appel payant n'est possible d'ici.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import re
import threading
import traceback
from collections import Counter
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import base_2027 as B
import boussole_2027 as BO
import descripteurs_2027 as D
import questionnaire_2027 as Q

PAGE = Path(__file__).parent / "web" / "tableau_de_bord_2027.html"
TYPES_SOURCE = ("programme", "entretien", "discours", "communique", "tribune", "video_transcription", "autre")
MOTIFS_REJET = ("pas une mesure", "hors programme", "doublon", "mauvaise attribution", "citation introuvable", "autre")
EXTENSIONS = {".pdf": "application/pdf", ".html": "text/html", ".htm": "text/html", ".txt": "text/plain",
              ".md": "text/markdown", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
TAILLE_MAX = 50 * 1024 * 1024
LIBELLES_MOTIFS = {
    "mesure_modifiee": "Mesure modifiée", "decision_a_revoir": "Décision à revoir",
    "rapprochement_incertain": "Rapprochement incertain", "deplacement_fort": "Déplacement fort",
    "axe_perdu_ou_gagne": "Axe perdu ou gagné", "nouvelle_mesure": "Nouvelle mesure", "confiance_basse": "Confiance basse",
    "divergence_lectures": "Lectures divergentes (initialisation)", "non_reprise": "Non reprise"}


def normal(texte: Any) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(texte or "").casefold()).split())


class Etat:
    """Base, decisions et export precedent en memoire ; rechargement si les fichiers changent sur le disque."""

    def __init__(self, racine: Path):
        self.racine = racine
        self.c = BO.chemins(argparse.Namespace(racine=str(racine)))
        self.c["manifeste"] = self.c["corpus"] / "manifest.json"
        self.c["depots"] = self.c["corpus"] / "depots"
        self.verrou = threading.Lock()
        self.job: dict[str, Any] = {"etat": "aucun"}
        self._mtimes: dict[str, float] = {}
        self.base: dict[str, Any] = {}
        self.decisions: list[dict[str, Any]] = []
        self.precedent: dict[str, dict[str, Any]] = {}
        self.recharger(force=True)

    def recharger(self, force: bool = False) -> None:
        mt = {k: self.c[k].stat().st_mtime if self.c[k].exists() else 0 for k in ("base", "decisions", "export")}
        if not force and mt == self._mtimes:
            return
        self.base = BO.charger_base(self.c)
        self.decisions = B.lire_json(self.c["decisions"], [])
        self.precedent = BO.export_precedent(self.c, self.base)
        self.par_uid = {m["uid"]: m for m in self.base["mesures"]}
        self.noms = {c["id"]: c.get("name") or c["id"] for c in self.base.get("candidates", [])}
        self.themes = {t["id"]: t.get("label") or t["id"] for t in self.base.get("themes", [])}
        self._mtimes = mt

    # --- lecture ---------------------------------------------------------------------------------------------------
    def resume(self, m: dict[str, Any]) -> dict[str, Any]:
        v = m["versions"][-1]
        return {"uid": m["uid"], "c": m["candidate_id"], "candidat": self.noms.get(m["candidate_id"], m["candidate_id"]),
                "t": m["theme_id"], "theme": self.themes.get(m["theme_id"], m["theme_id"]), "title": v["title"],
                "statut": m["statut"], "version": v["n"], "file": m.get("file") or [],
                "eco": (m.get("calculs") or {}).get("axes", {}).get("eco"), "annotee": bool(m.get("annotation"))}

    def etat(self) -> dict[str, Any]:
        runs = sorted(self.c["runs"].glob("*.json")) if self.c["runs"].exists() else []
        dernier = B.lire_json(runs[-1]) if runs else None
        md = runs[-1].with_suffix(".md").read_text(encoding="utf-8") if runs and runs[-1].with_suffix(".md").exists() else ""
        # Dernier batch envoye (annotation ou complement), lu localement : pas d'appel.
        etats = [f for f in [self.c["batch_annotation"], *self.c["donnees"].glob("complement_*_batch_2027.json")] if f.exists()]
        dernier_batch = max(etats, key=lambda f: f.stat().st_mtime) if etats else None
        batch = {**(B.lire_json(dernier_batch) or {}), "fichier": dernier_batch.name} if dernier_batch else {}
        batch.pop("lots", None)  # volumineux, inutile a la page
        sources = B.lire_json(self.c["sources"], {"ajouts": []})
        return {
            "mesures": dict(Counter(m["statut"] for m in self.base["mesures"])),
            "file": dict(Counter(f["motif"] for m in self.base["mesures"] for f in m.get("file") or [])),
            "libelles_motifs": LIBELLES_MOTIFS, "decisions": len(self.decisions),
            "decisions_non_appliquees": sum(d["date"] >= (self.base["meta"].get("calcule_le") or "") for d in self.decisions),
            "base_mise_a_jour": self.base["meta"].get("calcule_le") or self.base["meta"].get("mis_a_jour_le"), "dernier_run": dernier, "dernier_run_md": md,
            "nouveautes": B.lire_json(self.c["nouveautes"]),
            "batch": {k: batch.get(k) for k in ("batch_id", "status", "submitted_at", "collected_at", "estimate", "cost", "fichier")} if batch else None,
            "sources_en_attente": sum(s.get("statut") == "en_attente" for s in sources.get("ajouts", [])),
            "run_en_cours": self.c["verrou"].exists(), "job": self.job,
            "candidats": self.noms, "themes": self.themes,
        }

    def file(self, motif: str | None, candidat: str | None, theme: str | None, offset: int, limit: int) -> dict[str, Any]:
        lignes = []
        for m in self.base["mesures"]:
            entrees = [f for f in m.get("file") or [] if not motif or f["motif"] == motif]
            if not entrees or (candidat and m["candidate_id"] != candidat) or (theme and m["theme_id"] != theme):
                continue
            lignes.append((min(f["priorite"] for f in entrees), min(f["depuis"] for f in entrees), m))
        lignes.sort(key=lambda x: (x[0], x[1], x[2]["uid"]))
        return {"total": len(lignes), "items": [self.resume(m) for _, _, m in lignes[offset:offset + limit]]}

    def recherche(self, q: str, candidat: str | None, theme: str | None, statut: str | None, limit: int) -> dict[str, Any]:
        mots = normal(q).split()
        out = []
        for m in self.base["mesures"]:
            if (candidat and m["candidate_id"] != candidat) or (theme and m["theme_id"] != theme) or (statut and m["statut"] != statut):
                continue
            v = m["versions"][-1]
            if mots:
                texte = normal(f"{v['title']} {v['description']} {m['uid']}")
                if not all(w in texte for w in mots):
                    continue
            out.append(m)
        return {"total": len(out), "items": [self.resume(m) for m in out[:limit]]}

    def voisins(self, m: dict[str, Any], n: int = 5) -> list[dict[str, Any]]:
        ref = normal(f"{m['versions'][-1]['title']} {m['versions'][-1]['description']}")
        scores = []
        for o in self.base["mesures"]:
            if o is m or o["candidate_id"] != m["candidate_id"] or o["statut"] in ("rejetee", "remplacee"):
                continue
            texte = normal(f"{o['versions'][-1]['title']} {o['versions'][-1]['description']}")
            scores.append((difflib.SequenceMatcher(None, ref, texte).quick_ratio(), o))
        scores.sort(key=lambda x: -x[0])
        precis = [(difflib.SequenceMatcher(None, ref, normal(f"{o['versions'][-1]['title']} {o['versions'][-1]['description']}")).ratio(), o)
                  for _, o in scores[:30]]
        precis.sort(key=lambda x: -x[0])
        return [{**self.resume(o), "similarite": round(s, 2)} for s, o in precis[:n]]

    def fiche(self, uid: str) -> dict[str, Any]:
        m = self.par_uid.get(uid)
        if not m:
            raise KeyError(uid)
        decisions = [d for d in self.decisions if d["uid"] == uid]
        p, etat = B.vue(m, sorted(decisions, key=lambda d: d["date"]))
        details = p.get("score_details") or {}
        a = m.get("annotation")
        reponses = {**(a or {}).get("reponses", {}), **etat["corrections"]} if a else None
        eco = details.get("eco") or {}
        return {
            **self.resume(m), "versions": m["versions"], "affichage": m.get("affichage"),
            "description": m["versions"][-1]["description"],
            "sources": [{"quote": s.get("quote"), "page": s.get("page"), "url": s.get("source_url") or p.get("source_url"),
                         "titre": s.get("source_title") or p.get("source_title"), "date": s.get("source_date")}
                        for s in m["versions"][-1]["sources"]] or [{"url": p.get("source_url"), "titre": p.get("source_title")}],
            "annotation": {"reponses": reponses, "confiances": a.get("confiances"), "note": a.get("note"),
                           "modele": a.get("modele"), "version": a.get("version") or "descripteurs",
                           "corrigees": sorted(etat["corrections"])} if a else None,
            "explications": (m.get("calculs") or {}).get("explications") or {},
            "axes": {k: (p.get("axes") or {}).get(k) for k in ("eco", "soc", "sov", "ouverture", "ecolo", "rupture")},
            "confiances_axes": {k: (details.get(k) or {}).get("confidence") for k in ("eco", "soc", "sov", "ouverture", "ecolo")},
            "methodes_axes": {k: (details.get(k) or {}).get("method") for k in ("eco", "soc", "sov", "ouverture", "ecolo")},
            "eco_avant": eco.get("previous_value"), "explication_eco": eco.get("rationale") if eco.get("method") == "descripteurs-formule" else None,
            "ideologie": p.get("ideology"), "importance": p.get("importance"),
            "categories": {k: (p.get("axes") or {}).get(k) for k in ("legal_instrument", "cost_estimate")},
            "faisabilite": p.get("feasibility"), "precision": (m.get("affichage") or {}).get("precision"),
            "publie": self.precedent.get(uid), "etat_relecture": etat, "decisions": decisions,
            "voisins": self.voisins(m), "a_annoter": bool(m.get("a_annoter")),
            "rapprochement": {**m["rapprochement"], "cible_resume": self.resume(self.par_uid[m["rapprochement"]["cible"]])
                              if m["rapprochement"].get("cible") in self.par_uid else None} if m.get("rapprochement") else None,
            "rapprochements": m.get("rapprochements") or [],
        }

    def sources(self) -> dict[str, Any]:
        manifeste = B.lire_json(self.c["manifeste"], {"documents": {}})
        nb = Counter()
        for m in self.base["mesures"]:
            for s in m["versions"][-1]["sources"]:
                nb[s.get("document_id")] += 1
        docs = []
        for d in (manifeste.get("documents") or {}).values():
            b = (d.get("bindings") or [{}])[0]
            docs.append({"id": d["id"], "url": d.get("url"), "statut": d.get("status"), "candidate_id": b.get("candidate_id"),
                         "titre": b.get("title"), "type": b.get("role"), "date": b.get("published_date"),
                         "format": d.get("format"), "mesures": nb.get(d["id"], 0), "origine": "corpus"})
        ajouts = B.lire_json(self.c["sources"], {"ajouts": []}).get("ajouts", [])
        return {"documents": sorted(docs, key=lambda x: (x["candidate_id"] or "", x["date"] or "")), "ajouts": ajouts,
                "types": TYPES_SOURCE}

    # --- ecriture --------------------------------------------------------------------------------------------------
    def _pas_de_run(self) -> None:
        if self.c["verrou"].exists():
            raise RuntimeError("Un run est en cours : reessayer dans un instant.")

    def decider(self, corps: dict[str, Any]) -> dict[str, Any]:
        with self.verrou:
            self._pas_de_run()
            self.recharger()
            valeur = corps.get("valeur")
            d = B.nouvelle_decision(self.decisions, self.base, corps.get("uid"), corps.get("type"), corps.get("champ"),
                                    valeur, corps.get("cible"), corps.get("motif"))
            B.ecrire_json(self.c["decisions"], self.decisions)
            self._mtimes["decisions"] = self.c["decisions"].stat().st_mtime
            # Effet immediat sur la fiche et sa file ; la base et l'export sont recalcules par « Appliquer ».
            m = self.par_uid[d["uid"]]
            mini = {"mesures": [m]}
            vues = B.calculer(mini, [x for x in self.decisions if x["uid"] == m["uid"]])
            B.construire_file(mini, vues, self.precedent)
            return {"decision": d, "fiche": self.fiche(d["uid"])}

    def ajouter_source(self, corps: dict[str, Any]) -> dict[str, Any]:
        cand = corps.get("candidate_id")
        if cand not in self.noms:
            raise ValueError("Candidat inconnu.")
        if corps.get("type") not in TYPES_SOURCE:
            raise ValueError("Type de source inconnu.")
        url, fichier = (corps.get("url") or "").strip(), corps.get("fichier")
        if bool(url) == bool(fichier):
            raise ValueError("Donner soit une URL, soit un fichier.")
        if url and not re.match(r"^https?://", url):
            raise ValueError("URL http(s) attendue.")
        if corps.get("date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", corps["date"]):
            raise ValueError("Date au format AAAA-MM-JJ.")
        entree = {"candidate_id": cand, "type": corps["type"], "titre": (corps.get("titre") or "").strip()[:200] or None,
                  "date": corps.get("date") or None, "note": (corps.get("note") or "").strip()[:500] or None,
                  "ajoutee_le": B.maintenant(), "ajoutee_par": "local", "statut": "en_attente"}
        with self.verrou:
            if fichier:
                nom = Path(str(fichier.get("nom") or "document")).name
                ext = Path(nom).suffix.lower()
                if ext not in EXTENSIONS:
                    raise ValueError(f"Format accepte : {', '.join(EXTENSIONS)}.")
                contenu = base64.b64decode(fichier.get("base64") or "", validate=True)
                if not contenu or len(contenu) > TAILLE_MAX:
                    raise ValueError("Fichier vide ou trop gros (50 Mo maximum).")
                empreinte = hashlib.sha256(contenu).hexdigest()
                self.c["depots"].mkdir(parents=True, exist_ok=True)
                chemin = self.c["depots"] / f"{empreinte[:24]}{ext}"
                chemin.write_bytes(contenu)
                entree.update(fichier=str(chemin.relative_to(self.racine)).replace("\\", "/"), nom_fichier=nom,
                              empreinte=empreinte, taille=len(contenu))
            else:
                entree["url"] = url
            sources = B.lire_json(self.c["sources"], {"ajouts": []})
            cle = entree.get("url") or entree.get("empreinte")
            if any((s.get("url") or s.get("empreinte")) == cle and s["candidate_id"] == cand for s in sources["ajouts"]):
                raise ValueError("Source deja ajoutee pour ce candidat.")
            entree["id"] = f"s-{len(sources['ajouts']) + 1:04d}"
            sources["ajouts"].append(entree)
            B.ecrire_json(self.c["sources"], sources)
        return entree

    def lancer_mise_a_jour(self) -> dict[str, Any]:
        with self.verrou:
            if self.job.get("etat") == "en_cours":
                raise RuntimeError("Une mise a jour est deja en cours.")
            self._pas_de_run()
            self.job = {"etat": "en_cours", "debut": B.maintenant()}

        def tache():
            try:
                with BO.Verrou(self.c["verrou"]):
                    resume = BO.executer(self.c, list(BO.ETAPES_GRATUITES))
                self.recharger(force=True)
                self.job = {"etat": "termine", "fin": B.maintenant(), "resume": resume}
            except Exception as exc:  # signale a la page, sans arreter le serveur
                self.job = {"etat": "erreur", "fin": B.maintenant(), "erreur": str(exc)}
        threading.Thread(target=tache, daemon=True).start()
        return self.job


def fabriquer_handler(etat: Etat, page: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Boussole/1"

        def log_message(self, fmt, *args):  # journal discret
            pass

        def _hote_local(self) -> bool:
            hote = (self.headers.get("Host") or "").split(":")[0]
            return hote in ("127.0.0.1", "localhost")

        def _json(self, data: Any, status: int = 200) -> None:
            corps = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corps)

        def _erreur(self, exc: Exception) -> None:
            status = 404 if isinstance(exc, KeyError) else 409 if isinstance(exc, RuntimeError) else 400
            self._json({"erreur": str(exc).strip("'")}, status)

        def do_GET(self):
            if not self._hote_local():
                return self._json({"erreur": "Hote refuse."}, 403)
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path in ("/", "/index.html"):
                    corps = page.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(corps)))
                    self.end_headers()
                    return self.wfile.write(corps)
                etat.recharger()
                if url.path == "/api/etat":
                    return self._json(etat.etat())
                if url.path == "/api/questions":
                    return self._json({"questions": Q.TOUTES, "conditionnelles": list(Q.CONDITIONNELLES),
                                       "mots": {**D.MOTS, **Q.MOTS}, "motifs_rejet": MOTIFS_REJET,
                                       "libelles_motifs": LIBELLES_MOTIFS})
                if url.path == "/api/file":
                    return self._json(etat.file(q.get("motif"), q.get("candidat"), q.get("theme"),
                                                int(q.get("offset", 0)), min(int(q.get("limit", 50)), 200)))
                if url.path == "/api/mesures":
                    return self._json(etat.recherche(q.get("q", ""), q.get("candidat"), q.get("theme"), q.get("statut"),
                                                     min(int(q.get("limit", 50)), 200)))
                if url.path.startswith("/api/mesure/"):
                    return self._json(etat.fiche(unquote(url.path.rsplit("/", 1)[1])))
                if url.path == "/api/sources":
                    return self._json(etat.sources())
                if url.path == "/api/runs":
                    runs = sorted(etat.c["runs"].glob("*.json"), reverse=True)[:30] if etat.c["runs"].exists() else []
                    return self._json([{"nom": r.stem, **(B.lire_json(r) or {}),
                                        "md": r.with_suffix(".md").read_text(encoding="utf-8") if r.with_suffix(".md").exists() else ""}
                                       for r in runs])
                if url.path == "/api/job":
                    return self._json(etat.job)
                return self._json({"erreur": "Introuvable."}, 404)
            except Exception as exc:
                traceback.print_exc()
                return self._erreur(exc)

        def do_POST(self):
            # Protection contre les requetes d'un autre site : hote local et en-tete propre a la page.
            if not self._hote_local() or self.headers.get("X-Boussole") != "1":
                return self._json({"erreur": "Requete refusee."}, 403)
            try:
                taille = int(self.headers.get("Content-Length") or 0)
                if taille > TAILLE_MAX * 1.4:
                    raise ValueError("Requete trop grosse.")
                corps = json.loads(self.rfile.read(taille) or b"{}")
                if self.path == "/api/decision":
                    return self._json(etat.decider(corps))
                if self.path == "/api/source":
                    return self._json(etat.ajouter_source(corps))
                if self.path == "/api/mise-a-jour":
                    return self._json(etat.lancer_mise_a_jour())
                return self._json({"erreur": "Introuvable."}, 404)
            except Exception as exc:
                if not isinstance(exc, (ValueError, KeyError, RuntimeError)):
                    traceback.print_exc()
                return self._erreur(exc)
    return Handler


def servir(racine: Path, port: int) -> None:
    etat = Etat(racine)
    serveur = ThreadingHTTPServer(("127.0.0.1", port), fabriquer_handler(etat, PAGE))
    print(f"Tableau de bord : http://127.0.0.1:{port}/  (Ctrl+C pour arreter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", default=".")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        servir(Path(args.racine), args.port)
        return 0
    except (OSError, ValueError) as exc:
        print(f"Erreur tableau de bord: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
