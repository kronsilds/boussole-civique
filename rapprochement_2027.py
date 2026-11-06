"""Rapprochement des mesures (spec_pipeline_unifie_2027.md, section 5.3 ; phase 2).

Pour chaque mesure d'un nouvel export dont l'identifiant corpus est inconnu de la base, on cherche une mesure existante
du meme candidat :
1. pre-tri gratuit : citation identique ou chevauchante = meme ; sinon similarite textuelle (titre + description) ;
2. au-dessus de SEUIL_MEME : meme mesure (source ajoutee) ; en dessous de SEUIL_DIFFERENTE : nouvelle mesure ;
3. entre les deux : arbitrage par un modele chat sur la paire (meme / precisee / modifiee / differente), en cache.
   Sans verdict (pas de budget) ou verdict peu sur : nouvelle mesure « rapprochement incertain », non publiee avant
   validation humaine (fusion ou validation depuis le tableau de bord).

Seuils calibres le 2026-11-06 sur 2 745 mesures d'anciennes extractions comparees a toute la base du meme candidat
(verite : citations qui se chevauchent) : bonne mesure en tete 98,5 % ; au-dessus de 0,85, 99,4 % de « meme » justes ;
en dessous de 0,35, 2,9 % des vrais equivalents deviennent des doublons ; 23 % de paires a arbitrer (pire cas).
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
import urllib.request
from typing import Any

MOTS_VIDES = frozenset(
    "dans pour avec plus leur leurs cette ainsi entre vers sous tout tous toute toutes comme afin etre mettre faire "
    "mise place favoriser renforcer developper permettre assurer garantir politique publique publics nationale national "
    "france francais francaise sera seront chaque notamment aussi autres autre leurs elles ceux celles dont meme".split())
SEUIL_MEME = .85          # au-dessus : meme mesure sans arbitrage (99,4 % justes au calibrage)
SEUIL_DIFFERENTE = .35    # en dessous : nouvelle mesure (2,9 % de doublons crees au calibrage)
CONFIANCE_ARBITRE = .7    # verdict d'arbitre moins sur : motif rapprochement_incertain
VERDICTS = ("meme", "precisee", "modifiee", "differente")
VERSION_ARBITRE = 1
COUT_PAR_PAIRE = .0005    # estimation prudente (modele chat, raisonnement bas, lots de 20)


# --- Similarite ---------------------------------------------------------------------------------------------------

def normaliser(texte: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texte or "").casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def mots(texte: str) -> set[str]:
    return {w for w in texte.split() if len(w) > 3 and w not in MOTS_VIDES}


def empreinte_texte(title: Any, description: Any) -> tuple[str, set[str]]:
    t = normaliser(f"{title} {description}")
    return t, mots(t)


def similarite(a: tuple[str, set[str]], b: tuple[str, set[str]]) -> float:
    """Moyenne d'un ratio de sequence (formulation) et d'un Jaccard sur les mots significatifs (vocabulaire)."""
    if not (a[1] or b[1]):
        return 0.0
    jac = len(a[1] & b[1]) / len(a[1] | b[1]) if a[1] and b[1] else 0.0
    seq = difflib.SequenceMatcher(None, a[0], b[0], autojunk=False).ratio()
    return round((seq + jac) / 2, 3)


def meilleurs(e: tuple[str, set[str]], pool: list[tuple[Any, tuple[str, set[str]]]], k: int = 20) -> list[tuple[float, Any]]:
    """Pre-filtre rapide (Jaccard sur les mots) puis similarite complete sur les k plus proches, tries par score."""
    def jac(b):
        return len(e[1] & b[1]) / len(e[1] | b[1]) if e[1] and b[1] else 0.0
    proches = sorted(pool, key=lambda x: -jac(x[1]))[:k]
    return sorted(((similarite(e, emp), obj) for obj, emp in proches), key=lambda x: -x[0])


def citations_chevauchent(e1: dict[str, Any], e2: dict[str, Any]) -> bool:
    """Meme passage du meme document : segments egaux et intervalles qui se recouvrent, ou citation identique."""
    if e1.get("document_id") and e1.get("document_id") == e2.get("document_id"):
        if e1.get("segment_id") and e1.get("segment_id") == e2.get("segment_id"):
            s1, f1, s2, f2 = e1.get("start"), e1.get("end"), e2.get("start"), e2.get("end")
            if None not in (s1, f1, s2, f2) and s1 < f2 and s2 < f1:
                return True
    q1, q2 = normaliser(e1.get("quote")), normaliser(e2.get("quote"))
    return len(q1) > 40 and q1 == q2


# --- Pre-tri ---------------------------------------------------------------------------------------------------------

class Pool:
    """Mesures comparables d'un candidat, indexees par passage cite et par mot (recherche en temps quasi constant)."""

    def __init__(self):
        self.items: list[tuple[dict[str, Any], tuple[str, set[str]]]] = []
        self.par_mot: dict[str, list[int]] = {}
        self.par_segment: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        self.par_citation: dict[str, dict[str, Any]] = {}

    def ajouter(self, m: dict[str, Any]) -> None:
        v = m["versions"][-1]
        emp = empreinte_texte(v["title"], v["description"])
        i = len(self.items)
        self.items.append((m, emp))
        for w in emp[1]:
            self.par_mot.setdefault(w, []).append(i)
        for s in v.get("sources") or []:
            if s.get("document_id") and s.get("segment_id"):
                self.par_segment.setdefault((s["document_id"], s["segment_id"]), []).append((m, s))
            q = normaliser(s.get("quote"))
            if len(q) > 40:
                self.par_citation.setdefault(q, m)

    def par_passage(self, ev: dict[str, Any]) -> dict[str, Any] | None:
        for m, s in self.par_segment.get((ev.get("document_id"), ev.get("segment_id")), []):
            if citations_chevauchent(ev, s):
                return m
        return self.par_citation.get(normaliser(ev.get("quote"))) if len(normaliser(ev.get("quote"))) > 40 else None

    def meilleurs(self, e: tuple[str, set[str]], k: int = 20) -> list[tuple[float, dict[str, Any]]]:
        communs: dict[int, int] = {}
        for w in e[1]:
            for i in self.par_mot.get(w, ()):
                communs[i] = communs.get(i, 0) + 1
        def jac(i):
            b = self.items[i][1][1]
            return communs[i] / (len(e[1]) + len(b) - communs[i])
        proches = sorted(communs, key=jac, reverse=True)[:k]
        # Elagage : borne haute du score = (quick_ratio + Jaccard) / 2 ; le ratio exact (couteux) n'est calcule que si
        # le candidat peut encore battre le meilleur. Seul le premier element est garanti exact et en tete.
        resultats, meilleur = [], -1.0
        for i in proches:
            b = self.items[i][1]
            j = jac(i)
            sm = difflib.SequenceMatcher(None, e[0], b[0], autojunk=False)
            if (sm.quick_ratio() + j) / 2 <= meilleur:
                continue
            score = round((sm.ratio() + j) / 2, 3)
            resultats.append((score, self.items[i][0]))
            meilleur = max(meilleur, score)
        return sorted(resultats, key=lambda x: -x[0])


