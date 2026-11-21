"""Recherche par le sens dans les mesures : vecteurs (embeddings) des mesures et de la requete, plus proches voisins.

Deux moteurs, qui ont chacun leur index (on ne compare que des vecteurs d'un meme modele) :
- « api » (par defaut) : qwen/qwen3-embedding-8b via OpenRouter, avec une cle dediee lue dans .env.recherche (jamais
  dans .env) et un plafond mensuel (donnees/budget_recherche_2027.json). Le texte de la requete part chez OpenRouter et
  chez le fournisseur du modele ; il n'est ecrit dans aucun journal. Cout : 0,01 $ le million de jetons (une requete
  fait une quinzaine de jetons ; tout le corpus, environ un centime).
- « local » (secours) : Qwen3-Embedding-0.6B quantifie int8, export ONNX (onnx-community/Qwen3-Embedding-0.6B-ONNX,
  licence Apache 2.0), dans modeles/qwen3-embedding-0.6b/ (ignore par git), dependances optionnelles onnxruntime et
  tokenizers. Gratuit, hors ligne, mais nettement moins bon. Sert quand l'API est indisponible (pas de cle, panne,
  plafond atteint).
numpy est requis dans les deux cas ; le reste du pipeline n'importe pas ce module.

La recherche trouve des propositions sur un SUJET, pas une position : « supprimer l'ISF » et « retablir l'ISF » sont
proches pour le modele. Le sens vient des positions deja calculees a l'aveugle (calculs.axes) : les resultats sont
ranges par direction sur l'axe le plus present parmi eux. Essais et choix des modeles : docs/suivi/09 (2026-11-21).

    python recherche_semantique_2027.py index                     # plan : mesures sans vecteur, cout estime
    python recherche_semantique_2027.py index --max-cost 0.05     # complete l'index par l'API (cle de .env.recherche)
    python recherche_semantique_2027.py index --local             # index du moteur local (gratuit, environ 30 min)
    python recherche_semantique_2027.py chercher "aide a mourir" [--local]

L'index de l'API reprend d'abord, sans appel, les vecteurs deja payes par essai_embeddings_2027.py (meme texte, meme
cle). Le tableau de bord indexe lui-meme les mesures nouvelles ou modifiees, dans la limite du plafond mensuel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

STATUTS = ("active", "non_reprise")
SEUIL_DIRECTION = 15     # position sur l'axe : en dessous en valeur absolue, mesure « mixte ou neutre »
BONUS_MOTS = 0.05        # tous les mots de la requete presents dans le texte


@dataclass(frozen=True)
class Moteur:
    """Modele, consigne de requete et seuils de coupure (scores apres centrage) propres a chaque modele. On garde les
    resultats d'au moins `ratio` x le meilleur score et d'au moins `score_min` ; sous `score_faible` pour le meilleur,
    la correspondance est signalee comme faible."""
    nom: str
    modele: str
    dim: int
    consigne: str
    ratio: float
    score_min: float
    score_faible: float
    fichier_index: str


# Qwen3-Embedding attend une consigne devant les requetes (pas devant les documents) ; sans elle, resultats sans
# rapport. Celle du modele 8B est celle de l'essai du 2026-11-21 (12 requetes sur 12 pertinentes) ; le petit modele
# local, lui, etait attire par « citoyen » et « programme electoral » vers les mesures sur le vote : consigne neutre.
# Seuils calibres le 2026-11-21 sur les memes requetes types (docs/suivi/09) ; le 8B separe mieux les bons resultats
# du reste (chute nette du score), d'ou une coupure relative plus basse.
API = Moteur("api", "qwen/qwen3-embedding-8b", 4096,
             "Instruct: Étant donné une recherche d'un citoyen, retrouver les propositions de programme électoral "
             "qui y répondent\nQuery: ", 0.5, 0.20, 0.35, "index_recherche_2027")
LOCAL = Moteur("local", "onnx-community/Qwen3-Embedding-0.6B-ONNX:model_int8", 1024,
               "Instruct: Given a topic, retrieve policy proposals about this topic\nQuery: ", 0.6, 0.28, 0.40,
               "index_recherche_local_2027")
MOTEURS = {m.nom: m for m in (API, LOCAL)}


def texte_mesure(m: dict[str, Any]) -> str:
    v = m["versions"][-1]
    return f"{str(v.get('title') or '').strip()}. {str(v.get('description') or '').strip()}".strip()


def cle(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:24]


def normal(texte: Any) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(texte or "").casefold()).split())


class Indisponible(RuntimeError):
    """Le moteur ne peut pas repondre (pas de cle, panne reseau, plafond atteint, modele absent) : passer au secours."""


# --- Configuration et budget de l'API --------------------------------------------------------------------------------

FICHIER_CONFIG = ".env.recherche"
VARIABLES = ("OPENROUTER_RECHERCHE_KEY", "RECHERCHE_PLAFOND_MENSUEL")
PLAFOND_DEFAUT = 1.0     # $ par mois, requetes et indexation comprises


def lire_config(racine: Path) -> dict[str, str]:
    """NOM=valeur, sans commentaire en fin de ligne. Lu dans un dictionnaire, jamais copie dans l'environnement."""
    chemin = racine / FICHIER_CONFIG
    if not chemin.exists():
        return {}
    valeurs: dict[str, str] = {}
    for n, ligne in enumerate(chemin.read_text(encoding="utf-8-sig").splitlines(), 1):
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        m = re.fullmatch(r"([A-Z_][A-Z0-9_]*)\s*=\s*(.*)", ligne)
        if not m or m.group(1) not in VARIABLES:
            raise ValueError(f"{FICHIER_CONFIG}, ligne {n} : NOM=valeur attendu, avec NOM parmi {', '.join(VARIABLES)}.")
        valeurs[m.group(1)] = m.group(2).strip().strip("'\"")
    return valeurs


