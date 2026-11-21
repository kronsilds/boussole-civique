import ast
import gzip
import http.client
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import serveur_constellation_2027 as SC


class ServeurConstellationTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "web").mkdir()
        (self.dir / "donnees").mkdir()
        (self.dir / "web" / "constellation_2027.html").write_text("<title>Constellation</title>", encoding="utf-8")
        (self.dir / "donnees" / "donnees_interface_2027.json").write_text('{"proposals": []}', encoding="utf-8")
        (self.dir / "donnees" / "base_2027.json").write_text("{}", encoding="utf-8")
        (self.dir / ".env").write_text("SECRET=1", encoding="utf-8")
        self.srv = SC.Serveur(("127.0.0.1", 0), SC.fabriquer_handler(self.dir))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, chemin):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1])
        c.request("GET", chemin)
        r = c.getresponse()
        out = (r.status, r.getheader("Location"), r.read())
        c.close()
        return out

    def test_burst_of_visitors_is_served(self):
        self.assertGreaterEqual(SC.Serveur.request_queue_size, 64)
        with ThreadPoolExecutor(max_workers=60) as pool:
            codes = list(pool.map(lambda _: self.get(SC.PAGE)[0], range(120)))
        self.assertEqual(codes, [200] * 120)

    def test_only_page_and_export_are_served(self):
        self.assertEqual(self.get("/")[:2], (302, SC.PAGE))
        self.assertEqual(self.get(SC.PAGE)[0], 200)
        self.assertEqual(self.get("/donnees/donnees_interface_2027.json")[2], b'{"proposals": []}')
        for chemin in ("/.env", "/donnees/base_2027.json", "/donnees/", "/web/", "/logs/", "/web/../.env",
                       "/%2e%2e/.env", "/web/constellation_2027.html/../../.env", "/boussole_2027.py"):
            with self.subTest(chemin):
                status, _, corps = self.get(chemin)
                self.assertEqual(status, 404)
                self.assertNotIn(b"SECRET", corps)

    def reponse(self, chemin, entetes):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1])
        c.request("GET", chemin, headers=entetes)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def test_compression_and_revalidation(self):
        chemin = "/donnees/donnees_interface_2027.json"
        status, h, corps = self.reponse(chemin, {"Accept-Encoding": "br, gzip"})
        self.assertEqual((status, h["Content-Encoding"], h["Vary"]), (200, "gzip", "Accept-Encoding"))
        self.assertEqual(gzip.decompress(corps), b'{"proposals": []}')
        status, h2, corps = self.reponse(chemin, {"Accept-Encoding": "gzip", "If-None-Match": h["ETag"]})
        self.assertEqual((status, corps), (304, b""))
        status, h3, corps = self.reponse(chemin, {"Accept-Encoding": "gzip;q=0"})
        self.assertEqual((status, corps), (200, b'{"proposals": []}'))
        self.assertNotIn("Content-Encoding", h3)
        self.assertNotEqual(h3["ETag"], h["ETag"])

    def test_changed_file_is_published_again(self):
        chemin = "/donnees/donnees_interface_2027.json"
        etag = self.reponse(chemin, {})[1]["ETag"]
        (self.dir / "donnees" / "donnees_interface_2027.json").write_text('{"proposals": [1, 2]}', encoding="utf-8")
        status, _, corps = self.reponse(chemin, {"If-None-Match": etag})
        self.assertEqual((status, corps), (200, b'{"proposals": [1, 2]}'))

    def test_security_headers(self):
        _, h, _ = self.reponse(SC.PAGE, {})
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertEqual(h["Server"].split()[0], "Boussole")
        self.assertNotIn("Python", h["Server"])


class AdresseClientTests(unittest.TestCase):
    def test_forwarded_address_is_trusted_only_behind_local_proxy(self):
        self.assertEqual(SC.adresse_client("127.0.0.1", "203.0.113.9", True), "203.0.113.9")
        self.assertEqual(SC.adresse_client("127.0.0.1", "1.1.1.1, 203.0.113.9", True), "203.0.113.9")  # valeur du proxy
        self.assertEqual(SC.adresse_client("127.0.0.1", "203.0.113.9", False), "127.0.0.1")
        self.assertEqual(SC.adresse_client("198.51.100.7", "203.0.113.9", True), "198.51.100.7")  # pas le proxy local
        self.assertEqual(SC.adresse_client("127.0.0.1", "n'importe quoi", True), "127.0.0.1")
        self.assertEqual(SC.adresse_client("127.0.0.1", None, True), "127.0.0.1")

    def test_ipv6_is_grouped_by_network(self):
        a = SC.adresse_client("127.0.0.1", "2001:db8:1:2:aaaa::1", True)
        self.assertEqual(a, SC.adresse_client("127.0.0.1", "2001:db8:1:2:bbbb::2", True))
        self.assertNotEqual(a, SC.adresse_client("127.0.0.1", "2001:db8:1:3::1", True))
        self.assertEqual(SC.adresse_client("127.0.0.1", "::ffff:203.0.113.9", True), "203.0.113.9")


class ModulesEnLigneTests(unittest.TestCase):
    def test_online_server_needs_no_pipeline_module(self):
        racine = Path(SC.__file__).parent
        for nom, permis in (("serveur_constellation_2027.py", {"contributions_2027"}), ("contributions_2027.py", set())):
            arbre = ast.parse((racine / nom).read_text(encoding="utf-8"))
            modules = {a.name for n in arbre.body if isinstance(n, ast.Import) for a in n.names}
            modules |= {n.module for n in arbre.body if isinstance(n, ast.ImportFrom)}
            self.assertEqual({m for m in modules if m.endswith("_2027")}, permis, nom)


if __name__ == "__main__":
    unittest.main()
