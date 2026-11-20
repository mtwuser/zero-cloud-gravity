"""Unit tests for zcg.cockpit.routing.capability_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from zcg.cockpit.ops.asgi import create_node_cockpit_asgi_app
from zcg.cockpit.routing.capability_router import create_capability_router
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import Message, Scope


async def _call_asgi(
    app: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    hdrs = dict(headers or {})
    hdrs.setdefault("host", "persona-profile.localhost:8790")
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_h,
    }
    sent: list[Message] = []
    consumed = False

    async def receive() -> Message:
        nonlocal consumed
        chunk = b"" if consumed else body
        consumed = True
        return {"type": "http.request", "body": chunk, "more_body": False}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(bytes(m.get("body", b"")) for m in sent[1:])


class TestCapabilityRouter:
    """1:1 unit suite for /api/modules/capabilities R3 toggles, commits, and live ASGI sync."""

    def test_capability_router_list_toggle_reset_commit_and_r3_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET/POST /api/modules/capabilities HTML+JSON, R3 guard, and C3 Git commit."""
        # Arrange
        ws = tmp_path / "work-iso"
        (ws / "system").mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True
        )
        manifest = {
            "layer_id": "work-iso",
            "layer_role": "squad",
            "capability_policy": {
                "mandatory_modules": ["work_ledger"],
                "forbidden_modules": ["wallet_treasury"],
            },
        }
        (ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)

        tok = f"tok-{tmp_path.name}"
        rtr = create_capability_router(
            ws,
            view_archetype="personal-work-cockpit",
            default_modules=("work_ledger", "docs_reader", "crud", "vault"),
            crud_title="Ventures & Opportunity Log",
        )
        app = create_web_app(title="caps", csrf_token=tok, routers=(rtr,), allowed_hosts=("*",))
        csrf_h = {"x-zcg-csrf-token": tok}
        hx_form = {
            **csrf_h,
            "hx-request": "true",
            "content-type": "application/x-www-form-urlencoded",
        }
        json_h = {**csrf_h, "content-type": "application/json"}

        # Act
        async def _run() -> list[tuple[int, bytes]]:
            return [
                await _call_asgi(
                    app, "GET", "/api/modules/capabilities", headers={"host": "ext.example.org"}
                ),
                await _call_asgi(
                    app, "GET", "/api/modules/capabilities", headers={"hx-request": "true"}
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/toggle",
                    headers=hx_form,
                    body=urlencode({"module_id": "vault", "enabled": "0"}).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/toggle",
                    headers=json_h,
                    body=json.dumps({"module_id": "role_projection", "enabled": True}).encode(),
                ),
                await _call_asgi(app, "POST", "/api/modules/capabilities/toggle", headers=csrf_h),
                await _call_asgi(
                    app, "POST", "/api/modules/capabilities/toggle", headers=json_h, body=b"[1]"
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/commit",
                    headers={**hx_form},
                    body=urlencode(
                        {"commit_message": "chore(node): customize capabilities"}
                    ).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/commit",
                    headers=json_h,
                    body=b'{"commit_message":"chore(node): repeat"}',
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/commit",
                    headers=json_h,
                    body=b'{"commit_message":"bad"}',
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/modules/capabilities/toggle",
                    headers={**csrf_h, "hx-request": "true", **json_h},
                    body=b'{"action":"reset"}',
                ),
            ]

        (
            r_403,
            r_get,
            r_off,
            r_on,
            r_empty,
            r_bad_json,
            r_com,
            r_c409,
            r_c422,
            r_rst,
        ) = asyncio.run(_run())

        # Assert
        assert r_403[0] == 403 and b"R3_OPERATOR_REQUIRED" in r_403[1]
        assert r_get[0] == 200 and b"Ventures &amp; Opportunity Log" in r_get[1]
        assert b"Mandatory" in r_get[1] and b"Blocked" in r_get[1] and b"Optional" in r_get[1]
        assert b"zcg-cli-hint" in r_get[1] and b"zcg check-env-promotion" in r_get[1]
        assert r_off[0] == 200 and b"Disabled capability <code>vault</code>" in r_off[1]
        assert b"Reset to Archetype Defaults" in r_off[1]
        assert r_on[0] == 200 and "role_projection" in json.loads(r_on[1])["enabled_modules"]
        assert r_empty[0] == 422 and r_bad_json[0] == 400
        assert r_com[0] == 200 and b"Committed <code>" in r_com[1]
        assert r_c409[0] == 409 and r_c422[0] == 422
        assert r_rst[0] == 200 and b"Restored archetype default capabilities" in r_rst[1]

    def test_live_zero_restart_workspace_tab_update_after_capability_toggle_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify toggling a capability updates GET / and /healthz immediately with 0 restarts."""
        # Arrange
        ws = tmp_path / "live-node"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "live-node", "layer_role": "workstation"}), encoding="utf-8"
        )
        tok = f"tok-live-{tmp_path.name}"
        app = create_node_cockpit_asgi_app(ws, csrf_token=tok)
        json_h = {"x-zcg-csrf-token": tok, "content-type": "application/json"}

        # Act
        async def _exercise() -> tuple[bytes, bytes, bytes]:
            _, b_init = await _call_asgi(app, "GET", "/")
            await _call_asgi(
                app,
                "POST",
                "/api/modules/capabilities/toggle",
                headers=json_h,
                body=b'{"module_id":"vault","enabled":true}',
            )
            _, b_after = await _call_asgi(app, "GET", "/")
            _, b_hz = await _call_asgi(app, "GET", "/healthz")
            return b_init, b_after, b_hz

        b_init, b_after, b_hz = asyncio.run(_exercise())

        # Assert
        assert b"Document Vault" not in b_init
        assert b"Document Vault" in b_after
        assert "vault" in json.loads(b_hz)["enabled_modules"]