def construire_pool(base: dict[str, Any]) -> dict[str, Pool]:
    """Mesures comparables par candidat (actives ou non reprises ; ni rejetees ni fusionnees)."""
    pools: dict[str, Pool] = {}
    for m in base["mesures"]:
        if m["statut"] in ("active", "non_reprise"):
            pools.setdefault(m["candidate_id"], Pool()).ajouter(m)
    return pools


def pretrier(p: dict[str, Any], pool: Pool) -> dict[str, Any]:
    """Verdict gratuit : meme (citation ou texte tres proche), nouvelle (texte eloigne) ou a_arbitrer."""
    for ev in p.get("source_evidence") or []:
        m = pool.par_passage(ev)
        if m is not None:
            return {"verdict": "meme", "cible": m["uid"], "score": 1.0, "methode": "citation"}
    top = pool.meilleurs(empreinte_texte(p.get("title"), p.get("description")))
    if not top:
        return {"verdict": "nouvelle", "cible": None, "score": 0.0, "methode": "texte"}
    score, m = top[0]
    verdict = "meme" if score >= SEUIL_MEME else "nouvelle" if score < SEUIL_DIFFERENTE else "a_arbitrer"
    return {"verdict": verdict, "cible": m["uid"], "score": score, "methode": "texte"}


# --- Arbitrage (modele chat, plafonne, en cache) ----------------------------------------------------------------------

