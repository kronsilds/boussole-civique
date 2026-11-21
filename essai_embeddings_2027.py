"""Essai : rapprochement des mesures par embeddings (similarite de sens) compare au pre-tri lexical actuel.

Verite independante du texte : les anciennes extractions (corpus_programmes/extractions) reliees a une mesure de la base
par une citation qui chevauche (meme passage du meme document), avec une formulation differente de toutes les versions de
cette mesure. Pour chaque requete, on cherche parmi les mesures du meme candidat :
- cas « positif » : la bonne mesure est dans le vivier (une nouvelle formulation d'une mesure connue) ;
- cas « negatif » : on retire la bonne mesure du vivier (une mesure vraiment nouvelle) ; le meilleur score restant dit
  si elle serait fusionnee a tort.
Les methodes sont comparees a erreurs egales (seuils choisis pour ne pas faire pire que le lexical a 0,85 / 0,35) : la
meilleure est celle qui laisse le moins de paires a arbitrer.

Aucun appel payant sans --max-cost (plan : nombre de textes, jetons et cout estimes). Cache des vecteurs dans
runs/embeddings_2027/ (ignore par git) : relancer ne repaie rien. Rien n'est ecrit dans la base.

    python essai_embeddings_2027.py                                   # plan
    python essai_embeddings_2027.py --max-cost 0.10                   # calcule les vecteurs manquants, puis compare
    python essai_embeddings_2027.py --modeles baai/bge-m3 --max-cost 0.02
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

import rapprochement_2027 as R

MODELES = ("qwen/qwen3-embedding-8b", "baai/bge-m3", "openai/text-embedding-3-small")
URL = "https://openrouter.ai/api/v1/embeddings"
LOT = 100
CARACTERES_PAR_JETON = 3.0  # estimation prudente pour le francais


# --- Jeu de verite ---------------------------------------------------------------------------------------------------

def texte(title: Any, description: Any) -> str:
    return f"{str(title or '').strip()}. {str(description or '').strip()}".strip()


def jeu_de_verite(racine: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Viviers par candidat (version courante des mesures actives ou non reprises) et requetes reliees par citation."""
    base = json.loads((racine / "donnees" / "base_2027.json").read_text(encoding="utf-8"))
    pools = R.construire_pool(base)
    viviers: dict[str, list[dict[str, Any]]] = {}
    versions: dict[str, set[str]] = {}
    for m in base["mesures"]:
        versions[m["uid"]] = {R.normaliser(f"{v['title']} {v['description']}") for v in m["versions"]}
        if m["statut"] in ("active", "non_reprise"):
            v = m["versions"][-1]
            viviers.setdefault(m["candidate_id"], []).append(
                {"uid": m["uid"], "texte": texte(v["title"], v["description"]),
                 "emp": R.empreinte_texte(v["title"], v["description"])})
    requetes, vues = [], set()
    for f in sorted(glob.glob(str(racine / "corpus_programmes" / "extractions" / "*.json"))):
        e = json.loads(Path(f).read_text(encoding="utf-8"))
        for p in e.get("proposals") or []:
            pool, ev = pools.get(p.get("candidate_id")), p.get("evidence")
            if not pool or not ev:
                continue
            # toutes les mesures dont une citation chevauche ce passage comptent comme bonne reponse
            verite = {m["uid"] for m, s in pool.par_segment.get((ev.get("document_id"), ev.get("segment_id")), [])
                      if R.citations_chevauchent(ev, s)}
            q = R.normaliser(ev.get("quote"))
            if len(q) > 40 and q in pool.par_citation:
                verite.add(pool.par_citation[q]["uid"])
            if not verite:
                continue
            norm = R.normaliser(f"{p.get('title')} {p.get('description')}")
            if any(norm in versions[u] for u in verite) or (p["candidate_id"], norm) in vues:
                continue
            vues.add((p["candidate_id"], norm))
            requetes.append({"c": p["candidate_id"], "texte": texte(p.get("title"), p.get("description")),
                             "emp": R.empreinte_texte(p.get("title"), p.get("description")), "verite": verite})
    return viviers, requetes


# --- Cache des vecteurs ----------------------------------------------------------------------------------------------

def cle(texte_: str) -> str:
    return hashlib.sha256(texte_.encode("utf-8")).hexdigest()[:24]


