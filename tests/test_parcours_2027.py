"""Tests hors ligne du parcours des pages liees (meme hote, arborescence ou domaine)."""
from __future__ import annotations

import io
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import chaine_2027 as chaine
import programme_corpus_2027 as corpus

HOTE = "https://example.org"
TEXTE = "Nous proposons de construire cent logements publics par an pour les familles modestes de France."


def page(*liens: str, titre: str = "Page") -> bytes:
    corps = "".join(f'<a href="{lien}">lien</a>' for lien in liens)
    return (f"<!doctype html><html><body><nav><a href='/contact'>Contact</a></nav><main><h1>{titre}</h1>"
            f"<p>{TEXTE}</p>{corps}</main></body></html>").encode()


SITE = {
    f"{HOTE}/programme": page("/programme/logement", "/programme/sante#ancre", "/programme/logement/", "/autre",
                              "https://other.org/programme/x", "/programme/logo.png", "mailto:a@b.fr",
                              "/programme/chapitre.pdf-non", titre="Sommaire"),
    f"{HOTE}/programme/logement": page("/programme/logement/detail", "/programme/", titre="Logement"),
    f"{HOTE}/programme/sante": page(titre="Sante"),
    f"{HOTE}/programme/logement/detail": page("/programme/logement/detail/tres-profond", titre="Detail"),
    f"{HOTE}/programme/logement/detail/tres-profond": page(titre="Trop profond"),
    f"{HOTE}/programme/chapitre.pdf-non": page(titre="Chapitre"),
    f"{HOTE}/autre": page(titre="Autre"),
    f"{HOTE}/contact": page(titre="Contact"),
}


class Reponse(io.BytesIO):
    def __init__(self, contenu: bytes, url: str):
        super().__init__(contenu)
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self.url = url

    def geturl(self):
        return self.url


def faux_urlopen(demandes: list[str]):
    def ouvrir(request, timeout=None):
        url = request.full_url
        demandes.append(url)
        if url not in SITE:
            raise corpus.urllib.error.URLError("introuvable")
        return Reponse(SITE[url], url)
    return ouvrir


def donnees(parcours=None, url=f"{HOTE}/programme"):
    lien = {"url": url, "title": "Programme", "theme": "logement", "format": "page_web"}
    if parcours is not None:
        lien["parcours"] = parcours
    return {"candidates": [{"id": "test", "name": "Candidat Test", "program": {"thematic_links": [lien]}}],
            "themes": [{"id": "logement", "label": "Logement"}]}


