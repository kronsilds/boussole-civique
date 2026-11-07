import io
import json
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest import mock

import base_2027 as B
import boussole_2027 as BO
import votes_2027 as V


def votant(ref, delegue=False):
    return {"acteurRef": ref, "mandatRef": "PM1", "parDelegation": "true" if delegue else "false"}


def groupe(ref, pours=(), contres=(), abstentions=(), non_votants=(), position="pour"):
    def noeud(x):
        x = list(x)
        return None if not x else {"votant": x[0] if len(x) == 1 else x}  # un seul votant : objet, pas liste (comme le XML converti)
    return {"organeRef": ref, "nombreMembresGroupe": "10", "vote": {
        "positionMajoritaire": position,
        "decompteVoix": {"pour": str(len(list(pours))), "contre": str(len(list(contres))), "abstentions": str(len(list(abstentions))), "nonVotants": "0"},
        "decompteNominatif": {"pours": noeud(pours), "contres": noeud(contres), "abstentions": noeud(abstentions), "nonVotants": noeud(non_votants)}}}


def scrutin(numero, titre="l'ensemble du projet de loi relatif a l'energie", objet=None, leg="17", groupes=None, date="2025-03-04"):
    return {"scrutin": {"uid": f"VTANR5L{leg}V{numero}", "numero": str(numero), "legislature": leg, "dateScrutin": date, "titre": titre,
                        "objet": {"libelle": objet or titre}, "typeVote": {"codeTypeVote": "SPO", "libelleTypeVote": "scrutin public ordinaire", "typeMajorite": "majorite simple"},
                        "sort": {"code": "adopté"}, "ventilationVotes": {"organe": {"groupes": {"groupe": groupes or []}}}}}


def archive(dossier, scrutins, nom="Scrutins.json.zip", groupe_fichier=False):
    chemin = Path(dossier) / nom
    with zipfile.ZipFile(chemin, "w") as z:
        if groupe_fichier:
            z.writestr("scrutins.json", json.dumps({"scrutins": {"scrutin": [s["scrutin"] for s in scrutins]}}))
        else:
            for i, s in enumerate(scrutins):
                z.writestr(f"json/{s['scrutin'].get('uid', i)}.json", json.dumps(s))
    return chemin


