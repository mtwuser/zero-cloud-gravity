"""Unit tests for zcg.cockpit.surfaces.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from zcg.cockpit import surfaces


class TestSurfaces:
    """Verify Subdomain x Environment routing, 3-Scope Node Data, and HTML5 Cockpit rendering."""

    def test_resolve_node_intranet_topology_across_archetypes_expected(self) -> None:
        """Verify individual direct, public knowledge, and enterprise staged intranet routing."""
        # Arrange
        # Act
        ind = surfaces.resolve_node_intranet_topology(
            {"entity_kind": "individual", "precedence": 88}, layer_id="lab-iso"
        )
        know = surfaces.resolve_node_intranet_topology(
            {"layer_role": "knowledge", "visibility": "public", "precedence": 20},
            layer_id="sci-maths",
            active_env="pro",
        )
        pub_ind = surfaces.resolve_node_intranet_topology(
            {
                "entity_kind": "individual",
                "layer_role": "knowledge",
                "visibility": "public",
                "precedence": 88,
            },
            layer_id="pub-alex",
            active_env="pro",
        )
        squad = surfaces.resolve_node_intranet_topology(
            {
                "layer_role": "squad",
                "governing_root_id": "corp-acme-root",
                "precedence": 50,
            },
            layer_id="grid-squad",
            active_env="tst",
        )

        # Assert
        assert ind["promotion_pipeline"] == "direct"
        assert ind["remote_production_url"] is None
        assert ind["node_host"] == "lab-iso.personal.local"
        assert know["environment_reachability"]["pro"] == "public-remote-live"
        assert know["active_subdomain_url"] == "https://sci-maths.knowledge.local"
        assert pub_ind["promotion_pipeline"] == "direct"
        assert pub_ind["node_host"] == "pub-alex.knowledge.local"
        assert pub_ind["environment_reachability"]["pro"] == "public-remote-live"
        assert pub_ind["remote_production_url"] == "https://pub-alex.knowledge.local"
        assert squad["node_host"] == "grid-squad.acme.intranet.local"
        assert squad["environment_reachability"]["tst"] == "local-preview-unprovisioned-intranet"

    def test_materialize_node_data_scopes_and_render_html_across_roles_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify all 5 view archetypes, network links, fleet inventory, and HTML5 output."""
        # Arrange — 1. Workstation Control Tower
        ws_tower = tmp_path / "tower-iso"
        ws_tower.mkdir()
        m_tower = {"layer_id": "tower-iso", "layer_role": "workstation", "precedence": 90}
        st_tower = {
            "plugin_id": "workstation-control-tower",
            "environment": "dev",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_tower, layer_id="tower-iso"
            ),
        }
        sc_tower = surfaces.materialize_node_data_scopes(ws_tower, m_tower, st_tower)
        assert sc_tower["node"]["representation_context"]["workstation_config"] is not None

        # 2. Individual Academic Tutor Lab with docs & knowledge mount
        ws_tutor = tmp_path / "tutor-iso"
        (ws_tutor / "docs").mkdir(parents=True)
        (ws_tutor / "docs/lesson.md").write_text("# Lesson\n", "utf-8")
        m_tutor = {
            "layer_id": "tutor-iso",
            "layer_role": "department",
            "entity_kind": "individual",
            "mounted_layers": [{"name": "sci-maths"}],
        }
        st_tutor = {
            "plugin_id": "tutor-study-cockpit",
            "environment": "pro",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_tutor, layer_id="tutor-iso", active_env="pro"
            ),
        }
        sc_tutor = surfaces.materialize_node_data_scopes(ws_tutor, m_tutor, st_tutor)
        assert sc_tutor["node"]["representation_context"]["academic_study_state"] is not None
        assert (
            sc_tutor["node"]["representation_context"]["dual_world_contract"]["use_case_overlay"]
            == "university-specialty-m2-m3"
        )
        assert sc_tutor["federation"]["cloud_iac_target"]["stage"] == "production-cloud-run-gke"

        # 2b. School Student Tutor Overlay (M1..M2), Personal Work Hub (:8787) & SecOps (5)
        m_school = {**m_tutor, "academic_stage": "school"}
        sc_school = surfaces.materialize_node_data_scopes(ws_tutor, m_school, st_tutor)
        assert (
            sc_school["node"]["representation_context"]["dual_world_contract"]["use_case_overlay"]
            == "school-student-m1-m2"
        )
        ws_work = tmp_path / "alex-work"
        ws_work.mkdir()
        m_work = {
            "layer_id": "alex-work",
            "layer_role": "department",
            "precedence": 87,
            "entity_kind": "individual",
            "default_stack_templates": ["business-base", "node-work-cockpit"],
            "linked_nodes": [
                {
                    "node_id": "org-alpha",
                    "relation": "hr-process",
                    "layer_role": "knowledge",
                    "precedence": 20,
                    "target_ref": "/should/not/leak",
                    "cockpit_url": "http://127.0.0.1:8720",
                    "shared_packs": ["corporate-operations"],
                }
            ],
        }
        st_work = {
            "plugin_id": "node-work-cockpit",
            "environment": "dev",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_work, layer_id="alex-work"
            ),
        }
        sc_work = surfaces.materialize_node_data_scopes(ws_work, m_work, st_work)
        assert (
            sc_work["node"]["representation_context"]["view_archetype"] == "personal-work-cockpit"
        )
        assert (
            sc_work["node"]["representation_context"]["dual_world_contract"]["use_case_overlay"]
            == "personal-career-and-ventures"
        )
        assert sc_work["node"]["representation_context"]["personal_work_state"] == {
            "context_tracks": ["master", "opportunity/*", "venture/*", "engagement/*"],
            "linked_nodes_count": 1,
        }
        assert (
            "target_ref"
            not in sc_work["network"]["network_representation_links"]["linked_nodes"][0]
        )
        m_secops = {"layer_id": "secops-iso", "layer_role": "domain-policy", "precedence": 5}
        st_secops = {
            "plugin_id": "secops-mcp-guardian",
            "environment": "dev",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_secops, layer_id="secops-iso"
            ),
        }
        sc_secops = surfaces.materialize_node_data_scopes(ws_tutor, m_secops, st_secops)
        assert (
            sc_secops["node"]["representation_context"]["view_archetype"] == "secops-mcp-guardian"
        )

        # 3. Corporate Root Hub + 4. Public Knowledge + 5. Squad with mocked network peers
        ws_corp = tmp_path / "corp-iso"
        (ws_corp / ".agents/runtime").mkdir(parents=True)
        (ws_corp / ".agents/runtime/hub.json").write_text(
            json.dumps({"plugin_id": "corporate-root-hub", "status": "active"}), "utf-8"
        )
        m_corp = {"layer_id": "corp-iso", "layer_role": "corporate"}
        st_corp = {
            "plugin_id": "corporate-root-hub",
            "environment": "tst",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_corp, layer_id="corp-iso", active_env="tst"
            ),
        }
        sc_corp = surfaces.materialize_node_data_scopes(ws_corp, m_corp, st_corp)
        assert sc_corp["node"]["representation_context"]["view_archetype"] == "corporate-root-hub"
        assert (
            sc_corp["node"]["representation_context"]["dual_world_contract"]["enterprise_scale"]
            == "small-startup"
        )
        assert len(sc_corp["federation"]["fleet_plugin_inventory"]) == 1

        ws_know = tmp_path / "sci-iso"
        ws_know.mkdir()
        m_know = {"layer_id": "sci-iso", "layer_role": "knowledge", "visibility": "public"}
        st_know = {
            "plugin_id": "node-work-cockpit",
            "environment": "dev",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_know, layer_id="sci-iso"
            ),
        }
        sc_know = surfaces.materialize_node_data_scopes(ws_know, m_know, st_know)
        assert (
            sc_know["node"]["representation_context"]["view_archetype"]
            == "knowledge-stewardship-portal"
        )

        ws_sq = tmp_path / "squad-iso"
        ws_sq.mkdir()
        m_sq = {
            "layer_id": "squad-iso",
            "layer_role": "squad",
            "enabled_modules": ["crud", "vault"],
        }
        st_sq = {
            "plugin_id": "node-work-cockpit",
            "environment": "dev",
            "intranet_topology": surfaces.resolve_node_intranet_topology(
                m_sq, layer_id="squad-iso"
            ),
        }
        fake_net = {
            "node_connection_summary": {
                "upward_governor": {"node_id": "dept-a", "layer_role": "department"},
                "downward_governed_nodes": [{"node_id": "svc-1", "layer_role": "service-node"}],
                "lateral_peers": [{"node_id": "squad-b", "layer_role": "squad"}],
            }
        }
        with patch("zcg.cockpit.surfaces.discover_network_topology", return_value=fake_net):
            html = surfaces.render_node_cockpit_html(ws_sq, m_sq, st_sq)
            sc_corp_mid = surfaces.materialize_node_data_scopes(ws_corp, m_corp, st_corp)
        # Act

        # Assert
        assert (
            sc_corp_mid["node"]["representation_context"]["dual_world_contract"]["enterprise_scale"]
            == "medium-scaleup"
        )
        dc = sc_corp["node"]["representation_context"]["delivery_channel"]
        assert dc["zones"] == ["Z1", "Z2", "Z3", "Z4"]
        assert dc["http_poll_stop_status"] == 286
        rt = sc_corp["node"]["representation_context"]["runtime_telemetry"]
        assert rt["regime"] == "OPTIMAL"
        assert rt["health_score"] == 1.0
        assert "data-zcg-surface='cockpit'" in html
        assert "/static/img/logo.svg" in html
        assert "--zcg-bg" in html
        assert "<script src='/cockpit-shell.js' defer></script>" in html
        assert "onclick=" not in html
        shell_js = (ws_sq / "surfaces/web/cockpit-shell.js").read_text("utf-8")
        assert "IslandBus" in shell_js
        assert "NL.lateral_peers" in shell_js
        assert "NL.linked_nodes" in shell_js
        assert "onclick=" not in shell_js
        assert "Node Work & Sprint Ledger" in html
        assert "Epistemic Knowledge & Spec Atlas" in html
        assert (ws_sq / "surfaces/data/node_scope.json").is_file()
