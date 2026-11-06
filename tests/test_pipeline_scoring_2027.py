"""Régressions hors ligne : aucune clé ni requête réseau réelle."""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pipeline_scoring_2027 as pipeline
import scoring_context_2027 as context
from llm_logging_2027 import LLMJournal, LLMLogError


def bundle():
    return {
        "version": 2, "generated_at": "2026-11-01T00:00:00Z",
        "themes": [{"id": "economie", "label": "Economie"}],
        "context": {"checked": "2026-11-01", "themes": {
            "economie": [{"label": "PIB", "value": "3000 Md EUR", "source_url": "https://example.org/pib"}],
            "sante": [{"label": "Effectif", "value": "200000"}],
        }},
        "budgets": {"checked": "2026-11-01", "candidates": {"test": {"level": "partiel"}}},
        "candidates": [{"id": "test", "first_name": "A", "last_name": "Test",
                        "main_axes": ["Services publics"], "main_axes_source_url": "https://example.org/axes",
                        "program": {"main_url": "https://example.org/programme", "status": "partiel",
                                    "thematic_links": [{"theme": "sante", "url": "https://example.org/sante"}]}}],
        "measures": {"test": [{"id": f"p{i}", "theme": "economie", "title": f"Mesure {i}",
                               "description": "Depense de 2 milliards d'euros par an.",
                               "source_url": "https://example.org/mesure"} for i in range(3)]},
    }


def evidence(**overrides):
    return {"id": "extrait", "text": "Engagement prioritaire annonce en entretien.",
            "source_url": "https://example.org/entretien", "source_date": "2026-11-01",
            "reviewed_at": context.utc_now().date().isoformat(),
            "dimensions": ["media_importance"], **overrides}


AXES_QUESTIONS = {"has_eco", "eco", "has_soc", "soc", "has_sov", "sov", "has_ouverture", "ouverture", "has_ecolo", "ecolo", "rupture",
                  "income_direction", "legal_instrument", "horizon"}


def answers(confidence=.8, axes=False):
    """Réponses Jev simulées : ancien format (idéologie unique, 6 tags) par défaut, format à axes si axes=True."""
    names = pipeline.jev_questions() if axes else {
        k: v for k, v in pipeline.TYPESAFE_QUESTIONS.items() if k not in AXES_QUESTIONS}
    result = {}
    for name, question in names.items():
        if question["type"] == "score":
            result[name] = {"score": 2, "confidence": confidence}
        elif question["type"] == "noul":
            result[name] = {"probability": .9 if name.startswith("has_") else .05}
        else:
            result[name] = {"choice": next(iter(question["criteria"])), "confidence": confidence}
    return result


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def web_response(dimensions, confidence=.9):
    return {
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"assessments": {
                dim: {"value": -2 if dim == "budget_net_bn_year" else 60, "confidence": confidence,
                      "rationale": "Justification sourcee", "source_urls": ["https://example.org/source"],
                      "source_date": "2026-11-01", "evidence": "Constat public documente",
                      "period": "annual" if dim == "budget_net_bn_year" else None}
                for dim in dimensions
            }}),
            "annotations": [{"type": "url_citation", "url_citation": {
                "url": "https://example.org/source", "title": "Source"}}],
        }}],
    }


class EnvTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / ".env"

    def test_missing_file_leaves_environment_unchanged(self):
        with patch.dict(os.environ, {"LLM_MODEL": "existing"}, clear=True):
            pipeline.load_env_file(self.path)
            self.assertEqual(dict(os.environ), {"LLM_MODEL": "existing"})

    def test_literal_values_quotes_bom_and_blank_keys(self):
        self.path.write_text(
            '# Local\nLLM_PROVIDER=typesafe\nexport LLM_MODEL="jev"\n'
            "TYPESAFE_API_KEY='test#key=literal'\nOPENROUTER_API_KEY=\n"
            'LLM_API_KEY="$NO_EXPANSION"\n',
            encoding="utf-8-sig",
        )
        with patch.dict(os.environ, {}, clear=True):
            pipeline.load_env_file(self.path)
            self.assertEqual(os.environ["LLM_MODEL"], "jev")
            self.assertEqual(os.environ["TYPESAFE_API_KEY"], "test#key=literal")
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "")
            self.assertEqual(os.environ["LLM_API_KEY"], "$NO_EXPANSION")

    def test_existing_environment_takes_priority(self):
        self.path.write_text("LLM_MODEL=file-model\nTYPESAFE_API_KEY=file-test-key\n", encoding="utf-8")
        with patch.dict(os.environ, {"LLM_MODEL": "shell-model", "TYPESAFE_API_KEY": "shell-test-key"}, clear=True):
            pipeline.load_env_file(self.path)
            self.assertEqual(os.environ["LLM_MODEL"], "shell-model")
            self.assertEqual(os.environ["TYPESAFE_API_KEY"], "shell-test-key")

    def test_openrouter_models_are_independent_environment_values(self):
        self.path.write_text("OPENROUTER_SCORING_MODEL=example/score\nOPENROUTER_WEB_MODEL=example/research\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            pipeline.load_env_file(self.path)
            self.assertEqual(os.environ["OPENROUTER_SCORING_MODEL"], "example/score")
            self.assertEqual(os.environ["OPENROUTER_WEB_MODEL"], "example/research")

    def test_invalid_configuration_is_atomic_and_does_not_expose_values(self):
        for invalid in ("invalid-secret-line", "PATH=private-value", "LLM_MODEL='unclosed-secret",
                        "LLM_MODEL=duplicate-secret"):
            self.path.write_text("LLM_MODEL=first\n" + invalid, encoding="utf-8")
            with self.subTest(invalid=invalid), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as raised:
                    pipeline.load_env_file(self.path)
                self.assertIn("ligne 2", str(raised.exception))
                self.assertNotIn(invalid, str(raised.exception))
                self.assertEqual(dict(os.environ), {})

    def test_main_reports_configuration_errors_before_network(self):
        with patch.object(pipeline, "load_env_file", side_effect=ValueError("test configuration")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(pipeline.main(), 2)
            self.assertIn("Erreur de configuration", stderr.getvalue())


class APIErrorTests(unittest.TestCase):
    def test_permanent_error_exposes_message_but_not_api_key(self):
        request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         headers={"Authorization": "Bearer test-secret"})
        error = urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, response({
            "error": {"message": "Use /api/alpha/decisions, not chat. Token test-secret"}
        }))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(context.ScoringAPIError) as raised:
                context.request_json(request, 5)
        self.assertIn("HTTP 400", str(raised.exception))
        self.assertIn("/api/alpha/decisions", str(raised.exception))
        self.assertNotIn("test-secret", str(raised.exception))

    def test_transient_error_retains_provider_message(self):
        error = urllib.error.HTTPError("https://example.org", 503, "Unavailable", {}, response({
            "error": {"message": "Provider overloaded"}
        }))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.URLError) as raised:
                context.request_json(urllib.request.Request("https://example.org"), 5)
        self.assertIn("Provider overloaded", str(raised.exception))

    def test_non_json_error_body_is_not_dumped(self):
        error = urllib.error.HTTPError("https://example.org", 403, "Forbidden", {}, io.BytesIO(b"private echoed data"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(context.ScoringAPIError) as raised:
                context.request_json(urllib.request.Request("https://example.org"), 5)
        self.assertIn("Forbidden", str(raised.exception))
        self.assertNotIn("private echoed data", str(raised.exception))


class JournalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "llm.jsonl"

    def records(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def journal(self):
        journal = LLMJournal(self.path)
        self.addCleanup(journal.close)
        return journal

    def test_raw_results_are_logged_without_headers_keys_or_prompts(self):
        journal = self.journal()
        payload = {"model": "example/model", "max_tokens": 8192,
                   "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}]}
        request = urllib.request.Request("https://user:password@example.org/chat?api_key=query-secret",
                                         data=json.dumps(payload).encode(),
                                         headers={"Authorization": "Bearer synthetic-secret-value"})
        provider_result = {"id": "gen-test", "choices": [{"message": {
            "content": "synthetic-secret-value and Bearer other-secret"}}],
            "api_key": "unknown-secret", "usage": {"completion_tokens": 12}}
        with patch("urllib.request.urlopen", return_value=response(provider_result)):
            returned = context.request_json(request, 5, journal=journal, stage="web", proposal_ids=["p0"])
        self.assertEqual(returned, provider_result)
        records = self.records()
        self.assertEqual([r["event"] for r in records], ["api_request", "api_response"])
        self.assertEqual(records[0]["endpoint"], "https://example.org/chat")
        self.assertEqual(records[0]["proposal_ids"], ["p0"])
        self.assertEqual(records[0]["parameters"]["max_tokens"], 8192)
        self.assertEqual(records[0]["request_id"], records[1]["request_id"])
        self.assertEqual(records[1]["response"]["id"], "gen-test")
        self.assertEqual(records[1]["response"]["usage"]["completion_tokens"], 12)
        text = self.path.read_text(encoding="utf-8")
        for secret in ("synthetic-secret-value", "other-secret", "unknown-secret", "query-secret",
                       "PRIVATE_PROMPT", "password"):
            self.assertNotIn(secret, text)
        self.assertEqual(journal.request_counts, {"web": 1})

    def test_http_errors_keep_provider_body_with_secrets_redacted(self):
        journal = self.journal()
        request = urllib.request.Request("https://example.org/chat", headers={"x-api-key": "synthetic-error-secret"})
        error = urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, response({
            "error": {"message": "Bad request for synthetic-error-secret", "code": 400}
        }))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(context.ScoringAPIError):
                context.request_json(request, 5, journal=journal, stage="primary", proposal_ids=["p0"])
        records = self.records()
        self.assertEqual(records[-1]["event"], "api_error")
        self.assertEqual(records[-1]["http_status"], 400)
        self.assertEqual(records[-1]["response"]["error"]["code"], 400)
        self.assertNotIn("synthetic-error-secret", self.path.read_text(encoding="utf-8"))

    def test_invalid_http_json_is_captured_before_parser_failure(self):
        journal = self.journal()
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"{broken")):
            with self.assertRaises(ValueError):
                context.request_json(urllib.request.Request("https://example.org"), 5, journal=journal)
        record = self.records()[-1]
        self.assertEqual(record["response_text"], "{broken")
        self.assertIn("parse_error", record)

    def test_custom_file_appends_with_separate_run_ids(self):
        first = self.journal()
        first.write("run_start")
        second = self.journal()
        second.write("run_start")
        self.assertEqual(len(self.records()), 2)
        self.assertNotEqual(first.run_id, second.run_id)

    def test_nonfinite_diagnostics_remain_valid_json(self):
        journal = self.journal()
        journal.write("invalid_result", confidence=float("nan"))
        record = self.records()[0]
        self.assertEqual(record["confidence"], {"invalid_number": "nan"})
        json.dumps(record, allow_nan=False)

    def test_log_open_failure_is_explicit(self):
        occupied = self.path.parent / "occupied"
        occupied.write_text("keep", encoding="utf-8")
        with self.assertRaises(LLMLogError):
            LLMJournal(occupied / "log.jsonl")
        self.assertEqual(occupied.read_text(encoding="utf-8"), "keep")

    def test_unsupported_request_body_fails_before_network(self):
        journal = self.journal()
        request = urllib.request.Request("https://example.org", data=io.BytesIO(b"{}"))
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")):
            with self.assertRaises(LLMLogError):
                context.request_json(request, 5, journal=journal)


class JSONResponseTests(unittest.TestCase):
    def test_plain_and_fenced_json_objects(self):
        for content in ('{"ok":true}', '```json\n{"ok":true}\n```',
                        ' \n```JSON\r\n{"ok":true}\r\n```\n ', '```\n{"ok":true}\n```'):
            with self.subTest(content=content):
                self.assertEqual(context.parse_json_object(content, "Test"), {"ok": True})

    def test_empty_truncated_or_ambiguous_responses_are_rejected(self):
        for content in ("", " ", None, "[]", '```json\n{"ok":true}', 'Texte\n{"ok":true}',
                        '```json\n{"ok":true}\n```\nTexte', '{"ok":'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                context.parse_json_object(content, "Test")


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "context.json"
        self.data = pipeline.adapt_v2_bundle(bundle())
        self.snapshot = context.load_context(self.data, self.path)

    def test_adapter_and_scoped_context(self):
        self.assertIn("context", self.data)
        self.assertEqual(self.data["candidates"][0]["main_axes"], ["Services publics"])
        self.snapshot["evidence"] = [evidence(), evidence(id="other", candidate_id="other")]
        selected = context.proposal_context(self.data["proposals"][0], self.snapshot)
        self.assertEqual([e["id"] for e in selected["evidence"]], ["extrait"])
        self.assertEqual(selected["theme_facts"][0]["label"], "PIB")
        self.assertEqual(selected["programme"]["thematic_links"], [])
        self.assertNotIn("sante", json.dumps(selected))

    def test_refresh_preserves_manual_evidence_and_does_not_fake_review(self):
        self.snapshot["evidence"] = [evidence(reviewed_at="2025-01-01")]
        self.path.write_text(json.dumps(self.snapshot), encoding="utf-8")
        self.data["context"]["checked"] = "2026-11-02"
        self.assertEqual(context.load_context(self.data, self.path)["france"]["checked"], "2026-11-01")
        refreshed = context.load_context(self.data, self.path, True)
        self.assertEqual(refreshed["france"]["checked"], "2026-11-02")
        self.assertEqual(refreshed["evidence"][0]["reviewed_at"], "2025-01-01")
        self.assertTrue(context.context_warnings(refreshed, 30))

    def test_invalid_manual_evidence_is_an_error(self):
        for item in (evidence(source_url="file:secret"), evidence(dimensions=["invented"]),
                     evidence(reviewed_at="hier"), evidence(review_interval_days=0)):
            with self.subTest(item=item), self.assertRaises(ValueError):
                context.validate_context({**self.snapshot, "evidence": [item]})

    def test_context_and_votes_invalidate_hash_but_output_scores_do_not(self):
        p = {**self.data["proposals"][0], "scoring_context": context.proposal_context(self.data["proposals"][0], self.snapshot)}
        old = pipeline.content_hash(p)
        changed = copy.deepcopy(p)
        changed["scoring_context"]["theme_facts"][0]["value"] = "3100"
        self.assertNotEqual(old, pipeline.content_hash(changed))
        scored = pipeline._parse_jev_proposal_answers(p, answers(), "jev")
        self.assertEqual(old, pipeline.content_hash(scored))
        scored["importance_sources"]["votes"] = 80
        self.assertNotEqual(old, pipeline.content_hash(scored))

    def test_unrelated_context_does_not_change_fingerprint(self):
        p = self.data["proposals"][0]
        old = context.proposal_context(p, self.snapshot)
        self.snapshot["france"]["themes"]["sante"][0]["value"] = "999"
        self.assertEqual(old, context.proposal_context(p, self.snapshot))


class JevTests(unittest.TestCase):
    def test_decisions_models_and_chat_router_are_distinct(self):
        for model in ("~typesafe/jev-latest", "typesafe/jev-1.14", "typesafe/jev-1.13-20260917"):
            self.assertTrue(pipeline.is_openrouter_jev_model(model))
        for model in ("typesafe/jev-router", "anthropic/claude-haiku-5.5", "jev"):
            self.assertFalse(pipeline.is_openrouter_jev_model(model))

    def test_openrouter_decisions_single_and_batch_use_native_payload(self):
        p = {"id": "p", "scoring_context": {"theme_facts": [{"value": "test"}]}}
        for batch in (False, True):
            raw = {f"p{i}__{k}": v for i in range(2) for k, v in answers().items()} if batch else answers()
            api_response = {"answers": raw, "model": "typesafe/jev-1.14-20261001"}
            with self.subTest(batch=batch), patch("urllib.request.urlopen", return_value=response(api_response)) as http:
                if batch:
                    result = pipeline.typesafe_score_batch([p, {**p, "id": "p2"}], "https://openrouter.ai/api/v1",
                                                           "~typesafe/jev-latest", "test-key")
                else:
                    result = [pipeline.llm_score(p, "https://openrouter.ai/api/v1", "~typesafe/jev-latest",
                                                 "test-key", provider="openrouter")]
            request = http.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "https://openrouter.ai/api/alpha/decisions")
            self.assertEqual(payload["model"], "~typesafe/jev-latest")
            self.assertIsInstance(payload["questions"], dict)
            self.assertIn("state", payload)
            self.assertNotIn("messages", payload)
            self.assertNotIn("temperature", payload)
            self.assertNotIn("response_format", payload)
            self.assertEqual(len(result), 2 if batch else 1)
            self.assertEqual(result[0]["score_details"]["ideology"]["method"], "jev-calibrated")
            self.assertEqual(result[0]["typesafe_details"]["model"], "typesafe/jev-1.14-20261001")

    def test_missing_answers_are_null_not_extreme_scores(self):
        scored = pipeline._parse_jev_proposal_answers({"id": "p"}, {}, "jev")
        self.assertIsNone(scored["ideology"])
        self.assertIsNone(scored["feasibility"])
        self.assertIsNone(scored["confidence"])
        self.assertEqual(scored["threshold_tags"], [])
        self.assertEqual(len(context.review_issues(scored, .65)), 7)

    def test_missing_confidence_and_low_confidence_are_individual(self):
        a = answers()
        del a["ideology"]["confidence"]
        a["feasibility"]["confidence"] = .2
        a["has_rights_status"]["probability"] = .01
        scored = pipeline._parse_jev_proposal_answers({}, a, "jev")
        issues = {i["dimension"]: i["reason"] for i in context.review_issues(scored, .65)}
        self.assertEqual(issues["ideology"], "missing_confidence")
        self.assertEqual(issues["feasibility"], "low_confidence")
        self.assertNotIn("rights_status", issues)

    def test_uncertain_applicability_is_not_silently_discarded(self):
        a = answers()
        a["has_rights_status"]["probability"] = .38
        scored = pipeline._parse_jev_proposal_answers({}, a, "jev")
        issue = next(i for i in context.review_issues(scored, .65) if i["dimension"] == "rights_status")
        self.assertEqual(issue["reason"], "uncertain_applicability")

    def test_importance_requires_evidence_not_just_programme_url(self):
        p: dict[str, Any] = {"scoring_context": {"programme": {"main_url": "https://example.org/programme"}}}
        scored = pipeline._parse_jev_proposal_answers(p, answers(), "jev")
        self.assertIsNone(scored["importance_sources"]["programme"])
        self.assertIsNone(scored["importance_sources"]["media"])
        p["scoring_context"]["evidence"] = [evidence(dimensions=["programme_importance", "media_importance"])]
        scored = pipeline._parse_jev_proposal_answers(p, answers(), "jev")
        self.assertEqual(scored["importance_sources"]["programme"], 67)
        self.assertEqual(scored["importance_sources"]["media"], 67)

    def test_structural_importance_replaces_model_programme_importance(self):
        signal = evidence(dimensions=["programme_importance"])
        signal.update(source_kind="signal_structurel", values={
            "importance_structurelle": {"score": 42, "position": 70, "theme": 30, "repetition": 10}})
        p: dict[str, Any] = {"importance_sources": {"votes": None}, "scoring_context": {"evidence": [signal]}}
        scored = pipeline._parse_jev_proposal_answers(p, answers(), "jev")
        self.assertEqual(scored["importance_sources"]["programme"], 42)
        detail = scored["score_details"]["programme_importance"]
        self.assertEqual(detail["method"], "corpus-structure")
        self.assertEqual(detail["model_value"], 67)
        self.assertEqual(scored["importance"], 42)
        self.assertNotIn("programme_importance", {i["dimension"] for i in context.review_issues(scored, .65)})

    def test_axes_format_derives_ideology_tags_and_skips_structural_gaps(self):
        a = answers(axes=True)
        self.assertNotIn("ideology", a)
        a["eco"]["score"] = 1        # 5 niveaux : -50
        a["sov"]["score"] = 3        # +50
        a["has_soc"]["probability"] = .05   # sociétal non applicable, avec confiance .95
        a["legal_instrument"] = {"choice": "revision_constitutionnelle", "confidence": .9,
                                 "probabilities": {"revision_constitutionnelle": .9}}
        a["rights_income"]["score"] = 0     # micro-catégorie
        scored = pipeline._parse_jev_proposal_answers({"precision": "orientation_generale"}, a, "jev")
        axes = scored["axes"]
        self.assertEqual((axes["eco"], axes["sov"], axes["soc"], axes["rupture"]), (-50, 50, None, 67))
        self.assertEqual(axes["legal_instrument"], "revision_constitutionnelle")
        # moyenne de eco -50, ouverture 0 et accès aux droits 0 (50 ramené à 0) ; soc non applicable, sov hors gauche/droite
        self.assertEqual(scored["ideology"], -17)
        self.assertEqual(scored["score_details"]["ideology"]["status"], "derived")
        self.assertEqual(scored["rights_income"], 0)
        self.assertEqual(set(scored["threshold_tags"]),
                         {pipeline.TAGS[0], pipeline.TAGS[3], pipeline.TAGS[4]})  # licorne, ciblé, annonce déduits
        self.assertEqual(scored["score_details"]["media_importance"]["status"], "not_requested")
        self.assertEqual(scored["score_details"]["budget_net_bn_year"]["status"], "no_annual_amount")
        self.assertEqual(context.review_issues(scored, .65), [])

    def test_axes_format_low_confidence_reaches_review_queue(self):
        scored = pipeline._parse_jev_proposal_answers({}, answers(.2, axes=True), "jev")
        dims = {i["dimension"] for i in context.review_issues(scored, .65)}
        self.assertTrue({"eco", "soc", "sov", "ecolo", "rupture", "legal_instrument", "feasibility"} <= dims)
        self.assertFalse(dims & {"ideology", "media_importance", "budget_net_bn_year", "programme_importance", "horizon"})

    def test_dimensions_schema_describes_every_stored_axis(self):
        schema = pipeline.dimensions_schema()
        for dim in context.AXES_DIMENSIONS:
            self.assertEqual(schema[dim]["field"], f"axes.{dim}")
        self.assertEqual(list(schema["eco"]["anchors"]), ["-100", "-50", "0", "50", "100"])
        self.assertIn("revision_constitutionnelle", schema["legal_instrument"]["options"])
        self.assertEqual(schema["ideology"]["components"], ["eco", "soc", "ouverture", "rights_status"])
        self.assertEqual(schema["sov"]["label"], "Niveau de décision")

    def test_selection_filters_and_attaches_precision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sel.json"
            path.write_text(json.dumps({"selected": [{"id": "b", "precision": "chiffre", "precision_llm": 80}]}),
                            encoding="utf-8")
            data = pipeline.apply_selection({"proposals": [{"id": "a"}, {"id": "b"}]}, path)
            self.assertEqual(data["proposals"], [{"id": "b", "precision": "chiffre", "precision_llm": 80}])
            path.write_text(json.dumps({"selected": [{"id": "z"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                pipeline.apply_selection({"proposals": [{"id": "a"}]}, path)

    def test_only_explicit_annual_budget_is_accepted(self):
        for text, expected in (("20 Md€ sur cinq ans", None), ("20 Md€/an", 20),
                               ("2,5 milliards d'euros par an", 2.5), ("SMIC a 2200 euros", None)):
            with self.subTest(text=text):
                self.assertEqual(pipeline.extract_explicit_budget_bn({"description": text}), expected)

    def test_invalid_score_does_not_get_clamped(self):
        for invalid in (float("nan"), True, -1, 100):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pipeline._parse_jev_proposal_answers({}, {"ideology": {"score": invalid}}, "jev")

    def test_local_budget_must_be_annual_and_proposal_specific(self):
        p = {"id": "p", "scoring_context": {"evidence": [
            evidence(dimensions=["budget_net_bn_year"], text="2 Md€/an", proposal_id="other")
        ]}}
        self.assertIsNone(pipeline.extract_explicit_budget_bn(p))
        p["scoring_context"]["evidence"][0]["proposal_id"] = "p"
        self.assertEqual(pipeline.extract_explicit_budget_bn(p), 2)

    def test_single_batch_and_native_all_receive_context(self):
        p = {"id": "p", "scoring_context": {"theme_facts": [{"value": "test"}]}}
        for endpoint, batch in (("https://example.org/v1", False), ("https://api.typesafe.ai/v1", False),
                                ("https://example.org/v1", True), ("https://api.typesafe.ai/v1", True)):
            with self.subTest(endpoint=endpoint, batch=batch):
                payload_answers = {f"p{i}__{k}": v for i in range(2) for k, v in answers().items()} if batch else answers()
                with patch("urllib.request.urlopen", return_value=response({"answers": payload_answers})) as http:
                    if batch:
                        pipeline.typesafe_score_batch([p, {**p, "id": "p2"}], endpoint, "jev", "test-key")
                    else:
                        pipeline.typesafe_score(p, endpoint, "jev", "test-key")
                    payload = json.loads(http.call_args.args[0].data)
                    self.assertIn("theme_facts", json.dumps(payload))
                    self.assertIn("scoring_context.rules", json.dumps(payload))
                    self.assertLessEqual(len(payload["questions"]), 100)


class WebTests(unittest.TestCase):
    def test_search_execution_is_reported_by_provider_counters(self):
        payload = web_response(["feasibility"])
        payload["usage"] = {"server_tool_use_details": {
            "web_search_requests": 1, "tool_calls_requested": 1, "tool_calls_executed": 1}}
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        activity = result["web_review"]["search_activity"]
        self.assertEqual(activity["status"], "performed")
        self.assertEqual(activity["web_search_requests"], 1)
        self.assertEqual(activity["tool_calls_executed"], 1)
        self.assertEqual(result["web_review"]["response"]["search_activity"], activity)

    def test_missing_search_counter_is_unknown_not_zero(self):
        for usage in ({}, {"server_tool_use_details": {"tool_calls_executed": 1}},
                      {"server_tool_use_details": {"web_search_requests": True}}):
            payload = web_response(["feasibility"])
            payload["usage"] = usage
            with self.subTest(usage=usage), patch("urllib.request.urlopen", return_value=response(payload)):
                result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
            activity = result["web_review"]["search_activity"]
            self.assertEqual(activity["status"], "unknown")
            self.assertIsNone(activity["web_search_requests"])

    def test_explicit_no_search_cannot_produce_a_web_grounded_score(self):
        payload = web_response(["feasibility"])
        payload["usage"] = {"server_tool_use_details": {"web_search_requests": 0, "tool_calls_executed": 0}}
        with patch("urllib.request.urlopen", return_value=response(payload)):
            with self.assertRaises(context.WebResponseError) as raised:
                context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertIn("aucune recherche web", str(raised.exception))
        self.assertEqual(raised.exception.details["search_activity"]["status"], "not_performed")

    def test_only_requested_dimensions_are_changed(self):
        p = {"ideology": -20, "confidence": .2, "threshold_tags": ["old"],
             "importance_sources": {"programme": 80, "votes": 90}}
        issues = [{"dimension": "feasibility"}]
        with patch("urllib.request.urlopen", return_value=response(web_response(["feasibility"]))) as http:
            result = context.web_reassess(p, issues, "example/model", "test-key", .65)
        self.assertEqual(result["feasibility"], 60)
        self.assertEqual(result["ideology"], -20)
        self.assertNotIn("feasibility", p)
        self.assertEqual(result["threshold_tags"], ["old"])
        self.assertEqual(result["importance_sources"]["votes"], 90)
        self.assertEqual(result["score_details"]["feasibility"]["method"], "web-self-reported")
        payload = json.loads(http.call_args.args[0].data)
        self.assertEqual(payload["model"], "example/model")
        self.assertNotIn("plugins", payload)
        self.assertEqual(payload["tools"], [{
            "type": "openrouter:web_search",
            "parameters": {"engine": "exa", "max_results": 5, "max_uses": 1, "max_total_results": 5},
        }])
        self.assertEqual(result["web_review"]["search_tool"], payload["tools"][0])
        self.assertTrue(result["web_review"]["human_review_required"])
        self.assertIsNone(result["web_review"]["initial_assessments"]["feasibility"]["value"])

    def test_complete_fenced_json_is_accepted_without_weakening_citations(self):
        payload = web_response(["feasibility"])
        message = payload["choices"][0]["message"]
        message["content"] = "```json\n" + message["content"] + "\n```"
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertEqual(result["feasibility"], 60)
        self.assertTrue(result["web_review"]["citations"])

    def test_truncation_reports_token_usage_even_if_json_is_complete(self):
        payload = web_response(["feasibility"])
        payload.update(id="gen-truncated", usage={"completion_tokens": 4314,
                                                "completion_tokens_details": {"reasoning_tokens": 2192}})
        payload["choices"][0].update(finish_reason="length", native_finish_reason="max_output_tokens")
        with patch("urllib.request.urlopen", return_value=response(payload)):
            with self.assertRaises(context.WebResponseError) as raised:
                context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertIn("finish_reason=length", str(raised.exception))
        self.assertIn("reasoning_tokens=2192", str(raised.exception))
        self.assertIn("--web-max-tokens", str(raised.exception))
        self.assertEqual(raised.exception.details["response_id"], "gen-truncated")

    def test_empty_stopped_content_reports_clear_error(self):
        payload = web_response(["feasibility"])
        payload["id"] = "gen-empty"
        payload["choices"][0]["message"]["content"] = ""
        with patch("urllib.request.urlopen", return_value=response(payload)):
            with self.assertRaises(context.WebResponseError) as raised:
                context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertIn("contenu JSON vide", str(raised.exception))
        self.assertEqual(raised.exception.details["finish_reason"], "stop")
        self.assertEqual(raised.exception.details["content_characters"], 0)

    def test_web_output_budget_is_configurable_and_recorded(self):
        with patch("urllib.request.urlopen", return_value=response(web_response(["feasibility"]))) as http:
            result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65,
                                          max_tokens=12000)
        self.assertEqual(json.loads(http.call_args.args[0].data)["max_tokens"], 12000)
        self.assertEqual(result["web_review"]["response"]["max_tokens"], 12000)
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")):
            with self.assertRaises(ValueError):
                context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65, max_tokens=0)

    def test_low_confidence_web_response_is_recorded_but_not_applied(self):
        p = {"feasibility": 15}
        with patch("urllib.request.urlopen", return_value=response(web_response(["feasibility"], .4))):
            result = context.web_reassess(p, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertEqual(result["feasibility"], 15)
        self.assertEqual(result["web_review"]["accepted_dimensions"], [])

    def test_legacy_online_suffix_is_not_sent_to_openrouter(self):
        with patch("urllib.request.urlopen", return_value=response(web_response(["feasibility"]))) as http:
            result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model:free:online", "test-key", .65)
        payload = json.loads(http.call_args.args[0].data)
        self.assertEqual(payload["model"], "example/model:free")
        self.assertEqual(result["web_review"]["model"], "example/model:free")
        self.assertNotIn("plugins", payload)

    def test_no_search_evidence_keeps_unresolved_scores_in_queue(self):
        payload = web_response(["feasibility"])
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["feasibility"].update(value=None, source_urls=[])
        message["content"] = json.dumps(parsed)
        message["annotations"] = []
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)
        self.assertNotIn("feasibility", result)
        self.assertEqual(result["web_review"]["accepted_dimensions"], [])
        self.assertIn("feasibility", [i["dimension"] for i in context.review_issues(result, .65)])

    def test_missing_or_unconsulted_citations_are_rejected(self):
        for annotations in ([], [{"type": "url_citation", "url_citation": {"url": "https://example.org/other"}}]):
            payload = web_response(["feasibility"])
            payload["choices"][0]["message"]["annotations"] = annotations
            with self.subTest(annotations=annotations), patch("urllib.request.urlopen", return_value=response(payload)):
                with self.assertRaisesRegex(ValueError, "citations"):
                    context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)

    def test_bad_citation_does_not_discard_other_valid_dimensions(self):
        payload = web_response(["feasibility", "programme_importance"])
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["programme_importance"]["source_urls"] = ["https://example.org/not-consulted"]
        message["content"] = json.dumps(parsed)
        p = {"feasibility": 15, "importance_sources": {"programme": 81}}
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess(p, [{"dimension": d} for d in parsed["assessments"]], "example/model", "test-key", .65)
        self.assertEqual(result["feasibility"], 60)
        self.assertEqual(result["importance_sources"]["programme"], 81)
        self.assertEqual(p["feasibility"], 15)
        review = result["web_review"]
        self.assertEqual(review["status"], "partial")
        self.assertEqual(review["accepted_dimensions"], ["feasibility"])
        self.assertIn("programme_importance", review["rejected_dimensions"])
        self.assertNotIn("programme_importance", review["assessments"])

    def test_explicit_null_confidence_is_valid_only_for_abstention(self):
        payload = web_response(["feasibility", "media_importance"])
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["media_importance"].update(value=None, confidence=None, source_urls=[])
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess({"importance_sources": {"media": 20}},
                                         [{"dimension": d} for d in parsed["assessments"]], "example/model", "test-key", .65)
        self.assertEqual(result["feasibility"], 60)
        self.assertEqual(result["importance_sources"]["media"], 20)
        review = result["web_review"]
        self.assertEqual(review["status"], "completed")
        self.assertEqual(review["abstained_dimensions"], ["media_importance"])
        self.assertIsNone(review["assessments"]["media_importance"]["confidence"])
        self.assertEqual(review["rejected_dimensions"], {})

    def test_invalid_nonnull_confidence_is_not_coerced_and_does_not_leak_nan(self):
        for invalid in (None, "0.9", 90, True, float("nan"), -.1):
            payload = web_response(["feasibility", "media_importance"])
            message = payload["choices"][0]["message"]
            parsed = json.loads(message["content"])
            parsed["assessments"]["media_importance"]["confidence"] = invalid
            message["content"] = json.dumps(parsed)
            with self.subTest(invalid=invalid), patch("urllib.request.urlopen", return_value=response(payload)):
                result = context.web_reassess({}, [{"dimension": d} for d in parsed["assessments"]], "example/model", "test-key", .65)
            self.assertEqual(result["feasibility"], 60)
            self.assertNotIn("media_importance", result["web_review"]["assessments"])
            self.assertIn("confiance invalide", result["web_review"]["rejected_dimensions"]["media_importance"])
            json.dumps(result, allow_nan=False)

    def test_missing_confidence_is_not_an_implicit_abstention(self):
        payload = web_response(["feasibility", "media_importance"])
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["media_importance"]["value"] = None
        del parsed["assessments"]["media_importance"]["confidence"]
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", return_value=response(payload)):
            result = context.web_reassess({}, [{"dimension": d} for d in parsed["assessments"]], "example/model", "test-key", .65)
        self.assertEqual(result["web_review"]["status"], "partial")
        self.assertIn("media_importance", result["web_review"]["rejected_dimensions"])

    def test_fully_invalid_dimensions_keep_response_diagnostics(self):
        payload = web_response(["programme_importance", "media_importance"])
        payload["id"] = "gen-invalid-dimensions"
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["programme_importance"]["source_urls"] = []
        parsed["assessments"]["media_importance"]["confidence"] = "unknown"
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", return_value=response(payload)):
            with self.assertRaises(context.WebResponseError) as raised:
                context.web_reassess({}, [{"dimension": d} for d in parsed["assessments"]], "example/model", "test-key", .65)
        self.assertEqual(raised.exception.details["response_id"], "gen-invalid-dimensions")
        self.assertEqual(set(raised.exception.details["rejected_dimensions"]), {"programme_importance", "media_importance"})

    def test_extra_dimensions_and_nonannual_amounts_are_rejected(self):
        payload = web_response(["budget_net_bn_year"])
        message = payload["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["budget_net_bn_year"]["period"] = "five_years"
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", return_value=response(payload)), self.assertRaisesRegex(ValueError, "non annuel"):
            context.web_reassess({}, [{"dimension": "budget_net_bn_year"}], "example/model", "test-key", .65)
        with patch("urllib.request.urlopen", return_value=response(web_response(["ideology"]))), self.assertRaisesRegex(ValueError, "exactement"):
            context.web_reassess({}, [{"dimension": "feasibility"}], "example/model", "test-key", .65)

    def test_cache_normalizes_online_suffix_and_expires(self):
        p = {"web_review": {"model": "example/model", "searched_at": context.utc_now().isoformat(),
                            "cache_key": context.web_cache_key("fp", "example/model", .65)}}
        entry = {"web_scored": p}
        self.assertIs(context.reusable_web_result(entry, "fp", "", .65, 30), p)
        self.assertIsNone(context.reusable_web_result(entry, "changed", "", .65, 30))
        self.assertIsNone(context.reusable_web_result(entry, "fp", "different/model", .65, 30))
        self.assertIsNone(context.reusable_web_result(entry, "fp", "", .65, 30, max_tokens=12000))
        p["web_review"]["searched_at"] = (context.utc_now() - timedelta(days=31)).isoformat()
        self.assertIsNone(context.reusable_web_result(entry, "fp", "", .65, 30))

    def test_deprecated_plugin_cache_is_invalidated(self):
        old_key = context.digest({"version": 1, "fingerprint": "fp", "model": "example/model:online", "threshold": .65})
        entry = {"web_scored": {"web_review": {"model": "example/model:online",
                 "searched_at": context.utc_now().isoformat(), "cache_key": old_key}}}
        self.assertIsNone(context.reusable_web_result(entry, "fp", "example/model", .65, 30))
        self.assertEqual(context.web_cache_key("fp", "example/model", .65),
                         context.web_cache_key("fp", "example/model:online", .65))


class ChatTests(unittest.TestCase):
    def test_chat_providers_keep_context_scores_and_original_identity(self):
        p = {"id": "p", "candidate_id": "test", "description": "2 Md€/an",
             "importance_sources": {"votes": 91}, "scoring_context": {"evidence": []}}
        scored = pipeline._parse_jev_proposal_answers(p, answers(), "jev")
        for provider in ("openrouter", "openai", "mistral", "mammouth", "anthropic"):
            payload = {**scored, "id": "invented-id", "candidate_id": "invented-candidate"}
            content = json.dumps(payload)
            api_result = {"content": [{"type": "text", "text": content}], "stop_reason": "end_turn"} if provider == "anthropic" else {
                "choices": [{"finish_reason": "stop", "message": {"content": content}}]}
            with self.subTest(provider=provider), patch("urllib.request.urlopen", return_value=response(api_result)) as http:
                result = pipeline.llm_score(p, "https://example.org/v1", "test-model", "test-key", provider=provider)
            self.assertEqual(result["id"], "p")
            self.assertEqual(result["candidate_id"], "test")
            self.assertEqual(result["importance_sources"]["votes"], 91)
            self.assertEqual(result["score_details"]["ideology"]["method"], "chat-self-reported")
            self.assertIn("scoring_context", json.loads(http.call_args.args[0].data)["messages"][0]["content"])
            if provider == "openrouter":
                self.assertEqual(json.loads(http.call_args.args[0].data)["response_format"], {"type": "json_object"})

    def test_chat_rejects_invented_budget_and_inconsistent_status(self):
        scored = pipeline._parse_jev_proposal_answers({}, answers(), "jev")
        for field in ("budget", "status"):
            bad = copy.deepcopy(scored)
            if field == "budget":
                bad["budget_net_bn_year"] = -100
                bad["score_details"]["budget_net_bn_year"]["status"] = "scored"
            else:
                bad["score_details"]["ideology"]["status"] = "not_applicable"
            payload = {"choices": [{"message": {"content": json.dumps(bad)}}]}
            with self.subTest(field=field), patch("urllib.request.urlopen", return_value=response(payload)):
                with self.assertRaises(ValueError):
                    pipeline.llm_score({}, "https://example.org/v1", "test", "test-key", provider="openai")


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        source = self.root / "source.json"
        source.write_text(json.dumps(bundle()), encoding="utf-8")
        self.argv = ["pipeline", "--input", str(source), "--context-file", str(self.root / "context.json"),
                     "--cache-file", str(self.root / "cache.json"), "--out", str(self.root / "out.json"),
                     "--review-queue", str(self.root / "queue.json"), "--llm-log-file", str(self.root / "llm.jsonl"),
                     "--allow-legacy-scoring"]

    def run_cli(self, extra, environment=None):
        env = {
            "TYPESAFE_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-key", "LLM_PROVIDER": "typesafe",
            "LLM_MODEL": "jev", "OPENROUTER_MODEL": "", "LLM_API_BASE_URL": "https://example.org/v1",
        } if environment is None else environment
        self.stdout = io.StringIO()
        with patch.object(sys, "argv", self.argv + extra), patch.dict(os.environ, env, clear=True), \
                patch("sys.stdout", self.stdout), \
                patch.object(pipeline, "load_env_file"):
            return pipeline.main()

    def test_scoring_without_collected_sources_requires_explicit_legacy_opt_in(self):
        self.argv.remove("--allow-legacy-scoring")
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm"]), 2)
        self.assertIn("sans document collecté", stderr.getvalue())
        self.assertFalse((self.root / "out.json").exists())

    def test_journal_and_console_explain_limit_cache_and_abstentions(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest",
               "OPENROUTER_WEB_MODEL": "example/research"}
        raw = {f"p{i}__{k}": v for i in range(3) for k, v in answers(.2).items()}
        web = web_response(list(context.DIMENSIONS))
        message = web["choices"][0]["message"]
        parsed = json.loads(message["content"])
        for assessment in parsed["assessments"].values():
            assessment.update(value=None, confidence=None, source_urls=[])
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", side_effect=[response({"answers": raw}), response(web)]):
            self.assertEqual(self.run_cli(["--llm", "--web-fallback", "--web-max-calls", "1"], env), 0)
        events = [json.loads(line) for line in (self.root / "llm.jsonl").read_text(encoding="utf-8").splitlines()]
        summary = events[-1]
        self.assertEqual(summary["event"], "run_summary")
        self.assertEqual(summary["web_review_candidates"], 3)
        self.assertEqual(summary["web_calls"], 1)
        self.assertEqual(summary["web_deferred_by_limit"], 2)
        self.assertEqual(summary["web_abstained_dimensions"], len(context.DIMENSIONS))
        self.assertEqual(summary["web_applied_dimensions"], 0)
        self.assertEqual(summary["primary_api_calls"], 1)
        self.assertEqual(summary["web_api_calls"], 1)
        self.assertEqual(sum(event["event"] == "api_response" for event in events), 2)
        raw_web = next(event["response"] for event in events if event["event"] == "api_response" and event["stage"] == "web")
        self.assertEqual(raw_web["choices"][0]["message"]["content"], message["content"])
        self.assertIn("File web : 3", self.stdout.getvalue())
        self.assertIn("plafond=1", self.stdout.getvalue())
        self.assertIn("en attente du plafond=2", self.stdout.getvalue())
        with patch("urllib.request.urlopen", return_value=response(web)) as http:
            self.assertEqual(self.run_cli(["--llm", "--web-fallback", "--web-max-calls", "1"], env), 0)
        self.assertEqual(http.call_count, 1)
        events = [json.loads(line) for line in (self.root / "llm.jsonl").read_text(encoding="utf-8").splitlines()]
        second = events[-1]
        self.assertNotEqual(summary["run_id"], second["run_id"])
        self.assertEqual(second["primary_reused"], 3)
        self.assertEqual(second["primary_api_calls"], 0)
        self.assertEqual(second["web_reused"], 1)
        self.assertEqual(second["web_deferred_by_limit"], 1)
        with patch("urllib.request.urlopen", side_effect=AssertionError("cache only")):
            self.assertEqual(self.run_cli(["--llm"], env), 0)
        events = [json.loads(line) for line in (self.root / "llm.jsonl").read_text(encoding="utf-8").splitlines()]
        third = events[-1]
        self.assertEqual(third["web_calls"], 0)
        self.assertEqual(third["web_reused"], 2)
        self.assertEqual(third["web_skipped_disabled"], 1)
        current = [event for event in events if event["run_id"] == third["run_id"]]
        self.assertFalse(any(event["event"] == "api_request" for event in current))
        self.assertTrue(any(event["event"] == "assessment" and event["source"] == "cache" for event in current))

    def test_unwritable_journal_stops_before_api_requests(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm", "--llm-log-file", str(self.root)]), 2)
        self.assertIn("journal LLM", stderr.getvalue())
        self.assertFalse((self.root / "out.json").exists())

    def test_journal_write_failure_cannot_silently_disable_logging(self):
        with patch.object(LLMJournal, "write", side_effect=LLMLogError("disk full")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("no request")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm"]), 2)
        self.assertIn("disk full", stderr.getvalue())

    def test_all_openrouter_uses_two_models_and_one_key_with_cli_overrides(self):
        env = {"OPENROUTER_API_KEY": "shared-test-key", "OPENROUTER_SCORING_MODEL": "example/score",
               "OPENROUTER_WEB_MODEL": "example/research", "LLM_API_BASE_URL": "https://legacy.example/v1"}
        primary = pipeline._parse_jev_proposal_answers({"description": "2 Md€/an"}, answers(.2), "test")
        for extra, score_model, web_model in (
            ([], "example/score", "example/research"),
            (["--model", "override/score", "--web-model", "override/web"], "override/score", "override/web"),
        ):
            requests = []

            def fake_http(request, **_kwargs):
                requests.append(request)
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer shared-test-key")
                if payload["model"] == score_model:
                    return response({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(primary)}}]})
                self.assertEqual(payload["model"], web_model)
                self.assertEqual(payload["tools"][0]["type"], "openrouter:web_search")
                self.assertNotIn("plugins", payload)
                web_input = json.loads(payload["messages"][0]["content"].split("\n")[-1])
                self.assertEqual(web_input["rubric"]["feasibility"]["criteria"],
                                 pipeline.TYPESAFE_QUESTIONS["feasibility"]["criteria"])
                return response(web_response(web_input["dimensions"]))

            with self.subTest(extra=extra), patch("urllib.request.urlopen", side_effect=fake_http):
                self.assertEqual(self.run_cli(["--llm", "--limit", "1", "--web-fallback", "--web-max-calls", "1"] + extra, env), 0)
            self.assertEqual(len(requests), 2)
            output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(output["meta"]["llm_provider"], "openrouter")
            self.assertEqual(output["proposals"][0]["web_review"]["model"], web_model)
            self.assertEqual(output["proposals"][0]["web_review"]["initial_assessments"]["ideology"]["detail"]["method"], "chat-self-reported")

    def test_openrouter_missing_configuration_stops_before_ingestion(self):
        for env, expected in (({"OPENROUTER_API_KEY": "test-key"}, "OPENROUTER_SCORING_MODEL"),
                              ({"OPENROUTER_SCORING_MODEL": "example/score"}, "OPENROUTER_API_KEY")):
            with self.subTest(expected=expected), patch.object(pipeline, "ingest_json", side_effect=AssertionError("no ingestion")), \
                    patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(self.run_cli(["--llm"], env), 2)
                self.assertIn(expected, stderr.getvalue())

    def test_openrouter_jev_is_automatically_batched(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest"}
        raw = {f"p{i}__{k}": v for i in range(3) for k, v in answers().items()}
        with patch("urllib.request.urlopen", return_value=response({"answers": raw})) as http:
            self.assertEqual(self.run_cli(["--llm"], env), 0)
        self.assertEqual(http.call_count, 1)
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(len(json.loads(request.data)["questions"]), 3 * len(pipeline.jev_questions()))
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(output["meta"]["llm_scored_new_or_changed"], 3)

    def test_fatal_api_error_stops_after_first_request_and_preserves_output(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest"}
        output_path = self.root / "out.json"
        output_path.write_text('{"existing":true}', encoding="utf-8")
        error = urllib.error.HTTPError("https://openrouter.ai/api/alpha/decisions", 400, "Bad Request", {},
                                       response({"error": {"message": "Invalid question configuration"}}))
        with patch("urllib.request.urlopen", side_effect=error) as http, patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm"], env), 2)
        self.assertEqual(http.call_count, 1)
        self.assertIn("Invalid question configuration", stderr.getvalue())
        self.assertEqual(output_path.read_text(encoding="utf-8"), '{"existing":true}')

    def test_partial_cache_survives_fatal_api_error(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest"}
        error = urllib.error.HTTPError("https://openrouter.ai/api/alpha/decisions", 401, "Unauthorized", {},
                                       response({"error": {"message": "Key disabled"}}))
        with patch("urllib.request.urlopen", side_effect=[response({"answers": answers()}), error]) as http:
            self.assertEqual(self.run_cli(["--llm", "--batch-size", "1"], env), 2)
        self.assertEqual(http.call_count, 2)
        cached = json.loads((self.root / "cache.json").read_text(encoding="utf-8"))
        self.assertEqual(set(cached["measures"]), {"p0"})
        self.assertIsNotNone(cached["measures"]["p0"]["scored"]["ideology"])
        self.assertFalse((self.root / "out.json").exists())

    def test_decisions_model_cannot_be_used_for_web_search(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest",
               "OPENROUTER_WEB_MODEL": "~typesafe/jev-latest"}
        with patch("urllib.request.urlopen", side_effect=AssertionError("no request")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm", "--web-fallback"], env), 2)
        self.assertIn("modèle chat", stderr.getvalue())

    def test_legacy_web_model_variable_still_works(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "example/score",
               "OPENROUTER_MODEL": "legacy/research"}
        primary = pipeline._parse_jev_proposal_answers({}, answers(.2), "test")
        with patch.object(pipeline, "llm_score", return_value=primary), \
                patch.object(pipeline, "web_reassess", return_value={"web_review": {}}) as web:
            self.assertEqual(self.run_cli(["--llm", "--limit", "1", "--web-fallback"], env), 0)
        self.assertEqual(web.call_args.args[2], "legacy/research")

    def test_default_is_offline_and_persists_queue(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.run_cli([]), 0)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        queue = json.loads((self.root / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(output["meta"]["web_calls"], 0)
        self.assertEqual(queue["proposal_count"], 3)
        self.assertIsNone(output["proposals"][0]["ideology"])

    def test_bounded_web_calls_cache_reuse_and_primary_provenance(self):
        def fake_http(request, **_kwargs):
            payload = json.loads(request.data)
            if request.full_url.endswith("/decisions"):
                return response({"answers": answers(.2)})
            web_input = json.loads(payload["messages"][0]["content"].split("\n")[-1])
            return response(web_response(web_input["dimensions"]))

        with patch("urllib.request.urlopen", side_effect=fake_http) as http:
            self.assertEqual(self.run_cli(["--llm", "--batch-size", "1", "--web-fallback",
                                           "--web-model", "example/model", "--web-max-calls", "1"]), 0)
            self.assertEqual(http.call_count, 4)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(output["meta"]["web_calls"], 1)
        self.assertEqual(output["meta"]["review_proposal_count"], 2)
        cache = json.loads((self.root / "cache.json").read_text(encoding="utf-8"))
        self.assertEqual(cache["measures"]["p0"]["scored"]["score_details"]["ideology"]["confidence"], .2)
        self.assertEqual(cache["measures"]["p0"]["web_scored"]["score_details"]["ideology"]["confidence"], .9)
        with patch("urllib.request.urlopen", side_effect=AssertionError("cache should avoid network")):
            self.assertEqual(self.run_cli(["--llm"]), 0)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(output["meta"]["web_reused"], 1)
        self.assertEqual(output["meta"]["llm_reused_unchanged"], 3)
        with patch("urllib.request.urlopen", side_effect=fake_http) as http:
            self.assertEqual(self.run_cli(["--llm", "--batch-size", "1", "--model", "jev-new"]), 0)
            self.assertEqual(http.call_count, 3)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(output["meta"]["web_reused"], 0)
        self.assertEqual(output["meta"]["llm_reused_unchanged"], 0)

    def test_web_error_preserves_primary_score_and_queue(self):
        def fake_http(request, **_kwargs):
            if request.full_url.endswith("/decisions"):
                return response({"answers": answers(.2)})
            raise OSError("test outage")
        with patch("urllib.request.urlopen", side_effect=fake_http):
            self.assertEqual(self.run_cli(["--llm", "--batch-size", "1", "--web-fallback",
                                           "--web-model", "example/model", "--web-max-calls", "1"]), 0)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(output["proposals"][0]["web_review"]["status"], "error")
        self.assertEqual(output["proposals"][0]["ideology"], 0)
        self.assertEqual(output["meta"]["review_proposal_count"], 3)

    def test_web_format_error_preserves_scores_and_persists_response_diagnostics(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest",
               "OPENROUTER_WEB_MODEL": "example/research"}
        raw = {f"p{i}__{k}": v for i in range(3) for k, v in answers(.2).items()}
        web = web_response(["feasibility"])
        web.update(id="gen-test-truncated", usage={"completion_tokens": 12000})
        web["choices"][0]["finish_reason"] = "length"
        with patch("urllib.request.urlopen", side_effect=[response({"answers": raw}), response(web)]) as http:
            self.assertEqual(self.run_cli(["--llm", "--web-fallback", "--web-max-calls", "1",
                                           "--web-max-tokens", "12000"], env), 0)
        self.assertEqual(http.call_count, 2)
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        row = output["proposals"][0]
        self.assertEqual(row["ideology"], 0)
        self.assertEqual(row["web_review"]["status"], "error")
        self.assertEqual(row["web_review"]["response"]["response_id"], "gen-test-truncated")
        self.assertEqual(row["web_review"]["response"]["max_tokens"], 12000)
        self.assertEqual(output["meta"]["web_max_tokens"], 12000)
        cached = json.loads((self.root / "cache.json").read_text(encoding="utf-8"))
        self.assertNotIn("web_scored", cached["measures"]["p0"])

    def test_partial_web_review_is_cached_without_losing_jev_or_repeating_calls(self):
        env = {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_SCORING_MODEL": "~typesafe/jev-latest",
               "OPENROUTER_WEB_MODEL": "example/research"}
        raw = {f"p{i}__{k}": v for i in range(3) for k, v in answers(.2).items()}
        web = web_response(list(context.DIMENSIONS))
        message = web["choices"][0]["message"]
        parsed = json.loads(message["content"])
        parsed["assessments"]["programme_importance"]["source_urls"] = ["https://example.org/not-consulted"]
        parsed["assessments"]["media_importance"].update(value=None, confidence=None, source_urls=[])
        message["content"] = json.dumps(parsed)
        with patch("urllib.request.urlopen", side_effect=[response({"answers": raw}), response(web)]) as http, \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_cli(["--llm", "--web-fallback", "--web-max-calls", "1"], env), 0)
        self.assertEqual(http.call_count, 2)
        self.assertIn("dimension programme_importance", stderr.getvalue())
        self.assertNotIn("seconde lecture web impossible", stderr.getvalue())
        output = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        row = output["proposals"][0]
        self.assertEqual(row["feasibility"], 60)
        self.assertEqual(row["importance_sources"]["programme"], 67)
        self.assertEqual(row["web_review"]["status"], "partial")
        queue = json.loads((self.root / "queue.json").read_text(encoding="utf-8"))
        self.assertIn("programme_importance", {i["dimension"] for i in queue["proposals"][0]["issues"]})
        cached = json.loads((self.root / "cache.json").read_text(encoding="utf-8"))
        self.assertEqual(cached["measures"]["p0"]["scored"]["ideology"], 0)
        self.assertEqual(cached["measures"]["p0"]["web_scored"]["feasibility"], 60)
        with patch("urllib.request.urlopen", side_effect=AssertionError("cache should avoid network")):
            self.assertEqual(self.run_cli(["--llm"], env), 0)
        reused = json.loads((self.root / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(reused["meta"]["web_reused"], 1)
        self.assertEqual(reused["meta"]["llm_reused_unchanged"], 3)
        self.assertEqual(reused["proposals"][0]["web_review"]["status"], "partial")

    def test_bad_cache_is_not_silently_ignored(self):
        path = self.root / "cache.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cache"):
            pipeline.cached_scored_rows(path)

    def test_invalid_options_stop_before_network(self):
        for extra in (["--web-fallback"], ["--confidence-threshold", "1.1"],
                      ["--context-max-age-days", "0"], ["--web-max-calls", "-1"], ["--web-max-tokens", "0"]):
            with self.subTest(extra=extra), patch("urllib.request.urlopen", side_effect=AssertionError("no request")):
                self.assertEqual(self.run_cli(extra), 2)


class BlindStateTests(unittest.TestCase):
    def setUp(self):
        pipeline.set_blind_names([{"id": "x", "first_name": "Marine", "last_name": "Dupuis", "party": "Parti Exemple",
                                   "party_short": "PE"}])
        self.addCleanup(pipeline.BLIND_NAMES.clear)

    def proposal(self):
        return {"id": "p1", "candidate_id": "x", "theme": "logement", "title": "Plan Marine Dupuis pour le logement",
                "description": "Le Parti Exemple veut construire 100 logements.", "source_title": "Marine Dupuis 2027",
                "source_url": "https://exemple.fr/p.pdf", "source_type": "document_programme", "source_date": "2026-10-01",
                "scoring_context": {
                    "rules": "r", "theme_facts": [{"label": "fait"}], "public_finances": [{"label": "dette"}],
                    "programme": {"title": "Marine Dupuis", "main_url": "https://exemple.fr", "main_axes": ["axe du candidat"]},
                    "candidate_budget": {"level": "global"},
                    "programme_corpus": {"coverage": [{"url": "https://exemple.fr/p.pdf", "complete": True}]},
                    "evidence": [{"id": "e1", "proposal_id": "p1", "dimensions": ["ideology"], "source_url": "https://exemple.fr/p.pdf",
                                  "content_hash": "h", "text": "Marine Dupuis propose 100 logements.", "source_kind": "programme"},
                                 {"id": "p1-position", "proposal_id": "p1", "dimensions": ["programme_importance"],
                                  "text": "position", "values": {"position_pct": 3, "passages": 2},
                                  "source_url": "https://exemple.fr/p.pdf", "source_kind": "signal_structurel"}]}}

    def test_no_candidate_identity_reaches_the_model(self):
        state = pipeline.blind_state(self.proposal())
        dumped = json.dumps(state, ensure_ascii=False)
        for leak in ("Dupuis", "Marine", "Parti Exemple", "exemple.fr", "axe du candidat", "candidate_id", "global"):
            self.assertNotIn(leak, dumped)
        self.assertIn("[le candidat]", state["title"])
        self.assertEqual(state["scoring_context"]["theme_facts"], [{"label": "fait"}])
        self.assertEqual(state["scoring_context"]["public_finances"], [{"label": "dette"}])

    def test_importance_signals_values_are_kept_and_corpus_flag_is_boolean(self):
        state = pipeline.blind_state(self.proposal())
        signal = next(e for e in state["scoring_context"]["evidence"] if e["id"] == "p1-position")
        self.assertEqual(signal["values"], {"position_pct": 3, "passages": 2})
        self.assertIs(state["scoring_context"]["corpus_complete"], True)

    def test_unknown_names_are_left_alone_without_registry(self):
        pipeline.BLIND_NAMES.clear()
        self.assertEqual(pipeline.blind_text("Marine Dupuis"), "Marine Dupuis")


if __name__ == "__main__":
    unittest.main()
