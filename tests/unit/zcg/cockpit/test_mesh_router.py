"""Unit tests for zcg.cockpit.mesh_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from zcg.cockpit.mesh_router import create_node_mesh_router
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.factory import WebAppState, create_web_app

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
        status, body = asyncio.run(_call(app, "GET", "/api/modules/node-mesh"))
        swap_status, swap_body = asyncio.run(
            _call(app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")])
        )
        onb_status, onb_body = asyncio.run(_call(app, "GET", "/api/modules/node-mesh/onboarding"))

        # Assert
        parsed = json.loads(body)
        onb_parsed = json.loads(onb_body)
        assert status == 200 and parsed["layer_id"] == "node-standalone"
        assert parsed["children_count"] == 0 and parsed["linked_nodes"] == []
        assert swap_status == 200 and b"Standalone sovereign node." in swap_body
        assert onb_status == 200 and len(onb_parsed["constellation_pillars"]) == 4

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
                        "parent_home_node": None,
                        "downward_child_nodes": [{"node_id": "dept-eng"}],
                        "lateral_peers": [{"node_id": "dept-ops"}],
                        "linked_nodes": [
                            {"node_id": "org-public", "relation": "b2b-collaboration"}
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
        _, b_json = asyncio.run(_call(app, "GET", "/api/modules/node-mesh"))
        _, b_swap = asyncio.run(
            _call(app, "GET", "/api/modules/node-mesh", headers=[(b"hx-request", b"true")])
        )

        # Assert
        parsed = json.loads(b_json)
        assert parsed["layer_id"] == "root-hub"
        assert parsed["children_count"] == 1 and parsed["peers_count"] == 1
        assert parsed["mounted_layers_count"] == 1
        assert b"link:b2b-collaboration" in b_swap and b"dept-eng" in b_swap

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
        pc_dir = tmp_path / "alex-pc"
        (pc_dir / "system").mkdir(parents=True)
        (pc_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "alex-pc",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "precedence": 90,
                }
            ),
            encoding="utf-8",
        )
        tutor_dir = tmp_path / "alex-tutor"
        (tutor_dir / "system").mkdir(parents=True)
        (tutor_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "alex-tutor",
                    "layer_role": "department",
                    "entity_kind": "individual",
                    "precedence": 86,
                }
            ),
            encoding="utf-8",
        )
        wallet_dir = tmp_path / "alex-wallet"
        (wallet_dir / "system").mkdir(parents=True)
        (wallet_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "alex-wallet",
                    "layer_role": "squad",
                    "entity_kind": "individual",
                    "precedence": 88,
                }
            ),
            encoding="utf-8",
        )
        pc_states: list[WebAppState] = []
        pc_app = create_web_app(routers=(create_node_mesh_router(pc_dir),), state_out=pc_states)
        pc_csrf = pc_states[0].csrf_token.encode("ascii")

        wal_states: list[WebAppState] = []
        wal_app = create_web_app(
            routers=(create_node_mesh_router(wallet_dir),), state_out=wal_states
        )
        wal_csrf = wal_states[0].csrf_token.encode("ascii")

        # Act
        _, pc_onb_html = asyncio.run(
            _call(
                pc_app,
                "GET",
                "/api/modules/node-mesh/onboarding",
                headers=[(b"hx-request", b"true")],
            )
        )
        _, wal_onb_html = asyncio.run(
            _call(
                wal_app,
                "GET",
                "/api/modules/node-mesh/onboarding",
                headers=[(b"hx-request", b"true")],
            )
        )
        no_csrf_st, _ = asyncio.run(
            _call(pc_app, "POST", "/api/modules/node-mesh/link", body=b'{"target_id":"org-iso"}')
        )
        bad_json_st, _ = asyncio.run(
            _call(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b"[1, 2]",
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", pc_csrf),
                ],
            )
        )
        empty_st, _ = asyncio.run(
            _call(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b"",
                headers=[(b"x-zcg-csrf-token", pc_csrf)],
            )
        )
        bad_rel_st, _ = asyncio.run(
            _call(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b'{"target_id":"org-iso","relation":"bad-rel"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", pc_csrf),
                ],
            )
        )
        wal_block_st, wal_block_body = asyncio.run(
            _call(
                wal_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b'{"target_id":"org-iso"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", wal_csrf),
                ],
            )
        )
        form_st, form_body = asyncio.run(
            _call(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=f"from_source={tutor_dir}&relation=lateral-peer".encode(),
                headers=[
                    (b"content-type", b"application/x-www-form-urlencoded"),
                    (b"x-zcg-csrf-token", pc_csrf),
                ],
            )
        )
        json_st, json_body = asyncio.run(
            _call(
                pc_app,
                "POST",
                "/api/modules/node-mesh/link",
                body=b'{"target_id":"org-iso","relation":"b2b-collaboration"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", pc_csrf),
                ],
            )
        )

        # Assert
        assert b"Connect Sovereign Node" in pc_onb_html
        assert b"R3 Airlock Active" in wal_onb_html
        assert no_csrf_st == 403
        assert bad_json_st == 400
        assert empty_st == 400
        assert bad_rel_st == 400
        assert wal_block_st == 403 and b"WALLET_EXTERNAL_LINK_BLOCKED" in wal_block_body
        assert form_st == 201 and json.loads(form_body)["linked_node"]["node_id"] == "alex-tutor"
        assert str(tmp_path).encode("utf-8") not in form_body
        assert json_st == 201 and json.loads(json_body)["total_linked_nodes"] == 2
