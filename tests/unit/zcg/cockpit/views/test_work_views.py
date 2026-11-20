"""Unit tests for zcg.cockpit.views.work_views.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from zcg.cockpit.views import work_views


class TestWorkViews:
    """Verify dedicated Dashboard, Backlog, Roadmaps, Validations, and sidebar tab composition."""

    def test_normalize_section_and_build_workspace_sidebar_tabs_expected(self) -> None:
        """Verify 4 core tabs, unlabeled optional capability group, and transversal stage titles."""
        # Arrange
        hub_mods = [
            {"module_id": "work_ledger", "title": "Work Board"},
            {"module_id": "docs_reader", "title": "Docs & Knowledge"},
            {"module_id": "spatial_atlas", "title": "Network Atlas"},
            {"module_id": "portal_inbox", "title": "External Mailbox"},
        ]
        rich_mods = [*hub_mods, {"module_id": "vault", "title": "Document Vault"}]

        urls = {
            "portal_inbox": "/api/modules/portal-inbox?mode=workspace",
            "vault": "/api/modules/vault?view=cards",
        }

        # Act
        sec_ov = work_views.normalize_work_section("overview")
        sec_bk = work_views.normalize_work_section("backlog")
        sec_mt = work_views.normalize_work_section("metrics")
        sec_unk = work_views.normalize_work_section("unknown")
        core_empty, cap_empty, eff_d = work_views.build_workspace_sidebar_tabs(
            hub_mods, urls, show_mailbox=False, raw_view=""
        )
        _, cap_rich, eff_v = work_views.build_workspace_sidebar_tabs(
            rich_mods, urls, show_mailbox=True, raw_view="vault"
        )
        t_docs = work_views.resolve_workspace_view_title(rich_mods, "docs")
        t_metrics = work_views.resolve_workspace_view_title(rich_mods, "metrics")
        t_vault = work_views.resolve_workspace_view_title(rich_mods, "vault")
        t_fb = work_views.resolve_workspace_view_title(rich_mods, "nonexistent")

        # Assert
        assert (sec_ov, sec_bk, sec_mt, sec_unk) == ("dashboard", "backlog", "metrics", "dashboard")
        assert eff_d == "dashboard" and str(cap_empty) == ""
        assert work_views.CORE_WORKSPACE_TABS[0][0] == "docs"
        assert "Docs &amp; Knowledge" in str(core_empty) and "Metrics" in str(core_empty)
        assert "Dashboard" in str(core_empty) and "Backlog" in str(core_empty)
        assert "Roadmaps" in str(core_empty) and "Validations" in str(core_empty)
        assert eff_v == "vault" and "Document Vault" in str(cap_rich)
        assert "External Mailbox" in str(cap_rich) and "Docs &amp; Knowledge" not in str(cap_rich)
        assert (t_docs, t_metrics, t_vault, t_fb) == (
            "Docs & Knowledge",
            "Metrics",
            "Document Vault",
            "Dashboard",
        )

    def test_render_dashboard_backlog_roadmaps_and_validations_views_expected(self) -> None:
        """Verify all 4 dedicated WORK* views across populated and empty tracker states."""
        # Arrange
        tasks = [
            {"tracker": "WORKTASK.md", "state": " ", "body": "**[P1]** Build feature/ui"},
            {"tracker": "WORKTASK.md", "state": "/", "body": "Active sprint item"},
            {"tracker": "WORKTASK.md", "state": "x", "body": "Shipped item"},
            {"tracker": "BACKLOG.md", "state": " ", "body": "**[P2]** [BKL-01] Future venture/app"},
            {"tracker": "BACKLOG.md", "state": "x", "body": "[BKL-00] Archived item"},
        ]
        inbox = [
            {
                "request_id": "wreq-1",
                "sender_node": "corp-iso",
                "priority": "P1",
                "summary": "Review spec",
                "status": "pending",
            }
        ]
        roadmap_rich = {
            "tracker_file": "WORKROAD.md",
            "open_count": 1,
            "in_progress_count": 1,
            "done_count": 1,
            "sections": [
                {
                    "heading": "Horizon 1",
                    "items": [
                        {"state": " ", "body": "Milestone A"},
                        {"state": "/", "body": "Milestone B"},
                        {"state": "x", "body": "Milestone C"},
                    ],
                }
            ],
            "roadmap_docs": [{"rel_path": "roadmaps/v1.md", "title": "Strategic v1"}],
        }
        vali_rich = {
            "verified_count": 1,
            "total_count": 2,
            "completion_pct": 50,
            "sections": [
                {
                    "heading": "UI Gates",
                    "items": [
                        {"state": " ", "body": "Check mobile header"},
                        {"state": "x", "body": "Check dark contrast"},
                    ],
                }
            ],
        }

        # Act
        dash_html = work_views.render_dashboard_kanban_html(
            "/api/modules/work-ledger", tasks, (), inbox_items=inbox
        )
        dash_dirty = work_views.render_dashboard_kanban_html(
            "/api/modules/work-ledger", tasks, (), scope_filter="own", tracker_dirty=True
        )
        bkl_html = work_views.render_backlog_view_html("/api/modules/work-ledger", tasks)
        bkl_dirty = work_views.render_backlog_view_html(
            "/api/modules/work-ledger", tasks, query_filter="BKL", tracker_dirty=True
        )
        bkl_empty = work_views.render_backlog_view_html("/api/modules/work-ledger", ())
        rm_html = work_views.render_roadmaps_view_html(
            "/api/modules/work-ledger", roadmap_rich, tracker_dirty=True
        )
        rm_empty = work_views.render_roadmaps_view_html("/api/modules/work-ledger", {})
        vl_html = work_views.render_validations_view_html(
            "/api/modules/work-ledger",
            vali_rich,
            environment_gates={
                "pre": {"allowed": True},
                "pro": {"allowed": False, "failed_gates": ["MISSING_CHANGELOG"]},
                "tst": "invalid",
            },
            tracker_dirty=True,
        )
        vl_suppressed = work_views.render_validations_view_html(
            "/api/modules/work-ledger",
            vali_rich,
            environment_gates={"pro": {"allowed": False, "failed_gates": ["MISSING_CHANGELOG"]}},
            show_promotion_gates=False,
        )
        vl_empty = work_views.render_validations_view_html("/api/modules/work-ledger", {})

        # Assert
        assert set(work_views.WORK_VIEW_SPECS) == {
            "dashboard",
            "backlog",
            "roadmaps",
            "validations",
        }
        assert "data-work-section='dashboard'" in dash_html and "zcg-kanban" in dash_html
        assert "zcg-filter-bar" in dash_html and "zcg-quick-add-bar" in dash_html
        assert "<select name='scope'" not in dash_html
        assert "<code>WORKTASK.md</code> · <code>[TASK-NNN]</code>" in dash_html
        assert "make task TASK=" in dash_html and "make complete TASK=" in dash_html
        assert "name='action' value='add'" in dash_html and "<select name='action'" not in dash_html
        assert "zcg-dirty-banner" not in dash_html and ">Reset</button>" not in dash_html
        assert "zcg-dirty-banner" in dash_dirty and "Commit Now" in dash_dirty
        assert "data-zcg-get='/api/modules/work-ledger?section=dashboard'" in dash_dirty
        assert ">Reset</button>" in dash_dirty
        assert "Active work summary" not in dash_html
        assert all("data-zcg-cli-hint" in h for h in (dash_html, bkl_html, rm_html, vl_html))
        assert "Promote to To Do →" in bkl_html and "Completed" in bkl_html
        assert "Queued Backlog" not in bkl_html and "WORKTASK.md" not in bkl_html
        assert "<code>BACKLOG.md</code> · <code>[BKL-NNN]</code>" in bkl_html
        assert "zcg inspect-horizon ." in bkl_html
        assert "zcg-dirty-banner" not in bkl_html and ">Reset</button>" not in bkl_html
        assert "zcg-dirty-banner" in bkl_dirty and ">Reset</button>" in bkl_dirty
        assert "data-zcg-get='/api/modules/work-ledger?section=backlog'" in bkl_dirty
        assert "0 matching backlog items" in bkl_empty
        assert "Strategic Roadmaps" not in rm_html
        assert "<code>WORKROAD.md</code> · <code>[ROAD-NNN]</code>" in rm_html
        assert "zcg compare-upstream ." in rm_html
        assert "Strategic v1" in rm_html and "Mark Done ✓" in rm_html and "Reopen" in rm_html
        assert "zcg-dirty-banner" in rm_html and "WORKROAD.md" in rm_html
        assert "No milestone checkboxes" in rm_empty and "zcg-dirty-banner" not in rm_empty
        assert "Validation &amp; Promotion" not in vl_html
        assert "<code>WORKVALI.md</code> · <code>[VAL-NNN]</code>" in vl_html
        assert "Gate [PRE]: <strong>READY</strong>" in vl_html
        assert "title='MISSING_CHANGELOG'>Gate [PRO]: <strong>BLOCKED</strong>" in vl_html
        assert "Gate [TST]: <strong>BLOCKED</strong>" in vl_html
        assert "make env-gate ENV=pro" in vl_html
        assert "Gate [" not in vl_suppressed and "make env-gate ENV=pro" not in vl_suppressed
        assert "Gate [" not in vl_empty and "make env-gate ENV=pro" not in vl_empty
        assert "Verify ✓" in vl_html and "Reopen" in vl_html and "zcg-dirty-banner" in vl_html
        assert "No validation items" in vl_empty and "zcg-dirty-banner" not in vl_empty

    def test_workspace_scope_filtering_corpora_banner_and_quick_target_select_expected(
        self,
    ) -> None:
        """Verify ws_scope=node|network|corpora across all 4 work views and Quick-Add select."""
        # Arrange
        tasks = [
            {"tracker": "WORKTASK.md", "state": " ", "body": "Local own task"},
            {
                "tracker": "WORKTASK.md",
                "state": " ",
                "body": "Delegated from `corp-iso`: Sync audit",
            },
            {"tracker": "BACKLOG.md", "state": " ", "body": "Local backlog"},
            {"tracker": "BACKLOG.md", "state": " ", "body": "Peer handoff *(origin_ref: `a#1`)*"},
        ]
        road_d = {
            "tracker_file": "WORKROAD.md",
            "sections": [
                {"heading": "Local Only", "items": [{"state": " ", "body": "Internal refactor"}]},
                {
                    "heading": "Cross-Node",
                    "items": [{"state": " ", "body": "Delegated from `corp-iso`: Ship API"}],
                },
            ],
        }
        vali_d = {
            "sections": [
                {"heading": "Own QA", "items": [{"state": " ", "body": "Check local logs"}]},
                {
                    "heading": "Mesh QA",
                    "items": [{"state": "x", "body": "Sync `a` -> `b` contract"}],
                },
            ]
        }
        sel_h = (
            "<select name='exchange_target'><option value='dept-ops'>↓ Delegate</option></select>"
        )

        # Act
        dash_net = work_views.render_dashboard_kanban_html(
            "/api/modules/work-ledger",
            tasks,
            (),
            target_select_html=sel_h,
            ws_scope="network",
        )
        dash_corp = work_views.render_dashboard_kanban_html(
            "/api/modules/work-ledger", tasks, (), ws_scope="corpora"
        )
        bkl_net = work_views.render_backlog_view_html(
            "/api/modules/work-ledger", tasks, ws_scope="network"
        )
        rm_net = work_views.render_roadmaps_view_html(
            "/api/modules/work-ledger", road_d, ws_scope="network"
        )
        vl_node = work_views.render_validations_view_html(
            "/api/modules/work-ledger", vali_d, ws_scope="node"
        )

        # Assert
        assert "name='exchange_target'" in dash_net
        assert "<details class='zcg-peer-channel' open" in dash_net
        assert "Sync audit" in dash_net and "Local own task" not in dash_net
        assert "Browse Connected Corpora →" in dash_corp
        assert "Peer handoff" in bkl_net and "Local backlog" not in bkl_net
        assert "Cross-Node" in rm_net and "Local Only" not in rm_net
        assert "Own QA" in vl_node and "Mesh QA" not in vl_node
