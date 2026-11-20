"""Optional Google Gemini Decisions API (v1beta/decisions) and offline LiteRT provider.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.egress import is_egress_host_allowed, resolve_effective_egress_policy
from zcg.governance.runtime.tool_isolation import (
    DEFAULT_DECISIONS_MODEL,
    RUBRIC_PASS_THRESHOLD,
    RUBRIC_SCALE_MAX,
    DecisionEvaluationRequest,
    evaluate_calibrated_decisions,
)
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

GEMINI_DECISIONS_CONTRACT_REV: Final[str] = "zcg-gemini-decisions-v1"
GEMINI_DECISIONS_ENDPOINT: Final[str] = "https://generativelanguage.googleapis.com/v1beta/decisions"
GEMINI_API_HOST: Final[str] = "generativelanguage.googleapis.com"
DEFAULT_DECISIONS_TIMEOUT_SECONDS: Final[float] = 15.0
DECISIONS_API_KEY_ENV_VARS: Final[tuple[str, ...]] = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def resolve_gemini_api_key(env: Mapping[str, str] | None = None) -> str:
    """Resolve ambient GEMINI_API_KEY or GOOGLE_API_KEY without reading static secret files."""
    eff_env = os.environ if env is None else env
    for key_name in DECISIONS_API_KEY_ENV_VARS:
        candidate = eff_env.get(key_name, "").strip()
        if candidate:
            return candidate
    return ""


def build_v1beta_decisions_payload(
    requests: Sequence[DecisionEvaluationRequest],
    *,
    shared_input: str = "",
    model: str = DEFAULT_DECISIONS_MODEL,
) -> dict[str, Any]:
    """Translate DecisionEvaluationRequest batch into official POST /v1beta/decisions JSON."""
    clean_input = shared_input.strip() or "\n\n".join(
        f"[{req.item_id}] {req.prompt}" for req in requests
    )
    questions: dict[str, dict[str, Any]] = {}
    for req in requests:
        if req.task_kind == "yes_no":
            questions[req.item_id] = {"type": "noul", "instructions": req.prompt}
        elif req.task_kind == "choice":
            questions[req.item_id] = {
                "type": "choice",
                "instructions": req.prompt,
                "criteria": {choice: choice for choice in req.choices},
            }
        else:
            questions[req.item_id] = {
                "type": "score",
                "instructions": req.prompt,
                "criteria": [f"Evaluate {req.use_case}: {req.prompt}"],
            }
    return {"model": model, "input": clean_input, "questions": questions}


def parse_v1beta_decisions_response(
    requests: Sequence[DecisionEvaluationRequest],
    raw_response: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Normalize POST /v1beta/decisions answers into calibrated zero-output-token results."""
    raw_answers = raw_response.get("answers")
    answers: Mapping[str, Any] = raw_answers if isinstance(raw_answers, Mapping) else {}
    normalized: list[dict[str, Any]] = []
    for req in requests:
        entry = answers.get(req.item_id)
        ans: Mapping[str, Any] = entry if isinstance(entry, Mapping) else {}
        conf = round(min(1.0, max(0.0, float(ans.get("confidence", 1.0)))), 4)
        base = {
            "item_id": req.item_id,
            "task_kind": req.task_kind,
            "use_case": req.use_case,
            "confidence": conf,
        }
        if req.task_kind == "yes_no":
            prob = min(1.0, max(0.0, float(ans.get("noul", req.prior_score))))
            normalized.append(
                {
                    **base,
                    "decision": "yes" if prob >= 0.5 else "no",
                    "calibrated_probability": round(prob, 4),
                }
            )
        elif req.task_kind == "choice":
            raw_scores = ans.get("scores") or ans.get("probabilities")
            if isinstance(raw_scores, Mapping):
                dist = {
                    ch: round(max(0.0, float(raw_scores.get(ch, 0.0))), 4) for ch in req.choices
                }
                selected = max(req.choices, key=lambda ch: dist[ch])
            else:
                winner = str(ans.get("choice") or req.choices[0])
                selected = winner if winner in req.choices else req.choices[0]
                dist = {ch: (1.0 if ch == selected else 0.0) for ch in req.choices}
            normalized.append({**base, "selected_choice": selected, "distribution": dist})
        else:
            raw_val = max(0.0, float(ans.get("score", req.prior_score)))
            norm = raw_val if raw_val <= 1.0 else min(1.0, raw_val / RUBRIC_SCALE_MAX)
            normalized.append(
                {
                    **base,
                    "rubric_score": round(norm * RUBRIC_SCALE_MAX, 2),
                    "passed": norm >= RUBRIC_PASS_THRESHOLD,
                }
            )
    return normalized


