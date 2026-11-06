import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import annotation_2027 as A
import base_2027 as B
import boussole_2027 as BO
import questionnaire_2027 as Q
from test_base_2027 import data, prop

NUL = {k: None for k in Q.CONDITIONNELLES if k in Q.QUESTIONS}  # complements absents = pas encore poses
BASE = {**NUL, "public_vise": "toute_la_population", "precision": "precis", "instrument": "loi_ordinaire",
        "cout": "sans_impact_notable", "faisabilite": "elevee"}


def r(**k):
    return {**BASE, **k}


# (axe, libelle, valeur attendue, reponses)
CAS = [
    ("soc", "Perpétuité réelle pour terrorisme", 75, r(levier="sanction_ou_controle", portee="ciblee", changement="reforme_significative", soc_autorite="renforce", soc_libertes="restreint")),
    ("soc", "Recruter 10 000 policiers", 30, r(levier="depense_ou_service", portee="generale", changement="extension_moderee", cout="cout_modere", soc_autorite="renforce", soc_libertes="inchange")),
    ("soc", "Légaliser le cannabis", -60, r(levier="suppression_ou_allegement", portee="generale", changement="refonte_structurelle", soc_autorite="allege", soc_libertes="etend")),
    ("soc", "Aide active à mourir", -50, r(levier="obligation_ou_interdiction", portee="ciblee", changement="refonte_structurelle", soc_autorite="inchange", soc_libertes="etend")),
    ("ouverture", "Fin du droit du sol", 75, r(levier="organisation_institutionnelle", portee="large", changement="refonte_structurelle", instrument="revision_constitutionnelle", ouv_sens="fermeture")),
    ("ouverture", "Régularisation des travailleurs sans papiers", -50, r(levier="organisation_institutionnelle", portee="ciblee", changement="reforme_significative", ouv_sens="accueil")),
    ("sov", "Sortie de l'Union européenne", 100, r(levier="organisation_institutionnelle", portee="generale", changement="refonte_structurelle", sov_niveau="vers_national")),
    ("sov", "Défense européenne commune", -60, r(levier="organisation_institutionnelle", portee="generale", changement="reforme_significative", sov_niveau="vers_europe_international")),
    ("ecolo", "Interdire les voitures thermiques neuves", 80, r(levier="obligation_ou_interdiction", portee="generale", changement="refonte_structurelle", env_sens="protege")),
    ("ecolo", "Supprimer les ZFE", -50, r(levier="suppression_ou_allegement", portee="large", changement="reforme_significative", env_sens="allege")),
    ("ecolo", "Prime à la rénovation thermique", 35, r(levier="incitation", portee="large", changement="extension_moderee", cout="cout_important", env_sens="protege")),
    ("eco", "SMIC à 2 200 €", -75, r(levier="controle_prix_ou_revenus", portee="large", changement="refonte_structurelle", eco_etat="augmente", eco_distrib="vers_modestes_ou_salaries")),
]


class FormulaTests(unittest.TestCase):
    def test_reference_cases_within_one_anchor(self):
        for axe, libelle, attendu, rep in CAS:
            with self.subTest(libelle):
                valeurs, expl = Q.calculer(rep)
                self.assertLessEqual(abs(valeurs[axe] - attendu), 25, f"{libelle} : {valeurs[axe]}")
                self.assertTrue(expl[axe])

    def test_not_applicable_axes_stay_null_and_scalar_mappings(self):
        v, _ = Q.calculer(r(levier="declaration_ou_symbole", portee="generale", changement="statu_quo_ou_ajustement",
                            faisabilite="non_evaluable", droits_statut="reserve_nationaux", revenus_sens="hausse_forte"))
        self.assertEqual([v[k] for k in ("eco", "soc", "sov", "ouverture", "ecolo")], [None] * 5)
        self.assertEqual((v["feasibility"], v["rights_status"], v["income_direction"], v["rupture"]), (None, 0, 100, 0))

    def test_declared_orientation_weighs_by_ambition(self):
        fort = Q.calculer(r(levier="declaration_ou_symbole", portee="generale", changement="refonte_structurelle", sov_niveau="vers_national"))[0]
        faible = Q.calculer(r(levier="declaration_ou_symbole", portee="generale", changement="statu_quo_ou_ajustement", sov_niveau="vers_national"))[0]
        self.assertGreater(fort["sov"], 2 * faible["sov"])

    def test_tags(self):
        t = Q.etiquettes(r(levier="declaration_ou_symbole", portee="individuelle", instrument="revision_constitutionnelle", cout="cout_massif"))
        self.assertEqual(len(t), 4)
        self.assertEqual(Q.etiquettes(r(levier="prelevement", portee="large", precision="chiffre")), [])

    def test_every_option_is_mapped(self):
        for axe, table in Q.FORCES.items():
            self.assertEqual(set(table), set(Q.QUESTIONS["levier"]["criteria"]), axe)
        for q, table in Q.SENS.items():
            self.assertEqual(set(table), set(Q.QUESTIONS[q]["criteria"]), q)
        self.assertEqual(set(Q.CHANGEMENT), set(Q.QUESTIONS["changement"]["criteria"]))
        self.assertEqual(set(Q.FAISABILITE), set(Q.QUESTIONS["faisabilite"]["criteria"]))
        self.assertEqual(set(Q.DROITS), set(Q.QUESTIONS["droits_statut"]["criteria"]))
        self.assertEqual(set(Q.REVENUS), set(Q.QUESTIONS["revenus_sens"]["criteria"]))
        self.assertTrue(Q.QUESTIONS["instrument"]["criteria"] and Q.QUESTIONS["cout"]["criteria"])


