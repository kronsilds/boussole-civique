"""Orchestrateur du pipeline unifie (spec_pipeline_unifie_2027.md). Phase 1 : etapes gratuites.

  python .\\boussole_2027.py plan                         # etat, file, etapes a venir (gratuit)
  python .\\boussole_2027.py migrer --input export.json [--selection selection.json]   # creation initiale de la base
  python .\\boussole_2027.py mise-a-jour                  # calculs -> file -> export -> bilan (gratuit en phase 1)
  python .\\boussole_2027.py integrer --input nouvel_export.json [--plan] [--max-cost 0.1 | --sans-arbitrage]
  python .\\boussole_2027.py etape calculs|file|export|bilan
  python .\\boussole_2027.py decision --uid m-roussel-0001 --type validation
  python .\\boussole_2027.py file [--motif nouvelle_mesure] [--limit 20]

  python .\\boussole_2027.py tableau-de-bord [--port 8765]   # http://127.0.0.1:8765

Verrou contre deux runs simultanes, ecriture atomique, 5 sauvegardes de la base. Aucun appel reseau.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import base_2027 as B

ETAPES_GRATUITES = ("calculs", "file", "export", "bilan")
A_VENIR = {"sources et extraction": "mise-a-jour --complet (sources ajoutees au tableau de bord comprises)",
           "rapprochement": "fait : boussole_2027.py integrer --input <export>", "annotation": "boussole_2027.py annoter (questionnaire q1)"}


class Verrou:
    def __init__(self, path: Path, force: bool = False):
        self.path, self.force = path, force

    def __enter__(self):
        if self.path.exists() and not self.force:
            age = (time.time() - self.path.stat().st_mtime) / 3600
            raise RuntimeError(f"Un run semble en cours ({self.path}, {age:.1f} h). --force-verrou si ce n'est pas le cas.")
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


DONNEES = "donnees"  # sous-dossier des donnees du pipeline (entrees versionnees et sorties non versionnees)


def chemins(args: argparse.Namespace) -> dict[str, Path]:
    """Tous les chemins du pipeline, relatifs a --racine : donnees dans donnees/, dossiers de travail a la racine."""
    racine = Path(args.racine)
    d = racine / DONNEES
    return {"donnees": d, "base": d / "base_2027.json", "decisions": d / "decisions_2027.json",
            "export": d / "donnees_interface_2027.json", "nouveautes": d / "nouveautes_2027.json",
            "sources": d / "sources_2027.json", "surcharges": d / "sources_surcharges.json",
            "propositions": d / "propositions_programmes_2027.json", "export_nouveautes": d / "export_nouveautes_2027.json",
            "budget": d / "budget_2027.json", "cache_rapprochement": d / "cache_rapprochement_2027.json",
            "cache_annotation": d / "cache_annotation_2027.json", "batch_annotation": d / "annotation_batch_2027.json",
            "cache_complements": d / "cache_complements_2027.json", "cache_contexte": d / "cache_contexte_2027.json",
            "batch_contexte": d / "contexte_batch_2027.json",
            "lexique": d / "lexique_2027.json",
            "runs": racine / "runs", "sauvegardes": racine / "sauvegardes", "logs": racine / "logs",
            "corpus": racine / "corpus_programmes", "amont": racine / "upstream_repo",
            "verrou": racine / ".boussole.lock", "verrou_chaine": racine / ".boussole_chaine.lock"}


def charger_base(c: dict[str, Path]) -> dict[str, Any]:
    base = B.lire_json(c["base"])
    if base is None:
        raise ValueError(f"{c['base']} absent : lancer d'abord « migrer ».")
    return base


def export_precedent(c: dict[str, Path], base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Lignes du dernier export, indexees par uid (un export d'avant la migration utilise les identifiants corpus)."""
    data = B.lire_json(c["export"], {"proposals": []})
    uid_de = {m["historique"]["corpus_id"]: m["uid"] for m in base["mesures"]}
    return {uid_de.get(r["id"], r["id"]): {**r, "id": uid_de.get(r["id"], r["id"])} for r in data.get("proposals", [])}


