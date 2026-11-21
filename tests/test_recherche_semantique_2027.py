"""Recherche par le sens : index, rangement par direction, API (simulee), secours, route du tableau de bord. Aucun
modele charge ni appel reseau : un encodeur factice (mots -> vecteurs) remplace les modeles, urlopen est simule."""
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

import base_2027 as B
import boussole_2027 as BO
import recherche_semantique_2027 as RS
import tableau_de_bord_2027 as TB
from test_base_2027 import data, prop

MOTS = ("smic", "salaire", "retraite", "voiture")


class EncodeurFactice:
    """Un axe par mot-cle (plus un axe de bruit) : deux textes qui partagent un mot-cle sont proches."""

    def __init__(self):
        self.appels = 0

    def encoder(self, textes, requete=False, suivi=None):
        self.appels += len(textes)
        out = np.zeros((len(textes), 1024), dtype=np.float32)
        for i, t in enumerate(textes):
            t = t.lower()
            for k, w in enumerate(MOTS):
                out[i, k] = 1.0 if w in t else 0.0
            out[i, 10] = 0.2
            out[i] /= np.linalg.norm(out[i])
        return out


def mesure(uid, cand, titre, eco):
    return {"uid": uid, "candidate_id": cand, "theme_id": "economie", "statut": "active",
            "versions": [{"n": 1, "title": titre, "description": ""}], "calculs": {"axes": {"eco": eco, "soc": None}}}


BASE = {"dimensions_schema": {"eco": {"type": "scale", "label": "Orientation économique",
                                      "low_label": "redistribution", "high_label": "libéralisation"}},
        "mesures": [mesure("m-a-1", "a", "SMIC à 1600 euros", -50), mesure("m-b-1", "b", "Baisser le SMIC jeunes", 40),
                    mesure("m-c-1", "c", "Salaire minimum européen", 5), mesure("m-d-1", "d", "Retraite à 60 ans", None),
                    mesure("m-e-1", "e", "Voiture électrique", None)]}


class RangementTests(unittest.TestCase):
    def test_groupes_par_direction_sur_l_axe_le_plus_present(self):
        res = [{"score": .8, "axes": {"eco": -50}}, {"score": .7, "axes": {"eco": 40}},
               {"score": .6, "axes": {"eco": 5}}, {"score": .5, "axes": {"eco": None, "soc": 30}}]
        r = RS.ranger(res, RS.libelles_axes(BASE))
        self.assertEqual(r["axe"]["cle"], "eco")
        self.assertEqual([g["cle"] for g in r["groupes"]], ["bas", "neutre", "haut", "aucune"])
        self.assertIn("redistribution", r["groupes"][0]["titre"])

    def test_sans_aucune_position(self):
        r = RS.ranger([{"score": .5, "axes": {"eco": None}}], RS.libelles_axes(BASE))
        self.assertIsNone(r["axe"])
        self.assertEqual(len(r["groupes"]), 1)


class RechercheTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.enc = EncodeurFactice()

    def test_index_incremental_et_recherche(self):
        base = json.loads(json.dumps(BASE))
        idx = RS.Index(self.dir / "index")
        self.assertEqual(RS.mettre_a_jour_index(base, idx, self.enc), 5)
        self.assertEqual(RS.mettre_a_jour_index(base, RS.Index(self.dir / "index"), self.enc), 0)  # relu du disque
        base["mesures"][0]["versions"].append({"n": 2, "title": "SMIC à 1700 euros", "description": ""})
        self.assertEqual(RS.mettre_a_jour_index(base, RS.Index(self.dir / "index"), self.enc), 1)  # texte change

        r = RS.Recherche(self.dir, self.dir / "index", encodeur=self.enc).chercher(base, "le smic")
        uids = [x["uid"] for g in r["groupes"] for x in g["items"]]
        self.assertEqual(set(uids), {"m-a-1", "m-b-1"})  # « salaire minimum » et le reste sous la coupure
        self.assertEqual(r["axe"]["cle"], "eco")
        self.assertEqual([g["cle"] for g in r["groupes"]], ["bas", "haut"])

    def test_filtre_candidat_et_requete_vide(self):
        rech = RS.Recherche(self.dir, self.dir / "index", encodeur=self.enc)
        r = rech.chercher(BASE, "smic", candidat="b")
        self.assertEqual([x["uid"] for g in r["groupes"] for x in g["items"]], ["m-b-1"])
        with self.assertRaises(ValueError):
            rech.chercher(BASE, "   ")

    def test_index_d_un_autre_modele_ignore(self):
        RS.Index(self.dir / "index").sauver()
        meta = self.dir / "index.json"
        meta.write_text(json.dumps({"modele": "autre", "cles": ["x"]}), encoding="utf-8")
        self.assertEqual(RS.Index(self.dir / "index").cles, [])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        p1 = prop(1, title="Voiture électrique")
        p1["description"] = "Rouler en voiture électrique."  # les autres parlent du SMIC (description par defaut)
        base, _ = B.migrer(data(p1, prop(2, title="Hausse du SMIC à 1600 euros"), prop(3, cand="le-pen")))
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)
        BO.executer(BO.chemins(type("A", (), {"racine": str(self.dir)})()), list(BO.ETAPES_GRATUITES))
        self.etat = TB.Etat(self.dir)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TB.fabriquer_handler(self.etat, TB.PAGE))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_modele_absent_message_clair(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url + "/api/recherche-sens?q=smic")
        self.assertEqual(ctx.exception.code, 409)
        erreur = json.loads(ctx.exception.read())["erreur"]
        self.assertIn("OPENROUTER_RECHERCHE_KEY", erreur)  # pas de .env.recherche, puis
        self.assertIn("modele absent", erreur)              # pas de modele local

    def test_recherche_avec_encodeur_factice(self):
        self.etat.sens = [RS.Recherche(self.dir, self.dir / "donnees" / "index_recherche_2027", encodeur=EncodeurFactice())]
        with urllib.request.urlopen(self.url + "/api/recherche-sens?q=smic") as r:
            res = json.loads(r.read())
        items = [x for g in res["groupes"] for x in g["items"]]
        self.assertEqual(len(items), 2)  # les deux mesures sur le SMIC, pas la voiture
        self.assertIn("candidat", items[0])
        self.assertIsNone(res["axe"])  # mesures non notees : un seul groupe, sans direction
        self.assertEqual([g["cle"] for g in res["groupes"]], ["tous"])
        self.assertTrue((self.dir / "donnees" / "index_recherche_2027.npy").exists())


FACTICE = RS.Moteur("factice", "factice", 1024, "", 0.6, 0.28, 0.40, "index_factice")


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fausse_api(appels):
    """urlopen simule : un vecteur par texte (un axe par mot-cle), cout 1e-6 $ par texte."""
    def urlopen(req, timeout=None):
        corps = json.loads(req.data)
        appels.append(corps)
        vec = EncodeurFactice().encoder(corps["input"])
        data = [{"index": i, "embedding": [float(x) for x in v[:8]]} for i, v in enumerate(vec)]
        return Reponse(json.dumps({"data": data, "usage": {"prompt_tokens": 5, "cost": 1e-6 * len(data)}}).encode())
    return urlopen


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.moteur = RS.Moteur("api", "m", 8, "Consigne: ", 0.6, 0.2, 0.35, "index_api")

    def test_config(self):
        self.assertEqual(RS.lire_config(self.dir), {})
        (self.dir / ".env.recherche").write_text("# commentaire\nOPENROUTER_RECHERCHE_KEY=abc\n"
                                                 "RECHERCHE_PLAFOND_MENSUEL='0.5'\n", encoding="utf-8")
        self.assertEqual(RS.lire_config(self.dir), {"OPENROUTER_RECHERCHE_KEY": "abc", "RECHERCHE_PLAFOND_MENSUEL": "0.5"})
        enc = RS.EncodeurAPI.depuis_config(self.dir, self.dir / "budget.json")
        self.assertEqual(enc.budget.plafond, 0.5)
        (self.dir / ".env.recherche").write_text("OPENROUTER_API_KEY=x\n", encoding="utf-8")  # pas la cle de .env
        with self.assertRaises(RS.Indisponible):
            RS.EncodeurAPI.depuis_config(self.dir, self.dir / "budget.json")

    def test_requete_consigne_et_budget(self):
        appels = []
        enc = RS.EncodeurAPI("cle", RS.Budget(self.dir / "budget.json", 1.0), self.moteur)
        with mock.patch("urllib.request.urlopen", fausse_api(appels)):
            v = enc.encoder(["le smic", "retraite"], requete=True)
        self.assertEqual(v.shape, (2, 8))
        self.assertAlmostEqual(float(np.linalg.norm(v[0])), 1.0, places=5)
        self.assertEqual(appels[0]["input"][0], "Consigne: le smic")
        self.assertEqual(appels[0]["model"], "m")
        mois = json.loads((self.dir / "budget.json").read_text(encoding="utf-8"))["mois"][RS.Budget.courant()]
        self.assertEqual((mois["appels"], mois["textes"]), (1, 2))
        self.assertAlmostEqual(mois["cout"], 2e-6)

    def test_plafond_atteint_sans_appel(self):
        RS.Budget(self.dir / "budget.json", 1.0).ajouter(1.0, 0, 1)
        appels = []
        enc = RS.EncodeurAPI("cle", RS.Budget(self.dir / "budget.json", 1.0), self.moteur)
        with mock.patch("urllib.request.urlopen", fausse_api(appels)), self.assertRaises(RS.Indisponible):
            enc.encoder(["smic"], requete=True)
        self.assertEqual(appels, [])

    def test_erreur_http(self):
        def refus(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "non", {}, None)
        enc = RS.EncodeurAPI("cle", RS.Budget(self.dir / "budget.json", 1.0), self.moteur)
        with mock.patch("urllib.request.urlopen", refus), self.assertRaisesRegex(RS.Indisponible, "401"):
            enc.encoder(["smic"], requete=True)


class SecoursTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_secours_quand_le_premier_moteur_manque(self):
        def sans_cle():
            raise RS.Indisponible("pas de cle")
        rs = [RS.Recherche(self.dir, self.dir / "a", moteur=FACTICE, fabrique=sans_cle),
              RS.Recherche(self.dir, self.dir / "b", encodeur=EncodeurFactice(), moteur=FACTICE)]
        r = RS.chercher_avec_secours(rs, BASE, "smic")
        self.assertIn("pas de cle", r["secours"])
        self.assertEqual(len([x for g in r["groupes"] for x in g["items"]]), 2)
        rs[1].fabrique, rs[1].encodeur, rs[1].index = sans_cle, None, None
        with self.assertRaises(RS.Indisponible):
            RS.chercher_avec_secours(rs, BASE, "smic")

    def test_index_partiel_si_le_moteur_tombe(self):
        idx = RS.Index(self.dir / "idx", FACTICE)
        textes = RS.textes_a_indexer(BASE)
        idx.ajouter(textes[:3], EncodeurFactice().encoder(textes[:3]))
        idx.sauver()

        class EnPanne(EncodeurFactice):
            def encoder(self, textes, requete=False, suivi=None):
                if not requete:
                    raise RS.Indisponible("plafond")
                return super().encoder(textes)
        r = RS.Recherche(self.dir, self.dir / "idx", encodeur=EnPanne(), moteur=FACTICE).chercher(BASE, "smic")
        self.assertEqual(r["non_indexees"], 2)
        self.assertEqual({x["uid"] for g in r["groupes"] for x in g["items"]}, {"m-a-1", "m-b-1"})

    def test_reprise_des_vecteurs_de_l_essai(self):
        textes = RS.textes_a_indexer(BASE)
        essai = self.dir / "essai"
        essai.mkdir()
        np.save(essai / "factice.npy", EncodeurFactice().encoder(textes[:2]).astype(np.float16))
        (essai / "factice.json").write_text(json.dumps([RS.cle(t) for t in textes[:2]]), encoding="utf-8")
        idx = RS.Index(self.dir / "idx", FACTICE)
        self.assertEqual(RS.reprendre_essai(idx, textes, essai), 2)
        self.assertEqual(len(RS.Index(self.dir / "idx", FACTICE).cles), 2)
        self.assertEqual(RS.reprendre_essai(idx, textes, essai), 0)


if __name__ == "__main__":
    unittest.main()
