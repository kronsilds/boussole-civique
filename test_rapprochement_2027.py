import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import base_2027 as B
import boussole_2027 as BO
import rapprochement_2027 as R
from test_base_2027 import data

SMIC = ("Hausse du SMIC", "Porter le SMIC à 1600 euros nets par mois dès le début du quinquennat.")
TEXTES = {
    "quasi": ("Hausse du SMIC", "Porter le SMIC à 1600 euros nets par mois dès le début du quinquennat !"),   # 1.0
    "precis": ("Hausse du SMIC à 1600 euros",
               "Porter le SMIC à 1600 euros nets par mois dès juillet 2027, puis l'indexer sur les prix."),  # 0.60
    "modif": ("Hausse du SMIC", "Porter le SMIC à 1400 euros nets par mois en fin de quinquennat."),           # 0.80
    "loin": ("Gratuité des cantines", "Rendre les cantines scolaires gratuites pour tous les élèves du primaire."),
}


def mesure(i, titre, description, doc="doc-a", seg="s001", start=0, cand="roussel", quote=None):
    return {"id": f"corpus-{i:024d}", "candidate_id": cand, "theme_id": "emploi", "title": titre,
            "description": description, "precision": "precis", "axes": {"eco": -60},
            "source_evidence": [{"document_id": doc, "segment_id": seg, "start": start, "end": start + 50,
                                 "quote": quote or f"citation {i} " + "x" * 50}]}


class SimilarityTests(unittest.TestCase):
    def test_scores_and_overlap(self):
        e = R.empreinte_texte(*SMIC)
        self.assertEqual(R.similarite(e, R.empreinte_texte(*TEXTES["quasi"])), 1.0)
        self.assertLess(R.similarite(e, R.empreinte_texte(*TEXTES["loin"])), R.SEUIL_DIFFERENTE)
        for k in ("precis", "modif"):
            self.assertTrue(R.SEUIL_DIFFERENTE <= R.similarite(e, R.empreinte_texte(*TEXTES[k])) < R.SEUIL_MEME, k)
        a = {"document_id": "d", "segment_id": "s1", "start": 10, "end": 60}
        self.assertTrue(R.citations_chevauchent(a, {**a, "start": 50, "end": 90}))
        self.assertFalse(R.citations_chevauchent(a, {**a, "start": 60, "end": 90}))
        self.assertFalse(R.citations_chevauchent(a, {**a, "segment_id": "s2"}))
        q = "une citation assez longue pour compter comme identique entre deux sources"
        self.assertTrue(R.citations_chevauchent({"quote": q}, {"quote": q.upper()}))

    def test_prefilter_keeps_best(self):
        pool = [(k, R.empreinte_texte(*t)) for k, t in TEXTES.items()]
        self.assertEqual(R.meilleurs(R.empreinte_texte(*SMIC), pool, k=2)[0][1], "quasi")


def base_initiale():
    base, _ = B.migrer(data(mesure(1, *SMIC, doc="doc-a", seg="s001"),
                            mesure(2, "Autre mesure", "Créer un pôle public du médicament.", doc="doc-a", seg="s002"),
                            mesure(3, "Hors document", "Interdire les licenciements boursiers.", doc="doc-b", seg="s009")))
    return base