def executer(c: dict[str, Path], etapes: list[str], rapport_migration: dict[str, int] | None = None,
             changement_methode: bool = False) -> dict[str, Any]:
    base = charger_base(c)
    decisions = B.lire_json(c["decisions"], [])
    precedent = export_precedent(c, base)
    vues = B.calculer(base, decisions)  # toujours recalcule : gratuit et necessaire aux etapes suivantes
    base["meta"]["calcule_le"] = B.maintenant()  # decisions posterieures = pas encore appliquees
    file: Counter = Counter()
    nouv = None
    if "file" in etapes or "export" in etapes or "bilan" in etapes:
        file = B.construire_file(base, vues, precedent, changement_methode=changement_methode)
    if "export" in etapes:
        export = B.exporter(base, vues, precedent)
        nouv = B.nouveautes(precedent, export)
        B.ecrire_json(c["export"], export, compact=True)
        B.ecrire_json(c["nouveautes"], nouv)
    B.ecrire_json(c["base"], base, c["sauvegardes"])
    resume = {"file": dict(file), "nouveautes": {k: len(v) for k, v in (nouv or {}).items() if isinstance(v, list)}}
    if "bilan" in etapes:
        data, md = B.bilan(base, file, nouv, etapes, 0.0, rapport_migration)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        B.ecrire_json(c["runs"] / f"{stamp}.json", data)
        (c["runs"] / f"{stamp}.md").write_text(md, encoding="utf-8")
        resume["bilan"] = str(c["runs"] / f"{stamp}.md")
    return resume


def cmd_plan(c: dict[str, Path], args: argparse.Namespace) -> int:
    base = B.lire_json(c["base"])
    if base is None:
        print("Base absente : « migrer » d'abord.")
        return 0
    statuts = Counter(m["statut"] for m in base["mesures"])
    file = Counter(f["motif"] for m in base["mesures"] for f in m.get("file") or [])
    print(f"Base : {len(base['mesures'])} mesures ({dict(statuts)}), mise a jour {base['meta'].get('mis_a_jour_le')}.")
    print(f"File (dernier calcul) : {dict(file) or 'vide'}.")
    print(f"Decisions : {len(B.lire_json(c['decisions'], []))}.")
    for nom in [c["batch_annotation"], *sorted(c["donnees"].glob("complement_*_batch_2027.json"))]:
        batch = B.lire_json(nom)
        if batch and not batch.get("collected_at"):
            print(f"Batch {nom.name} : {batch.get('batch_id')} - {batch.get('status')} (a recuperer : --batch-collect).")
    print("Etapes gratuites (mise-a-jour) : " + " -> ".join(ETAPES_GRATUITES) + ". Cout : 0 $.")
    for etape, quand in A_VENIR.items():
        print(f"  {etape} : {quand}")
    return 0


def cmd_migrer(c: dict[str, Path], args: argparse.Namespace) -> int:
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    marqueurs = {s["id"]: s for s in json.loads(Path(args.selection).read_text(encoding="utf-8"))["selected"]} \
        if args.selection else {}
    with Verrou(c["verrou"], args.force_verrou):
        base, rapport = B.migrer(data, marqueurs, B.lire_json(c["base"]))
        B.ecrire_json(c["base"], base, c["sauvegardes"])
        print(f"Migration : {json.dumps(rapport, ensure_ascii=False)}")
        if not args.sans_mise_a_jour:
            print(json.dumps(executer(c, list(ETAPES_GRATUITES), rapport, args.changement_methode), ensure_ascii=False, indent=1))
    return 0


