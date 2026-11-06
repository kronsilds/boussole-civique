import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pilote_descripteurs_2027 as pd

ANSWER = {"levier": "controle_prix_ou_revenus", "public_vise": "salaries", "portee": "large",
          "eco_etat": "augmente", "eco_distrib": "vers_modestes_ou_salaries"}


def shown(i, t="fiscalite", eco=-50):
    return {"id": f"corpus-{i:024d}", "c": "roussel", "t": t, "title": f"Mesure {i}", "v": {"eco": eco}}


def full(p):
    return {"id": p["id"], "theme_id": p["t"], "title": p["title"], "description": "Hausser le SMIC.",
            "axes": {"rupture": 75, "cost_estimate": "sans_impact_notable"}, "source_evidence": [{"quote": "SMIC"}]}


def completion(items, **override):
    reviews = [{"id": i["id"], "assessments": {q: {"value": v, "confidence": .8} for q, v in {**ANSWER, **override}.items()},
                "note": "ok"} for i in items]
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": reviews})}}]}


def body(request):
    """Corps JSON de la requete : derniere ligne du message (la consigne contient des retours a la ligne)."""
    return json.loads(json.loads(request.data)["messages"][0]["content"].split("\n")[-1])


class SchemaTests(unittest.TestCase):
    def test_rubric_gates_only_eco_questions(self):
        r = pd.rubric()
        self.assertEqual(list(r), list(pd.QUESTIONS))
        self.assertTrue(all("applies_if" in r[q] for q in pd.ECO))
        self.assertFalse(any("applies_if" in r[q] for q in pd.COMMON))

    def test_schema_allows_null_only_for_eco(self):
        props = pd.response_schema()["properties"]["reviews"]["items"]["properties"]["assessments"]["properties"]
        self.assertIn(None, props["eco_etat"]["properties"]["value"]["enum"])
        self.assertNotIn(None, props["levier"]["properties"]["value"]["enum"])

    def test_parse_rejects_null_common_and_unknown_option(self):
        lot = [{"id": "a"}, {"id": "b"}]
        good = completion([{"id": "a"}])
        bad = completion([{"id": "b"}], levier=None)
        merged = json.loads(good["choices"][0]["message"]["content"])["reviews"] + \
            json.loads(bad["choices"][0]["message"]["content"])["reviews"]
        resp = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"reviews": merged})}}]}
        self.assertEqual(list(pd.parse(resp, lot)), ["a"])
        with self.assertRaises(ValueError):
            pd.parse(completion(lot, portee="immense"), lot)
        self.assertIsNone(pd.parse(completion(lot, eco_etat=None, eco_distrib=None), lot)["a"]["assessments"]["eco_etat"]["value"])

    def test_cache_key_differs_by_reading(self):
        item = {"id": "x"}
        self.assertNotEqual(pd.cache_key("m", item, 1), pd.cache_key("m", item, 2))


class SampleTests(unittest.TestCase):
    def test_eco9_rows_then_per_theme(self):
        disp = [shown(i) for i in range(5)] + [shown(100 + i, t=t, eco=None) for i, t in enumerate(pd.OTHER_THEMES * 3)]
        s = pd.select_sample([{"id": disp[0]["id"]}, {"id": disp[1]["id"]}], disp, 2, seed=1)
        self.assertEqual([p["id"] for p in s[:2]], [disp[0]["id"], disp[1]["id"]])
        self.assertEqual(len(s), 2 + 2 * len(pd.OTHER_THEMES))


