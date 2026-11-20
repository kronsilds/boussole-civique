import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import registre_2027 as R
from pipeline_scoring_2027 import adapt_v2_bundle


def amont_exemple():
    return {
        "version": 2, "generated_at": "2026-11-18T00:00:00Z",
        "meta": {"election": {"first_round": "2027-04-18"}, "inclusion_rule": "regle", "report_url": "x"},
        "themes": [{"id": "economie", "label": "Economie", "short": "Eco", "icon": "Wallet", "description": "d"},
                   {"id": "sante", "label": "Sante", "short": "Sante", "icon": "Heart", "description": "d"}],
        "candidates": [
            {"id": "alpha", "first_name": "Anne", "last_name": "Alpha", "party": "Parti A", "party_short": "PA",
             "color": "#111111", "status": "declare", "status_source_url": "https://a.example/declaration",
             "program": {"main_url": "https://a.example/programme.pdf", "title": "Programme A", "format": "pdf",
                         "published_date": "2026-06-01",
                         "thematic_links": [{"theme": "sante", "title": "Sante", "url": "https://a.example/sante"}]}},
            {"id": "beta", "first_name": "Bruno", "last_name": "Beta", "party": "Parti B", "status": "probable",
             "program": {"main_url": "https://b.example/", "thematic_links": []}},
        ],
        "measures": {"alpha": [{"id": "x1", "theme": "sante", "title": "Mesure amont"}]},
    }


class RegistreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        racine = Path(self.tmp.name)
        self.c = {"candidats": racine / "donnees" / "candidats_2027.json", "themes": racine / "donnees" / "themes_2027.json",
                  "veille_amont": racine / "donnees" / "veille_amont_2027.json", "amont": racine / "upstream_repo"}
        self.ecrire_amont(amont_exemple())

    def tearDown(self):
        self.tmp.cleanup()

    def ecrire_amont(self, amont):
        chemin = R.fichier_amont(self.c["amont"])
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(amont, ensure_ascii=False), encoding="utf-8")

    def test_import_puis_lecture_identique_a_l_amont(self):
        r = R.importer(self.c)
        self.assertEqual((r["candidats"], r["themes"], r["liens"]), (2, 2, 1))
        data = R.charger(self.c)
        ancien = adapt_v2_bundle(amont_exemple())
        self.assertEqual(data["candidates"], ancien["candidates"])  # meme forme pour l'inventaire et l'export
        self.assertEqual(data["themes"], ancien["themes"])
        self.assertEqual(data["proposals"], [])  # les mesures de l'amont ne sont pas reprises
        self.assertNotIn("repository", data["meta"])
        self.assertEqual(data["meta"]["inclusion_rule"], "regle")
        self.assertNotIn("report_url", data["meta"])

    def test_import_refuse_d_ecraser(self):
        R.importer(self.c)
        with self.assertRaises(ValueError):
            R.importer(self.c)
        R.importer(self.c, remplacer=True)

    def test_registre_absent(self):
        with self.assertRaisesRegex(ValueError, "registre importer"):
            R.charger(self.c)

    def test_charger_ne_modifie_pas_le_registre(self):
        R.importer(self.c)
        data = R.charger(self.c)
        data["candidates"][0]["program"]["thematic_links"].append({"url": "https://ajout.example"})
        self.assertEqual(len(R.charger(self.c)["candidates"][0]["program"]["thematic_links"]), 1)

    def test_amont_change_seulement_signale(self):
        R.importer(self.c)
        amont = amont_exemple()
        a = amont["candidates"][0]
        a["program"]["thematic_links"] = [{"theme": "economie", "title": "Eco", "url": "https://a.example/eco#p2"}]
        a["program"]["main_url"] = "https://a.example/programme-v2.pdf"
        amont["candidates"][1]["status"] = "declare"
        amont["candidates"].append({"id": "gamma", "first_name": "G", "last_name": "Gamma", "status": "declare",
                                    "program": {"thematic_links": [{"url": "https://g.example"}]}})
        amont["themes"][1]["label"] = "Sante publique"
        self.ecrire_amont(amont)
        veille = R.veiller_amont(self.c, pull=False)
        types = sorted(e["type"] for e in veille["ecarts"])
        self.assertEqual(types, ["candidat_nouveau", "lien_nouveau", "lien_retire", "programme", "statut", "themes"])
        self.assertTrue(self.c["veille_amont"].exists())
        self.assertEqual(len(R.charger(self.c)["candidates"]), 2)  # rien n'est applique
        theme = next(e for e in veille["ecarts"] if e["type"] == "themes")
        self.assertEqual(theme["renommes"], ["sante"])
        # identifiants stables d'un run a l'autre
        self.assertEqual([e["id"] for e in R.veiller_amont(self.c, pull=False)["ecarts"]], [e["id"] for e in veille["ecarts"]])

    def test_reprendre_et_ecarter(self):
        R.importer(self.c)
        amont = amont_exemple()
        amont["candidates"][0]["program"]["thematic_links"].append({"theme": "economie", "url": "https://a.example/eco"})
        amont["candidates"][1]["status"] = "declare"
        amont["candidates"][1]["status_source_url"] = "https://b.example/declaration"
        amont["candidates"].append({"id": "gamma", "first_name": "G", "status": "declare", "program": {}})
        self.ecrire_amont(amont)
        ecarts = {e["type"]: e for e in R.veiller_amont(self.c, pull=False)["ecarts"]}
        faits = R.reprendre(self.c, [ecarts["statut"]["id"]], tous_liens=True)
        self.assertEqual(sorted(e["type"] for e in faits), ["lien_nouveau", "statut"])
        registre, _ = R.lire_registre(self.c)
        beta = next(x for x in registre["candidates"] if x["id"] == "beta")
        self.assertEqual((beta["status"], beta["status_source_url"]), ("declare", "https://b.example/declaration"))
        self.assertEqual(len(R.liens_de(registre["candidates"][0])), 2)
        self.assertEqual([j["action"] for j in registre["journal"]], ["importer", "reprendre", "reprendre"])
        self.assertEqual(R.ecarter(self.c, [ecarts["candidat_nouveau"]["id"]], "hors regle d'inclusion"), 1)
        restants = R.veiller_amont(self.c, pull=False)["ecarts"]
        self.assertEqual([(e["type"], e["ecarte"]) for e in restants], [("candidat_nouveau", True)])
        self.assertIn("aucun ecart", R.resume_ecarts(restants))
        with self.assertRaisesRegex(ValueError, "inconnu"):
            R.reprendre(self.c, [ecarts["statut"]["id"]])  # deja repris

    def test_themes_et_candidat_absent_non_applicables(self):
        R.importer(self.c)
        amont = amont_exemple()
        amont["themes"].pop()
        amont["candidates"].pop()
        self.ecrire_amont(amont)
        ecarts = R.veiller_amont(self.c, pull=False)["ecarts"]
        for e in ecarts:
            with self.assertRaisesRegex(ValueError, "non applicable"):
                R.reprendre(self.c, [e["id"]])

    def test_amont_absent_ou_pull_en_echec_n_arrete_rien(self):
        R.importer(self.c)
        with mock.patch("update_corpus_2027.git_pull", side_effect=RuntimeError("reseau")):
            veille = R.veiller_amont(self.c, pull=True)
        self.assertIn("echec", veille["pull"])
        self.assertEqual(veille["ecarts"], [])
        R.fichier_amont(self.c["amont"]).unlink()
        self.assertIn("absent", R.veiller_amont(self.c, pull=True)["pull"])
        self.assertEqual(len(R.charger(self.c)["candidates"]), 2)

    def test_chaine_lit_le_registre(self):
        import update_corpus_2027 as up
        R.importer(self.c)
        ns = argparse.Namespace(candidats=self.c["candidats"], themes=self.c["themes"], repo_dir=self.c["amont"],
                                veille_amont=self.c["veille_amont"], no_pull=True)
        with contextlib.redirect_stdout(io.StringIO()) as sortie:
            data = up.charger_donnees(ns)
        self.assertEqual([x["id"] for x in data["candidates"]], ["alpha", "beta"])
        self.assertIn("registre local : 2 candidats", sortie.getvalue())
        self.assertIn("aucun ecart", sortie.getvalue())

    def test_commande(self):
        R.importer(self.c)
        amont = amont_exemple()
        amont["candidates"][1]["status"] = "declare"
        self.ecrire_amont(amont)
        with contextlib.redirect_stdout(io.StringIO()) as sortie:
            R.executer(self.c, argparse.Namespace(action="plan", pull=False, tout=False))
        self.assertIn("statut", sortie.getvalue())
        self.assertIn("probable -> declare", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
