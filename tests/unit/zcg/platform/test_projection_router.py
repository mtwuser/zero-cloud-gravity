"""Unit tests for zcg.platform.projection_router.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from zcg.platform.projection import DisclosureTier, PayloadFieldSegment, RolePayloadProjector
from zcg.platform.projection_router import create_role_projection_router, parse_payload_segments
from zcg.web.factory import create_web_app
from zcg.web.security import WebAppError


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": headers or [],
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestProjectionRouter:
    """Verify parse_payload_segments and minimal-disclosure RolePayloadProjector routing."""

    def test_configured_segments_withhold_onboarding_fields_until_day1_stage_expected(self) -> None:
        """Verify GET projection withholds DAY1_ONBOARDING fields at candidate_application."""
        # Arrange
        segments = (
            PayloadFieldSegment("summary", DisclosureTier.CORE_SUMMARY, "Principal Architect"),
            PayloadFieldSegment("onboarding_ref", DisclosureTier.DAY1_ONBOARDING, "RECORD-99"),
        )
        router = create_role_projection_router(
            projector=RolePayloadProjector(),
            default_segments=segments,
            resource_id="profile-01",
            shared_packs=("universal-base",),
        )
        app = create_web_app(routers=(router,))

        async def _scenario() -> tuple[dict[str, Any], dict[str, Any], bytes]:
            _, b_cand = await _call(
                app, "GET", "/api/platform/projection", query="stage=candidate_application&target="
            )
            _, b_day1 = await _call(
                app,
                "GET",
                "/api/platform/projection",
                query="stage=day1_onboarding&target=org-peer",
            )
            _, b_swap = await _call(
                app,
                "GET",
                "/api/platform/projection",
                query="stage=candidate_application",
                headers=[(b"hx-request", b"true")],
            )
            return json.loads(b_cand), json.loads(b_day1), b_swap

        # Act
        cand_out, day1_out, swap_html = asyncio.run(_scenario())

        # Assert
        cand_cap = cand_out["capsule"]
        day1_cap = day1_out["capsule"]
        assert "onboarding_ref" not in cand_cap["disclosed_fields"]
        assert "onboarding_ref" in cand_cap["withheld_field_ids"]
        assert cand_cap["target_node_id"] == "peer-node"
        assert day1_cap["disclosed_fields"]["onboarding_ref"] == "RECORD-99"
        assert b"Role Projection (profile-01)" in swap_html

    def test_dynamic_post_projects_caller_segments_and_citation_receipts_expected(self) -> None:
        """Verify POST projects caller-supplied segments with citation receipts and shared_packs."""
        # Arrange
        app = create_web_app(
            routers=(create_role_projection_router(shared_packs=("science-base",)),)
        )
        receipt = "gov-iso::statutes.md#s1@0123456789abcdef:E3"
        payload_custom_packs = {
            "stage": "b2b_proposal",
            "resource_id": "venture-01",
            "target_node_id": "client-node",
            "shared_packs": ["business-base"],
            "segments": [
                {"field_id": "headline", "tier": "core_summary", "value": "Systems Audit"},
                {
                    "field_id": "statute",
                    "tier": "verified_competency",
                    "value": "Verified",
                    "citation_receipt": receipt,
                },
            ],
        }
        payload_fallback_packs = {
            "stage": "b2b_proposal",
            "shared_packs": "not-a-list",
            "segments": [{"field_id": "headline", "tier": "core_summary", "value": "Summary"}],
        }

        async def _scenario() -> tuple[dict[str, Any], dict[str, Any]]:
            _, b1 = await _call(
                app,
                "POST",
                "/api/platform/projection",
                body=json.dumps(payload_custom_packs).encode(),
            )
            _, b2 = await _call(
                app,
                "POST",
                "/api/platform/projection",
                body=json.dumps(payload_fallback_packs).encode(),
            )
            return json.loads(b1), json.loads(b2)

        # Act
        out_custom, out_fallback = asyncio.run(_scenario())

        # Assert
        assert out_custom["capsule"]["shared_packs"] == ["business-base"]
        assert receipt in out_custom["capsule"]["citation_receipts"]
        assert out_fallback["capsule"]["shared_packs"] == ["science-base"]

    def test_parse_payload_segments_rejects_empty_and_invalid_tier_inputs_expected(self) -> None:
        """Verify parse_payload_segments raises 422 WebAppError on empty or invalid tier inputs."""
        # Arrange
        bad_tier = [{"field_id": "headline", "tier": "unknown_tier", "value": "x"}]

        # Act
        with pytest.raises(WebAppError) as exc_empty:
            parse_payload_segments(())
        with pytest.raises(WebAppError) as exc_tier:
            parse_payload_segments(bad_tier)

        # Assert
        assert exc_empty.value.http_status == 422
        assert exc_tier.value.http_status == 422

    def test_bipolar_unconfigured_get_invalid_stage_and_post_payload_guards_expected(self) -> None:
        """Verify 422 unconfigured GET, 400 invalid stage/non-dict POST, and 422 bad segments."""
        # Arrange
        app = create_web_app(routers=(create_role_projection_router(),))

        async def _scenario() -> tuple[int, int, int, int]:
            s_unconf, _ = await _call(app, "GET", "/api/platform/projection")
            s_bad_stage, _ = await _call(
                app, "GET", "/api/platform/projection", query="stage=unknown"
            )
            s_bad_json, _ = await _call(app, "POST", "/api/platform/projection", body=b"")
            s_bad_segs, _ = await _call(
                app,
                "POST",
                "/api/platform/projection",
                body=json.dumps({"segments": "invalid"}).encode(),
            )
            return s_unconf, s_bad_stage, s_bad_json, s_bad_segs

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (422, 400, 400, 422)
