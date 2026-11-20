"""Unit tests for zcg.cockpit.ops.mesh_studio.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from zcg.cockpit.ops.mesh_studio import (
    activate_local_mesh_node,
    build_constellation_pillars,
    is_corpus_link,
    parse_mesh_policy_mutation,
    render_corpora_scope_alert_html,
    render_hierarchy_node_row_html,
    render_link_form_html,
    render_mesh_governance_card_html,
    render_quick_task_target_select_html,
    render_unlink_btn,
    render_workspace_scope_bar_html,
    resolve_local_node_workspace_dir,
)
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.policy.mesh_relations import (
    NodeRelationGrant,
    configure_mesh_governance_policy,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestMeshStudio:
    """Verify Workspace Scope Lens, Quick-Task Target Selector, and Mesh Governance Studio."""

    def test_workspace_scope_bar_corpora_alert_and_quick_task_selector_expected(self) -> None:
        """Verify 4-pill scope bar, Corpora banner, and grant-driven Quick-Add target options."""
        # Arrange
        grants = (
            NodeRelationGrant(
                "persona-work", "persona-wallet", "squad", "airlocked", (), False, "persona-profile"
            ),
            NodeRelationGrant(
                "persona-work",
                "persona-profile",
                "workstation",
                "governed-child",
                ("consult_context", "propose_work"),
                True,
                "persona-profile",
            ),
            NodeRelationGrant(
                "persona-work",
                "persona-tutor",
                "department",
                "governed-peer",
                ("consult_context", "propose_work"),
                True,
                "persona-profile",
            ),
            NodeRelationGrant(
                "persona-work",
                "venture-mvp",
                "project",
                "governor",
                ("consult_context", "propose_work", "delegate_work", "validate_gate"),
                True,
                "persona-work",
            ),
        )

        # Act
        bar_default = render_workspace_scope_bar_html()
        bar_net = render_workspace_scope_bar_html("network")
        alert_empty = render_corpora_scope_alert_html("node")
        alert_corp = render_corpora_scope_alert_html("corpora")
        sel_empty = render_quick_task_target_select_html(())
        sel_airlock = render_quick_task_target_select_html((grants[0],))
        sel_full = render_quick_task_target_select_html(grants)

        # Assert
        assert "data-zcg-ws-scope='all'" in bar_default and "data-ws-scope='corpora'" in bar_default
        assert "data-ws-scope='network' aria-pressed='true'" in bar_net
        assert alert_empty == "" and "Browse Connected Corpora →" in alert_corp
        assert sel_empty == "" and sel_airlock == ""
        assert "📍 This Node (WORKTASK.md)" in sel_full
        assert "↑ Propose: persona-profile" in sel_full
        assert "↔ Request: persona-tutor" in sel_full
        assert "↓ Delegate: venture-mvp" in sel_full
        assert "persona-wallet" not in sel_full

    def test_mesh_governance_card_link_helpers_and_constellation_pillars_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Root 0 editor (0/1/2+ channels), child inherited card, and link/pillar helpers."""
        # Arrange
        root_ws = tmp_path / "corp-iso"
        (root_ws / "system").mkdir(parents=True)
        (root_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "corp-iso",
                    "layer_role": "corporate",
                    "entity_kind": "enterprise",
                    "precedence": 30,
                }
            ),
            encoding="utf-8",
        )
        eng_ws = root_ws / "layers/dept-eng"
        ops_ws = root_ws / "layers/dept-ops"
        for cdir, cid in ((eng_ws, "dept-eng"), (ops_ws, "dept-ops")):
            (cdir / "system").mkdir(parents=True)
            (cdir / NODE_MANIFEST_REL_PATH).write_text(
                json.dumps(
                    {
                        "layer_id": cid,
                        "layer_role": "department",
                        "entity_kind": "enterprise",
                        "governing_root_id": "corp-iso",
                        "precedence": 40,
                    }
                ),
                encoding="utf-8",
            )
        standalone_ws = tmp_path / "solo-project"
        standalone_ws.mkdir()

        # Act
        gov_empty_html = render_mesh_governance_card_html(
            root_ws, clean_prefix="/api/modules/node-mesh", children=({"node_id": "dept-eng"},)
        )
        configure_mesh_governance_policy(
            root_ws,
            topology_mode="curated-matrix",
            add_channel={
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": ["consult_context", "propose_work"],
                "reciprocal": False,
            },
        )
        gov_full_html = render_mesh_governance_card_html(
            root_ws,
            clean_prefix="/api/modules/node-mesh",
            children=(
                {"node_id": "dept-eng"},
                {"node_id": "dept-ops"},
                {"node_id": "persona-wallet"},
            ),
        )
        child_html = render_mesh_governance_card_html(
            eng_ws, clean_prefix="/api/modules/node-mesh", children=()
        )
        solo_html = render_mesh_governance_card_html(
            standalone_ws, clean_prefix="/api/modules/node-mesh", children=()
        )
        link_form = render_link_form_html("/api/modules/node-mesh/link")
        unlink_btn = render_unlink_btn("/api/modules/node-mesh/unlink", "org-iso")
        pillars = build_constellation_pillars(
            root_ws,
            "persona-work",
            {"upstream_layer": {"layer_id": "persona-profile"}, "linked_nodes": []},
        )
        solo_pillars = build_constellation_pillars(root_ws, "custom-hub", {})

        # Assert
        assert "Governed Mesh &amp; Role Policy (<code>corp-iso</code>)" in gov_empty_html
        assert "0 curated lateral channels configured." in gov_empty_html
        assert "Authorize Channel" not in gov_empty_html
        assert "dept-eng</code> → <code>dept-ops" in gov_full_html
        assert "action_kind' value='remove_channel'" in gov_full_html
        assert "Authorize Channel" in gov_full_html and "persona-wallet" not in gov_full_html
        assert "Inherited Mesh Role Policy (Governed by <code>corp-iso</code>)" in child_html
        assert "dept-ops · governed-peer" in child_html
        assert "0 active 1-hop relation grants resolved." in solo_html
        assert "Connect Sovereign Node" in link_form and "Disconnect" in unlink_btn
        assert is_corpus_link({"node_id": "sci-maths"}) is True
        assert is_corpus_link({"node_id": "partner-iso", "relation": "b2b-collaboration"}) is False
        assert any(p["node_id"] == "persona-profile" and p["status"] == "active" for p in pillars)
        assert all(p["node_id"].startswith("custom-hub-") for p in solo_pillars)

    def test_resolve_local_node_workspace_dir_order_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify kebab validation, candidate lookup order, and manifest layer_id matching."""
        # Arrange
        ws = tmp_path / "corp-iso"
        mismatch_dir = ws / "layers/dept-eng"
        sibling_dir = tmp_path / "dept-eng"
        child_dir = ws / "layers/dept-child"
        for d, lid in (
            (mismatch_dir, "wrong-id"),
            (sibling_dir, "dept-eng"),
            (child_dir, "dept-child"),
        ):
            (d / "system").mkdir(parents=True)
            (d / NODE_MANIFEST_REL_PATH).write_text(json.dumps({"layer_id": lid}), "utf-8")

        # Act
        invalid = resolve_local_node_workspace_dir(ws, "../escape")
        resolved_child = resolve_local_node_workspace_dir(ws, "dept-child")
        resolved_sib = resolve_local_node_workspace_dir(ws, "dept-eng")
        missing = resolve_local_node_workspace_dir(ws, "dept-missing")

        # Assert
        assert invalid is None
        assert resolved_child == child_dir.resolve()
        assert resolved_sib == sibling_dir.resolve()
        assert missing is None

    def test_render_hierarchy_node_row_html_online_offline_wakeup_and_plain_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify hierarchy row renders Online link, Offline wakeup controls, or plain badges."""
        # Arrange
        ws = tmp_path / "corp-iso"
        child_dir = ws / "layers/dept-child"
        (child_dir / "system").mkdir(parents=True)
        (child_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "dept-child"}), "utf-8"
        )
        sib_dir = tmp_path / "dept-sib"
        (sib_dir / "system").mkdir(parents=True)
        (sib_dir / NODE_MANIFEST_REL_PATH).write_text(json.dumps({"layer_id": "dept-sib"}), "utf-8")
        cache: dict[int, bool] = {}

        # Act
        with patch(
            "zcg.cockpit.ops.mesh_studio.probe_local_node_online",
            side_effect=[(True, "online"), (False, "offline"), (False, "offline")],
        ):
            online_row = render_hierarchy_node_row_html(
                ws,
                sym="↳",
                nid="dept-child",
                kind="child",
                role_label="Department",
                clean_prefix="/api/modules/node-mesh",
                entry={"cockpit_url": "http://dept-child.localhost:8752/"},
                cache=cache,
            )
            offline_child_row = render_hierarchy_node_row_html(
                ws,
                sym="↳",
                nid="dept-child",
                kind="child",
                role_label="Department",
                clean_prefix="/api/modules/node-mesh",
                entry={"cockpit_url": "http://dept-child.localhost:8752/"},
                cache=cache,
            )
            offline_parent_row = render_hierarchy_node_row_html(
                ws,
                sym="↑",
                nid="corp-parent",
                kind="Root 0 / Parent",
                role_label="Corporate",
                clean_prefix="/api/modules/node-mesh",
                entry={"public_url": "http://corp-parent.localhost:8750/"},
                cache=cache,
            )
        offline_sib_row = render_hierarchy_node_row_html(
            ws,
            sym="↔",
            nid="dept-sib",
            kind="sibling",
            role_label="Department",
            clean_prefix="/api/modules/node-mesh",
            entry={},
        )
        plain_row = render_hierarchy_node_row_html(
            ws,
            sym="↳",
            nid="dept-remote",
            kind="child",
            role_label="Department",
            clean_prefix="/api/modules/node-mesh",
        )

        # Assert
        assert "🟢 Online" in online_row and "Open Workspace →" in online_row
        assert "http://dept-child.localhost:8752/" in online_row
        assert "⚪ Offline" in offline_child_row and "Start Workspace" in offline_child_row
        assert "action='/api/modules/node-mesh/activate'" in offline_child_row
        assert f"zcg apply-project {child_dir.resolve()} --service-action activate" in (
            offline_child_row
        )
        assert "Start Workspace" in offline_sib_row and "dept-sib" in offline_sib_row
        assert "⚪ Offline" in offline_parent_row and "Start Workspace" not in offline_parent_row
        assert "⚪ Offline" not in plain_row and "Start Workspace" not in plain_row

    def test_activate_local_mesh_node_success_scope_refresh_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local wakeup activates target, refreshes parent scopes, and guards missing IDs."""
        # Arrange
        ws = tmp_path / "corp-iso"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps({"layer_id": "corp-iso"}), "utf-8")
        (ws / "surfaces/data").mkdir(parents=True)
        (ws / "surfaces/data/node_scope.json").write_text("{}", "utf-8")
        child_dir = ws / "layers/dept-child"
        (child_dir / "system").mkdir(parents=True)
        (child_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "dept-child"}), "utf-8"
        )
        bare_ws = tmp_path / "bare-hub"
        bare_child = bare_ws / "layers/dept-bare"
        (bare_child / "system").mkdir(parents=True)
        (bare_child / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "dept-bare"}), "utf-8"
        )

        # Act
        with pytest.raises(ValueError, match="TARGET_WORKSPACE_NOT_FOUND"):
            activate_local_mesh_node(ws, "dept-missing")

        with patch(
            "zcg.cockpit.ops.lifecycle.manage_plugin_service",
            return_value={
                "layer_id": "dept-child",
                "environment": "dev",
                "services": [
                    {
                        "intranet_topology": {
                            "local_subdomain_url": "http://dept-child.localhost:8752/"
                        }
                    }
                ],
            },
        ) as svc_mock:
            act_res = activate_local_mesh_node(ws, "dept-child")
        with patch(
            "zcg.cockpit.ops.lifecycle.manage_plugin_service",
            return_value={"layer_id": "dept-bare", "environment": "dev", "services": []},
        ) as bare_mock:
            bare_res = activate_local_mesh_node(bare_ws, "dept-bare")

        # Assert
        assert act_res["activated_node_id"] == "dept-child"
        assert act_res["cockpit_url"] == "http://dept-child.localhost:8752/"
        assert act_res["workspace_dir"] == str(child_dir.resolve())
        assert svc_mock.call_count == 2
        assert svc_mock.call_args_list[0].kwargs["parent_dir"] == ws
        assert bare_res["cockpit_url"] == "http://127.0.0.1:8750/"
        bare_mock.assert_called_once_with(
            bare_child.resolve(), action="activate", target_env="", parent_dir=None
        )

    def test_parse_mesh_policy_mutation_add_remove_and_noop_expected(self) -> None:
        """Verify policy payload parsing for add_channel (JSON/form), remove_channel, and no-op."""
        # Arrange
        noop_pl = {"topology_mode": "full-mesh"}

        # Act
        noop = parse_mesh_policy_mutation(noop_pl, content_type="application/json")
        add_json = parse_mesh_policy_mutation(
            {
                "action_kind": "add_channel",
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": ["consult_context", ""],
                "reciprocal": False,
            },
            content_type="application/json",
        )
        add_form = parse_mesh_policy_mutation(
            {
                "action_kind": "add_channel",
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": "consult_context,propose_work",
                "reciprocal": "1",
            },
            content_type="application/x-www-form-urlencoded",
        )
        rem_res = parse_mesh_policy_mutation(
            {"action_kind": "remove_channel", "source": "dept-eng", "target": "dept-ops"},
            content_type="application/json",
        )

        # Assert
        assert noop == (None, None)
        assert add_json == (
            {
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": ["consult_context"],
                "reciprocal": False,
            },
            None,
        )
        assert add_form == (
            {
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": ["consult_context", "propose_work"],
                "reciprocal": True,
            },
            None,
        )
        assert rem_res == (None, ("dept-eng", "dept-ops"))
