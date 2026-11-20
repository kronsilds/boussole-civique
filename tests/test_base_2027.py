import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import base_2027 as B
import boussole_2027 as BO
import pipeline_scoring_2027 as ps
import questionnaire_2027 as Q
from test_pipeline_scoring_2027 import answers

# Reponses q1 d'une hausse du SMIC (toutes les questions du questionnaire principal).
REPONSES_Q1 = {**{k: None for k in Q.CONDITIONNELLES if k in Q.QUESTIONS}, "levier": "controle_prix_ou_revenus",
               "public_vise": "salaries", "portee": "large", "changement": "reforme_significative", "precision": "precis",
               "instrument": "loi_ordinaire", "cout": "sans_impact_notable", "faisabilite": "elevee",
               "eco_etat": "augmente", "eco_distrib": "vers_modestes_ou_salaries"}


def jev_row(confidence=.2, **over):
    p = ps._parse_jev_proposal_answers({"id": "a", "title": "t"}, answers(confidence, axes=True), "jev")
    p.update(over)
    return p


def annoter(base, n, conf=.8):
    """Annotation q1 de la n-ieme mesure (1 = premiere), comme apres l'etape d'annotation."""
    m = base["mesures"][n - 1]
    m["annotation"] = {"version": Q.VERSION, "methode": "questionnaire", "modele": "m", "date": "2026-11-01T00:00:00+00:00",
                       "version_mesure": len(m["versions"]), "reponses": dict(REPONSES_Q1),
                       "confiances": {k: conf for k in REPONSES_Q1}, "note": "ok"}
    m["a_annoter"] = False
    return base


def prop(i, cand="roussel", title=None, eco=-50):
    p = jev_row(.9, id=f"corpus-{i:024d}", candidate_id=cand, theme_id="fiscalite", title=title or f"Mesure {i}",
                description="Hausser le SMIC.", precision="precis",
                repetition={"related_proposals": 2, "similar_proposals": 0, "documents": 1},
                source_evidence=[{"quote": "SMIC", "position": {"segment_index": 1, "segment_total": 10}}])
    p["axes"].update(eco=eco, rupture=75, cost_estimate="sans_impact_notable")
    return p


def data(*props):
    return {"meta": {"pipeline": "test"}, "candidates": [{"id": "roussel"}, {"id": "le-pen"}],
            "themes": [{"id": "fiscalite"}], "proposals": list(props)}