class ParcoursTests(unittest.TestCase):
    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.root = Path(temporaire.name)
        self.manifest = corpus.load_manifest(self.root)
        self.demandes: list[str] = []

    def lancer(self, parcours, **kw):
        data = donnees(parcours)
        ids = corpus.inventory(data, self.manifest, [])
        with patch("urllib.request.urlopen", side_effect=faux_urlopen(self.demandes)):
            corpus.collect(self.root, self.manifest, ids, pause=0)
            compteurs = corpus.parcourir(self.root, self.manifest, ids, pause=0, **kw)
        return compteurs, corpus.inventory(data, self.manifest, [])

    def urls(self, ids):
        return sorted(self.manifest["documents"][i]["url"] for i in ids)

    def test_sans_option_une_seule_page(self):
        compteurs, ids = self.lancer(None)
        self.assertEqual(compteurs["racines"], 0)
        self.assertEqual(self.urls(ids), [f"{HOTE}/programme"])
        self.assertEqual(self.demandes, [f"{HOTE}/programme"])

    def test_arborescence_reste_sous_le_dossier_et_le_meme_hote(self):
        compteurs, ids = self.lancer({"portee": "arborescence", "profondeur": 2})
        self.assertEqual(self.urls(ids), [f"{HOTE}/programme", f"{HOTE}/programme/chapitre.pdf-non",
                                          f"{HOTE}/programme/logement", f"{HOTE}/programme/logement/detail",
                                          f"{HOTE}/programme/sante"])
        self.assertEqual(compteurs["decouvertes"], 4)
        self.assertNotIn(f"{HOTE}/autre", self.demandes)
        self.assertNotIn(f"{HOTE}/contact", self.demandes)
        self.assertNotIn(f"{HOTE}/programme/logement/detail/tres-profond", self.demandes)
        self.assertFalse(any(u.endswith(".png") or "other.org" in u for u in self.demandes))
        # chaque page n'est telechargee qu'une fois (doublons, fragments et barres finales)
        self.assertEqual(len(self.demandes), len(set(self.demandes)))

    def test_profondeur_un_ne_suit_pas_les_liens_des_sous_pages(self):
        _, ids = self.lancer({"portee": "arborescence", "profondeur": 1})
        self.assertNotIn(f"{HOTE}/programme/logement/detail", self.urls(ids))

    def test_domaine_suit_tout_le_site_mais_pas_les_autres_hotes(self):
        _, ids = self.lancer({"portee": "domaine", "profondeur": 1})
        urls = self.urls(ids)
        self.assertIn(f"{HOTE}/autre", urls)
        self.assertIn(f"{HOTE}/programme/logement", urls)
        self.assertFalse(any("other.org" in u for u in urls))

    def test_exclure_ecarte_les_urls_correspondantes(self):
        _, ids = self.lancer({"portee": "domaine", "profondeur": 1, "exclure": ["/autre", "chapitre"]})
        urls = self.urls(ids)
        self.assertNotIn(f"{HOTE}/autre", urls)
        self.assertNotIn(f"{HOTE}/programme/chapitre.pdf-non", urls)

    def test_plafond_de_pages(self):
        compteurs, ids = self.lancer({"portee": "arborescence", "profondeur": 3, "max_pages": 2})
        self.assertEqual(len(ids), 3)
        self.assertEqual(compteurs["tronquees"], 1)
        self.assertTrue(self.manifest["documents"][ids[0]]["parcours"]["tronque"])

    def test_pages_decouvertes_reprennent_le_rattachement_sans_changer_celui_de_la_racine(self):
        data = donnees()
        racine_avant = corpus.inventory(data, self.manifest, [])[0]
        liaisons_avant = [dict(b) for b in self.manifest["documents"][racine_avant]["bindings"]]
        _, ids = self.lancer({"portee": "arborescence", "profondeur": 1})
        # activer le parcours ne modifie pas le rattachement de la page de depart (donc aucune re-extraction)
        self.assertEqual(self.manifest["documents"][racine_avant]["bindings"], liaisons_avant)
        enfant = next(self.manifest["documents"][i] for i in ids
                      if self.manifest["documents"][i]["url"].endswith("/logement"))
        self.assertEqual(enfant["parcours_de"], racine_avant)
        self.assertEqual(enfant["bindings"][0]["candidate_id"], "test")
        self.assertEqual(enfant["bindings"][0]["theme_id"], "logement")
        self.assertEqual(enfant["bindings"][0]["source_url"], f"{HOTE}/programme/logement")
        self.assertEqual(enfant["status"], "ready")

    def test_inventaire_suivant_conserve_les_pages_et_le_retrait_du_parcours_les_ecarte(self):
        _, ids = self.lancer({"portee": "arborescence", "profondeur": 2})
        avec = corpus.inventory(donnees({"portee": "arborescence", "profondeur": 2}), self.manifest, [])
        self.assertEqual(sorted(avec), sorted(ids))
        sans = corpus.inventory(donnees(None), self.manifest, [])
        self.assertEqual(self.urls(sans), [f"{HOTE}/programme"])
        self.assertNotIn("parcours", self.manifest["documents"][sans[0]])

    def test_deuxieme_passage_ne_retelecharge_rien(self):
        self.lancer({"portee": "arborescence", "profondeur": 2})
        premiers = len(self.demandes)
        compteurs, _ = self.lancer({"portee": "arborescence", "profondeur": 2})
        self.assertEqual(len(self.demandes), premiers)
        self.assertEqual(compteurs["nouvelles"], 0)

    def test_page_exclue_par_la_liste_d_exclusion_des_sources(self):
        _, ids = self.lancer({"portee": "arborescence", "profondeur": 1}, exclude_urls={f"{HOTE}/programme/sante"})
        self.assertNotIn(f"{HOTE}/programme/sante", self.urls(ids))

    def test_page_en_erreur_est_signalee_sans_arreter_le_parcours(self):
        SITE_AVANT = dict(SITE)
        self.addCleanup(lambda: (SITE.clear(), SITE.update(SITE_AVANT)))
        del SITE[f"{HOTE}/programme/sante"]
        _, ids = self.lancer({"portee": "arborescence", "profondeur": 1})
        statuts = {self.manifest["documents"][i]["url"].rsplit("/", 1)[-1]: self.manifest["documents"][i]["status"] for i in ids}
        self.assertEqual(statuts["sante"], "error")
        self.assertEqual(statuts["logement"], "ready")