def cmd_integrer(c: dict[str, Path], args: argparse.Namespace) -> int:
    """Integre un nouvel export (complet ou partiel) avec rapprochement ; arbitrage payant seulement sous plafond."""
    import os

    import pipeline_scoring_2027 as ps
    import rapprochement_2027 as R
    from commun_2027 import blind_names
    from llm_logging_2027 import LLMJournal
    from update_corpus_2027 import journal_cost
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    marqueurs = {s["id"]: s for s in json.loads(Path(args.selection).read_text(encoding="utf-8"))["selected"]} \
        if args.selection else {}
    remplacements = dict(r.split("=", 1) for r in args.remplace or [])
    with Verrou(c["verrou"], args.force_verrou):
        base = charger_base(c)
        noms = blind_names(data.get("candidates") or base.get("candidates") or [])
        pre = R.plan(base, data, noms)
        compte = Counter(r["verdict"] for r in pre.values())
        cache = B.lire_json(c["cache_rapprochement"], {})
        paires = {cid: r["paire"] for cid, r in pre.items() if r["verdict"] == "a_arbitrer" and r.get("paire")}
        a_faire = [cid for cid, pr in paires.items() if R.cle_paire(args.modele, pr) not in cache]
        print(f"Plan : {len(data['proposals'])} propositions, {len(data['proposals']) - len(pre)} deja connues ; "
              f"inconnues : meme {compte['meme']}, nouvelles {compte['nouvelle']}, a arbitrer {compte['a_arbitrer']} "
              f"({len(paires) - len(a_faire)} en cache, {len(a_faire)} a faire, estimation "
              f"{len(a_faire) * R.COUT_PAR_PAIRE:.3f} $, modele {args.modele}).")
        if args.plan:
            return 0
        if a_faire and args.max_cost <= 0 and not args.sans_arbitrage:
            print("Aucun appel lance. --max-cost <dollars> pour arbitrer, ou --sans-arbitrage : les paires douteuses "
                  "deviennent des mesures « rapprochement incertain », non publiees avant validation.")
            return 0
        cout = 0.0
        if a_faire and args.max_cost > 0:
            ps.load_env_file(Path(__file__).with_name(".env"))
            cle = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not cle:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(cle,))
            try:
                R.arbitrer(paires, args.modele, cle, journal, cache, args.max_cost, effort=args.effort)
                cout = journal_cost(journal.path)
            finally:
                journal.close()
            B.ecrire_json(c["cache_rapprochement"], cache)
        verdicts = {cid: cache[R.cle_paire(args.modele, pr)] for cid, pr in paires.items()
                    if R.cle_paire(args.modele, pr) in cache}
        rapport = R.integrer(base, data, pre, verdicts, marqueurs, remplacements)
        B.ecrire_json(c["base"], base, c["sauvegardes"])
        print(f"Integration : {json.dumps(rapport, ensure_ascii=False)} ; cout {cout:.4f} $")
        print(json.dumps(executer(c, list(ETAPES_GRATUITES), {**rapport, "cout_arbitrage": round(cout, 4)}),
                         ensure_ascii=False, indent=1))
    return 0


