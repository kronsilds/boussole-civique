import unittest

import descripteurs_2027 as D


def case(levier, portee, rupture, cout, etat, distrib):
    return dict(levier=levier, portee=portee, rupture=rupture, cost_estimate=cout, eco_etat=etat, eco_distrib=distrib)


M, N, A = "vers_modestes_ou_salaries", "neutre", "vers_aises_ou_entreprises"
# (libelle, repere attendu du bareme a 9 reperes ou None si discutable, descripteurs)
CASES = [
    ("Collectivisation : expropriation des grands groupes", -100, case("propriete_publique", "generale", 100, "indeterminable", "augmente", M)),
    ("Blocage du prix des carburants", -75, case("controle_prix_ou_revenus", "generale", 50, "cout_important", "augmente", M)),
    ("SMIC à 2 200 €", -75, case("controle_prix_ou_revenus", "large", 75, "sans_impact_notable", "augmente", M)),
    ("Nationalisation d'une seule entreprise", -75, case("propriete_publique", "individuelle", 75, "cout_modere", "augmente", N)),
    ("Soins remboursés à 100 %", -75, case("depense_ou_service", "generale", 75, "cout_massif", "augmente", M)),
    ("Fonds public de 500 Md€ pour le climat", -50, case("depense_ou_service", "generale", 75, "cout_massif", "augmente", N)),
    ("ISF renforcé sur les gros patrimoines", -50, case("prelevement", "ciblee", 50, "gain_important", "augmente", M)),
    ("Gratuité du permis pour les moins de 25 ans", -25, case("depense_ou_service", "ciblee", 25, "cout_modere", "augmente", N)),
    ("Sanctionner l'intérim abusif", -25, case("sanction_ou_controle", "large", 25, "sans_impact_notable", "augmente", M)),
    ("Subvention à la réindustrialisation", None, case("depense_ou_service", "large", 50, "cout_important", "augmente", A)),
    ("Crédit d'impôt rénovation énergétique", 0, case("incitation", "large", 25, "cout_modere", "inchange_ou_mixte", N)),
    ("Rapport sur la fiscalité des héritages", 0, case("information_ou_evaluation", "large", 0, "sans_impact_notable", "inchange_ou_mixte", N)),
    ("Baisse de TVA sur les produits de première nécessité", None, case("prelevement", "generale", 50, "cout_important", "diminue", M)),
    ("Simplification administrative pour les PME", 25, case("suppression_ou_allegement", "large", 25, "sans_impact_notable", "diminue", N)),
    ("Suppression de 100 000 postes de fonctionnaires", 50, case("depense_ou_service", "large", 75, "gain_important", "diminue", N)),
    ("Assouplir le licenciement", 50, case("suppression_ou_allegement", "large", 50, "sans_impact_notable", "diminue", A)),
    ("Baisse générale et forte des charges", 75, case("prelevement", "generale", 50, "cout_massif", "diminue", A)),
    ("Suppression des droits de succession", 75, case("prelevement", "large", 75, "cout_important", "diminue", A)),
    ("Privatiser la SNCF", 75, case("transfert_au_prive", "large", 100, "gain_modere", "diminue", N)),
    ("Privatisations massives et flat tax", 100, case("transfert_au_prive", "generale", 100, "gain_massif", "diminue", A)),
]
TOLERANCE = 25  # un repere d'ecart au plus


class EcoFormulaTests(unittest.TestCase):
    def test_reference_cases_within_one_anchor(self):
        for label, expected, d in CASES:
            value, _ = D.eco_score(d)
            if expected is not None:
                with self.subTest(label):
                    self.assertLessEqual(abs(value - expected), TOLERANCE, f"{label}: {value}")

    def test_extremes_and_neutral(self):
        self.assertEqual(D.eco_score(CASES[0][2])[0], -100)
        self.assertEqual(D.eco_score(CASES[-1][2])[0], 100)
        self.assertEqual(D.eco_score(case("incitation", "large", 25, None, "inchange_ou_mixte", N))[0], 0)

    def test_missing_answer_or_unknown_budget(self):
        self.assertIsNone(D.eco_score({**CASES[1][2], "eco_etat": None})[0])
        d = {**CASES[2][2], "cost_estimate": "indeterminable"}  # budget inconnu : seule la rupture compte
        self.assertEqual(D.eco_score(d)[0], D.eco_score({**d, "cost_estimate": "sans_impact_notable"})[0])

    def test_declaration_weighs_by_ambition(self):
        base = dict(levier="declaration_ou_symbole", portee="generale", cost_estimate="indeterminable",
                    eco_etat="augmente", eco_distrib=M)
        self.assertLessEqual(D.eco_score({**base, "rupture": 100})[0], -80)   # « mettre fin au capitalisme »
        self.assertGreaterEqual(D.eco_score({**base, "rupture": 0})[0], -20)  # objectif modeste
        self.assertEqual(D.eco_score({**base, "rupture": 100, "eco_etat": "inchange_ou_mixte", "eco_distrib": N})[0], 0)

    def test_scale_is_spread_not_snapped(self):
        values = {D.eco_score(d)[0] for _, _, d in CASES}
        self.assertGreaterEqual(len(values), 16)

    def test_explanation_in_words(self):
        _, detail = D.eco_score(CASES[2][2])
        self.assertIn("vers les modestes", detail["explication"])
        self.assertIn("portée large", detail["explication"])

    def test_every_option_has_a_weight(self):
        self.assertEqual(set(D.LEVIER_ECO), set(D.QUESTIONS["levier"]["criteria"]))
        self.assertEqual(set(D.MOTS["levier"]), set(D.QUESTIONS["levier"]["criteria"]))
        self.assertEqual(set(D.PORTEE), set(D.QUESTIONS["portee"]["criteria"]))
        self.assertEqual(set(D.ETAT), set(D.QUESTIONS["eco_etat"]["criteria"]))
        self.assertEqual(set(D.DISTRIB), set(D.QUESTIONS["eco_distrib"]["criteria"]))


if __name__ == "__main__":
    unittest.main()