class Budget:
    """Depense de la recherche par mois (cout reel renvoye par OpenRouter, sinon estime) : donnees/budget_recherche_2027.json."""

    def __init__(self, chemin: Path, plafond: float):
        self.chemin, self.plafond = chemin, plafond
        self.verrou = threading.Lock()
        try:
            self.mois = json.loads(chemin.read_text(encoding="utf-8")).get("mois", {})
        except (OSError, ValueError):
            self.mois = {}

    @staticmethod
    def courant() -> str:
        return time.strftime("%Y-%m")

    def depense(self) -> float:
        return float(self.mois.get(self.courant(), {}).get("cout", 0.0))

    def reste(self) -> float:
        return max(self.plafond - self.depense(), 0.0)

    def ajouter(self, cout: float, jetons: int, textes: int) -> None:
        with self.verrou:
            m = self.mois.setdefault(self.courant(), {"cout": 0.0, "appels": 0, "textes": 0, "jetons": 0})
            m["cout"] = round(m["cout"] + cout, 8)
            m["appels"] += 1
            m["textes"] += textes
            m["jetons"] += jetons
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps({"plafond_mensuel": self.plafond, "mois": self.mois}, indent=1), encoding="utf-8")
            tmp.replace(self.chemin)


# --- Encodeurs -------------------------------------------------------------------------------------------------------

