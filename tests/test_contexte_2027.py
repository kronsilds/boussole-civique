import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import base_2027 as B
import boussole_2027 as BO
import contexte_2027 as CX
import questionnaire_2027 as Q
from test_base_2027 import REPONSES_Q1, annoter, data, prop


class NormalisationTests(unittest.TestCase):
    def test_indeterminate_neutral_in_pair_else_axis_dropped(self):
        r = {**REPONSES_Q1, "eco_distrib": Q.INDETERMINE, "sov_niveau": Q.INDETERMINE}
        n = Q.normaliser(r)
        self.assertEqual((n["eco_distrib"], n["sov_niveau"]), ("neutre", None))
        v, _ = Q.calculer(r)
        self.assertIsNotNone(v["eco"])  # l'Etat augmente : l'axe reste calcule
        self.assertIsNone(v["sov"])
        v, _ = Q.calculer({**r, "eco_etat": Q.INDETERMINE})
        self.assertIsNone(v["eco"])  # tout le sens economique est indetermine
        self.assertIs(Q.normaliser(REPONSES_Q1), REPONSES_Q1)  # rien a faire sans « indetermine »


class SelectionEtApplicationTests(unittest.TestCase):
    def setUp(self):
        self.base = annoter(annoter(B.migrer(data(prop(1), prop(2), prop(3)))[0], 1), 2)
        self.base = annoter(self.base, 3)
        self.base["mesures"][0]["annotation"]["confiances"]["eco_distrib"] = .3   # doute de sens
        self.base["mesures"][1]["annotation"]["confiances"]["cout"] = .2          # doute d'ampleur seulement

    def test_only_direction_doubts_and_once_per_version(self):
        self.assertEqual([m["uid"] for m in CX.a_relire(self.base)], ["m-roussel-0001"])
        m = self.base["mesures"][0]
        review = {"assessments": {k: {"value": REPONSES_Q1[k], "confidence": .9} for k in Q.QUESTIONS}, "note": "ok"}
        review["assessments"]["eco_distrib"] = {"value": Q.INDETERMINE, "confidence": .8}
        m["annotation"]["reponses"]["soc_finalite"] = "ordre_securite"  # complement : conserve
        CX.appliquer(m, review, "mod", "2026-11-07T00:00:00+00:00")
        a = m["annotation"]
        self.assertEqual(a["reponses"]["eco_distrib"], Q.INDETERMINE)
        self.assertEqual(a["reponses"]["soc_finalite"], "ordre_securite")
        self.assertEqual(a["contexte"]["version_mesure"], 1)
        self.assertEqual(m["historique"]["annotations_precedentes"][-1]["reponses"]["eco_distrib"], REPONSES_Q1["eco_distrib"])
        self.assertEqual(CX.a_relire(self.base), [])  # relue pour cette version
        vues = B.calculer(self.base, [])
        B.construire_file(self.base, vues, {})
        self.assertNotIn("confiance_basse", {f["motif"] for f in m["file"]})  # « indetermine » n'est pas un doute
        self.assertIsNotNone(vues[m["uid"]][0]["axes"]["eco"])

    def test_correction_to_indeterminate_allowed(self):
        dec = []
        B.nouvelle_decision(dec, self.base, "m-roussel-0001", "correction", "sov_niveau", Q.INDETERMINE)
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, self.base, "m-roussel-0001", "correction", "cout", Q.INDETERMINE)
        self.assertIsNone(B.calculer(self.base, dec)["m-roussel-0001"][0]["axes"]["sov"])

    def test_reader_accepts_indeterminate_only_on_direction_questions(self):
        lot = [{"id": "a"}]
        ok = {k: {"value": REPONSES_Q1[k], "confidence": .9} for k in Q.QUESTIONS}
        rep = lambda a: {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(  # noqa: E731
            {"reviews": [{"id": "a", "assessments": a, "note": ""}]})}}]}
        self.assertIn("a", CX.lire(rep({**ok, "eco_distrib": {"value": Q.INDETERMINE, "confidence": .7}}), lot))
        with self.assertRaises(ValueError):
            CX.lire(rep({**ok, "levier": {"value": Q.INDETERMINE, "confidence": .7}}), lot)


