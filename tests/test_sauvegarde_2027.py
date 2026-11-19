"""Tests hors ligne de la sauvegarde des donnees non versionnees."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import boussole_2027 as BO
import sauvegarde_2027 as S


class SauvegardeTests(unittest.TestCase):
    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.tmp = Path(temporaire.name)
        self.racine = self.tmp / "projet"
        self.dest = self.tmp / "ailleurs"
        fichiers = {"donnees/base_2027.json": '{"mesures": []}', "donnees/cache_lecture_q2_2027.json": "{}" * 500,
                    "donnees/base.lock": "123", "donnees/x.tmp": "t", "corpus_programmes/manifest.json": "{}",
                    "corpus_programmes/documents/abc.bin": "%PDF", "runs/2026-11-19_1200.md": "# bilan",
                    "logs/llm_1.jsonl": "{}", "archives/donnees/cache_scores.json": "{}", ".env": "SECRET=1",
                    "donnees/.env.local": "SECRET=2", "web/page.html": "<p>"}
        for chemin, texte in fichiers.items():
            (self.racine / chemin).parent.mkdir(parents=True, exist_ok=True)
            (self.racine / chemin).write_text(texte, encoding="utf-8")

    def noms(self, archive):
        with zipfile.ZipFile(archive) as z:
            return set(z.namelist())

    def test_archive_contains_data_only_and_is_verified(self):
        rapport = S.sauvegarder(self.racine, self.dest, horodatage="20261119_120000")
        archive = Path(rapport["archive"])
        self.assertEqual(archive.name, "boussole_sauvegarde_20261119_120000.zip")
        self.assertTrue(rapport["verifiee"])
        self.assertEqual(self.noms(archive), {"donnees/base_2027.json", "donnees/cache_lecture_q2_2027.json",
                                              "corpus_programmes/manifest.json", "corpus_programmes/documents/abc.bin",
                                              "runs/2026-11-19_1200.md", S.MANIFESTE})
        with zipfile.ZipFile(archive) as z:
            manifeste = json.loads(z.read(S.MANIFESTE))
            base = z.read("donnees/base_2027.json")
        entree = next(f for f in manifeste["fichiers"] if f["chemin"] == "donnees/base_2027.json")
        self.assertEqual(entree["sha256"], hashlib.sha256(base).hexdigest())
        self.assertEqual(S.verifier(archive)["fichiers"], 5)
        self.assertFalse(list(self.dest.glob("*.partiel")))

    def test_options_add_logs_and_archives(self):
        rapport = S.sauvegarder(self.racine, self.dest, journaux=True, archives=True, horodatage="20261119_120000")
        noms = self.noms(rapport["archive"])
        self.assertIn("logs/llm_1.jsonl", noms)
        self.assertIn("archives/donnees/cache_scores.json", noms)

    def test_trial_writes_nothing(self):
        rapport = S.sauvegarder(self.racine, self.dest, essai=True)
        self.assertEqual(rapport["fichiers"], 5)
        self.assertEqual(set(rapport["octets_par_dossier"]), {"donnees", "corpus_programmes", "runs"})
        self.assertFalse(self.dest.exists())

    def test_rotation_keeps_newest_and_ignores_other_files(self):
        self.dest.mkdir()
        (self.dest / "notes.txt").write_text("a garder", encoding="utf-8")
        for stamp in ("20261101_000000", "20261102_000000", "20261103_000000"):
            S.sauvegarder(self.racine, self.dest, garder=2, horodatage=stamp)
        restantes = sorted(p.name for p in self.dest.iterdir())
        self.assertEqual(restantes, ["boussole_sauvegarde_20261102_000000.zip",
                                     "boussole_sauvegarde_20261103_000000.zip", "notes.txt"])

    def test_destination_inside_saved_folder_is_refused(self):
        with self.assertRaisesRegex(ValueError, "dossier sauvegarde"):
            S.sauvegarder(self.racine, self.racine / "donnees" / "copies")
        self.assertTrue(any("meme disque" in a for a in S.sauvegarder(self.racine, self.dest, essai=True)["avertissements"]))

    def test_corrupted_archive_is_detected(self):
        archive = Path(S.sauvegarder(self.racine, self.dest, horodatage="20261119_120000")["archive"])
        with patch.object(zipfile.ZipFile, "testzip", return_value="donnees/base_2027.json"):
            with self.assertRaisesRegex(ValueError, "corrompue"):
                S.verifier(archive)
        contenu = archive.read_bytes()
        archive.write_bytes(contenu[:len(contenu) // 2])  # copie interrompue
        with self.assertRaises(zipfile.BadZipFile):
            S.verifier(archive)

    def test_failed_verification_keeps_older_archives(self):
        S.sauvegarder(self.racine, self.dest, garder=1, horodatage="20261101_000000")
        with patch.object(S, "verifier", side_effect=ValueError("archive corrompue")):
            with self.assertRaises(ValueError):
                S.sauvegarder(self.racine, self.dest, garder=1, horodatage="20261102_000000")
        self.assertEqual([p.name for p in self.dest.iterdir()], ["boussole_sauvegarde_20261101_000000.zip"])

    def lancer(self, *arguments):
        sortie = io.StringIO()
        with patch.object(sys, "argv", ["boussole_2027.py", "--racine", str(self.racine), *arguments]), \
                contextlib.redirect_stdout(sortie):
            code = BO.main()
        return code, sortie.getvalue()

    def test_command_remembers_destination_and_lists(self):
        code, _ = self.lancer("sauvegarder")
        self.assertEqual(code, 2)  # aucune destination
        code, texte = self.lancer("sauvegarder", "--destination", str(self.dest), "--memoriser", "--garder", "3")
        self.assertEqual(code, 0, texte)
        self.assertIn("Sauvegarde verifiee", texte)
        self.assertEqual(S.lire_config(self.racine), [(self.dest, 3)])
        self.assertFalse((self.racine / ".boussole.lock").exists())
        code, texte = self.lancer("sauvegarder", "--lister")
        self.assertIn("1 archive(s)", texte)
        archive = next(self.dest.glob("*.zip"))
        code, texte = self.lancer("sauvegarder", "--verifier", str(archive))
        self.assertEqual((code, json.loads(texte)["fichiers"]), (0, 6))  # dont la configuration memorisee (donnees/)

    def test_command_refuses_while_a_run_holds_the_lock(self):
        (self.racine / ".boussole_chaine.lock").write_text("1", encoding="utf-8")
        code, _ = self.lancer("sauvegarder", "--destination", str(self.dest))
        self.assertEqual(code, 2)
        self.assertFalse(self.dest.exists())

    def test_second_destination_gets_verified_copy_with_its_own_rotation(self):
        nuage = self.tmp / "nuage"
        for stamp in ("20261101_000000", "20261102_000000", "20261103_000000"):
            rapport = S.sauvegarder(self.racine, [(self.dest, 3), (nuage, 2)], horodatage=stamp)
        self.assertEqual(len(list(self.dest.glob("*.zip"))), 3)
        self.assertEqual(sorted(p.name for p in nuage.iterdir()), ["boussole_sauvegarde_20261102_000000.zip",
                                                                   "boussole_sauvegarde_20261103_000000.zip"])
        self.assertEqual(rapport["copies"][0]["supprimees"], ["boussole_sauvegarde_20261101_000000.zip"])
        self.assertEqual(S.verifier(nuage / "boussole_sauvegarde_20261103_000000.zip")["fichiers"], 5)

    def test_failed_copy_is_reported_and_primary_kept(self):
        with patch.object(S.shutil, "copyfile", side_effect=OSError("OneDrive indisponible")):
            rapport = S.sauvegarder(self.racine, [self.dest, self.tmp / "nuage"], horodatage="20261119_120000")
        self.assertTrue(Path(rapport["archive"]).exists())
        self.assertIn("OneDrive indisponible", rapport["copies"][0]["erreur"])
        self.assertIn("COPIE ECHOUEE", S.resume_texte(rapport))
        self.assertFalse(list((self.tmp / "nuage").glob("*")))

    def test_invalid_config_is_rejected(self):
        (self.racine / S.CONFIG).write_text(json.dumps({"destination": "E:/x"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            S.lire_config(self.racine)
        (self.racine / S.CONFIG).write_text(json.dumps({"destinations": [{"chemin": "E:/x", "garder": 0}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            S.lire_config(self.racine)

    def test_end_of_chain_hook(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            self.assertIsNone(S.apres_chaine(self.racine))
            S.ecrire_config(self.racine, [(self.dest, 2), (self.tmp / "nuage", 1)])
            self.assertTrue(S.apres_chaine(self.racine))
            for archive in self.dest.glob("*.zip"):  # meme seconde : meme nom d'archive
                archive.unlink()
            with patch.object(S.shutil, "copyfile", side_effect=OSError("hors ligne")):
                self.assertFalse(S.apres_chaine(self.racine))
            S.ecrire_config(self.racine, [(self.racine / "runs" / "copies", 2)])
            self.assertFalse(S.apres_chaine(self.racine))
        self.assertIn("SAUVEGARDE ECHOUEE", sortie.getvalue())
        self.assertIn("COPIE ECHOUEE", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