class Cache:
    """Vecteurs d'un modele, normalises, en float16 : runs/embeddings_2027/<modele>.npy + index des cles."""

    def __init__(self, dossier: Path, modele: str):
        nom = modele.replace("/", "__")
        self.npy, self.idx = dossier / f"{nom}.npy", dossier / f"{nom}.json"
        self.cles: list[str] = json.loads(self.idx.read_text(encoding="utf-8")) if self.idx.exists() else []
        self.vec = np.load(self.npy) if self.npy.exists() else None
        self.pos = {k: i for i, k in enumerate(self.cles)}
        self.nouveaux: list[tuple[str, np.ndarray]] = []

    def __contains__(self, k: str) -> bool:
        return k in self.pos

    def ajouter(self, k: str, v: list[float]) -> None:
        a = np.asarray(v, dtype=np.float32)
        a /= np.linalg.norm(a) or 1.0
        self.pos[k] = len(self.cles) + len(self.nouveaux)
        self.nouveaux.append((k, a.astype(np.float16)))

    def sauver(self) -> None:
        if not self.nouveaux:
            return
        bloc = np.stack([a for _, a in self.nouveaux])
        self.vec = bloc if self.vec is None else np.concatenate([self.vec, bloc])
        self.cles += [k for k, _ in self.nouveaux]
        self.nouveaux = []
        self.npy.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.npy, self.vec)
        self.idx.write_text(json.dumps(self.cles), encoding="utf-8")

    def matrice(self, cles: list[str]) -> np.ndarray:
        self.sauver()
        return self.vec[[self.pos[k] for k in cles]].astype(np.float32)


