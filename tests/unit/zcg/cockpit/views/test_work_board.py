"""Unit tests for zcg.cockpit.views.work_board.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from zcg.cockpit.views import work_board
from zcg.governance.work.work_inbox import enqueue_work_inbox_request, triage_work_inbox_request

if TYPE_CHECKING:
    from pathlib import Path


class TestWorkBoard:
    """Verify outbound receipts, Work Inbox 1-Hop grouping, and 3-column Kanban + filter HTML."""

    def test_outbound_receipts_and_counterpart_channel_grouping_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify receipt JSONL persistence, Work Inbox pending grouping, and active sorting."""
        # Arrange
        solo_ws = tmp_path / "solo"
        solo_ws.mkdir()
        rich_ws = tmp_path / "persona-work"
        (rich_ws / "system").mkdir(parents=True)
        (rich_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "persona-work", "precedence": 87}), encoding="utf-8"
        )
        enqueue_work_inbox_request(
            rich_ws, sender_node="persona-profile", summary="Align roadmap", direction="parent"
        )
        dec_req = enqueue_work_inbox_request(
            rich_ws, sender_node="persona-tutor", summary="Already closed"
        )
        triage_work_inbox_request(rich_ws, request_id=dec_req["request_id"], decision="decline")
        net_scope = {
            "network_representation_links": {
                "parent_home_node": {"node_id": "persona-profile", "layer_role": "workstation"},
                "downward_child_nodes": [
                    {"node_id": "venture-mvp", "layer_role": "project"},
                    {"node_id": "venture-mvp", "layer_role": "project"},
                    {"node_id": "", "layer_role": "project"},
                ],
                "lateral_peers": [{"node_id": "persona-wallet", "layer_role": "department"}],
                "linked_nodes": [
                    {
                        "node_id": "gov-iso",
                        "layer_role": "knowledge",
                        "relation": "knowledge-feed",
                    },
                    {
                        "node_id": "partner-b2b",
                        "layer_role": "corporate",
                        "relation": "service-contract",
                    },
                ],
            }
        }

        # Act
        empty_rec = work_board.read_outbound_exchange_receipts(solo_ws)
        saved = work_board.record_outbound_exchange_receipt(
            rich_ws, target_node="ext-peer", mode="propose", summary="Review spec"
        )
        raw_jsonl = rich_ws / work_board.OUTBOUND_RECEIPTS_REL_PATH
        with raw_jsonl.open("a", encoding="utf-8") as fh:
            fh.write("\nnot-json\n[1, 2]\n{}\n")
        loaded_rec = work_board.read_outbound_exchange_receipts(rich_ws)
        solo_channels = work_board.collect_counterpart_work_channels(solo_ws)
        rich_channels = work_board.collect_counterpart_work_channels(rich_ws, net_scope)

        # Assert
        assert empty_rec == []
        assert saved["target_node"] == "ext-peer" and len(loaded_rec) == 1
        assert solo_channels == []
        by_id = {c["node_id"]: c for c in rich_channels}
        assert "gov-iso" not in by_id and "persona-wallet" not in by_id
        assert by_id["persona-profile"]["direction"] == "parent"
        assert by_id["persona-profile"]["allowed_mode"] == "propose"
        assert by_id["persona-profile"]["active_count"] == 1
        assert by_id["venture-mvp"]["allowed_mode"] == "delegate"
        assert by_id["venture-mvp"]["active_count"] == 0
        assert by_id["ext-peer"]["outbound"][0]["summary"] == "Review spec"
        active_ids = [c["node_id"] for c in rich_channels if c["active_count"] > 0]
        assert active_ids[0] == "persona-profile"

    def test_collect_counterpart_work_channels_enforces_mesh_governance_modes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify full-mesh, hierarchical-only, curated-matrix, and wallet airlock filtering."""
        # Arrange
        ws_full = tmp_path / "persona-work"
        (ws_full / "system").mkdir(parents=True)
        (ws_full / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "persona-work", "entity_kind": "individual", "precedence": 87}),
            encoding="utf-8",
        )
        ws_hier = tmp_path / "dept-hier"
        (ws_hier / "system").mkdir(parents=True)
        (ws_hier / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "dept-hier",
                    "entity_kind": "enterprise",
                    "capability_policy": {
                        "mesh_governance": {"topology_mode": "hierarchical-only"}
                    },
                }
            ),
            encoding="utf-8",
        )
        ws_mat = tmp_path / "dept-eng"
        (ws_mat / "system").mkdir(parents=True)
        (ws_mat / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "dept-eng",
                    "entity_kind": "enterprise",
                    "capability_policy": {
                        "mesh_governance": {
                            "topology_mode": "curated-matrix",
                            "lateral_channels": [
                                {
                                    "source_node": "dept-eng",
                                    "target_node": "dept-ops",
                                    "allowed_verbs": ["consult_context", "delegate_work"],
                                    "reciprocal": False,
                                },
                                {
                                    "source_node": "dept-qa",
                                    "target_node": "dept-eng",
                                    "allowed_verbs": ["consult_context", "propose_work"],
                                    "reciprocal": True,
                                },
                                {
                                    "source_node": "dept-eng",
                                    "target_node": "dept-ro",
                                    "allowed_verbs": ["consult_context"],
                                    "reciprocal": True,
                                },
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        net_sc = {
            "network_representation_links": {
                "downward_child_nodes": [{"node_id": "persona-wallet", "layer_role": "squad"}],
                "lateral_peers": [
                    {"node_id": "persona-tutor", "layer_role": "department"},
                    {"node_id": "dept-ops", "layer_role": "department"},
                    {"node_id": "dept-qa", "layer_role": "department"},
                    {"node_id": "dept-ro", "layer_role": "department"},
                    {"node_id": "dept-blocked", "layer_role": "department"},
                    {"node_id": "persona-wallet", "layer_role": "squad"},
                ],
                "linked_nodes": [{"node_id": "persona-wallet", "relation": "lateral-peer"}],
            }
        }

        # Act
        ch_full = {
            c["node_id"]: c for c in work_board.collect_counterpart_work_channels(ws_full, net_sc)
        }
        ch_hier = {
            c["node_id"]: c for c in work_board.collect_counterpart_work_channels(ws_hier, net_sc)
        }
        ch_mat = {
            c["node_id"]: c for c in work_board.collect_counterpart_work_channels(ws_mat, net_sc)
        }

        # Assert
        assert "persona-tutor" in ch_full and "persona-wallet" not in ch_full
        assert ch_hier == {}
        assert ch_mat["dept-ops"]["allowed_mode"] == "delegate"
        assert ch_mat["dept-qa"]["allowed_mode"] == "propose"
        assert "dept-ro" not in ch_mat and "dept-blocked" not in ch_mat

    def test_render_work_board_and_channels_html_across_columns_and_modes_expected(self) -> None:
        """Verify filter bar, Work Inbox drawer, Kanban cards, Backlog promote, and channels."""
        # Arrange
        long_task = "**T99**: `venture/saas` " + ("Very long task description segment " * 3)
        tasks = [
            *[
                {"tracker": "WORKTASK.md", "state": " ", "body": f"**T{idx}**: Open item"}
                for idx in range(12)
            ],
            {"tracker": "WORKTASK.md", "state": "/", "body": long_task},
            {"tracker": "WORKTASK.md", "state": "x", "body": "**T0**: Completed item"},
            {"tracker": "WORKTASK.md", "state": "?", "body": "Custom state note"},
            {"tracker": "BACKLOG.md", "state": " ", "body": "[BKL-001] Future item"},
            {"tracker": "BACKLOG.md", "state": "x", "body": "[BKL-000] Archived item"},
        ]
        inbox_items = [
            {
                "request_id": "wreq-1234",
                "sender_node": "persona-profile",
                "priority": "P0",
                "summary": "Sync host configs",
                "status": "pending",
            }
        ]
        channels = [
            {
                "node_id": "persona-profile",
                "human_role": "Personal Hub",
                "direction": "parent",
                "arrow": "↑",
                "allowed_mode": "propose",
                "action_label": "Send Work Request (↑)",
                "inbound": [
                    {"path": "from-persona-profile/wreq-1234", "summary": "Sync host configs"}
                ],
                "outbound": [{"mode": "propose", "summary": "Ready for review"}],
                "active_count": 2,
            },
            {
                "node_id": "persona-tutor",
                "human_role": "Study & Tutor",
                "direction": "peer",
                "arrow": "↔",
                "allowed_mode": "propose",
                "action_label": "Send Work Request (↔)",
                "inbound": [],
                "outbound": [],
                "active_count": 0,
            },
        ]

        # Act
        board_with_peers = work_board.render_work_board_and_channels_html(
            "/api/modules/work-ledger", tasks, channels, inbox_items=inbox_items
        )
        board_standalone = work_board.render_work_board_and_channels_html(
            "/api/modules/work-ledger", [], []
        )

        # Assert
        assert "data-kanban-col='todo'" in board_with_peers
        assert "+2 more in WORKTASK.md" in board_with_peers
        assert "venture/saas" in board_with_peers
        assert "Incoming Work Requests" in board_with_peers
        assert "Accept → To Do" in board_with_peers and "Promote to To Do →" in board_with_peers
        assert "Start →" in board_with_peers and "Complete ✓" in board_with_peers
        assert "[BKL-001] Future item" in board_with_peers
        assert "data-counterpart='persona-profile' open" in board_with_peers
        assert "2 active" in board_with_peers and "0 pending" in board_with_peers
        assert "← Inbound" in board_with_peers and "→ Sent (propose)" in board_with_peers
        assert "Standalone node (0 connected 1-hop counterparts)" in board_standalone
        assert "0 backlog items in BACKLOG.md" in board_standalone
