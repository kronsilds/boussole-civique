import json
import unittest

import pipeline_scoring_2027 as ps
import revision_2027 as rv
from test_pipeline_scoring_2027 import answers


def jev_row(confidence=.2, **over):
    p = ps._parse_jev_proposal_answers({"id": "a", "title": "t"}, answers(confidence, axes=True), "jev")
    p.update(over)
    return p


def content(*reviews):
    return json.dumps({"reviews": list(reviews)})


class RubricTests(unittest.TestCase):
    def test_anchors_scale_and_applicability(self):
        r = rv.rubric(["eco", "rupture", "legal_instrument"])
        self.assertEqual(list(r["eco"]["anchors"]), ["-100", "-50", "0", "50", "100"])
        self.assertEqual(list(r["rupture"]["anchors"]), ["0", "33", "67", "100"])
        self.assertIn("applies_if", r["eco"])
        self.assertIn("revision_constitutionnelle", r["legal_instrument"]["options"])

    def test_only_reviewable_low_confidence_dimensions(self):
        dims = rv.dimensions_to_review(jev_row(), .65)
        self.assertIn("eco", dims)
        self.assertNotIn("ideology", dims)
        self.assertNotIn("budget_net_bn_year", dims)
        self.assertEqual(rv.dimensions_to_review(jev_row(.9), .65), [])


class ParseTests(unittest.TestCase):
    batch = [{"id": "a", "dimensions": ["eco", "horizon"]}]

    def ok(self, **over):
        item = {"id": "a", "assessments": {"eco": {"value": -40.4, "confidence": .8},
                                           "horizon": {"value": "mandat_1_a_5_ans", "confidence": .6}}, "note": "ok"}
        item.update(over)
        return item

    def test_valid_review_is_rounded(self):
        result = rv.parse_reviews(content(self.ok()), self.batch)
        self.assertEqual(result["a"]["assessments"]["eco"]["value"], -40)

    def test_invalid_parts_are_dropped_not_the_whole_batch(self):
        partial = rv.parse_reviews(content(self.ok(assessments={"eco": {"value": 0, "confidence": .5},
                                                                 "extra": {"value": 1, "confidence": .5}})), self.batch)
        self.assertEqual(list(partial["a"]["assessments"]), ["eco"])  # omise : gardee en file ; en trop : ignoree
        dropped = {}
        two = [{"id": "a", "dimensions": ["eco", "horizon"]}, {"id": "b", "dimensions": ["eco"]}]
        result = rv.parse_reviews(content(
            self.ok(assessments={"eco": {"value": 120, "confidence": .5}, "horizon": {"value": "demain", "confidence": .5}}),
            {"id": "b", "assessments": {"eco": {"value": 10, "confidence": .5}}, "note": "ok"}), two, dropped)
        self.assertEqual(list(result), ["b"])
        self.assertEqual(dropped, {"dimensions": 2, "proposals": 1})

    def test_reviews_keyed_by_id_are_accepted(self):
        raw = json.dumps({"reviews": {"a": {k: v for k, v in self.ok().items() if k != "id"}}})
        self.assertEqual(rv.parse_reviews(raw, self.batch)["a"]["assessments"]["eco"]["value"], -40)

    def test_unusable_responses_raise(self):
        bad = [self.ok(note=""), self.ok(id="z"), self.ok(assessments={"extra": {"value": 0, "confidence": .5}}),
               self.ok(assessments={"eco": {"value": 0, "confidence": 2}, "horizon": {"value": "x", "confidence": .5}})]
        for item in bad:
            with self.assertRaises(ValueError, msg=str(item)):
                rv.parse_reviews(content(item), self.batch)
        for raw in (content(), '{"reviews": [{"id": "a"}, "b": 1]}'):
            with self.assertRaises(ValueError):
                rv.parse_reviews(raw, self.batch)


