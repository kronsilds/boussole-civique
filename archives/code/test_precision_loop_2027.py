import unittest

import precision_loop_2027 as pl
import selection_scoring_2027 as sel


def prop(i, title, description, candidate="a", theme="t"):
    return {"id": i, "candidate_id": candidate, "theme_id": theme, "title": title, "description": description,
            "source_evidence": [{"quote": description}]}


def make_group(n):
    """n propositions distinctes dont la precision heuristique decroit avec l'indice."""
    items = [prop(f"p{i}", f"Mesure numero{i} sujet{i}x", f"Porter le plafond a {1000 - i} euros par mois pour le cas {i}")
             for i in range(3)]
    items += [prop(f"q{i}", f"Orientation unique{i}z", f"Soutenir la politique generale numero {i}") for i in range(n - 3)]
    return sel.ordered_pools(items)


class ParseTests(unittest.TestCase):
    def test_accepts_exact_ids_only(self):
        ok = pl.parse_scores('{"scores": [{"id": "a", "precision": 10}, {"id": "b", "precision": 90}]}', ["a", "b"])
        self.assertEqual(ok, {"a": 10, "b": 90})
        for bad in ('{"scores": [{"id": "a", "precision": 10}]}',
                    '{"scores": [{"id": "a", "precision": 101}, {"id": "b", "precision": 1}]}',
                    '{"scores": [{"id": "a", "precision": 1.5}, {"id": "b", "precision": 1}]}',
                    '{"scores": [{"id": "a", "precision": 1}, {"id": "a", "precision": 1}]}',
                    '{"scores": [{"id": "a", "precision": 1, "x": 2}, {"id": "b", "precision": 1}]}'):
            with self.assertRaises(ValueError):
                pl.parse_scores(bad, ["a", "b"])

    def test_labels(self):
        self.assertEqual([pl.label_of(v) for v in (0, 33, 34, 66, 67, 100)],
                         ["orientation_generale", "orientation_generale", "precis", "precis", "chiffre", "chiffre"])


class LoopTests(unittest.TestCase):
    def test_no_extra_draw_when_llm_agrees_with_heuristic(self):
        pools = make_group(20)
        calls = []

        def agree(items):
            calls.append(len(items))
            return {p["id"]: int(pl.heuristic100(sel.precision_score(p)[0])) for p in items}
        result = pl.run_loop(pools, agree, per_theme=5, tolerance=25)
        self.assertEqual(calls, [5])
        self.assertEqual(result["report"]["extra_drawn"], 0)
        self.assertEqual(len(result["selected"]), 5)

    def test_draws_more_when_llm_disagrees_and_promotes_hidden_gems(self):
        pools = make_group(20)

        def disagree(items):  # le LLM trouve precises les "orientations" que l'heuristique rejette
            return {p["id"]: (95 if p["id"] in {"q15", "q16"} else 5) for p in items}
        result = pl.run_loop(pools, disagree, per_theme=5, tolerance=20, max_rounds=6, seed=1)
        self.assertGreater(result["report"]["extra_drawn"], 0)
        self.assertLessEqual(len(result["selected"]), 5)
        self.assertGreaterEqual(result["report"]["rounds_used"], 2)

    def test_stops_on_budget_and_flags_incomplete(self):
        pools = make_group(12)

        def broke(items):
            raise pl.BudgetExhausted()
        result = pl.run_loop(pools, broke, per_theme=4)
        self.assertTrue(result["report"]["exhausted_budget"])
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["report"]["incomplete_groups"], 1)

    def test_small_group_is_fully_scored_and_selected(self):
        pools = make_group(4)
        result = pl.run_loop(pools, lambda items: {p["id"]: 50 for p in items}, per_theme=8)
        self.assertEqual(len(result["selected"]), 4)


if __name__ == "__main__":
    unittest.main()
