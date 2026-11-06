import json
import tempfile
import unittest
from pathlib import Path

import update_corpus_2027 as up


class BudgetTests(unittest.TestCase):
    def test_budget_calls(self):
        self.assertEqual(up.budget_calls(1.0, 0.0, 0.004), 250)
        self.assertEqual(up.budget_calls(1.0, 0.9, 0.004), 25)
        self.assertEqual(up.budget_calls(1.0, 1.2, 0.004), 0)
        self.assertEqual(up.budget_calls(0, 0, 0.004), 0)  # pas de budget : aucun appel

    def test_journal_cost_ignores_lines_without_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "j.jsonl"
            lines = [{"event": "x"}, {"response": {"usage": {"cost": 0.01}}},
                     {"response": {"usage": {"cost": 0.0025}}}, {"response": {}}]
            path.write_text("\n".join(json.dumps(l) for l in lines) + "\nnot json\n", encoding="utf-8")
            self.assertAlmostEqual(up.journal_cost(path), 0.0125)
        self.assertEqual(up.journal_cost(Path("absent.jsonl")), 0.0)


class QualityReportTests(unittest.TestCase):
    def _corpus(self, tmp, per_candidate):
        root, manifest, ids = Path(tmp), {"documents": {}}, []
        for candidate, counts in per_candidate.items():
            chunks = []
            for i, n in enumerate(counts):
                rel = f"extractions/{candidate}-{i}.json"
                (root / "extractions").mkdir(exist_ok=True)
                (root / rel).write_text(json.dumps({"proposals": [{}] * n}), encoding="utf-8")
                chunks.append({"status": "ready", "path": rel})
            manifest["documents"][candidate] = {"bindings": [{"candidate_id": candidate}],
                                               "extraction": {"chunks": chunks}}
            ids.append(candidate)
        return root, manifest, ids

    def test_flags_density_outliers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, manifest, ids = self._corpus(tmp, {"a": [10, 10], "b": [12, 8], "c": [11, 9], "gros": [60, 60]})
            report = "\n".join(up.quality_report(root, manifest, ids))
        gros = next(l for l in report.splitlines() if l.startswith("gros"))
        self.assertIn("ALERTE densite elevee", gros)
        self.assertNotIn("ALERTE", next(l for l in report.splitlines() if l.startswith("a ")))

    def test_counts_empty_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, manifest, ids = self._corpus(tmp, {"a": [5, 0, 5]})
            line = up.quality_report(root, manifest, ids)[1].split()
        self.assertEqual(line[:5], ["a", "3", "10", "3.3", "1"])


if __name__ == "__main__":
    unittest.main()
