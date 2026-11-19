import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import arbitrage_q2_2027 as ARB
import base_2027 as B
import boussole_2027 as BO
import essai_q2_2027 as E
from commun_2027 import masquer_alias
from llm_logging_2027 import LLMJournal as Journal
import lecture_q2_2027 as L
import questionnaire_2027 as Q1
import questionnaire_q2_2027 as Q2
from test_base_2027 import data, prop
from test_q2_2027 import api

ECO = {"levier": "depense_ou_service", "instrument": "loi_ordinaire", "cout": "cout_modere", "financement": "evoque",
       "portee": "large", "eco_depense": "augmente", "eco_marche": "inchange", "eco_transfert": "neutre"}


def lecture(conf=.8, **r):
    """Lecture q2 telle que le cache la garde : toutes les questions, null si absente."""
    rep = {**{k: None for k in Q2.QUESTIONS}, "chiffree": "non", "degre": "notable", **ECO, **r}
    return {"conditions": {}, "assessments": {k: {"value": v, "confidence": conf} for k, v in rep.items()}, "note": ""}


def arbitrage(lits, conf=.8, **valeurs):
    """Arbitrage simule : `valeurs` par question (absente : la reponse de la lecture A)."""
    return {"methode": ARB.METHODE, "litiges": {
        x["litige"]: {"reponses": {k: valeurs[k] if k in valeurs else (None if x["A"][k]["reponse"] == ARB.SANS_OBJET
                                                                       else x["A"][k]["reponse"]) for k in x["questions"]},
                      "confiance": conf, "raison": "Parce que."} for x in lits}}


def chat(contenu, fin="stop"):
    return {"choices": [{"finish_reason": fin, "message": {"content": json.dumps(contenu)}}]}


