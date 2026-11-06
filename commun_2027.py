"""Fonctions communes aux etapes payantes du pipeline unifie.

- masquage des noms (annotation a l'aveugle) : blind_names, blind_item ;
- identifiant court envoye au modele : short_id ;
- batch OpenRouter (asynchrone, non annulable) : batch_submit, batch_collect.

Reprises a l'identique de l'ancien code (axes_2027, relecture_ciblee_2027), archive dans archives/code/.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import programme_corpus_2027 as pc
from llm_logging_2027 import LLMJournal
from scoring_context_2027 import request_json

BATCH_URL = "https://openrouter.ai/api/v1/batches"


def blind_names(candidates: list[dict[str, Any]]) -> set[str]:
    """Noms, partis et mouvements des candidats, a masquer dans ce qui est envoye au modele."""
    names: set[str] = set()
    for c in candidates or []:
        for key in ("last_name", "party", "party_short", "name", "movement"):
            value = str(c.get(key) or "").strip()
            if len(value) >= 3:
                names.add(value)
        full = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        if len(full) >= 3:
            names.add(full)
    return names


def blind_item(p: dict[str, Any], names: set[str]) -> dict[str, Any]:
    """Mesure sans le nom du candidat : titre, description et premiere citation (600 caracteres)."""
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?!\w)",
                         re.I) if names else None

    def mask(text: Any) -> Any:
        return pattern.sub("[le candidat]", text) if pattern and isinstance(text, str) else text
    quote = ((p.get("source_evidence") or [{}])[0]).get("quote", "")[:600]
    return {"id": p["id"], "theme": p.get("theme_id"), "title": mask(p.get("title")), "description": mask(p.get("description")),
            "quote": mask(quote)}


def short_id(proposal_id: str) -> str:
    """Identifiant court envoye au modele (moins de tokens en entree et en sortie), stable pour le cache."""
    return proposal_id[-8:]


def batch_submit(state_path: Path, model: str, effort: str, key: str, batches: list[list[dict[str, Any]]],
                 max_cost: float, cost_per_item: float, journal: LLMJournal,
                 make_body: Callable[[list[dict[str, Any]]], dict[str, Any]]) -> dict[str, Any]:
    """Envoie tous les lots en un batch OpenRouter si l'estimation tient dans le plafond.

    make_body(lot) -> corps chat/completions.
    """
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not state.get("collected_at"):
            raise ValueError(f"Batch {state.get('batch_id')} deja envoye et non recupere : --batch-collect d'abord.")
    n_items = sum(len(b) for b in batches)
    estimate = n_items * cost_per_item
    print(f"Batch : {len(batches)} requetes, {n_items} propositions, estimation {estimate:.2f} $ (plafond {max_cost:.2f} $).")
    if estimate > max_cost:
        raise ValueError("Estimation au-dessus du plafond : batch non envoye (un batch ne peut pas etre annule).")
    requests = [{"custom_id": f"lot-{n:04d}", "body": make_body(b)} for n, b in enumerate(batches)]
    body = {"endpoint": "/v1/chat/completions", "model": model, "requests": requests}
    request = urllib.request.Request(BATCH_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    response = request_json(request, 600, journal=journal, stage="batch_submit")
    state = {"batch_id": response.get("id"), "status": response.get("status"), "model": model, "effort": effort,
             "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "estimate": round(estimate, 4),
             "lots": {r["custom_id"]: b for r, b in zip(requests, batches)}}
    pc.save_json(state_path, state)
    return state


def batch_collect(state_path: Path, key: str, cache: dict[str, Any], cache_path: Path, journal: LLMJournal,
                  raw_path: Path | None, parse: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
                  key_fn: Callable[[str, dict[str, Any]], str]) -> dict[str, Any]:
    """Recupere un batch termine et range chaque reponse valide dans le cache (aucun cout).

    parse(corps, lot) -> {id: reponse} ; key_fn(modele, item) -> cle de cache.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    request = urllib.request.Request(f"{BATCH_URL}/{state['batch_id']}", headers={"Authorization": "Bearer " + key})
    response = request_json(request, 300, journal=journal, stage="batch_collect")
    status, counts = response.get("status"), response.get("request_counts") or {}
    report = {"batch_id": state["batch_id"], "status": status, "request_counts": counts}
    if status not in {"completed", "expired", "failed", "cancelled"}:
        return report
    stats = {"lots_ok": 0, "lots_failed": 0, "reviews": 0}
    for result in response.get("results") or []:
        batch = state["lots"].get(result.get("custom_id"))
        body = (result.get("response") or {}).get("body")
        if batch is None or result.get("error") or not isinstance(body, dict):
            stats["lots_failed"] += 1
            continue
        try:
            reviews = parse(body, batch)
        except ValueError:
            stats["lots_failed"] += 1
            continue
        stats["lots_ok"] += 1
        for item in batch:
            if item["id"] in reviews:
                cache[key_fn(state["model"], item)] = reviews[item["id"]]
                stats["reviews"] += 1
    pc.save_json(cache_path, cache)
    if raw_path:
        pc.save_json(raw_path, response)
    usage = response.get("usage") or {}
    state.update(status=status, collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 cost=usage.get("cost"), usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                 collect=stats)
    pc.save_json(state_path, state)
    return {**report, **stats, "cost": usage.get("cost"), "estimate": state.get("estimate")}