def invoke_v1beta_decisions_http(
    payload: Mapping[str, Any],
    *,
    api_key: str,
    endpoint: str = GEMINI_DECISIONS_ENDPOINT,
    timeout_seconds: float = DEFAULT_DECISIONS_TIMEOUT_SECONDS,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute HTTPS POST /v1beta/decisions via stdlib urllib.request (0 third-party deps)."""
    clean_key = api_key.strip()
    if not clean_key:
        raise ValueError("MISSING_GEMINI_API_KEY: GEMINI_API_KEY or GOOGLE_API_KEY is required")
    clean_ep = endpoint.strip()
    parts = urlsplit(clean_ep)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username is not None:
        raise ValueError(f"INSECURE_DECISIONS_ENDPOINT: HTTPS endpoint required, got {endpoint!r}")
    http_req = urllib.request.Request(  # noqa: S310
        clean_ep,
        data=json.dumps(dict(payload)).encode("utf-8"),
        headers={"content-type": "application/json", "x-goog-api-key": clean_key},
        method="POST",
    )
    eff_opener = urllib.request.urlopen if opener is None else opener
    with eff_opener(http_req, timeout=timeout_seconds) as resp:
        raw_bytes: bytes = resp.read()
    parsed = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("INVALID_DECISIONS_HTTP_RESPONSE: root JSON object expected")
    return parsed


def evaluate_node_decisions(
    workspace_dir: Path,
    requests: Sequence[DecisionEvaluationRequest],
    *,
    parent_dir: Path | None = None,
    shared_input: str = "",
    offline_override: bool = False,
    model: str = DEFAULT_DECISIONS_MODEL,
    endpoint: str = GEMINI_DECISIONS_ENDPOINT,
    env: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Evaluate calibrated decisions via live v1beta/decisions or automatic offline LiteRT."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    posture = resolve_governance_posture(ws, manifest, parent_dir=eff_parent)
    egress = resolve_effective_egress_policy(ws, manifest=manifest, parent_dir=eff_parent)
    ep_host = (urlsplit(endpoint.strip()).hostname or GEMINI_API_HOST).lower()
    api_key = resolve_gemini_api_key(env)

    if offline_override:
        fb_reason = "offline-override"
    elif posture.get("personal_pillar") == "wallet":
        fb_reason = "wallet-r3-airgap"
    elif egress.egress_restricted and not is_egress_host_allowed(ep_host, egress.allowed_domains):
        fb_reason = "egress-policy-restricted"
    elif not api_key:
        fb_reason = "missing-api-key"
    else:
        fb_reason = ""

    if fb_reason:
        local_res = evaluate_calibrated_decisions(requests, offline_mode=True)
        return {
            **local_res,
            "contract_rev": GEMINI_DECISIONS_CONTRACT_REV,
            "fallback_reason": fb_reason,
        }

    def _live_transport(_batch: dict[str, Any]) -> dict[str, Any]:
        v1_body = build_v1beta_decisions_payload(requests, shared_input=shared_input, model=model)
        raw_resp = invoke_v1beta_decisions_http(
            v1_body, api_key=api_key, endpoint=endpoint, opener=opener
        )
        return {"model": model, "results": parse_v1beta_decisions_response(requests, raw_resp)}

    try:
        online_res = evaluate_calibrated_decisions(requests, transport_fn=_live_transport)
    except OSError:
        err_res = evaluate_calibrated_decisions(requests, offline_mode=True)
        return {
            **err_res,
            "contract_rev": GEMINI_DECISIONS_CONTRACT_REV,
            "fallback_reason": "transport-error-fallback",
        }
    return {
        **online_res,
        "contract_rev": GEMINI_DECISIONS_CONTRACT_REV,
        "fallback_reason": None,
    }