class EncodeurAPI:
    """Vecteurs par OpenRouter (/api/v1/embeddings), normalises. Toute erreur devient Indisponible."""
    URL = "https://openrouter.ai/api/v1/embeddings"
    PRIX_JETON = 0.01e-6        # $ par jeton (qwen3-embedding-8b, tarif du 2026-11-21) : estimation avant l'appel
    CARACTERES_PAR_JETON = 3.0  # estimation prudente pour le francais
    LOT = 100

    def __init__(self, cle_api: str, budget: Budget, moteur: Moteur = API, delai: float = 10.0):
        import numpy as np
        self.np, self.cle_api, self.budget, self.moteur, self.delai = np, cle_api, budget, moteur, delai

    @classmethod
    def depuis_config(cls, racine: Path, chemin_budget: Path) -> "EncodeurAPI":
        try:
            conf = lire_config(racine)
        except ValueError as exc:
            raise Indisponible(str(exc)) from exc
        cle_api = conf.get("OPENROUTER_RECHERCHE_KEY", "")
        if not cle_api:
            raise Indisponible(f"pas de cle OPENROUTER_RECHERCHE_KEY dans {FICHIER_CONFIG}")
        try:
            plafond = float(conf.get("RECHERCHE_PLAFOND_MENSUEL") or PLAFOND_DEFAUT)
        except ValueError as exc:
            raise Indisponible(f"RECHERCHE_PLAFOND_MENSUEL illisible dans {FICHIER_CONFIG}") from exc
        return cls(cle_api, Budget(chemin_budget, plafond))

    def _appel(self, lot: list[str], essais: int) -> list[list[float]]:
        estime = sum(map(len, lot)) / self.CARACTERES_PAR_JETON * self.PRIX_JETON
        if estime > self.budget.reste():
            raise Indisponible(f"plafond mensuel de la recherche atteint ({self.budget.depense():.4f} $ sur "
                               f"{self.budget.plafond} $)")
        req = urllib.request.Request(self.URL, data=json.dumps({"model": self.moteur.modele, "input": lot}).encode(),
                                     headers={"Authorization": "Bearer " + self.cle_api,
                                              "Content-Type": "application/json", "X-Title": "Boussole 2027"})
        for essai in range(essais):
            try:
                with urllib.request.urlopen(req, timeout=self.delai) as r:
                    rep = json.loads(r.read())
                break
            except urllib.error.HTTPError as exc:  # 4xx : cle refusee, credit epuise... inutile d'insister
                if exc.code < 500 or essai == essais - 1:
                    raise Indisponible(f"API de recherche : erreur HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                if essai == essais - 1:
                    raise Indisponible(f"API de recherche injoignable ({type(exc).__name__})") from exc
            time.sleep(2 * (essai + 1))
        data = sorted(rep.get("data") or [], key=lambda d: d["index"])
        if len(data) != len(lot):
            raise Indisponible(f"API de recherche : {len(data)} vecteurs pour {len(lot)} textes")
        usage = rep.get("usage") or {}
        cout = float(usage["cost"]) if usage.get("cost") is not None else estime
        self.budget.ajouter(cout, int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0), len(lot))
        return [d["embedding"] for d in data]

    def encoder(self, textes: list[str], requete: bool = False, suivi: Callable[[int, int], None] | None = None):
        np = self.np
        textes = [self.moteur.consigne + t if requete else t for t in textes]
        out = np.zeros((len(textes), self.moteur.dim), dtype=np.float32)
        for k in range(0, len(textes), self.LOT):
            lot = textes[k:k + self.LOT]
            # une requete : un seul essai (le secours local repond vite) ; l'indexation insiste un peu
            v = np.asarray(self._appel(lot, 1 if requete else 3), dtype=np.float32)
            out[k:k + len(lot)] = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            if suivi:
                suivi(min(k + self.LOT, len(textes)), len(textes))
        return out


DOSSIER_MODELE = Path("modeles") / "qwen3-embedding-0.6b"
FICHIER_MODELE = "onnx/model_int8.onnx"
LONGUEUR_MAX = 256       # jetons par texte (titre + description d'une mesure : bien en dessous)
# Un texte a la fois : la quantification int8 dynamique calcule l'echelle des activations sur tout le lot, si bien
# qu'un texte encode dans un lot differe du meme encode seul (similarite 0,92) ; un par un, c'est aussi rapide sur CPU.
TAILLE_LOT = 1