CONSIGNE_ARBITRE = (
    "Tu compares, sans connaitre leur auteur, deux formulations d'engagements tires des programmes d'un meme candidat : "
    "`existante` (deja connue) et `nouvelle` (tiree d'un document plus recent ou d'une autre source). Ne cherche pas a "
    "deviner le candidat. Pour chaque paire, choisis un verdict :\n"
    "- meme : le meme engagement, meme portee, seule la formulation change ;\n"
    "- precisee : le meme engagement, la nouvelle formulation ajoute des details compatibles (chiffre, calendrier, "
    "modalite) sans rien changer de l'engagement ;\n"
    "- modifiee : le meme sujet et le meme dispositif, mais l'engagement change (montant, sens, perimetre, conditions, "
    "calendrier contradictoire) ;\n"
    "- differente : deux engagements distincts, meme si le theme est proche.\n"
    "Donne une confiance entre 0 et 1 et une note tres breve (120 caracteres maximum) qui cite la difference decisive.\n"
    "Reponds uniquement par l'objet JSON {\"paires\": [{\"id\": \"...\", \"verdict\": \"...\", \"confidence\": 0.0, "
    "\"note\": \"...\"}]}, une entree par identifiant recu.")


def texte_aveugle(titre: Any, description: Any, citation: Any, noms: set[str]) -> dict[str, Any]:
    from axes_2027 import blind_item
    item = blind_item({"id": "x", "title": titre, "description": description,
                       "source_evidence": [{"quote": citation or ""}]}, noms)
    return {k: item[k] for k in ("title", "description", "quote")}


def paire(m: dict[str, Any], p: dict[str, Any], noms: set[str]) -> dict[str, Any]:
    v = m["versions"][-1]
    q_old = ((v.get("sources") or [{}])[0]).get("quote")
    q_new = ((p.get("source_evidence") or [{}])[0]).get("quote")
    return {"existante": texte_aveugle(v["title"], v["description"], q_old, noms),
            "nouvelle": texte_aveugle(p.get("title"), p.get("description"), q_new, noms)}


def cle_paire(modele: str, pr: dict[str, Any]) -> str:
    from scoring_context_2027 import digest
    return digest({"v": VERSION_ARBITRE, "modele": modele, "paire": pr, "consigne": CONSIGNE_ARBITRE})


def schema_arbitre() -> dict[str, Any]:
    item = {"type": "object", "additionalProperties": False, "required": ["id", "verdict", "confidence", "note"],
            "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                           "confidence": {"type": "number"}, "note": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["paires"],
            "properties": {"paires": {"type": "array", "items": item}}}


def requete_arbitre(modele: str, lot: list[dict[str, Any]], effort: str) -> dict[str, Any]:
    return {"model": modele, "max_tokens": 12000, "reasoning": {"effort": effort},
            "response_format": {"type": "json_schema", "json_schema": {"name": "rapprochement", "strict": True,
                                                                        "schema": schema_arbitre()}},
            "messages": [{"role": "user", "content": CONSIGNE_ARBITRE + "\n" + json.dumps({"paires": lot}, ensure_ascii=False)}]}


def lire_arbitrage(reponse: dict[str, Any], lot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    import programme_corpus_2027 as pc
    choix = (reponse.get("choices") or [{}])[0]
    if choix.get("finish_reason") != "stop":
        raise ValueError("Reponse interrompue.")
    items = pc.parse_json_object((choix.get("message") or {}).get("content"), "Rapprochement").get("paires")
    attendus = {x["id"] for x in lot}
    out = {}
    for it in items if isinstance(items, list) else []:
        conf = it.get("confidence") if isinstance(it, dict) else None
        if (isinstance(it, dict) and it.get("id") in attendus and it.get("verdict") in VERDICTS
                and isinstance(conf, (int, float)) and not isinstance(conf, bool) and 0 <= conf <= 1):
            out[it["id"]] = {"verdict": it["verdict"], "confiance": round(float(conf), 2),
                             "note": str(it.get("note") or "")[:160]}
    if not out:
        raise ValueError("Aucun verdict valide.")
    return out


def arbitrer(paires: dict[str, dict[str, Any]], modele: str, cle_api: str, journal: Any, cache: dict[str, Any],
             max_cost: float, effort: str = "low", taille_lot: int = 20, appel=None) -> dict[str, dict[str, Any]]:
    """Arbitre les paires absentes du cache, lot par lot, sans depasser le plafond (cout reel du journal)."""
    from scoring_context_2027 import request_json
    from update_corpus_2027 import journal_cost
    appel = appel or request_json
    a_faire = [(i, pr) for i, pr in paires.items() if cle_paire(modele, pr) not in cache]
    estime = 0.0  # cumul estime : protege aussi quand le cout reel n'est pas (encore) dans le journal
    for debut in range(0, len(a_faire), taille_lot):
        lot = a_faire[debut:debut + taille_lot]
        depense = max(estime, journal_cost(journal.path) if journal is not None else 0.0)
        if depense + COUT_PAR_PAIRE * len(lot) > max_cost:
            break
        estime = depense + COUT_PAR_PAIRE * len(lot)
        corps = [{"id": i, **pr} for i, pr in lot]
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(requete_arbitre(modele, corps, effort), ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + cle_api, "Content-Type": "application/json"})
        try:
            verdicts = lire_arbitrage(appel(req, 300, journal=journal, stage="rapprochement",
                                            proposal_ids=[i for i, _ in lot]), corps)
        except (OSError, ValueError, KeyError) as exc:
            print(f"ERREUR arbitrage ({len(lot)} paires) : {exc}", file=sys.stderr)
            continue
        for i, pr in lot:
            if i in verdicts:
                cache[cle_paire(modele, pr)] = verdicts[i]
    return {i: cache[cle_paire(modele, pr)] for i, pr in paires.items() if cle_paire(modele, pr) in cache}