class CombinaisonTests(unittest.TestCase):
    def test_sans_motif_la_lecture_1(self):
        r = L.combiner(lecture(.9), lecture(.6))
        self.assertEqual((r["arbitrage"], r["divergences"]), ([], []))
        self.assertEqual(r["reponses"]["eco_depense"], "augmente")
        self.assertEqual(r["confiances"]["eco_depense"], .9)
        self.assertEqual(L.combiner(lecture(.4), lecture(.7))["confiances"]["eco_depense"], .7)   # accord : la plus haute

    def test_l_arbitre_choisit_et_s_explique(self):
        l1, l2 = lecture(eco_depense="augmente", levier="incitation"), lecture(eco_depense="reduit")
        self.assertIsNone(L.combiner(l1, l2))                          # arbitre pas encore lu
        lits = ARB.litiges(l1, l2, "x")
        self.assertEqual([x["litige"] for x in lits], ["eco_depense"])  # le levier n'est pas un motif d'arbitrage
        r = L.combiner(l1, l2, lits, arbitrage(lits, eco_depense="reduit"))
        self.assertEqual(r["reponses"]["eco_depense"], "reduit")
        self.assertEqual(r["reponses"]["levier"], "incitation")         # hors litige : la lecture 1
        self.assertEqual((r["arbitrage"], r["divergences"]), (["sens"], []))
        self.assertEqual(r["arbitrages"]["eco_depense"], {"choix": "lecteur2", "confiance": .8, "raison": "Parce que."})
        self.assertIn("Parce que.", r["note"])
        r = L.combiner(l1, l2, lits, arbitrage(lits, eco_depense="inchange"))   # ni l'une ni l'autre : signalee
        self.assertEqual((r["reponses"]["eco_depense"], r["divergences"]), ("inchange", ["eco_depense"]))
        r = L.combiner(l1, l2, lits, arbitrage(lits, conf=.3, eco_depense="augmente"))   # peu sur : signalee
        self.assertEqual((r["reponses"]["eco_depense"], r["confiances"]["eco_depense"], r["divergences"]),
                         ("augmente", .3, ["eco_depense"]))

    def test_revenus_d_un_bloc_et_coherence(self):
        stages = dict(levier="controle_prix_ou_revenus", eco_transfert="vers_modestes_ou_salaries")
        gagne = {k: "gagne" for k in Q1.CLASSES_REVENU}
        lits = ARB.litiges(lecture(**stages), lecture(**stages), "x")
        self.assertEqual([(x["litige"], "doute" in x) for x in lits], [("revenus", True)])
        self.assertEqual(lits[0]["A"]["rev_modestes"]["reponse"], ARB.SANS_OBJET)
        r = L.combiner(lecture(**stages), lecture(**stages), lits, arbitrage(lits, **gagne))
        self.assertEqual(r["arbitrage"], ["revenus_coherence"])
        self.assertEqual(r["reponses"]["rev_modestes"], "gagne")       # erreur commune corrigee par l'arbitre
        self.assertEqual(r["divergences"], ["revenus"])                 # ... a verifier a la main
        r = L.combiner(lecture(**stages), lecture(**stages), lits, arbitrage(lits))   # confirmee
        self.assertEqual((r["reponses"]["rev_modestes"], r["divergences"]), (None, []))
        perd = {k: "perd" for k in Q1.CLASSES_REVENU}
        lits = ARB.litiges(lecture(**gagne), lecture(**perd), "x")
        r = L.combiner(lecture(**gagne), lecture(**perd), lits, arbitrage(lits, **perd))
        self.assertEqual((r["reponses"]["rev_aises"], r["divergences"]), ("perd", []))

    def test_file_de_validation(self):
        base, _ = B.migrer(data(prop(1)))
        m = base["mesures"][0]
        l1, l2 = lecture(eco_depense="augmente"), lecture(eco_depense="reduit")
        lits = ARB.litiges(l1, l2, "x")
        L.appliquer(m, L.combiner(l1, l2, lits, arbitrage(lits, eco_depense="inchange")), "2026-11-12T00:00:00+00:00")
        self.assertEqual(m["annotation"]["arbitrages"]["eco_depense"]["choix"], "autre")
        vues = B.calculer(base, [])
        B.construire_file(base, vues, {})
        self.assertIn("divergence_lectures", {f["motif"] for f in m["file"]})
        dec = []
        B.nouvelle_decision(dec, base, m["uid"], "correction", champ="eco_depense", valeur="reduit")
        vues = B.calculer(base, dec)
        B.construire_file(base, vues, {})
        self.assertNotIn("divergence_lectures", {f["motif"] for f in m["file"]})


class ArbitrageTests(unittest.TestCase):
    def test_litiges_anonymes_ordre_tire_et_probabilites(self):
        l1 = E.lire_decision(api(ouvertes=("a_dispositif", "a_eco"), valeurs={**ECO, "degre": "notable"}))
        l2 = E.lire_decision(api(ouvertes=("a_dispositif", "a_eco"), valeurs={**ECO, "degre": "rupture"}))
        ordres = set()
        for uid in ("a", "b", "c", "d", "e", "f"):
            (x,) = ARB.litiges(l1, l2, uid)
            self.assertEqual((x["litige"], x["questions"]), ("degre", ["degre"]))
            self.assertEqual(x["A"]["degre"]["probabilites"], {x["A"]["degre"]["reponse"]: .8})
            ordres.add(x["A"]["degre"]["reponse"])
            self.assertEqual(ARB.litiges(l1, l2, uid), [x])             # meme mesure, meme ordre
        self.assertEqual(ordres, {"notable", "rupture"})                # l'ordre change d'une mesure a l'autre
        self.assertNotIn("drex", json.dumps(ARB.litiges(l1, l2, "a")))   # pas de nom de modele

    def test_lecture_de_la_reponse(self):
        l1, l2 = lecture(degre="notable"), lecture(degre="rupture", portee=None)
        it = ARB.item({"id": "m1", "title": "T"}, ARB.litiges(l1, l2, "m1"))
        self.assertEqual([x["litige"] for x in it["litiges"]], ["portee", "degre"])
        req = ARB.requete(L.ARBITRE, [it], "low")
        self.assertIn(ARB.SANS_OBJET, json.loads(req["messages"][0]["content"].split("\n", 4)[-1])["questions"]["portee"]["options"])
        bon = {"arbitrages": [{"id": "m1", "litiges": [
            {"litige": "portee", "reponses": [{"question": "portee", "reponse": "sans_objet"}], "confiance": .7, "raison": "R1"},
            {"litige": "degre", "reponses": [{"question": "degre", "reponse": "rupture"}], "confiance": .9, "raison": "R2"}]}]}
        out = ARB.lire(chat(bon), [it])
        self.assertEqual(out["m1"]["litiges"]["portee"], {"reponses": {"portee": None}, "confiance": .7, "raison": "R1"})
        mauvais = json.loads(json.dumps(bon))
        mauvais["arbitrages"][0]["litiges"][1]["reponses"][0]["reponse"] = "enorme"
        with self.assertRaises(ValueError):                               # hors options : mesure ecartee
            ARB.lire(chat(mauvais), [it])
        with self.assertRaises(ValueError):
            ARB.lire(chat(bon, fin="length"), [it])
        self.assertNotEqual(ARB.cle(L.ARBITRE, it, "low"), ARB.cle(L.ARBITRE, {**it, "litiges": []}, "low"))


