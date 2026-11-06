import unittest

import selection_scoring_2027 as sel


def prop(i, title, description, candidate="a", theme="t", quote=""):
    return {"id": i, "candidate_id": candidate, "theme_id": theme, "title": title,
            "description": description, "source_evidence": [{"quote": quote or description}]}


class PrecisionTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(sel.precision_score(prop("1", "SMIC", "Porter le SMIC à 2 200 euros net par mois."))[1], "chiffre")
        self.assertEqual(sel.precision_score(prop("2", "Loi", "Supprimer la taxe sur les successions de la résidence principale."))[1], "precis")
        self.assertEqual(sel.precision_score(prop("3", "Climat", "Soutenir la transition écologique."))[1], "orientation_generale")

    def test_numbers_written_in_words_count_as_numeric(self):
        for text in ("Étendre le congé de naissance jusqu'aux six mois de l'enfant.",
                     "Exiger cinq ans de résidence régulière.",
                     "Rendre obligatoires les conseils dans les communes de plus de 5 000 habitants."):
            self.assertEqual(sel.precision_score(prop("n", "Mesure", text))[1], "chiffre", text)
        self.assertEqual(sel.precision_score(prop("n", "Mesure", "Soutenir une politique familiale ambitieuse."))[1],
                         "orientation_generale")

    def test_vague_verb_with_number_is_still_numeric(self):
        self.assertEqual(sel.precision_score(prop("4", "Aide", "Soutenir 10 000 places d’hébergement par an."))[1], "chiffre")


class ExtendTests(unittest.TestCase):
    def test_adds_whole_themes_without_near_duplicates_and_keeps_base(self):
        props = [prop("1", "Quotas migratoires annuels", "Fixer 50 000 entrees par an.", theme="immigration"),
                 prop("2", "Quotas migratoires annuels votes", "Voter des quotas.", theme="immigration"),
                 prop("3", "Naturalisation plus exigeante", "Exiger dix ans de residence.", theme="immigration"),
                 prop("4", "Taxe carbone", "Hausse de 10 euros.", theme="ecologie")]
        base = [{"id": "3", "candidate_id": "a", "theme_id": "immigration", "precision": "chiffre", "precision_llm": 80}]
        chosen, stats = sel.extend_selection(props, base, ("immigration",))
        by_id = {c["id"]: c for c in chosen}
        self.assertEqual(set(by_id), {"1", "3"})          # 2 = quasi-doublon de 1 ; 4 hors theme
        self.assertEqual(by_id["3"]["selection"], "n8")
        self.assertEqual(by_id["3"]["precision_llm"], 80)
        self.assertEqual(by_id["1"]["selection"], "theme_complet")
        self.assertEqual(stats["added"], 1)


class SelectionTests(unittest.TestCase):
    def test_caps_per_candidate_and_theme_and_prefers_precise(self):
        items = [prop(f"v{i}", f"Orientation {i} distincte{i}", "Soutenir la transition écologique et sociale.")
                 for i in range(5)]
        items.append(prop("x", "SMIC 2200", "Porter le SMIC à 2 200 euros net par mois."))
        items.append(prop("o", "Autre theme", "Soutenir la culture.", theme="culture"))
        chosen, stats = sel.select(items, 2)
        ids = {c["id"] for c in chosen}
        self.assertIn("x", ids)
        self.assertIn("o", ids)  # chaque theme garde au moins sa meilleure proposition
        self.assertEqual(sum(c["theme_id"] == "t" for c in chosen), 2)
        self.assertEqual(stats["selected"], 3)

    def test_near_duplicate_titles_are_dropped(self):
        items = [prop("a", "Baisse du train de vie de l'État", "Baisser le train de vie de l'État de 2 milliards d'euros."),
                 prop("b", "Baisse du train de vie de l'État", "Baisser le train de vie de l'État de 3 milliards d'euros.")]
        chosen, _ = sel.select(items, 5)
        self.assertEqual(len(chosen), 1)


if __name__ == "__main__":
    unittest.main()