# --- Integration dans la base ------------------------------------------------------------------------------------------

def _connues(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in base["mesures"]:
        for cid in [m["historique"]["corpus_id"], *m["historique"].get("alias", [])]:
            out.setdefault(cid, m)
    return out


def _ajouter_sources(m: dict[str, Any], p: dict[str, Any]) -> None:
    sources = m["versions"][-1]["sources"]
    for ev in p.get("source_evidence") or []:
        if not any(ev == s or citations_chevauchent(ev, s) for s in sources):
            sources.append(ev)


def _nouvelle_version(m: dict[str, Any], p: dict[str, Any], nature: str, date: str) -> None:
    import base_2027 as B
    m["versions"].append({"n": len(m["versions"]) + 1, "date": date, "title": p.get("title"),
                          "description": p.get("description"), "empreinte": B.empreinte(p.get("title"), p.get("description")),
                          "sources": p.get("source_evidence") or [], "nature": nature})
    m["proposition"] = {**m["proposition"], **{k: p[k] for k in ("title", "description", "source_url", "source_title",
                                                                 "source_date", "source_page", "source_evidence") if k in p}}
    m["a_annoter"] = True  # les notes restent celles de l'ancienne version jusqu'a la reannotation (phase 3)


def _documents(p: dict[str, Any]) -> set[str]:
    return {e.get("document_id") or (e.get("position") or {}).get("document_id") for e in p.get("source_evidence") or []} - {None}


def plan(base: dict[str, Any], data: dict[str, Any], noms: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Pre-tri de chaque proposition inconnue de la base : {corpus_id: {verdict, cible, score, methode, paire?}}.

    Les propositions d'un meme export sont comparees aussi entre elles (une mesure redite deux fois dans le nouveau
    document ne cree qu'une mesure) : une nouvelle mesure entre dans le pool des suivantes.
    """
    connues = _connues(base)
    pool = construire_pool(base)
    noms = noms or set()
    par_uid = {m["uid"]: m for m in base["mesures"]}
    out: dict[str, dict[str, Any]] = {}
    for p in data["proposals"]:
        if p["id"] in connues:
            continue
        cand_pool = pool.setdefault(p["candidate_id"], Pool())
        r = pretrier(p, cand_pool)
        if r["verdict"] == "a_arbitrer":
            r["paire"] = paire(par_uid[r["cible"]], p, noms)
        out[p["id"]] = r
        if r["verdict"] != "meme":  # mesure provisoire, cle = identifiant corpus : comparee aux suivantes
            provisoire = {"uid": p["id"], "candidate_id": p["candidate_id"],
                          "versions": [{"title": p.get("title"), "description": p.get("description"),
                                        "sources": p.get("source_evidence") or []}]}
            par_uid[p["id"]] = provisoire
            cand_pool.ajouter(provisoire)
    return out


def integrer(base: dict[str, Any], data: dict[str, Any], prerapport: dict[str, dict[str, Any]],
             verdicts_arbitre: dict[str, dict[str, Any]] | None = None, marqueurs: dict[str, dict[str, Any]] | None = None,
             remplacements: dict[str, str] | None = None, date: str | None = None) -> dict[str, Any]:
    """Integre un export (complet ou partiel) dans la base. Modifie la base en place, renvoie le rapport.

    - identifiant corpus connu : mise a jour (nouvelle version si le texte change) ;
    - inconnu : verdict du pre-tri, ou de l'arbitre pour les paires douteuses ;
    - une mesure non retrouvee dont tous les documents sont couverts par l'export (ou remplaces) passe en non reprise.
    """
    import base_2027 as B
    date = date or B.maintenant()
    marqueurs = marqueurs or {}
    verdicts_arbitre = verdicts_arbitre or {}
    connues = _connues(base)
    par_uid = {m["uid"]: m for m in base["mesures"]}
    provisoires: dict[str, dict[str, Any]] = {}  # identifiant corpus d'une nouvelle mesure -> mesure creee
    touchees: set[str] = set()
    rapport = {k: 0 for k in ("connues", "nouvelles_versions", "meme", "precisee", "modifiee", "nouvelles", "incertaines",
                              "non_reprises", "reprises")}

    def creer(p: dict[str, Any], rapprochement: dict[str, Any] | None) -> dict[str, Any]:
        cand = p["candidate_id"]
        n = base["compteurs"].get(cand, 0) + 1
        base["compteurs"][cand] = n
        m = {"uid": f"m-{cand}-{n:04d}", "candidate_id": cand, "theme_id": p.get("theme_id"), "statut": "active",
             "versions": [{"n": 1, "date": date, "title": p.get("title"), "description": p.get("description"),
                           "empreinte": B.empreinte(p.get("title"), p.get("description")),
                           "sources": p.get("source_evidence") or []}],
             "file": [], "historique": {"corpus_id": p["id"]}, "ajoutee_le": date, "nouvelle": True, "a_annoter": True,
             "proposition": {k: v for k, v in p.items() if k not in B.CHAMPS_EXCLUS}, "annotation": None,
             "affichage": {"selection": (marqueurs.get(p["id"]) or {}).get("selection") or "n8",
                           "precision": p.get("precision"), "precision_llm": p.get("precision_llm")}}
        if rapprochement:
            m["rapprochement"] = rapprochement
        base["mesures"].append(m)
        par_uid[m["uid"]] = m
        touchees.add(m["uid"])  # creee par cette integration : jamais « non reprise »
        return m

    for p in data["proposals"]:
        cid = p["id"]
        m = connues.get(cid)
        if m is not None:  # deja connue : comme migrer
            rapport["connues"] += 1
            if m["statut"] == "non_reprise":
                m["statut"] = "active"
                rapport["reprises"] += 1
            if m["versions"][-1]["empreinte"] != B.empreinte(p.get("title"), p.get("description")):
                _nouvelle_version(m, p, "texte", date)
                rapport["nouvelles_versions"] += 1
            m["proposition"] = {k: v for k, v in p.items() if k not in B.CHAMPS_EXCLUS}
            touchees.add(m["uid"])
            continue
        r = dict(prerapport.get(cid) or {"verdict": "nouvelle", "cible": None, "score": 0.0, "methode": "texte"})
        cible = par_uid.get(r.get("cible")) or provisoires.get(r.get("cible"))
        verdict = r["verdict"]
        trace = {"cible": cible["uid"] if cible else None, "score": r.get("score"), "methode": r.get("methode"), "date": date}
        if verdict == "a_arbitrer":
            arb = verdicts_arbitre.get(cid)
            if arb and arb["confiance"] >= CONFIANCE_ARBITRE and cible is not None:
                verdict = arb["verdict"]
                trace.update(methode="arbitre", verdict_arbitre=arb["verdict"], confiance=arb["confiance"], note=arb["note"])
            else:
                trace.update(etat="incertain", verdict_arbitre=(arb or {}).get("verdict"),
                             confiance=(arb or {}).get("confiance"), note=(arb or {}).get("note"))
                provisoires[cid] = creer(p, trace)
                rapport["incertaines"] += 1
                continue
        if verdict in ("meme", "precisee", "modifiee") and cible is not None:
            cible.setdefault("historique", {}).setdefault("alias", []).append(cid)
            cible.setdefault("rapprochements", []).append({**trace, "corpus_id": cid, "verdict": verdict})
            if verdict == "meme":
                _ajouter_sources(cible, p)
            else:
                _nouvelle_version(cible, p, verdict, date)
            if cible["statut"] == "non_reprise":
                cible["statut"] = "active"
            touchees.add(cible["uid"])
            rapport[verdict] += 1
            continue
        provisoires[cid] = creer(p, {**trace, "verdict": "differente" if verdict == "differente" else "nouvelle"})
        rapport["nouvelles"] += 1

    couverts = {d for p in data["proposals"] for d in _documents(p)} | set((remplacements or {}).keys())
    for m in base["mesures"]:
        if m["uid"] in touchees or m["statut"] != "active":
            continue
        docs = {s.get("document_id") or (s.get("position") or {}).get("document_id") for s in m["versions"][-1]["sources"]} - {None}
        if docs and docs <= couverts:
            m["statut"] = "non_reprise"
            rapport["non_reprises"] += 1
    base["meta"]["mis_a_jour_le"] = date
    for key in ("candidates", "themes", "dimensions_schema"):
        if key in data:
            base[key] = data[key]
    return rapport