class PasseCibleeTests(unittest.TestCase):
    def test_v5_puis_passe_ciblee_fusionnee(self):
        it = {"id": "m1", "title": "Le RN et les insoumis veulent", "description": "Selon Jordan Bardella."}
        v5 = E.lire_decision(api(ouvertes=("a_dispositif", "a_eco"), valeurs={**ECO, "degre": "ajustement"}))
        caches = [{E.cle_v5_decision(x, it): v5 for x in L.LECTEURS}]
        et = L.etat([it], caches)
        self.assertEqual(et[L.LECTEUR1]["lues"], {})
        (lu,) = et[L.LECTEUR1]["ciblees"]
        self.assertEqual((lu["title"], lu["description"]), ("Le [parti] et les [parti] veulent", "Selon [personnalité]."))
        self.assertEqual(L.plan([it], et)["lecteur1_passe_ciblee"], 1)
        cib = L.methode_cible()
        (req,) = cib.requetes(L.LECTEUR1, lu)
        self.assertEqual(list(req["questions"]), list(L.QUESTIONS_CIBLE))
        rep = api(ouvertes=("a_dispositif", "a_eco", "a_menages"), valeurs={**ECO, "degre": "notable"})
        nouveau = cib.lire(rep)
        self.assertEqual(set(nouveau["brut"]), set(L.QUESTIONS_CIBLE))
        caches[0].update({cib.cle(x, lu): nouveau for x in L.LECTEURS})
        et = L.etat([it], caches)
        x = et[L.LECTEUR1]["lues"]["m1"]
        self.assertEqual(E.reponses(x)["degre"], "notable")              # question reecrite : la passe ciblee
        self.assertEqual(E.reponses(x)["levier"], ECO["levier"])         # les autres : la v5
        self.assertIsNotNone(E.reponses(x)["rev_modestes"])               # condition rouverte par la passe ciblee
        self.assertEqual(L.plan([it], et)["lecteur1_passe_ciblee"], 0)
        bad = {k: v for k, v in rep["answers"].items() if k != "portee"}
        with self.assertRaises(ValueError):
            cib.lire({"answers": bad})

    def test_masquage_complementaire(self):
        self.assertEqual(masquer_alias({"id": "RN", "passage": "le PS, LR et l'EELV ; Les écologistes ; LE PEUPLE ; "
                                                                "Front National"}),
                         {"id": "RN", "passage": "le [parti], [parti] et l'[parti] ; Les [parti] ; LE PEUPLE ; [parti]"})
        self.assertEqual(masquer_alias("transition écologiste, PSG, RN-12"), "transition écologiste, PSG, RN-12")


