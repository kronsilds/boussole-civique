import json
import unittest
from pathlib import Path
from unittest import mock

import comparer_modeles_2027 as CM
import contexte_2027 as CX
import decisions_2027 as DX
import questionnaire_2027 as Q
from test_base_2027 import REPONSES_Q1

ITEM = {"id": "abc12345", "theme": "fiscalite", "title": "Taxe sur les superprofits", "description": "Taxer les superprofits.",
        "quote": "Nous taxerons les superprofits.", "passage": "Avant. Nous taxerons les superprofits. Apres."}
COMPLEMENTS = {"soc_finalite": "ordre_securite", "degre_rupture": "notable", **{k: "non_concernee" for k in Q.CLASSES_REVENU}}


def reponse(ouvertes=("has_eco",), valeurs=None, proba=.9, liste=False):
    """Reponse simulee de l'API : conditions `ouvertes` a `proba`, les autres a 0,1 ; une option par question."""
    valeurs = {**{k: v for k, v in REPONSES_Q1.items() if v is not None}, **COMPLEMENTS, **(valeurs or {})}
    answers = {c: {"type": "noul", "noul": proba if c in ouvertes else .1} for c in DX.conditions()}
    for k in Q.TOUTES:
        val = valeurs.get(k) or DX.permis(k)[0]
        answers[k] = {"type": "choice", "choice": val, "probabilities": {val: .8}, "confidence": .7}
    if liste:
        answers = [{"name": k, **v} for k, v in answers.items()]
    return {"model": "m", "answers": answers, "usage": {"input_tokens": 100, "cost": .001}}


class QuestionsTests(unittest.TestCase):
    def test_one_gate_per_axis_then_every_question_as_choice(self):
        par_nom = DX.questions()
        self.assertLessEqual(len(par_nom), 100)  # limite de l'API
        self.assertEqual([k for k, q in par_nom.items() if q["type"] == "noul"], list(DX.conditions()))
        self.assertEqual([k for k, q in par_nom.items() if q["type"] == "choice"], list(Q.TOUTES))
        self.assertIn(Q.INDETERMINE, par_nom["eco_distrib"]["criteria"])
        self.assertNotIn(Q.INDETERMINE, par_nom["levier"]["criteria"])
        self.assertNotIn(Q.INDETERMINE, par_nom["soc_finalite"]["criteria"])
        self.assertIn(CX.LECTURE_DROITS, par_nom["droits_statut"]["instructions"])
        self.assertNotIn("null", par_nom["rev_cadres"]["instructions"])  # un choix n'a pas de null

    def test_state_is_blind_and_carries_passage(self):
        e = DX.etat({**ITEM, "lexique": [{"terme": "laicite", "phrase": "x"}]})
        self.assertEqual(list(e), ["regles", "theme", "title", "description", "quote", "passage", "lexique"])  # pas d'identifiant
        self.assertEqual(e["passage"], ITEM["passage"])
        corps = DX.requetes("m", ITEM)
        self.assertTrue(all(set(c) == {"model", "state", "questions"} and len(c["questions"]) <= DX.MAX_QUESTIONS for c in corps))
        self.assertEqual({k for c in corps for k in c["questions"]}, set(DX.questions()))  # chaque question posee une fois
        self.assertEqual(sum(len(c["questions"]) for c in corps), len(DX.questions()))
        self.assertTrue(set(DX.conditions()) <= set(corps[0]["questions"]))