class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        rows = [shown(i) for i in range(4)] + [shown(10 + i, t=t, eco=None) for i, t in enumerate(pd.OTHER_THEMES)]
        (self.dir / "ui.json").write_text(json.dumps({"proposals": rows}), encoding="utf-8")
        (self.dir / "in.json").write_text(json.dumps({"candidates": [], "proposals": [full(p) for p in rows]}), encoding="utf-8")
        eco9 = [{"id": r["id"], "eco9": -75} for r in rows[:4]]
        (self.dir / "eco9.json").write_text(json.dumps({"mesures": eco9}), encoding="utf-8")

    def argv(self, *extra):
        return ["x", "--input", str(self.dir / "in.json"), "--interface", str(self.dir / "ui.json"),
                "--eco9", str(self.dir / "eco9.json"), "--out", str(self.dir / "out.json"),
                "--cache-file", str(self.dir / "cache.json"), "--per-theme", "1", "--double", "3", *extra]

    def test_plan_only_without_budget(self):
        with mock.patch.object(sys, "argv", self.argv()), mock.patch.object(pd, "request_json") as call:
            self.assertEqual(pd.main(), 0)
        call.assert_not_called()
        self.assertFalse((self.dir / "out.json").exists())

    def test_run_then_rerun_is_free(self):
        def fake(request, timeout, **kw):
            return completion(body(request)["proposals"])
        with mock.patch.object(sys, "argv", self.argv("--max-cost", "1")), \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), mock.patch.object(pd.ps, "load_env_file"), \
                mock.patch.object(pd, "request_json", side_effect=fake) as call, \
                mock.patch.object(pd, "LLMJournal") as journal, mock.patch.object(pd, "journal_cost", return_value=0.0):
            journal.return_value.path = self.dir / "j.jsonl"
            self.assertEqual(pd.main(), 0)
        self.assertEqual(call.call_count, 2)  # premiere lecture + seconde lecture
        r = json.loads((self.dir / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(r["lectures"]["premiere"], 9)
        self.assertEqual(r["lectures"]["seconde"], 3)
        self.assertEqual(r["stabilite"]["levier"], 1.0)
        self.assertEqual(r["mesures"][0]["eco_calculee"], -74)  # cas type SMIC de test_descripteurs_2027
        self.assertEqual(r["accord_eco9"]["part_moins_de_25_points"], 1.0)
        self.assertEqual(r["condition_eco"]["eco_actuelle_absente_mais_repondu"], 5)
        with mock.patch.object(sys, "argv", self.argv()), mock.patch.object(pd, "request_json") as call:
            self.assertEqual(pd.main(), 0)
        call.assert_not_called()

    def run_with(self, fake, *extra):
        with mock.patch.object(sys, "argv", self.argv("--max-cost", "1", *extra)),                 mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), mock.patch.object(pd.ps, "load_env_file"),                 mock.patch.object(pd, "request_json", side_effect=fake) as call,                 mock.patch.object(pd, "LLMJournal") as journal, mock.patch.object(pd, "journal_cost", return_value=0.0):
            journal.return_value.path = self.dir / "j.jsonl"
            code = pd.main()
        return code, call

    def test_correctif_rereads_only_declarations_with_new_instructions(self):
        declaration = dict(levier="declaration_ou_symbole", eco_etat="inchange_ou_mixte", eco_distrib="neutre")
        code, _ = self.run_with(lambda req, t, **kw: completion(body(req)["proposals"], **declaration))
        self.assertEqual(code, 0)
        seen = []

        def fixed(req, t, **kw):
            seen.append(json.loads(req.data)["messages"][0]["content"])
            return completion(body(req)["proposals"], levier="declaration_ou_symbole")
        code, call = self.run_with(fixed, "--correctif")
        self.assertEqual(code, 0)
        self.assertEqual(call.call_count, 1)  # 9 mesures en un lot, lectures 1 et 2 deja en cache
        self.assertTrue(seen[0].startswith(pd.INSTRUCTIONS))
        r = json.loads((self.dir / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(r["lectures"]["corrigees"], 9)
        self.assertEqual(r["mesures"][0]["premiere_lecture"]["eco_etat"], "inchange_ou_mixte")
        self.assertLess(r["mesures"][0]["eco_calculee"], -50)  # orientation annoncee, ampleur forte (rupture 75)
        code, call = self.run_with(fixed, "--correctif")
        self.assertEqual(call.call_count, 0)

    def test_needs_fix(self):
        def first(**over):
            return {"assessments": {q: {"value": v} for q, v in {**ANSWER, **over}.items()}}
        self.assertFalse(pd.needs_fix(first(), -50))
        self.assertTrue(pd.needs_fix(first(levier="declaration_ou_symbole"), None))
        self.assertTrue(pd.needs_fix(first(eco_etat="inchange_ou_mixte", eco_distrib="neutre"), None))
        self.assertTrue(pd.needs_fix(first(eco_etat=None, eco_distrib=None), -40))
        self.assertFalse(pd.needs_fix(first(eco_etat=None, eco_distrib=None), None))


if __name__ == "__main__":
    unittest.main()