class Encodeur:
    """Moteur local : Qwen3-Embedding en ONNX, regroupement sur le dernier vrai jeton (remplissage a droite)."""
    moteur = LOCAL

    def __init__(self, dossier: Path):
        import numpy as np
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise Indisponible("moteur local : installer onnxruntime et tokenizers") from exc
        modele = dossier / FICHIER_MODELE
        if not modele.exists():
            raise Indisponible(f"moteur local : modele absent ({modele})")
        self.np = np
        self.tok = Tokenizer.from_file(str(dossier / "tokenizer.json"))
        self.tok.no_padding()
        self.tok.enable_truncation(LONGUEUR_MAX)
        self.fin = self.tok.token_to_id("<|endoftext|>")
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(modele), options, providers=["CPUExecutionProvider"])
        self.passes = [(i.name, i.shape[1]) for i in self.session.get_inputs() if i.name.startswith("past_key_values")]
        self.verrou = threading.Lock()  # une inference a la fois (serveur a fils multiples)

    def _lot(self, textes: list[str]):
        np = self.np
        ids = []
        for e in self.tok.encode_batch(textes):
            x = list(e.ids)
            if not x or x[-1] != self.fin:  # tronque : le jeton de fin, sur lequel on regroupe, doit rester
                x = x[:LONGUEUR_MAX - 1] + [self.fin]
            ids.append(x)
        # Remplissage a DROITE et regroupement sur le dernier vrai jeton : avec l'attention causale, les jetons de
        # remplissage, places apres le texte, ne peuvent pas l'influencer. (Le remplissage a gauche de l'export ONNX
        # changeait les vecteurs selon le lot : similarite 0,90 entre un texte seul et le meme dans un lot.)
        n = max(map(len, ids))
        entree = np.full((len(ids), n), self.fin, dtype=np.int64)
        masque = np.zeros((len(ids), n), dtype=np.int64)
        for i, x in enumerate(ids):
            entree[i, :len(x)] = x
            masque[i, :len(x)] = 1
        positions = np.tile(np.arange(n, dtype=np.int64), (len(ids), 1))
        flux = {"input_ids": entree, "attention_mask": masque, "position_ids": positions}
        for nom, tetes in self.passes:
            flux[nom] = np.zeros((len(ids), tetes, 0, 128), dtype=np.float32)
        with self.verrou:
            sortie = self.session.run(["last_hidden_state"], flux)[0]
        v = sortie[np.arange(len(ids)), [len(x) - 1 for x in ids], :]
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def encoder(self, textes: list[str], requete: bool = False, suivi: Callable[[int, int], None] | None = None):
        np = self.np
        textes = [LOCAL.consigne + t if requete else t for t in textes]
        ordre = sorted(range(len(textes)), key=lambda i: len(textes[i]))
        out = np.zeros((len(textes), LOCAL.dim), dtype=np.float32)
        for k in range(0, len(ordre), TAILLE_LOT):
            idx = ordre[k:k + TAILLE_LOT]
            out[idx] = self._lot([textes[i] for i in idx])
            if suivi:
                suivi(min(k + TAILLE_LOT, len(ordre)), len(ordre))
        return out


# --- Index des mesures -----------------------------------------------------------------------------------------------

class Index:
    """Vecteurs des textes de mesures (float16), par empreinte du texte : donnees/<fichier_index>.npy + .json."""

    def __init__(self, chemin: Path, moteur: Moteur = LOCAL):
        import numpy as np
        self.np, self.moteur = np, moteur
        self.npy, self.meta = chemin.with_suffix(".npy"), chemin.with_suffix(".json")
        meta = json.loads(self.meta.read_text(encoding="utf-8")) if self.meta.exists() else {}
        if meta.get("modele") == moteur.modele and self.npy.exists():
            self.cles, self.vec = meta["cles"], np.load(self.npy)
        else:  # autre modele (ou rien) : on repart de zero
            self.cles, self.vec = [], np.zeros((0, moteur.dim), dtype=np.float16)
        self.pos = {k: i for i, k in enumerate(self.cles)}

    def manquants(self, textes: list[str]) -> list[str]:
        return [t for t in dict.fromkeys(textes) if cle(t) not in self.pos]

    def ajouter(self, textes: list[str], vecteurs) -> None:
        np = self.np
        for t in textes:
            self.pos[cle(t)] = len(self.cles)
            self.cles.append(cle(t))
        self.vec = np.concatenate([self.vec, np.asarray(vecteurs).astype(np.float16)])

    def sauver(self) -> None:
        self.npy.parent.mkdir(parents=True, exist_ok=True)
        self.np.save(self.npy, self.vec)
        self.meta.write_text(json.dumps({"modele": self.moteur.modele, "cles": self.cles}), encoding="utf-8")


def textes_a_indexer(base: dict[str, Any]) -> list[str]:
    return [texte_mesure(m) for m in base["mesures"] if m["statut"] in STATUTS]


def reprendre_essai(index: Index, textes: list[str], dossier: Path) -> int:
    """Copie, sans appel, les vecteurs deja payes par essai_embeddings_2027.py (meme modele, meme texte, meme cle)."""
    nom = index.moteur.modele.replace("/", "__")
    idx, npy = dossier / f"{nom}.json", dossier / f"{nom}.npy"
    if not (idx.exists() and npy.exists()):
        return 0
    pos = {k: i for i, k in enumerate(json.loads(idx.read_text(encoding="utf-8")))}
    pris = [t for t in index.manquants(textes) if cle(t) in pos]
    if pris:
        vec = index.np.load(npy, mmap_mode="r")
        index.ajouter(pris, vec[[pos[cle(t)] for t in pris]])
        index.sauver()
    return len(pris)


