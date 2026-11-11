import json
import unittest
from pathlib import Path
from unittest import mock

import decisions_2027 as DX
import essai_q2_2027 as E
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2

ITEM = {"id": "abc12345", "theme": "institutions", "title": "Référendum d'initiative citoyenne", "description": "Créer le RIC.",
        "quote": "Nous créerons le RIC.", "passage": "Avant. Nous créerons le RIC. Après."}
BASE = {"levier": "obligation_ou_interdiction", "portee": "large", "chiffree": "non", "degre": "notable"}


def reponses(**r):
    return {**{k: None for k in Q2.QUESTIONS}, **BASE, **r}


def api(ouvertes=("a_institutions",), valeurs=None, proba=.9, refus=None):
    """Reponse simulee de l'API de decision : conditions `ouvertes` a `proba`, les autres a 0,1 ; une option par question."""
    valeurs = {**BASE, "inst_objet": "pouvoir", "inst_direct": "inchange", "inst_controle": "renforce", **(valeurs or {})}
    answers = {c: {"type": "noul", "noul": proba if c in ouvertes else .1} for c in Q2.CONDITIONS}
    for k, q in E.questions_decision().items():
        if k in Q2.CONDITIONS:
            continue
        options = list(Q2.QUESTIONS[k]["options"])
        val = valeurs.get(k) or options[0]
        if q["type"] == "noul":
            answers[k] = {"type": "noul", "noul": .9 if val == Q2.OUI else .2}
        elif q["type"] == "score":
            i = options.index(val)
            answers[k] = {"type": "score", "score": float(i), "confidence": .7, "probabilities": {str(i): .8}}
        else:
            answers[k] = {"type": "choice", "choice": val, "confidence": .7, "probabilities": {val: .8}}
    if refus:
        answers[refus] = {"type": "refusal"}
    return {"answers": answers, "usage": {"input_tokens": 100, "cost": .0003}}


