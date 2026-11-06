import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import renotation_eco_2027 as re9


def shown(i, c="roussel", t="fiscalite", eco=-50):
    return {"id": f"corpus-{i:024d}", "c": c, "t": t, "title": f"Mesure {i}", "v": {"eco": eco}, "meth": {"eco": "jev"}}


def full(p):
    return {"id": p["id"], "theme_id": p["t"], "title": p["title"], "description": "Hausser le SMIC.",
            "source_evidence": [{"quote": "Hausser le SMIC"}]}


class BaremeTests(unittest.TestCase):
    def test_eco9_has_nine_regular_anchors_and_keeps_gate(self):
        r9, r5 = re9.rubric("eco9")["eco"], re9.rubric("eco5")["eco"]
        self.assertEqual([int(k) for k in r9["anchors"]], list(range(-100, 101, 25)))
        self.assertEqual([int(k) for k in r5["anchors"]], [-100, -50, 0, 50, 100])
        self.assertEqual(r9["applies_if"], r5["applies_if"])
        self.assertEqual(r9["anchors"]["-50"], r5["anchors"]["-50"])

    def test_cache_key_depends_on_bareme(self):
        item = {"id": "x", "dimensions": ["eco"]}
        self.assertNotEqual(re9.cache_key("m", "eco9", item), re9.cache_key("m", "eco5", item))


class SampleTests(unittest.TestCase):
    def test_only_economic_themes_with_eco_and_reproducible(self):
        rows = [shown(i) for i in range(20)] + [shown(100, t="securite"), shown(101, eco=None)]
        a = re9.select_sample(rows, {"roussel": 5}, 1, seed=1)
        self.assertEqual(len(a), 5)
        self.assertTrue(all(p["t"] == "fiscalite" and p["v"]["eco"] is not None for p in a))
        self.assertEqual([p["id"] for p in a], [p["id"] for p in re9.select_sample(list(reversed(rows)), {"roussel": 5}, 1, seed=1)])
        self.assertEqual(len(re9.select_sample(rows + [shown(200, c="zemmour")], {"roussel": 5}, 1, seed=1)), 6)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        rows = [shown(i) for i in range(3)]
        (self.dir / "ui.json").write_text(json.dumps({"proposals": rows}), encoding="utf-8")
        (self.dir / "in.json").write_text(json.dumps({"candidates": [], "proposals": [full(p) for p in rows]}), encoding="utf-8")

    def argv(self, *extra):
        return ["x", "--input", str(self.dir / "in.json"), "--interface", str(self.dir / "ui.json"),
                "--out", str(self.dir / "out.json"), "--cache-file", str(self.dir / "cache.json"), *extra]

    def test_plan_only_without_budget(self):
        with mock.patch.object(sys, "argv", self.argv()), mock.patch.object(re9, "request_json") as call:
            self.assertEqual(re9.main(), 0)
        call.assert_not_called()
        self.assertFalse((self.dir / "out.json").exists())

    def test_run_fills_cache_and_report_then_rerun_is_free(self):
        def fake(request, timeout, **kw):
            items = json.loads(json.loads(request.data)["messages"][0]["content"][len(re9.INSTRUCTIONS) + 1:])["proposals"]
            content = {"reviews": [{"id": i["id"], "assessments": {"eco": {"value": -75, "confidence": .8}}, "note": "SMIC"}
                                   for i in items]}
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}
        env = {"OPENROUTER_API_KEY": "test"}
        with mock.patch.object(sys, "argv", self.argv("--max-cost", "1")), mock.patch.dict("os.environ", env), \
                mock.patch.object(re9.ps, "load_env_file"), mock.patch.object(re9, "request_json", side_effect=fake) as call, \
                mock.patch.object(re9, "LLMJournal") as journal, mock.patch.object(re9, "journal_cost", return_value=0.0):
            journal.return_value.path = self.dir / "j.jsonl"
            self.assertEqual(re9.main(), 0)
        self.assertEqual(call.call_count, 2)  # un lot par bareme
        report = json.loads((self.dir / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(report["notes_obtenues"], {"eco9": 3, "eco5": 3})
        self.assertEqual(report["par_candidat"]["roussel"]["eco9"]["part_sous_-60"], 1.0)
        self.assertEqual(report["par_candidat"]["roussel"]["actuelle"]["moyenne"], -50)
        with mock.patch.object(sys, "argv", self.argv()), mock.patch.object(re9, "request_json") as call:
            self.assertEqual(re9.main(), 0)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