def mettre_a_jour_index(base: dict[str, Any], index: Index, encodeur: Any, suivi=None) -> int:
    """Calcule les vecteurs des mesures dont le texte courant n'est pas encore indexe. Renvoie leur nombre. Un moteur
    qui devient indisponible en cours de route (plafond...) laisse l'index sauve avec ce qui est fait."""
    textes = index.manquants(textes_a_indexer(base))
    for k in range(0, len(textes), 500):  # sauvegarde reguliere : une interruption ne perd presque rien
        lot = textes[k:k + 500]
        index.ajouter(lot, encodeur.encoder(lot, suivi=(lambda i, n, k=k: suivi(k + i, len(textes))) if suivi else None))
        index.sauver()
    return len(textes)


# --- Recherche et rangement par direction ----------------------------------------------------------------------------

def libelles_axes(base: dict[str, Any]) -> dict[str, dict[str, str]]:
    schema = base.get("dimensions_schema") or {}
    return {k: {"label": s.get("label") or k, "bas": s.get("low_label") or "−", "haut": s.get("high_label") or "+"}
            for k, s in schema.items() if isinstance(s, dict) and s.get("type") == "scale"}


def ranger(resultats: list[dict[str, Any]], axes: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Axe le plus present parmi les resultats (pondere par le score), puis groupes : vers le bas de l'axe, mixte ou
    neutre, vers le haut, sans position sur cet axe. Les positions viennent de la notation a l'aveugle."""
    poids: dict[str, float] = {}
    for r in resultats:
        for k, v in r["axes"].items():
            if v is not None and k in axes:
                poids[k] = poids.get(k, 0.0) + r["score"]
    if not poids:
        return {"axe": None, "groupes": [{"cle": "tous", "titre": "Propositions sur ce sujet", "items": resultats}]}
    axe = max(poids, key=poids.get)
    lib = axes[axe]
    groupes = {"bas": [], "neutre": [], "haut": [], "aucune": []}
    for r in resultats:
        v = r["axes"].get(axe)
        r["position"] = v
        g = "aucune" if v is None else "bas" if v <= -SEUIL_DIRECTION else "haut" if v >= SEUIL_DIRECTION else "neutre"
        groupes[g].append(r)
    titres = {"bas": f"Vers « {lib['bas']} »", "neutre": "Mixte ou neutre", "haut": f"Vers « {lib['haut']} »",
              "aucune": f"Sans position sur l'axe « {lib['label']} »"}
    return {"axe": {"cle": axe, **lib},
            "groupes": [{"cle": g, "titre": titres[g], "items": groupes[g]} for g in ("bas", "neutre", "haut", "aucune") if groupes[g]]}


class Recherche:
    """Un moteur : index en memoire (centre), encodeur cree au premier besoin, cache des requetes recentes.
    `fabrique` cree l'encodeur (peut lever Indisponible) ; les tests fournissent directement un encodeur."""

    def __init__(self, racine: Path, chemin_index: Path, encodeur: Any = None, moteur: Moteur = LOCAL,
                 fabrique: Callable[[], Any] | None = None):
        self.racine, self.chemin_index, self.moteur = racine, chemin_index, moteur
        self.encodeur = encodeur
        self.fabrique = fabrique or (lambda: Encodeur(racine / DOSSIER_MODELE))
        self.index: Index | None = None
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.verrou = threading.Lock()
        self.matrice = None
        self.non_indexees = 0
        self._base_id = None

    def _preparer(self, base: dict[str, Any]) -> None:
        with self.verrou:
            if self.encodeur is None:
                self.encodeur = self.fabrique()
            if self.index is None:
                self.index = Index(self.chemin_index, self.moteur)
            if self._base_id == id(base):
                return
            # base rechargee : textes changes ou mesures nouvelles a indexer ; si le moteur ne peut pas (plafond,
            # panne), on cherche dans ce qui est deja indexe et on le dit
            try:
                mettre_a_jour_index(base, self.index, self.encodeur)
            except Indisponible:
                if not self.index.cles:
                    raise
            self.uids, lignes = [], []
            for m in base["mesures"]:
                if m["statut"] in STATUTS and cle(texte_mesure(m)) in self.index.pos:
                    self.uids.append(m["uid"])
                    lignes.append(self.index.pos[cle(texte_mesure(m))])
            self.non_indexees = sum(m["statut"] in STATUTS for m in base["mesures"]) - len(self.uids)
            # Centrage sur la moyenne du corpus (requete comprise) : retire la direction commune a toutes les
            # mesures, qui faisait remonter partout les textes generiques (« Socialisme au programme »...).
            np = self.index.np
            M = self.index.vec[lignes].astype("float32")
            self.moyenne = M.mean(axis=0) if len(M) else np.zeros(self.moteur.dim, dtype=np.float32)
            M -= self.moyenne
            self.matrice = M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-9)
            self._base_id = id(base)

    def vecteur_requete(self, q: str):
        with self.verrou:
            if q in self.cache:
                self.cache.move_to_end(q)
                return self.cache[q]
        v = self.encodeur.encoder([q], requete=True)[0]
        with self.verrou:
            self.cache[q] = v
            if len(self.cache) > 500:
                self.cache.popitem(last=False)
        return v

    def chercher(self, base: dict[str, Any], q: str, candidat: str | None = None, theme: str | None = None,
                 limite: int = 40) -> dict[str, Any]:
        q = " ".join(str(q or "").split())[:300]
        if not q:
            raise ValueError("Recherche vide.")
        mo = self.moteur
        t0 = time.perf_counter()
        self._preparer(base)
        t1 = time.perf_counter()
        np = self.index.np
        v = self.vecteur_requete(q) - self.moyenne
        v = v / max(float(np.linalg.norm(v)), 1e-9)
        t2 = time.perf_counter()
        scores = self.matrice @ v
        par_uid = {m["uid"]: m for m in base["mesures"]}
        mots = normal(q).split()
        garder = np.ones(len(self.uids), dtype=bool)
        if candidat or theme:
            for i, u in enumerate(self.uids):
                m = par_uid[u]
                garder[i] = (not candidat or m["candidate_id"] == candidat) and (not theme or m["theme_id"] == theme)
        scores = np.where(garder, scores, -1.0)
        ordre = np.argsort(-scores)[:max(limite * 3, 60)]
        bruts = []
        for i in ordre:
            if scores[i] < 0:
                break
            m = par_uid[self.uids[i]]
            s = float(scores[i])
            if mots and all(w in normal(texte_mesure(m)) for w in mots):
                s += BONUS_MOTS
            bruts.append((s, m))
        bruts.sort(key=lambda x: -x[0])
        haut = bruts[0][0] if bruts else 0.0
        coupure = max(haut * mo.ratio, mo.score_min)
        retenus = [(s, m) for s, m in bruts if s >= coupure][:limite]
        resultats = [{"uid": m["uid"], "c": m["candidate_id"], "t": m["theme_id"], "title": m["versions"][-1]["title"],
                      "description": m["versions"][-1].get("description") or "", "statut": m["statut"],
                      "score": round(s, 3), "axes": dict((m.get("calculs") or {}).get("axes") or {})}
                     for s, m in retenus]
        rangement = ranger(resultats, libelles_axes(base))
        return {"q": q, "moteur": mo.nom, "modele": mo.modele, "total": len(resultats),
                "candidats": len({r["c"] for r in resultats}), "non_indexees": self.non_indexees,
                "coupure": round(coupure, 3), "meilleur": round(haut, 3), "faible": haut < mo.score_faible, **rangement,
                "temps_ms": {"preparation": round((t1 - t0) * 1000), "requete": round((t2 - t1) * 1000),
                             "total": round((time.perf_counter() - t0) * 1000)}}