class QuestionnaireTests(unittest.TestCase):
    def test_every_question_is_gated_by_a_known_condition_and_fits_the_api_lots(self):
        self.assertTrue(all(c in Q2.CONDITIONS for q in Q2.QUESTIONS.values() for c in Q2.conditions_de(q)))
        self.assertEqual(Q2.conditions_de(Q2.QUESTIONS["portee"]), ("a_menages", "a_eco", "a_ecolo"))   # un public, ou rien
        self.assertEqual(list(Q2.QUESTIONS["portee"]["options"]), ["individuelle", "ciblee", "large"])
        self.assertTrue(all(set(c) == {"question", "oui", "non"} for c in Q2.CONDITIONS.values()))
        poses = [k for lot in E.LOTS for k in lot]
        self.assertEqual(sorted(poses), sorted([*Q2.CONDITIONS, *Q2.QUESTIONS]))   # chaque question posee une fois
        self.assertTrue(all(len(lot) <= DX.MAX_QUESTIONS for lot in E.LOTS))
        for lot in E.LOTS:   # une condition est posee dans le meme appel que ses questions
            self.assertTrue(all(Q2.QUESTIONS[k]["condition"] in lot for k in lot
                                if k in Q2.QUESTIONS and isinstance(Q2.QUESTIONS[k]["condition"], str)))
        for k in Q2.QUESTIONS_SENS:   # echelle symetrique : un milieu, deux poles
            self.assertEqual((Q2.QUESTIONS[k]["type"], len(Q2.QUESTIONS[k]["options"]) % 2), ("echelle", 1))
        for retiree in ("public_vise", "changement", "faisabilite", "revenus_sens", "soc_finalite"):
            self.assertNotIn(retiree, Q2.QUESTIONS)
        self.assertNotIn("non_identifiable", Q2.QUESTIONS["instrument"]["options"])   # la condition a_dispositif en tient lieu
        self.assertNotIn("precision", Q2.QUESTIONS)   # calculee : a_dispositif + chiffree
        self.assertEqual(Q2.QUESTIONS["levier"]["condition"], "a_dispositif")

    def test_no_device_means_declaration_and_general_orientation(self):
        v = Q2.calculer(reponses(levier=None, degre="rupture", sov_niveau="vers_national"))[0]
        self.assertEqual((v["levier"], v["precision"], v["sov"]), ("declaration_ou_symbole", "orientation_generale", 85))
        self.assertEqual(Q2.calculer(reponses())[0]["precision"], "precis")
        self.assertEqual(Q2.calculer(reponses(levier=None, chiffree=Q2.OUI))[0]["precision"], "chiffre")   # objectif chiffre

    def test_axes_follow_one_rule_and_new_axes_are_scored(self):
        v, expl = Q2.calculer(reponses(inst_objet="pouvoir", inst_controle="renforce", int_alliances="non_alignement", def_effort="augmente"))
        self.assertEqual((v["inst"], v["inter"], v["defense"]), (-57, 57, 57))   # 100 x 1 x 0,7 x (0,55 + 0,45 x 0,6)
        self.assertIn("renforce", expl["inst"])
        self.assertTrue(all(v[ax] is None for ax in ("eco", "soc", "sov", "ouverture", "ecolo")))
        rupture = Q2.calculer(reponses(degre="rupture", sov_niveau="vers_national", env_sens="protege"))[0]
        self.assertEqual((rupture["sov"], rupture["ecolo"], rupture["rupture"]), (100, 100, 100))   # meme plafond partout
        annonce = Q2.calculer(reponses(levier="declaration_ou_symbole", degre="rupture", sov_niveau="vers_national"))[0]
        self.assertEqual(annonce["sov"], 85)   # un acte symbolique ne pese jamais comme un dispositif

    def test_economy_judges_three_aspects_and_weights_who_gains_most(self):
        def eco(depense="inchange", marche="inchange", transfert="neutre"):
            return Q2.calculer(reponses(eco_depense=depense, eco_marche=marche, eco_transfert=transfert))[0]["eco"]
        self.assertGreater(eco("augmente", transfert="vers_aises_ou_entreprises"), 0)   # aide aux entreprises
        self.assertLess(eco("reduit", transfert="vers_modestes_ou_salaries"), 0)        # baisse d'impot des modestes
        self.assertLess(eco(marche="encadre"), 0)                                       # nationalisation indemnisee
        self.assertEqual(eco("augmente", "liberalise"), 0)                              # depense publique et marche ouvert
        self.assertLess(eco("augmente", "encadre", "vers_modestes_ou_salaries"), eco("augmente"))
        self.assertIsNone(eco())   # trois fois le niveau du milieu : pas de direction
        self.assertIsNone(Q2.calculer(reponses(eco_depense="augmente"))[0]["eco"])
        self.assertNotIn("budget public", Q2.calculer(reponses(eco_depense="inchange", eco_marche="encadre", eco_transfert="neutre"))[1]["eco"])

    def test_society_single_question_is_not_capped_and_protection_ignores_the_sanction(self):
        soc = lambda **r: Q2.calculer(reponses(degre="rupture", **r))[0]["soc"]  # noqa: E731
        self.assertEqual(soc(soc_autorite="inchange", soc_libertes="etend", soc_egalite=Q2.NON), -80)   # q1 : -60
        self.assertEqual(soc(soc_autorite="renforce", soc_libertes="restreint", soc_egalite=Q2.NON), 100)
        self.assertEqual(soc(soc_autorite="renforce", soc_libertes="etend", soc_egalite=Q2.NON), 0)
        self.assertEqual(soc(soc_autorite="renforce", soc_libertes="etend", soc_egalite=Q2.OUI), -80)   # sanctionner une discrimination
        self.assertIsNone(soc(soc_autorite="renforce", soc_libertes="inchange", soc_egalite=Q2.OUI))    # plus de bascule automatique
        self.assertEqual(soc(soc_autorite="renforce", soc_libertes="inchange", soc_egalite=Q2.NON), 80)

    def test_rights_by_status_feed_the_immigration_axis_and_feasibility_is_computed(self):
        v = Q2.calculer(reponses(droits_statut="reserve_nationaux"))[0]
        self.assertGreater(v["ouverture"], 0)
        self.assertEqual(v["rights_status"], Q1.DROITS["reserve_nationaux"])
        v = Q2.calculer(reponses(droits_statut="reserve_nationaux", ouv_sens="accueil"))[0]
        self.assertLess(v["ouverture"], 0)   # la regle d'entree et de sejour prime
        f = lambda **r: Q2.calculer(reponses(**r))[0]["feasibility"]  # noqa: E731
        self.assertIsNone(f())   # pas de dispositif
        self.assertEqual(f(instrument="decret_ou_arrete"), 100)
        self.assertEqual(f(instrument="loi_ordinaire", cout="cout_faible"), 75)
        self.assertEqual(f(instrument="loi_de_finances_ou_securite_sociale", cout="cout_massif", financement="non_finance"), 25)
        self.assertEqual(f(instrument="loi_de_finances_ou_securite_sociale", cout="cout_massif", financement="designe"), 50)
        self.assertEqual(f(instrument="revision_constitutionnelle"), 0)
        v = Q2.calculer(reponses(instrument="loi_ordinaire", cout="gain_modere", financement="designe", rev_modestes="gagne"))[0]
        self.assertIsNone(v["financement"])   # sans objet pour une recette
        self.assertEqual((v["income_direction"], v["revenu_position"]), (50, -100))


    def test_institutions_counter_powers_axis_direct_democracy_and_probity_counted(self):
        inst = lambda **r: Q2.calculer(reponses(**r))[0]  # noqa: E731
        v = inst(inst_objet="pouvoir", inst_direct="etend", inst_controle="affaiblit")
        self.assertEqual((v["democratie_directe"], v["inst"], v["probite"]), ("etend", 57, False))   # plus de referendum, moins de juges
        self.assertNotIn("direct", Q2.AXES)   # indicateur compte, pas une position
        v = inst(inst_objet="pouvoir", inst_direct="etend", inst_controle="inchange")
        self.assertEqual((v["democratie_directe"], v["inst"]), ("etend", None))   # aspect non touche : pas de note
        self.assertIsNone(inst(inst_objet="pouvoir", inst_direct="inchange", inst_controle="renforce")["democratie_directe"])
        v = inst(inst_objet="probite", inst_direct="etend", inst_controle="renforce")
        self.assertEqual((v["democratie_directe"], v["inst"], v["probite"]), (None, None, True))   # comptee a part, hors axe
        v = inst(inst_objet="contenu_inconnu", inst_direct="etend", inst_controle="affaiblit")
        self.assertEqual((v["democratie_directe"], v["inst"]), (None, None))   # nouvelle Constitution : effet encore a ecrire
        self.assertIsNone(inst()["probite"])   # condition fermee
        self.assertIn("ponctuel", Q2.QUESTIONS["inst_direct"]["options"]["inchange"])
        self.assertIn("ponctuel", Q2.CONDITIONS["a_institutions"]["non"])
        self.assertNotIn("probit", Q2.QUESTIONS["inst_controle"]["options"]["renforce"])
        self.assertIn("initiative citoyenne", Q2.QUESTIONS["inst_controle"]["options"]["inchange"])   # le RIC n'affaiblit pas
        self.assertNotIn("initiative citoyenne", Q2.QUESTIONS["inst_controle"]["options"]["affaiblit"])
        valeurs = [{"democratie_directe": "etend", "probite": False}, {"democratie_directe": "etend", "probite": None},
                   {"democratie_directe": "recule", "probite": None}, {"democratie_directe": None, "probite": True}]
        self.assertEqual(Q2.frequences(valeurs, 500), {"democratie_directe": 2.0, "probite": 2.0})   # pour 1 000 mesures
        self.assertEqual(Q2.frequences([], 0), {"democratie_directe": None, "probite": None})

