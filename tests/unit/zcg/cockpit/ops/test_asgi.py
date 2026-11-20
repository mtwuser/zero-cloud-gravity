"""Unit tests for zcg.cockpit.ops.asgi.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from zcg.cockpit.ops.asgi import (
    create_node_cockpit_asgi_app,
    resolve_cockpit_web_dirs,
    run_cockpit_daemon_cli,
)
from zcg.cockpit.ops.plugin_sdk import scaffold_plugin_module
from zcg.web.auth.security import CSRF_HEADER, DocsAccessMode, WebAppError
from zcg.web.http.channels import CHANNEL_HEADER, DeliveryChannel
from zcg.web.http.request import Message, Scope
from zcg.web.ui.static_files import CURRENT_ENGINE_ASSET_DIGEST


async def _invoke_http(
    app: Any, method: str, path: str, *, query: str = "",
    headers: dict[str, str] | None = None, chunks: list[bytes] | None = None,
) -> tuple[int, dict[str, str], bytes]:  # fmt: skip
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http", "method": method, "path": path,
        "query_string": query.encode("latin1"), "headers": raw_h,
    }  # fmt: skip
    body_list, idx, sent = chunks if chunks is not None else [b""], 0, list[Message]()

    async def receive() -> Message:
        nonlocal idx
        piece = body_list[idx]
        idx += 1
        return {"type": "http.request", "body": piece, "more_body": idx < len(body_list)}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    start = sent[0]
    resp_h = {
        bytes(k).decode("latin1"): bytes(v).decode("latin1") for k, v in start.get("headers", [])
    }
    body = b"".join(bytes(m.get("body", b"")) for m in sent[1:])
    return int(start["status"]), resp_h, body


class TestAsgi:
    """Verify Native Python 3.14 ASGI routes, partial swaps, HTTP 286, SSE, and security guards."""

    def test_lifespan_scope_guard_index_swaps_and_static_containment_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify lifespan, unsupported scope, full vs partial /, and static containment."""
        # Arrange
        ws = tmp_path / "persona-work"
        (ws / "surfaces/data").mkdir(parents=True)
        (ws / "surfaces/web/data").mkdir(parents=True)
        scope_doc = {
            "layer_id": "persona-work",
            "own_node_ledger": {"in_progress_count": 0},
            "representation_context": {"enabled_modules": ["crud"]},
        }
        (ws / "surfaces/data/node_scope.json").write_text(json.dumps(scope_doc), "utf-8")
        (ws / "surfaces/data/network_scope.json").write_text("[1, 2]", "utf-8")
        (ws / "surfaces/web/data/fallback.json").write_text('{"fallback":true}', "utf-8")
        (ws / "surfaces/web/blob.unknownext").write_bytes(b"\x00\x01")
        tok_a = "iso-tok-a"
        app = create_node_cockpit_asgi_app(ws, csrf_token=tok_a)

        async def _run() -> int:
            async def _noop_recv() -> Message:
                return {"type": "websocket.disconnect"}

            async def _noop_send(msg: Message) -> None:
                return None

            with pytest.raises(WebAppError, match="Unsupported ASGI scope"):
                await app({"type": "websocket"}, _noop_recv, _noop_send)

            # Fallback index before index.html exists, then materialized index.html
            st0, h0, b0 = await _invoke_http(app, "GET", "/")
            assert st0 == 200 and b"<title>persona-work</title>" in b0
            assert h0[CHANNEL_HEADER] == DeliveryChannel.ISLAND_SYNC.value
            (ws / "surfaces/web/index.html").write_text("<html>Full Cockpit</html>", "utf-8")
            st1, _, b1 = await _invoke_http(
                app, "GET", "/", headers={"hx-request": "true", "hx-boosted": "true"}
            )
            assert st1 == 200 and b"Full Cockpit" in b1

            # Partial swap with and without hx-target
            st2, h2, b2 = await _invoke_http(
                app, "GET", "/", headers={"hx-request": "true", "hx-target": "#z2"}
            )
            assert st2 == 200 and h2["hx-reselect"] == "#z2" and b"zcg-z2-fragment" in b2
            st3, h3, _ = await _invoke_http(app, "GET", "/", headers={"hx-request": "true"})
            assert st3 == 200 and "hx-reselect" not in h3

            # Static & /data/* resolution + non-GET fallback 404 + containment + 404
            st_d1, _, bd1 = await _invoke_http(app, "GET", "/data/node_scope.json")
            st_d2, _, bd2 = await _invoke_http(app, "GET", "/data/fallback.json")
            st_bin, h_bin, _ = await _invoke_http(app, "GET", "/blob.unknownext")
            st_404, _, _ = await _invoke_http(app, "GET", "/missing.html")
            st_p404, _, _ = await _invoke_http(app, "POST", "/missing.html")
            st_403, _, b_403 = await _invoke_http(app, "GET", "/..%2fsecret.txt")
            assert st_d1 == 200 and b"persona-work" in bd1
            assert st_d2 == 200 and b"fallback" in bd2
            assert st_bin == 200 and h_bin["content-type"] == "application/octet-stream"
            assert st_404 == 404 and st_p404 == 404
            assert st_403 == 403 and b"PATH_CONTAINMENT_VIOLATION" in b_403
            return st0

        # Act
        status_code = asyncio.run(_run())
        cli_rc = run_cockpit_daemon_cli(["--workspace", str(ws), "--self-test"])

        # Assert
        assert status_code == 200
        assert cli_rc == 0

    def test_manifest_surface_access_ring_enforcement_on_cockpit_asgi_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify manifest surface_access rings, live / upgrade, and stale scope module union."""
        # Arrange
        ws, ws_exp, ws_pend = tmp_path / "corp-ring", tmp_path / "exp-mods", tmp_path / "pend-node"
        for sub in (ws / "system", ws / "surfaces/web", ws / "surfaces/data", ws_exp / "system", ws_exp / "surfaces/web", ws_pend / "system"):  # fmt: skip  # noqa: E501
            sub.mkdir(parents=True)
        corp_m = {"layer_id": "corp-ring", "layer_role": "corporate", "surface_access": {"default_ring": "R2", "loopback_operator_bypass": False}}  # fmt: skip  # noqa: E501
        (ws / "system/zcg-node.json").write_text(json.dumps(corp_m), "utf-8")
        (ws / "surfaces/web/index.html").write_text("<script>const D = {};</script>", "utf-8")
        (ws / "surfaces/data/node_scope.json").write_text(
            json.dumps({"representation_context": {"enabled_modules": ["crud"]}}), "utf-8"
        )
        exp_m = {"layer_id": "exp-mods", "enabled_modules": ["crud", "vault"]}
        (ws_exp / "system/zcg-node.json").write_text(json.dumps(exp_m), "utf-8")
        (ws_exp / "surfaces/web/index.html").write_text("<script>const D = {};</script>", "utf-8")
        pend_m = {"layer_id": "pend-node", "layer_role": "workstation"}
        (ws_pend / "system/zcg-node.json").write_text(json.dumps(pend_m), "utf-8")
        wt = "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n"
        (ws_pend / "WORKTASK.md").write_text(wt, "utf-8")
        app, app_exp, app_pend = (create_node_cockpit_asgi_app(w) for w in (ws, ws_exp, ws_pend))

        # Act
        st_hz, h_hz, b_hz = asyncio.run(_invoke_http(app, "GET", "/healthz"))
        st_port, h_port, b_port = asyncio.run(_invoke_http(app, "GET", "/portal"))
        st_sess, h_sess, _ = asyncio.run(_invoke_http(app, "GET", "/auth/session"))
        st_dash, h_dash, _ = asyncio.run(_invoke_http(app, "GET", "/dashboard"))
        st_leg, _, b_leg = asyncio.run(_invoke_http(app_exp, "GET", "/"))
        (ws_exp / "surfaces/web/index.html").unlink()
        st_live, _, b_live = asyncio.run(_invoke_http(app_exp, "GET", "/"))
        st_pend, _, b_pend = asyncio.run(_invoke_http(app_pend, "GET", "/"))
        st_atlas, h_atlas, b_atlas = asyncio.run(_invoke_http(app_exp, "GET", "/atlas"))
        st_a_q, _, b_a_q = asyncio.run(_invoke_http(app_pend, "GET", "/", query="view=atlas"))
        st_set, _, b_set = asyncio.run(_invoke_http(app_exp, "GET", "/admin"))
        st_rt, _, b_rt = asyncio.run(_invoke_http(app_exp, "GET", "/api/modules/runtime"))
        _, _, b_exp_hz = asyncio.run(_invoke_http(app_exp, "GET", "/healthz"))

        # Assert
        hz_doc = json.loads(b_hz)
        hz_mods = hz_doc["enabled_modules"]
        assert st_hz == 200 and h_hz["x-zcg-surface-ring"] == "R0"
        assert hz_doc["engine_asset_digest"] == CURRENT_ENGINE_ASSET_DIGEST
        assert "spatial_atlas" in hz_mods and "work_ledger" in hz_mods and "crud" not in hz_mods
        assert "tool_stack" not in hz_mods and "telemetry" not in hz_mods
        assert st_port == 200 and h_port["x-zcg-surface-ring"] == "R0"
        assert b"corporate-brand-portal" in b_port and b"ring.localhost" in b_port
        assert st_sess == 200 and h_sess["x-zcg-surface-ring"] == "R0"
        assert st_dash == 401 and h_dash["x-zcg-surface-ring"] == "R2"
        assert st_leg == 200 and b'data-zcg-plane="workspace"' in b_leg
        assert b"zcg-plane-switch" not in b_leg and b'href="/admin"' in b_leg
        assert st_live == 200 and b'data-zcg-plane="workspace"' in b_live
        assert st_pend == 200 and b"data-island='draft-studio'" in b_pend
        assert st_atlas == 200 and h_atlas[CHANNEL_HEADER] == DeliveryChannel.IMMERSIVE_SYNC.value
        assert b"id='zcg-atlas-stage'" in b_atlas and b"zcg-atlas-icon-btn is-active'" in b_atlas
        assert st_a_q == 200 and b"id='zcg-atlas-stage'" in b_a_q and b"draft-studio" not in b_a_q
        assert st_set == 200 and b'data-island="cockpit-passport"' in b_set
        assert b'data-admin-tab="runtime"' in b_set and b'data-admin-tab="skills"' in b_set
        assert st_rt == 200 and json.loads(b_rt)["update_plan"]["layer_id"] == "exp-mods"
        assert json.loads(b_exp_hz)["enabled_modules"] == ["crud", "vault"]

    def test_poll_286_ack_csrf_payload_cap_docs_modes_and_sse_shutdown_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify HTTP 286 poll, CSRF/413 guards, DocsAccessMode, and SSE hold + shutdown."""
        # Arrange
        ws = tmp_path / "node-sse"
        ws.mkdir()
        tok = "tok-iso-99"
        app = create_node_cockpit_asgi_app(
            ws,
            csrf_token=tok,
            max_payload_bytes=16,
            docs_access_mode=DocsAccessMode.AUTHENTICATED,
            docs_bearer_token=tok,
            sse_heartbeat_sec=0.01,
        )
        app_dis = create_node_cockpit_asgi_app(ws, docs_access_mode=DocsAccessMode.DISABLED)
        app_v = create_node_cockpit_asgi_app(ws, csrf_token=tok)

        async def _run() -> int:
            # Healthz & HTTP 286 polling (auto, deferred job 200->286, done=1/0 partial)
            st_hz, _, b_hz = await _invoke_http(app, "GET", "/healthz")
            hz_doc = json.loads(b_hz)
            assert st_hz == 200 and hz_doc["delivery_channels_count"] == 16
            assert hz_doc["telemetry_grade"] == "G1" and hz_doc["jitter_status"] == "STABLE"
            st_p_auto, _, _ = await _invoke_http(app, "GET", "/api/poll/status")
            st_vj_reg, h_vj, _ = await _invoke_http(
                app_v,
                "POST",
                "/api/modules/work-ledger/jobs",
                chunks=[b'{"task_id":"j1"}'],
            )
            st_p_busy, _, _ = await _invoke_http(app_v, "GET", "/api/poll/status")
            await _invoke_http(
                app_v,
                "POST",
                "/api/modules/work-ledger/jobs/j1/progress",
                headers={CSRF_HEADER: tok, "hx-request": "true"},
                chunks=[b'{"progress":1.0}'],
            )
            st_p_done_after, _, _ = await _invoke_http(app_v, "GET", "/api/poll/status")
            assert st_vj_reg == 201 and h_vj[CHANNEL_HEADER] == DeliveryChannel.ISLAND_SYNC.value
            assert st_p_busy == 200 and st_p_done_after == 286
            st_p_done, _, b_done = await _invoke_http(
                app, "GET", "/api/poll/status", query="done=1", headers={"hx-request": "true"}
            )
            st_p_wait, _, b_wait = await _invoke_http(
                app, "GET", "/api/poll/status", query="done=0", headers={"hx-request": "true"}
            )
            assert st_p_auto == 286 and st_p_done == 286 and b"Completed" in b_done
            assert st_p_wait == 200 and b"In Progress" in b_wait

            # CSRF 403 (partial HTML), 413 Content-Length & streaming chunks, and valid ACK
            st_csrf, _, b_csrf = await _invoke_http(
                app, "POST", "/fragments/ack", headers={"hx-request": "true"}, chunks=[b"{}"]
            )
            st_cl, _, _ = await _invoke_http(
                app, "POST", "/fragments/ack", headers={"content-length": "99"}, chunks=[b"x"]
            )
            st_ch, _, _ = await _invoke_http(
                app, "POST", "/fragments/ack", chunks=[b"0123456789", b"0123456789"]
            )
            st_ack_j, h_ack, b_ack = await _invoke_http(
                app, "POST", "/fragments/ack", headers={CSRF_HEADER: tok}, chunks=[b'{"a":1}']
            )
            st_ack_h, _, b_ack_h = await _invoke_http(
                app,
                "POST",
                "/fragments/ack",
                headers={CSRF_HEADER: tok, "hx-request": "true"},
                chunks=[b"note=ok"],
            )
            assert st_csrf == 403 and b"CSRF_VALIDATION_FAILED" in b_csrf
            assert st_cl == 413 and st_ch == 413
            assert st_ack_j == 200 and h_ack["hx-trigger"] == "cockpitAck"
            assert json.loads(b_ack)["payload"] == {"a": 1}
            assert st_ack_h == 200 and b"zcg-ack" in b_ack_h

            # DocsAccessMode: disabled (404), authenticated missing (401) & valid (/docs & /openapi)
            st_dd, _, _ = await _invoke_http(app_dis, "GET", "/docs")
            st_401, h_401, _ = await _invoke_http(app, "GET", "/docs")
            st_oa, _, b_oa = await _invoke_http(
                app, "GET", "/openapi.json", headers={"authorization": f"Bearer {tok}"}
            )
            st_dc, _, b_dc = await _invoke_http(
                app, "GET", "/docs", headers={"authorization": f"Bearer {tok}"}
            )
            assert st_dd == 404 and st_401 == 401 and "Bearer" in h_401["www-authenticate"]
            assert st_oa == 200 and json.loads(b_oa)["openapi"] == "3.1.0"
            assert st_dc == 200 and b"/events" in b_dc

            # SSE normal snapshot + held stream terminated via lifespan.shutdown
            st_sse, _, b_sse = await _invoke_http(app, "GET", "/events")
            assert st_sse == 200 and b"event: cockpit.snapshot" in b_sse

            life_q: asyncio.Queue[Message] = asyncio.Queue()
            life_out: list[Message] = []
            await life_q.put({"type": "lifespan.startup"})
            await life_q.put({"type": "lifespan.noop"})

            async def _life_send(msg: Message) -> None:
                life_out.append(msg)

            async def _shutdown_soon() -> None:
                await asyncio.sleep(0.025)
                await life_q.put({"type": "lifespan.shutdown"})

            life_task = asyncio.create_task(app({"type": "lifespan"}, life_q.get, _life_send))
            shut_task = asyncio.create_task(_shutdown_soon())
            _, _, b_held = await _invoke_http(app, "GET", "/events", query="hold=1")
            await asyncio.gather(life_task, shut_task)
            assert b": heartbeat" in b_held
            assert [m["type"] for m in life_out] == [
                "lifespan.startup.complete",
                "lifespan.shutdown.complete",
            ]
            return len(life_out)

        # Act
        life_count = asyncio.run(_run())

        # Assert
        assert life_count == 2

    def test_plugin_dashboard_cascading_templates_static_overrides_and_fallbacks_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify /dashboard, /dashboard/overview, cascading web overrides, and empty fallback."""
        # Arrange
        ws_know = tmp_path / "sci-iso"
        (ws_know / ".agents/runtime").mkdir(parents=True)
        (ws_know / ".agents/runtime/knowledge-stewardship-portal.json").write_text(
            json.dumps({"plugin_id": "knowledge-stewardship-portal"}), encoding="utf-8"
        )
        (ws_know / "surfaces/data").mkdir(parents=True)
        know_scope = {
            "layer_id": "sci-iso",
            "representation_context": {
                "view_archetype": "knowledge-stewardship-portal",
                "dual_world_contract": {
                    "common_base_plugin": "knowledge-stewardship-portal",
                    "use_case_overlay": "knowledge-stewardship-portal",
                },
            },
        }
        (ws_know / "surfaces/data/node_scope.json").write_text(json.dumps(know_scope), "utf-8")
        app_plugin = create_node_cockpit_asgi_app(ws_know)

        # Local Two-World override in <ws>/surfaces/web/{templates,static}
        ws_over = tmp_path / "corp-over"
        (ws_over / ".agents/runtime").mkdir(parents=True)
        (ws_over / ".agents/runtime/corporate-root-hub.json").write_text(
            json.dumps({"plugin_id": "corporate-root-hub"}), encoding="utf-8"
        )
        (ws_over / "surfaces/web/templates/partials").mkdir(parents=True)
        (ws_over / "surfaces/web/static/css").mkdir(parents=True)
        (ws_over / "surfaces/web/templates/partials/overview.html").write_text(
            "<div id='custom-local-overview'>Custom Sovereign Override</div>", encoding="utf-8"
        )
        (ws_over / "surfaces/web/static/css/plugin.css").write_text(
            ":root { --zcg-accent: #10b981; }\n", encoding="utf-8"
        )
        (ws_over / "surfaces/web/leak.py").write_text("SECRET = 1\n", encoding="utf-8")
        scaffold_plugin_module(ws_over, plugin_id="local", module_name="ops-note")
        app_over = create_node_cockpit_asgi_app(ws_over)

        # Custom installed plugin pack with status=active, base fallback & custom router
        ws_cust = tmp_path / "org-cust"
        (ws_cust / ".agents/runtime").mkdir(parents=True)
        (ws_cust / ".agents/runtime/a-inactive.json").write_text(
            json.dumps({"plugin_id": "corporate-root-hub", "status": "installed"}), "utf-8"
        )
        (ws_cust / ".agents/runtime/alpha-portal.json").write_text(
            json.dumps({"plugin_id": "alpha-portal", "status": "active", "environment": "pro"}),
            "utf-8",
        )
        cust_pack = ws_cust / "templates/plugin-stack/alpha-portal"
        (cust_pack / "web/templates/partials").mkdir(parents=True)
        (cust_pack / "routers").mkdir(parents=True)
        (cust_pack / "template.json").write_text(
            json.dumps({"id": "alpha-portal", "kind": "plugin-stack"}), "utf-8"
        )
        (cust_pack / "web/templates/partials/overview.html").write_text(
            "<div>Alpha Custom Portal ({{ active_env }})</div>", "utf-8"
        )
        (cust_pack / "routers/ping.py").write_text(
            "from zcg.web.http.channels import DeliveryChannel\n"
            "from zcg.web.http.request import respond\n"
            "from zcg.web.http.router import APIRouter\n"
            "def build_router(ws, state):  # noqa: ANN001, ANN201, ARG001\n"
            "    r = APIRouter(prefix='/api/plugins/ping')\n"
            "    @r.get('', channel=DeliveryChannel.ISLAND_SYNC)\n"
            "    def get_ping(req):  # noqa: ANN001, ANN202\n"
            "        return respond(req, html_fragment='<span>ok</span>', data={'ok': True})\n"
            "    return r\n",
            "utf-8",
        )
        app_cust = create_node_cockpit_asgi_app(ws_cust)

        # Minimal empty engine_dir fallback + quarantined broken overlay router
        empty_eng, ws_min = tmp_path / "empty-engine", tmp_path / "min-node"
        empty_eng.mkdir()
        (ws_min / "surfaces/web/routers").mkdir(parents=True)
        (ws_min / "surfaces/web/routers/bad.py").write_text("def broken(:\n", "utf-8")
        app_min = create_node_cockpit_asgi_app(ws_min, engine_dir=empty_eng)

        async def _exercise() -> dict[str, tuple[int, dict[str, str], bytes]]:
            return {
                "full": await _invoke_http(app_plugin, "GET", "/dashboard"),
                "swap": await _invoke_http(
                    app_plugin, "GET", "/dashboard", headers={"hx-request": "true"}
                ),
                "ov": await _invoke_http(app_plugin, "GET", "/dashboard/overview"),
                "bkl_ssr": await _invoke_http(
                    app_plugin, "GET", "/dashboard", query="view=backlog&ws_scope=network"
                ),
                "met_ssr": await _invoke_http(
                    app_plugin, "GET", "/dashboard", query="view=metrics&metrics_scope=node"
                ),
                "css": await _invoke_http(app_plugin, "GET", "/static/css/plugin.css"),
                "js": await _invoke_http(app_plugin, "GET", "/static/js/islands/plugin-island.js"),
                "over_ov": await _invoke_http(app_over, "GET", "/dashboard/overview"),
                "over_css": await _invoke_http(app_over, "GET", "/static/css/plugin.css"),
                "over_api": await _invoke_http(
                    app_over, "GET", "/api/plugins/ops-note", headers={"hx-request": "true"}
                ),
                "blk_dir": await _invoke_http(app_over, "GET", "/routers/ops_note.py"),
                "blk_ext": await _invoke_http(app_over, "GET", "/leak.py"),
                "cust_ov": await _invoke_http(app_cust, "GET", "/dashboard/overview"),
                "cust_api": await _invoke_http(app_cust, "GET", "/api/plugins/ping"),
                "min_full": await _invoke_http(app_min, "GET", "/dashboard"),
                "min_ov": await _invoke_http(app_min, "GET", "/dashboard/overview"),
                "min_hz": await _invoke_http(app_min, "GET", "/healthz"),
            }

        # Act
        pid_over, tdirs_over, sdirs_over = resolve_cockpit_web_dirs(ws_over)
        pid_cust, tdirs_cust, _ = resolve_cockpit_web_dirs(ws_cust)
        pid_min, tdirs_min, sdirs_min = resolve_cockpit_web_dirs(ws_min, engine_dir=empty_eng)
        out = asyncio.run(_exercise())

        # Assert
        assert pid_over == "corporate-root-hub" and len(tdirs_over) == len(sdirs_over) == 2
        assert pid_cust == "alpha-portal" and len(tdirs_cust) == 2
        assert pid_min == "node-work-cockpit" and tdirs_min == () and sdirs_min == ()
        assert out["full"][0] == 200 and b"zcg-capability-stage" in out["full"][2]
        assert b"knowledge-stewardship-portal" in out["full"][2]
        assert out["swap"][0] == 200 and out["swap"][1][CHANNEL_HEADER] == (
            DeliveryChannel.SWAP_SYNC.value
        )
        assert b"<!doctype html>" not in out["swap"][2]
        assert out["ov"][0] == 200 and b"zcg-kanban" in out["ov"][2]
        assert out["bkl_ssr"][0] == 200 and b"data-work-section='backlog'" in out["bkl_ssr"][2]
        assert b"data-zcg-ws-scope='network'" in out["bkl_ssr"][2]
        assert out["met_ssr"][0] == 200 and b"data-zcg-metrics-view" in out["met_ssr"][2]
        assert out["css"][0] == 200 and b"#2dd4bf" in out["css"][2]
        assert out["js"][0] == 200 and b"ZCGIslands" in out["js"][2]
        assert out["over_ov"][0] == 200 and b"Custom Sovereign Override" in out["over_ov"][2]
        assert out["over_css"][0] == 200 and b"#10b981" in out["over_css"][2]
        assert out["over_api"][0] == 200 and b"0 records" in out["over_api"][2]
        assert out["blk_dir"][0] == 404 and out["blk_ext"][0] == 404
        assert out["cust_ov"][0] == 200 and b"Alpha Custom Portal (pro)" in out["cust_ov"][2]
        assert out["cust_api"][0] == 200 and json.loads(out["cust_api"][2])["ok"] is True
        assert out["min_full"][0] == 200 and b"<!doctype html>" in out["min_full"][2]
        assert json.loads(out["min_hz"][2])["overlay_boot_status"] == "OVERLAY_BOOT_QUARANTINED"
        assert out["min_ov"][0] == 200 and b"Department &amp; Squad Operations" in out["min_ov"][2]