def cmd_complement(c: dict[str, Path], args: argparse.Namespace) -> int:
    """Question ajoutee apres coup (questionnaire_2027.COMPLEMENTS), posee aux seules mesures concernees."""
    import os

    import annotation_2027 as A
    import pipeline_scoring_2027 as ps
    import commun_2027 as rc
    from commun_2027 import blind_names
    from llm_logging_2027 import LLMJournal
    from update_corpus_2027 import journal_cost
    qs = (args.complement,)
    etat_batch = c["donnees"] / f"complement_{args.complement}_batch_2027.json"
    cache_path = c["cache_complements"]
    with Verrou(c["verrou"], args.force_verrou):
        base = charger_base(c)
        uids = set(args.uid or []) or None
        mesures = A.a_completer(base, args.complement, uids)[:args.limit or None]
        noms = blind_names(base.get("candidates") or [])
        items = [A.item(m, noms) for m in mesures]
        cache = B.lire_json(cache_path, {})
        todo = [i for i in items if A.cle_complement(args.modele, i, qs, args.effort) not in cache]
        lots = [todo[s:s + A.TAILLE_LOT_COMPLEMENT] for s in range(0, len(todo), A.TAILLE_LOT_COMPLEMENT)]
        print(f"Plan complement {args.complement} : {len(items)} mesures concernees, {len(items) - len(todo)} en cache, "
              f"{len(todo)} a faire en {len(lots)} lots ; estimation directe {len(todo) * A.COUT_COMPLEMENT:.2f} $, "
              f"batch {len(todo) * A.COUT_COMPLEMENT / 2:.2f} $ ; modele {args.modele}, raisonnement {args.effort}.")
        cout = 0.0
        if args.batch_submit or args.batch_collect or (todo and args.max_cost > 0):
            ps.load_env_file(Path(__file__).with_name(".env"))
            cle = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not cle:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(cle,))
            try:
                if args.batch_collect:
                    effort_batch = (B.lire_json(etat_batch) or {}).get("effort", args.effort)
                    print(json.dumps(rc.batch_collect(
                        etat_batch, cle, cache, cache_path, journal, etat_batch.with_name(etat_batch.stem + "_resultats.json"),
                        parse=lambda corps, lot: A.lire_complement(corps, lot, qs),
                        key_fn=lambda mod, it: A.cle_complement(mod, it, qs, effort_batch)), ensure_ascii=False, indent=1))
                elif args.batch_submit:
                    if args.max_cost <= 0 or not lots:
                        raise ValueError("--batch-submit demande --max-cost et des mesures a completer.")
                    etat = rc.batch_submit(etat_batch, args.modele, args.effort, cle, lots, args.max_cost, A.COUT_COMPLEMENT / 2,
                                           journal, make_body=lambda lot: A.requete_complement(args.modele, lot, args.effort, qs))
                    print(f"Batch envoye : {etat['batch_id']}, {len(etat['lots'])} requetes. Recuperer avec --batch-collect.")
                    return 0
                else:
                    stats = A.completer_direct(lots, args.modele, args.effort, qs, cle, journal, cache, args.max_cost)
                    B.ecrire_json(cache_path, cache)
                    print(f"Complement direct : {json.dumps(stats)}")
                cout = journal_cost(journal.path)
            finally:
                journal.close()
        elif todo:
            print("Aucun appel lance. --max-cost <dollars> (appel direct) ou --batch-submit --max-cost <dollars>.")
        date, appliquees = B.maintenant(), 0
        for m, it in zip(mesures, items):
            r = cache.get(A.cle_complement(args.modele, it, qs, args.effort))
            if r:
                A.appliquer_complement(m, r, args.modele, args.effort, date)
                appliquees += 1
        if not appliquees:
            return 0
        B.ecrire_json(c["base"], base, c["sauvegardes"])
        print(f"Complements appliques : {appliquees} ; cout {cout:.4f} $")
        print(json.dumps(executer(c, list(ETAPES_GRATUITES), {"complement": args.complement, "appliques": appliquees,
                                                               "cout": round(cout, 4)}, changement_methode=True),
                         ensure_ascii=False, indent=1))
    return 0