class TousTests(unittest.TestCase):
    def test_all_mode_covers_new_measures_and_reprocessing(self):
        base = annoter(B.migrer(data(prop(1), prop(2)))[0], 1)  # mesure 2 : pas encore annotee
        self.assertEqual(CX.a_relire(base), [])  # aucun doute : rien en mode par defaut
        self.assertEqual([m["uid"] for m in CX.a_relire(base, tous=True)], ["m-roussel-0001", "m-roussel-0002"])
        review = {"assessments": {k: {"value": REPONSES_Q1[k], "confidence": .9} for k in Q.QUESTIONS}, "note": ""}
        for m in base["mesures"]:
            CX.appliquer(m, review, "mod", "2026-11-07T00:00:00+00:00")
        nouvelle = base["mesures"][1]["annotation"]
        self.assertEqual((nouvelle["version"], nouvelle["contexte"]["methode"]), (Q.VERSION, CX.METHODE))
        self.assertEqual(CX.a_relire(base, tous=True), [])  # tout est lu pour la version courante
        dec = [{"uid": "m-roussel-0002", "type": "retraiter", "date": "2026-11-08T00:00:00+00:00"}]
        self.assertEqual([m["uid"] for m in CX.a_relire(base, dec)], ["m-roussel-0002"])  # retraitement demande
        base["mesures"][0]["annotation"]["contexte"]["methode"] = "contexte-v1"  # lue avec une consigne anterieure
        self.assertEqual([m["uid"] for m in CX.a_relire(base, tous=True)], ["m-roussel-0001"])
        base["mesures"][0]["annotation"]["contexte"]["methode"] = CX.METHODE
        base, _ = B.migrer(data(prop(1, title="Texte change"), prop(2)), base=base)
        self.assertIn("m-roussel-0001", [m["uid"] for m in CX.a_relire(base, tous=True)])  # nouvelle version


class PassageTests(unittest.TestCase):
    def test_passage_around_quote_masked(self):
        d = Path(tempfile.mkdtemp())
        segs = [{"id": "s0", "text": "Page precedente. " * 5}, {"id": "s1", "text": "Debut. Jean Dupont veut la citation exacte ici. Fin."},
                {"id": "s2", "text": "Page suivante."}]
        (d / "h.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
        m = {"versions": [{"sources": [{"content_hash": "h", "segment_id": "s1", "quote": "la citation exacte"}]}]}
        t = CX.passage(m, d, CX.masqueur({"Jean Dupont"}))
        self.assertIn("la citation exacte", t)
        self.assertIn("Page precedente", t)
        self.assertIn("Page suivante", t)
        self.assertNotIn("Dupont", t)
        self.assertEqual(CX.passage({"versions": [{"sources": [{"content_hash": "absent"}]}]}, d, lambda x: x), "")


class CommandeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base = annoter(annoter(B.migrer(data(prop(1), prop(2)))[0], 1), 2)
        base["mesures"][0]["annotation"]["confiances"]["eco_distrib"] = .3
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)

    def run_cli(self, *args, fake=None):
        with mock.patch.object(sys, "argv", ["x", "--racine", str(self.dir), "annoter", "--contexte", "--effort", "low", *args]), \
                mock.patch("builtins.print"), mock.patch("contexte_2027.request_json", side_effect=fake), \
                mock.patch("llm_logging_2027.LLMJournal") as journal, mock.patch("update_corpus_2027.journal_cost", return_value=0.0), \
                mock.patch("pipeline_scoring_2027.load_env_file"), mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "t"}):
            journal.return_value.path = self.dir / "j.jsonl"
            return BO.main()

    def test_plan_then_direct_reading_applied(self):
        appels = []

        def fake(req, *a, **k):
            corps = json.loads(req.data)
            contenu = corps["messages"][0]["content"]
            props = json.loads(contenu[contenu.index('{"rubric"'):])["proposals"]
            appels.append(props)
            assert "passage" in props[0]
            reviews = [{"id": p["id"], "note": "ok", "assessments": {
                k: {"value": Q.INDETERMINE if k == "eco_distrib" else REPONSES_Q1[k], "confidence": .9} for k in Q.QUESTIONS}}
                for p in props]
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": reviews})}}]}

        self.assertEqual(self.run_cli(fake=fake), 0)  # plan : aucun appel
        self.assertEqual(appels, [])
        self.assertEqual(self.run_cli("--max-cost", "1", fake=fake), 0)
        self.assertEqual(len(appels), 1)
        self.assertEqual(len(appels[0]), 1)  # seule la mesure au doute de sens est relue
        base = B.lire_json(self.dir / "donnees" / "base_2027.json")
        a = base["mesures"][0]["annotation"]
        self.assertEqual((a["reponses"]["eco_distrib"], a["contexte"]["methode"]), (Q.INDETERMINE, CX.METHODE))
        self.assertNotIn("confiance_basse", {f["motif"] for f in base["mesures"][0]["file"]})
        self.assertEqual(self.run_cli("--max-cost", "1", fake=fake), 0)  # deja relue : rien a refaire
        self.assertEqual(len(appels), 1)


if __name__ == "__main__":
    unittest.main()
