"""Votes, phase 2 : liens vote-mesure (journal, etats, recherche, export, API du tableau de bord)."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from argparse import Namespace
from http.server import ThreadingHTTPServer
from pathlib import Path

import base_2027 as B
import boussole_2027 as BO
import tableau_de_bord_2027 as TB
import votes_2027 as V
from test_base_2027 import annoter, data, prop
from test_votes_2027 import archive, groupe, scrutin, votant

ETAPES = list(BO.ETAPES_GRATUITES)


def scrutins(avec_mise_au_point=False):
    retraites = scrutin(1, titre="l'ensemble de la proposition de loi relative aux retraites", date="2025-03-04",
                        groupes=[groupe("PO1", pours=[votant("PA100")], contres=[votant("PA200")])])
    smic = scrutin(2, titre="l'amendement n° 12 de Mme X a l'article 3 sur le SMIC", date="2025-04-01",
                   groupes=[groupe("PO1", contres=[votant("PA100")], position="contre")])
    autre = scrutin(3, titre="l'ensemble du projet de loi sur les retraites complementaires", date="2024-01-10",
                    groupes=[groupe("PO2", pours=[votant("PA200")])])
    if avec_mise_au_point:
        retraites["scrutin"]["miseAuPoint"] = {"contres": {"votant": votant("PA100")}}
    return [retraites, smic, autre]


class Socle(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base, _ = B.migrer(data(prop(1), prop(2, title="Hausse du SMIC à 1600 euros"), prop(3, cand="le-pen")))
        base = annoter(base, 1)
        B.ecrire_json(self.dir / "donnees" / "base_2027.json", base)
        self.c = BO.chemins(Namespace(racine=str(self.dir)))
        self.v = V.chemins_votes(self.c)
        V.ajouter_votant(self.v["votants"], "roussel", "PA100")
        V.ajouter_votant(self.v["votants"], "le-pen", "PA200")
        V.importer(self.c, "17", archive=archive(self.dir, scrutins()))
        BO.executer(self.c, ETAPES)
        self.d = V.Donnees(self.c)
        self.base = BO.charger_base(self.c)
        self.par_uid = {m["uid"]: m for m in self.base["mesures"]}
        self.m1 = self.par_uid["m-roussel-0001"]


class LiensTests(Socle):
    def test_recherche_limitee_aux_votes_du_candidat(self):
        r = self.d.chercher("roussel", "retraites")
        self.assertEqual([x["id"] for x in r["items"]], ["VTANR5L17V1"])  # le scrutin 3 n'a pas de vote de Roussel
        self.assertEqual(r["items"][0]["position"], "pour")
        self.assertEqual(self.d.chercher("roussel")["total"], 2)  # sans mot : tous ses scrutins, du plus recent au plus ancien
        self.assertEqual([x["id"] for x in self.d.chercher("roussel")["items"]], ["VTANR5L17V2", "VTANR5L17V1"])
        self.assertEqual(self.d.chercher("roussel", position="contre")["total"], 1)
        self.assertEqual(self.d.chercher("roussel", portee="amendement")["total"], 1)
        self.assertEqual(self.d.chercher("roussel", legislature="16")["total"], 0)
        self.assertEqual(self.d.chercher("le-pen", "retraites")["total"], 2)
        with self.assertRaises(ValueError):
            self.d.chercher("melenchon")  # pas de votant declare

    def test_cycle_du_lien(self):
        e = self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "texte_compose", note="  ok  ", preuve="art. 2")
        self.assertEqual((e["id"], e["version"], e["origine"], e["note"]), ("lv-000001", 1, "humain", "ok"))
        self.assertEqual(e["vote_vu"], {"position": "pour", "mise_au_point": None, "delegue": False})
        self.assertEqual(len(self.d.liens(self.par_uid)), 1)
        self.d.ajouter_lien(self.m1, "VTANR5L17V1", "partielle", "texte_compose")  # remplace, ne s'ajoute pas
        liens = self.d.liens(self.par_uid)
        self.assertEqual([(x["relation"], x["etat"]) for x in liens], [("partielle", "ok")])
        self.assertEqual(len(self.d.journal), 2)  # l'ancien lien reste dans le journal
        self.d.retirer_lien(liens[0]["id"])
        self.assertEqual(self.d.liens(self.par_uid), [])
        self.assertEqual([x["type"] for x in self.d.journal], ["lien", "lien", "retrait"])  # rien n'est efface
        with self.assertRaises(KeyError):
            self.d.retirer_lien("lv-999999")
        rechargees = V.Donnees(self.c)  # persiste sur le disque
        self.assertEqual(len(rechargees.journal), 3)

    def test_refus(self):
        m3 = self.par_uid["m-le-pen-0001"]
        with self.assertRaisesRegex(ValueError, "Relation"):
            self.d.ajouter_lien(self.m1, "VTANR5L17V1", "pour", "mesure")
        with self.assertRaisesRegex(ValueError, "Portee"):
            self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "loi")
        with self.assertRaisesRegex(ValueError, "inconnu"):
            self.d.ajouter_lien(self.m1, "VTANR5L17V99", "conforme", "mesure")
        with self.assertRaisesRegex(ValueError, "rien a relier"):
            self.d.ajouter_lien(self.m1, "VTANR5L17V3", "conforme", "mesure")  # Roussel n'a pas vote ce scrutin
        with self.assertRaisesRegex(ValueError, "caracteres"):
            self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "mesure", note="x" * 501)
        self.d.ajouter_lien(m3, "VTANR5L17V3", "conforme", "texte_compose")  # le vote de Le Pen n'est pas celui de Roussel
        self.assertEqual(self.d.liens(self.par_uid, candidat="roussel"), [])
        self.assertEqual(len(self.d.journal), 1)  # un refus n'ecrit rien

    def test_lien_a_revoir_si_la_mesure_change(self):
        e = self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "texte_compose")
        modifiee = {**self.m1, "versions": self.m1["versions"] + [self.m1["versions"][-1]]}
        self.assertEqual(self.d.etat_lien(e, self.m1), ("ok", []))
        self.assertEqual(self.d.etat_lien(e, modifiee), ("a_revoir", ["mesure_modifiee"]))

    def test_lien_a_revoir_si_le_vote_est_rectifie(self):
        self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "texte_compose")
        self.assertEqual(self.d.liens(self.par_uid)[0]["etat"], "ok")
        V.importer(self.c, "17", archive=archive(self.dir, scrutins(avec_mise_au_point=True)))
        self.d.recharger()
        lien = self.d.liens(self.par_uid)[0]
        self.assertEqual((lien["etat"], lien["raisons"]), ("a_revoir", ["vote_rectifie"]))
        self.assertEqual(lien["vote"]["position"], "pour")  # le vote enregistre n'est pas remplace
        self.assertEqual(lien["vote"]["mise_au_point"], "contre")  # la mise au point est montree a cote
        self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "texte_compose")  # reconfirmation
        self.assertEqual(self.d.liens(self.par_uid)[0]["etat"], "ok")

    def test_export_des_liens_a_jour_seulement(self):
        self.d.ajouter_lien(self.m1, "VTANR5L17V1", "conforme", "texte_compose")
        self.d.ajouter_lien(self.m1, "VTANR5L17V2", "sans_rapport", "amendement")
        r = self.d.pour_export(self.par_uid)
        self.assertEqual(list(r), ["m-roussel-0001"])
        self.assertEqual(len(r["m-roussel-0001"]), 1)  # « sans rapport » n'est pas publie
        ligne = r["m-roussel-0001"][0]
        self.assertEqual((ligne["s"], ligne["p"], ligne["r"], ligne["po"], ligne["g"], ligne["gp"]),
                         ("VTANR5L17V1", "pour", "conforme", "texte_compose", "PO1", "pour"))
        self.assertNotIn("roussel", json.dumps(ligne).lower())  # aucun nom de candidat dans la ligne
        V.importer(self.c, "17", archive=archive(self.dir, scrutins(avec_mise_au_point=True)))
        self.d.recharger()
        self.assertEqual(self.d.pour_export(self.par_uid), {})  # a revoir : plus publie

    def test_export_complet_et_lignes_precedentes(self):
        self.d.ajouter_lien(self.m1, "VTANR5L17V1", "contraire", "article")
        BO.executer(self.c, ETAPES)
        rows = {r["id"]: r for r in B.lire_json(self.c["export"])["proposals"]}
        self.assertEqual(rows["m-roussel-0001"]["votes"][0]["r"], "contraire")
        self.assertNotIn("votes", rows["m-roussel-0002"])
        self.d.retirer_lien(self.d.liens(self.par_uid)[0]["id"])
        BO.executer(self.c, ETAPES)
        rows = {r["id"]: r for r in B.lire_json(self.c["export"])["proposals"]}
        self.assertNotIn("votes", rows["m-roussel-0001"])  # jamais repris d'un export precedent

    def test_noms_de_groupes(self):
        self.assertEqual(V.completer_noms_groupes(self.c), 0)  # pas d'archive des acteurs : groupes connus par leur seul identifiant
        self.assertEqual(self.d.groupe("PO1")["abrege"], "PO1")


class ApiTests(Socle):
    def setUp(self):
        super().setUp()
        self.etat = TB.Etat(self.dir)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TB.fabriquer_handler(self.etat, TB.PAGE))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url + path) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def post(self, path, body, header=True):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-Boussole": "1"} if header else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_parcours_complet(self):
        _, e = self.get("/api/votes")
        self.assertEqual((e["nb_scrutins"], e["nb_liens"], len(e["votants"])), (3, 0, 2))
        self.assertEqual([x["total"] for x in e["votants"]], [2, 2])
        status, r = self.get("/api/votes/scrutins?candidat=roussel&q=retraites")
        self.assertEqual((status, [x["id"] for x in r["items"]]), (200, ["VTANR5L17V1"]))
        self.assertEqual(self.get("/api/votes/scrutins?candidat=inconnu")[0], 400)
        status, d = self.get("/api/votes/scrutin/VTANR5L17V1?candidat=roussel")
        self.assertEqual((status, d["vote"]["position"], d["portee_par_defaut"]), (200, "pour", "texte_compose"))
        self.assertEqual(self.get("/api/votes/scrutin/VTANR5L17V99?candidat=roussel")[0], 404)
        corps = {"uid": "m-roussel-0001", "scrutin": "VTANR5L17V1", "relation": "conforme", "portee": "texte_compose"}
        self.assertEqual(self.post("/api/votes/lien", corps, header=False)[0], 403)  # sans l'en-tete de la page
        self.assertEqual(self.post("/api/votes/lien", {**corps, "relation": "x"})[0], 400)
        self.assertEqual(self.post("/api/votes/lien", {**corps, "uid": "m-roussel-9999"})[0], 404)
        status, r = self.post("/api/votes/lien", corps)
        self.assertEqual((status, r["lien"]["etat"], len(r["liens"])), (200, "ok", 1))
        fiche = self.get("/api/mesure/m-roussel-0001")[1]
        self.assertTrue(fiche["votes"]["votant"])
        self.assertEqual(fiche["votes"]["liens"][0]["scrutin"]["id"], "VTANR5L17V1")
        self.assertEqual(self.get("/api/etat")[1]["votes"], {"votants": 2, "scrutins": 3, "liens": 1, "a_revoir": 0})
        lien_id = r["lien"]["id"]
        status, r = self.post("/api/votes/retrait", {"lien": lien_id})
        self.assertEqual((status, r["liens"]), (200, []))
        self.assertEqual(self.post("/api/votes/retrait", {"lien": lien_id})[0], 404)  # deja retire
        self.assertEqual(self.get("/api/votes/liens")[1]["total"], 0)

    def test_candidat_sans_votant(self):
        B.ecrire_json(self.v["votants"], {"votants": {"roussel": V.lire_votants(self.v["votants"])["votants"]["roussel"]}})
        fiche = self.get("/api/mesure/m-le-pen-0001")[1]
        self.assertFalse(fiche["votes"]["votant"])
        self.assertEqual(self.get("/api/votes")[1]["sans_votant"], ["le-pen"])


if __name__ == "__main__":
    unittest.main()
