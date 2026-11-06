import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import base_2027 as B
import boussole_2027 as BO
import tableau_de_bord_2027 as TB
from test_base_2027 import data, prop


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base, _ = B.migrer(data(prop(1, descripteurs=True), prop(2, title="Hausse du SMIC à 1600 euros"), prop(3, cand="le-pen")))
        base, _ = B.migrer(data(prop(1, descripteurs=True), prop(2, title="Hausse du SMIC à 1600 euros"),
                                prop(3, cand="le-pen"), prop(4, title="Hausse du SMIC à 1700 euros")), base=base)
        B.ecrire_json(self.dir / "base_2027.json", base)
        BO.executer(BO.chemins(type("A", (), {"racine": str(self.dir)})()), list(BO.ETAPES_GRATUITES))
        self.etat = TB.Etat(self.dir)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TB.fabriquer_handler(self.etat, Path(TB.__file__).with_name(TB.PAGE)))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.url + path) as r:
            return json.loads(r.read())

    def post(self, path, body, header=True):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-Boussole": "1"} if header else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_page_state_and_queue(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn("Boussole", r.read().decode("utf-8"))
        e = self.get("/api/etat")
        self.assertEqual(e["mesures"], {"active": 4})
        self.assertEqual(e["file"].get("nouvelle_mesure"), 1)
        f = self.get("/api/file?motif=nouvelle_mesure")
        self.assertEqual([m["uid"] for m in f["items"]], ["m-roussel-0003"])
        self.assertEqual(self.get("/api/mesures?q=1600")["total"], 1)
        self.assertIn("levier", self.get("/api/questions")["questions"])

    def test_fiche_with_neighbours_and_correction(self):
        fiche = self.get("/api/mesure/m-roussel-0002")
        self.assertEqual(fiche["voisins"][0]["uid"], "m-roussel-0003")  # 1600 / 1700 euros : la plus proche
        status, _ = self.post("/api/decision", {"uid": "m-roussel-0001", "type": "validation"}, header=False)
        self.assertEqual(status, 403)  # sans l'en-tete de la page
        before = self.get("/api/mesure/m-roussel-0001")["axes"]["eco"]
        status, r = self.post("/api/decision", {"uid": "m-roussel-0001", "type": "correction", "champ": "eco_distrib",
                                                "valeur": "neutre"})
        self.assertEqual(status, 200)
        self.assertNotEqual(r["fiche"]["axes"]["eco"], before)
        self.assertEqual(r["fiche"]["annotation"]["corrigees"], ["eco_distrib"])
        self.assertEqual(len(B.lire_json(self.dir / "decisions_2027.json")), 1)
        status, r = self.post("/api/decision", {"uid": "m-roussel-0003", "type": "validation"})
        self.assertEqual(r["fiche"]["file"], [])  # sort de la file tout de suite
        status, r = self.post("/api/decision", {"uid": "m-roussel-0001", "type": "rejet"})
        self.assertEqual(status, 400)  # motif requis
        self.assertEqual(self.get("/api/etat")["decisions_non_appliquees"], 2)

    def test_add_sources(self):
        status, s = self.post("/api/source", {"candidate_id": "roussel", "type": "entretien", "url": "https://exemple.fr/a",
                                              "date": "2026-11-12", "titre": "Entretien"})
        self.assertEqual((status, s["statut"], s["id"]), (200, "en_attente", "s-0001"))
        status, _ = self.post("/api/source", {"candidate_id": "roussel", "type": "entretien", "url": "https://exemple.fr/a"})
        self.assertEqual(status, 400)  # doublon
        status, _ = self.post("/api/source", {"candidate_id": "inconnu", "type": "entretien", "url": "https://x.fr"})
        self.assertEqual(status, 400)
        contenu = base64.b64encode(b"%PDF-1.4 test").decode()
        status, s = self.post("/api/source", {"candidate_id": "le-pen", "type": "programme",
                                              "fichier": {"nom": "../../prog.pdf", "base64": contenu}})
        self.assertEqual(status, 200)
        self.assertTrue((self.dir / s["fichier"]).exists())
        self.assertTrue(s["fichier"].startswith("corpus_programmes/depots/"))  # nom de fichier assaini
        status, _ = self.post("/api/source", {"candidate_id": "le-pen", "type": "programme",
                                              "fichier": {"nom": "x.exe", "base64": contenu}})
        self.assertEqual(status, 400)
        self.assertEqual(len(self.get("/api/sources")["ajouts"]), 2)

    def test_free_update_job_applies_decisions(self):
        self.post("/api/decision", {"uid": "m-roussel-0003", "type": "rejet", "motif": "doublon"})
        status, job = self.post("/api/mise-a-jour", {})
        self.assertEqual(status, 200)
        for _ in range(100):
            job = self.get("/api/job")
            if job["etat"] != "en_cours":
                break
            time.sleep(.05)
        self.assertEqual(job["etat"], "termine")
        export = B.lire_json(self.dir / "donnees_interface_2027.json")
        self.assertNotIn("m-roussel-0003", {r["id"] for r in export["proposals"]})
        self.assertEqual(self.get("/api/etat")["mesures"].get("rejetee"), 1)

    def test_writes_refused_while_run_in_progress(self):
        (self.dir / ".boussole.lock").write_text("1", encoding="utf-8")
        status, r = self.post("/api/decision", {"uid": "m-roussel-0001", "type": "validation"})
        self.assertEqual(status, 409)


if __name__ == "__main__":
    unittest.main()