def cmd_annoter(c: dict[str, Path], args: argparse.Namespace) -> int:
    """Questionnaire q1 : plan gratuit ; appel direct (--max-cost) ou batch (--batch-submit / --batch-collect)."""
    if getattr(args, "contexte", False):
        return cmd_contexte(c, args)
    if args.complement:
        return cmd_complement(c, args)
    import math
    import os

    import annotation_2027 as A
    import pipeline_scoring_2027 as ps
    import commun_2027 as rc
    from commun_2027 import blind_names
    from llm_logging_2027 import LLMJournal
    from update_corpus_2027 import journal_cost
    etat_batch = c["batch_annotation"]
    cache_path = c["cache_annotation"]
    with Verrou(c["verrou"], args.force_verrou):
        base = charger_base(c)
        decisions = B.lire_json(c["decisions"], [])
        uids = set(args.uid or []) or None
        if args.pilote:
            par_corpus = {m["historique"]["corpus_id"]: m["uid"] for m in base["mesures"]}
            pilote = json.loads(Path(args.pilote).read_text(encoding="utf-8"))["mesures"]
            uids = {par_corpus[r["id"]] for r in pilote if r["id"] in par_corpus}
        mesures = A.a_annoter(base, decisions, uids)[:args.limit or None]
        noms = blind_names(base.get("candidates") or [])
        items = [A.item(m, noms, A.reprises(m, decisions)) for m in mesures]
        if len({i["id"] for i in items}) != len(items):
            raise ValueError("Identifiants courts en collision.")
        cache = B.lire_json(cache_path, {})
        todo = [i for i in items if A.cle(args.modele, i, args.effort) not in cache]
        lots = [todo[s:s + A.TAILLE_LOT] for s in range(0, len(todo), A.TAILLE_LOT)]
        print(f"Plan : {len(items)} mesures a annoter (questionnaire {A.Q.VERSION}), {len(items) - len(todo)} en cache, "
              f"{len(todo)} a faire en {len(lots)} lots ; estimation directe {len(todo) * A.COUT_DIRECT:.2f} $, "
              f"batch {len(todo) * A.COUT_DIRECT / 2:.2f} $ ; modele {args.modele}, raisonnement {args.effort}.")
        cout = 0.0
        if args.batch_submit or args.batch_collect or (todo and args.max_cost > 0):
            ps.load_env_file(Path(__file__).with_name(".env"))
            cle = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not cle:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(cle,))
            try:
                if args.batch_collect:
                    effort_batch = (B.lire_json(etat_batch) or {}).get("effort", args.effort)
                    rapport = rc.batch_collect(etat_batch, cle, cache, cache_path, journal,
                                               etat_batch.with_name(etat_batch.stem + "_resultats.json"),
                                               parse=A.lire, key_fn=lambda mod, it: A.cle(mod, it, effort_batch))
                    print(json.dumps(rapport, ensure_ascii=False, indent=1))
                elif args.batch_submit:
                    if args.max_cost <= 0 or not lots:
                        raise ValueError("--batch-submit demande --max-cost et des mesures a annoter.")
                    etat = rc.batch_submit(etat_batch, args.modele, args.effort, cle, lots, args.max_cost,
                                           A.COUT_DIRECT / 2, journal,
                                           make_body=lambda lot: A.requete(args.modele, lot, args.effort))
                    print(f"Batch envoye : {etat['batch_id']}, {len(etat['lots'])} requetes. Recuperer avec --batch-collect.")
                    return 0
                else:
                    stats = A.annoter_direct(lots, args.modele, args.effort, cle, journal, cache, args.max_cost)
                    B.ecrire_json(cache_path, cache)
                    print(f"Annotation directe : {json.dumps(stats)}")
                cout = journal_cost(journal.path)
            finally:
                journal.close()
        elif todo:
            print("Aucun appel lance. --max-cost <dollars> (appel direct) ou --batch-submit --max-cost <dollars>.")
        if args.comparer:  # comparaison avec une autre lecture en cache ; rien n'est applique a la base
            rapport = A.comparer(mesures, items, cache, args.modele, args.effort, args.comparer, cout)
            sortie = c["runs"] / f"comparaison_{args.effort}_{args.comparer}.json"
            B.ecrire_json(sortie, rapport)
            print(json.dumps({k: v for k, v in rapport.items() if k != "mesures"}, ensure_ascii=False, indent=1))
            print(f"Rapport : {sortie}")
            return 0
        date = B.maintenant()
        appliquees = 0
        for m, it in zip(mesures, items):
            r = cache.get(A.cle(args.modele, it, args.effort))
            if r:
                A.appliquer(m, r, args.modele, date)
                appliquees += 1
        if not appliquees:
            return 0
        B.ecrire_json(c["base"], base, c["sauvegardes"])
        print(f"Annotations appliquees : {appliquees} ; cout {cout:.4f} $")
        print(json.dumps(executer(c, list(ETAPES_GRATUITES), {"annotees": appliquees, "cout_annotation": round(cout, 4)},
                                  changement_methode=True), ensure_ascii=False, indent=1))
    return 0