def moteurs(racine: Path, donnees: Path) -> list[Recherche]:
    """L'API d'abord, le modele local en secours (dans cet ordre)."""
    budget = donnees / "budget_recherche_2027.json"
    return [Recherche(racine, donnees / API.fichier_index, moteur=API,
                      fabrique=lambda: EncodeurAPI.depuis_config(racine, budget)),
            Recherche(racine, donnees / LOCAL.fichier_index, moteur=LOCAL)]


def chercher_avec_secours(recherches: list[Recherche], base: dict[str, Any], q: str, **kw) -> dict[str, Any]:
    """Premier moteur qui repond ; `secours` dit pourquoi les precedents n'ont pas pu."""
    raisons = []
    for r in recherches:
        try:
            res = r.chercher(base, q, **kw)
        except Indisponible as exc:
            raisons.append(f"{r.moteur.nom} : {exc}")
            continue
        if raisons:
            res["secours"] = " ; ".join(raisons)
        return res
    raise Indisponible("Recherche par le sens indisponible (" + " ; ".join(raisons) + ").")


def main(argv: list[str] | None = None) -> int:
    import boussole_2027 as BO
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("index", "chercher"))
    ap.add_argument("requete", nargs="?")
    ap.add_argument("--racine", default=".")
    ap.add_argument("--local", action="store_true", help="moteur local (gratuit) au lieu de l'API")
    ap.add_argument("--max-cost", type=float, help="index par l'API : plafond de ce run en $ (sans lui : plan)")
    a = ap.parse_args(argv)
    racine = Path(a.racine)
    c = BO.chemins(argparse.Namespace(racine=str(racine)))
    base = BO.charger_base(c)
    moteur = LOCAL if a.local else API
    chemin = c["donnees"] / moteur.fichier_index
    budget = c["donnees"] / "budget_recherche_2027.json"
    t0 = time.perf_counter()

    def suivi(i, n):
        if i % 500 < (TAILLE_LOT if a.local else EncodeurAPI.LOT) or i == n:
            print(f"  {i}/{n} ({time.perf_counter() - t0:.0f} s)", flush=True)

    if a.action == "index":
        idx = Index(chemin, moteur)
        textes = textes_a_indexer(base)
        if not a.local:
            n = reprendre_essai(idx, textes, racine / "runs" / "embeddings_2027")
            print(f"{n} vecteurs repris de l'essai (sans appel)")
            manq = idx.manquants(textes)
            est = sum(map(len, manq)) / EncodeurAPI.CARACTERES_PAR_JETON * EncodeurAPI.PRIX_JETON
            print(f"{len(manq)} textes sans vecteur, environ {est:.4f} $")
            if not manq:
                return 0
            if a.max_cost is None:
                print("Plan seulement : ajouter --max-cost pour les calculer par l'API (cle de .env.recherche).")
                return 0
            try:
                enc = EncodeurAPI.depuis_config(racine, budget)
            except Indisponible as exc:
                print(f"Arret : {exc}.")
                return 2
            # le plafond du run s'ajoute au plafond mensuel : le plus petit des deux s'applique
            enc.budget = Budget(budget, min(enc.budget.plafond, enc.budget.depense() + a.max_cost))
        else:
            try:
                enc = Encodeur(racine / DOSSIER_MODELE)
            except Indisponible as exc:
                print(f"Arret : {exc}.")
                return 2
            print(f"Modele charge en {time.perf_counter() - t0:.1f} s")
        try:
            n = mettre_a_jour_index(base, idx, enc, suivi)
        except Indisponible as exc:
            print(f"Arret : {exc}. Index sauve : {len(idx.cles)} textes.")
            return 2
        print(f"{n} textes indexes en {time.perf_counter() - t0:.0f} s ; index : {len(idx.cles)} textes")
        return 0
    if not a.requete:
        ap.error("requete manquante")
    rs = moteurs(racine, c["donnees"])
    try:
        r = chercher_avec_secours(rs[1:] if a.local else rs, base, a.requete)
    except Indisponible as exc:
        print(exc)
        return 2
    noms = {x["id"]: x.get("name") or x["id"] for x in base.get("candidates", [])}
    print(f"Moteur {r['moteur']}{' (secours : ' + r['secours'] + ')' if r.get('secours') else ''}")
    print(f"{r['total']} resultats, {r['candidats']} candidats, coupure {r['coupure']}, meilleur {r['meilleur']}"
          f"{' (faible)' if r['faible'] else ''}, non indexees {r['non_indexees']}, temps {r['temps_ms']}")
    for g in r["groupes"]:
        print(f"\n{g['titre']}")
        for x in g["items"]:
            print(f"  {x['score']:.2f} {x.get('position')!s:>5} {noms.get(x['c'], x['c'])} : {x['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
