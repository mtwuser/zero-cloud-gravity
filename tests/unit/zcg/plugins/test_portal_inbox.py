"""Unit tests for zcg.plugins.portal_inbox.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.plugins.portal_channels import (
    record_portal_contact_message,
    record_portal_handshake_request,
)
from zcg.plugins.portal_inbox import (
    INBOX_TRIAGE_REL_PATH,
    build_public_exposure_context,
    check_workspace_portal_exposure,
    create_portal_inbox_router,
    enforce_portal_exposure_gate,
    inspect_portal_mailbox,
    parse_public_exposure_spec,
    triage_portal_mailbox_item,
    update_public_exposure_mode,
)
from zcg.web.auth.security import WebAppError
from zcg.web.auth.surface_access import SURFACE_RING_HEADER
from zcg.web.http.factory import WebAppState, create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
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

    hdrs = list(headers or [])
    if not any(k.lower() == b"host" for k, _ in hdrs):
        hdrs.append((b"host", b"127.0.0.1:8790"))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": hdrs,
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestPortalInbox:
    """Verify 4-mode local exposure switch, facet guards, and R3 mailbox triage router."""

    def test_parse_exposure_spec_and_enforce_kill_switch_and_members_gate_expected(self) -> None:
        """Verify exposure modes, security-facet rejection, and disabled/members-only gates."""
        # Arrange
        pub_m = {
            "visibility": "public",
            "public_exposure": {
                "mode": "online",
                "availability_note": "Open for Chess & B2B",
                "public_facets": [
                    "skip-non-dict",
                    {"pillar": "", "label": "Skip"},
                    {
                        "pillar": "game",
                        "label": "Tabletop Game Arena",
                        "summary": "Invite for 1v1 Chess",
                        "purpose": "game-match-invite",
                        "public_url": "javascript:alert(1)",
                    },
                    {
                        "pillar": "wallet",
                        "label": "R0 Stewardship",
                        "purpose": "unknown-purpose",
                        "public_url": "",
                    },
                ],
            },
        }

        # Act
        spec_on = parse_public_exposure_spec(pub_m)
        spec_def = parse_public_exposure_spec({"public_exposure": {"mode": "invalid"}})
        spec_mem = parse_public_exposure_spec({"public_exposure": {"mode": "members-only"}})
        spec_off = parse_public_exposure_spec({"public_exposure": {"mode": "disabled"}})

        # Assert
        assert spec_on.mode == "online"
        assert len(spec_on.public_facets) == 2
        assert spec_on.public_facets[0]["public_url"] == "#contact"
        assert spec_on.public_facets[1]["purpose"] == "personal-connection"
        assert spec_def.mode == "inbox-only"
        exp_ctx = build_public_exposure_context(pub_m)
        assert exp_ctx["exposure_mode"] == "online" and len(exp_ctx["public_facets"]) == 2
        check_workspace_portal_exposure(None, caller_ring="R0")
        enforce_portal_exposure_gate(spec_on, caller_ring="R0")
        enforce_portal_exposure_gate(spec_off, caller_ring="R3")
        enforce_portal_exposure_gate(spec_mem, caller_ring="R1")
        with pytest.raises(WebAppError, match="disabled"):
            enforce_portal_exposure_gate(spec_off, caller_ring="R0")
        with pytest.raises(WebAppError, match="restricted"):
            enforce_portal_exposure_gate(spec_mem, caller_ring="R0")
        with pytest.raises(ValueError, match="PRIVATE_SECURITY_FACET_FORBIDDEN"):
            parse_public_exposure_spec(
                {"public_exposure": {"public_facets": [{"pillar": "security", "label": "Sec"}]}}
            )

    def test_portal_inbox_router_exposure_switch_and_mailbox_triage_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET/POST /api/modules/portal-inbox R3 guards, exposure updates, and triage."""
        # Arrange
        assert inspect_portal_mailbox(None) == {"items": [], "pending_count": 0, "total_count": 0}
        ws_bare = tmp_path / "bare"
        ws_bare.mkdir()
        with pytest.raises(ValueError, match="WORKSPACE_MANIFEST_MISSING"):
            update_public_exposure_mode(ws_bare, mode="online")

        ws = tmp_path / "persona-profile"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "persona-profile", "visibility": "public"}), encoding="utf-8"
        )
        states: list[WebAppState] = []
        app = create_web_app(
            routers=(create_portal_inbox_router(ws),), state_out=states, allowed_hosts=("*",)
        )
        csrf_b = states[0].csrf_token.encode("ascii")

        # Empty mailbox first, plus non-dict JSONL line & non-dict triage file resilience
        st_empty, b_empty = asyncio.run(
            _call(app, "GET", "/api/modules/portal-inbox", headers=[(b"hx-request", b"true")])
        )
        st_ws_mode, b_ws_mode = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/portal-inbox",
                query="mode=workspace",
                headers=[(b"hx-request", b"true")],
            )
        )
        st_adm_mode, b_adm_mode = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/portal-inbox",
                query="mode=admin",
                headers=[(b"hx-request", b"true")],
            )
        )
        check_workspace_portal_exposure(ws, caller_ring="R0")
        c_rec = record_portal_contact_message(
            ws, sender_name="Ada", sender_contact="ada@example.org", message="Tutoring inquiry"
        )
        h_rec = record_portal_handshake_request(
            ws, peer_node_id="peer-game", purpose="personal-connection", note="1v1 Chess?"
        )
        with (ws / ".zcg/runtime/portal/contact_inbox.jsonl").open("a", encoding="utf-8") as fh:
            fh.write("\n[1, 2]\n")
        (ws / INBOX_TRIAGE_REL_PATH).write_text("[1, 2]\n", encoding="utf-8")

        # Act
        st_r0, _ = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/portal-inbox",
                headers=[(SURFACE_RING_HEADER.encode("ascii"), b"R0")],
            )
        )
        st_exp_ok, b_exp_ok = asyncio.run(
            _call(
                app,
                "POST",
                "/api/modules/portal-inbox/exposure",
                body=b"mode=inbox-only&availability_note=Async+Mailbox",
                headers=[
                    (b"content-type", b"application/x-www-form-urlencoded"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_exp_bad, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/modules/portal-inbox/exposure",
                body=b'{"mode":"invalid"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_tri_ok, b_tri_ok = asyncio.run(
            _call(
                app,
                "POST",
                "/api/modules/portal-inbox/triage",
                body=json.dumps({"item_id": c_rec["receipt_id"], "decision": "accepted"}).encode(),
                headers=[
                    (b"content-type", b"application/json"),
                    (b"accept", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_tri_empty_body, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/modules/portal-inbox/triage",
                body=b"",
                headers=[(b"x-zcg-csrf-token", csrf_b)],
            )
        )
        with pytest.raises(ValueError, match="INVALID_INBOX_TRIAGE_DECISION"):
            triage_portal_mailbox_item(ws, item_id=h_rec["request_id"], decision="later")

        # Assert
        assert st_empty == 200 and b"0 requests" in b_empty
        assert st_ws_mode == 200 and b"External Mailbox" in b_ws_mode
        assert st_adm_mode == 200 and b"Public Exposure" in b_adm_mode
        assert b"Preview Local /portal" in b_adm_mode
        assert st_r0 == 403
        assert st_exp_ok == 200 and b"inbox-only" in b_exp_ok
        assert st_exp_bad == 422
        assert st_tri_ok == 200
        tri_doc = json.loads(b_tri_ok)
        assert tri_doc["mailbox"]["total_count"] == 2
        assert tri_doc["mailbox"]["pending_count"] == 1
        assert st_tri_empty_body == 422
