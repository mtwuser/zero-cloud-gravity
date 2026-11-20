"""Unit tests for zcg.cockpit.routing.mesh_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from zcg.cockpit.routing.mesh_router import create_node_mesh_router
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.http.factory import WebAppState, create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
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

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


def _req(
    app: Any,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, bytes]:
    return asyncio.run(_call(app, method, path, body=body, headers=headers))


def _write_manifest(ws: Path, doc: dict[str, Any]) -> Path:
    (ws / "system").mkdir(parents=True, exist_ok=True)
    (ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(doc), encoding="utf-8")
    return ws


def _mk_app(ws: Path) -> tuple[Any, bytes]:
    states: list[WebAppState] = []
    app = create_web_app(routers=(create_node_mesh_router(ws),), state_out=states)
    return app, states[0].csrf_token.encode("ascii")


class TestMeshRouter:
    """Verify 1:1 Sovereign Node 3-Scope, Constellation Setup & Link APIRouter."""

    def test_standalone_node_without_scope_files_returns_empty_mesh_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing surfaces/data/*.json falls back to workspace name and 0 counts."""
        # Arrange
        ws = tmp_path / "node-standalone"
        ws.mkdir()
        app = create_web_app(routers=(create_node_mesh_router(ws),))

        # Act
        status, body = _req(app, "GET", "/api/modules/node-mesh")
        swap_status, swap_body = _req(
            app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")]
        )
        onb_status, onb_body = _req(app, "GET", "/api/modules/node-mesh/onboarding")

        # Assert
        parsed = json.loads(body)
        onb_parsed = json.loads(onb_body)
        assert status == 200 and parsed["layer_id"] == "node-standalone"
        assert parsed["children_count"] == 0 and parsed["linked_nodes"] == []
        assert swap_status == 200 and b"Standalone sovereign node." in swap_body
        assert onb_status == 200 and len(onb_parsed["constellation_pillars"]) == 6

    def test_populated_three_scope_feeds_project_children_peers_links_and_mounts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify node, network, and federation scope feeds populate mesh JSON and HTML table."""
        # Arrange
        data_dir = tmp_path / "surfaces/data"
        data_dir.mkdir(parents=True)
        (data_dir / "node_scope.json").write_text(json.dumps({"layer_id": "root-hub"}), "utf-8")
        (data_dir / "network_scope.json").write_text(
            json.dumps(
                {
                    "network_representation_links": {
                        "parent_home_node": {"node_id": "corp-root", "layer_role": "corporate"},
                        "downward_child_nodes": [{"node_id": "dept-eng"}],
                        "lateral_peers": [{"node_id": "dept-ops"}, {"node_id": "dept-eng"}],
                        "linked_nodes": [
                            {"node_id": "org-public", "relation": "b2b-collaboration"},
                            {"node_id": "dept-eng", "relation": "lateral-peer"},
                            {"node_id": "sci-maths", "relation": "knowledge-feed"},
                            {"node_id": "gov-iso", "relation": "knowledge-feed"},
                        ],
                    }
                }
            ),
            "utf-8",
        )
        (data_dir / "federation_scope.json").write_text(
            json.dumps({"mounted_layers": [{"layer_id": "gov-iso"}]}), "utf-8"
        )
        app = create_web_app(routers=(create_node_mesh_router(tmp_path),))

        # Act
        _, b_json = _req(app, "GET", "/api/modules/node-mesh")
        _, b_swap = _req(app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")])

        # Assert
        parsed = json.loads(b_json)
        assert parsed["layer_id"] == "root-hub"
        assert parsed["children_count"] == 1 and parsed["peers_count"] == 2
        assert parsed["mounted_layers_count"] == 1
        assert b"link:b2b-collaboration" in b_swap and b"dept-eng" in b_swap
        assert b"Clean Up Duplicate" in b_swap and b"sci-maths" in b_swap
        assert b"zcg-cli-hint" in b_swap and b"make consult" in b_swap

    def test_non_dict_json_scope_files_degrade_safely_expected(self, tmp_path: Path) -> None:
        """Verify non-object JSON in surfaces/data/*.json degrades safely without crashing."""
        # Arrange
        data_dir = tmp_path / "surfaces/data"
        data_dir.mkdir(parents=True)
        (data_dir / "node_scope.json").write_text("[1, 2]", "utf-8")
        (data_dir / "network_scope.json").write_text(
            json.dumps({"network_representation_links": "invalid"}), "utf-8"
        )
        app = create_web_app(routers=(create_node_mesh_router(tmp_path),))

        # Act
        status, body = asyncio.run(_call(app, "GET", "/api/modules/node-mesh"))

        # Assert
        assert status == 200
        assert json.loads(body)["children_count"] == 0

    def test_onboarding_and_csrf_guarded_link_post_with_wallet_airlock_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 4-pillar onboarding, CSRF guard, form/JSON linking, and R3 wallet airlock."""
        # Arrange
        pc_dir = _write_manifest(
            tmp_path / "persona-profile",
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "precedence": 90,
            },
        )
        tutor_dir = _write_manifest(
            tmp_path / "persona-tutor",
            {
                "layer_id": "persona-tutor",
                "layer_role": "department",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
                "precedence": 86,
            },
        )
        wallet_dir = _write_manifest(
            tmp_path / "persona-wallet",
            {
                "layer_id": "persona-wallet",
                "layer_role": "squad",
                "entity_kind": "individual",
                "precedence": 88,
            },
        )
        pc_app, pc_csrf = _mk_app(pc_dir)
        wal_app, wal_csrf = _mk_app(wallet_dir)

        # Act
        _, pc_onb_html = _req(
            pc_app, "GET", "/api/modules/node-mesh/onboarding", headers=[(b"hx-request", b"true")]
        )
        _, wal_onb_html = _req(
            wal_app, "GET", "/api/modules/node-mesh/onboarding", headers=[(b"hx-request", b"true")]
        )
        js_pc = [(b"content-type", b"application/json"), (b"x-zcg-csrf-token", pc_csrf)]
        fm_pc = [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"x-zcg-csrf-token", pc_csrf),
        ]
        js_wal = [(b"content-type", b"application/json"), (b"x-zcg-csrf-token", wal_csrf)]
        no_csrf_st, _ = _req(
            pc_app, "POST", "/api/modules/node-mesh/link", body=b'{"target_id":"org-iso"}'
        )
        bad_json_st, _ = _req(
            pc_app, "POST", "/api/modules/node-mesh/link", body=b"[1, 2]", headers=js_pc
        )
        empty_st, _ = _req(
            pc_app,
            "POST",
            "/api/modules/node-mesh/link",
            body=b"",
            headers=[(b"x-zcg-csrf-token", pc_csrf)],
        )
        bad_rel_st, _ = _req(
            pc_app,
            "POST",
            "/api/modules/node-mesh/link",
            body=b'{"target_id":"org-iso","relation":"bad-rel"}',
            headers=js_pc,
        )
        wal_block_st, wal_block_body = _req(
            wal_app,
            "POST",
            "/api/modules/node-mesh/link",
            body=b'{"target_id":"org-iso"}',
            headers=js_wal,
        )
        form_st, form_body = _req(
            pc_app,
            "POST",
            "/api/modules/node-mesh/link",
            body=f"from_source={tutor_dir}&relation=lateral-peer".encode(),
            headers=fm_pc,
        )
        (pc_dir / "surfaces/data").mkdir(parents=True, exist_ok=True)
        (pc_dir / "surfaces/data/node_scope.json").write_text("{}", encoding="utf-8")
        with patch("zcg.cockpit.ops.lifecycle.manage_plugin_service") as prov_mock:
            json_st, json_body = _req(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b'{"target_id":"org-iso","relation":"b2b-collaboration"}',
                headers=js_pc,
            )
        prov_mock.assert_called_once()

        # Assert
        assert b"Connect Sovereign Node" in pc_onb_html
        assert b"R3 Airlock Active" in wal_onb_html
        assert no_csrf_st == 403 and bad_json_st == 400 and empty_st == 400 and bad_rel_st == 400
        assert wal_block_st == 403 and b"WALLET_EXTERNAL_LINK_BLOCKED" in wal_block_body
        assert form_st == 201 and json.loads(form_body)["linked_node"]["node_id"] == "persona-tutor"
        assert str(tmp_path).encode("utf-8") not in form_body
        assert json_st == 201 and json.loads(json_body)["total_linked_nodes"] == 2

        # Verify child registry inheritance + POST /unlink success & validation error
        tutor_app = create_web_app(routers=(create_node_mesh_router(tutor_dir),))
        _, tutor_mesh_html = _req(
            tutor_app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")]
        )
        assert b"Available Knowledge Registry" in tutor_mesh_html and b"gov-es" in tutor_mesh_html

        bad_unl_st, _ = _req(
            pc_app,
            "POST",
            "/api/modules/node-mesh/unlink",
            body=b'{"target_id":"bad id!"}',
            headers=js_pc,
        )
        with patch("zcg.cockpit.ops.lifecycle.manage_plugin_service") as unl_prov:
            unl_st, unl_body = _req(
                pc_app,
                "POST",
                "/api/modules/node-mesh/unlink",
                body=b"target_id=org-iso",
                headers=fm_pc,
            )
        unl_prov.assert_called_once()
        (pc_dir / "surfaces/data/node_scope.json").unlink()
        unl_no_sc_st, _ = _req(
            pc_app,
            "POST",
            "/api/modules/node-mesh/unlink",
            body=b"target_id=persona-tutor",
            headers=fm_pc,
        )
        assert bad_unl_st == 400 and unl_st == 200 and json.loads(unl_body)["removed"] is True
        assert unl_no_sc_st == 200

    def test_mesh_policy_endpoint_updates_topology_channels_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /policy topology switch, add/remove channel, wallet 403, and 400 guards."""
        # Arrange
        ws = _write_manifest(
            tmp_path / "corp-iso",
            {
                "layer_id": "corp-iso",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "precedence": 30,
            },
        )
        app, csrf = _mk_app(ws)
        pol = "/api/modules/node-mesh/policy"
        js_h = [(b"content-type", b"application/json"), (b"x-zcg-csrf-token", csrf)]
        fm_h = [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"x-zcg-csrf-token", csrf),
        ]

        # Act
        st_mode, b_mode = _req(
            app, "POST", pol, body=b'{"topology_mode":"hierarchical-only"}', headers=js_h
        )
        add_form_b = (
            b"action_kind=add_channel&source=dept-eng&target=dept-ops"
            b"&verbs=consult_context,propose_work&reciprocal=1"
        )
        st_add_f, b_add_f = _req(app, "POST", pol, body=add_form_b, headers=fm_h)
        (ws / "surfaces/data").mkdir(parents=True, exist_ok=True)
        (ws / "surfaces/data/node_scope.json").write_text("{}", encoding="utf-8")
        add_j = json.dumps(
            {
                "action_kind": "add_channel",
                "source": "dept-eng",
                "target": "dept-qa",
                "verbs": ["consult_context"],
                "reciprocal": False,
            }
        ).encode()
        with patch("zcg.cockpit.ops.lifecycle.manage_plugin_service") as prov_m:
            st_add_j, b_add_j = _req(app, "POST", pol, body=add_j, headers=js_h)
        prov_m.assert_called_once()
        (ws / "surfaces/data/node_scope.json").unlink()
        st_rm, b_rm = _req(
            app,
            "POST",
            pol,
            body=b'{"action_kind":"remove_channel","source":"dept-eng","target":"dept-ops"}',
            headers=js_h,
        )
        st_wal, b_wal = _req(
            app,
            "POST",
            pol,
            body=b'{"action_kind":"add_channel","source":"dept-eng","target":"persona-wallet"}',
            headers=js_h,
        )
        st_bad, _ = _req(app, "POST", pol, body=b'{"topology_mode":"invalid-mode"}', headers=js_h)

        # Assert
        assert st_mode == 200 and json.loads(b_mode)["topology_mode"] == "hierarchical-only"
        assert st_add_f == 200 and json.loads(b_add_f)["channel_count"] == 1
        assert st_add_j == 200 and json.loads(b_add_j)["channel_count"] == 2
        assert st_rm == 200 and json.loads(b_rm)["channel_count"] == 1
        assert st_wal == 403 and b"WALLET_LATERAL_CHANNEL_BLOCKED" in b_wal
        assert st_bad == 400

    def test_activate_endpoint_wakes_local_node_and_maps_error_codes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /activate success swap/JSON, CSRF 403, missing 404, and failure 400."""
        # Arrange
        ws = tmp_path / "corp-iso"
        child_dir = _write_manifest(ws / "layers/dept-child", {"layer_id": "dept-child"})
        (ws / "surfaces/data").mkdir(parents=True)
        net = {
            "network_representation_links": {
                "downward_child_nodes": [{"node_id": "dept-child", "layer_role": "department"}]
            }
        }
        (ws / "surfaces/data/network_scope.json").write_text(json.dumps(net), encoding="utf-8")
        app, csrf = _mk_app(ws)
        act = "/api/modules/node-mesh/activate"
        js_h = [(b"content-type", b"application/json"), (b"x-zcg-csrf-token", csrf)]
        hx_h = [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"x-zcg-csrf-token", csrf),
            (b"hx-request", b"true"),
        ]

        # Act
        _, mesh_html = _req(
            app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")]
        )
        st_csrf, _ = _req(app, "POST", act, body=b'{"target_id":"dept-child"}')
        st_nf, b_nf = _req(app, "POST", act, body=b'{"target_id":"dept-missing"}', headers=js_h)
        with patch(
            "zcg.cockpit.ops.mesh_studio.activate_local_mesh_node",
            side_effect=ValueError("PLUGIN_ENV_GATE_BLOCKED (pro): missing approval"),
        ):
            st_fail, b_fail = _req(
                app, "POST", act, body=b'{"target_id":"dept-child"}', headers=js_h
            )
        act_payload = {
            "activated_node_id": "dept-child",
            "workspace_dir": str(child_dir.resolve()),
            "cockpit_url": "http://dept-child.localhost:8752/",
            "environment": "dev",
        }
        with patch(
            "zcg.cockpit.ops.mesh_studio.activate_local_mesh_node", return_value=act_payload
        ):
            st_ok, b_ok = _req(app, "POST", act, body=b'{"target_id":"dept-child"}', headers=js_h)
            st_hx, b_hx = _req(app, "POST", act, body=b"target_id=dept-child", headers=hx_h)

        # Assert
        assert b"Start Workspace" in mesh_html and b"Copy Start CLI" in mesh_html
        assert st_csrf == 403
        assert st_nf == 404 and b"TARGET_WORKSPACE_NOT_FOUND" in b_nf
        assert st_fail == 400 and b"NODE_ACTIVATION_FAILED" in b_fail
        assert st_ok == 200 and json.loads(b_ok)["capability"] == "node_mesh_activate"
        assert json.loads(b_ok)["activated_node_id"] == "dept-child"
        assert st_hx == 200 and b"Activated <code>dept-child</code>" in b_hx
        assert b"http://dept-child.localhost:8752/" in b_hx and b"Open Workspace" in b_hx