class TexteTests(unittest.TestCase):
    def lot(self, conditions=None, valeurs=None, sans=None):
        cond = {c: False for c in Q2.CONDITIONS} | (conditions or {})
        a = {k: {"value": (valeurs or {}).get(k, BASE.get(k, list(q["options"])[0])), "confidence": .8} for k, q in Q2.QUESTIONS.items()}
        a.pop(sans, None)
        contenu = json.dumps({"reviews": [{"id": ITEM["id"], "conditions": cond, "assessments": a, "note": "n"}]})
        return {"choices": [{"finish_reason": "stop", "message": {"content": contenu}}]}

    def test_rubric_asks_conditions_first_and_null_only_for_gated_questions(self):
        corps = E.requete("m", [ITEM], "low")
        self.assertIn("conditions", corps["messages"][0]["content"])
        r = E.rubrique()
        self.assertEqual(r["questions"]["inst_controle"]["si"], "a_institutions")
        self.assertNotIn("si", r["questions"]["degre"])
        self.assertEqual(r["questions"]["levier"]["si"], "a_dispositif")
        self.assertIn("eco_", E.CONSIGNE)   # le niveau du milieu est une reponse normale pour les trois aspects
        props = E.schema()["properties"]["reviews"]["items"]["properties"]
        self.assertEqual(props["conditions"]["required"], list(Q2.CONDITIONS))
        self.assertIn(None, props["assessments"]["properties"]["inst_controle"]["properties"]["value"]["enum"])
        self.assertNotIn(None, props["assessments"]["properties"]["degre"]["properties"]["value"]["enum"])

    def test_false_condition_nulls_its_questions_and_incomplete_review_is_rejected(self):
        r = E.lire(self.lot({"a_institutions": True}, {"inst_controle": "affaiblit", "sov_niveau": "vers_national"}), [ITEM])[ITEM["id"]]
        self.assertEqual(r["assessments"]["inst_controle"]["value"], "affaiblit")
        self.assertIsNone(r["assessments"]["sov_niveau"]["value"])   # condition a_sov fausse : la reponse est ignoree
        self.assertEqual((r["conditions"]["a_institutions"], r["conditions"]["a_sov"]), (1.0, 0.0))
        v = Q2.calculer(E.reponses(r))[0]
        self.assertGreater(v["inst"], 0)
        self.assertIsNone(v["sov"])
        with self.assertRaises(ValueError):
            E.lire(self.lot(sans="portee"), [ITEM])
        with self.assertRaises(ValueError):
            E.lire(self.lot(valeurs={"degre": "inconnu"}), [ITEM])
        self.assertNotEqual(E.cle("m", ITEM, "low"), E.cle("m", ITEM, "medium"))


