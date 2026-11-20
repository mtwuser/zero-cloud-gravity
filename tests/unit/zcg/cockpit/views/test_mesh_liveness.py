"""Unit tests for zcg.cockpit.views.mesh_liveness.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from unittest.mock import patch

from zcg.cockpit.views import mesh_liveness
from zcg.web.ops.probes import PeerHealthVerdict


class TestMeshLiveness:
    """Verify loopback /healthz probing, liveness annotation, tree HTML, and branch switcher UI."""

    def test_probe_local_node_online_across_loopback_external_and_cache_expected(self) -> None:
        """Verify empty, invalid, external, portless loopback, cached, and default probe paths."""
        # Arrange
        calls: list[str] = []

        def _fake_probe(url: str) -> PeerHealthVerdict:
            calls.append(url)
            healthy = url.endswith(":8787")
            return PeerHealthVerdict(url, healthy, 200 if healthy else 0, "OPTIMAL", 0.5)

        cache: dict[int, bool] = {}

        # Act
        empty_res = mesh_liveness.probe_local_node_online("   ")
        bad_scheme = mesh_liveness.probe_local_node_online("ftp://invalid.example")
        no_host = mesh_liveness.probe_local_node_online("http:///missing-host")
        ext_res = mesh_liveness.probe_local_node_online("https://github.com/org/gov-iso")
        no_port = mesh_liveness.probe_local_node_online("http://wallet.persona.localhost/")
        on_first = mesh_liveness.probe_local_node_online(
            "http://work.persona.localhost:8787/", probe_fn=_fake_probe, cache=cache
        )
        on_cached = mesh_liveness.probe_local_node_online(
            "http://127.0.0.1:8787/dashboard", probe_fn=_fake_probe, cache=cache
        )
        off_first = mesh_liveness.probe_local_node_online(
            "http://profile.persona.localhost:8790/", probe_fn=_fake_probe, cache=cache
        )
        off_cached = mesh_liveness.probe_local_node_online(
            "http://localhost:8790/", probe_fn=_fake_probe, cache=cache
        )
        with patch(
            "zcg.cockpit.views.mesh_liveness.probe_peer_healthz",
            return_value=PeerHealthVerdict(
                "http://127.0.0.1:8788/healthz", True, 200, "OPTIMAL", 1
            ),
        ) as mock_default:
            uncached_default = mesh_liveness.probe_local_node_online(
                "http://wallet.persona.localhost:8788/"
            )

        # Assert
        assert empty_res == (False, "offline")
        assert bad_scheme == (False, "offline")
        assert no_host == (False, "offline")
        assert ext_res == (True, "external")
        assert no_port == (False, "offline")
        assert on_first == (True, "online") and on_cached == (True, "online")
        assert off_first == (False, "offline") and off_cached == (False, "offline")
        assert calls == ["http://127.0.0.1:8787", "http://127.0.0.1:8790"]
        assert uncached_default == (True, "online")
        mock_default.assert_called_once()

    def test_annotate_cross_node_and_passport_links_liveness_expected(self) -> None:
        """Verify nav item and passport network_representation_links liveness enrichment."""

        # Arrange
        def _fake_probe(url: str) -> PeerHealthVerdict:
            ok = url.endswith(":8787")
            return PeerHealthVerdict(url, ok, 200 if ok else 0, "OPTIMAL", 0.4)

        nav_in = [
            {
                "direction": "↑ Governor",
                "node_id": "persona-profile",
                "url": "http://persona-profile.localhost:8790/",
            },
            {
                "direction": "↔ Peer",
                "node_id": "persona-work",
                "url": "http://persona-work.localhost:8787/",
            },
            {
                "direction": "📚 Corpus",
                "node_id": "gov-iso",
                "url": "https://github.com/org/gov-iso",
            },
        ]
        net_with_parent = {
            "parent_home_node": {
                "node_id": "persona-profile",
                "cockpit_url": "http://persona-profile.localhost:8790",
            },
            "downward_child_nodes": [
                {"node_id": "persona-work", "cockpit_url": "http://persona-work.localhost:8787"},
                "skip-non-dict",
            ],
            "lateral_peers": [],
            "linked_nodes": [
                {"node_id": "gov-iso", "cockpit_url": "", "public_url": "https://g.example"}
            ],
            "knowledge_nodes": [{"node_id": "sci-maths", "cockpit_url": ""}],
        }
        net_root = {"parent_home_node": None}

        # Act
        nav_out = mesh_liveness.annotate_cross_node_liveness(nav_in, probe_fn=_fake_probe)
        pass_child = mesh_liveness.annotate_passport_links_liveness(
            net_with_parent, probe_fn=_fake_probe
        )
        pass_root = mesh_liveness.annotate_passport_links_liveness(net_root, probe_fn=_fake_probe)

        # Assert
        assert [it["liveness"] for it in nav_out] == ["offline", "online", "external"]
        assert [it["online"] for it in nav_out] == ["false", "true", "true"]
        assert pass_child["parent_home_node"]["online"] is False
        assert pass_child["downward_child_nodes"][0]["online"] is True
        assert len(pass_child["downward_child_nodes"]) == 1
        assert pass_child["linked_nodes"][0]["liveness"] == "external"
        assert pass_child["knowledge_nodes"][0]["online"] is False
        assert pass_root["parent_home_node"] is None

    def test_render_liveness_network_tree_html_across_states_expected(self) -> None:
        """Verify standalone, offline disabled controls, external corpora, and crown fallback."""
        # Arrange
        full_items = [
            {
                "direction": "↑ Governor",
                "node_id": "persona-profile",
                "role_label": "Personal Hub",
                "horizon_group": "1-Hop Hierarchy",
                "url": "http://persona-profile.localhost:8790/",
                "liveness": "offline",
            },
            {
                "direction": "↔ Peer",
                "node_id": "persona-work",
                "role_label": "Career & Ventures",
                "horizon_group": "1-Hop Hierarchy",
                "url": "http://persona-work.persona-profile.localhost:8787/",
                "liveness": "online",
            },
            {
                "direction": "Link:service-contract",
                "node_id": "partner-b2b",
                "role_label": "Department",
                "horizon_group": "Peers & B2B",
                "url": "http://partner.localhost:8735/",
                "liveness": "online",
            },
            {
                "direction": "Link:knowledge-feed",
                "node_id": "gov-iso",
                "role_label": "Knowledge Corpus",
                "horizon_group": "Public Admin",
                "url": "https://github.com/org/gov-iso",
                "liveness": "external",
            },
            {
                "direction": "📚 Corpus",
                "node_id": "sci-economic",
                "role": "knowledge",
                "horizon_group": "Knowledge",
                "url": "https://github.com/org/sci-economic",
                "liveness": "external",
            },
        ]
        crown_only_items = [
            {
                "direction": "↓ Sub-Node",
                "node_id": "persona-wallet",
                "role_label": "Patrimony & Wallet",
                "horizon_group": "1-Hop Hierarchy",
                "url": "http://persona-wallet.persona-profile.localhost:8788/",
                "liveness": "online",
            }
        ]

        # Act
        standalone_html = mesh_liveness.render_liveness_network_tree_html("solo-node", [])
        full_html = mesh_liveness.render_liveness_network_tree_html("persona-wallet", full_items)
        crown_html = mesh_liveness.render_liveness_network_tree_html(
            "persona-profile", crown_only_items
        )
        menu_empty = mesh_liveness.render_menu_constellation_html([])
        menu_full = mesh_liveness.render_menu_constellation_html(
            [
                *full_items,
                {
                    "direction": "↓ Sub-Node",
                    "node_id": "persona-game",
                    "role_label": "Game & Lab",
                    "url": "http://persona-game.persona-profile.localhost:8789/",
                    "liveness": "offline",
                },
                {
                    "direction": "⇄ Peer",
                    "node_id": "remote-peer",
                    "role": "peer",
                    "url": "https://peer.example.org/",
                    "liveness": "external",
                },
            ]
        )
        menu_many = mesh_liveness.render_menu_constellation_html(crown_only_items * 7)

        # Assert
        assert menu_empty == ""
        assert "<details class='zcg-menu-constellation' open>" in menu_full
        assert "1-Hop Nodes (4) <span aria-hidden='true'>▾</span>" in menu_full
        assert "zcg-menu-constellation__toggle" in menu_full and "Network Atlas" not in menu_full
        assert (
            "persona-work" in menu_full and "persona-game" in menu_full and "Offline" in menu_full
        )
        assert "sci-economic" not in menu_full and "gov-iso" not in menu_full
        assert "target='_blank'" in menu_full
        assert "<details class='zcg-menu-constellation'>" in menu_many
        assert "1-Hop Nodes (7) <span aria-hidden='true'>▾</span>" in menu_many
        assert "zcg-menu-constellation__list" in menu_many
        assert "Standalone sovereign node" in standalone_html
        assert "Root 0 Origin" not in standalone_html
        assert "zcg-tree__item--parent zcg-tree__item--offline" in full_html
        assert "aria-disabled='true'" in full_html and "Personal Hub · Offline" in full_html
        assert "href='http://persona-work.persona-profile.localhost:8787/'" in full_html
        assert "Explicit Node Links" in full_html and "Knowledge &amp; Corpora" in full_html
        assert "zcg-tree__item--peer zcg-tree__item--corpus" in full_html
        assert "target='_blank'" in full_html and "sci-economic" in full_html
        assert "zcg-tree__item--root-self" in crown_html and "Root 0 · Current" in crown_html
        assert "Root 0 Origin" not in crown_html and "zcg-tree__divider" not in crown_html

    def test_render_branch_switcher_html_excludes_blueprints_and_adds_new_form_expected(
        self,
    ) -> None:
        """Verify blueprint chips are excluded from branch chips and + New branch is rendered."""
        # Arrange
        rich_branches = {
            "active_branch": "master",
            "tracks": [
                "skip-non-dict",
                {"branch": "master", "purpose": "Main branch", "status": "active"},
                {"branch": "specialty/maths", "purpose": "Maths track", "status": "created"},
                {"branch": "specialty/ghost", "purpose": "Uncreated", "status": "blueprint"},
            ],
            "blueprints": [
                {"branch": "specialty/physics", "purpose": "Physics lab"},
                "skip-str",
            ],
        }
        minimal_branches = {
            "active_branch": "master",
            "tracks": [{"branch": "master", "status": "active"}],
            "blueprints": [],
        }

        # Act
        rich_html = mesh_liveness.render_branch_switcher_html(rich_branches)
        min_html = mesh_liveness.render_branch_switcher_html(minimal_branches)
        nav_branch_dd = mesh_liveness.render_navbar_branch_dropdown_html(rich_branches)
        env_staged_dev = mesh_liveness.render_navbar_env_switcher_html(
            active_env="dev",
            promotion_pipeline="staged",
            entity_kind="enterprise",
            env_urls={"dev": "/?env=dev", "pro": "/?env=pro"},
        )
        env_staged_pro = mesh_liveness.render_navbar_env_switcher_html(
            active_env="invalid",
            promotion_pipeline="staged",
            entity_kind="open-source",
        )
        env_direct_pro = mesh_liveness.render_navbar_env_switcher_html(
            active_env="pro",
            promotion_pipeline="direct",
            entity_kind="individual",
        )
        env_direct_dev = mesh_liveness.render_navbar_env_switcher_html(
            active_env="dev",
            promotion_pipeline="direct",
            entity_kind="individual",
        )
        env_explicit_stages = mesh_liveness.render_navbar_env_switcher_html(
            active_env="pro",
            stages=("dev", "pro"),
            href_prefix="/admin?tab=health",
        )
        env_no_switch = mesh_liveness.render_navbar_env_switcher_html(
            active_env="dev",
            stages=("dev", "pro"),
            can_switch=False,
        )

        # Assert
        assert "● <code>master</code>" in rich_html
        assert "✓ <code>specialty/maths</code>" in rich_html
        assert "name='allow_create' value='0'" in rich_html
        assert "specialty/ghost" not in rich_html
        assert "+ New branch" in rich_html and "name='allow_create' value='1'" in rich_html
        assert "<datalist id='zcg-bp-list'>" in rich_html
        assert "specialty/physics" in rich_html and "<datalist" not in min_html
        assert "zcg-branch-dd" in nav_branch_dd and "zcg-nav-branch-out" in nav_branch_dd
        assert "Env: DEV" in env_staged_dev and "zcg-env-dot--dev" in env_staged_dev
        assert "Env: PRO" in env_staged_pro and "/?env=tst" in env_staged_pro
        assert "LIVE" not in env_staged_pro
        assert env_direct_pro == "" and env_direct_dev == ""
        assert "/admin?tab=health&amp;env=dev" in env_explicit_stages
        assert env_no_switch == ""
