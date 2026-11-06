import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import descripteurs_corpus_2027 as dc
import pilote_descripteurs_2027 as pd
from test_revision_2027 import jev_row

ANSWER = {"levier": "controle_prix_ou_revenus", "public_vise": "salaries", "portee": "large",
          "eco_etat": "augmente", "eco_distrib": "vers_modestes_ou_salaries"}


def review(**over):
    return {"assessments": {q: {"value": v, "confidence": .8} for q, v in {**ANSWER, **over}.items()}, "note": "ok"}


def row(i, eco=-50):
    p = jev_row(.9, id=f"corpus-{i:024d}", theme_id="fiscalite", candidate_id="roussel", title=f"Mesure {i}",
                description="Hausser le SMIC.", source_evidence=[{"quote": "SMIC"}])
    p["axes"].update(eco=eco, rupture=75, cost_estimate="sans_impact_notable")
    return p


class ApplyTests(unittest.TestCase):
    def test_calculated_eco_replaces_old_and_keeps_audit_trail(self):
        q = dc.apply_descriptors(row(1, eco=-50), review(), "m")
        self.assertEqual(q["axes"]["eco"], -74)  # cas type SMIC
        e = q["score_details"]["eco"]
        self.assertEqual((e["method"], e["previous_value"], e["status"]), (dc.METHOD, -50, "scored"))
        self.assertIn("vers les modestes", e["rationale"])
        self.assertEqual(q["descripteurs"], {k: ANSWER[k] for k in pd.COMMON})
        self.assertIsNotNone(q["ideology"])  # idéologie composite recalculée

    def test_not_applicable_is_resolved_without_human_review(self):
        p = row(2, eco=-40)
        p["revision"] = {"disagreements": ["eco"], "human_review_required": True}
        q = dc.apply_descriptors(p, review(eco_etat=None, eco_distrib=None), "m")
        self.assertIsNone(q["axes"]["eco"])
        self.assertEqual(q["score_details"]["eco"]["resolution"], "non_applicable_descripteurs")
        self.assertFalse(q["revision"]["human_review_required"])

    def test_original_proposal_untouched(self):
        p = row(3)
        dc.apply_descriptors(p, review(), "m")
        self.assertEqual(p["axes"]["eco"], -50)
        self.assertNotIn("descripteurs", p)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "in.json").write_text(json.dumps({"candidates": [], "proposals": [row(i) for i in range(3)]}),
                                          encoding="utf-8")

    def argv(self, *extra):
        return ["x", "--input", str(self.dir / "in.json"), "--cache-file", str(self.dir / "cache.json"),
                "--batch-state", str(self.dir / "state.json"), *extra]

    def run_main(self, *extra, fake=None):
        with mock.patch.object(sys, "argv", self.argv(*extra)), \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), mock.patch.object(dc.ps, "load_env_file"), \
                mock.patch.object(dc.rc, "request_json", side_effect=fake) as call, \
                mock.patch.object(dc, "LLMJournal") as journal:
            journal.return_value.path = self.dir / "j.jsonl"
            return dc.main(), call

    def test_plan_only_and_no_write_without_cache(self):
        code, call = self.run_main()
        self.assertEqual(code, 0)
        call.assert_not_called()
        code, _ = self.run_main("--out", str(self.dir / "out.json"))
        self.assertEqual(code, 2)  # descriptions manquantes
        self.assertFalse((self.dir / "out.json").exists())

    def test_submit_requires_cap_then_collect_then_write(self):
        code, call = self.run_main("--batch-submit")
        self.assertEqual(code, 2)
        call.assert_not_called()
        sent = {}

        def fake(request, timeout, **kw):
            if request.data:
                sent.update(json.loads(request.data))
                return {"id": "batch_1", "status": "validating"}
            results = []
            for r in sent["requests"]:
                items = json.loads(r["body"]["messages"][0]["content"].split("\n")[-1])["proposals"]
                content = json.dumps({"reviews": [{"id": i["id"], **review()} for i in items]})
                results.append({"custom_id": r["custom_id"], "error": None, "response": {"status_code": 200, "body": {
                    "choices": [{"finish_reason": "stop", "message": {"content": content}}]}}})
            return {"status": "completed", "request_counts": {}, "usage": {"cost": 0.002}, "results": results}
        code, _ = self.run_main("--batch-submit", "--max-cost", "1", fake=fake)
        self.assertEqual(code, 0)
        body = sent["requests"][0]["body"]
        self.assertTrue(body["messages"][0]["content"].startswith(pd.INSTRUCTIONS))  # consigne corrigee
        self.assertEqual(body["response_format"]["json_schema"]["name"], "descripteurs")
        code, _ = self.run_main("--batch-collect", fake=fake)
        self.assertEqual(code, 0)
        code, call = self.run_main("--out", str(self.dir / "out.json"))
        self.assertEqual(code, 0)
        call.assert_not_called()
        out = json.loads((self.dir / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(out["meta"]["descripteurs"]["decrites"], 3)
        self.assertEqual({p["axes"]["eco"] for p in out["proposals"]}, {-74})

    def test_pilot_corrected_readings_are_reused(self):
        data = json.loads((self.dir / "in.json").read_text(encoding="utf-8"))
        item = pd.make_item(data["proposals"][0], set())
        cache = {pd.cache_key("openai/gpt-6.1-terra", item, 1, pd.INSTRUCTIONS): review()}
        (self.dir / "cache.json").write_text(json.dumps(cache), encoding="utf-8")
        with mock.patch.object(sys, "argv", self.argv()), mock.patch("builtins.print") as out:
            dc.main()
        self.assertIn("1 en cache", out.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
