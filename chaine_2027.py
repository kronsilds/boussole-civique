"""Chaine complete du pipeline unifie (spec_pipeline_unifie_2027.md, phase 5).

  python .\\boussole_2027.py mise-a-jour --complet                          # collecte (gratuite) et plan, aucun appel payant
  python .\\boussole_2027.py mise-a-jour --complet --max-cost 1 --mensuel 5  # chaine complete, plafonnee

Etapes, dans l'ordre :
1. sources : depot amont (git pull) + sources ajoutees au tableau de bord (sources_2027.json), collecte, OCR et
   extraction des documents nouveaux ou modifies (update_corpus_2027.run) ;
2. integration : seules les propositions des documents nouveaux ou modifies depuis la derniere integration
   (base.meta.documents_integres) sont rapprochees et integrees ; au premier passage, le corpus actuel sert d'amorce ;
3. annotation q1 des mesures nouvelles ou modifiees ;
4. complements, dans cet ordre : soc_finalite puis degre_rupture ;
5. calculs, file, export, bilan (lances par chaque etape) ; depense notee dans budget_2027.json.

Le plafond (--max-cost) couvre toute la chaine : chaque etape recoit ce qui reste. Le plafond mensuel (--mensuel) le
reduit si besoin. Arret de securite au-dela de SEUIL_NOUVELLES propositions nouvelles (changement de format probable) :
le run s'arrete apres le plan et attend --forcer. Codes : 0 termine, 1 arret de securite, 2 erreur, 3 plafond atteint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

import base_2027 as B
import programme_corpus_2027 as pc

SEUIL_NOUVELLES = 300
COMPLEMENTS_ORDRE = ("soc_finalite", "degre_rupture")
MODELE = "openai/gpt-6.1-terra"
EFFORT = "low"


def url_de(ajout: dict[str, Any], racine: Path) -> str:
    return ajout.get("url") or (racine / ajout["fichier"]).resolve().as_uri()


def doc_id_de(url: str) -> str:
    """Meme identifiant que programme_corpus_2027.inventory."""
    return hashlib.sha256(urldefrag(url)[0].encode()).hexdigest()[:24]


def injecter_sources(data: dict[str, Any], ajouts: list[dict[str, Any]], racine: Path) -> dict[str, Any]:
    """Ajoute les sources du tableau de bord aux liens du candidat, comme un lien thematique de l'amont."""
    candidats = {str(c["id"]): c for c in data.get("candidates", [])}
    for a in ajouts:
        c = candidats.get(a.get("candidate_id"))
        if c is None or a.get("statut") == "exclue":
            continue
        url = url_de(a, racine)
        liens = c.setdefault("program", {}).setdefault("thematic_links", [])
        if any(l.get("url") == url for l in liens):
            continue
        nom = (a.get("nom_fichier") or a.get("url") or "").lower()
        fmt = "pdf" if nom.endswith(".pdf") else "html" if nom.endswith((".html", ".htm")) else None
        liens.append({"url": url, "title": a.get("titre") or a.get("type"), "format": fmt, "role": a.get("type"),
                      "published_date": a.get("date"), "source_ajoutee": a.get("id")})
    return data


def statut_sources(ajouts: list[dict[str, Any]], manifeste: dict[str, Any], racine: Path) -> int:
    """Met a jour le statut des sources ajoutees d'apres le manifeste ; renvoie le nombre de changements."""
    changes = 0
    for a in ajouts:
        doc = manifeste["documents"].get(doc_id_de(url_de(a, racine)))
        if doc is None:
            continue
        nouveau = "traitee" if doc.get("status") == "ready" and (doc.get("extraction") or {}).get("complete") else \
            "erreur" if doc.get("status") not in ("ready", "pending") else "en_attente"
        if a.get("statut") != nouveau or a.get("document_id") != doc["id"]:
            a.update(statut=nouveau, document_id=doc["id"], erreur=doc.get("error"))
            changes += 1
    return changes


def extrait(d: dict[str, Any]) -> bool:
    """Texte actuel entierement extrait (tous les morceaux traites). Des pages sans texte (photos, pages blanches) ne
    l'empechent pas, contrairement au marqueur « complete » du manifeste."""
    e = d.get("extraction") or {}
    morceaux = e.get("chunks") or []
    return (d.get("status") == "ready" and e.get("text_hash") == d.get("text_hash") and bool(morceaux)
            and all(isinstance(m, dict) and m.get("status") == "ready" for m in morceaux))


