"""Relecture humaine d'un echantillon tire au hasard (relecture_aleatoire_q2_2027) : tirage reproductible et
stratifie, fiches a l'aveugle, calcul des taux sur des reponses factices. Aucun appel reseau."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import questionnaire_q2_2027 as Q2
import relecture_aleatoire_q2_2027 as RA

THEMES = ("fiscalite", "sante", "securite", "ecologie")
CANDIDATS = {"roussel": 60, "le-pen": 30, "petit": 3}   # « petit » : trop peu de mesures pour une part proportionnelle


def reponses_q2(**r):
    return {**{k: None for k in Q2.QUESTIONS}, "degre": "notable", "chiffree": "non", **r}


ECO = dict(portee="large", eco_depense="augmente", eco_marche="inchange", eco_transfert="vers_modestes_ou_salaries",
           levier="depense_ou_service", rev_modestes="gagne", rev_moyennes="gagne", rev_cadres="non_concernee",
           rev_aises="non_concernee", rev_tres_aises="non_concernee")


def mesure(cand, n, theme, arbitree):
    return {"uid": f"m-{cand}-{n:04d}", "candidate_id": cand, "theme_id": theme, "statut": "active",
            "historique": {"corpus_id": f"corpus-{cand}-{n:012d}"},
            "versions": [{"n": 1, "date": "2026-11-01T00:00:00+00:00", "title": f"Mesure {n} de Roussel ({theme})",
                          "description": "Le RN et Fabien Roussel proposent de hausser le SMIC.",
                          "sources": [{"quote": "Nous, insoumis, hausserons le SMIC.", "segment_id": "s1"}]}],
            "annotation": {"version": "q2", "methode": "essai-q2-v7", "reponses": reponses_q2(**ECO),
                           "arbitrage": ["sens"] if arbitree else []}}


def base_factice():
    mesures = []
    for cand, nb in CANDIDATS.items():
        for n in range(1, nb + 1):
            mesures.append(mesure(cand, n, THEMES[n % len(THEMES)], arbitree=n % 3 == 0))
    mesures.append({**mesure("roussel", 999, "sante", False), "statut": "rejetee"})       # jamais publiee
    sans = mesure("le-pen", 998, "sante", False)
    sans["annotation"] = {}                                                                 # pas lue en q2
    mesures.append(sans)
    return {"meta": {}, "mesures": mesures, "themes": [{"id": t, "label": t.capitalize()} for t in THEMES],
            "candidates": [{"id": "roussel", "first_name": "Fabien", "last_name": "Roussel", "party": "Parti communiste français",
                            "party_short": "PCF"}, {"id": "le-pen", "first_name": "Marine", "last_name": "Le Pen",
                                                    "party": "Rassemblement national", "party_short": "RN"},
                           {"id": "petit", "first_name": "Jean", "last_name": "Petitcandidat"}]}


class TirageTests(unittest.TestCase):
    def setUp(self):
        self.pop = RA.population(base_factice(), None)

    def test_population_publiee_et_lue_en_q2(self):
        self.assertEqual(len(self.pop), sum(CANDIDATS.values()))
        export = {"proposals": [{"id": "m-roussel-0001"}, {"id": "m-roussel-0002", "badge": "en_revision"},
                                {"id": "m-roussel-0999"}]}
        self.assertEqual([x["uid"] for x in RA.population(base_factice(), export)], ["m-roussel-0001"])

    def test_reproductible_avec_la_meme_graine(self):
        a, ja = RA.tirer(self.pop, 30, 7)
        b, jb = RA.tirer(list(reversed(self.pop)), 30, 7)   # ordre d'entree sans effet
        self.assertEqual([x["uid"] for x in a], [x["uid"] for x in b])
        self.assertEqual(ja["empreinte_population"], RA.empreinte(sorted(self.pop, key=lambda x: x["uid"])))
        c, _ = RA.tirer(self.pop, 30, 8)
        self.assertNotEqual([x["uid"] for x in a], [x["uid"] for x in c])
        self.assertEqual((ja["graine"], ja["taille"]), (7, 30))

    def test_stratification(self):
        tires, journal = RA.tirer(self.pop, 30, 7)
        self.assertEqual(len({x["uid"] for x in tires}), 30)                     # sans remise
        par_cand = Counter(x["candidat"] for x in tires)
        self.assertGreaterEqual(par_cand["petit"], 1)                              # au moins une fiche par candidat
        self.assertGreater(par_cand["roussel"], par_cand["le-pen"])               # proportionnel sinon
        self.assertEqual(sum(v["fiches"] for v in journal["strates"].values()), 30)
        arb = sum(x["arbitree"] for x in tires)
        self.assertTrue(0 < arb < 30)                                              # arbitrees et non arbitrees
        self.assertEqual(set(Counter(x["theme"] for x in tires)), set(THEMES))   # tirage systematique : tous les themes
        for x in tires:                                                            # poids = taille de strate / fiches
            s = journal["strates"][x["strate"]]
            self.assertAlmostEqual(x["poids"], s["taille"] / s["fiches"], places=5)

    def test_allocation(self):
        alloc = RA.allocation({"a|accord": 90, "a|arbitree": 9, "b|accord": 1}, 10)
        self.assertEqual(sum(alloc.values()), 10)
        self.assertEqual(alloc["b|accord"], 1)
        self.assertEqual(RA.allocation({"a|accord": 3}, 10), {"a|accord": 3})   # pas plus que la population


class FichesTests(unittest.TestCase):
    def test_preparer_fiches_a_l_aveugle(self):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            (racine / "donnees").mkdir()
            (racine / "donnees" / "base_2027.json").write_text(json.dumps(base_factice()), encoding="utf-8")
            vus = {}

            def refs(_r, uids):
                vus["uids"] = uids
                return {u: {"publiee": reponses_q2(**ECO), "lecteur1": reponses_q2(**ECO), "lecteur2": reponses_q2(**ECO),
                            "arbitrage": []} for u in uids}
            journal = RA.preparer(racine, 20, 3, refs=refs)
            dossier = racine / RA.DOSSIER
            donnees = json.loads((dossier / "donnees.json").read_text(encoding="utf-8"))
            self.assertEqual(len(donnees["fiches"]), 20)
            self.assertEqual(vus["uids"], {f["uid"] for f in donnees["fiches"]})
            texte = json.dumps(donnees, ensure_ascii=False)
            for nom in ("Roussel", "RN", "insoumis", "Le Pen", "Petitcandidat"):
                self.assertNotIn(nom, texte)                                       # noms et alias masques
            self.assertIn("[le candidat]", texte)
            self.assertIn("[parti]", texte)
            # ni reponse de modele ni strate (qui dirait si la mesure a ete arbitree) dans la page
            for cle in ("publiee", "lecteur1", "arbitree", "strate", "poids", "vers_modestes_ou_salaries\": \"", "candidat\""):
                self.assertNotIn(cle, json.dumps(donnees["fiches"]) + json.dumps(donnees["mesures"]))
            self.assertEqual(set(donnees["questions"]) >= {"fidelite", "a_dispositif", "blocs", "degre", "portee", "revenus",
                                                           "eco_depense", "soc_libertes", "def_effort"}, True)
            self.assertEqual(donnees["questions"]["eco_depense"]["si"], ["a_eco"])
            page = (dossier / "relecture.html").read_text(encoding="utf-8")
            self.assertIn('"sorte": "aleatoire"', page)                            # donnees incluses : page autonome
            self.assertNotIn("</script>\"", page)
            artifact = (dossier / "relecture_artifact.html").read_text(encoding="utf-8")
            self.assertTrue(artifact.startswith("<title>"))                       # squelette ajoute a la publication
            self.assertNotIn("<body>", artifact)
            self.assertNotIn("�", artifact)
            self.assertEqual(journal["controle_lecteur1"]["sans_arbitrage"], journal["controle_lecteur1"]["identiques_publiee"])
            tirage = json.loads((dossier / "tirage.json").read_text(encoding="utf-8"))
            self.assertEqual(tirage["graine"], 3)
            # meme base, meme graine : meme echantillon
            RA.preparer(racine, 20, 3, refs=refs)
            again = json.loads((dossier / "donnees.json").read_text(encoding="utf-8"))
            self.assertEqual(donnees["fiches"], again["fiches"])
            self.assertFalse((racine / "donnees" / "decisions_2027.json").exists())   # rien d'ecrit hors du dossier


class BilanTests(unittest.TestCase):
    def setUp(self):
        self.donnees = {"graine": 1, "mesures": {f"u{i}": {"titre": f"Titre-secret-{i}"} for i in range(4)},
                        "fiches": [{"id": f"aleatoire:u{i}", "uid": f"u{i}"} for i in range(4)]}
        juste = reponses_q2(**ECO)
        faux_commun = reponses_q2(**{**ECO, "rev_modestes": "non_concernee", "rev_moyennes": "non_concernee"})
        l2_autre = reponses_q2(**{**ECO, "degre": "rupture"})
        self.refs = {
            "u0": {"publiee": juste, "lecteur1": juste, "lecteur2": juste},
            "u1": {"publiee": faux_commun, "lecteur1": faux_commun, "lecteur2": faux_commun},   # erreur commune
            "u2": {"publiee": juste, "lecteur1": reponses_q2(**{**ECO, "degre": "ajustement"}), "lecteur2": l2_autre},
            "u3": {"publiee": juste, "lecteur1": juste, "lecteur2": None},                       # lecture manquante
        }
        self.tires = {"u0": {"theme": "fiscalite", "poids": 10, "arbitree": False},
                      "u1": {"theme": "fiscalite", "poids": 10, "arbitree": False},
                      "u2": {"theme": "sante", "poids": 30, "arbitree": True},
                      "u3": {"theme": "sante", "poids": 10, "arbitree": False}}
        humain = {"fidelite": "fidele", "a_dispositif": "oui", "blocs": ["a_menages", "a_eco"], "degre": "notable",
                  "portee": "large", "eco_depense": "augmente", "eco_marche": "inchange",
                  "eco_transfert": "vers_modestes_ou_salaries", "rev_modestes": "gagne", "rev_moyennes": "gagne",
                  "rev_cadres": "non_concernee", "rev_aises": "non_concernee", "rev_tres_aises": "non_concernee"}
        self.reponses = {
            "aleatoire:u0": {"reponses": humain},
            "aleatoire:u1": {"reponses": {**humain, "fidelite": "hypothese"}, "commentaires": {"fiche": "Les bas salaires gagnent."}},
            "aleatoire:u2": {"reponses": {**humain, "eco_marche": RA.NSP}},
            # u3 non relue
        }

    def test_humain(self):
        h = RA.humain({"fidelite": "fidele", "a_dispositif": RA.NSP, "blocs": [], "degre": "rupture", "eco_depense": "augmente"})
        self.assertEqual(h["a_eco"], False)
        self.assertNotIn("a_dispositif", h)          # « je ne sais pas » : pas compte
        self.assertNotIn("eco_depense", h)           # bloc non coche : question fermee
        self.assertEqual((h["degre"], h["a_menages"]), ("rupture", False))
        tous_nc = {"blocs": ["a_menages"], **{k: "non_concernee" for k in RA.CLASSES}}
        self.assertEqual(RA.humain(tous_nc)["a_menages"], False)   # « pas concernee » partout = aucun menage touche
        # « ne s'applique pas » : None, comme une question fermee ; un bloc dont tout est sans objet n'est pas touche
        so = RA.humain({"blocs": ["a_eco", "a_soc"], "degre": RA.SANS_OBJET, "portee": RA.SANS_OBJET,
                        "eco_depense": "augmente", "eco_marche": RA.SANS_OBJET, "eco_transfert": RA.NSP,
                        "soc_autorite": RA.SANS_OBJET, "soc_libertes": RA.SANS_OBJET})
        self.assertEqual((so["degre"], so["portee"], so["eco_marche"], so["eco_depense"]), (None, None, None, "augmente"))
        self.assertNotIn("eco_transfert", so)
        self.assertEqual((so["a_eco"], so["a_soc"]), (True, False))
        lignes = {x["k"]: x for x in RA.comparaisons(so, {"publiee": reponses_q2(**ECO), "lecteur1": None, "lecteur2": None})}
        self.assertTrue(lignes["soc_autorite"]["publiee"])          # le modele n'ouvre pas non plus la question
        self.assertFalse(lignes["eco_marche"]["publiee"])           # le modele repond « inchange »
        self.assertEqual((lignes["a_eco"]["sorte"], lignes["a_soc"]["sorte"]), ("bloc_oui", "bloc_non"))
        self.assertIsNone(lignes["degre"]["accord"])                # lectures manquantes

    def test_bloc_ouvert(self):
        self.assertTrue(RA.bloc_ouvert(reponses_q2(**ECO), "a_eco"))
        self.assertFalse(RA.bloc_ouvert(reponses_q2(**ECO), "a_soc"))
        self.assertTrue(RA.bloc_ouvert(reponses_q2(**ECO), "a_dispositif"))
        self.assertFalse(RA.bloc_ouvert(reponses_q2(**{k: "non_concernee" for k in RA.CLASSES}), "a_menages"))
        self.assertIsNone(RA.bloc_ouvert(None, "a_eco"))

    def test_taux(self):
        b = RA.bilan(self.donnees, self.refs, self.tires, self.reponses)
        self.assertEqual((b["relues"], b["fiches"], b["complete"]), (3, 4, False))
        rev = b["par_sorte"]["revenus"]["publiee"]
        self.assertEqual((rev["justes"], rev["lues"]), (13, 15))            # u1 : deux classes fausses sur cinq
        deg = b["par_sorte"]["degre"]
        self.assertEqual((deg["publiee"]["justes"], deg["lecteur1"]["justes"], deg["lecteur2"]["justes"]), (3, 2, 2))
        self.assertEqual(b["par_question"]["eco_marche"]["publiee"]["lues"], 2)   # « je ne sais pas » ecarte
        # accord des lecteurs : erreur commune visible seulement la
        acc = b["accord_lecteurs"]
        self.assertEqual((acc["revenus|accord"]["justes"], acc["revenus|accord"]["lues"]), (13, 15))
        self.assertEqual((acc["degre|desaccord"]["justes"], acc["degre|desaccord"]["lues"]), (1, 1))
        communes = {(x["uid"], x["question"]) for x in b["erreurs_communes"]}
        self.assertEqual(communes, {("u1", "rev_modestes"), ("u1", "rev_moyennes"), ("u1", "a_menages")})
        self.assertEqual(b["erreurs_communes"][0]["commentaire"], "Les bas salaires gagnent.")
        # avant et apres arbitrage, mesures arbitrees ou non
        self.assertEqual(b["arbitrage"]["arbitree|publiee"]["justes"], b["arbitrage"]["arbitree|publiee"]["lues"])
        self.assertLess(b["arbitrage"]["arbitree|lecteur1"]["justes"], b["arbitrage"]["arbitree|lecteur1"]["lues"])
        # fidelite de l'extraction
        f = b["fidelite"]
        self.assertEqual((f["fideles"], f["lues"], f["erreurs"]["hypothese"]), (2, 3, 1))
        self.assertEqual(f["par_theme"]["fiscalite"]["justes"], 1)
        # taux d'ensemble : contenu seulement, pondere par les strates
        g = b["global"]
        self.assertEqual(g["lues"], b["par_sorte"]["degre"]["publiee"]["lues"] + b["par_sorte"]["portee"]["publiee"]["lues"]
                         + b["par_sorte"]["sens"]["publiee"]["lues"] + rev["lues"])
        self.assertGreater(g["taux_pondere"], g["taux"])                    # la fiche juste u2 pese 30
        lo, hi = g["intervalle"]
        self.assertTrue(lo < g["taux"] < hi)
        self.assertEqual(b["par_theme"]["sante"]["justes"], b["par_theme"]["sante"]["lues"])

    def test_markdown_et_resume_public(self):
        b = RA.bilan(self.donnees, self.refs, self.tires, self.reponses)
        md = RA.markdown(b, {"fiscalite": "Fiscalité"})
        self.assertIn("relecture inachevée", md)
        self.assertIn("Fiscalité", md)
        self.assertIn("Erreurs communes aux deux lecteurs", md)
        r = RA.resume_public(b, {"population": 12, "empreinte_population": "abc"})
        self.assertFalse(r["publiable"])
        self.assertNotIn("Titre-secret", json.dumps(r))                               # aucun titre ni commentaire publie
        self.assertEqual(r["par_sorte"]["degre"]["publiee"], {"justes": 3, "lues": 3})
        complet = {**self.reponses, "aleatoire:u3": {"reponses": self.reponses["aleatoire:u0"]["reponses"]}}
        self.assertTrue(RA.resume_public(RA.bilan(self.donnees, self.refs, self.tires, complet), {})["publiable"])

    def test_evaluer_ecrit_les_sorties(self):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            dossier = racine / RA.DOSSIER
            dossier.mkdir(parents=True)
            (dossier / "donnees.json").write_text(json.dumps(self.donnees), encoding="utf-8")
            (dossier / "references.json").write_text(json.dumps(self.refs), encoding="utf-8")
            (dossier / "tirage.json").write_text(json.dumps({"population": 4, "fiches": [{"uid": u, **t} for u, t in self.tires.items()]}),
                                                 encoding="utf-8")
            (dossier / "reponses.json").write_text(json.dumps(self.reponses), encoding="utf-8")
            b, md = RA.evaluer(racine)
            self.assertTrue((racine / RA.DOC).exists())
            self.assertTrue((dossier / "bilan.json").exists())
            resume = json.loads((racine / RA.RESUME).read_text(encoding="utf-8"))
            self.assertEqual((resume["relues"], resume["publiable"]), (3, False))


if __name__ == "__main__":
    unittest.main()