class OptionsTests(unittest.TestCase):
    def test_valeurs_par_defaut_et_validation(self):
        self.assertIsNone(corpus.normaliser_parcours(None))
        self.assertEqual(corpus.normaliser_parcours(True)["portee"], "arborescence")
        self.assertEqual(corpus.normaliser_parcours({"exclure": [" /Contact "]})["exclure"], ["/contact"])
        for invalide in ({"portee": "internet"}, {"profondeur": 0}, {"profondeur": 6}, {"max_pages": 201},
                         {"max_pages": "10"}, {"exclure": "x"}, "oui"):
            with self.assertRaises(ValueError, msg=str(invalide)):
                corpus.normaliser_parcours(invalide)

    def test_prefixe_arborescence(self):
        self.assertEqual(corpus.prefixe_arborescence(f"{HOTE}/programme/livre"), "/programme/livre/")
        self.assertEqual(corpus.prefixe_arborescence(f"{HOTE}/programme/livre/"), "/programme/livre/")
        self.assertEqual(corpus.prefixe_arborescence(f"{HOTE}/programme/index.html"), "/programme/")
        self.assertEqual(corpus.prefixe_arborescence(HOTE), "/")

    def test_www_equivaut_au_domaine_nu_mais_pas_un_prefixe_voisin(self):
        options = corpus.normaliser_parcours({"portee": "arborescence"})
        self.assertTrue(corpus.lien_admis("https://www.example.org/programme/a", f"{HOTE}/programme", options))
        self.assertFalse(corpus.lien_admis(f"{HOTE}/programme-autre/a", f"{HOTE}/programme", options))
        self.assertFalse(corpus.lien_admis("https://example.org.evil.net/programme/a", f"{HOTE}/programme", options))

    def test_les_sources_du_tableau_de_bord_transmettent_le_parcours(self):
        data = {"candidates": [{"id": "test", "program": {}}]}
        ajout = {"id": "s-0001", "candidate_id": "test", "type": "programme", "url": f"{HOTE}/p",
                 "parcours": {"portee": "domaine", "profondeur": 2, "max_pages": 10, "exclure": []}}
        chaine.injecter_sources(data, [ajout], Path("."))
        self.assertEqual(data["candidates"][0]["program"]["thematic_links"][0]["parcours"]["portee"], "domaine")
        # meme page qu'un lien amont : le parcours s'y applique
        data = {"candidates": [{"id": "test", "program": {"thematic_links": [{"url": f"{HOTE}/p"}]}}]}
        chaine.injecter_sources(data, [ajout], Path("."))
        self.assertEqual(data["candidates"][0]["program"]["thematic_links"][0]["parcours"]["max_pages"], 10)


if __name__ == "__main__":
    unittest.main()