class RetryTests(unittest.TestCase):
    def test_unreadable_batch_is_retried_one_by_one(self):
        from unittest.mock import patch
        import tempfile
        from pathlib import Path
        good = lambda pid: {"choices": [{"finish_reason": "stop", "message": {"content": content(
            {"id": pid, "assessments": {"eco": {"value": 5, "confidence": .5}}, "note": "ok"})}}]}
        responses = [{"choices": [{"finish_reason": "stop", "message": {"content": "{pas du json"}}]}, good("a"), good("b")]
        stats = {"calls": 0, "cached": 0, "failed_batches": 0, "retried": 0, "unreviewed": 0, "dropped_dimensions": 0}
        with tempfile.TemporaryDirectory() as tmp,                 patch.object(rv, "request_json", side_effect=responses), patch.object(rv, "journal_cost", return_value=0.0),                 patch("sys.stderr"):
            journal = type("J", (), {"path": Path(tmp) / "j.jsonl"})()
            reviewer = rv.make_reviewer("m", "k", journal, {}, Path(tmp) / "c.json", 1.0, .01, stats)
            result = reviewer([{"id": "a", "dimensions": ["eco"]}, {"id": "b", "dimensions": ["eco"]}])
        self.assertEqual(set(result), {"a", "b"})
        self.assertEqual((stats["calls"], stats["retried"], stats["unreviewed"]), (3, 2, 0))


class ApplyTests(unittest.TestCase):
    def test_revision_replaces_value_keeps_jev_and_rederives_ideology(self):
        p = jev_row()
        self.assertEqual(p["axes"]["eco"], 0)
        review = {"assessments": {"eco": {"value": -80, "confidence": .9},
                                  "legal_instrument": {"value": "revision_constitutionnelle", "confidence": .8}},
                  "note": "Mesure de collectivisation."}
        q = rv.apply_review(p, review, "haiku")
        self.assertEqual(q["axes"]["eco"], -80)
        detail = q["score_details"]["eco"]
        self.assertEqual((detail["jev_value"], detail["method"]), (0, "revision-chat"))
        self.assertEqual(q["revision"]["disagreements"], ["eco", "legal_instrument"])
        self.assertEqual(q["ideology"], -20)  # moyenne de eco -80, soc 0, ouverture 0, accès aux droits 0
        self.assertIn(ps.TAGS[0], q["threshold_tags"])
        self.assertEqual(p["axes"]["eco"], 0)  # l'original n'est pas modifie
        remaining = {i["dimension"] for i in rv.review_issues(q, .65)}
        self.assertTrue({"eco", "legal_instrument"} <= remaining)  # divergences : relecture humaine

    def test_agreeing_revision_leaves_queue(self):
        review = {"assessments": {"eco": {"value": 10, "confidence": .4}}, "note": "Mesure mixte."}
        q = rv.apply_review(jev_row(), review, "haiku")
        self.assertNotIn("eco", {i["dimension"] for i in rv.review_issues(q, .65)})

    def test_not_applicable_revision_resolves_without_human_review(self):
        review = {"assessments": {"eco": {"value": None, "confidence": .8},
                                  "feasibility": {"value": None, "confidence": .7}}, "note": "Mesure de securite."}
        p = jev_row()
        p["feasibility"] = 60
        q = rv.apply_review(p, review, "haiku")
        self.assertIsNone(q["axes"]["eco"])
        self.assertEqual(q["score_details"]["eco"]["resolution"], "non_applicable_seconde_lecture")
        self.assertEqual(q["revision"]["disagreements"], ["feasibility"])  # faisabilite : null = vague, reste en file
        remaining = {i["dimension"] for i in rv.review_issues(q, .65)}
        self.assertNotIn("eco", remaining)

    def test_instrument_disagreement_only_across_classes_and_horizon_not_reviewed(self):
        self.assertFalse(rv.disagrees("legal_instrument", "loi_ordinaire", "loi_de_finances_ou_securite_sociale"))
        self.assertTrue(rv.disagrees("legal_instrument", "decret_ou_arrete", "loi_ordinaire"))
        self.assertTrue(rv.disagrees("legal_instrument", "non_identifiable", "revision_constitutionnelle"))
        self.assertNotIn("horizon", rv.dimensions_to_review(jev_row(), .65))

    def test_not_applicable_and_small_gap(self):
        self.assertTrue(rv.disagrees("soc", 10, None))
        self.assertFalse(rv.disagrees("soc", 10, 50))
        self.assertTrue(rv.disagrees("rupture", 10, 50))


if __name__ == "__main__":
    unittest.main()