def acteur(ref, prenom, nom, naissance="1975-03-01", mandats=()):
    return {"acteur": {"uid": {"@xsi:type": "x", "#text": ref}, "etatCivil": {"ident": {"civ": "M.", "prenom": prenom, "nom": nom},
            "infoNaissance": {"dateNais": naissance}},
            "mandats": {"mandat": [{"typeOrgane": t, "legislature": leg, "dateDebut": "2022-06-22", "dateFin": None} for t, leg in mandats]}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.c = BO.chemins(Namespace(racine=str(self.dir)))
        self.v = V.chemins_votes(self.c)
        self.tracked = {"PA100": "ruffin", "PA200": "le-pen"}
        V.ajouter_votant(self.v["votants"], "ruffin", "PA100")
        V.ajouter_votant(self.v["votants"], "le-pen", "PA200")

    def importer(self, scrutins, **kw):
        return V.importer(self.c, kw.pop("leg", "17"), archive=archive(self.dir, scrutins, **kw))


class LectureTests(unittest.TestCase):
    def test_positions_delegation_et_groupes(self):
        s = scrutin(7, groupes=[groupe("PO1", pours=[votant("PA100"), votant("PA999")], contres=[votant("PA200", delegue=True)]),
                                groupe("PO2", abstentions=[votant("PA300")], position="abstention")])
        r = V.lire_scrutin(s["scrutin"], {"PA100": "ruffin", "PA200": "le-pen"})
        self.assertEqual(r["votes"]["PA100"], {"position": "pour", "delegue": False, "groupe": "PO1"})
        self.assertEqual(r["votes"]["PA200"], {"position": "contre", "delegue": True, "groupe": "PO1"})
        self.assertNotIn("PA999", r["votes"])  # seuls les votants suivis sont gardes
        self.assertEqual(set(r["groupes"]), {"PO1", "PO2"})  # les groupes sont gardes en entier
        self.assertEqual(r["groupes"]["PO2"]["position"], "abstention")
        self.assertEqual(r["groupes"]["PO1"]["pour"], 2)
        self.assertEqual(r["lien"], "https://www.assemblee-nationale.fr/dyn/17/scrutins/7")

    def test_noeuds_absents_ou_uniques(self):
        s = scrutin(8, groupes=[groupe("PO1")])  # aucun votant nominatif
        self.assertEqual(V.lire_scrutin(s["scrutin"], {"PA100": "ruffin"})["votes"], {})
        sans = {"scrutin": {"uid": "VTX", "numero": "1", "legislature": "17"}}  # ventilation absente
        self.assertEqual(V.lire_scrutin(sans["scrutin"], {})["groupes"], {})
        groupe_unique = scrutin(9)
        groupe_unique["scrutin"]["ventilationVotes"]["organe"]["groupes"]["groupe"] = groupe("PO1", pours=[votant("PA100")])  # objet, pas liste
        self.assertEqual(V.lire_scrutin(groupe_unique["scrutin"], {"PA100": "ruffin"})["votes"]["PA100"]["position"], "pour")

    def test_cause_du_non_vote_et_mise_au_point(self):
        s = scrutin(10, groupes=[groupe("PO1", pours=[votant("PA999")], non_votants=[{**votant("PA100"), "causePositionVote": "MG"}],
                                        contres=[votant("PA200")])])
        s["scrutin"]["miseAuPoint"] = {"pours": {"votant": votant("PA100")}, "contres": None, "abstentions": [None, None],  # formes reelles du fichier
                                       "nonVotants": [None, None], "nonVotantsVolontaires": [None, None],
                                       "dysfonctionnement": {"pour": None}}
        r = V.lire_scrutin(s["scrutin"], {"PA100": "ruffin", "PA200": "le-pen"})
        self.assertEqual(r["votes"]["PA100"], {"position": "non_votant", "delegue": False, "groupe": "PO1", "cause": "MG", "mise_au_point": "pour"})
        self.assertNotIn("mise_au_point", r["votes"]["PA200"])  # le vote enregistre n'est jamais remplace par l'intention
        orphelin = scrutin(11, groupes=[groupe("PO1")])
        orphelin["scrutin"]["miseAuPoint"] = {"contres": {"votant": votant("PA100")}}
        self.assertEqual(V.lire_scrutin(orphelin["scrutin"], {"PA100": "ruffin"})["votes"]["PA100"]["position"], "absent")

    def test_adresse_des_archives_par_legislature(self):
        self.assertTrue(V.url_scrutins("17").endswith("/repository/17/loi/scrutins/Scrutins.json.zip"))
        self.assertTrue(V.url_scrutins("16").endswith("/repository/16/loi/scrutins/Scrutins.json.zip"))
        self.assertTrue(V.url_scrutins("15").endswith("/repository/15/loi/scrutins/Scrutins_XV.json.zip"))  # nom different pour la 15e

    def test_portee_probable(self):
        for titre, attendu in [("la motion de censure de M. X", "motion"), ("l'amendement n° 12 de Mme Y a l'article 3", "amendement"),
                               ("l'article 5 du projet", "article"), ("l'ensemble du projet de loi", "ensemble"), ("la declaration du gouvernement", "inconnue")]:
            self.assertEqual(V.portee_probable(titre, None), attendu, titre)

    def test_fichier_groupe_ou_un_fichier_par_scrutin(self):
        s = scrutin(1)
        self.assertEqual(len(list(V.scrutins_de(s))), 1)
        self.assertEqual(len(list(V.scrutins_de({"scrutins": {"scrutin": [s["scrutin"], scrutin(2)["scrutin"]]}}))), 2)
        self.assertEqual(list(V.scrutins_de({"autre": 1})), [])


class VotantsTests(Base):
    def test_validation(self):
        with self.assertRaises(ValueError):
            V.ajouter_votant(self.v["votants"], "ruffin", "1234")
        with self.assertRaises(ValueError):
            V.ajouter_votant(self.v["votants"], "inconnu", "PA5", candidats={"ruffin"})
        with self.assertRaisesRegex(ValueError, "deja attribue"):
            V.ajouter_votant(self.v["votants"], "attal", "PA100")
        V.ajouter_votant(self.v["votants"], "ruffin", "PA101")  # un candidat peut etre corrige
        self.assertEqual(V.lire_votants(self.v["votants"])["votants"]["ruffin"]["an_acteur"], "PA101")

    def test_chercher_homonymes_et_accents(self):
        z = Path(self.dir) / "AMO.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("json/acteur/PA1.json", json.dumps(acteur("PA1", "François", "Ruffin", mandats=[("ASSEMBLEE", "17"), ("GP", "17")])))
            f.writestr("json/acteur/PA2.json", json.dumps(acteur("PA2", "Jean", "Ruffin", "1950-01-01")))
            f.writestr("json/acteur/PA3.json", json.dumps(acteur("PA3", "Éric", "Zemmour")))
        self.assertEqual([x["an_acteur"] for x in V.chercher_acteurs(z, "ruffin")], ["PA1", "PA2"])  # homonymes : a confirmer
        un = V.chercher_acteurs(z, "francois ruffin")
        self.assertEqual(len(un), 1)
        self.assertEqual(un[0]["mandats_assemblee"], [{"legislature": "17", "debut": "2022-06-22", "fin": None}])  # seul le mandat de depute
        self.assertEqual(V.chercher_acteurs(z, "eric zemmour")[0]["an_acteur"], "PA3")
        with self.assertRaises(ValueError):
            V.chercher_acteurs(z, "  ")

    def test_chercher_fichier_groupe(self):
        z = Path(self.dir) / "AMO.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("amo.json", json.dumps({"export": {"acteurs": {"acteur": [acteur("PA1", "Marine", "Le Pen")["acteur"]]}}}))
        self.assertEqual(V.chercher_acteurs(z, "le pen")[0]["an_acteur"], "PA1")


class ImportTests(Base):
    def lot(self, position_ruffin="pour"):
        pours, contres = ([votant("PA100")], [votant("PA200")]) if position_ruffin == "pour" else ([votant("PA200")], [votant("PA100")])
        return [scrutin(1, groupes=[groupe("PO1", pours=pours, contres=contres)]),
                scrutin(2, groupes=[groupe("PO1", pours=[votant("PA999")])])]  # aucun suivi n'y a vote

    def test_import_garde_les_scrutins_suivis(self):
        r = self.importer(self.lot())
        self.assertEqual((r["etat"], r["scrutins_total"], r["scrutins_suivis"]), ("importe", 2, 1))
        donnees = B.lire_json(self.v["scrutins"])
        self.assertEqual(list(donnees["scrutins"]), ["VTANR5L17V1"])
        self.assertEqual(donnees["scrutins"]["VTANR5L17V1"]["votes"]["PA100"]["position"], "pour")
        self.assertIn("Licence ouverte", donnees["meta"]["licence"])

    def test_idempotent_puis_nouveau_votant(self):
        z = archive(self.dir, self.lot())
        V.importer(self.c, "17", archive=z)
        avant = self.v["scrutins"].stat().st_mtime_ns
        self.assertEqual(V.importer(self.c, "17", archive=z)["etat"], "inchange")
        self.assertEqual(self.v["scrutins"].stat().st_mtime_ns, avant)
        V.ajouter_votant(self.v["votants"], "attal", "PA999")  # nouveau votant : relecture de la meme archive
        r = V.importer(self.c, "17", archive=z)
        self.assertEqual((r["etat"], r["scrutins_suivis"]), ("importe", 2))

    def test_rectification_signalee(self):
        self.importer(self.lot("pour"))
        r = self.importer(self.lot("contre"), nom="Scrutins2.json.zip")
        self.assertEqual(r["rectifications"], 2)  # Ruffin et Le Pen : positions inversees
        rect = B.lire_json(self.v["scrutins"])["meta"]["rectifications"]
        self.assertIn({"scrutin": "VTANR5L17V1", "acteur": "PA100", "avant": "pour", "apres": "contre",
                       "mise_au_point_avant": None, "mise_au_point_apres": None}, rect)

    def test_legislatures_independantes(self):
        self.importer([scrutin(1, groupes=[groupe("PO1", pours=[votant("PA100")])])])
        self.importer([scrutin(5, leg="16", groupes=[groupe("PO1", contres=[votant("PA100")])])], leg="16", nom="Scrutins16.json.zip")
        self.assertEqual(sorted(B.lire_json(self.v["scrutins"])["scrutins"]), ["VTANR5L16V5", "VTANR5L17V1"])
        self.importer([], nom="Scrutins17b.json.zip")  # la 17e est remplacee, la 16e reste
        self.assertEqual(list(B.lire_json(self.v["scrutins"])["scrutins"]), ["VTANR5L16V5"])

    def test_fichier_groupe(self):
        r = self.importer(self.lot(), groupe_fichier=True)
        self.assertEqual(r["scrutins_suivis"], 1)

    def test_erreurs(self):
        with self.assertRaisesRegex(ValueError, "introuvable"):
            V.importer(self.c, "17", archive=self.dir / "absente.zip")
        with self.assertRaisesRegex(ValueError, "stockee"):
            V.importer(self.c, "17", hors_ligne=True)
        self.v["votants"].write_text('{"votants": {}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Aucun votant"):
            self.importer(self.lot())

    def test_format_change_sans_identifiant(self):
        mauvais = scrutin(3)
        del mauvais["scrutin"]["uid"]
        with self.assertRaisesRegex(ValueError, "format officiel"):
            self.importer([mauvais])

    def test_archive_suspecte(self):
        z = archive(self.dir, self.lot())
        with mock.patch.object(V, "FICHIERS_MAX", 1), self.assertRaisesRegex(ValueError, "suspecte"):
            V.importer(self.c, "17", archive=z)
        with mock.patch.object(V, "FICHIER_JSON_MAX", 10), self.assertRaisesRegex(ValueError, "trop gros"):
            V.importer(self.c, "17", archive=z)

    def test_plan(self):
        self.importer(self.lot())
        p = V.plan(self.c, {"ruffin": "F. Ruffin", "le-pen": "M. Le Pen", "zemmour": "E. Zemmour"})
        self.assertEqual(p["votants"]["ruffin"]["pour"], 1)
        self.assertEqual(p["votants"]["le-pen"]["contre"], 1)
        self.assertEqual(p["sans_votant"], ["zemmour"])
        self.assertEqual(p["portees_probables"], {"ensemble": 2})


class TelechargementTests(Base):
    class Reponse:
        def __init__(self, contenu, url=f"https://{V.HOTE}/x.zip", longueur=None):
            self.contenu, self.url, self.pos = contenu, url, 0
            self.headers = {"Content-Length": str(len(contenu) if longueur is None else longueur)}

        def geturl(self):
            return self.url

        def read(self, n):
            bloc, self.pos = self.contenu[self.pos:self.pos + n], self.pos + n
            return bloc

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def zip_octets(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("a.json", "{}")
        return b.getvalue()

    def telecharger(self, reponse, url=f"https://{V.HOTE}/x.zip", **kw):
        return V.telecharger(url, self.dir / "brut" / "x.zip", ouvrir=lambda req, timeout: reponse, **kw)

    def test_succes(self):
        octets = self.zip_octets()
        r = self.telecharger(self.Reponse(octets))
        self.assertEqual(r["taille"], len(octets))
        self.assertTrue((self.dir / "brut" / "x.zip").exists())
        self.assertFalse((self.dir / "brut" / "x.zip.tmp").exists())

    def test_refus(self):
        octets = self.zip_octets()
        for url in ("http://data.assemblee-nationale.fr/x.zip", "https://exemple.org/x.zip", "https://data.assemblee-nationale.fr.exemple.org/x.zip"):
            with self.assertRaisesRegex(ValueError, "refusee"):
                self.telecharger(self.Reponse(octets), url=url)
        with self.assertRaisesRegex(ValueError, "refusee"):  # redirection vers un autre hote
            self.telecharger(self.Reponse(octets, url="https://exemple.org/y.zip"))

    def test_taille_et_format(self):
        octets = self.zip_octets()
        with self.assertRaisesRegex(ValueError, "volumineuse"):
            self.telecharger(self.Reponse(octets, longueur=10 ** 9))
        with self.assertRaisesRegex(ValueError, "interrompu"):  # taille annoncee fausse
            self.telecharger(self.Reponse(octets, longueur=1), taille_max=len(octets) - 1)
        self.assertFalse((self.dir / "brut" / "x.zip").exists())
        with self.assertRaisesRegex(ValueError, "zip"):
            self.telecharger(self.Reponse(b"<html>pas un zip</html>"))
        self.assertFalse((self.dir / "brut" / "x.zip.tmp").exists())

    def test_import_telecharge_et_hors_ligne(self):
        octets = self.zip_octets()
        faux = lambda url, dest: V.telecharger(url, dest, ouvrir=lambda req, timeout: self.Reponse(octets, url=url))
        r = V.importer(self.c, "17", telecharge=faux)
        self.assertEqual(r["etat"], "importe")
        self.assertEqual(V.importer(self.c, "17", hors_ligne=True)["etat"], "inchange")  # relit l'archive stockee, sans reseau


class CommandeTests(Base):
    def test_commandes(self):
        ns = lambda **kw: Namespace(**kw)
        self.assertEqual(V.executer(self.c, ns(action="plan")), 0)
        self.assertEqual(V.executer(self.c, ns(action="votant", candidat="attal", an_acteur="PA300", note=None)), 0)
        self.assertEqual(V.lire_votants(self.v["votants"])["votants"]["attal"]["an_acteur"], "PA300")
        with self.assertRaises(ValueError):
            V.executer(self.c, ns(action="inconnue"))


if __name__ == "__main__":
    unittest.main()
