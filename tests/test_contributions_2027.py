import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import base_2027 as B
import contributions_2027 as CT
import serveur_constellation_2027 as SC
from test_base_2027 import data, prop


class ValidationTests(unittest.TestCase):
    def test_accepted_and_refused_entries(self):
        e = CT.valider({"url": "https://exemple.fr/programme.pdf", "candidate_id": "roussel", "type": "programme",
                        "titre": "  Programme   complet ", "date": "2026-11-01", "note": ""}, {"roussel"})
        self.assertEqual(e, {"url": "https://exemple.fr/programme.pdf", "candidate_id": "roussel", "type": "programme",
                             "titre": "Programme complet", "date": "2026-11-01", "note": None})
        refus = [{"url": "ftp://exemple.fr/a"}, {"url": "javascript:alert(1)"}, {"url": "https://127.0.0.1/a"},
                 {"url": "http://[::1]/a"}, {"url": "https://user:mdp@exemple.fr/"}, {"url": "http://localhost/a"},
                 {"url": "https://intranet/a"}, {"url": "https://exemple.fr/a b"}, {},
                 {"url": "https://exemple.fr/a", "candidate_id": "inconnu"}, {"url": "https://exemple.fr/a", "type": "x"},
                 {"url": "https://exemple.fr/a", "date": "01/11/2026"}, {"url": "https://exemple.fr/a", "note": "x" * 1001},
                 {"url": ["https://exemple.fr/a"]}]
        for corps in refus:
            with self.subTest(corps=str(corps)[:60]):
                with self.assertRaises(ValueError):
                    CT.valider(corps, {"roussel"})

    def test_url_key_ignores_www_fragment_and_trailing_slash(self):
        self.assertEqual(CT.normaliser_url("https://www.Exemple.fr/prog/#page=3"), CT.normaliser_url("http://exemple.fr/prog"))
        self.assertNotEqual(CT.normaliser_url("https://exemple.fr/a?x=1"), CT.normaliser_url("https://exemple.fr/a"))


class DepotTests(unittest.TestCase):
    def setUp(self):
        self.f = Path(tempfile.mkdtemp()) / "donnees" / "contributions_2027.json"

    def entree(self, url):
        return CT.valider({"url": url}, set())

    def test_deposit_dedupe_and_processing(self):
        a = CT.deposer(self.f, self.entree("https://exemple.fr/a"))
        b = CT.deposer(self.f, self.entree("https://exemple.fr/b"))
        self.assertEqual((a["id"], b["id"], a["statut"]), ("c-0001", "c-0002", "en_attente"))
        with self.assertRaises(ValueError):
            CT.deposer(self.f, self.entree("https://www.exemple.fr/a/"))  # meme lien
        with self.assertRaises(ValueError):
            CT.deposer(self.f, self.entree("https://exemple.fr/corpus"), {CT.normaliser_url("https://exemple.fr/corpus")})
        CT.traiter(self.f, "c-0001", "acceptee", source_id="s-0009")
        CT.traiter(self.f, "c-0002", "refusee", motif="hors sujet")
        items = {c["id"]: c for c in CT.lire(self.f)["contributions"]}
        self.assertEqual((items["c-0001"]["statut"], items["c-0001"]["source_id"]), ("acceptee", "s-0009"))
        self.assertEqual((items["c-0002"]["statut"], items["c-0002"]["motif"]), ("refusee", "hors sujet"))
        with self.assertRaises(ValueError):
            CT.traiter(self.f, "c-0001", "refusee", motif="x")  # deja traitee
        with self.assertRaises(KeyError):
            CT.traiter(self.f, "c-0404", "refusee")
        self.assertFalse(self.f.with_name(self.f.name + ".lock").exists())

    def test_pending_cap(self):
        CT.B.ecrire_json(self.f, {"contributions": [{"id": f"c-{i:04d}", "url": f"https://exemple.fr/{i}", "statut": "en_attente"}
                                                    for i in range(1, CT.MAX_EN_ATTENTE + 1)]})
        with self.assertRaises(RuntimeError):
            CT.deposer(self.f, self.entree("https://exemple.fr/nouveau"))


class ServeurContributionsTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "web").mkdir()
        (self.dir / "web" / "constellation_2027.html").write_text("<title>C</title>", encoding="utf-8")
        B.ecrire_json(self.dir / SC.EXPORT, {"candidates": [{"id": "roussel"}], "proposals": [],
                                             "sources": [{"id": "d1", "c": "roussel", "url": "https://deja.fr/programme.pdf"}]})
        self.serveurs = []

    def tearDown(self):
        for s in self.serveurs:
            s.shutdown()
            s.server_close()

    def lancer(self, contributions=True):
        s = ThreadingHTTPServer(("127.0.0.1", 0), SC.fabriquer_handler(self.dir, contributions))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.serveurs.append(s)
        return s.server_address[1]

    def requete(self, port, methode, chemin, corps=None, entetes=None):
        c = http.client.HTTPConnection("127.0.0.1", port)
        c.request(methode, chemin, body=json.dumps(corps).encode() if corps is not None else None,
                  headers=entetes if entetes is not None else {"Content-Type": "application/json", "X-Boussole": "1"})
        r = c.getresponse()
        out = r.status, json.loads(r.read() or b"{}")
        c.close()
        return out

    def stockees(self):
        return CT.lire(self.dir / SC.CONTRIBUTIONS)["contributions"]

    def test_deposit_flow(self):
        port = self.lancer()
        self.assertEqual(self.requete(port, "GET", "/api/contributions")[1]["ouvertes"], True)
        status, r = self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/a"},
                                 {"Content-Type": "application/json"})
        self.assertEqual(status, 403)  # sans l'en-tete de la page
        status, r = self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/a"},
                                 {"Content-Type": "text/plain", "X-Boussole": "1"})
        self.assertEqual(status, 403)
        status, r = self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/a", "candidate_id": "roussel",
                                                                     "titre": "Livret"})
        self.assertEqual((status, r["id"]), (200, "c-0001"))
        self.assertEqual(self.requete(port, "POST", "/api/contribution", {"url": "https://deja.fr/programme.pdf"})[0], 400)
        self.assertEqual(self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/a"})[0], 400)  # doublon
        self.assertEqual(self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/z", "candidate_id": "x"})[0], 400)
        status, r = self.requete(port, "POST", "/api/contribution", {"url": "https://robot.fr/", "site_web": "spam"})
        self.assertEqual((status, r), (200, {"ok": True}))  # champ piege : reponse normale, rien d'enregistre
        self.assertEqual([c["url"] for c in self.stockees()], ["https://exemple.fr/a"])
        self.assertNotIn("ip", json.dumps(self.stockees()))
        self.assertEqual(self.requete(port, "POST", "/api/autre", {"url": "https://exemple.fr/b"})[0], 404)

    def test_rate_limit(self):
        port = self.lancer()
        codes = [self.requete(port, "POST", "/api/contribution", {"url": f"https://exemple.fr/{i}"})[0] for i in range(7)]
        self.assertEqual(codes, [200] * 5 + [429] * 2)

    def test_closed(self):
        port = self.lancer(contributions=False)
        self.assertEqual(self.requete(port, "GET", "/api/contributions")[1]["ouvertes"], False)
        self.assertEqual(self.requete(port, "POST", "/api/contribution", {"url": "https://exemple.fr/a"})[0], 404)
        self.assertFalse((self.dir / SC.CONTRIBUTIONS).exists())


class RecapSourcesTests(unittest.TestCase):
    def test_counts_per_document_and_local_links_hidden(self):
        def avec_doc(p, *docs):
            p["source_evidence"] = [{**p["source_evidence"][0], "document_id": d, "source_url": "u"} for d in docs]
            return p
        base, _ = B.migrer(data(avec_doc(prop(1), "d1"), avec_doc(prop(2), "d1", "d2"), avec_doc(prop(3, cand="le-pen"), "d3")))
        base["mesures"][2]["proposition"]["source_url"] = "file:///D:/secret/depot.pdf"
        manifeste = {"documents": {
            "d1": {"id": "d1", "url": "https://a.fr/p.pdf", "status": "ready", "format": "pdf",
                   "bindings": [{"candidate_id": "roussel", "role": "thematic", "title": "Partie"},
                                {"candidate_id": "roussel", "role": "programme", "title": "Programme", "published_date": "2026-10-01"}]},
            "d2": {"id": "d2", "url": "https://a.fr/t", "status": "ready", "bindings": [{"candidate_id": "roussel", "title": "Tribune"}]},
            "d3": {"id": "d3", "url": "file:///D:/secret/depot.pdf", "status": "ready", "bindings": [{"candidate_id": "le-pen"}]},
            "d4": {"id": "d4", "url": "https://a.fr/404", "status": "error", "bindings": [{"candidate_id": "le-pen"}]}}}
        vues = B.calculer(base, [])
        precedent = {}
        export = B.exporter(base, vues, precedent, manifeste=manifeste,
                            ajouts=[{"candidate_id": "roussel", "url": "https://b.fr", "statut": "en_attente", "titre": "T"},
                                    {"candidate_id": "roussel", "url": "https://c.fr", "statut": "traitee"}])
        docs = {d["id"]: d for d in export["sources"]}
        self.assertEqual((docs["d1"]["titre"], docs["d1"]["date"], docs["d1"]["ext"], docs["d1"]["n"]), ("Programme", "2026-10-01", 2, 2))
        self.assertEqual((docs["d2"]["ext"], docs["d3"]["ext"], docs["d4"]["ext"], docs["d4"]["statut"]), (1, 1, 0, "error"))
        self.assertEqual((docs["d3"]["url"], docs["d3"]["depot"]), (None, True))
        self.assertNotIn("file://", json.dumps(export))
        self.assertEqual([a["url"] for a in export["sources_en_attente"]], ["https://b.fr"])
        self.assertIn("notation", export["meta"]["modeles"])
        self.assertNotIn("sources", B.exporter(base, vues, precedent))  # sans manifeste : pas de recapitulatif


if __name__ == "__main__":
    unittest.main()
