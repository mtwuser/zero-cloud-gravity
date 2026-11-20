"""Unit tests for zcg.providers.gemini_decisions.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from zcg.governance.runtime.tool_isolation import DecisionEvaluationRequest
from zcg.providers.gemini_decisions import (
    GEMINI_DECISIONS_CONTRACT_REV,
    GEMINI_DECISIONS_ENDPOINT,
    build_v1beta_decisions_payload,
    evaluate_node_decisions,
    invoke_v1beta_decisions_http,
    parse_v1beta_decisions_response,
    resolve_gemini_api_key,
)


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self._buf.close()


class TestGeminiDecisionsProvider:
    """1:1 unit suite for POST /v1beta/decisions transport and offline LiteRT fallback."""

    def test_resolve_gemini_api_key_precedence_and_empty_expected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify GEMINI_API_KEY -> GOOGLE_API_KEY precedence and ambient os.environ lookup."""
        # Arrange
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        # Act
        k_none = resolve_gemini_api_key()
        k_primary = resolve_gemini_api_key(
            {"GEMINI_API_KEY": " gem-01 ", "GOOGLE_API_KEY": "goog-02"}
        )
        k_secondary = resolve_gemini_api_key({"GEMINI_API_KEY": "  ", "GOOGLE_API_KEY": "goog-02"})

        # Assert
        assert k_none == ""
        assert k_primary == "gem-01"
        assert k_secondary == "goog-02"

    def test_build_and_parse_v1beta_decisions_payload_all_task_kinds_expected(self) -> None:
        """Verify noul, choice, and score payload synthesis and response normalization."""
        # Arrange
        reqs = (
            DecisionEvaluationRequest("q1", "yes_no", "env-gate", "Ship pro?", prior_score=0.2),
            DecisionEvaluationRequest("q2", "yes_no", "env-gate", "Hold?", prior_score=0.8),
            DecisionEvaluationRequest(
                "q3", "choice", "model-routing", "Select tier", choices=("flash", "pro")
            ),
            DecisionEvaluationRequest(
                "q4", "choice", "handoff-axis", "Pick axis", choices=("front", "back")
            ),
            DecisionEvaluationRequest(
                "q5", "choice", "handoff-axis", "Fallback choice", choices=("alpha", "beta")
            ),
            DecisionEvaluationRequest("q6", "rubric", "epistemic-q-score", "Rate E3"),
            DecisionEvaluationRequest("q7", "rubric", "disclosure-sensitivity", "Rate raw 4pt"),
        )
        raw_api = {
            "answers": {
                "q1": {"type": "noul", "noul": 0.91, "confidence": 0.96},
                "q2": {"type": "noul", "noul": 0.12, "confidence": 0.88},
                "q3": {
                    "type": "choice",
                    "scores": {"flash": 0.15, "pro": 0.85},
                    "confidence": 0.93,
                },
                "q4": {"type": "choice", "choice": "back", "confidence": 0.80},
                "q5": {"type": "choice", "choice": "unlisted"},
                "q6": {"type": "score", "score": 0.85, "confidence": 0.90},
                "q7": {"type": "score", "score": 1.6, "confidence": 0.75},
            }
        }

        # Act
        body_auto = build_v1beta_decisions_payload(reqs[:1])
        body_shared = build_v1beta_decisions_payload(reqs, shared_input="Shared artifact")
        parsed_full = parse_v1beta_decisions_response(reqs, raw_api)
        parsed_empty = parse_v1beta_decisions_response(reqs[:1], {"answers": None})

        # Assert
        assert body_auto["input"] == "[q1] Ship pro?"
        assert body_shared["input"] == "Shared artifact"
        assert body_shared["questions"]["q1"]["type"] == "noul"
        assert body_shared["questions"]["q3"]["type"] == "choice"
        assert body_shared["questions"]["q6"]["type"] == "score"
        by_id = {r["item_id"]: r for r in parsed_full}
        assert by_id["q1"]["decision"] == "yes" and by_id["q2"]["decision"] == "no"
        assert by_id["q3"]["selected_choice"] == "pro"
        assert by_id["q4"]["selected_choice"] == "back"
        assert by_id["q5"]["selected_choice"] == "alpha"
        assert by_id["q6"]["rubric_score"] == 3.4 and by_id["q6"]["passed"] is True
        assert by_id["q7"]["rubric_score"] == 1.6 and by_id["q7"]["passed"] is False
        assert parsed_empty[0]["decision"] == "no"

    def test_invoke_v1beta_decisions_http_security_and_response_guards_expected(self) -> None:
        """Verify HTTPS enforcement, x-goog-api-key header injection, and JSON object check."""
        # Arrange
        seen: dict[str, Any] = {}

        def _good_opener(req: Any, timeout: float = 0.0) -> _FakeHttpResponse:
            seen["url"] = req.full_url
            seen["key"] = req.get_header("X-goog-api-key")
            seen["timeout"] = timeout
            return _FakeHttpResponse(b'{"answers": {"q1": {"noul": 0.8}}}')

        def _list_opener(_req: Any, timeout: float = 0.0) -> _FakeHttpResponse:
            del timeout
            return _FakeHttpResponse(b"[1, 2, 3]")

        # Act
        ok_resp = invoke_v1beta_decisions_http(
            {"model": "gemini-decision-1"}, api_key="secret-k", opener=_good_opener
        )
        with pytest.raises(ValueError, match="MISSING_GEMINI_API_KEY"):
            invoke_v1beta_decisions_http({}, api_key="   ")
        with pytest.raises(ValueError, match="INSECURE_DECISIONS_ENDPOINT"):
            invoke_v1beta_decisions_http({}, api_key="k", endpoint="http://insecure.example/v1")
        with pytest.raises(ValueError, match="INSECURE_DECISIONS_ENDPOINT"):
            invoke_v1beta_decisions_http(
                {}, api_key="k", endpoint="https://user@generativelanguage.googleapis.com/v1"
            )
        with pytest.raises(ValueError, match="INVALID_DECISIONS_HTTP_RESPONSE"):
            invoke_v1beta_decisions_http({}, api_key="k", opener=_list_opener)

        # Assert
        assert seen["url"] == GEMINI_DECISIONS_ENDPOINT and seen["key"] == "secret-k"
        assert ok_resp["answers"]["q1"]["noul"] == 0.8

    def test_evaluate_node_decisions_airgap_egress_live_and_oserror_fallback_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify all 4 offline fallback gates, live v1beta HTTP, and OSError resilience."""
        # Arrange
        req = (DecisionEvaluationRequest("g1", "yes_no", "env-gate", "Ready?", prior_score=0.9),)
        open_ws = tmp_path / "dept-eng"
        (open_ws / "system").mkdir(parents=True)
        (open_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "dept-eng", "layer_role": "department"}), encoding="utf-8"
        )
        wallet_ws = tmp_path / "persona-wallet"
        (wallet_ws / "system").mkdir(parents=True)
        (wallet_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "entity_kind": "individual",
                    "layer_role": "squad",
                    "precedence": 88,
                }
            ),
            encoding="utf-8",
        )
        egress_ws = tmp_path / "corp-strict"
        (egress_ws / "system").mkdir(parents=True)
        (egress_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "corp-strict",
                    "layer_role": "corporate",
                    "network_egress_policy": {"allowed_domains": ["internal.example"]},
                }
            ),
            encoding="utf-8",
        )

        def _live_opener(_http_req: Any, timeout: float = 0.0) -> _FakeHttpResponse:
            del timeout
            return _FakeHttpResponse(b'{"answers": {"g1": {"noul": 0.95, "confidence": 0.99}}}')

        def _failing_opener(_http_req: Any, timeout: float = 0.0) -> _FakeHttpResponse:
            del timeout
            raise OSError("network unreachable")

        # Act
        r_override = evaluate_node_decisions(
            open_ws, req, offline_override=True, env={"GEMINI_API_KEY": "k"}
        )
        r_wallet = evaluate_node_decisions(wallet_ws, req, env={"GEMINI_API_KEY": "k"})
        r_egress = evaluate_node_decisions(egress_ws, req, env={"GEMINI_API_KEY": "k"})
        r_nokey = evaluate_node_decisions(open_ws, req, env={})
        r_live = evaluate_node_decisions(
            open_ws, req, env={"GEMINI_API_KEY": "k"}, opener=_live_opener
        )
        r_oserr = evaluate_node_decisions(
            open_ws, req, env={"GEMINI_API_KEY": "k"}, opener=_failing_opener
        )

        # Assert
        assert r_override["fallback_reason"] == "offline-override"
        assert r_wallet["fallback_reason"] == "wallet-r3-airgap"
        assert r_egress["fallback_reason"] == "egress-policy-restricted"
        assert r_nokey["fallback_reason"] == "missing-api-key"
        assert r_live["contract_rev"] == GEMINI_DECISIONS_CONTRACT_REV
        assert r_live["backend"] == "gemini-decisions-api" and r_live["fallback_reason"] is None
        assert r_live["results"][0]["calibrated_probability"] == 0.95
        assert r_oserr["backend"] == "litert-gemma-4"
        assert r_oserr["fallback_reason"] == "transport-error-fallback"