def reponse_q1(lot, **over):
    rep = r(**{"levier": "controle_prix_ou_revenus", "portee": "large", "changement": "reforme_significative",
               "eco_etat": "augmente", "eco_distrib": "vers_modestes_ou_salaries", "revenus_sens": "hausse_forte", **over})
    reviews = [{"id": x["id"], "assessments": {k: {"value": v, "confidence": .8} for k, v in rep.items()}, "note": "ok"} for x in lot]
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": reviews})}}]}


def corps(req):
    return json.loads(json.loads(req.data)["messages"][0]["content"].split("\n")[-1])


class AnnotationTests(unittest.TestCase):
    def test_schema_rubric_and_parsing(self):
        props = A.schema()["properties"]["reviews"]["items"]["properties"]["assessments"]["properties"]
        self.assertIn(None, props["soc_autorite"]["properties"]["value"]["enum"])
        self.assertNotIn(None, props["levier"]["properties"]["value"]["enum"])
        self.assertIn("applies_if", A.rubrique()["ouv_sens"])
        lot = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(set(A.lire(reponse_q1(lot), lot)), {"a", "b"})
        with self.assertRaises(ValueError):
            A.lire(reponse_q1(lot, levier=None), lot)  # question commune sans reponse

    def test_blind_item_and_selection(self):
        base, _ = B.migrer(data(prop(1), prop(2)))
        m1 = base["mesures"][0]
        it = A.item(m1, {"Roussel"})
        self.assertNotIn("roussel", json.dumps(it).casefold())
        self.assertEqual(len(A.a_annoter(base, [])), 2)
        A.appliquer(m1, A.lire(reponse_q1([{"id": "x"}]), [{"id": "x"}])["x"], "m", "2026-11-10T00:00:00+00:00")
        self.assertEqual([m["uid"] for m in A.a_annoter(base, [])], [base["mesures"][1]["uid"]])
        dec = [{"uid": m1["uid"], "type": "retraiter", "version": 1, "date": "2026-11-11T00:00:00+00:00"}]
        self.assertEqual(len(A.a_annoter(base, dec)), 2)  # retraitement posterieur a l'annotation
        self.assertNotEqual(A.cle("m", A.item(m1, set())), A.cle("m", A.item(m1, set(), A.reprises(m1, dec))))
        dec[0]["date"] = "2026-11-09T00:00:00+00:00"
        self.assertEqual(len(A.a_annoter(base, dec)), 1)  # demande deja traitee

    def test_q1_view_and_correction(self):
        base, _ = B.migrer(data(prop(1)))
        m = base["mesures"][0]
        A.appliquer(m, A.lire(reponse_q1([{"id": "x"}]), [{"id": "x"}])["x"], "m", B.maintenant())
        p, _ = B.vue(m, [])
        self.assertEqual(p["axes"]["horizon"], None)
        self.assertIsNone(p["rights_income"])
        self.assertEqual(p["income_direction"] if "income_direction" in p else p["axes"]["income_direction"], 100)
        self.assertLess(p["axes"]["eco"], -50)
        self.assertEqual(p["score_details"]["eco"]["method"], "questionnaire-q1")
        self.assertIn("vers les modestes", p["score_details"]["eco"]["rationale"])
        dec = []
        B.nouvelle_decision(dec, base, m["uid"], "correction", "soc_autorite", "renforce")  # question q1
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, base, m["uid"], "correction", "levier", None)  # commune : null interdit
        B.nouvelle_decision(dec, base, m["uid"], "correction", "soc_libertes", "restreint")
        p, _ = B.vue(m, B.decisions_par_mesure(dec)[m["uid"]])
        self.assertGreater(p["axes"]["soc"], 0)
        self.assertEqual(p["score_details"]["soc"]["corrigee"], ["soc_autorite", "soc_libertes"])


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        B.ecrire_json(self.dir / "base_2027.json", B.migrer(data(prop(1), prop(2), prop(3, cand="le-pen")))[0])

    def run_cli(self, *args, fake=None):
        with mock.patch.object(sys, "argv", ["x", "--racine", str(self.dir), *args]), mock.patch("builtins.print"), \
                mock.patch("annotation_2027.request_json", side_effect=fake), mock.patch("scoring_context_2027.request_json", side_effect=fake), \
                mock.patch("relecture_ciblee_2027.request_json", side_effect=fake), \
                mock.patch("llm_logging_2027.LLMJournal") as journal, mock.patch("update_corpus_2027.journal_cost", return_value=0.0), \
                mock.patch("pipeline_scoring_2027.load_env_file"), mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "t"}):
            journal.return_value.path = self.dir / "j.jsonl"
            return BO.main()

    def test_plan_then_direct_annotation(self):
        appels = []

        def fake(req, timeout, **kw):
            appels.append(1)
            return reponse_q1(corps(req)["proposals"])
        self.assertEqual(self.run_cli("annoter", fake=fake), 0)
        self.assertEqual(appels, [])
        self.assertEqual(self.run_cli("annoter", "--uid", "m-roussel-0001", "--max-cost", "1", fake=fake), 0)
        base = B.lire_json(self.dir / "base_2027.json")
        annotees = [m["uid"] for m in base["mesures"] if (m.get("annotation") or {}).get("version") == "q1"]
        self.assertEqual((appels, annotees), ([1], ["m-roussel-0001"]))
        export = B.lire_json(self.dir / "donnees_interface_2027.json")
        row = [x for x in export["proposals"] if x["id"] == "m-roussel-0001"][0]
        self.assertIn("eco", row["expl"])
        self.assertEqual(self.run_cli("annoter", "--max-cost", "1", fake=fake), 0)  # les deux autres
        self.assertEqual(len(appels), 2)

    def test_batch_submit_and_collect(self):
        sent = {}

        def fake(req, timeout, **kw):
            if req.data:
                sent.update(json.loads(req.data))
                return {"id": "batch_q1", "status": "validating"}
            results = [{"custom_id": x["custom_id"], "error": None, "response": {"status_code": 200, "body": reponse_q1(
                json.loads(x["body"]["messages"][0]["content"].split("\n")[-1])["proposals"])}} for x in sent["requests"]]
            return {"status": "completed", "request_counts": {}, "usage": {"cost": .01}, "results": results}
        self.assertEqual(self.run_cli("annoter", "--batch-submit", fake=fake), 2)  # plafond requis
        self.assertEqual(self.run_cli("annoter", "--batch-submit", "--max-cost", "1", fake=fake), 0)
        self.assertEqual(sent["requests"][0]["body"]["response_format"]["json_schema"]["name"], "questionnaire")
        self.assertEqual(self.run_cli("annoter", "--batch-collect", fake=fake), 0)
        base = B.lire_json(self.dir / "base_2027.json")
        self.assertTrue(all((m.get("annotation") or {}).get("version") == "q1" for m in base["mesures"]))


