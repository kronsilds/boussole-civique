import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pipeline_scoring_2027 as ps
import relecture_ciblee_2027 as rc
import revision_2027 as rv
from scoring_context_2027 import review_issues
from test_revision_2027 import jev_row


def row(theme="securite", **over):
    p = jev_row(.9, theme_id=theme, id="a")
    p["axes"]["eco"] = -40
    p.update(over)
    return p


class PlanTests(unittest.TestCase):
    def test_eco_only_outside_economic_themes_cost_everywhere(self):
        self.assertEqual(rc.targeted_dimensions(row("securite")), ["eco", "cost_estimate"])
        self.assertEqual(rc.targeted_dimensions(row("fiscalite")), ["cost_estimate"])
        p = row("securite"); p["axes"]["eco"] = None
        self.assertEqual(rc.targeted_dimensions(p), ["cost_estimate"])

    def test_published_amount_passed_to_reader(self):
        item = rc.make_item(row(budget_net_bn_year=-2.5, id="corpus-0123456789abcdef"), set())
        self.assertEqual(item["id"], "89abcdef")
        self.assertEqual(item["montant_annuel_publie_md"], -2.5)
        self.assertNotIn("montant_annuel_publie_md", rc.make_item(row(budget_net_bn_year=None, id="corpus-x1"), set()))

    def test_strict_schema_lists_exact_dimensions_and_options(self):
        s = rc.response_schema(["eco", "cost_estimate"])
        a = s["properties"]["reviews"]["items"]["properties"]["assessments"]
        self.assertEqual(a["required"], ["eco", "cost_estimate"])
        self.assertIn("indeterminable", a["properties"]["cost_estimate"]["properties"]["value"]["enum"])
        self.assertEqual(a["properties"]["eco"]["properties"]["value"]["type"], ["integer", "null"])

    def test_new_eco_definition_excludes_mere_cost(self):
        text = ps.TYPESAFE_QUESTIONS["has_eco"]["instructions"]
        self.assertIn("seul coût", text)
        self.assertNotEqual(rv.rubric(["eco"])["eco"]["applies_if"], rv.rubric(["eco"], legacy=True)["eco"]["applies_if"])
        self.assertIn("cost_estimate", [q for q in ps.jev_questions()])


class ApplyTests(unittest.TestCase):
    def test_eco_becomes_not_applicable_without_human_review_and_cost_stored(self):
        review = {"assessments": {"eco": {"value": None, "confidence": .8},
                                  "cost_estimate": {"value": "cout_modere", "confidence": .6}}, "note": "Effectifs de police."}
        q = rc.apply_targeted(row(), review, "gpt")
        self.assertIsNone(q["axes"]["eco"])
        self.assertEqual(q["axes"]["cost_estimate"], "cout_modere")
        d = q["score_details"]["eco"]
        self.assertEqual((d["previous_value"], d["jev_value"], d["resolution"], d["disagreement"]),
                         (-40, -40, "non_applicable_relecture", False))
        self.assertFalse(q["score_details"]["cost_estimate"]["disagreement"])
        dims = {i["dimension"] for i in review_issues(q, .65)}
        self.assertFalse({"eco", "cost_estimate"} & dims)

    def test_large_gap_flagged_and_prior_revision_superseded(self):
        p = row(revision={"disagreements": ["eco", "soc"], "dimensions": ["eco", "soc"], "note": "x"})
        p["score_details"]["eco"] = {"method": "revision-chat", "jev_value": 10, "jev_confidence": .3, "disagreement": True}
        review = {"assessments": {"eco": {"value": 50, "confidence": .7},
                                  "cost_estimate": {"value": "indeterminable", "confidence": .5}}, "note": "Baisse d'impôt."}
        q = rc.apply_targeted(p, review, "gpt")
        self.assertEqual(q["relecture_ciblee"]["disagreements"], ["eco"])
        self.assertEqual(q["revision"]["disagreements"], ["soc"])  # l'ancienne divergence eco est remplacee
        self.assertEqual(q["score_details"]["eco"]["jev_value"], 10)  # note Jev d'origine conservee
        self.assertIn("eco", {i["dimension"] for i in review_issues(q, .65)})


