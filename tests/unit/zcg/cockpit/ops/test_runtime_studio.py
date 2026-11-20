"""Unit tests for zcg.cockpit.ops.runtime_studio.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from typing import Any

from zcg.cockpit.ops.runtime_studio import render_runtime_and_updates_html


def _sample_local_agy(*, installed: bool = True, online_allowed: bool = True) -> dict[str, Any]:
    return {
        "contract_rev": "zcg-agy-runtime-v1",
        "any_installed": installed,
        "online_checks_allowed": online_allowed,
        "home_stow_coupled": installed,
        "components": {
            "agents": {
                "label": "Antigravity Agents",
                "path": "/opt/antigravity-agents",
                "installed": installed,
                "version": "2.32.1" if installed else None,
            },
            "cli": {
                "label": "Antigravity CLI (agy)",
                "path": "/home/iso/.local/bin/agy",
                "installed": installed,
                "version": "0.14.0" if installed else None,
            },
            "ide": {
                "label": "Antigravity IDE",
                "path": "/opt/antigravity-ide",
                "installed": False,
                "version": None,
            },
        },
        "workspace_projection": {
            "rules_count": 4,
            "skills_count": 9,
            "has_session_pin": installed,
            "has_sidecar": installed,
        },
        "commands": {
            "workspace_path": "/ws/dept-iso",
            "open_workspace": "cd /ws/dept-iso && agy",
            "update_agents": "make workstation-update-agy",
            "update_cli": "/repo/scripts/install-antigravity.sh --cli",
            "update_all": "/repo/scripts/install-antigravity.sh --all",
        },
    }


class TestRuntimeStudio:
    """Verify pure-HTML Runtime & Updates Studio rendering across all status branches."""

    def test_render_runtime_studio_installed_online_update_and_parent_law_expected(self) -> None:
        """Verify live online release badges, 1-Hop Upgrade Law warning, open prompt, and policy."""
        # Arrange
        local_agy = _sample_local_agy(installed=True, online_allowed=True)
        online_check = {
            "checked": True,
            "reason": "OK",
            "updates_available": True,
            "components": {
                "agents": {
                    "installed_version": "2.32.1",
                    "latest_version": "2.33.0",
                    "update_available": True,
                    "status": "update-available",
                },
                "cli": {
                    "installed_version": "0.14.0",
                    "latest_version": "0.14.0",
                    "update_available": False,
                    "status": "up-to-date",
                },
                "ide": {
                    "installed_version": None,
                    "latest_version": "1.5.0",
                    "update_available": False,
                    "status": "not-installed",
                },
            },
        }
        update_plan = {
            "node_engine_version": "1.1.0",
            "oss_engine_version": "1.2.0",
            "target_version": "1.1.5",
            "update_source_kind": "governing-parent",
            "update_source_id": "persona-profile",
            "parent_update_required_first": True,
            "parent_admin_url": "http://persona-profile.localhost:8790/admin?tab=runtime",
            "update_available": True,
            "pending_releases": [
                {
                    "version": "1.2.0",
                    "title": "6-Pillar Constellation",
                    "highlights": ["Unified Runtime Studio", "1-Hop Upgrade Law"],
                }
            ],
            "commands": {
                "pull_oss": "",
                "sync_node": "make -C /ws/dept-iso sync STRATEGY=reconcile",
            },
            "reconciliation_prompt": "Reconcile dept-iso from v1.1.0 to v1.1.5.",
        }
        guidance = {
            "profile_label": "Software Engineering & Architecture",
            "recommended_base_model": "Gemini 4 Carbon (High)",
            "auto_orchestration_summary": "Inline for 1-4 files; Swarm for disjoint slices.",
        }

        # Act
        out = render_runtime_and_updates_html(
            local_agy, update_plan, online_check=online_check, agent_guidance=guidance
        )

        # Assert
        assert "<div id='zcg-runtime-panel'><section data-zcg-runtime>" in out
        assert "Local Antigravity Environment" in out
        assert "✓ $HOME Stow Coupled" in out
        assert "🟢 v2.32.1" in out and "⚪ Not installed" in out
        assert "🟠 Update available: v2.32.1 → v2.33.0" in out
        assert "🟢 Up to date (v0.14.0)" in out
        assert "⚪ Not installed (latest v1.5.0)" in out
        assert "data-zcg-get='/api/modules/runtime/check-updates'" in out
        assert "Copy Folder Path (Agents App)" in out
        assert "Copy Terminal CLI: cd & agy" in out
        assert "Copy CLI: Update Agents + CLI" in out
        assert "ZeroCloudGravity 1-Hop Node Update &amp; Reconciliation" in out
        assert "1-Hop Governing Parent: persona-profile" in out
        assert "🟠 Update / Sync Available -> v1.1.5" in out
        assert "⚠️ 1-Hop Upgrade Law: Governing parent 'persona-profile' is behind " in out
        assert "Open Parent Runtime &amp; Updates →" in out
        assert "6-Pillar Constellation" in out and "Unified Runtime Studio" in out
        assert "<h4>Guided AI Reconciliation Prompt</h4>" in out
        assert "<details" not in out
        assert "Copy Guided Reconciliation Prompt" in out
        assert "Set-and-Forget Agent &amp; Automatic Swarm Policy" in out
        assert "Gemini 4 Carbon (High)" in out
        assert "<script" not in out

    def test_render_runtime_studio_offline_airlock_up_to_date_and_edge_variants_expected(
        self,
    ) -> None:
        """Verify airlocked offline guard, unreachable status, collapsed prompt, and edge cases."""
        # Arrange
        airlock_agy = _sample_local_agy(installed=False, online_allowed=False)
        unreachable_check = {
            "checked": True,
            "reason": "OK",
            "updates_available": False,
            "components": {
                "agents": {"status": "unreachable"},
                "cli": {"status": "unreachable"},
                "ide": {"status": "unreachable"},
            },
        }
        up_to_date_plan: dict[str, Any] = {
            "node_engine_version": None,
            "oss_engine_version": "1.2.0",
            "target_version": "1.2.0",
            "update_source_kind": "oss-engine",
            "update_source_id": "zero-cloud-gravity",
            "parent_update_required_first": False,
            "parent_admin_url": "",
            "update_available": False,
            "pending_releases": [],
            "commands": {
                "pull_oss": "git -C /repo pull --ff-only",
                "sync_node": "zcg workstation sync",
            },
            "reconciliation_prompt": "Optional reconciliation prompt for Root 0.",
        }
        minimal_agy: dict[str, Any] = {
            "components": {},
            "workspace_projection": {},
            "commands": {},
        }
        minimal_plan: dict[str, Any] = {
            "parent_update_required_first": True,
            "parent_admin_url": "",
            "update_available": False,
            "commands": {},
            "reconciliation_prompt": "",
        }

        # Act
        out_airlock = render_runtime_and_updates_html(
            airlock_agy, up_to_date_plan, online_check=unreachable_check, agent_guidance=None
        )
        out_minimal = render_runtime_and_updates_html(minimal_agy, minimal_plan)

        # Assert
        assert "Standalone ($HOME Uncoupled)" in out_airlock
        assert "🔒 Offline Airlock (online checks disabled)" in out_airlock
        assert "data-zcg-get='/api/modules/runtime/check-updates'" not in out_airlock
        assert "⚠️ Release server unreachable" in out_airlock
        assert "unstamped" in out_airlock
        assert "Open-Source ZeroCloudGravity" in out_airlock
        assert "🟢 Up to date" in out_airlock
        assert "Copy Pull OSS CLI" in out_airlock and "Copy Sync CLI" in out_airlock
        assert "<summary><strong>Guided AI Reconciliation Prompt (Optional)</strong></summary>" in (
            out_airlock
        )
        assert "data-runtime-card='agent-policy'" not in out_airlock

        assert "Live Release" not in out_minimal
        assert "Open Parent Runtime &amp; Updates" not in out_minimal
        assert "Copy Guided Reconciliation Prompt" not in out_minimal
