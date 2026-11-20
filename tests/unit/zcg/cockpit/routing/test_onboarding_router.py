"""Unit tests for zcg.cockpit.routing.onboarding_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from zcg.cockpit.routing import onboarding_router
from zcg.core import blueprints
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.auth.security import WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy, SurfaceRing
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.factory import WebAppState
from zcg.web.http.request import Request, WebResponse
from zcg.web.http.router import RouteHandler
from zcg.web.ui.templates import TemplateCatalog

if TYPE_CHECKING:
    from pathlib import Path


def _make_req(
    method: str = "GET",
    path: str = "/",
    *,
    query: str = "",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    body: bytes = b"",
) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query.encode("latin1"),
            "headers": list(headers),
            "client": ("198.51.100.10", 44300),
        },
        body,
    )


def _make_state() -> WebAppState:
    state = MagicMock(spec=WebAppState)
    state.csrf_token = f"tok-{len('iso')}"
    state.templates = TemplateCatalog()
    return state


def _sync_call(handler: RouteHandler, req: Request) -> WebResponse:
    out = handler(req)
    assert isinstance(out, WebResponse)
    return out


class TestOnboardingRouter:
    """Verify Pending-Setup Studio gate, full-page renderer, and /api/modules/onboarding routes."""

    def test_should_render_and_serve_pending_setup_studio_modes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify pending vs configured studio gate, ?view=workspace, ?setup=studio, and HTML."""
        # Arrange
        bare_ws = tmp_path / "bare-node"
        bare_ws.mkdir()
        ws = tmp_path / "persona-profile"
        (ws / "system").mkdir(parents=True)
        (ws / "surfaces/data").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-profile",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "precedence": 90,
                }
            ),
            encoding="utf-8",
        )
        (ws / "surfaces/data/network_scope.json").write_text(
            json.dumps(
                {
                    "network_representation_links": {
                        "downward_child_nodes": [
                            {
                                "node_id": "persona-work",
                                "layer_role": "department",
                                "cockpit_url": "http://persona-work.localhost:8787/",
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        (ws / "README.md").write_text(
            blueprints.render_layer_onboarding_readme(
                "persona-profile",
                "workstation",
                90,
                "persona-profile",
                ["universal-base"],
                entity_kind="individual",
            ),
            encoding="utf-8",
        )
        (ws / "WORKTASK.md").write_text(
            "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n",
            encoding="utf-8",
        )
        state = _make_state()

        # Act
        no_manifest = onboarding_router.should_render_pending_setup_studio(bare_ws, _make_req())
        pending_ok = onboarding_router.should_render_pending_setup_studio(ws, _make_req())
        skip_ws = onboarding_router.should_render_pending_setup_studio(
            ws, _make_req(query="view=workspace")
        )
        skip_docs = onboarding_router.should_render_pending_setup_studio(
            ws, _make_req(query="view=docs")
        )
        skip_tab = onboarding_router.should_render_pending_setup_studio(
            ws, _make_req(query="tab=runtime")
        )
        resp_default = onboarding_router.serve_pending_setup_studio(
            ws,
            _make_req(),
            state=state,
            plugin_id="workstation-control-tower",
            view_archetype="workstation-control-tower",
        )
        (ws / "README.md").write_text("# Configured\n", encoding="utf-8")
        (ws / "WORKTASK.md").write_text(
            "- [x] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n",
            encoding="utf-8",
        )
        configured_skip = onboarding_router.should_render_pending_setup_studio(ws, _make_req())
        forced_studio = onboarding_router.should_render_pending_setup_studio(
            ws, _make_req(query="setup=studio")
        )
        r3_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R3_OPERATOR, loopback_operator_bypass=True
        )
        resp_env = onboarding_router.serve_pending_setup_studio(
            ws,
            _make_req(query="env=dev"),
            state=state,
            plugin_id="workstation-control-tower",
            view_archetype="workstation-control-tower",
            policy=r3_policy,
        )
        atlas_default = onboarding_router.serve_node_atlas_plane(
            ws,
            _make_req(path="/atlas"),
            state=state,
            plugin_id="workstation-control-tower",
            view_archetype="workstation-control-tower",
        )
        atlas_env = onboarding_router.serve_node_atlas_plane(
            ws,
            _make_req(path="/atlas", query="env=dev"),
            state=state,
            plugin_id="workstation-control-tower",
            view_archetype="workstation-control-tower",
            policy=r3_policy,
        )

        # Assert
        assert no_manifest is False
        assert pending_ok is True and skip_ws is False
        assert skip_docs is False and skip_tab is False
        assert configured_skip is False and forced_studio is True
        assert resp_default.status == 200
        assert b"data-island='draft-studio'" in resp_default.body
        assert b"1-Hop Nodes" in resp_default.body
        assert b"persona-work" in resp_default.body
        assert b"Remote Chrome" not in resp_default.body
        assert b"Open this folder in Antigravity Agents" in resp_default.body
        assert b"Copy Folder Path" in resp_default.body
        assert b"<summary>Terminal CLI &amp; Installer Commands (Optional)</summary>" in (
            resp_default.body
        )
        assert b"Copy Terminal CLI" in resp_default.body
        assert b'href="/?view=workspace">Explore Workspace (Skip Setup)' in resp_default.body
        assert b"Copy Prompt for Antigravity Chat" in resp_default.body
        assert b"<script>" not in resp_default.body
        assert resp_env.status == 200 and b'data-zcg-env="dev"' in resp_env.body
        assert atlas_default.status == 200
        assert atlas_default.channel == DeliveryChannel.IMMERSIVE_SYNC
        assert b"id='zcg-atlas-stage'" in atlas_default.body
        assert b'data-island="spatial-atlas"' in atlas_default.body
        assert (
            b"zcg-atlas-icon-btn is-active' href='/atlas' aria-current='page'" in atlas_default.body
        )
        assert b"<a class='is-active' aria-current='page' href='/'>" not in atlas_default.body
        assert b"<h3>2D/3D Network Atlas</h3>" not in atlas_default.body
        assert b"data-zcg-ws-scope" not in atlas_default.body
        assert b'href="/atlas"' in atlas_default.body
        assert b"1-Hop Nodes" in atlas_default.body
        assert atlas_env.status == 200 and b'data-zcg-env="dev"' in atlas_env.body

    def test_render_onboarding_card_pure_local_detected_and_not_installed_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Step 2 pure-local Antigravity detected vs setup-required rendering modes."""
        # Arrange
        ws_dir = tmp_path / "persona-work"
        base_state = {
            "layer_id": "persona-work",
            "workspace_path": str(ws_dir),
            "open_workspace_cmd": f"cd {ws_dir} && agy",
            "install_agents_cmd": "zcg install-antigravity --agents",
            "active_prompt": "/sopen - Initial kickoff prompt",
            "has_saved_draft": False,
            "updated_at": "",
        }
        agy_installed = {
            "any_installed": True,
            "components": {
                "agents": {"installed": True, "version": "2.33.0"},
                "cli": {"installed": True, "version": "0.14.0"},
                "ide": {"installed": False, "version": None},
            },
        }
        agy_missing = {
            "any_installed": False,
            "components": {
                "agents": {"installed": False, "version": None},
                "cli": {"installed": False, "version": None},
                "ide": {"installed": False, "version": None},
            },
        }

        # Act
        html_inst = onboarding_router.render_onboarding_studio_card_html(
            base_state, local_agy=agy_installed
        )
        html_miss = onboarding_router.render_onboarding_studio_card_html(
            base_state, local_agy=agy_missing
        )

        # Assert
        assert "Remote Chrome" not in html_inst and "Remote Chrome" not in html_miss
        assert "✓ Local Antigravity Detected (Agents v2.33.0 · CLI v0.14.0)" in html_inst
        assert f'data-zcg-copy="{ws_dir}"' in html_inst
        assert "<details style='margin:0.35rem 0 0.2rem;'>" in html_inst
        assert "<summary>Terminal CLI &amp; Installer Commands (Optional)</summary>" in html_inst
        assert "Local Antigravity Setup" in html_miss
        assert "<details open style='margin:0.35rem 0 0.2rem;'>" in html_miss
        assert 'data-zcg-copy="zcg install-antigravity --agents"' in html_miss
        assert f'data-zcg-copy="cd {ws_dir} &amp;&amp; agy"' in html_miss
        assert "Downloads and installs (or updates)" in html_miss
        assert (
            "Starts an interactive Antigravity agent chat directly inside your Linux terminal"
            in (html_miss)
        )

    def test_create_onboarding_router_get_draft_reset_and_r3_guard_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET/POST /api/modules/onboarding routes, 422 empty draft, and 403 non-R3 guard."""
        # Arrange
        ws = tmp_path / "dept-iso"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "dept-iso", "layer_role": "department", "precedence": 25}),
            encoding="utf-8",
        )
        router = onboarding_router.create_onboarding_router(ws)
        routes = {(r.method, r.path_template): r.handler for r in router.routes}
        r0_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R0_PUBLIC, loopback_operator_bypass=False
        )
        locked_router = onboarding_router.create_onboarding_router(ws, policy=r0_policy)
        locked_get = locked_router.routes[0].handler

        # Act
        get_init = _sync_call(routes[("GET", "/api/modules/onboarding")], _make_req())
        post_json = _sync_call(
            routes[("POST", "/api/modules/onboarding/draft")],
            _make_req(
                "POST",
                "/api/modules/onboarding/draft",
                headers=((b"content-type", b"application/json"),),
                body=b'{"prompt":"/sopen - Adapted JSON draft"}',
            ),
        )
        get_saved_html = _sync_call(
            routes[("GET", "/api/modules/onboarding")],
            _make_req(headers=((b"hx-request", b"true"),)),
        )
        post_form = _sync_call(
            routes[("POST", "/api/modules/onboarding/draft")],
            _make_req(
                "POST",
                "/api/modules/onboarding/draft",
                headers=((b"content-type", b"application/x-www-form-urlencoded"),),
                body=b"prompt=Form+adapted+draft",
            ),
        )
        reset_resp = _sync_call(
            routes[("POST", "/api/modules/onboarding/reset")],
            _make_req("POST", "/api/modules/onboarding/reset"),
        )

        # Assert
        assert get_init.status == 200
        assert json.loads(get_init.body)["has_saved_draft"] is False
        assert post_json.status == 200 and json.loads(post_json.body)["saved"] is True
        assert b"Saved draft loaded from .zcg/runtime/" in get_saved_html.body
        assert post_form.status == 200 and json.loads(post_form.body)["has_saved_draft"] is True
        assert reset_resp.status == 200 and json.loads(reset_resp.body)["reset"] is True
        with pytest.raises(WebAppError, match="INVALID_ONBOARDING_DRAFT"):
            routes[("POST", "/api/modules/onboarding/draft")](
                _make_req("POST", "/api/modules/onboarding/draft", body=b"")
            )
        with pytest.raises(WebAppError, match="INVALID_ONBOARDING_DRAFT"):
            routes[("POST", "/api/modules/onboarding/draft")](
                _make_req(
                    "POST",
                    "/api/modules/onboarding/draft",
                    headers=((b"content-type", b"application/json"),),
                    body=b"[1, 2]",
                )
            )
        with pytest.raises(WebAppError, match="R3_OPERATOR"):
            locked_get(_make_req(headers=((b"host", b"public.example.org"),)))