class DecisionTests(unittest.TestCase):
    def test_questions_are_self_contained_and_typed(self):
        qs = E.questions_decision()
        self.assertEqual({k for k, q in qs.items() if q["type"] == "noul"}, {*Q2.CONDITIONS, "soc_egalite", "chiffree"})
        self.assertEqual(set(qs["a_droits"]["criteria"]), {"true", "false"})
        self.assertEqual((qs["levier"]["type"], qs["inst_controle"]["type"]), ("choice", "score"))
        self.assertEqual(qs["inst_controle"]["criteria"], list(Q2.QUESTIONS["inst_controle"]["options"].values()))
        self.assertEqual(qs["inst_objet"]["type"], "choice")
        self.assertIn(E.RAPPEL_ASPECT, qs["inst_direct"]["instructions"])   # milieu = aspect non touche
        self.assertTrue(all(q["instructions"].startswith(E.PREFIXE) for q in qs.values()))   # chaque question nomme ce qu'elle juge
        self.assertIn(E.RAPPEL_SENS, qs["sov_niveau"]["instructions"])
        self.assertIn(E.RAPPEL_ASPECT, qs["eco_marche"]["instructions"])   # milieu = aspect non touche
        self.assertNotIn(E.RAPPEL_SENS, qs["eco_marche"]["instructions"])
        self.assertNotIn(E.RAPPEL_SENS, qs["levier"]["instructions"])
        self.assertEqual(E.questions_decision("choice")["inst_controle"]["type"], "choice")
        m = E.methode_decision()
        corps = m.requetes("m", ITEM)
        self.assertEqual([list(c["questions"]) for c in corps], [list(lot) for lot in E.LOTS])
        self.assertNotIn(ITEM["id"], json.dumps(corps[0]["state"]))   # aveugle : pas d'identifiant
        self.assertNotEqual(m.cle("m", ITEM), E.methode_decision("choice").cle("m", ITEM))

    def test_reading_applies_threshold_scale_levels_and_refusals(self):
        r = E.lire_decision(api(valeurs={"sov_niveau": "vers_national", "soc_egalite": Q2.OUI}, proba=.6))
        a = r["assessments"]
        self.assertEqual((a["inst_controle"]["value"], a["inst_controle"]["confidence"]), ("renforce", .6))   # min(0,7 ; 0,6)
        self.assertEqual((a["sov_niveau"]["value"], a["sov_niveau"]["confidence"]), (None, .9))
        self.assertEqual(a["degre"]["value"], "notable")
        self.assertIsNone(a["levier"]["value"])   # a_dispositif fermee : declaration, calculee
        self.assertEqual(Q2.calculer(E.reponses(r))[0]["levier"], "declaration_ou_symbole")
        self.assertIsNone(a["soc_egalite"]["value"])   # a_soc fermee
        self.assertLess(Q2.calculer(E.reponses(r))[0]["inst"], 0)
        self.assertIsNone(E.lire_decision(api(proba=.6), seuil=.7)["assessments"]["inst_controle"]["value"])
        self.assertEqual(E.lire_decision({"answers": r["brut"]})["assessments"], a)   # relisible depuis `brut`
        ouvert = E.lire_decision(api(ouvertes=("a_soc",), valeurs={"soc_egalite": Q2.OUI}))["assessments"]["soc_egalite"]
        self.assertEqual((ouvert["value"], ouvert["confidence"]), (Q2.OUI, .8))   # |2 x 0,9 - 1|
        rep = api()
        rep["answers"]["degre"] = {"type": "score", "score": 1.8, "confidence": .6}   # sans probabilites : niveau arrondi
        self.assertEqual(E.lire_decision(rep)["assessments"]["degre"]["value"], "rupture")
        for casse in (api(refus="chiffree"), api(refus="a_eco"), {"answers": {**api()["answers"], "degre": {"type": "score", "score": 7}}}):
            with self.assertRaises(ValueError):
                E.lire_decision(casse)

    def test_direct_reading_uses_the_q2_method_three_calls_per_measure(self):
        cache, corps = {}, []

        def appel(req, *a, **k):
            corps.append(json.loads(req.data))
            self.assertEqual(k["stage"], "essai_q2_decisions")
            return api()

        methode = E.methode_decision()
        journal = mock.Mock(path=Path("inexistant.jsonl"))
        with mock.patch("update_corpus_2027.journal_cost", return_value=0.0), mock.patch("builtins.print"):
            stats = DX.lire_direct([ITEM], "m", "cle", journal, 1.0, cache.update, appel=appel, methode=methode)
        self.assertEqual((stats["lues"], stats["appels"]), (1, len(E.LOTS)))
        self.assertEqual(list(cache), [methode.cle("m", ITEM)])
        self.assertEqual(cache[methode.cle("m", ITEM)]["assessments"]["inst_controle"]["value"], "renforce")
        self.assertEqual(sum(len(c["questions"]) for c in corps), len(Q2.CONDITIONS) + len(Q2.QUESTIONS))


