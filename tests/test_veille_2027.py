import tempfile
import unittest
from pathlib import Path

import base_2027 as B
import registre_2027 as R
import veille_2027 as V

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Site</title>
<item><title>Plan pauvrete</title><link>https://a.example/plan-pauvrete/</link><pubDate>Mon, 16 Nov 2026 10:00:00 +0000</pubDate></item>
<item><title>Vieux texte</title><link>https://a.example/vieux/</link><pubDate>Mon, 02 Mar 2026 10:00:00 +0000</pubDate></item>
<item><title>Programme</title><link>https://a.example/programme</link><pubDate>Mon, 16 Nov 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>F</title>
<entry><title>Entretien</title><link rel="alternate" href="https://a.example/entretien"/><published>2026-11-18T08:00:00Z</published></entry>
</feed>"""

INDEX = b"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://b.example/pages.xml</loc><lastmod>2026-11-19</lastmod></sitemap></sitemapindex>"""

PAGES = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://b.example/actualites/a</loc><lastmod>2026-11-19</lastmod></url>
<url><loc>https://b.example/mentions</loc><lastmod>2026-11-19</lastmod></url></urlset>"""


class FluxTests(unittest.TestCase):
    def test_rss_et_atom(self):
        items = V.lire_rss(RSS)
        self.assertEqual([x["date"] for x in items], ["2026-11-16", "2026-03-02", "2026-11-16"])
        self.assertEqual(V.lire_rss(ATOM), [{"url": "https://a.example/entretien", "titre": "Entretien", "date": "2026-11-18"}])

    def test_rss_invalide_lu_par_le_repli(self):
        casse = b"<rss><channel><item><title><![CDATA[Communique]]></title><link>https://a.example/c</link>" \
                b"<pubDate>Tue, 17 Nov 2026 10:00:00 +0000</pubDate><dc:creator>x</dc:creator></item></channel></rss>"
        self.assertEqual(V.lire_rss(casse), [{"url": "https://a.example/c", "titre": "Communique", "date": "2026-11-17"}])

    def test_index_de_sitemaps_et_filtre(self):
        pages = {"https://b.example/sitemap.xml": INDEX, "https://b.example/pages.xml": PAGES}
        nature, items = V.relever_flux({"type": "sitemap", "url": "https://b.example/sitemap.xml", "filtre": "/actualites/"},
                                       pages.__getitem__)
        self.assertEqual((nature, [x["url"] for x in items]), ("sitemap", ["https://b.example/actualites/a"]))

    def test_le_contenu_decide_de_la_nature(self):
        nature, items = V.relever_flux({"type": "sitemap", "url": "https://a.example/rss.xml"}, lambda u: RSS)
        self.assertEqual((nature, len(items)), ("rss", 3))


class ReleveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.c = {"candidats": d / "candidats_2027.json", "themes": d / "themes_2027.json", "veille": d / "veille_2027.json",
                  "sources": d / "sources_2027.json", "amont": d / "amont"}
        B.ecrire_json(self.c["themes"], {"format": 1, "themes": [{"id": "sante", "label": "Sante"}]})
        B.ecrire_json(self.c["candidats"], {"format": 1, "meta": {}, "journal": [], "candidates": [
            {"id": "alpha", "status": "declare", "program": {"main_url": "https://a.example/programme", "thematic_links": []},
             "veille": [{"type": "rss", "url": "https://a.example/feed"}, {"type": "sitemap", "url": "https://b.example/sitemap.xml"}]},
            {"id": "beta", "status": "declare", "program": {}, "veille": [{"type": "rss", "url": "https://c.example/feed"}]}]})
        self.pages = {"https://a.example/feed": RSS, "https://b.example/sitemap.xml": INDEX, "https://b.example/pages.xml": PAGES}

    def tearDown(self):
        self.tmp.cleanup()

    def lire(self, url):
        if url not in self.pages:
            raise OSError("hors ligne")
        return self.pages[url]

    def releve(self, **kw):
        return V.releve(self.c, lire=self.lire, aujourd_hui="2026-11-21", **kw)

    def test_premier_releve_puis_nouveautes(self):
        b = self.releve()
        # Premier releve : seul l'article RSS recent entre ; le programme est deja connu, le sitemap sert de reference.
        etat = V.lire_etat(self.c["veille"])
        self.assertEqual([e["url"] for e in etat["elements"]], ["https://a.example/plan-pauvrete/"])
        self.assertEqual((b["flux"], b["nouveaux"], len(b["erreurs"])), (3, 1, 1))  # c.example hors ligne
        self.assertIn("erreur", etat["flux"]["beta|https://c.example/feed"]["statut"])
        # Second releve : une page nouvelle du sitemap (quelle que soit sa date) et un doublon de titre ecarte.
        self.pages["https://b.example/pages.xml"] = PAGES.replace(
            b"</urlset>", b"<url><loc>https://b.example/actualites/b</loc></url></urlset>")
        self.pages["https://a.example/feed"] = RSS.replace(b"</channel>", b"<item><title>Plan pauvrete</title>"
                                                          b"<link>https://parti.example/plan-pauvrete</link></item></channel>")
        b = self.releve()
        urls = [e["url"] for e in V.lire_etat(self.c["veille"])["elements"]]
        self.assertEqual(urls, ["https://a.example/plan-pauvrete/", "https://b.example/actualites/b"])
        self.assertEqual(b["nouveaux"], 1)
        self.assertEqual(self.releve()["nouveaux"], 0)

    def test_traiter(self):
        self.releve()
        with self.assertRaisesRegex(ValueError, "Motif"):
            V.traiter(self.c, "v-0001", "ignoree")
        e = V.traiter(self.c, "v-0001", "ajoutee", source_id="s-0009")
        self.assertEqual((e["statut"], e["source_id"]), ("ajoutee", "s-0009"))
        self.assertEqual(V.en_attente(self.c), {})
        with self.assertRaisesRegex(ValueError, "Deja"):
            V.traiter(self.c, "v-0001", "ignoree", motif="doublon")

    def test_candidat_retire_non_releve_et_retrait(self):
        R.retrait(self.c, "alpha", "2026-12-13", "https://a.example/retrait", soutien="beta", note="ralliement")
        b = self.releve()
        self.assertEqual((b["ignores_retires"], b["flux"]), (["alpha"], 1))
        registre, _ = R.lire_registre(self.c)
        alpha = registre["candidates"][0]
        self.assertEqual((alpha["status"], alpha["retrait"]["soutien"], alpha["retrait"]["statut_avant"]),
                         ("retire", "beta", "declare"))
        with self.assertRaisesRegex(ValueError, "deja retire"):
            R.retrait(self.c, "alpha", "2026-12-13", "https://a.example/retrait")
        R.retrait(self.c, "alpha", annuler=True)
        registre, _ = R.lire_registre(self.c)
        self.assertEqual(registre["candidates"][0]["status"], "declare")
        self.assertNotIn("retrait", registre["candidates"][0])
        self.assertEqual([j["action"] for j in registre["journal"]], ["retrait", "retrait_annule"])

    def test_retrait_valide_ses_champs(self):
        with self.assertRaisesRegex(ValueError, "Date"):
            R.retrait(self.c, "alpha", "13/12/2026", "https://a.example/r")
        with self.assertRaisesRegex(ValueError, "URL"):
            R.retrait(self.c, "alpha", "2026-12-13", None)
        with self.assertRaisesRegex(ValueError, "soutenu"):
            R.retrait(self.c, "alpha", "2026-12-13", "https://a.example/r", soutien="alpha")
        with self.assertRaisesRegex(ValueError, "inconnu"):
            R.retrait(self.c, "zeta", "2026-12-13", "https://a.example/r")


class AjoutEtExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.c = {"candidats": d / "candidats_2027.json", "themes": d / "themes_2027.json"}
        B.ecrire_json(self.c["themes"], {"format": 1, "themes": [{"id": "sante", "label": "Sante"}]})
        B.ecrire_json(self.c["candidats"], {"format": 1, "journal": [], "candidates": [{"id": "alpha", "status": "declare"}],
                                            "meta": {"other_declared": [{"name": "Clára Égger", "programme_recherche": {"resultat": "programme"}},
                                                                        {"name": "Autre Nom"}]}})
        self.fiche = {"id": "egger", "first_name": "Clara", "last_name": "Egger", "party": "SD", "party_short": "SD",
                      "status": "declare", "color": "#0891B2", "status_source_url": "https://e.example/annonce",
                      "program": {"main_url": "https://e.example/programme.pdf",
                                  "thematic_links": [{"theme": "sante", "url": "https://e.example/sante"}]}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_ajouter_candidat(self):
        self.assertEqual(R.ajouter_candidat(self.c, [self.fiche], "decision"), ["egger"])
        registre, _ = R.lire_registre(self.c)
        egger = registre["candidates"][1]
        self.assertEqual((egger["origine"], egger["programme_recherche"]["resultat"]), ("registre", "programme"))
        self.assertEqual([o["name"] for o in registre["meta"]["other_declared"]], ["Autre Nom"])
        self.assertEqual(registre["journal"][-1]["action"], "candidat_ajoute")
        with self.assertRaisesRegex(ValueError, "deja present"):
            R.ajouter_candidat(self.c, [self.fiche])
        # un candidat ajoute localement n'est pas signale comme absent de l'amont
        self.assertEqual([e["candidat"] for e in R.ecarts(registre, {"themes": [{"id": "sante", "label": "Sante"}]},
                                                          {"themes": [{"id": "sante", "label": "Sante"}], "candidates": []})],
                         ["alpha"])

    def test_ajouter_verifie_avant_d_ecrire(self):
        mauvais = {**self.fiche, "id": "zeta", "program": {"main_url": "https://e.example/p", "thematic_links": [{"theme": "inconnu", "url": "https://e.example/x"}]}}
        with self.assertRaisesRegex(ValueError, "themes inconnus"):
            R.ajouter_candidat(self.c, [self.fiche, mauvais])
        with self.assertRaisesRegex(ValueError, "couleur"):
            R.ajouter_candidat(self.c, [{**self.fiche, "color": "vert"}])
        registre, _ = R.lire_registre(self.c)
        self.assertEqual(len(registre["candidates"]), 1)  # rien n'a ete ecrit

    def test_statut_et_retrait_exportes(self):
        import export_interface_2027 as EI
        R.ajouter_candidat(self.c, [self.fiche])
        R.retrait(self.c, "alpha", "2026-12-13", "https://a.example/r", soutien="egger", note="interne")
        base = {"candidates": [{"id": "alpha", "status": "declare", "name": "A"}, {"id": "egger", "status": "declare", "name": "E"}]}
        B.statuts_du_registre(base, B.lire_json(self.c["candidats"], {}))
        export = EI.export({**base, "proposals": []}, None)["candidates"]
        self.assertEqual(export[0]["status"], "retire")
        self.assertEqual(export[0]["retrait"], {"date": "2026-12-13", "soutien": "egger", "source_url": "https://a.example/r"})
        self.assertNotIn("retrait", export[1])
        R.retrait(self.c, "alpha", annuler=True)
        B.statuts_du_registre(base, B.lire_json(self.c["candidats"], {}))
        self.assertNotIn("retrait", base["candidates"][0])


class DecouverteTests(unittest.TestCase):
    def test_flux_declares_et_sitemap(self):
        class Faux:
            def lire(self, url):
                pages = {"https://a.example/": b'<html><head><link rel="alternate" type="application/rss+xml" '
                                               b'href="/feed/"><link rel="alternate" type="application/rss+xml" '
                                               b'href="/comments/feed/"></head></html>',
                         "https://a.example/sitemap.xml": PAGES}
                if url not in pages:
                    raise OSError("404")
                return pages[url]

            def robots_sitemaps(self, url):
                return []
        cand = {"id": "alpha", "website": "https://a.example/accueil", "program": {"main_url": "https://a.example/programme"}}
        self.assertEqual([(f["type"], f["url"]) for f in V.decouvrir_candidat(cand, Faux())],
                         [("rss", "https://a.example/feed/"), ("sitemap", "https://a.example/sitemap.xml")])


if __name__ == "__main__":
    unittest.main()