def cmd_contexte(c: dict[str, Path], args: argparse.Namespace) -> int:
    """Lecture avec contexte (passage du document, lexique en source secondaire) : mesures en confiance basse, ou toutes
    (--tous) ; appel direct (--max-cost) ou batch (--batch-submit / --batch-collect)."""
    import os

    import annotation_2027 as A
    import commun_2027 as rc
    import contexte_2027 as CX
    import pipeline_scoring_2027 as ps
    from commun_2027 import blind_names
    from llm_logging_2027 import LLMJournal
    from update_corpus_2027 import journal_cost
    cache_path = c["cache_contexte"]
    etat_batch = c["batch_contexte"]
    tous = getattr(args, "tous", False)
    with Verrou(c["verrou"], args.force_verrou):
        base = charger_base(c)
        decisions = B.lire_json(c["decisions"], [])
        mesures = CX.a_relire(base, decisions, tous)[:args.limit or None]
        noms = blind_names(base.get("candidates") or [])
        lexique = B.lire_json(c["lexique"], {})
        masque = CX.masqueur(noms)
        items = [CX.item(m, noms, c["corpus"] / "texts", lexique, masque, A.reprises(m, decisions)) for m in mesures]
        if len({i["id"] for i in items}) != len(items):
            raise ValueError("Identifiants courts en collision.")
        cache = B.lire_json(cache_path, {})
        todo = [i for i in items if CX.cle(args.modele, i, args.effort) not in cache]
        lots = [todo[s:s + A_TAILLE_LOT] for s in range(0, len(todo), A_TAILLE_LOT)]
        print(f"Plan lecture avec contexte : {len(items)} mesures ({'toutes celles a lire' if tous else 'confiance basse (sens)'}), "
              f"{len(items) - len(todo)} en cache, {len(todo)} a lire en {len(lots)} lots "
              f"({sum('lexique' in i for i in items)} avec lexique) ; estimation directe {len(todo) * CX.COUT_ESTIME:.2f} $, "
              f"batch {len(todo) * CX.COUT_ESTIME / 2:.2f} $ ; modele {args.modele}, raisonnement {args.effort}.")
        cout = 0.0
        batch_submit, batch_collect = getattr(args, "batch_submit", False), getattr(args, "batch_collect", False)
        if batch_submit or batch_collect or (todo and args.max_cost > 0):
            ps.load_env_file(Path(__file__).with_name(".env"))
            cle = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not cle:
                raise ValueError("OPENROUTER_API_KEY manque ; aucun appel lance.")
            journal = LLMJournal(secrets=(cle,))
            try:
                if batch_collect:
                    effort_batch = (B.lire_json(etat_batch) or {}).get("effort", args.effort)
                    print(json.dumps(rc.batch_collect(etat_batch, cle, cache, cache_path, journal,
                                                      etat_batch.with_name(etat_batch.stem + "_resultats.json"),
                                                      parse=CX.lire, key_fn=lambda mod, it: CX.cle(mod, it, effort_batch)),
                                     ensure_ascii=False, indent=1))
                elif batch_submit:
                    if args.max_cost <= 0 or not lots:
                        raise ValueError("--batch-submit demande --max-cost et des mesures a lire.")
                    etat = rc.batch_submit(etat_batch, args.modele, args.effort, cle, lots, args.max_cost, CX.COUT_ESTIME / 2,
                                           journal, make_body=lambda lot: CX.requete(args.modele, lot, args.effort))
                    print(f"Batch envoye : {etat['batch_id']}, {len(etat['lots'])} requetes. Recuperer avec --batch-collect.")
                    return 0
                else:
                    stats = CX.relire_direct(lots, args.modele, args.effort, cle, journal, cache, args.max_cost,
                                             ecrire=lambda ca: B.ecrire_json(cache_path, ca))
                    print(f"Lecture directe : {json.dumps(stats)}")
                cout = journal_cost(journal.path)
            finally:
                journal.close()
        elif todo:
            print("Aucun appel lance. --max-cost <dollars> (appel direct) ou --batch-submit --max-cost <dollars>.")
        date = B.maintenant()
        appliquees = 0
        for m, it in zip(mesures, items):
            r = cache.get(CX.cle(args.modele, it, args.effort))
            if r:
                CX.appliquer(m, r, args.modele, date)
                appliquees += 1
        if not appliquees:
            return 0
        B.ecrire_json(c["base"], base, c["sauvegardes"])
        print(f"Relectures appliquees : {appliquees} ; cout {cout:.4f} $")
        print(json.dumps(executer(c, list(ETAPES_GRATUITES), {"relecture_contexte": appliquees, "cout": round(cout, 4)},
                                  changement_methode=True), ensure_ascii=False, indent=1))
    return 0


A_TAILLE_LOT = 10  # mesures par requete (comme l'annotation q1)


def cmd_mise_a_jour(c: dict[str, Path], args: argparse.Namespace) -> int:
    if args.complet:  # chaine complete : sources -> extraction -> integration -> annotation -> complements -> calculs
        import chaine_2027
        return chaine_2027.chaine(c, args, sys.modules[__name__])
    if args.max_cost:
        print("Sans --complet, seules les etapes gratuites tournent ; --max-cost ignore.")
    with Verrou(c["verrou"], args.force_verrou):
        print(json.dumps(executer(c, list(ETAPES_GRATUITES), changement_methode=args.changement_methode), ensure_ascii=False, indent=1))
    return 0


