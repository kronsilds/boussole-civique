import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
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
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), SC.fabriquer_handler(self.dir))
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


if __name__ == "__main__":
    unittest.main()
