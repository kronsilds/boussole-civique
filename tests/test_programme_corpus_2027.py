"""Tests hors ligne de la chaine documents -> propositions -> scoring."""
from __future__ import annotations

import io
import base64
import json
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import pipeline_scoring_2027 as pipeline
import programme_corpus_2027 as corpus
import scoring_context_2027 as context
from llm_logging_2027 import LLMJournal
from test_pipeline_scoring_2027 import answers
from pypdf import PdfReader, PdfWriter

QUOTE = "Nous proposons de construire cent logements publics par an pour les familles modestes."
HTML = ("<!doctype html><html><body><nav>Navigation non pertinente</nav><main>"
        "<h1>Programme 2027</h1><h2>Logement</h2><p>" + QUOTE + "</p>"
        "<script>Instructions malveillantes ignorees</script></main></body></html>").encode()


class Download(io.BytesIO):
    def __init__(self, content=HTML, content_type="text/html; charset=utf-8"):
        super().__init__(content)
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def geturl(self):
        return "https://example.org/programme"


def source_data():
    return {
        "meta": {"source_generated_at": "2026-11-03T00:00:00Z"},
        "candidates": [{"id": "test", "name": "Candidat Test",
                        "program": {"main_url": "https://example.org/programme", "title": "Programme 2027",
                                    "format": "page_web", "published_date": "2026-10-01",
                                    "thematic_links": [{"url": "https://example.org/programme#logement",
                                                        "title": "Logement", "theme": "logement", "format": "page_web"}]}}],
        "themes": [{"id": "logement", "label": "Logement"}],
        "proposals": [{"id": "legacy", "candidate_id": "test"}],
        "context": {"checked": "2026-11-03", "themes": {}}, "budgets": {},
    }


def extraction_result(chunk):
    segment = next(s for s in chunk["segments"] if QUOTE in s["text"])
    return {"proposals": [{"candidate_id": "test", "title": "Construire des logements publics",
                           "description": "Construire cent logements publics par an pour les familles modestes.",
                           "theme_id": "logement", "segment_id": segment["id"], "quote": QUOTE}]}

def pdf_fixture(text=QUOTE):
    instructions = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(instructions)} >>\nstream\n".encode() + instructions + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)

def ocr_response(text=QUOTE):
    return {"id": "gen-ocr-test", "choices": [{"finish_reason": "stop", "message": {
        "content": "Texte invente par le modele, a ne jamais utiliser.",
        "annotations": [{"type": "file", "file": {"hash": "parsed-file-hash", "name": "page.pdf",
                                                 "content": [{"type": "text", "text": text}]}}],
    }}]}


class CorpusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = source_data()
        self.manifest = corpus.load_manifest(self.root)
        self.ids = corpus.inventory(self.data, self.manifest, [])
        self.themes = {"logement": "Logement"}
        self.journal = LLMJournal(self.root / "llm.jsonl", secrets=("test-key",))
        self.addCleanup(self.journal.close)

    def collect(self):
        with patch("urllib.request.urlopen", return_value=Download()):
            result = corpus.collect(self.root, self.manifest, self.ids, pause=0)
        self.assertEqual(result["downloaded"], 1)

    def extract(self, max_calls=1):
        def fake_api(request, *args, **kwargs):
            payload = json.loads(request.data)
            self.assertNotIn("tools", payload)
            self.assertEqual(payload["model"], "example/extractor")
            model_input = json.loads(payload["messages"][0]["content"].split("\n")[-1])
            result = extraction_result(model_input["chunk"])
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        with patch.object(corpus, "request_json", side_effect=fake_api) as api:
            counts = corpus.extract_proposals(self.root, self.manifest, self.ids, self.themes,
                                              "example/extractor", "test-key", max_calls, self.journal)
        return counts, api.call_count

    def test_inventory_deduplicates_fragments_and_preserves_bindings(self):
        self.assertEqual(len(self.ids), 1)
        doc = self.manifest["documents"][self.ids[0]]
        self.assertEqual(len(doc["bindings"]), 2)
        self.assertEqual(doc["url"], "https://example.org/programme")
        self.assertEqual(len(corpus.inventory(self.data, self.manifest, [])), 1)
        self.assertEqual(len(doc["bindings"]), 2)
        with self.assertRaises(ValueError):
            corpus.inventory(self.data, self.manifest, ["unknown"])

    def test_html_text_has_headings_and_no_scripts_or_navigation(self):
        kind, segments = corpus.extract_text(HTML, "text/html", "utf-8")
        self.assertEqual(kind, "html")
        text = " ".join(s["text"] for s in segments)
        self.assertIn(QUOTE, text)
        self.assertNotIn("malveillantes", text)
        self.assertNotIn("Navigation", text)
        quote = next(s for s in segments if s["text"] == QUOTE)
        self.assertEqual(quote["heading"], "Logement")

    def test_pdf_extracts_real_text_with_page_numbers(self):
        kind, segments = corpus.extract_text(pdf_fixture(), "application/pdf", None)
        self.assertEqual(kind, "pdf")
        self.assertEqual(segments[0]["text"], QUOTE)
        self.assertEqual(segments[0]["page"], 1)
        with self.assertRaisesRegex(ValueError, "OCR"):
            corpus.extract_text(pdf_fixture(""), "application/pdf", None)

    def test_real_pdf_download_export_keeps_page_citation(self):
        with patch("urllib.request.urlopen", return_value=Download(pdf_fixture(), "application/pdf")):
            corpus.collect(self.root, self.manifest, self.ids, pause=0)
        self.extract()
        result = corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        self.assertEqual(result["proposals"][0]["source_evidence"][0]["page"], 1)
        self.assertEqual(result["proposals"][0]["source_url"], "https://example.org/programme#page=1")

    def test_collection_reuses_download_and_tracks_refresh_errors(self):
        self.collect()
        with patch("urllib.request.urlopen", side_effect=AssertionError("cache only")):
            self.assertEqual(corpus.collect(self.root, self.manifest, self.ids, pause=0)["reused"], 1)
        doc = self.manifest["documents"][self.ids[0]]
        prior_hash = doc["content_hash"]
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("outage")):
            result = corpus.collect(self.root, self.manifest, self.ids, refresh=True, pause=0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(doc["status"], "error")
        self.assertEqual(doc["content_hash"], prior_hash)
        self.assertTrue(corpus.corpus_path(self.root, doc["raw_path"]).exists())
        with self.assertRaises(ValueError):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)

    def test_refresh_ignores_raw_html_noise_when_text_is_unchanged(self):
        self.collect()
        self.extract()
        doc = self.manifest["documents"][self.ids[0]]
        prior = {k: doc[k] for k in ("content_hash", "raw_path", "text_path", "text_hash")}
        noisy = HTML if isinstance(HTML, bytes) else HTML.encode()
        noisy = noisy.replace(b"</body>", b"<!-- jeton anti-bot 123 --></body>")
        self.assertNotEqual(noisy, HTML if isinstance(HTML, bytes) else HTML.encode())
        with patch("urllib.request.urlopen", return_value=Download(noisy)):
            result = corpus.collect(self.root, self.manifest, self.ids, refresh=True, pause=0)
        self.assertEqual(result["downloaded"], 0)
        self.assertEqual({k: doc[k] for k in prior}, prior)
        self.assertTrue(doc["extraction"]["complete"])
        counts, calls = self.extract(max_calls=0)
        self.assertEqual(counts["deferred_chunks"], 0)

    def test_refresh_with_real_text_change_invalidates_extraction(self):
        self.collect()
        self.extract()
        doc = self.manifest["documents"][self.ids[0]]
        changed = (HTML if isinstance(HTML, bytes) else HTML.encode()).replace(QUOTE.encode(), QUOTE.encode() + b" Nouvelle mesure.")
        with patch("urllib.request.urlopen", return_value=Download(changed)):
            result = corpus.collect(self.root, self.manifest, self.ids, refresh=True, pause=0)
        self.assertEqual(result["downloaded"], 1)
        self.assertNotIn("extraction", doc)

    def test_download_size_and_unknown_formats_are_rejected(self):
        with patch.object(corpus, "MAX_DOWNLOAD_BYTES", 10), patch("urllib.request.urlopen", return_value=Download()):
            self.assertEqual(corpus.collect(self.root, self.manifest, self.ids, pause=0)["failed"], 1)
        with self.assertRaises(ValueError):
            corpus.extract_text(b"audio binary", "audio/mpeg", None)
        with self.assertRaises(ValueError):
            corpus.corpus_path(self.root, "..\\outside")

    def test_video_is_explicitly_unsupported_without_network(self):
        doc = self.manifest["documents"][self.ids[0]]
        for binding in doc["bindings"]:
            binding["format"] = "video"
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")):
            result = corpus.collect(self.root, self.manifest, self.ids, pause=0)
        self.assertEqual(result["unsupported"], 1)
        self.assertEqual(doc["status"], "unsupported")

    def test_chunking_covers_all_text_with_locators(self):
        text = ("Un engagement long. " * 1800).strip()
        chunks = corpus.document_chunks({"segments": [{"id": "s00000", "text": text, "page": 2, "heading": "Chapitre"}]})
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(sum(len(s["text"]) for s in chunk["segments"]), corpus.CHUNK_CHARACTERS)
            for segment in chunk["segments"]:
                self.assertEqual(text[segment["offset"]:segment["offset"] + len(segment["text"])], segment["text"])
                self.assertEqual(segment["page"], 2)
        last = chunks[-1]["segments"][-1]
        self.assertEqual(last["offset"] + len(last["text"]), len(text))

    def test_end_to_end_export_is_source_based_and_does_not_replace_reference(self):
        self.collect()
        counts, calls = self.extract()
        self.assertEqual((counts["calls"], calls), (1, 1))
        self.assertTrue(self.manifest["documents"][self.ids[0]]["extraction"]["complete"])
        result = corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        self.assertEqual(len(result["proposals"]), 1)
        p = result["proposals"][0]
        self.assertTrue(p["id"].startswith("corpus-"))
        self.assertEqual(p["source_evidence"][0]["quote"], QUOTE)
        self.assertEqual(p["source_evidence"][0]["heading"], "Logement")
        self.assertNotIn("ideology", p)
        self.assertEqual(self.data["proposals"][0]["id"], "legacy")
        self.assertEqual(result["meta"]["reference_proposal_count"], 1)
        self.assertFalse(result["meta"]["corpus_partial"])
        base = {"evidence": [], "rules": context.CONTEXT_RULES}
        enriched = corpus.with_corpus_evidence(p, base)
        self.assertEqual(enriched["evidence"][0]["text"], QUOTE)
        self.assertNotIn("document_outline", enriched["programme_corpus"]["coverage"][0])
        self.assertNotIn("programme_importance", enriched["evidence"][0]["dimensions"])
        position = next(e for e in enriched["evidence"] if e["id"].endswith("-position"))
        self.assertEqual(position["dimensions"], ["programme_importance"])
        self.assertIn("Signaux de position", position["text"])
        self.assertIn("1 passage(s) de 1 document(s)", position["text"])
        self.assertTrue(context.importance_evidence({"scoring_context": enriched}, "programme_importance"))
        without_position = {**p, "source_evidence": [{k: v for k, v in e.items() if k != "position"} for e in p["source_evidence"]]}
        bare = corpus.with_corpus_evidence(without_position, base)
        self.assertFalse(any(e["id"].endswith("-position") for e in bare["evidence"]))
        self.assertFalse(context.importance_evidence({"scoring_context": bare}, "programme_importance"))
        self.assertEqual({k: p["repetition"][k] for k in ("similar_proposals", "documents", "related_proposals")},
                         {"similar_proposals": 0, "documents": 1, "related_proposals": 0})
        self.assertEqual(p["repetition"]["theme_share_pct"], 100.0)
        repeated = corpus.position_signal({**p, "repetition": {"similar_proposals": 2, "documents": 3}})
        self.assertIn("Formulations proches dans 2 autre(s) proposition(s)", repeated["text"])
        corpus.save_json(self.root / "proposals.json", result)
        ingested = pipeline.ingest_json(self.root / "proposals.json")
        self.assertEqual(ingested["proposals"][0]["source_evidence"], p["source_evidence"])

    def test_extraction_reuses_cache_and_model_change_invalidates(self):
        self.collect()
        self.extract()
        with patch.object(corpus, "request_json", side_effect=AssertionError("cache only")):
            counts = corpus.extract_proposals(self.root, self.manifest, self.ids, self.themes,
                                              "example/extractor", "", 0, self.journal)
        self.assertEqual(counts["reused_chunks"], 1)
        counts = corpus.extract_proposals(self.root, self.manifest, self.ids, self.themes,
                                          "example/other-model", "", 0, self.journal)
        self.assertEqual(counts["deferred_chunks"], 1)
        with self.assertRaises(ValueError):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)

    def test_citations_and_candidates_are_validated(self):
        self.collect()
        doc = self.manifest["documents"][self.ids[0]]
        document = json.loads(corpus.corpus_path(self.root, doc["text_path"]).read_text(encoding="utf-8"))
        chunk = corpus.document_chunks(document)[0]
        for field, value in (("quote", "Cette citation a ete inventee et n'existe dans aucun texte."),
                             ("candidate_id", "invented"), ("theme_id", "invented"),
                             ("segment_id", "invented"), ("ideology", -100)):
            result = extraction_result(chunk)
            result["proposals"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                corpus.validate_proposals(result, doc, chunk, self.themes)

    def test_tolerant_quote_matching_stores_the_exact_source_text(self):
        source_a = "Preambule sans lien. Nous voulons arra- cher le pouvoir aux speculateurs pour la spéciﬁcité nationale."
        source_b = "Autre segment : Nous baisserons le prix de l’électricité de 30 % pour tous les foyers français."
        doc = {"id": "d", "content_hash": "h", "text_hash": "t",
               "bindings": [{"candidate_id": "test", "candidate_name": "Candidat Test"}]}
        chunk = {"segments": [{"id": "s1", "text": source_a, "offset": 0, "page": 1},
                              {"id": "s2", "text": source_b, "offset": 100, "page": 2}]}

        def proposal(quote, segment_id="s1"):
            return {"candidate_id": "test", "theme_id": "logement", "title": "T", "description": "D",
                    "segment_id": segment_id, "quote": quote}

        result = {"proposals": [
            proposal("Nous voulons arracher le pouvoir aux speculateurs pour la spécificité nationale."),
            proposal("Nous baisserons le prix de l'électricité de 30 % pour tous les foyers français.", "s1"),
            proposal("Nous supprimerons tous les impots sur le revenu et sur le patrimoine immediatement.")]}
        rejected = []
        kept = corpus.validate_proposals(result, doc, chunk, {"logement": "Logement"}, rejected)
        self.assertEqual(len(kept), 2)
        self.assertEqual(len(rejected), 1)
        first, second = (k["evidence"] for k in kept)
        self.assertEqual(first["quote"], source_a[source_a.index("Nous voulons"):source_a.index("nationale.") + 10])
        self.assertEqual(second["segment_id"], "s2")
        self.assertEqual(second["page"], 2)
        self.assertEqual(source_b[second["start"] - 100:second["end"] - 100], second["quote"])
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, {"logement": "Logement"})

    def test_exact_candidate_name_is_mapped_to_its_id_but_other_names_stay_rejected(self):
        self.collect()
        doc = self.manifest["documents"][self.ids[0]]
        document = json.loads(corpus.corpus_path(self.root, doc["text_path"]).read_text(encoding="utf-8"))
        chunk = corpus.document_chunks(document)[0]
        result = extraction_result(chunk)
        result["proposals"][0]["candidate_id"] = "  candidat TEST "
        kept = corpus.validate_proposals(result, doc, chunk, self.themes)
        self.assertEqual(kept[0]["candidate_id"], "test")
        result["proposals"][0]["candidate_id"] = "Candidat Inconnu"
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, self.themes)

    def test_inexact_quote_drops_only_that_proposal_when_rejections_are_collected(self):
        self.collect()
        doc = self.manifest["documents"][self.ids[0]]
        document = json.loads(corpus.corpus_path(self.root, doc["text_path"]).read_text(encoding="utf-8"))
        chunk = corpus.document_chunks(document)[0]
        result = extraction_result(chunk)
        bad = dict(result["proposals"][0], title="Citation alteree",
                   quote="Cette citation a ete inventee et n'existe dans aucun texte.")
        result["proposals"].append(bad)
        rejected = []
        kept = corpus.validate_proposals(result, doc, chunk, self.themes, rejected)
        self.assertEqual(len(kept), len(result["proposals"]) - 1)
        self.assertEqual([r["title"] for r in rejected], ["Citation alteree"])
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, self.themes)
        result["proposals"][0]["theme_id"] = "invented"
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, self.themes)
        rejected = []
        kept = corpus.validate_proposals(result, doc, chunk, self.themes, rejected)
        self.assertEqual(len(kept), 0)
        self.assertEqual({r["reason"] for r in rejected}, {"candidat/theme inconnu", "citation non retrouvee"})
        result["proposals"][0]["ideology"] = -100
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, self.themes, [])

    def test_short_quotes_need_15_characters_in_tolerant_mode_only(self):
        doc = {"id": "d", "content_hash": "h", "text_hash": "t",
               "bindings": [{"candidate_id": "test", "candidate_name": "Candidat Test"}]}
        chunk = {"segments": [{"id": "s1", "text": "Programme. • Abroger le 49.3 et revitaliser tout le parlement.",
                               "offset": 0, "page": 1}]}
        result = {"proposals": [{"candidate_id": "test", "theme_id": "logement", "title": "T", "description": "D",
                                 "segment_id": "s1", "quote": "Abroger le 49.3"},
                                {"candidate_id": "test", "theme_id": "logement", "title": "U", "description": "D",
                                 "segment_id": "s1", "quote": "Programme."}]}
        rejected = []
        kept = corpus.validate_proposals(result, doc, chunk, {"logement": "Logement"}, rejected)
        self.assertEqual([k["evidence"]["quote"] for k in kept], ["Abroger le 49.3"])
        self.assertEqual(len(rejected), 1)
        with self.assertRaises(ValueError):
            corpus.validate_proposals(result, doc, chunk, {"logement": "Logement"})

    def test_source_overrides_replace_and_exclude_documents_without_touching_the_upstream_data(self):
        data = source_data()
        manifest = corpus.load_manifest(self.root)
        replaced = corpus.inventory(data, manifest, [], {"https://example.org/programme": "https://example.org/nouveau"})
        urls = {manifest["documents"][i]["url"] for i in replaced}
        self.assertEqual(urls, {"https://example.org/nouveau"})
        manifest = corpus.load_manifest(self.root)
        self.assertEqual(corpus.inventory(data, manifest, [], None, {"https://example.org/programme"}), [])
        path = self.root / "sources.json"
        path.write_text(json.dumps({"replace_urls": {"https://a.org/x": "https://a.org/y"},
                                    "exclude_urls": ["https://b.org/z"]}), encoding="utf-8")
        self.assertEqual(corpus.load_source_overrides(path), ({"https://a.org/x": "https://a.org/y"}, {"https://b.org/z"}))
        self.assertEqual(corpus.load_source_overrides(self.root / "absent.json"), ({}, set()))
        path.write_text(json.dumps({"replace_urls": {"nope": "https://a.org/y"}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            corpus.load_source_overrides(path)

    def test_export_refuses_tampered_citations_or_changed_document(self):
        self.collect()
        self.extract()
        doc = self.manifest["documents"][self.ids[0]]
        record = doc["extraction"]["chunks"][0]
        path = corpus.corpus_path(self.root, record["path"])
        cached = json.loads(path.read_text(encoding="utf-8"))
        cached["proposals"][0]["evidence"]["quote"] = "Invented quote"
        corpus.save_json(path, cached)
        with self.assertRaisesRegex(ValueError, "Citation"):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        doc["content_hash"] = "changed"
        with self.assertRaisesRegex(ValueError, "incomplet"):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)

    def test_incomplete_chunk_budget_never_looks_complete(self):
        self.collect()
        with patch.object(corpus, "CHUNK_CHARACTERS", 90):
            counts, calls = self.extract(max_calls=0)
        self.assertEqual(calls, 0)
        self.assertGreater(counts["deferred_chunks"], 0)
        with self.assertRaisesRegex(ValueError, "incomplet"):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        with self.assertRaisesRegex(ValueError, "Aucune proposition"):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data, allow_partial=True)

    def test_full_rubrics_are_available_for_every_score(self):
        rubric = pipeline.scoring_rubric()
        self.assertEqual(set(rubric), set(context.DIMENSIONS))
        self.assertEqual([a["score"] for a in rubric["ideology"]["anchors"]], [-100, -50, 0, 50, 100])
        self.assertEqual(len(rubric["feasibility"]["anchors"]), 5)
        self.assertEqual(len(rubric["media_importance"]["anchors"]), 4)

    def test_exported_corpus_reaches_jev_with_text_and_page_provenance(self):
        self.collect()
        self.extract()
        result = corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        path = self.root / "proposals.json"
        corpus.save_json(path, result)
        args = ["pipeline", "--input", str(path), "--llm", "--provider", "openrouter",
                "--model", "~typesafe/jev-latest", "--batch-size", "1",
                "--context-file", str(self.root / "context.json"), "--cache-file", str(self.root / "scores.json"),
                "--out", str(self.root / "scored.json"), "--review-queue", str(self.root / "review.json"),
                "--llm-log-file", str(self.root / "scoring.jsonl")]
        api_response = {"answers": answers(), "model": "typesafe/jev-1.14"}
        with patch.object(sys, "argv", args), patch.object(pipeline, "load_env_file"), \
                patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True), \
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(api_response).encode())) as http:
            self.assertEqual(pipeline.main(), 0)
        payload = json.loads(http.call_args.args[0].data)
        state = payload["state"]
        self.assertEqual(state["scoring_context"]["evidence"][0]["text"], QUOTE)
        self.assertNotIn("programme_corpus", state["scoring_context"])
        for forbidden in ("candidate_id", "source_title", "source_url"):
            self.assertNotIn(forbidden, state)
        self.assertNotIn("programme", state["scoring_context"])
        self.assertNotIn("candidate_budget", state["scoring_context"])
        self.assertNotIn("source_url", json.dumps(state["scoring_context"]["evidence"]))
        scored = json.loads((self.root / "scored.json").read_text(encoding="utf-8"))
        self.assertEqual(scored["meta"]["llm_scored_new_or_changed"], 1)
        self.assertEqual(scored["proposals"][0]["source_evidence"][0]["quote"], QUOTE)
        self.assertEqual(scored["meta"]["web_calls"], 0)

    def test_partial_export_has_explicit_coverage_not_success_shaped_defaults(self):
        self.collect()
        self.extract()
        self.manifest["documents"][self.ids[0]]["extraction"]["complete"] = False
        with self.assertRaises(ValueError):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        result = corpus.export_proposals(self.root, self.manifest, self.ids, self.data, allow_partial=True)
        self.assertTrue(result["meta"]["corpus_partial"])
        self.assertFalse(result["proposals"][0]["programme_context"]["coverage"][0]["complete"])

    def test_selecting_one_document_does_not_claim_full_programme_coverage(self):
        self.collect()
        self.extract()
        self.data["candidates"][0]["program"]["thematic_links"].append({
            "url": "https://example.org/other-document", "theme": "logement", "format": "page_web", "title": "Complement"})
        with self.assertRaisesRegex(ValueError, "non selectionnes"):
            corpus.export_proposals(self.root, self.manifest, self.ids, self.data)
        result = corpus.export_proposals(self.root, self.manifest, self.ids, self.data, allow_partial=True)
        self.assertTrue(result["meta"]["corpus_partial"])
        self.assertEqual(result["meta"]["corpus_unselected_document_count"], 1)
        self.assertEqual(result["proposals"][0]["programme_context"]["coverage"][-1]["status"], "not_selected")

    def collect_pdf(self, text=""):
        with patch("urllib.request.urlopen", return_value=Download(pdf_fixture(text), "application/pdf")):
            corpus.collect(self.root, self.manifest, self.ids, pause=0)

    def test_local_reparse_uses_only_cached_bytes_and_keeps_unchanged_extraction(self):
        self.collect_pdf(QUOTE)
        self.extract()
        doc = self.manifest["documents"][self.ids[0]]
        old_extraction = doc["extraction"]
        with patch("urllib.request.urlopen", side_effect=AssertionError("local only")):
            result = corpus.reparse_local(self.root, self.manifest, self.ids)
        self.assertEqual(result["reparsed"], 1)
        self.assertEqual(result["changed"], 0)
        self.assertIs(doc["extraction"], old_extraction)

    def test_local_changed_text_invalidates_old_extraction(self):
        self.collect_pdf(QUOTE)
        self.extract()
        doc = self.manifest["documents"][self.ids[0]]
        changed = [{"page": 1, "heading": None, "text": QUOTE + " Texte corrige.", "text_missing": False}]
        with patch.object(corpus, "extract_text", return_value=("pdf", changed)):
            result = corpus.reparse_local(self.root, self.manifest, self.ids)
        self.assertEqual(result["changed"], 1)
        self.assertNotIn("extraction", doc)

    def test_ocr_is_opt_in_and_counts_deferred_pages(self):
        self.collect_pdf()
        doc = self.manifest["documents"][self.ids[0]]
        self.assertEqual(doc["text_incomplete_pages"], [1])
        with patch.object(corpus, "request_json", side_effect=AssertionError("no paid request")):
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "", 0, "mistral-ocr", self.journal)
        self.assertEqual(counts["calls"], 0)
        self.assertEqual(counts["deferred_pages"], 1)
        self.assertEqual(doc["text_incomplete_pages"], [1])

    def test_ocr_uses_parser_annotations_not_model_generated_text(self):
        self.collect_pdf()
        with patch.object(corpus, "request_json", return_value=ocr_response()) as api:
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                                      "mistral-ocr", self.journal)
        self.assertEqual(counts["calls"], 1)
        self.assertEqual(counts["parsed_pages"], 1)
        payload = json.loads(api.call_args.args[0].data)
        self.assertEqual(payload["plugins"], [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}])
        self.assertNotIn("tools", payload)
        data_url = payload["messages"][0]["content"][1]["file"]["file_data"]
        reader = PdfReader(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))
        self.assertEqual(len(reader.pages), 1)
        doc = self.manifest["documents"][self.ids[0]]
        text = json.loads(corpus.corpus_path(self.root, doc["text_path"]).read_text(encoding="utf-8"))
        self.assertEqual(text["segments"][0]["text"], QUOTE)
        self.assertEqual(text["segments"][0]["source_method"], "openrouter:mistral-ocr")
        self.assertNotIn("invente", text["segments"][0]["text"])
        self.assertEqual(doc["text_incomplete_pages"], [])
        self.assertEqual(text["segments"][0]["page"], 1)

    def test_original_page_number_is_preserved_when_sending_single_page_pdf(self):
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(pdf_fixture(QUOTE))).pages[0])
        writer.add_page(PdfReader(io.BytesIO(pdf_fixture(""))).pages[0])
        buffer = io.BytesIO()
        writer.write(buffer)
        with patch("urllib.request.urlopen", return_value=Download(buffer.getvalue(), "application/pdf")):
            corpus.collect(self.root, self.manifest, self.ids, pause=0)
        doc = self.manifest["documents"][self.ids[0]]
        self.assertEqual(doc["text_incomplete_pages"], [2])
        with patch.object(corpus, "request_json", return_value=ocr_response()) as api:
            corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                             "mistral-ocr", self.journal)
        payload = json.loads(api.call_args.args[0].data)
        self.assertTrue(payload["messages"][0]["content"][1]["file"]["filename"].endswith("-page-2.pdf"))
        text = json.loads(corpus.corpus_path(self.root, doc["text_path"]).read_text(encoding="utf-8"))
        self.assertEqual(text["segments"][1]["page"], 2)
        self.assertEqual(text["segments"][1]["text"], QUOTE)

    def test_missing_file_annotations_cannot_be_replaced_by_model_knowledge(self):
        self.collect_pdf()
        result = ocr_response()
        result["choices"][0]["message"]["annotations"] = []
        with patch.object(corpus, "request_json", return_value=result):
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                                      "mistral-ocr", self.journal)
        self.assertEqual(counts["failed_pages"], 1)
        self.assertEqual(self.manifest["documents"][self.ids[0]]["text_incomplete_pages"], [1])

    def test_empty_ocr_is_cached_but_never_claimed_to_be_a_verified_blank(self):
        self.collect_pdf()
        with patch.object(corpus, "request_json", return_value=ocr_response("")):
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                                      "mistral-ocr", self.journal)
        self.assertEqual(counts["no_text_pages"], 1)
        self.assertEqual(self.manifest["documents"][self.ids[0]]["text_incomplete_pages"], [1])
        with patch.object(corpus, "request_json", side_effect=AssertionError("no repeat payment")):
            reused = corpus.ocr_pages(self.root, self.manifest, self.ids, "another/model", "", 0,
                                      "mistral-ocr", self.journal)
        self.assertEqual(reused["reused_pages"], 1)
        self.assertEqual(reused["calls"], 0)
        self.assertEqual(reused["no_text_pages"], 1)

    def test_cached_parser_output_is_reused_and_survives_local_reparse(self):
        self.collect_pdf()
        with patch.object(corpus, "request_json", return_value=ocr_response()):
            corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                             "mistral-ocr", self.journal)
        doc = self.manifest["documents"][self.ids[0]]
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
            reparsed = corpus.reparse_local(self.root, self.manifest, self.ids)
        self.assertEqual(reparsed["changed"], 0)
        self.assertEqual(doc["text_incomplete_pages"], [])
        with patch("urllib.request.urlopen", return_value=Download(pdf_fixture(""), "application/pdf")):
            corpus.collect(self.root, self.manifest, self.ids, refresh=True, pause=0)
        self.assertEqual(doc["text_incomplete_pages"], [])

    def test_parsing_annotations_can_be_recovered_from_inference_http_error(self):
        self.collect_pdf()
        annotations = ocr_response()["choices"][0]["message"]["annotations"]
        body = {"error": {"message": "All inference providers failed", "metadata": {"file_annotations": annotations}}}
        error = context.ScoringHTTPError("HTTP 502", body)
        with patch.object(corpus, "request_json", side_effect=error):
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                                      "mistral-ocr", self.journal)
        self.assertEqual(counts["parsed_pages"], 1)
        self.assertEqual(counts["recovered_annotations"], 1)
        self.assertEqual(counts["failed_pages"], 0)

    def test_file_name_wrappers_and_punctuation_are_not_document_content(self):
        self.collect_pdf()
        result = ocr_response()
        result["choices"][0]["message"]["annotations"][0]["file"]["content"] = [
            {"type": "text", "text": '<file name="page-2.pdf">'},
            {"type": "text", "text": "."}, {"type": "text", "text": "</file>"},
        ]
        with patch.object(corpus, "request_json", return_value=result):
            counts = corpus.ocr_pages(self.root, self.manifest, self.ids, "example/model", "test-key", 1,
                                      "mistral-ocr", self.journal)
        self.assertEqual(counts["parsed_pages"], 0)
        self.assertEqual(counts["no_text_pages"], 1)
        self.assertEqual(self.manifest["documents"][self.ids[0]]["text_incomplete_pages"], [1])

    def test_wrapped_parser_text_keeps_only_the_actual_transcript(self):
        self.assertEqual(corpus.ocr_plain_text('<file name="programme.pdf">\n' + QUOTE + "\n</file>"), QUOTE)
        self.assertEqual(corpus.ocr_plain_text('<file name="programme.pdf">.\n</file>'), "")