class MigrationTests(unittest.TestCase):
    def test_uids_stable_versions_and_statuses(self):
        base, r = B.migrer(data(prop(1), prop(2), prop(3, cand="le-pen")))
        uids = {m["historique"]["corpus_id"]: m["uid"] for m in base["mesures"]}
        self.assertEqual(sorted(uids.values()), ["m-le-pen-0001", "m-roussel-0001", "m-roussel-0002"])
        self.assertFalse(any(m["nouvelle"] for m in base["mesures"]))  # premiere migration : rien de « nouveau »
        p1 = prop(1, title="Mesure 1 précisée")
        base, r = B.migrer(data(p1, prop(3, cand="le-pen"), prop(4)), base=base)
        by = {m["historique"]["corpus_id"]: m for m in base["mesures"]}
        self.assertEqual(by[p1["id"]]["uid"], uids[p1["id"]])
        self.assertEqual(len(by[p1["id"]]["versions"]), 2)
        self.assertEqual(by[prop(2)["id"]]["statut"], "non_reprise")
        self.assertEqual(by[prop(4)["id"]]["uid"], "m-roussel-0003")
        self.assertTrue(by[prop(4)["id"]]["nouvelle"])
        self.assertEqual((r["ajoutees"], r["nouvelles_versions"], r["non_reprises"]), (1, 1, 1))
        base, r = B.migrer(data(p1, prop(2), prop(3, cand="le-pen"), prop(4)), base=base)
        self.assertEqual(by[prop(2)["id"]]["statut"], "active")

    def test_heavy_context_not_copied(self):
        p = prop(1)
        p["scoring_context"] = {"evidence": ["x" * 100]}
        base, _ = B.migrer(data(p))
        self.assertNotIn("scoring_context", base["mesures"][0]["proposition"])


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.base = annoter(B.migrer(data(prop(1), prop(2)))[0], 1)
        self.uid1, self.uid2 = (m["uid"] for m in self.base["mesures"])

    def test_validation_errors(self):
        dec = []
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, self.base, "m-x", "validation")
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, self.base, self.uid1, "correction", "levier", "inconnu")
        with self.assertRaises(ValueError):  # mesure 2 pas encore annotee
            B.nouvelle_decision(dec, self.base, self.uid2, "correction", "levier", "incitation")
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, self.base, self.uid1, "rejet")
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, self.base, self.uid1, "fusion", cible=self.uid1)
        self.assertEqual(dec, [])

    def test_correction_recomputes_eco_and_rejection_fusion(self):
        vues = B.calculer(self.base, [])
        avant = vues[self.uid1][0]["axes"]["eco"]
        self.assertLess(avant, -40)
        dec = []
        B.nouvelle_decision(dec, self.base, self.uid1, "correction", "eco_distrib", "neutre")
        vues = B.calculer(self.base, dec)
        p = vues[self.uid1][0]
        self.assertGreater(p["axes"]["eco"], avant)
        self.assertEqual(p["score_details"]["eco"]["corrigee"], ["eco_distrib"])
        B.nouvelle_decision(dec, self.base, self.uid2, "fusion", cible=self.uid1)
        B.calculer(self.base, dec)
        self.assertEqual(self.base["mesures"][1]["statut"], "remplacee")
        B.nouvelle_decision(dec, self.base, self.uid1, "rejet", motif="pas une mesure")
        B.calculer(self.base, dec)
        self.assertEqual(self.base["mesures"][0]["statut"], "rejetee")

    def test_decision_on_old_version_must_be_reviewed(self):
        dec = []
        B.nouvelle_decision(dec, self.base, self.uid1, "validation")
        base, _ = B.migrer(data(prop(1, title="Autre texte"), prop(2)), base=self.base)
        self.assertIsNotNone(base["mesures"][0]["annotation"])  # gardee, mais mesure a reannoter
        self.assertTrue(base["mesures"][0]["a_annoter"])
        vues = B.calculer(base, dec)
        self.assertTrue(vues[self.uid1][1]["a_revoir"])
        file = B.construire_file(base, vues, {})
        self.assertIn("decision_a_revoir", {f["motif"] for f in base["mesures"][0]["file"]})
        self.assertIn("mesure_modifiee", file)