class LectureTests(unittest.TestCase):
    def test_closed_axis_is_null_and_open_axis_bounded_by_gate(self):
        r = DX.lire(reponse(ouvertes=("has_eco",), proba=.6))
        a = r["assessments"]
        self.assertEqual(set(a), set(Q.QUESTIONS))
        self.assertEqual((a["eco_etat"]["value"], a["eco_etat"]["confidence"]), (REPONSES_Q1["eco_etat"], .6))  # min(0,7 ; 0,6)
        self.assertEqual((a["sov_niveau"]["value"], a["sov_niveau"]["confidence"]), (None, .9))  # 1 - 0,1
        self.assertEqual(a["levier"]["confidence"], .7)
        self.assertEqual(set(r["complements"]), set(Q.CLASSES_REVENU))  # ni societe ni immigration : pas de finalite ni de degre
        self.assertEqual(r["conditions"]["has_eco"], .6)
        valeurs, _ = Q.calculer(DX.reponses(r))
        self.assertIsNotNone(valeurs["eco"])
        self.assertIsNone(valeurs["soc"])
        self.assertNotIn("soc_finalite", DX.reponses(r, complements=False))

    def test_society_axis_gets_its_complements_and_threshold_can_move(self):
        rep = reponse(ouvertes=("has_soc",), valeurs={"soc_autorite": "renforce", "soc_libertes": "restreint"}, proba=.55)
        r = DX.lire(rep)
        self.assertEqual({k: v["value"] for k, v in r["complements"].items()},
                         {"soc_finalite": "ordre_securite", "degre_rupture": "notable"})
        self.assertGreater(Q.calculer(DX.reponses(r))[0]["soc"], 0)
        self.assertIsNone(DX.lire(rep, seuil=.6)["assessments"]["soc_autorite"]["value"])  # meme reponse, seuil plus haut
        self.assertEqual(DX.lire({"answers": r["brut"]})["assessments"], r["assessments"])  # relisible depuis `brut`

    def test_list_answers_accepted_and_invalid_answers_rejected(self):
        self.assertEqual(DX.lire(reponse(liste=True))["assessments"], DX.lire(reponse())["assessments"])
        for casse in ({"levier": {"choice": "inconnu", "confidence": .9}}, {"has_eco": {"type": "noul"}},
                      {"levier": {"choice": "prelevement"}}, {"portee": None}):
            rep = reponse()
            rep["answers"].update(casse)
            with self.assertRaises(ValueError):
                DX.lire(rep)
        with self.assertRaises(ValueError):
            DX.lire({"choices": []})

    def test_choice_falls_back_on_most_probable_option(self):
        rep = reponse()
        rep["answers"]["levier"] = {"probabilities": {"prelevement": .6, "incitation": .4}}
        self.assertEqual(DX.lire(rep)["assessments"]["levier"], {"value": "prelevement", "confidence": .6, "p": .6})


class AppelsTests(unittest.TestCase):
    def lancer(self, items, plafond, appel, cout_reel=0.0):
        cache = {}
        journal = mock.Mock(path=Path("inexistant.jsonl"))
        with mock.patch("update_corpus_2027.journal_cost", side_effect=lambda _p: cout_reel * len(cache)), mock.patch("builtins.print"):
            stats = DX.lire_direct(items, "m", "cle", journal, plafond, cache.update, appel=appel)
        return stats, cache

    def test_one_call_per_measure_under_cap_with_real_cost(self):
        corps = []

        def appel(req, *a, **k):
            corps.append(json.loads(req.data))
            self.assertEqual(req.full_url, DX.URL)
            return reponse()

        items = [{**ITEM, "id": f"id{i}"} for i in range(5)]
        stats, cache = self.lancer(items, .01, appel)  # sans cout reel : 0,003 par mesure, soit 3 mesures sous 0,01
        self.assertEqual((stats["mesures"], stats["lues"], stats["appels"]), (3, 3, 3 * len(DX.lots_questions())))
        self.assertEqual(set(cache), {DX.cle("m", it) for it in items[:3]})
        self.assertNotIn("id0", json.dumps(corps[0]["state"]))
        stats, _ = self.lancer(items, .01, appel, cout_reel=.001)  # cout reel connu : les 5 passent (0,004 + 0,0015 < 0,01)
        self.assertEqual(stats["lues"], 5)
        stats, _ = self.lancer(items, .002, appel)  # plafond sous l'estimation : aucun appel
        self.assertEqual(stats["appels"], 0)

    def test_stops_after_consecutive_failures(self):
        stats, cache = self.lancer([{**ITEM, "id": f"id{i}"} for i in range(6)], 1.0, lambda *a, **k: {"answers": {}})
        self.assertEqual((stats["mesures"], stats["echecs"], cache), (DX.ECHECS_MAX, DX.ECHECS_MAX, {}))


class ComparaisonTests(unittest.TestCase):
    def test_decision_model_is_a_candidate_with_its_own_cache_key(self):
        conf = CM.config("nace-ai/drex-max:decisions")
        self.assertEqual(conf, ("nace-ai/drex-max", DX.EFFORT))
        self.assertEqual(CM.cle_lecture(conf, ITEM, 0), DX.cle("nace-ai/drex-max", ITEM))
        self.assertNotEqual(CM.cle_lecture(conf, ITEM, 1), CM.cle_lecture(conf, ITEM, 0))
        self.assertNotEqual(DX.cle("nace-ai/drex-max", ITEM), DX.cle("autre/modele", ITEM))
        ligne = CM.comparer(DX.lire(reponse()), DX.lire(reponse(valeurs={"eco_etat": "diminue"})))
        self.assertEqual(ligne["sens_differe"], ["eco_etat"])


if __name__ == "__main__":
    unittest.main()