def documents_a_integrer(base: dict[str, Any], manifeste: dict[str, Any]) -> tuple[list[str], bool]:
    """Documents extraits dont le texte n'a pas encore ete integre. Premier passage : amorce sur le corpus actuel.

    Rattrapage : un document extrait, absent du registre mais dont la base contient deja des mesures, est enregistre
    comme integre (sans quoi ses propositions ecartees a la selection reviendraient comme nouvelles).
    """
    prets = {i: d.get("text_hash") for i, d in manifeste["documents"].items() if extrait(d)}
    integres = base["meta"].get("documents_integres")
    if integres is None:
        base["meta"]["documents_integres"] = prets
        return [], True
    cites = {s.get("document_id") or (s.get("position") or {}).get("document_id")
             for m in base["mesures"] for s in m["versions"][-1]["sources"]}
    rattrapes = [i for i in prets if i not in integres and i in cites]
    for i in rattrapes:
        integres[i] = prets[i]
    return sorted(i for i, h in prets.items() if integres.get(i) != h), bool(rattrapes)


def documents_de(p: dict[str, Any]) -> set[str]:
    return {e.get("document_id") or (e.get("position") or {}).get("document_id") for e in p.get("source_evidence") or []} - {None}


def modele_du_corpus(manifeste: dict[str, Any]) -> str | None:
    """Modele qui a extrait le corpus existant (le plus frequent). Le cache d'extraction depend du modele : en changer
    reextrairait tout le corpus et produirait des propositions reformulees, prises pour nouvelles."""
    from collections import Counter
    modeles = Counter((d.get("extraction") or {}).get("model") for d in manifeste["documents"].values())
    modeles.pop(None, None)
    return modeles.most_common(1)[0][0] if modeles else None


def depense_depuis(debut: float, logs: Path) -> float:
    from update_corpus_2027 import journal_cost
    return round(sum(journal_cost(f) for f in logs.glob("llm_*.jsonl") if f.stat().st_mtime >= debut), 4) if logs.exists() else 0.0


def depense_du_mois(chemin: Path) -> float:
    mois = datetime.now().strftime("%Y-%m")
    return round(sum(r.get("cout", 0) for r in B.lire_json(chemin, {"runs": []})["runs"] if r.get("date", "").startswith(mois)), 4)


def noter(chemin: Path, cout: float, etapes: list[str], code: int) -> None:
    data = B.lire_json(chemin, {"runs": []})
    data["runs"].append({"date": datetime.now().isoformat(timespec="seconds"), "cout": round(cout, 4), "etapes": etapes, "code": code})
    B.ecrire_json(chemin, data)


