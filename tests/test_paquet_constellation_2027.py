import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import paquet_constellation_2027 as P

PAGE = '<link rel="canonical" href="https://exemple.fr/"><h2>Mentions légales</h2><p>Hébergeur : exemple</p>'


class PaquetTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for f, texte in (("serveur_constellation_2027.py", "# s"), ("contributions_2027.py", "# c"),
                         ("web/constellation_2027.html", PAGE), ("web/partage_2027.png", "png"),
                         ("donnees/donnees_interface_2027.json", json.dumps({"meta": {"genere_le": "2026-11-23T21:16:00+00:00"}, "proposals": [{"id": "m"}], "candidates": [{"id": "c"}]})),
                         ("donnees/sources_2027.json", json.dumps({"ajouts": [{"url": "https://exemple.fr/a", "note": "interne"},
                                                                              {"url": "file:///D:/depot.pdf"}]})),
                         (".env", "SECRET=1"), ("donnees/base_2027.json", "{}"), ("donnees/cache_lecture_q2_2027.json", "{}")):
            (self.dir / f).parent.mkdir(parents=True, exist_ok=True)
            (self.dir / f).write_text(texte, encoding="utf-8")

    def test_only_listed_files_are_packaged(self):
        self.assertEqual(P.controler(self.dir), [])
        sortie = self.dir / P.SORTIE
        (sortie).mkdir(parents=True)
        (sortie / "ancien.txt").write_text("x", encoding="utf-8")
        publies = P.construire(self.dir, sortie)
        trouves = sorted(f.relative_to(sortie).as_posix() for f in sortie.rglob("*") if f.is_file())
        self.assertEqual(trouves, sorted([*publies, "SHA256SUMS"]))
        self.assertEqual(json.loads((sortie / P.SOURCES).read_text(encoding="utf-8")), {"ajouts": [{"url": "https://exemple.fr/a"}]})
        lignes = (sortie / "SHA256SUMS").read_bytes().decode("ascii").splitlines()
        self.assertEqual(len(lignes), len(publies))
        for ligne in lignes:
            empreinte, f = ligne.split("  ")
            self.assertEqual(hashlib.sha256((sortie / f).read_bytes()).hexdigest(), empreinte)

    def test_robots_and_sitemap_follow_canonical_address(self):
        sortie = self.dir / P.SORTIE
        self.assertIn(P.PLAN_SITE, P.construire(self.dir, sortie))
        self.assertIn("Sitemap: https://exemple.fr/sitemap.xml", (sortie / P.ROBOTS).read_text(encoding="utf-8"))
        self.assertIn("<loc>https://exemple.fr/</loc><lastmod>2026-11-23</lastmod>",
                      (sortie / P.PLAN_SITE).read_text(encoding="utf-8"))

    def test_canonical_address_is_required_except_for_a_trial(self):
        (self.dir / "web/constellation_2027.html").write_text(PAGE.split(">", 1)[1], encoding="utf-8")
        self.assertTrue(any("canonique" in e for e in P.controler(self.dir)))
        self.assertEqual(P.controler(self.dir, essai=True), [])
        self.assertNotIn(P.ROBOTS, P.construire(self.dir, self.dir / P.SORTIE))

    def test_legal_notice_is_required_except_for_a_trial(self):
        (self.dir / "web/constellation_2027.html").write_text("<p>page</p>", encoding="utf-8")
        self.assertTrue(any("Mentions legales" in e for e in P.controler(self.dir)))
        self.assertEqual(P.controler(self.dir, essai=True), [])

    def test_unfilled_legal_notice_is_refused(self):
        (self.dir / "web/constellation_2027.html").write_text(PAGE + "<p>[À COMPLÉTER : contact]</p>", encoding="utf-8")
        self.assertTrue(any("incompletes" in e for e in P.controler(self.dir)))
        self.assertEqual(P.controler(self.dir, essai=True), [])

    def test_secrets_local_paths_and_empty_export_are_refused(self):
        export = self.dir / "donnees/donnees_interface_2027.json"
        for contenu, attendu in (({"proposals": [{"url": "file:///D:/x.pdf"}], "candidates": [1]}, "file://"),
                                 ({"proposals": [{"k": "sk-or-v1-abcdef1234"}], "candidates": [1]}, "cle OpenRouter"),
                                 ({"proposals": [], "candidates": []}, "Export vide")):
            export.write_text(json.dumps(contenu), encoding="utf-8")
            with self.subTest(attendu):
                self.assertTrue(any(attendu in e for e in P.controler(self.dir)))
        export.write_text("{", encoding="utf-8")
        self.assertTrue(any("illisible" in e for e in P.controler(self.dir)))
        export.unlink()
        self.assertTrue(any("manquant" in e for e in P.controler(self.dir)))


if __name__ == "__main__":
    unittest.main()
