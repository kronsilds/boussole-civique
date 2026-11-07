import argparse
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import base_2027 as B
import boussole_2027 as BO
import chaine_2027 as CH
import programme_corpus_2027 as pc


def prop(i, doc, titre):
    return {"id": f"corpus-{i:024d}", "candidate_id": "roussel", "theme_id": "emploi", "title": titre,
            "description": f"Description {i}.", "precision": "precis",
            "source_evidence": [{"document_id": doc, "segment_id": f"s{i}", "start": 0, "end": 40, "quote": f"citation {i} " + "x" * 50}]}


def doc(i, h):
    return {"id": i, "url": f"https://exemple.fr/{i}", "status": "ready", "bindings": [], "text_hash": h,
            "extraction": {"complete": True, "text_hash": h, "chunks": [{"status": "ready"}]}}


class SourcesTests(unittest.TestCase):
    def test_injection_and_inventory_accept_deposits(self):
        racine = Path(tempfile.mkdtemp())
        (racine / "corpus_programmes" / "depots").mkdir(parents=True)
        (racine / "corpus_programmes" / "depots" / "a.pdf").write_bytes(b"%PDF")
        data = {"candidates": [{"id": "roussel", "name": "Roussel", "program": {"main_url": "https://pcf.fr/prog"}}]}
        ajouts = [{"id": "s-0001", "candidate_id": "roussel", "type": "entretien", "url": "https://exemple.fr/itw", "date": "2026-11-10"},
                  {"id": "s-0002", "candidate_id": "roussel", "type": "programme", "fichier": "corpus_programmes/depots/a.pdf",
                   "nom_fichier": "a.pdf"}]
        data = CH.injecter_sources(data, ajouts, racine)
        data = CH.injecter_sources(data, ajouts, racine)  # idempotent
        liens = data["candidates"][0]["program"]["thematic_links"]
        self.assertEqual(len(liens), 2)
        manifeste = {"documents": {}}
        ids = pc.inventory(data, manifeste, [])
        self.assertEqual(len(ids), 3)
        roles = {b["role"] for d in manifeste["documents"].values() for b in d["bindings"]}
        self.assertEqual(roles, {"programme", "entretien"})
        dates = {b["published_date"] for d in manifeste["documents"].values() for b in d["bindings"]}
        self.assertIn("2026-11-10", dates)
        self.assertIn(CH.doc_id_de(CH.url_de(ajouts[1], racine)), manifeste["documents"])
        self.assertFalse(pc.depot_url("file:///C:/Windows/system32/x.pdf"))  # seuls les depots sont admis

    def test_source_status_follows_manifest(self):
        racine = Path(tempfile.mkdtemp())
        a = {"id": "s-0001", "candidate_id": "roussel", "type": "entretien", "url": "https://exemple.fr/itw", "statut": "en_attente"}
        manifeste = {"documents": {CH.doc_id_de(a["url"]): {**doc(CH.doc_id_de(a["url"]), "h")}}}
        self.assertEqual(CH.statut_sources([a], manifeste, racine), 1)
        self.assertEqual(a["statut"], "traitee")


class ChaineTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "corpus_programmes").mkdir()
        self.manifeste = {"version": 1, "documents": {"doc-a": doc("doc-a", "h1")}}
        self.props = [prop(1, "doc-a", "Hausse du SMIC"), prop(2, "doc-a", "Gratuité des cantines")]
        base, _ = B.migrer({"meta": {}, "candidates": [{"id": "roussel"}], "themes": [], "proposals": self.props})
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)
        self.annoter = []

    def ecrire_sources(self):
        B.ecrire_json(self.dir / "corpus_programmes" / "manifest.json", self.manifeste)

    def faux_run(self, ns, transformer=None, resume=None):
        self.ecrire_sources()
        B.ecrire_json(ns.out, {"meta": {}, "candidates": [{"id": "roussel"}], "themes": [], "proposals": self.props})
        if resume is not None:
            resume.update(cout=0.0)
        return 0

    def lancer(self, *extra):
        argv = ["x", "--racine", str(self.dir), "mise-a-jour", "--complet", "--no-pull", *extra]
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"), \
                mock.patch("update_corpus_2027.run", side_effect=self.faux_run), \
                mock.patch.object(BO, "cmd_annoter", side_effect=lambda c, a: self.annoter.append(
                    "contexte" if getattr(a, "contexte", False) else a.complement) or 0):
            return BO.main()

    def mesures(self):
        return B.lire_json(self.dir / "donnees" / "base_2027.json")["mesures"]

    def test_bootstrap_then_new_document_integrated(self):
        self.assertEqual(self.lancer("--max-cost", "1"), 0)
        self.assertEqual(len(self.mesures()), 2)  # amorce : le corpus actuel est considere comme integre
        self.assertEqual(self.annoter, ["contexte", None, "soc_finalite", "degre_rupture"])  # ordre des etapes
        self.manifeste["documents"]["doc-b"] = doc("doc-b", "h2")
        self.props.append(prop(3, "doc-b", "Interdire les licenciements boursiers dans les grands groupes"))
        self.assertEqual(self.lancer("--max-cost", "1"), 0)
        ms = self.mesures()
        self.assertEqual(len(ms), 3)
        self.assertTrue(ms[-1]["nouvelle"])
        self.assertIn("doc-b", B.lire_json(self.dir / "donnees" / "base_2027.json")["meta"]["documents_integres"])
        self.assertEqual(self.lancer("--max-cost", "1"), 0)  # rien de nouveau : pas de doublon
        self.assertEqual(len(self.mesures()), 3)
        runs = B.lire_json(self.dir / "donnees" / "budget_2027.json")["runs"]
        self.assertEqual(len(runs), 3)

    def test_plan_mode_integrates_nothing(self):
        self.lancer("--max-cost", "1")  # amorce
        self.manifeste["documents"]["doc-b"] = doc("doc-b", "h2")
        self.props.append(prop(3, "doc-b", "Interdire les licenciements boursiers"))
        self.assertEqual(self.lancer(), 0)
        self.assertEqual(len(self.mesures()), 2)

    def test_safety_stop(self):
        self.lancer("--max-cost", "1")
        self.manifeste["documents"]["doc-b"] = doc("doc-b", "h2")
        self.props.append(prop(3, "doc-b", "Nouvelle mesure"))
        with mock.patch.object(CH, "SEUIL_NOUVELLES", 0):
            self.assertEqual(self.lancer("--max-cost", "1"), 1)
            self.assertEqual(len(self.mesures()), 2)
            self.assertEqual(self.lancer("--max-cost", "1", "--forcer"), 0)
        self.assertEqual(len(self.mesures()), 3)

    def test_monthly_cap_turns_run_into_plan(self):
        B.ecrire_json(self.dir / "donnees" / "budget_2027.json", {"runs": [{"date": datetime.now().isoformat(), "cout": 5.0}]})
        self.lancer("--max-cost", "1")  # amorce, mais plafond mensuel deja atteint
        self.manifeste["documents"]["doc-b"] = doc("doc-b", "h2")
        self.props.append(prop(3, "doc-b", "Nouvelle mesure"))
        self.assertEqual(self.lancer("--max-cost", "1", "--mensuel", "5"), 0)
        self.assertEqual(len(self.mesures()), 2)  # plan seulement


if __name__ == "__main__":
    unittest.main()


class ModeleTests(unittest.TestCase):
    def test_extraction_model_pinned_to_corpus(self):
        m = {"documents": {"a": {"extraction": {"model": "haiku"}}, "b": {"extraction": {"model": "haiku"}},
                           "c": {"extraction": {"model": "gpt"}}, "d": {}}}
        self.assertEqual(CH.modele_du_corpus(m), "haiku")
        self.assertIsNone(CH.modele_du_corpus({"documents": {}}))


class RegistreTests(unittest.TestCase):
    def test_extracted_despite_blank_pages_and_catch_up(self):
        ok = {"status": "ready", "text_hash": "h", "text_incomplete_pages": [3],
              "extraction": {"text_hash": "h", "complete": False, "chunks": [{"status": "ready"}]}}
        self.assertTrue(CH.extrait(ok))  # pages sans texte : extrait quand meme
        self.assertFalse(CH.extrait({**ok, "extraction": {**ok["extraction"], "chunks": [{"status": "error"}]}}))
        self.assertFalse(CH.extrait({**ok, "text_hash": "h2"}))  # texte change depuis l'extraction
        base, _ = B.migrer({"meta": {}, "candidates": [], "themes": [], "proposals": [prop(1, "doc-a", "Mesure")]})
        base["meta"]["documents_integres"] = {}
        manifeste = {"documents": {"doc-a": {**ok, "id": "doc-a"}, "doc-b": {**ok, "id": "doc-b"}}}
        docs, change = CH.documents_a_integrer(base, manifeste)
        self.assertTrue(change)
        self.assertEqual(docs, ["doc-b"])  # doc-a deja present dans la base : rattrape, pas reintegre
        self.assertIn("doc-a", base["meta"]["documents_integres"])
