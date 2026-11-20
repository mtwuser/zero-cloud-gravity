"""Unit tests for zcg.cockpit.ops.plugin_sdk.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from zcg.cockpit.ops.plugin_sdk import (
    load_plugin_routers,
    orchestrate_web_app_scaffold,
    resolve_plugin_pack_dir,
    scaffold_plugin_module,
)
from zcg.core.constants import REPO_DIR
from zcg.governance.policy.arch_linter import lint_architecture
from zcg.governance.workspace.scaffolder import configure_node_manifest, scaffold_template_pack
from zcg.web.auth.security import CSRF_HEADER
from zcg.web.http.factory import WebAppState, create_web_app
from zcg.web.http.request import ASGIApp, Message, Scope


async def _invoke_http(
    app: ASGIApp,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
    ]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_headers,
    }
    sent_body = False

    async def receive() -> Message:
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    out: list[Message] = []

    async def send(msg: Message) -> None:
        out.append(msg)

    await app(scope, receive, send)
    start = next(m for m in out if m["type"] == "http.response.start")
    resp_hdrs = {
        bytes(k).decode("latin-1").lower(): bytes(v).decode("latin-1")
        for k, v in start.get("headers", [])
    }
    resp_body = b"".join(
        bytes(m.get("body", b"")) for m in out if m["type"] == "http.response.body"
    )
    return int(start["status"]), resp_hdrs, resp_body


class TestPluginSdk:
    """Verify 4-quadrant resolution, Hexagonal module scaffolding, and contained router loading."""

    def test_resolve_plugin_pack_dir_nominal_fallback_and_non_plugin_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify workspace-first, engine-fallback, invalid ID, and kind!='plugin-stack' checks."""
        # Arrange
        ws_dir = tmp_path / "dept-tech"
        eng_dir = tmp_path / "engine"
        scaffold_template_pack(ws_dir, template_name="alpha-portal", kind="plugin-stack")
        scaffold_template_pack(ws_dir, template_name="fw-only", kind="tool-stack")
        scaffold_template_pack(eng_dir, template_name="shared-cockpit", kind="plugin-stack")
        scaffold_template_pack(ws_dir, template_name="node-work-cockpit", kind="plugin-stack")
        scaffold_template_pack(eng_dir, template_name="node-work-cockpit", kind="plugin-stack")
        broken_dir = ws_dir / "templates/plugin-stack/list-manifest"
        broken_dir.mkdir(parents=True)
        (broken_dir / "template.json").write_text("[1, 2]\n", encoding="utf-8")
        no_tj_dir = ws_dir / "templates/plugin-stack/missing-manifest"
        no_tj_dir.mkdir(parents=True)

        # Act
        res_local = resolve_plugin_pack_dir(ws_dir, "alpha-portal", engine_dir=eng_dir)
        res_fallback = resolve_plugin_pack_dir(ws_dir, "shared-cockpit", engine_dir=eng_dir)
        res_comm = resolve_plugin_pack_dir(ws_dir, "node-work-cockpit", engine_dir=eng_dir)
        res_blank = resolve_plugin_pack_dir(ws_dir, "   ", engine_dir=eng_dir)
        res_bad_id = resolve_plugin_pack_dir(ws_dir, "BAD_ID", engine_dir=eng_dir)
        res_fw = resolve_plugin_pack_dir(ws_dir, "fw-only", engine_dir=eng_dir)
        res_list = resolve_plugin_pack_dir(ws_dir, "list-manifest", engine_dir=eng_dir)
        res_missing = resolve_plugin_pack_dir(ws_dir, "missing-manifest", engine_dir=eng_dir)
        res_absent = resolve_plugin_pack_dir(ws_dir, "ghost-plugin", engine_dir=eng_dir)

        # Assert
        assert res_local == (ws_dir / "templates/alpha-portal").resolve()
        assert res_fallback == (eng_dir / "templates/shared-cockpit").resolve()
        assert res_comm == (eng_dir / "templates/node-work-cockpit").resolve()
        assert res_blank is None
        assert res_bad_id is None
        assert res_fw is None
        assert res_list is None
        assert res_missing is None
        assert res_absent is None

    def test_scaffold_plugin_module_and_load_routers_end_to_end_asgi_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify scaffold_plugin_module passes lint-arch and serves ASGI GET/POST outside Git."""
        # Arrange
        repo_dir = tmp_path / "dept-tech"
        scaffold_template_pack(repo_dir, template_name="alpha-portal", kind="plugin-stack")
        plugin_dir = repo_dir / "templates/alpha-portal"
        tok = "plugin-csrf-tok"

        # Also add a static 'router: APIRouter' file + ignored '_helper.py' + non-.py file
        (plugin_dir / "routers").mkdir(parents=True, exist_ok=True)
        (plugin_dir / "routers/_helper.py").write_text("CONST = 1\n", encoding="utf-8")
        (plugin_dir / "routers/README.txt").write_text("notes\n", encoding="utf-8")
        (plugin_dir / "routers/static_ping.py").write_text(
            "from zcg.web.http.channels import DeliveryChannel\n"
            "from zcg.web.http.request import Request, WebResponse, respond\n"
            "from zcg.web.http.router import APIRouter\n\n"
            'router = APIRouter(prefix="/api/plugins/ping", tags=("ping",))\n\n'
            '@router.get("", channel=DeliveryChannel.ISLAND_SYNC, summary="Ping")\n'
            "def ping(req: Request) -> WebResponse:\n"
            '    return respond(req, html_fragment="<span>pong</span>", data={"pong": True})\n',
            encoding="utf-8",
        )

        # Act
        dry_res = scaffold_plugin_module(
            repo_dir, plugin_id="alpha-portal", module_name="batch-verifier", dry_run=True
        )
        scaf_res = scaffold_plugin_module(
            repo_dir,
            plugin_id="alpha-portal",
            module_name="batch-verifier",
            description="Verify roasted lot quality",
        )
        scaf_second = scaffold_plugin_module(
            repo_dir,
            plugin_id="alpha-portal",
            module_name="lead-intake",
            route_prefix="/api/plugins/leads",
        )
        arch_audit = lint_architecture(plugin_dir, check_tests=False)

        ws_live = tmp_path / "org-alpha-runtime"
        ws_live.mkdir()
        app = create_web_app(
            title="Plugin Portal Test",
            router_factory=lambda st: load_plugin_routers(ws_live, plugin_dir, state=st),
            template_dirs=(plugin_dir / "web/templates",),
            csrf_token=tok,
        )
        # Exercise second call to verify idempotent synthetic package reuse in sys.modules
        app_reload = create_web_app(
            title="Plugin Portal Reload",
            router_factory=lambda st: load_plugin_routers(ws_live, plugin_dir, state=st),
            template_dirs=(plugin_dir / "web/templates",),
            csrf_token=tok,
        )

        async def _exercise() -> dict[str, Any]:
            st_empty_h, _, b_empty_h = await _invoke_http(
                app, "GET", "/api/plugins/batch-verifier", headers={"hx-request": "true"}
            )
            st_bad, _, b_bad = await _invoke_http(
                app,
                "POST",
                "/api/plugins/batch-verifier",
                headers={CSRF_HEADER: tok, "content-type": "application/json"},
                body=b'{"title": "   "}',
            )
            st_post_j, _, b_post_j = await _invoke_http(
                app,
                "POST",
                "/api/plugins/batch-verifier",
                headers={CSRF_HEADER: tok, "content-type": "application/json"},
                body=b'{"title": "Batch 001", "summary": "Biochar Grade A"}',
            )
            st_post_f, _, b_post_f = await _invoke_http(
                app,
                "POST",
                "/api/plugins/batch-verifier",
                headers={
                    CSRF_HEADER: tok,
                    "hx-request": "true",
                    "content-type": "application/x-www-form-urlencoded",
                },
                body=b"title=Batch+002&status=approved",
            )
            st_list_j, _, b_list_j = await _invoke_http(app, "GET", "/api/plugins/batch-verifier")
            st_ping, _, b_ping = await _invoke_http(app_reload, "GET", "/api/plugins/ping")
            return {
                "empty_h": (st_empty_h, b_empty_h),
                "bad": (st_bad, b_bad),
                "post_j": (st_post_j, json.loads(b_post_j)),
                "post_f": (st_post_f, b_post_f),
                "list_j": (st_list_j, json.loads(b_list_j)),
                "ping": (st_ping, json.loads(b_ping)),
            }

        results = asyncio.run(_exercise())
        tj_after = json.loads((plugin_dir / "template.json").read_text(encoding="utf-8"))

        # Assert
        assert dry_res["dry_run"] is True
        assert scaf_res["module_package"] == "batch_verifier"
        assert scaf_second["route_prefix"] == "/api/plugins/leads"
        assert arch_audit["passed"] is True
        assert tj_after["runtime_service"]["plugin_routers"] == [
            "routers/batch_verifier.py",
            "routers/lead_intake.py",
        ]
        assert results["empty_h"][0] == 200 and b"0 records" in results["empty_h"][1]
        assert results["bad"][0] == 422 and b"VALIDATION_ERROR" in results["bad"][1]
        assert results["post_j"][0] == 201 and results["post_j"][1]["count"] == 1
        assert results["post_f"][0] == 201 and b"Batch 002" in results["post_f"][1]
        assert results["list_j"][0] == 200 and len(results["list_j"][1]["items"]) == 2
        assert results["ping"][0] == 200 and results["ping"][1] == {"pong": True}
        assert (ws_live / ".zcg/runtime/alpha-portal_batch_verifier.sqlite3").is_file()
        assert not list(plugin_dir.rglob("*.sqlite3"))

    def test_scaffold_plugin_module_bipolar_validation_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify validation guards on invalid IDs, prefixes, non-plugin packs, and duplicates."""
        # Arrange
        repo_dir = tmp_path / "repo"
        scaffold_template_pack(repo_dir, template_name="alpha-portal", kind="plugin-stack")
        scaffold_template_pack(repo_dir, template_name="fw-pack", kind="tool-stack")
        scaffold_plugin_module(repo_dir, plugin_id="alpha-portal", module_name="dup-mod")

        # Act
        invalid_calls: tuple[tuple[str, str, str | None, str], ...] = (
            ("BAD_ID", "mod-a", None, "Invalid plugin_id"),
            ("alpha-portal", "BAD_MOD", None, "Invalid module_name"),
            ("alpha-portal", "mod-a", "no-slash", "Invalid route_prefix"),
            ("alpha-portal", "mod-a", "/api/../escape", "Invalid route_prefix"),
            ("fw-pack", "mod-a", None, "not found"),
            ("alpha-portal", "dup-mod", None, "already exists"),
        )

        # Assert
        for pid, mname, pref, expected_msg in invalid_calls:
            with pytest.raises(ValueError, match=expected_msg):
                scaffold_plugin_module(
                    repo_dir, plugin_id=pid, module_name=mname, route_prefix=pref
                )

    def test_load_plugin_routers_empty_containment_permissions_and_contract_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify empty dir, symlink escape, world-writable mode, and missing router contract."""
        # Arrange
        ws = tmp_path / "ws"
        ws.mkdir()
        state = MagicMock(spec=WebAppState)

        empty_pdir = tmp_path / "no-routers-plugin"
        empty_pdir.mkdir()

        outside_py = tmp_path / "outside_evil.py"
        outside_py.write_text("router = None\n", encoding="utf-8")
        sym_pdir = tmp_path / "sym-plugin"
        (sym_pdir / "routers").mkdir(parents=True)
        (sym_pdir / "routers/escape.py").symlink_to(outside_py)

        ww_pdir = tmp_path / "ww-plugin"
        (ww_pdir / "routers").mkdir(parents=True)
        ww_file = ww_pdir / "routers/unsafe.py"
        ww_file.write_text("router = None\n", encoding="utf-8")
        ww_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IWOTH)

        bad_contract_pdir = tmp_path / "bad-contract-plugin"
        (bad_contract_pdir / "routers").mkdir(parents=True)
        (bad_contract_pdir / "routers/broken.py").write_text(
            "NOT_A_ROUTER = 42\n", encoding="utf-8"
        )

        # Act
        empty_res = load_plugin_routers(ws, empty_pdir, state=state)

        # Assert
        assert empty_res == ()
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            load_plugin_routers(ws, sym_pdir, state=state)
        try:
            with pytest.raises(ValueError, match="UNSAFE_PLUGIN_ROUTER_PERMISSIONS"):
                load_plugin_routers(ws, ww_pdir, state=state)
        finally:
            ww_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        with pytest.raises(ValueError, match="INVALID_PLUGIN_ROUTER_CONTRACT"):
            load_plugin_routers(ws, bad_contract_pdir, state=state)

    def test_community_overlay_read_only_guard_and_web_app_orchestration_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify surfaces/web overlay for community/local packs and standalone/networked apps."""
        # Arrange
        consumer_ws = tmp_path / "dept-ops"
        consumer_ws.mkdir()
        oss_ws = tmp_path / "oss-upstream"
        configure_node_manifest(
            oss_ws, layer_id="root", layer_role="workstation", entity_kind="open-source"
        )
        scaffold_template_pack(oss_ws, template_name="node-work-cockpit", kind="plugin-stack")
        standalone_dir = tmp_path / "solo-web"
        networked_dir = tmp_path / "net-web"

        # Act
        comm_overlay = scaffold_plugin_module(
            consumer_ws,
            plugin_id="node-work-cockpit",
            module_name="kpi-feed",
            engine_dir=REPO_DIR,
        )
        local_overlay = scaffold_plugin_module(
            consumer_ws, plugin_id="local", module_name="local-note"
        )
        oss_in_pack = scaffold_plugin_module(
            oss_ws, plugin_id="node-work-cockpit", module_name="core-widget", overlay=False
        )
        solo_app = orchestrate_web_app_scaffold(
            REPO_DIR, standalone_dir, title="Solo App", standalone=True
        )
        net_app = orchestrate_web_app_scaffold(
            REPO_DIR, networked_dir, parent_dir=oss_ws, standalone=False
        )

        # Assert
        assert comm_overlay["target_mode"] == "surface-overlay"
        assert (consumer_ws / "surfaces/web/routers/kpi_feed.py").is_file()
        assert (consumer_ws / "surfaces/web/templates/partials/kpi-feed.html").is_file()
        assert not (consumer_ws / "templates").exists()
        assert local_overlay["target_mode"] == "surface-overlay"
        assert oss_in_pack["target_mode"] == "plugin-pack"
        assert solo_app["layer_rules_applied"] is None
        assert net_app["layer_rules_applied"] is not None
        assert (networked_dir / ".agents/zcg.mk").is_file()
        with pytest.raises(ValueError, match="COMMUNITY_PLUGIN_READ_ONLY"):
            scaffold_plugin_module(
                consumer_ws,
                plugin_id="node-work-cockpit",
                module_name="forbidden-edit",
                overlay=False,
                engine_dir=REPO_DIR,
            )
        with pytest.raises(ValueError, match="COMMUNITY_PLUGIN_READ_ONLY"):
            scaffold_plugin_module(
                consumer_ws, plugin_id="local", module_name="bad-local", overlay=False
            )
