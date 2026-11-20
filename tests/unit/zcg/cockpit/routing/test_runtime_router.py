"""Unit tests for zcg.cockpit.routing.runtime_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from zcg.cockpit.routing.runtime_router import create_runtime_router
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.auth.security import WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy, SurfaceRing
from zcg.web.http.request import Request, WebResponse
from zcg.web.http.router import RouteHandler

if TYPE_CHECKING:
    from pathlib import Path


def _make_req(
    path: str = "/api/modules/runtime",
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": list(headers),
            "client": ("198.51.100.20", 44321),
        },
        b"",
    )


def _sync_call(handler: RouteHandler, req: Request) -> WebResponse:
    out = handler(req)
    assert isinstance(out, WebResponse)
    return out


class TestRuntimeRouter:
    """Verify /api/modules/runtime and /check-updates routes, HTML/JSON output, and R3 guards."""

    def test_runtime_router_overview_online_check_and_r3_guard_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET overview, GET /check-updates, wallet airlock fallback, and 403 non-R3."""
        # Arrange
        ws = tmp_path / "dept-iso"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "dept-iso",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "precedence": 25,
                    "engine_version": "1.1.0",
                }
            ),
            encoding="utf-8",
        )
        wallet_ws = tmp_path / "persona-wallet"
        (wallet_ws / "system").mkdir(parents=True)
        (wallet_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "layer_role": "department",
                    "entity_kind": "individual",
                    "personal_pillar": "wallet",
                    "view_archetype": "sovereign-wallet-cockpit",
                    "precedence": 88,
                }
            ),
            encoding="utf-8",
        )

        def _fake_checker(
            workspace: Path, *, local_runtime: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            assert workspace == ws.resolve()
            assert local_runtime is not None
            return {
                "checked": True,
                "reason": "OK",
                "updates_available": True,
                "components": {
                    "agents": {
                        "installed_version": "2.32.0",
                        "latest_version": "2.33.0",
                        "update_available": True,
                        "status": "update-available",
                    },
                    "cli": {
                        "installed_version": "0.14.0",
                        "latest_version": "0.14.0",
                        "update_available": False,
                        "status": "up-to-date",
                    },
                    "ide": {
                        "installed_version": None,
                        "latest_version": None,
                        "update_available": False,
                        "status": "unreachable",
                    },
                },
            }

        open_rtr = create_runtime_router(ws, online_checker=_fake_checker)
        open_routes = {(r.method, r.path_template): r.handler for r in open_rtr.routes}

        r3_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R3_OPERATOR, loopback_operator_bypass=True
        )
        wallet_rtr = create_runtime_router(wallet_ws, policy=r3_policy)
        wallet_routes = {(r.method, r.path_template): r.handler for r in wallet_rtr.routes}

        r0_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R0_PUBLIC, loopback_operator_bypass=False
        )
        locked_rtr = create_runtime_router(ws, policy=r0_policy)
        locked_routes = {(r.method, r.path_template): r.handler for r in locked_rtr.routes}

        # Act
        resp_json = _sync_call(open_routes[("GET", "/api/modules/runtime")], _make_req())
        resp_html = _sync_call(
            open_routes[("GET", "/api/modules/runtime")],
            _make_req(headers=((b"hx-request", b"true"),)),
        )
        resp_chk_json = _sync_call(
            open_routes[("GET", "/api/modules/runtime/check-updates")],
            _make_req("/api/modules/runtime/check-updates"),
        )
        resp_chk_html = _sync_call(
            open_routes[("GET", "/api/modules/runtime/check-updates")],
            _make_req(
                "/api/modules/runtime/check-updates",
                headers=((b"hx-request", b"true"),),
            ),
        )
        resp_wallet_chk = _sync_call(
            wallet_routes[("GET", "/api/modules/runtime/check-updates")],
            _make_req(
                "/api/modules/runtime/check-updates",
                headers=((b"host", b"persona-wallet.localhost:8788"),),
            ),
        )

        # Assert
        payload = json.loads(resp_json.body)
        assert resp_json.status == 200
        assert payload["update_plan"]["layer_id"] == "dept-iso"
        assert "local_antigravity" in payload and "agent_guidance" in payload
        assert resp_html.status == 200
        assert b"id='zcg-runtime-panel'" in resp_html.body
        assert b"Local Antigravity Environment" in resp_html.body

        chk_payload = json.loads(resp_chk_json.body)
        assert resp_chk_json.status == 200 and chk_payload["online_check"]["checked"] is True
        assert resp_chk_html.status == 200
        assert b"Update available: v2.32.0" in resp_chk_html.body

        wallet_payload = json.loads(resp_wallet_chk.body)
        assert resp_wallet_chk.status == 200
        assert wallet_payload["online_check"]["checked"] is False
        assert wallet_payload["online_check"]["reason"] == "WALLET_AIRLOCK_OFFLINE"

        for route_path in ("/api/modules/runtime", "/api/modules/runtime/check-updates"):
            with pytest.raises(WebAppError, match="R3 operator") as exc_info:
                locked_routes[("GET", route_path)](
                    _make_req(route_path, headers=((b"host", b"public.example.org"),))
                )
            assert exc_info.value.error_code == "NODE_ADMIN_OPERATOR_REQUIRED"
            assert exc_info.value.http_status == 403