def chaine(c: dict[str, Path], args: argparse.Namespace, BO: Any) -> int:
    import update_corpus_2027 as uc
    racine = Path(args.racine)
    budget_path = c["budget"]
    debut = time.time()
    plafond = max(0.0, args.max_cost)
    if args.mensuel:
        reste_mois = round(args.mensuel - depense_du_mois(budget_path), 4)
        if plafond > reste_mois:
            print(f"Plafond mensuel {args.mensuel} $ : {reste_mois} $ restants ce mois-ci ; plafond du run ramene a {max(reste_mois, 0)} $.")
            plafond = max(0.0, reste_mois)
    payant = plafond > 0
    restant = lambda: max(0.0, round(plafond - depense_depuis(debut, c["logs"]), 4))  # noqa: E731
    etapes: list[str] = []
    code = 0
    with BO.Verrou(c["verrou_chaine"], args.force_verrou):
        # 1. Sources, collecte, extraction
        sources_path = c["sources"]
        sources = B.lire_json(sources_path, {"ajouts": []})
        resume: dict[str, Any] = {}
        modele_extraction = args.modele_extraction or modele_du_corpus(pc.load_manifest(c["corpus"]))
        print(f"   Modele d'extraction : {modele_extraction or 'OPENROUTER_WEB_MODEL du .env'}"
              f"{' (choisi explicitement)' if args.modele_extraction else ' (celui du corpus existant)'}")
        ns = argparse.Namespace(repo_dir=c["amont"], corpus_dir=c["corpus"],
                                sources_file=c["surcharges"], out=c["propositions"],
                                candidate=args.candidate or [], model=modele_extraction, max_cost=restant() if payant else 0.0,
                                cost_per_call=uc.DEFAULT_COST_PER_CALL, retries=3, retry_wait=15.0, max_tokens=32768,
                                max_age_days=7, force_refresh=False, max_download_mib=50, pdf_engine="mistral-ocr",
                                no_pull=args.no_pull)
        print("== 1. Sources, collecte, extraction")
        uc.run(ns, transformer=lambda d: injecter_sources(d, sources["ajouts"], racine), resume=resume)
        etapes.append("sources")
        manifeste = pc.load_manifest(c["corpus"])
        if statut_sources(sources["ajouts"], manifeste, racine):
            B.ecrire_json(sources_path, sources)
        # 2. Integration des documents nouveaux ou modifies
        print("== 2. Integration")
        base = BO.charger_base(c)
        docs, amorce = documents_a_integrer(base, manifeste)
        if amorce:
            B.ecrire_json(c["base"], base, c["sauvegardes"])
            print(f"   Registre des documents integres : {len(base['meta']['documents_integres'])} documents (amorce ou rattrapage).")
        export = B.lire_json(ns.out, {"proposals": []})
        props = [p for p in export.get("proposals", []) if documents_de(p) & set(docs)]
        print(f"   {len(docs)} document(s) nouveau(x) ou modifie(s), {len(props)} proposition(s) a rapprocher.")
        if len(props) > SEUIL_NOUVELLES and not args.forcer:
            print(f"   ARRET DE SECURITE : plus de {SEUIL_NOUVELLES} propositions d'un coup. Verifier les sources, puis relancer avec --forcer.")
            noter(budget_path, depense_depuis(debut, c["logs"]), etapes, 1)
            return 1
        if props:
            filtre = c["export_nouveautes"]
            B.ecrire_json(filtre, {**export, "proposals": props})
            BO.cmd_integrer(c, argparse.Namespace(input=str(filtre), selection=None, plan=not payant, max_cost=restant(),
                                                  sans_arbitrage=payant and restant() <= 0, modele=MODELE, effort=EFFORT,
                                                  remplace=None, force_verrou=args.force_verrou))
            if payant:
                base = BO.charger_base(c)
                for d in docs:
                    base["meta"]["documents_integres"][d] = manifeste["documents"][d].get("text_hash")
                B.ecrire_json(c["base"], base, c["sauvegardes"])
            etapes.append("integration")
        # 3. Annotation, 4. complements (dans l'ordre : le degre depend de la finalite)
        commun = dict(racine=args.racine, pilote=None, uid=None, limit=0, batch_submit=False, batch_collect=False,
                      modele=MODELE, effort=EFFORT, comparer=None, force_verrou=args.force_verrou)
        print("== 3. Annotation q1")
        BO.cmd_annoter(c, argparse.Namespace(**commun, complement=None, max_cost=restant() if payant else 0.0))
        etapes.append("annotation")
        for q in COMPLEMENTS_ORDRE:
            print(f"== 4. Complement {q}")
            BO.cmd_annoter(c, argparse.Namespace(**commun, complement=q, max_cost=restant() if payant else 0.0))
            etapes.append(f"complement:{q}")
        # 5. Calculs, file, export, bilan
        print("== 5. Calculs, file, export, bilan")
        cout = depense_depuis(debut, c["logs"])
        print(json.dumps(BO.executer(c, list(BO.ETAPES_GRATUITES), {"chaine": etapes, "cout": cout, "plafond": plafond},
                                     changement_methode=True), ensure_ascii=False, indent=1))
        if payant and restant() <= 0:
            code = 3
            print("Plafond atteint : relancer pour finir les etapes restantes (tout ce qui est fait reste en cache).")
        if not payant:
            print("Plan seulement (pas de --max-cost) : aucune etape payante lancee ; les etapes 3 et 4 ne voient les "
                  "nouvelles mesures qu'apres l'integration.")
        noter(budget_path, cout, etapes, code)
        print(f"Cout du run : {cout:.4f} $ (plafond {plafond} $).")
    return code