class StructuralImportanceTests(unittest.TestCase):
    base = {"position_pct": 5, "section_synthese": False, "passages": 1, "documents": 1, "formulations_proches": 0,
            "connexes_pct_du_theme": 0, "part_du_theme_pct": 5.0}

    def test_early_position_beats_middle_and_theme_weight_matters(self):
        early = corpus.structural_importance(self.base)
        middle = corpus.structural_importance({**self.base, "position_pct": 60})
        self.assertGreater(early["position"], middle["position"])
        heavy = corpus.structural_importance({**self.base, "part_du_theme_pct": 15.0})
        light = corpus.structural_importance({**self.base, "part_du_theme_pct": 1.0})
        self.assertGreater(heavy["theme"], light["theme"])
        self.assertGreater(heavy["score"], light["score"])

    def test_repetition_and_synthesis_section_raise_score_within_bounds(self):
        plain = corpus.structural_importance(self.base)["score"]
        boosted = corpus.structural_importance({**self.base, "section_synthese": True, "passages": 3, "documents": 2,
                                                "formulations_proches": 2, "connexes_pct_du_theme": 40})
        self.assertGreater(boosted["score"], plain)
        for part in ("score", "position", "theme", "repetition"):
            self.assertTrue(0 <= boosted[part] <= 100)

    def test_missing_values_are_safe(self):
        self.assertTrue(0 <= corpus.structural_importance({})["score"] <= 100)


if __name__ == "__main__":
    unittest.main()