class ChaineTests(unittest.TestCase):
    """annoter --q2 de bout en bout, API simulee : plan gratuit, lecteurs, arbitre, base passee en q2."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        f = self.dir / "in.json"
        f.write_text(json.dumps(data(prop(1), prop(2))), encoding="utf-8")
        self.run_cli("migrer", "--input", str(f))
        self.appels = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        with mock.patch.object(sys, "argv", ["x", "--racine", str(self.dir), *args]), mock.patch("builtins.print") as p:
            code = BO.main()
        self.sortie = "\n".join(" ".join(map(str, c.args)) for c in p.call_args_list)
        return code

    def requete(self, req, timeout, **k):
        corps = json.loads(req.data)
        self.appels.append(corps["model"])
        titre = corps["state"]["title"]
        # Mesure 1 : memes lectures. Mesure 2 : degre different -> arbitre.
        degre = "rupture" if titre == "Mesure 2" and corps["model"] == L.LECTEUR2 else "notable"
        return api(ouvertes=("a_dispositif", "a_eco", "a_menages"), valeurs={**ECO, "degre": degre})

    def test_plan_puis_lecture(self):
        self.assertEqual(self.run_cli("annoter", "--q2"), 0)
        self.assertIn("Aucun appel lance", self.sortie)
        self.assertEqual(self.appels, [])

        def arbitre(lots, modele, effort, cle, journal, cache, reste, ecrire=None, methode=None, **k):
            for lot in lots:
                for it in lot:
                    cache[methode.cle(modele, it, effort)] = arbitrage(it["litiges"], degre="rupture")
            ecrire(cache)
            return {"lots": len(lots), "echecs": 0, "relues": sum(map(len, lots))}

        with mock.patch("scoring_context_2027.request_json", side_effect=self.requete), mock.patch("time.sleep"), \
                mock.patch("contexte_2027.relire_direct", side_effect=arbitre) as terra, \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), \
                mock.patch("llm_logging_2027.LLMJournal", side_effect=lambda secrets=(): Journal(self.dir / "j.jsonl", secrets)), \
                mock.patch("update_corpus_2027.journal_cost", return_value=0.01):   # depense deja faite (journal)
            self.assertEqual(self.run_cli("annoter", "--q2", "--max-cost", "1"), 0)
        (it,) = terra.call_args.args[0][0]                                   # seule la mesure 2 va a l'arbitre
        self.assertEqual([x["litige"] for x in it["litiges"]], ["degre"])
        self.assertEqual(terra.call_args.args[6], 1.0)                        # plafond du run, pas le reste
        self.assertIn(L.LECTEUR2, self.appels)                                # le lecteur 2 lit malgre la depense du 1
        base = json.loads((self.dir / "donnees" / "base_2027.json").read_text(encoding="utf-8"))
        self.assertEqual(base["meta"]["questionnaire"], "q2")
        a1, a2 = (m["annotation"] for m in base["mesures"])
        self.assertEqual((a1["version"], a1["arbitrage"], a1["lecteurs"]), ("q2", [], [L.LECTEUR1, L.LECTEUR2]))
        self.assertEqual((a2["arbitrage"], a2["reponses"]["degre"]), (["degre"], "rupture"))
        self.assertEqual(a2["arbitrages"]["degre"]["choix"], "lecteur2")
        export = json.loads((self.dir / "donnees" / "donnees_interface_2027.json").read_text(encoding="utf-8"))
        self.assertEqual(export["meta"]["questionnaires"], {"q2": 2})
        # deuxieme run : tout est lu, rien n'est relu ; les lectures q1 sont refusees
        n = len(self.appels)
        with mock.patch("scoring_context_2027.request_json", side_effect=self.requete):
            self.assertEqual(self.run_cli("annoter", "--q2", "--max-cost", "1"), 0)
        self.assertEqual(len(self.appels), n)
        self.assertEqual(self.run_cli("annoter", "--contexte", "--tous", "--max-cost", "1"), 0)
        self.assertIn("Base passee au questionnaire q2", self.sortie)


if __name__ == "__main__":
    unittest.main()
