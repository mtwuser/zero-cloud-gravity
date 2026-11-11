"""Unit tests for zcg.cockpit.mesh_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from zcg.cockpit.mesh_router import create_node_mesh_router
from zcg.web.factory import create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any, method: str, path: str, *, headers: list[tuple[bytes, bytes]] | None = None
) -> tuple[int, bytes]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
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
    """Verify 1:1 Sovereign Node 3-Scope & Linked Cloud Topology APIRouter."""

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

        # Assert
        parsed = json.loads(body)
        assert status == 200 and parsed["layer_id"] == "node-standalone"
        assert parsed["children_count"] == 0 and parsed["linked_nodes"] == []
        assert swap_status == 200 and b"Standalone sovereign node." in swap_body

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