class ReviewerTests(unittest.TestCase):
    def test_hook_sets_reasoning_strict_schema_and_drops_temperature(self):
        sent = {}

        def fake(request, timeout, **kw):
            sent.update(json.loads(request.data))
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": [
                {"id": "a", "assessments": {"cost_estimate": {"value": "cout_faible", "confidence": .5}}, "note": "ok"}]})}}]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rv, "request_json", fake), \
                mock.patch.object(rv, "journal_cost", return_value=0.0):
            stats = {"calls": 0, "cached": 0, "failed_batches": 0, "retried": 0, "unreviewed": 0, "dropped_dimensions": 0}
            journal = type("J", (), {"path": Path(tmp) / "j.jsonl"})()
            reviewer = rv.make_reviewer("m", "k", journal, {}, Path(tmp) / "c.json", 1.0, .01, stats, legacy=False,
                                        instructions=rc.INSTRUCTIONS, payload_hook=rc.payload_hook("medium"))
            result = reviewer([{"id": "a", "dimensions": ["cost_estimate"]}])
        self.assertEqual(result["a"]["assessments"]["cost_estimate"]["value"], "cout_faible")
        self.assertNotIn("temperature", sent)
        self.assertEqual(sent["reasoning"], {"effort": "medium"})
        self.assertEqual(sent["response_format"]["type"], "json_schema")
        self.assertIn("cost_estimate", json.loads(sent["messages"][0]["content"].split("\n", 1)[1].split("\n")[-1])["rubric"])

    def test_batch_refused_over_cap_then_submitted_and_collected_into_cache(self):
        batch = [{"id": "a", "dimensions": ["cost_estimate"]}, {"id": "b", "dimensions": ["cost_estimate"]}]
        sent = {}

        def fake(request, timeout, **kw):
            if request.data:
                sent.update(json.loads(request.data))
                return {"id": "batch_1", "status": "validating"}
            content = json.dumps({"reviews": [{"id": i, "assessments": {"cost_estimate": {"value": "cout_faible", "confidence": .5}},
                                               "note": "ok"} for i in ("a", "b")]})
            return {"status": "completed", "request_counts": {"total": 1, "completed": 1, "failed": 0},
                    "usage": {"cost": 0.01, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "results": [{"custom_id": "lot-0000", "response": {"status_code": 200, "body": {
                        "choices": [{"finish_reason": "stop", "message": {"content": content}}]}}, "error": None}]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rc, "request_json", fake):
            state, cache_path = Path(tmp) / "s.json", Path(tmp) / "c.json"
            with self.assertRaises(ValueError):
                rc.batch_submit(state, "m", "medium", "k", [batch], 0.001, 0.01, None)
            self.assertFalse(state.exists())
            rc.batch_submit(state, "m", "medium", "k", [batch], 1.0, 0.01, None)
            self.assertEqual(sent["requests"][0]["custom_id"], "lot-0000")
            self.assertEqual(sent["requests"][0]["body"]["reasoning"], {"effort": "medium"})
            with self.assertRaises(ValueError):  # un batch non recupere bloque un nouvel envoi
                rc.batch_submit(state, "m", "medium", "k", [batch], 1.0, 0.01, None)
            cache: dict = {}
            report = rc.batch_collect(state, "k", cache, cache_path, None)
            self.assertEqual((report["reviews"], report["lots_failed"], report["cost"]), (2, 0, 0.01))
            self.assertIn(rv.cache_key("m", batch[0]), cache)
            self.assertTrue(json.loads(state.read_text(encoding="utf-8"))["collected_at"])

    def test_legacy_cache_reused_only_when_allowed(self):
        item = {"id": "a", "dimensions": ["eco"]}
        cache = {rv.cache_key("m", item, legacy=True): {"assessments": {}, "note": "ancienne"}}
        self.assertEqual(rv.cached_review(cache, "m", item, True), (cache[rv.cache_key("m", item, legacy=True)], True))
        self.assertEqual(rv.cached_review(cache, "m", item, False), (None, False))


if __name__ == "__main__":
    unittest.main()