def prix_modeles() -> dict[str, float]:
    req = urllib.request.Request("https://openrouter.ai/api/v1/embeddings/models", headers={"User-Agent": "client"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return {m["id"]: float((m.get("pricing") or {}).get("prompt") or 0) for m in json.load(r)["data"]}


def calculer(modele: str, textes: list[str], cache: Cache, cle_api: str, journal: Any, plafond: float,
             depense: float, prix: float) -> float:
    """Vecteurs manquants par lots ; s'arrete avant de depasser le plafond (cout reel, sinon estime)."""
    from scoring_context_2027 import ScoringHTTPError, request_json
    manquants = [t for t in dict.fromkeys(textes) if cle(t) not in cache]
    for i in range(0, len(manquants), LOT):
        lot = manquants[i:i + LOT]
        estime = sum(len(t) for t in lot) / CARACTERES_PAR_JETON * prix
        if depense + estime > plafond:
            print(f"  plafond atteint ({depense:.4f} $) : {len(manquants) - i} textes restent sans vecteur")
            break
        req = urllib.request.Request(URL, data=json.dumps({"model": modele, "input": lot}).encode(), headers={
            "Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
        rid = journal.start_request(req, "embeddings", [])
        t0 = time.perf_counter()
        for essai in range(4):  # delais et erreurs 5xx passagers ; une erreur permanente (4xx) arrete tout
            try:
                rep = request_json(req, 180)  # journal reduit ci-dessous : les vecteurs n'entrent pas dans logs/
                break
            except (TimeoutError, OSError, ScoringHTTPError) as exc:
                if essai == 3:
                    cache.sauver()
                    raise
                print(f"  lot {i // LOT + 1} : {type(exc).__name__}, nouvel essai dans {5 * (essai + 1)} s")
                time.sleep(5 * (essai + 1))
        usage = rep.get("usage") or {}
        journal.write("api_response", request_id=rid, stage="embeddings", proposal_ids=[], http_status=200,
                      elapsed_seconds=round(time.perf_counter() - t0, 3),
                      response={"model": rep.get("model"), "n": len(rep.get("data") or []), "usage": usage})
        data = sorted(rep.get("data") or [], key=lambda d: d["index"])
        if len(data) != len(lot):
            raise ValueError(f"{modele} : {len(data)} vecteurs pour {len(lot)} textes")
        for t, d in zip(lot, data):
            cache.ajouter(cle(t), d["embedding"])
        depense += float(usage["cost"]) if usage.get("cost") is not None else estime
        if (i // LOT) % 20 == 19:
            cache.sauver()
    cache.sauver()
    return depense


# --- Evaluation ------------------------------------------------------------------------------------------------------

def scores_lexicaux(viviers, requetes) -> list[tuple[float, bool, float]]:
    """(meilleur score, meilleur = bonne mesure, meilleur score hors bonnes mesures) comme le pre-tri actuel (k = 20)."""
    listes = {c: [(x["uid"], x["emp"]) for x in v] for c, v in viviers.items()}
    out = []
    for q in requetes:
        top = R.meilleurs(q["emp"], listes[q["c"]], k=20)
        if not top:
            out.append((0.0, False, 0.0))
            continue
        hors = next((s for s, u in top if u not in q["verite"]), 0.0)
        out.append((top[0][0], top[0][1] in q["verite"], hors))
    return out


def scores_cosinus(viviers, requetes, cache: Cache) -> list[tuple[float, bool, float]]:
    out = []
    par_c: dict[str, list[dict[str, Any]]] = {}
    for q in requetes:
        par_c.setdefault(q["c"], []).append(q)
    res = {}
    for c, qs in par_c.items():
        V = cache.matrice([cle(x["texte"]) for x in viviers[c]])
        Q = cache.matrice([cle(q["texte"]) for q in qs])
        S = Q @ V.T
        uids = [x["uid"] for x in viviers[c]]
        for q, row in zip(qs, S):
            ordre = np.argsort(-row)
            j = int(ordre[0])
            hors = next(float(row[k]) for k in ordre if uids[k] not in q["verite"]) if len(ordre) > 1 else 0.0
            res[id(q)] = (float(row[j]), uids[j] in q["verite"], hors)
    return [res[id(q)] for q in requetes]


def bilan(sc: list[tuple[float, bool, float]], haut: float, bas: float) -> dict[str, float]:
    n = len(sc)
    fusion_fausse_pos = sum(1 for s, ok, _ in sc if s >= haut and not ok) / n
    fusion_fausse_neg = sum(1 for _, _, h in sc if h >= haut) / n
    doublons = sum(1 for s, _, _ in sc if s < bas) / n
    gris_pos = sum(1 for s, _, _ in sc if bas <= s < haut) / n
    gris_neg = sum(1 for _, _, h in sc if bas <= h < haut) / n
    return {"fusion_fausse_pos": fusion_fausse_pos, "fusion_fausse_neg": fusion_fausse_neg, "doublons": doublons,
            "gris_pos": gris_pos, "gris_neg": gris_neg}


def seuils_a_erreurs_egales(sc, ref: dict[str, float]) -> tuple[float, float]:
    """Haut le plus bas qui ne fusionne pas plus a tort que la reference ; bas le plus haut qui ne cree pas plus de
    doublons."""
    grille = sorted({round(x, 3) for s, _, h in sc for x in (s, h)} | {0.0, 1.0001})
    haut = next(t for t in grille if bilan(sc, t, 0)["fusion_fausse_pos"] <= ref["fusion_fausse_pos"]
                and bilan(sc, t, 0)["fusion_fausse_neg"] <= ref["fusion_fausse_neg"])
    bas = max((t for t in grille if t <= haut and bilan(sc, haut, t)["doublons"] <= ref["doublons"]), default=0.0)
    return haut, bas


def afficher(nom: str, sc, haut: float, bas: float) -> dict[str, Any]:
    b = bilan(sc, haut, bas)
    tete = sum(ok for _, ok, _ in sc) / len(sc)
    print(f"  {nom:<34} en tete {tete:6.1%} | seuils {haut:.3f} / {bas:.3f} | fusions fausses {b['fusion_fausse_pos']:.1%}"
          f" (connue) {b['fusion_fausse_neg']:.1%} (nouvelle) | doublons {b['doublons']:.1%} | a arbitrer "
          f"{b['gris_pos']:.1%} (connue) {b['gris_neg']:.1%} (nouvelle)")
    return {"methode": nom, "en_tete": tete, "haut": haut, "bas": bas, **b}


def vitesse(cache: Cache, cles: list[str]) -> dict[str, float]:
    """Temps d'une recherche sur tout le corpus : numpy, et pur Python sur 1 024 dimensions."""
    M = cache.matrice(cles)
    q = M[0]
    t0 = time.perf_counter()
    for _ in range(20):
        np.argsort(-(M @ q))[:20]
    t_np = (time.perf_counter() - t0) / 20
    lignes = [list(map(float, r[:1024])) for r in M]
    qp = lignes[0]
    t0 = time.perf_counter()
    sorted(range(len(lignes)), key=lambda i: -sum(a * b for a, b in zip(qp, lignes[i])))[:20]
    return {"textes": len(cles), "dimensions": int(M.shape[1]), "numpy_s": t_np, "python_1024_s": time.perf_counter() - t0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--racine", default=".")
    ap.add_argument("--modeles", default=",".join(MODELES))
    ap.add_argument("--max-cost", type=float, help="plafond en dollars ; sans lui, plan seulement")
    ap.add_argument("--sortie", default="runs/essai_embeddings_2027.json")
    a = ap.parse_args(argv)
    racine = Path(a.racine)
    modeles = [m.strip() for m in a.modeles.split(",") if m.strip()]
    t0 = time.perf_counter()
    viviers, requetes = jeu_de_verite(racine)
    textes = [x["texte"] for v in viviers.values() for x in v] + [q["texte"] for q in requetes]
    print(f"Jeu de verite : {len(requetes)} requetes, {sum(map(len, viviers.values()))} mesures dans les viviers "
          f"({time.perf_counter() - t0:.0f} s)")
    dossier = racine / "runs" / "embeddings_2027"
    prix = prix_modeles()
    caches = {m: Cache(dossier, m) for m in modeles}
    total = 0.0
    for m in modeles:
        manq = [t for t in dict.fromkeys(textes) if cle(t) not in caches[m]]
        est = sum(map(len, manq)) / CARACTERES_PAR_JETON * prix.get(m, 0)
        total += est
        print(f"  {m} : {len(manq)} textes sans vecteur, environ {sum(map(len, manq)) / CARACTERES_PAR_JETON:,.0f} "
              f"jetons, {est:.4f} $ estimes")
    if a.max_cost is None:
        print(f"Plan seulement (environ {total:.4f} $ au total) : ajouter --max-cost pour calculer.")
        return 0
    from pipeline_scoring_2027 import load_env_file
    from llm_logging_2027 import LLMJournal
    load_env_file(racine / ".env")
    cle_api = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not cle_api:
        raise SystemExit("OPENROUTER_API_KEY manque ; aucun appel lance.")
    from update_corpus_2027 import journal_cost
    # le plafond couvre aussi les runs precedents de cet essai (cout reel de leurs journaux)
    depense = sum(journal_cost(Path(f)) for f in glob.glob(str(racine / "logs" / "llm_embeddings_*.jsonl")))
    print(f"Deja depense par cet essai : {depense:.4f} $")
    journal = LLMJournal(racine / "logs" / f"llm_embeddings_{time.strftime('%Y%m%dT%H%M%S')}.jsonl", [cle_api])
    try:
        for m in modeles:
            print(f"Vecteurs : {m}")
            depense = calculer(m, textes, caches[m], cle_api, journal, a.max_cost, depense, prix.get(m, 0))
    finally:
        journal.close()
    print(f"Depense : {depense:.4f} $ (plafond {a.max_cost} $)")

    print("\nComparaison (positif : la mesure est connue ; negatif : elle est retiree du vivier)")
    t0 = time.perf_counter()
    lex = scores_lexicaux(viviers, requetes)
    print(f"  (lexical calcule en {time.perf_counter() - t0:.0f} s)")
    resultats = [afficher("lexical actuel (0,85 / 0,35)", lex, R.SEUIL_MEME, R.SEUIL_DIFFERENTE)]
    ref = bilan(lex, R.SEUIL_MEME, R.SEUIL_DIFFERENTE)
    for m in modeles:
        if any(cle(t) not in caches[m] for t in textes):
            print(f"  {m} : vecteurs incomplets, ignore")
            continue
        cos = scores_cosinus(viviers, requetes, caches[m])
        resultats.append(afficher(m, cos, *seuils_a_erreurs_egales(cos, ref)))
    vit = {m: vitesse(caches[m], [cle(x["texte"]) for v in viviers.values() for x in v]) for m in modeles
           if all(cle(t) in caches[m] for t in textes)}
    for m, v in vit.items():
        print(f"  recherche sur {v['textes']} mesures, {m} ({v['dimensions']} dim.) : numpy {v['numpy_s'] * 1000:.1f} ms,"
              f" pur Python (1 024 dim.) {v['python_1024_s']:.1f} s")
    sortie = racine / a.sortie
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M"), "requetes": len(requetes),
                                  "depense": depense, "resultats": resultats, "vitesse": vit}, ensure_ascii=False,
                                 indent=1), encoding="utf-8")
    print(f"Resultats : {sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
