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
from test_base_2027 import annoter, data, prop


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base, _ = B.migrer(data(prop(1), prop(2, title="Hausse du SMIC à 1600 euros"), prop(3, cand="le-pen")))
        base = annoter(base, 1)
        base, _ = B.migrer(data(prop(1), prop(2, title="Hausse du SMIC à 1600 euros"),
                                prop(3, cand="le-pen"), prop(4, title="Hausse du SMIC à 1700 euros")), base=base)
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)
        BO.executer(BO.chemins(type("A", (), {"racine": str(self.dir)})()), list(BO.ETAPES_GRATUITES))
        self.etat = TB.Etat(self.dir)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TB.fabriquer_handler(self.etat, TB.PAGE))
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
        self.assertEqual(len(B.lire_json(self.dir / "donnees" / "decisions_2027.json")), 1)
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
        export = B.lire_json(self.dir / "donnees" / "donnees_interface_2027.json")
        self.assertNotIn("m-roussel-0003", {r["id"] for r in export["proposals"]})
        self.assertEqual(self.get("/api/etat")["mesures"].get("rejetee"), 1)

    def test_writes_refused_while_run_in_progress(self):
        (self.dir / ".boussole.lock").write_text("1", encoding="utf-8")
        status, r = self.post("/api/decision", {"uid": "m-roussel-0001", "type": "validation"})
        self.assertEqual(status, 409)


class ReseauTests(unittest.TestCase):
    """Mode reseau : une autre machine (en-tete Host non local) n'entre qu'avec le jeton, puis le cookie."""
    JETON = "j" * 24

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base = annoter(B.migrer(data(prop(1), prop(2)))[0], 1)
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)
        BO.executer(BO.chemins(type("A", (), {"racine": str(self.dir)})()), list(BO.ETAPES_GRATUITES))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TB.fabriquer_handler(TB.Etat(self.dir), TB.PAGE, self.JETON))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, methode, chemin, hote="192.168.1.20", cookie=None, corps=None, entete=True):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = {"Host": f"{hote}:{self.port}"}
        if cookie:
            h["Cookie"] = f"{TB.COOKIE}={cookie}"
        if corps is not None:
            h.update({"Content-Type": "application/json", **({"X-Boussole": "1"} if entete else {})})
        c.request(methode, chemin, body=json.dumps(corps) if corps is not None else None, headers=h)
        r = c.getresponse()
        out = (r.status, r.getheader("Set-Cookie"), r.read())
        c.close()
        return out

    def test_token_cookie_flow(self):
        self.assertEqual(self.req("GET", "/")[0], 403)
        self.assertEqual(self.req("GET", "/api/etat")[0], 403)
        self.assertEqual(self.req("GET", "/?jeton=mauvais")[0], 403)
        status, cookie, _ = self.req("GET", "/?jeton=" + self.JETON)
        self.assertEqual(status, 303)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        status, _, corps = self.req("GET", "/api/etat", cookie=self.JETON)
        self.assertEqual(status, 200)
        self.assertNotIn("acces_reseau", json.loads(corps))  # lien montre a l'ordinateur seulement
        self.assertEqual(self.req("GET", "/api/etat", cookie="faux")[0], 403)
        decision = {"uid": "m-roussel-0002", "type": "validation"}
        self.assertEqual(self.req("POST", "/api/decision", cookie=self.JETON, corps=decision, entete=False)[0], 403)
        self.assertEqual(self.req("POST", "/api/decision", corps=decision)[0], 403)
        self.assertEqual(self.req("POST", "/api/decision", cookie=self.JETON, corps=decision)[0], 200)
        status, _, corps = self.req("GET", "/api/etat", hote="127.0.0.1")  # l'ordinateur : sans jeton, lien affiche
        self.assertEqual(status, 200)
        self.assertIn("acces_reseau", json.loads(corps))

    def test_token_kept_between_runs(self):
        j = TB.jeton_acces(self.dir)
        self.assertEqual(TB.jeton_acces(self.dir), j)
        self.assertNotEqual(TB.jeton_acces(self.dir, nouveau=True), j)
        self.assertGreaterEqual(len(j), 20)


if __name__ == "__main__":
    unittest.main()
