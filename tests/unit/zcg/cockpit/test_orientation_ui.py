"""Unit tests for zcg.cockpit.orientation_ui.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from zcg.cockpit.orientation_ui import (
    build_node_dashboard_enrichment,
    create_node_context_router,
    create_surface_attestation_router,
)
from zcg.web.factory import create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
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
        "query_string": query.encode("latin1"),
        "headers": headers or [],
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestOrientationUi:
    """Verify SafeHTML orientation compass, cross-node switcher, spotlights, and spinout router."""

    def test_build_node_dashboard_enrichment_across_all_archetypes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify SafeHTML blocks for workstation, tutor (empty/rich), work, and corporate nodes."""
        # Arrange
        ws_empty = tmp_path / "tutor-empty"
        ws_empty.mkdir()
        ws_rich = tmp_path / "node-rich"
        (ws_rich / "system").mkdir(parents=True)
        (ws_rich / "surfaces/data").mkdir(parents=True)
        (ws_rich / "docs").mkdir(parents=True)
        (ws_rich / "docs/lesson.md").write_text("# Lesson\n", encoding="utf-8")
        (ws_rich / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_role": "workstation",
                    "precedence": 90,
                    "linked_nodes": [
                        {
                            "node_id": "alex-work",
                            "relation": "knowledge-feed",
                            "layer_role": "department",
                            "cockpit_url": "http://127.0.0.1:8787",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (ws_rich / "surfaces/data/network_scope.json").write_text(
            json.dumps(
                {
                    "network_representation_links": {
                        "downward_child_nodes": [
                            {
                                "node_id": "alex-work",
                                "layer_role": "department",
                                "cockpit_url": "http://127.0.0.1:8787",
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        (ws_rich / "surfaces/data/federation_scope.json").write_text(
            json.dumps(
                {
                    "mounted_layers": [
                        {"layer_id": "sci-maths"},
                        {"layer_id": "local-pack", "active_endpoint": "layers/local-pack"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        fake_branches = {
            "active_branch": "master",
            "local_branches": ["master", "machine/laptop-linux"],
            "tracks": [
                {"branch": "master", "purpose": "Main", "status": "active"},
                {"branch": "machine/laptop-linux", "purpose": "Laptop", "status": "created"},
                {"branch": "hat/research", "purpose": "Research", "status": "blueprint"},
            ],
        }

        # Act
        with patch(
            "zcg.cockpit.orientation_ui.inspect_context_branches", return_value=fake_branches
        ):
            tower = build_node_dashboard_enrichment(
                ws_rich,
                layer_id="alex-pc",
                view_archetype="workstation-control-tower",
                active_env="dev",
            )
            tutor_rich = build_node_dashboard_enrichment(
                ws_rich,
                layer_id="alex-tutor",
                view_archetype="academic-tutor-cockpit",
                active_env="dev",
            )
        tutor_empty = build_node_dashboard_enrichment(
            ws_empty,
            layer_id="alex-tutor",
            view_archetype="academic-tutor-cockpit",
            active_env="dev",
        )
        work = build_node_dashboard_enrichment(
            ws_empty,
            layer_id="alex-work",
            view_archetype="personal-work-cockpit",
            active_env="dev",
        )
        corp = build_node_dashboard_enrichment(
            ws_empty,
            layer_id="corp-iso",
            view_archetype="corporate-root-hub",
            active_env="pro",
        )

        # Assert
        assert "Switch Node:" in str(tower["cross_node_nav_html"])
        assert "Host Machine, Quick Shortcuts" in str(tower["archetype_spotlight_html"])
        assert "✓ <code>machine/laptop-linux</code>" in str(tower["archetype_spotlight_html"])
        assert "sci-maths" in str(tutor_rich["archetype_spotlight_html"])
        assert "docs/lesson.md" in str(tutor_rich["archetype_spotlight_html"])
        assert "Standalone sovereign node" in str(tutor_empty["cross_node_nav_html"])
        assert "Mount corpora via" in str(tutor_empty["archetype_spotlight_html"])
        assert "spinout-preview" in str(work["archetype_spotlight_html"])
        assert "Parallel Governance Branches" in str(corp["archetype_spotlight_html"])

    def test_node_context_router_and_spinout_preview_across_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET /api/modules/node-context and /spinout-preview 200 and 422 guards."""
        # Arrange
        ws = tmp_path / "alex-work"
        ws.mkdir()
        app = create_web_app(
            routers=(
                create_node_context_router(ws, view_archetype="personal-work-cockpit"),
                create_surface_attestation_router(ws, plugin_id="node-work-cockpit"),
            )
        )
        fake_existing = {
            "active_branch": "master",
            "local_branches": ["master", "venture/ready-app"],
            "tracks": [],
        }

        # Act
        st_ctx, b_ctx = asyncio.run(_call(app, "GET", "/api/modules/node-context"))
        st_att, b_att = asyncio.run(_call(app, "GET", "/.well-known/zcg-attestation.json"))
        st_new, b_new = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/node-context/spinout-preview",
                query="branch=venture/alpha&project_id=alpha-app",
                headers=[(b"hx-request", b"true")],
            )
        )
        with patch(
            "zcg.cockpit.orientation_ui.inspect_context_branches", return_value=fake_existing
        ):
            st_rdy, b_rdy = asyncio.run(
                _call(
                    app,
                    "GET",
                    "/api/modules/node-context/spinout-preview",
                    query="branch=venture/ready-app&project_id=ready-app",
                )
            )
        st_bad_id, _ = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/node-context/spinout-preview",
                query="branch=venture/x&project_id=BAD_ID",
            )
        )
        st_bad_br, _ = asyncio.run(
            _call(
                app,
                "GET",
                "/api/modules/node-context/spinout-preview",
                query="branch=master&project_id=valid-id",
            )
        )

        # Assert
        assert st_ctx == 200 and json.loads(b_ctx)["branches"]["active_branch"] == "master"
        assert st_att == 200 and json.loads(b_att)["schema_version"] == "zcg-surface-seal-v1"
        assert st_new == 200 and b"Create + Extract" in b_new
        assert st_rdy == 200 and json.loads(b_rdy)["branch_exists"] is True
        assert st_bad_id == 422
        assert st_bad_br == 422