class RapportTests(unittest.TestCase):
    def test_comparison_and_sample_of_measures_without_axis(self):
        a = E.lire_decision(api())
        b = E.lire_decision(api(ouvertes=("a_institutions", "a_sov"), valeurs={"inst_controle": "affaiblit", "sov_niveau": "vers_national"}))
        ligne = E.comparer(a, b)
        self.assertEqual(ligne["sens_differe"], ["sov_niveau", "inst_controle"])
        self.assertEqual(ligne["conditions"]["a_sov"], (False, True))
        s = E.synthese([ligne, E.comparer(a, a)])
        self.assertEqual((s["mesures_comparees"], s["accord_sens_complet"]), (2, 1))
        self.assertEqual(s["conditions"]["a_sov"], {"accord": 1, "oui_premier_seul": 0, "oui_second_seul": 1, "oui_des_deux": 0})
        self.assertEqual(s["questions"]["inst_controle"], {"n": 2, "accord": 1})
        self.assertEqual(s["questions"]["sov_niveau"]["n"], 0)   # jamais notee des deux cotes
        self.assertEqual(s["axes"]["inst"]["signes_opposes"], 1)

        def mesure(uid, cand, theme, eco=None):
            r = {"levier": "declaration_ou_symbole", "portee": "generale", "changement": "reforme_significative",
                 "eco_etat": eco, "eco_distrib": eco and "neutre"}
            return {"uid": uid, "statut": "active", "candidate_id": cand, "theme_id": theme, "annotation": {"reponses": r},
                    "versions": [{"title": "Sortir de l'OTAN" if uid == "n1" else "Titre", "description": ""}]}
        base = {"mesures": [mesure("i1", "a", "institutions"), mesure("i2", "b", "institutions"), mesure("n1", "a", "international"),
                            mesure("e1", "a", "institutions", eco="augmente"), mesure("s1", "a", "sante")]}
        tirage = E.nouveaux_axes(base, {"i2"}, 5, 1)
        self.assertEqual(sorted(tirage), ["i1", "n1"])   # ni la mesure deja notee, ni l'exclue, ni un autre theme
        self.assertEqual(tirage, E.nouveaux_axes(base, {"i2"}, 5, 1))
        neuf = E.echantillon_neuf(base, {"i2"}, 1, {"neuf_alliances": 2, "neuf_representatif": 2})
        self.assertEqual(neuf["neuf_alliances"], ["n1"])   # mots des alliances
        self.assertEqual(len(neuf["neuf_representatif"]), 2)
        self.assertFalse({"n1", "i2"} & set(neuf["neuf_representatif"]))   # une mesure n'entre que dans un groupe
        self.assertEqual(neuf, E.echantillon_neuf(base, {"i2"}, 1, {"neuf_alliances": 2, "neuf_representatif": 2}))

    def test_references_three_readings_and_long_scales(self):
        a = E.lire_decision(api())
        self.assertEqual(E.ecarts_etalon(a, {"a_institutions": True, "inst_controle": ["renforce"], "a_sov": False, "sov_niveau": [None]}), [])
        self.assertEqual(E.ecarts_etalon(a, {"a_sov": True, "inst_controle": ["affaiblit", "inchange"]}),
                         [("a_sov", True, False), ("inst_controle", ["affaiblit", "inchange"], "renforce")])
        b = E.lire_decision(api(valeurs={"inst_controle": "affaiblit"}))
        t = E.trois_lectures({"x": [a, a, None], "y": [a, a, a], "z": [a, b, a]})
        self.assertEqual((t["mesures_lues_par_tous"], t["accord_complet"]), (2, 1))
        self.assertEqual(t["seul_contre_les_autres"], {"x": 0, "y": 0, "z": 1})
        self.assertEqual(t["unanimes"], 2 * len(Q2.QUESTIONS_SENS) - 1)
        ouvertes = ("a_dispositif", "a_menages")
        c1 = E.lire_decision(api(ouvertes, {"cout": "cout_modere", "rev_modestes": "gagne", "rev_aises": "perd"}))
        c2 = E.lire_decision(api(ouvertes, {"cout": "cout_important", "rev_modestes": "gagne_fortement", "rev_aises": "gagne"}))
        q = E.synthese([E.comparer(c1, c2)])["questions"]
        self.assertEqual(q["cout"], {"n": 1, "accord": 0, "a_un_niveau": 1, "meme_cote": 1})
        self.assertEqual((q["rev_modestes"]["accord"], q["rev_modestes"]["meme_cote"]), (0, 1))   # meme sens, autre intensite
        self.assertEqual(q["rev_aises"]["meme_cote"], 0)


if __name__ == "__main__":
    unittest.main()