class FileAndExportTests(unittest.TestCase):
    def test_motifs_cleared_by_later_validation(self):
        base, _ = B.migrer(data(prop(1)))
        base = annoter(B.migrer(data(prop(1), prop(2)), base=base)[0], 2, conf=.3)
        uid2 = base["mesures"][1]["uid"]
        vues = B.calculer(base, [])
        B.construire_file(base, vues, {}, date="2026-11-10T00:00:00+00:00")
        self.assertEqual({f["motif"] for f in base["mesures"][1]["file"]}, {"nouvelle_mesure", "confiance_basse"})
        dec = []
        B.nouvelle_decision(dec, base, uid2, "validation", date="2026-11-11T00:00:00+00:00")
        vues = B.calculer(base, dec)
        B.construire_file(base, vues, {}, date="2026-11-12T00:00:00+00:00")
        self.assertEqual(base["mesures"][1]["file"], [])

    def test_low_confidence_only_on_direction_questions(self):
        base = annoter(B.migrer(data(prop(1)))[0], 1)
        base["mesures"][0]["annotation"]["confiances"]["cout"] = .2  # ampleur : pas de relecture
        B.construire_file(base, B.calculer(base, []), {})
        self.assertNotIn("confiance_basse", {f["motif"] for f in base["mesures"][0]["file"]})
        base["mesures"][0]["annotation"]["confiances"]["eco_distrib"] = .3  # sens : relecture
        B.construire_file(base, B.calculer(base, []), {})
        self.assertIn("confiance_basse", {f["motif"] for f in base["mesures"][0]["file"]})

    def test_strong_move_and_publication_rules(self):
        base, _ = B.migrer(data(prop(1, eco=-50), prop(2)))
        uid1, uid2 = (m["uid"] for m in base["mesures"])
        vues = B.calculer(base, [])
        precedent = {uid1: {"id": uid1, "c": "roussel", "t": "fiscalite", "title": "Ancien", "v": {"eco": 20}}}
        B.construire_file(base, vues, precedent)
        self.assertIn("deplacement_fort", {f["motif"] for f in base["mesures"][0]["file"]})
        base, _ = B.migrer(data(prop(1, eco=-50, title="Modifiée"), prop(2)), base=base)
        vues = B.calculer(base, [])
        B.construire_file(base, vues, precedent)
        export = B.exporter(base, vues, precedent)
        rows = {r["id"]: r for r in export["proposals"]}
        self.assertEqual((rows[uid1]["title"], rows[uid1]["badge"]), ("Ancien", "en_revision"))  # bloquee
        self.assertEqual(rows[uid2]["title"], "Mesure 2")
        self.assertNotIn("badge", rows[uid2])

    def test_new_measure_published_with_badge_and_rejected_hidden(self):
        base, _ = B.migrer(data(prop(1)))
        base, _ = B.migrer(data(prop(1), prop(2)), base=base)
        uid1, uid2 = (m["uid"] for m in base["mesures"])
        dec = []
        B.nouvelle_decision(dec, base, uid1, "rejet", motif="doublon")
        vues = B.calculer(base, dec)
        B.construire_file(base, vues, {})
        rows = {r["id"]: r for r in B.exporter(base, vues, {})["proposals"]}
        self.assertNotIn(uid1, rows)
        self.assertEqual(rows[uid2]["badge"], "non_relue")
        self.assertEqual(rows[uid2]["lec"], {"rel": ["nouvelle_mesure"]})  # pas encore lue : seul le motif

    def test_reading_summary_exported(self):
        a = {"version": "q2", "lecteurs": ["x/lecteur-a", "y/lecteur-b", "z/arbitre"], "arbitrage": ["sens", "portee"],
             "divergences": ["cout"], "note": "r" * 500}
        lec = B.resume_lecture(a, {"confiance_basse", "deplacement_fort"}, {"validee_le": "2026-11-20T10:00:00+00:00"})
        self.assertEqual((lec["m"], lec["arb"], lec["lit"], lec["sig"]), (["lecteur-a", "lecteur-b"], "arbitre", ["sens", "portee"], ["cout"]))
        self.assertEqual((len(lec["raison"]), lec["raison"][-1]), (B.LONGUEUR_RAISON, "…"))
        self.assertEqual((lec["rel"], lec["val"]), (["confiance_basse"], "2026-11-20"))
        self.assertNotIn("vote", lec)  # arbitre des seuls litiges
        self.assertEqual(B.resume_lecture({**a, "methode": "essai-q2-v5"}, set(), {})["vote"], 1)  # troisieme lecture, vote
        accord = B.resume_lecture({**a, "lecteurs": a["lecteurs"][:2], "arbitrage": [], "divergences": [], "note": None}, set(), {})
        self.assertEqual(accord, {"m": ["lecteur-a", "lecteur-b"]})  # meme reponses : ni arbitre ni raison

    def test_structural_importance(self):
        low = prop(1)
        low.update(precision="orientation_generale", repetition={})
        low["source_evidence"] = [{"position": {"segment_index": 9, "segment_total": 10}}]
        high = prop(2)
        high.update(precision="chiffre", repetition={"related_proposals": 8, "similar_proposals": 1, "documents": 2})
        high["source_evidence"] = [{"position": {"segment_index": 0, "segment_total": 10}}, {}]
        self.assertLess(B.importance_structurelle(low, None), 25)
        self.assertEqual(B.importance_structurelle(high, None), 100)

    def test_nouveautes(self):
        precedent = {"a": {"id": "a", "c": "x", "t": "y", "title": "A", "v": {"eco": 0}},
                     "b": {"id": "b", "c": "x", "t": "y", "title": "B", "v": {"eco": 0}}}
        export = {"proposals": [{"id": "a", "c": "x", "t": "y", "title": "A2", "v": {"eco": 40}},
                                {"id": "c", "c": "x", "t": "y", "title": "C", "v": {"eco": 0}}]}
        n = B.nouveautes(precedent, export)
        self.assertEqual((n["ajoutees"], n["retirees"], n["modifiees"]), (["c"], ["b"], ["a"]))
        self.assertEqual(n["mesures_deplacees"][0]["apres"], 40)
        self.assertEqual(n["etoiles_deplacees"][0]["apres"], 20)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def run_cli(self, *args):
        with mock.patch.object(sys, "argv", ["x", "--racine", str(self.dir), *args]), mock.patch("builtins.print"):
            return BO.main()

    def write(self, name, payload):
        (self.dir / name).parent.mkdir(parents=True, exist_ok=True)
        (self.dir / name).write_text(json.dumps(payload), encoding="utf-8")
        return str(self.dir / name)

    def test_two_runs_end_to_end(self):
        # Export d'avant la migration (identifiants corpus) : sert de reference aux nouveautes.
        self.write("donnees/donnees_interface_2027.json", {"proposals": [
            {"id": prop(1)["id"], "c": "roussel", "t": "fiscalite", "title": "Mesure 1", "desc": "Hausser le SMIC.",
             "v": {"eco": -50}}]})
        first = self.write("in1.json", data(prop(1), prop(2)))
        self.assertEqual(self.run_cli("migrer", "--input", first), 0)
        export = json.loads((self.dir / "donnees" / "donnees_interface_2027.json").read_text(encoding="utf-8"))
        self.assertEqual({r["id"] for r in export["proposals"]}, {"m-roussel-0001", "m-roussel-0002"})
        nouv = json.loads((self.dir / "donnees" / "nouveautes_2027.json").read_text(encoding="utf-8"))
        self.assertEqual(nouv["ajoutees"], ["m-roussel-0002"])  # m-roussel-0001 reconnue via l'identifiant corpus
        self.assertTrue(list((self.dir / "runs").glob("*.md")))
        self.assertEqual(self.run_cli("decision", "--uid", "m-roussel-0002", "--type", "validation"), 0)
        second = self.write("in2.json", data(prop(1, title="Mesure 1 modifiée"), prop(2),
                                             prop(5, cand="le-pen")))
        self.assertEqual(self.run_cli("migrer", "--input", second), 0)
        base = json.loads((self.dir / "donnees" / "base_2027.json").read_text(encoding="utf-8"))
        by = {m["uid"]: m for m in base["mesures"]}
        self.assertEqual(set(by), {"m-roussel-0001", "m-roussel-0002", "m-le-pen-0001"})
        self.assertEqual({f["motif"] for f in by["m-roussel-0001"]["file"]}, {"mesure_modifiee"})
        self.assertEqual(by["m-roussel-0002"]["file"], [])  # validee, inchangee
        self.assertEqual({f["motif"] for f in by["m-le-pen-0001"]["file"]}, {"nouvelle_mesure"})
        rows = {r["id"]: r for r in json.loads((self.dir / "donnees" / "donnees_interface_2027.json").read_text(encoding="utf-8"))["proposals"]}
        self.assertEqual(rows["m-roussel-0001"]["title"], "Mesure 1")  # ancienne version publiee jusqu'a validation
        self.assertEqual(rows["m-le-pen-0001"]["badge"], "non_relue")
        self.assertEqual(len(list((self.dir / "sauvegardes").glob("base_2027_*.json"))) >= 1, True)

    def test_lock_and_missing_base(self):
        self.assertEqual(self.run_cli("mise-a-jour"), 2)  # base absente
        (self.dir / ".boussole.lock").write_text("1", encoding="utf-8")
        first = self.write("in1.json", data(prop(1)))
        self.assertEqual(self.run_cli("migrer", "--input", first), 2)
        self.assertEqual(self.run_cli("--force-verrou", "migrer", "--input", first), 0)
        self.assertFalse((self.dir / ".boussole.lock").exists())


