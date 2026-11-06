"""Journal JSONL local des appels LLM et de leurs résultats, sans identifiants secrets."""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4


class LLMLogError(RuntimeError):
    """Un journal inutilisable doit arrêter le traitement avant de nouveaux appels."""


class LLMJournal:
    def __init__(self, path: Path | None = None, secrets: Iterable[str] = ()):
        self.run_id = uuid4().hex
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = path if path is not None else Path("logs") / f"llm_{stamp}_{self.run_id[:8]}.jsonl"
        self.secrets = {secret for secret in secrets if secret}
        self.request_counts: dict[str, int] = {}
        self._request_number = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open("a", encoding="utf-8")
        except OSError as exc:
            raise LLMLogError(f"Impossible d'ouvrir le journal LLM {self.path}: {exc}") from exc

    def _redact_text(self, text: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        return re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", text)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, float) and not math.isfinite(value):
            return {"invalid_number": str(value)}
        if isinstance(value, dict):
            sensitive = {"authorization", "x_api_key", "api_key", "openrouter_api_key",
                         "llm_api_key", "typesafe_api_key", "cookie", "set_cookie",
                         "access_token", "refresh_token"}
            return {
                str(key): "[REDACTED]" if str(key).lower().replace("-", "_") in sensitive else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact(item) for item in value]
        return value

    def write(self, event: str, **fields: Any) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                  "run_id": self.run_id, "event": event, **fields}
        try:
            line = json.dumps(self._redact(record), ensure_ascii=False, allow_nan=False)
            self._stream.write(line + "\n")
            self._stream.flush()
        except (OSError, ValueError, TypeError) as exc:
            detail = self._redact_text(str(exc))
            raise LLMLogError(f"Impossible d'écrire le journal LLM {self.path}: {detail}") from exc

    def close(self) -> None:
        try:
            self._stream.close()
        except OSError as exc:
            raise LLMLogError(f"Impossible de fermer le journal LLM {self.path}: {self._redact_text(str(exc))}") from exc

    def start_request(self, request: urllib.request.Request, stage: str, proposal_ids: list[str]) -> str:
        for name, value in request.header_items():
            if name.lower() in {"authorization", "x-api-key"}:
                self.secrets.add(value)
                self.secrets.add(re.sub(r"(?i)^Bearer\s+", "", value))
        data = request.data
        if data is None:
            payload = {}
        elif isinstance(data, (str, bytes, bytearray)):
            try:
                payload = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise LLMLogError("Impossible de journaliser une requête dont le corps n'est pas du JSON valide.") from exc
        else:
            raise LLMLogError("Le journal LLM attend un corps JSON encodé en texte ou en octets.")
        payload = payload if isinstance(payload, dict) else {}
        parts = urlsplit(request.full_url)
        endpoint = urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
        parameters = {key: payload[key] for key in ("temperature", "max_tokens", "response_format", "tools", "plugins") if key in payload}
        questions = payload.get("questions")
        if isinstance(questions, (dict, list)):
            parameters["question_count"] = len(questions)
        self._request_number += 1
        request_id = f"{self.run_id}-{self._request_number:06d}"
        self.write("api_request", request_id=request_id, stage=stage, proposal_ids=proposal_ids,
                   model=payload.get("model"), endpoint=endpoint, parameters=parameters)
        self.request_counts[stage] = self.request_counts.get(stage, 0) + 1
        return request_id


def scoring_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    keys = ("ideology", "feasibility", "rights_income", "rights_status", "budget_net_bn_year",
            "importance", "importance_sources", "confidence", "rationale", "source_note",
            "threshold_tags", "score_details", "typesafe_details", "web_review", "axes", "revision")
    return {key: proposal[key] for key in keys if key in proposal}
