import json
import unittest

import axes_2027 as ax


def row(**over):
    base = {"id": "a", "eco": 50, "soc": None, "sov": 0, "ecolo": -20, "rupture": 40, "income_direction": 30,
            "income_breadth": 60, "legal_instrument": "loi_ordinaire", "horizon": "mandat_1_a_5_ans", "note": "ok"}
    base.update(over)
    return base


def content(*rows):
    return json.dumps({"scores": list(rows)})


class ParseAxesTests(unittest.TestCase):
    def test_valid_rows_and_nulls(self):
        result = ax.parse_axes(content(row(), row(id="b", soc=-70)), ["a", "b"])
        self.assertEqual(result["a"]["soc"], None)
        self.assertEqual(result["b"]["soc"], -70)
        self.assertEqual(result["a"]["legal_instrument"], "loi_ordinaire")

    def test_breadth_is_null_when_direction_is_null(self):
        result = ax.parse_axes(content(row(income_direction=None, income_breadth=80)), ["a"])
        self.assertIsNone(result["a"]["income_breadth"])

    def test_rejects_invalid_content(self):
        bad = [row(eco=101), row(rupture=-1), row(eco=1.5), row(eco=True), row(legal_instrument="decret_royal"),
               row(horizon="demain"), row(note=None), {k: v for k, v in row().items() if k != "ecolo"},
               {**row(), "extra": 1}]
        for item in bad:
            with self.assertRaises(ValueError, msg=str(item)):
                ax.parse_axes(content(item), ["a"])
        with self.assertRaises(ValueError):
            ax.parse_axes(content(row(), row()), ["a"])  # doublon
        with self.assertRaises(ValueError):
            ax.parse_axes(content(row()), ["a", "b"])  # identifiant manquant

    def test_integer_valued_floats_are_accepted(self):
        self.assertEqual(ax.parse_axes(content(row(eco=40.0)), ["a"])["a"]["eco"], 40)


class BlindTests(unittest.TestCase):
    def test_names_are_masked_and_identity_fields_absent(self):
        names = ax.blind_names([{"first_name": "Marine", "last_name": "Dupuis", "party": "Parti Exemple"}])
        p = {"id": "p1", "candidate_id": "x", "theme_id": "logement", "title": "Plan Dupuis", "source_url": "https://e.fr",
             "description": "Le Parti Exemple veut 100 logements.",
             "source_evidence": [{"quote": "Marine Dupuis propose la marine nationale."}]}
        item = ax.blind_item(p, names)
        dumped = json.dumps(item)
        self.assertNotIn("Dupuis", dumped)
        self.assertNotIn("Parti Exemple", dumped)
        self.assertIn("marine nationale", dumped)  # prenom seul non masque : mot courant
        self.assertEqual(set(item), {"id", "theme", "title", "description", "quote"})

    def test_cache_key_depends_on_model_and_text(self):
        item = {"id": "a", "title": "t"}
        self.assertNotEqual(ax.cache_key("m1", item), ax.cache_key("m2", item))
        self.assertNotEqual(ax.cache_key("m1", item), ax.cache_key("m1", {**item, "title": "u"}))


class ScoreAllTests(unittest.TestCase):
    def test_batches_are_split(self):
        sizes = []

        def fake(batch):
            sizes.append(len(batch))
            return {i["id"]: {"eco": 0} for i in batch}
        result = ax.score_all([{"id": str(i)} for i in range(25)], fake, 10)
        self.assertEqual(sizes, [10, 10, 5])
        self.assertEqual(len(result), 25)


if __name__ == "__main__":
    unittest.main()