def cmd_etape(c: dict[str, Path], args: argparse.Namespace) -> int:
    with Verrou(c["verrou"], args.force_verrou):
        print(json.dumps(executer(c, [args.nom], changement_methode=args.changement_methode), ensure_ascii=False, indent=1))
    return 0


def cmd_decision(c: dict[str, Path], args: argparse.Namespace) -> int:
    with Verrou(c["verrou"], args.force_verrou):
        base = charger_base(c)
        decisions = B.lire_json(c["decisions"], [])
        valeur = None if args.valeur == "null" else args.valeur
        d = B.nouvelle_decision(decisions, base, args.uid, args.type, args.champ, valeur, args.cible, args.motif)
        B.ecrire_json(c["decisions"], decisions)
        print(f"Decision {d['id']} enregistree ({d['type']} sur {d['uid']}, version {d['version']}). "
              f"Effet au prochain calcul (mise-a-jour ou etape calculs).")
    return 0


def cmd_file(c: dict[str, Path], args: argparse.Namespace) -> int:
    base = charger_base(c)
    lignes = [(f["priorite"], f["depuis"], f["motif"], m) for m in base["mesures"] for f in m.get("file") or []
              if not args.motif or f["motif"] == args.motif]
    lignes.sort(key=lambda x: (x[0], x[1]))
    print(f"{len(lignes)} entrees" + (f" (motif {args.motif})" if args.motif else "") + ".")
    for prio, depuis, motif, m in lignes[:args.limit]:
        print(f"  [{prio}] {motif:22} {m['uid']:20} {m['versions'][-1]['title'][:70]}")
    return 0


def cmd_planifier(c: dict[str, Path], args: argparse.Namespace) -> int:
    """Prepare le script de la mise a jour hebdomadaire et affiche la commande Windows a lancer (non executee)."""
    racine = Path(args.racine).resolve()
    script = racine / "planification" / "boussole_hebdo.cmd"
    script.parent.mkdir(exist_ok=True)
    lignes = ["@echo off", f'cd /d "{racine}"',
              f'"{sys.executable}" boussole_2027.py mise-a-jour --complet --max-cost {args.max_cost} --mensuel {args.mensuel}'
              r' >> runs\planifie.log 2>&1', ""]
    script.write_bytes("\r\n".join(lignes).encode("utf-8"))  # fins de ligne Windows pour un .cmd
    jour = {"lundi": "MON", "mardi": "TUE", "mercredi": "WED", "jeudi": "THU", "vendredi": "FRI", "samedi": "SAT",
            "dimanche": "SUN"}[args.jour]
    commande = f'schtasks /Create /TN "Boussole 2027 - mise a jour" /TR "\\"{script}\\"" /SC WEEKLY /D {jour} /ST {args.heure} /F'
    print(f"Script ecrit : {script}")
    print(f"Plafonds : {args.max_cost} $ par run, {args.mensuel} $ par mois.")
    print("Pour creer la tache planifiee Windows (a lancer soi-meme, dans PowerShell) :")
    print("  " + commande)
    print('Pour la supprimer : schtasks /Delete /TN "Boussole 2027 - mise a jour" /F')
    return 0