if __name__ == "__main__":
    unittest.main()


class FinaliteTests(unittest.TestCase):
    def base_soc(self, **k):
        return r(**{"levier": "sanction_ou_controle", "portee": "ciblee", "changement": "reforme_significative",
                    "soc_autorite": "renforce", "soc_libertes": "restreint", **k})

    def test_finality_changes_side_or_applicability(self):
        self.assertGreater(Q.calculer(self.base_soc(soc_finalite="ordre_securite"))[0]["soc"], 50)
        self.assertLess(Q.calculer(self.base_soc(soc_finalite="droits_egalite"))[0]["soc"], -50)  # lutte contre les discriminations
        self.assertIsNone(Q.calculer(self.base_soc(soc_finalite="probite_pouvoirs"))[0]["soc"])     # probite : hors axe
        self.assertEqual(Q.calculer(self.base_soc())[0]["soc"], Q.calculer(self.base_soc(soc_finalite="autre"))[0]["soc"])
        self.assertIsNone(Q.calculer(self.base_soc(soc_finalite=None))[0]["soc"])  # lecture ciblee : axe non applicable
        self.assertIn("au nom de l'égalité", Q.calculer(self.base_soc(soc_finalite="droits_egalite"))[1]["soc"])

    def test_main_questionnaire_cache_key_unchanged(self):
        self.assertNotIn("soc_finalite", A.rubrique())          # cle des lectures deja payees preservee
        self.assertIn("soc_finalite", Q.TOUTES)
        self.assertIn("soc_finalite", Q.CONDITIONNELLES)