if __name__ == "__main__":
    unittest.main()


def annoter_q2(base, n, **reponses):
    """Annotation q2 (questionnaire a l'essai) de la n-ieme mesure : reponses absentes = null (condition fermee)."""
    import questionnaire_q2_2027 as Q2
    m = base["mesures"][n - 1]
    r = {**{k: None for k in Q2.QUESTIONS}, "chiffree": "non", "degre": "notable", **reponses}
    m["annotation"] = {"version": Q2.VERSION, "methode": "essai-q2-v5", "modele": "drex-max", "date": "2026-11-12T00:00:00+00:00",
                       "version_mesure": len(m["versions"]), "reponses": r, "confiances": {k: .9 for k in r if r[k] is not None}}
    m["a_annoter"] = False
    return base


class Q2ExportTests(unittest.TestCase):
    """Base et export d'une mesure lue en q2 : nouveaux axes, faisabilite calculee, financement, indicateurs, regle
    societe, « Personnes concernees » vide sans public. Une mesure lue en q1 garde exactement son export."""

    def exporter(self, **par_mesure):
        base, _ = B.migrer(data(prop(1), prop(2), prop(3), prop(4)))
        annoter(base, 1)
        for n, r in par_mesure.items():
            annoter_q2(base, int(n[1:]), **r)
        vues = B.calculer(base, [])
        B.construire_file(base, vues, {})
        out = B.exporter(base, vues, {})
        return out, {r["id"]: r for r in out["proposals"]}, base

    def test_q2_measure_exported(self):
        dispositif = {"levier": "organisation_institutionnelle", "instrument": "revision_constitutionnelle", "cout": "sans_impact_notable"}
        out, rows, base = self.exporter(
            m2={**dispositif, "inst_objet": "pouvoir", "inst_direct": "etend", "inst_controle": "renforce", "financement": None},
            m3={"levier": "depense_ou_service", "instrument": "loi_ordinaire", "cout": "cout_massif", "financement": "non_finance",
                "portee": "large", "def_effort": "augmente", "int_alliances": "alliances",
                "eco_depense": "augmente", "eco_marche": "inchange", "eco_transfert": "neutre"},
            m4={**dispositif, "instrument": "loi_ordinaire", "inst_objet": "probite", "soc_autorite": "renforce",
                "soc_libertes": "etend", "soc_egalite": "oui"})
        u1, u2, u3, u4 = (m["uid"] for m in base["mesures"])
        self.assertEqual(out["meta"]["questionnaires"], {"q1": 1, "q2": 3})
        for k in ("inst", "inter", "defense", "financement"):
            self.assertIn(k, out["schema"])
        # mesure q1 : aucun champ q2 ajoute (export inchange)
        self.assertFalse({"inst", "inter", "defense"} & set(rows[u1]["v"]))
        self.assertNotIn("financement", rows[u1]["cat"])
        self.assertIsNotNone(rows[u1]["v"]["rights_income"])
        # contre-pouvoirs renforces (pole -100), democratie directe comptee, pas de public : portee vide
        r2 = rows[u2]
        self.assertLess(r2["v"]["inst"], 0)
        self.assertEqual(r2["ind"], ["democratie_directe"])
        self.assertIsNone(r2["v"]["rights_income"])
        self.assertEqual(r2["v"]["feasibility"], 0)            # revision constitutionnelle
        self.assertIn("calculée", r2["expl"]["feasibility"])
        self.assertEqual(r2["meth"]["inst"], "questionnaire-q2")
        # defense, alliances, faisabilite calculee (loi 50, cout massif non finance -25), financement exporte
        r3 = rows[u3]
        self.assertGreater(r3["v"]["defense"], 0)
        self.assertLess(r3["v"]["inter"], 0)
        self.assertEqual(r3["v"]["feasibility"], 25)
        self.assertEqual(r3["cat"]["financement"], "non_finance")
        self.assertEqual(r3["v"]["rights_income"], 100)
        self.assertNotIn("ind", r3)
        # regle societe q2 : protection contre une discrimination, seul le sens des libertes compte ; probite comptee
        r4 = rows[u4]
        self.assertLess(r4["v"]["soc"], 0)
        self.assertEqual(sorted(r4["ind"]), ["antidiscrimination", "probite"])
        self.assertNotIn("inst", r4["v"])                       # probite : pas de note de contre-pouvoirs

    def test_recul_and_correction_q2(self):
        _, rows, base = self.exporter(m2={"inst_objet": "pouvoir", "inst_direct": "recule", "inst_controle": "inchange"})
        u2 = base["mesures"][1]["uid"]
        self.assertEqual(rows[u2]["ind"], ["-democratie_directe"])
        self.assertNotIn("inst", rows[u2]["v"])                 # aspect non touche : pas de note
        dec = []
        B.nouvelle_decision(dec, base, u2, "correction", champ="inst_controle", valeur="affaiblit")
        with self.assertRaises(ValueError):
            B.nouvelle_decision(dec, base, u2, "correction", champ="eco_etat", valeur="augmente")   # question q1
        vues = B.calculer(base, dec)
        self.assertGreater(vues[u2][0]["axes"]["inst"], 0)