def cmd_tableau(c: dict[str, Path], args: argparse.Namespace) -> int:
    import tableau_de_bord_2027 as TB  # import tardif : le serveur n'est utile qu'ici
    TB.servir(Path(args.racine), args.port, args.reseau, args.nouveau_jeton)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", default=".", help="Dossier du projet (tests)")
    parser.add_argument("--force-verrou", action="store_true")
    sub = parser.add_subparsers(dest="commande", required=True)
    sub.add_parser("plan")
    p = sub.add_parser("migrer")
    p.add_argument("--input", required=True)
    p.add_argument("--selection")
    p.add_argument("--sans-mise-a-jour", action="store_true")
    p.add_argument("--changement-methode", action="store_true", help="Renotation voulue : deplacements non signales")
    p = sub.add_parser("integrer", help="Nouvel export (complet ou partiel) avec rapprochement des mesures")
    p.add_argument("--input", required=True)
    p.add_argument("--selection")
    p.add_argument("--plan", action="store_true", help="Pre-tri seul, rien n'est ecrit")
    p.add_argument("--max-cost", type=float, default=0.0, help="Plafond de l'arbitrage en dollars")
    p.add_argument("--sans-arbitrage", action="store_true")
    p.add_argument("--modele", default="openai/gpt-6.1-terra")
    p.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    p.add_argument("--remplace", action="append", metavar="ANCIEN_DOC=NOUVEAU_DOC",
                   help="Document remplace : ses mesures non retrouvees passent en non reprise")
    p = sub.add_parser("annoter", help="Questionnaire q1 (plan gratuit sans --max-cost)")
    p.add_argument("--pilote", help="Rapport de pilote dont les mesures forment l'echantillon (ex. archives/pilotes/pilote_descripteurs_2027.json)")
    p.add_argument("--uid", action="append")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-cost", type=float, default=0.0)
    p.add_argument("--batch-submit", action="store_true")
    p.add_argument("--batch-collect", action="store_true")
    p.add_argument("--modele", default="openai/gpt-6.1-terra")
    p.add_argument("--effort", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--contexte", action="store_true",
                   help="Lit avec le passage du document et le lexique (contexte_2027.py) les mesures en confiance basse")
    p.add_argument("--tous", action="store_true",
                   help="Avec --contexte : toutes les mesures pas encore lues avec le contexte pour leur version")
    p.add_argument("--complement", choices=["soc_finalite", "degre_rupture"],
                   help="Question ajoutee apres coup, posee aux seules mesures concernees (ex. soc_finalite)")
    p.add_argument("--comparer", choices=["low", "medium", "high"],
                   help="Compare a la lecture en cache de cet effort ; n'applique rien a la base")
    p = sub.add_parser("mise-a-jour", help="Etapes gratuites ; --complet : chaine complete (plan sans --max-cost)")
    p.add_argument("--complet", action="store_true", help="Sources, extraction, integration, annotation, complements, calculs")
    p.add_argument("--max-cost", type=float, default=0.0, help="Plafond de toute la chaine (avec --complet)")
    p.add_argument("--mensuel", type=float, default=0.0, help="Plafond mensuel (budget_2027.json)")
    p.add_argument("--no-pull", action="store_true", help="Ne pas mettre a jour le depot amont")
    p.add_argument("--candidate", action="append", help="Limiter la collecte a un candidat (repetable)")
    p.add_argument("--forcer", action="store_true", help="Passer l'arret de securite (trop de nouvelles propositions)")
    p.add_argument("--modele-extraction", help="Changer de modele d'extraction (reextrait tout le corpus) ; defaut : celui du corpus")
    p.add_argument("--changement-methode", action="store_true")
    p = sub.add_parser("etape")
    p.add_argument("nom", choices=ETAPES_GRATUITES)
    p.add_argument("--changement-methode", action="store_true")
    p = sub.add_parser("decision")
    p.add_argument("--uid", required=True)
    p.add_argument("--type", required=True, choices=B.TYPES_DECISION)
    p.add_argument("--champ")
    p.add_argument("--valeur")
    p.add_argument("--cible")
    p.add_argument("--motif")
    p = sub.add_parser("file")
    p.add_argument("--motif")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("planifier", help="Prepare la mise a jour hebdomadaire (affiche la commande schtasks)")
    p.add_argument("--jour", choices=["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"], default="lundi")
    p.add_argument("--heure", default="07:00")
    p.add_argument("--max-cost", type=float, default=1.0)
    p.add_argument("--mensuel", type=float, default=5.0)
    p = sub.add_parser("tableau-de-bord", help="Serveur local http://127.0.0.1:8765")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--reseau", action="store_true", help="Ecoute aussi sur le reseau local (lien avec jeton)")
    p.add_argument("--nouveau-jeton", action="store_true", help="Change le jeton (deconnecte les telephones)")
    args = parser.parse_args()
    c = chemins(args)
    commandes = {"plan": cmd_plan, "migrer": cmd_migrer, "integrer": cmd_integrer, "annoter": cmd_annoter, "mise-a-jour": cmd_mise_a_jour, "etape": cmd_etape,
                 "decision": cmd_decision, "file": cmd_file, "tableau-de-bord": cmd_tableau,
                 "planifier": cmd_planifier}
    try:
        return commandes[args.commande](c, args)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Erreur boussole: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