def reponse_complement(lot, valeur="probite_pouvoirs"):
    reviews = [{"id": x["id"], "assessments": {"soc_finalite": {"value": valeur, "confidence": .9}}, "note": "ok"} for x in lot]
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": reviews})}}]}


class ComplementTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base, _ = B.migrer(data(prop(1), prop(2), prop(3, cand="le-pen")))
        rep = A.lire(reponse_q1([{"id": "x"}], soc_autorite="renforce", soc_libertes="restreint"), [{"id": "x"}])["x"]
        sans_soc = A.lire(reponse_q1([{"id": "x"}]), [{"id": "x"}])["x"]
        for m, rv in zip(base["mesures"], (rep, rep, sans_soc)):
            A.appliquer(m, rv, "m", B.maintenant())
        B.ecrire_json(self.dir / "base_2027.json", base)

    def run_cli(self, *args, fake=None):
        return CommandTests.run_cli(self, *args, fake=fake)

    def test_selection_plan_direct_and_application(self):
        base = B.lire_json(self.dir / "base_2027.json")
        self.assertEqual(len(A.a_completer(base, "soc_finalite")), 2)  # la mesure sans axe societe n'est pas concernee
        appels = []

        def fake(req, timeout, **kw):
            appels.append(1)
            corps_ = json.loads(json.loads(req.data)["messages"][0]["content"].split("\n")[-1])
            self.assertEqual(list(corps_["rubric"]), ["soc_finalite"])
            return reponse_complement(corps_["proposals"])
        self.assertEqual(self.run_cli("annoter", "--complement", "soc_finalite", "--effort", "low", fake=fake), 0)
        self.assertEqual(appels, [])  # plan seul
        self.assertEqual(self.run_cli("annoter", "--complement", "soc_finalite", "--effort", "low", "--max-cost", "1", fake=fake), 0)
        base = B.lire_json(self.dir / "base_2027.json")
        touchees = [m for m in base["mesures"] if "soc_finalite" in m["annotation"]["reponses"]]
        self.assertEqual((len(appels), len(touchees)), (1, 2))
        self.assertTrue(all(m["calculs"]["axes"]["soc"] is None for m in touchees))  # probite : hors axe
        self.assertEqual(A.a_completer(base, "soc_finalite"), [])
        # La reponse est corrigeable comme les autres.
        dec = []
        B.nouvelle_decision(dec, base, touchees[0]["uid"], "correction", "soc_finalite", "ordre_securite")
        p, _ = B.vue(touchees[0], dec)
        self.assertGreater(p["axes"]["soc"], 0)


class DegreTests(unittest.TestCase):
    def test_rupture_reaches_extremes_and_grades(self):
        fermeture = r(levier="suppression_ou_allegement", portee="ciblee", changement="refonte_structurelle", ouv_sens="fermeture")
        self.assertEqual(Q.calculer({**fermeture, "degre_rupture": "rupture"})[0]["ouverture"], 100)
        valeurs = [Q.calculer({**fermeture, "degre_rupture": d})[0]["ouverture"] for d in ("ajustement", "notable", "rupture")]
        self.assertEqual(valeurs, sorted(valeurs))
        self.assertLess(Q.calculer(fermeture)[0]["ouverture"], 70)  # sans complement : comme avant
        peine = r(levier="declaration_ou_symbole", portee="ciblee", changement="refonte_structurelle", soc_autorite="renforce",
                  soc_libertes="restreint", soc_finalite="ordre_securite", degre_rupture="rupture")
        self.assertEqual(Q.calculer(peine)[0]["soc"], 100)
        self.assertIn("rupture du cadre", Q.calculer(peine)[1]["soc"])

    def test_degree_does_not_touch_other_axes(self):
        rep = r(levier="prelevement", portee="large", changement="reforme_significative", eco_etat="augmente",
                eco_distrib="vers_modestes_ou_salaries")
        self.assertEqual(Q.calculer(rep)[0]["eco"], Q.calculer({**rep, "degre_rupture": "rupture"})[0]["eco"])

    def test_selection_condition(self):
        cond = A.CONDITIONS_COMPLEMENT["degre_rupture"]
        self.assertTrue(cond({"ouv_sens": "fermeture"}))
        self.assertTrue(cond({"soc_autorite": "renforce"}))  # finalite pas encore posee
        self.assertTrue(cond({"soc_autorite": "renforce", "soc_finalite": "droits_egalite"}))
        self.assertFalse(cond({"soc_autorite": "renforce", "soc_finalite": "probite_pouvoirs"}))
        self.assertFalse(cond({"soc_autorite": "renforce", "soc_finalite": None}))
        self.assertNotIn("degre_rupture", A.rubrique())  # cle des lectures payees preservee