class IntegrationTests(unittest.TestCase):
    def test_plan_and_integration_verdicts(self):
        base = base_initiale()
        uid_smic, uid_pole, uid_b = (m["uid"] for m in base["mesures"])
        export = data(
            mesure(1, *SMIC, doc="doc-a", seg="s001"),                                            # connue
            mesure(10, "Hausse du salaire minimum", "Texte reformulé.", doc="doc-a", seg="s001", start=20),  # citation : meme
            mesure(11, *TEXTES["precis"], doc="doc-c", seg="s100"),                                # a arbitrer -> precisee
            mesure(12, *TEXTES["loin"], doc="doc-c", seg="s101"),                                  # nouvelle
            mesure(13, *TEXTES["loin"], doc="doc-c", seg="s102", start=300),                       # redite du 12 dans l'export
        )
        pre = R.plan(base, export)
        self.assertEqual({k: v["verdict"] for k, v in pre.items()},
                         {export["proposals"][1]["id"]: "meme", export["proposals"][2]["id"]: "a_arbitrer",
                          export["proposals"][3]["id"]: "nouvelle", export["proposals"][4]["id"]: "meme"})
        self.assertEqual(pre[export["proposals"][1]["id"]]["methode"], "citation")
        self.assertIn("existante", pre[export["proposals"][2]["id"]]["paire"])
        verdicts = {export["proposals"][2]["id"]: {"verdict": "precisee", "confiance": .9, "note": "date ajoutée"}}
        rapport = R.integrer(base, export, pre, verdicts)
        self.assertEqual((rapport["connues"], rapport["meme"], rapport["precisee"], rapport["nouvelles"]), (1, 2, 1, 1))
        by = {m["uid"]: m for m in base["mesures"]}
        smic = by[uid_smic]
        self.assertEqual(len(smic["versions"]), 2)
        self.assertEqual(smic["versions"][-1]["nature"], "precisee")
        self.assertIn(export["proposals"][1]["id"], smic["historique"]["alias"])
        self.assertEqual(by[uid_pole]["statut"], "non_reprise")  # doc-a couvert, mesure absente
        self.assertEqual(by[uid_b]["statut"], "active")          # doc-b non couvert
        nouvelle = [m for m in base["mesures"] if m["historique"]["corpus_id"] == export["proposals"][3]["id"]][0]
        self.assertEqual(len(nouvelle["versions"][-1]["sources"]), 2)  # la redite a rejoint la nouvelle mesure
        vues = B.calculer(base, [])
        B.construire_file(base, vues, {})
        self.assertNotIn("mesure_modifiee", {f["motif"] for f in smic["file"]})  # precisee : pas de relecture
        # Les identifiants deja vus sont reconnus au run suivant : rien de nouveau.
        self.assertEqual(R.plan(base, export), {})

    def test_uncertain_and_modified(self):
        base = base_initiale()
        uid_smic = base["mesures"][0]["uid"]
        export = data(mesure(20, *TEXTES["modif"], doc="doc-d", seg="s1"), mesure(21, *TEXTES["precis"], doc="doc-d", seg="s2"))
        pre = R.plan(base, export)
        cid_modif, cid_precis = (p["id"] for p in export["proposals"])
        verdicts = {cid_modif: {"verdict": "modifiee", "confiance": .95, "note": "montant change"},
                    cid_precis: {"verdict": "meme", "confiance": .5, "note": "hesitant"}}  # confiance basse
        R.integrer(base, export, pre, verdicts)
        by = {m["uid"]: m for m in base["mesures"]}
        incertaine = [m for m in base["mesures"] if m["historique"]["corpus_id"] == cid_precis][0]
        self.assertEqual(incertaine["rapprochement"]["etat"], "incertain")
        vues = B.calculer(base, [])
        precedent = {uid_smic: {"id": uid_smic, "c": "roussel", "t": "emploi", "title": "Hausse du SMIC", "v": {"eco": -60}}}
        B.construire_file(base, vues, precedent)
        self.assertIn("mesure_modifiee", {f["motif"] for f in by[uid_smic]["file"]})
        self.assertEqual({f["motif"] for f in incertaine["file"]} >= {"rapprochement_incertain"}, True)
        rows = {r["id"]: r for r in B.exporter(base, vues, precedent)["proposals"]}
        self.assertEqual(rows[uid_smic]["badge"], "en_revision")      # ancienne version publiee
        self.assertNotIn(incertaine["uid"], rows)                    # doublon possible : pas publie
        dec = []
        B.nouvelle_decision(dec, base, incertaine["uid"], "validation", date="2099-01-01T00:00:00+00:00")
        vues = B.calculer(base, dec)
        B.construire_file(base, vues, precedent)
        self.assertIn(incertaine["uid"], {r["id"] for r in B.exporter(base, vues, precedent)["proposals"]})

    def test_arbiter_budget_and_cache(self):
        paires = {f"p{i}": {"existante": {"title": "a"}, "nouvelle": {"title": str(i)}} for i in range(3)}
        appels = []

        def fake(req, timeout, **kw):
            lot = json.loads(json.loads(req.data)["messages"][0]["content"].split("\n")[-1])["paires"]
            appels.append(len(lot))
            content = json.dumps({"paires": [{"id": x["id"], "verdict": "meme", "confidence": .9, "note": "ok"} for x in lot]})
            return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        cache = {}
        out = R.arbitrer(paires, "m", "k", None, cache, max_cost=R.COUT_PAR_PAIRE * 2.5, taille_lot=2, appel=fake)
        self.assertEqual((appels, len(out)), ([2], 2))  # le second lot depasserait le plafond
        out = R.arbitrer(paires, "m", "k", None, cache, max_cost=1, taille_lot=2, appel=fake)
        self.assertEqual((appels, len(out)), ([2, 1], 3))  # seules les paires hors cache sont envoyees


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        B.ecrire_json(self.dir / "base_2027.json", base_initiale())
        self.export = self.dir / "export.json"
        self.export.write_text(json.dumps(data(mesure(30, *TEXTES["precis"], doc="doc-z", seg="s1"),
                                                mesure(31, *TEXTES["loin"], doc="doc-z", seg="s2"))), encoding="utf-8")

    def run_cli(self, *args):
        with mock.patch.object(sys, "argv", ["x", "--racine", str(self.dir), *args]), mock.patch("builtins.print"):
            return BO.main()

    def mesures(self):
        return B.lire_json(self.dir / "base_2027.json")["mesures"]

    def test_plan_then_no_budget_then_without_arbitration(self):
        self.assertEqual(self.run_cli("integrer", "--input", str(self.export), "--plan"), 0)
        self.assertEqual(len(self.mesures()), 3)
        self.assertEqual(self.run_cli("integrer", "--input", str(self.export)), 0)  # paire a arbitrer, pas de budget
        self.assertEqual(len(self.mesures()), 3)
        self.assertEqual(self.run_cli("integrer", "--input", str(self.export), "--sans-arbitrage"), 0)
        ms = self.mesures()
        self.assertEqual(len(ms), 5)
        self.assertEqual(sum((m.get("rapprochement") or {}).get("etat") == "incertain" for m in ms), 1)
        self.assertTrue(list((self.dir / "runs").glob("*.md")))

    def test_paid_arbitration_with_cap(self):
        def fake(req, timeout, **kw):
            lot = json.loads(json.loads(req.data)["messages"][0]["content"].split("\n")[-1])["paires"]
            content = json.dumps({"paires": [{"id": x["id"], "verdict": "precisee", "confidence": .9, "note": "ok"} for x in lot]})
            return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        with mock.patch("scoring_context_2027.request_json", side_effect=fake), \
                mock.patch("llm_logging_2027.LLMJournal") as journal, mock.patch("update_corpus_2027.journal_cost", return_value=0.0), \
                mock.patch("pipeline_scoring_2027.load_env_file"), mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "t"}):
            journal.return_value.path = self.dir / "j.jsonl"
            self.assertEqual(self.run_cli("integrer", "--input", str(self.export), "--max-cost", "0.1"), 0)
        smic = self.mesures()[0]
        self.assertEqual((len(smic["versions"]), smic["versions"][-1]["nature"]), (2, "precisee"))
        self.assertTrue(B.lire_json(self.dir / "cache_rapprochement_2027.json"))


if __name__ == "__main__":
    unittest.main()
