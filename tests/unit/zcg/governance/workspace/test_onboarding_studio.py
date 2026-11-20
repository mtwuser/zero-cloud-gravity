"""Unit tests for zcg.governance.workspace.onboarding_studio.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from zcg.core import blueprints
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.workspace import onboarding_studio

if TYPE_CHECKING:
    from pathlib import Path


class TestOnboardingStudio:
    """Verify Day-0 kickoff prompt resolution, .zcg/runtime draft lifecycle, and TTY guides."""

    def test_canonical_workspace_root_url_and_fallback_prompt_synthesis_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify URL root normalization and fallback prompt synthesis without README fences."""
        # Arrange
        ws = tmp_path / "persona-tutor"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-tutor",
                    "layer_role": "department",
                    "entity_kind": "individual",
                    "precedence": 86,
                    "default_stack_templates": ["academic-base", "tutor-study-cockpit"],
                }
            ),
            encoding="utf-8",
        )
        (ws / "WORKTASK.md").write_text(
            "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n",
            encoding="utf-8",
        )

        # Act
        url_dash = onboarding_studio.canonical_workspace_root_url(
            "http://dev.persona-tutor.localhost:8786/dashboard?env=dev"
        )
        url_empty = onboarding_studio.canonical_workspace_root_url("", fallback_port=8786)
        url_invalid = onboarding_studio.canonical_workspace_root_url(
            "ftp://bad-scheme", fallback_port=8790
        )
        state = onboarding_studio.inspect_onboarding_studio_state(ws)

        # Assert
        assert url_dash == "http://dev.persona-tutor.localhost:8786/"
        assert url_empty == "http://127.0.0.1:8786/"
        assert url_invalid == "http://127.0.0.1:8790/"
        assert state["setup_state"] == "pending_customization"
        assert state["is_configured"] is False
        assert state["has_saved_draft"] is False
        assert "Phase A" in state["default_prompt"]
        assert state["open_workspace_cmd"] == f"cd {ws.resolve()} && agy"

    def test_save_inspect_corrupt_and_reset_onboarding_draft_lifecycle_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify draft save, corrupt JSON fallback, reset idempotence, and bipolar guards."""
        # Arrange
        ws = tmp_path / "corp-alpha"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "corp-alpha", "layer_role": "corporate", "precedence": 10}),
            encoding="utf-8",
        )
        (ws / "README.md").write_text(
            blueprints.render_layer_onboarding_readme(
                "corp-alpha", "corporate", 10, "corp-alpha", ["business-base"]
            ),
            encoding="utf-8",
        )
        draft_file = ws / onboarding_studio.ONBOARDING_DRAFT_REL_PATH

        # Act
        reset_missing = onboarding_studio.reset_onboarding_draft(ws)
        saved = onboarding_studio.save_onboarding_draft(
            ws, prompt_text="/sopen — Custom mission\r\nPhase A: Ready\n"
        )
        inspected = onboarding_studio.inspect_onboarding_studio_state(ws)
        draft_file.write_text("{corrupt-json", encoding="utf-8")
        corrupt_state = onboarding_studio.inspect_onboarding_studio_state(ws)
        draft_file.write_text("[1, 2, 3]", encoding="utf-8")
        list_state = onboarding_studio.inspect_onboarding_studio_state(ws)
        onboarding_studio.save_onboarding_draft(ws, prompt_text="Temporary custom text")
        reset_existing = onboarding_studio.reset_onboarding_draft(ws)

        # Assert
        assert reset_missing["reset"] is True and reset_missing["has_saved_draft"] is False
        assert saved["saved"] is True and saved["has_saved_draft"] is True
        assert "\r" not in saved["active_prompt"]
        assert inspected["has_saved_draft"] is True
        assert inspected["active_prompt"].startswith("/sopen — Custom mission")
        assert corrupt_state["has_saved_draft"] is False
        assert list_state["has_saved_draft"] is False
        assert reset_existing["has_saved_draft"] is False
        assert not draft_file.exists()
        with pytest.raises(ValueError, match="INVALID_ONBOARDING_DRAFT"):
            onboarding_studio.save_onboarding_draft(ws, prompt_text="   \n  ")
        with pytest.raises(ValueError, match="INVALID_ONBOARDING_DRAFT"):
            onboarding_studio.save_onboarding_draft(
                ws, prompt_text="x" * (onboarding_studio.MAX_ONBOARDING_DRAFT_CHARS + 1)
            )

    def test_format_bootstrap_tty_guide_live_and_dry_run_expected(self) -> None:
        """Verify 3-step Day-0 terminal guide formatting across live and dry-run payloads."""
        # Arrange
        live_payload = {
            "layer_id": "persona-profile",
            "target_dir": "/home/persona/persona-profile",
            "precedence": 90,
            "dry_run": False,
            "active_dashboard_url": "http://persona-profile.localhost:8790/dashboard?env=pro",
        }
        dry_payload = {
            "layer_id": "dept-iso",
            "target_dir": "/tmp/dept-iso",
            "precedence": 25,
            "dry_run": True,
        }

        # Act
        live_guide = onboarding_studio.format_bootstrap_tty_guide(live_payload)
        dry_guide = onboarding_studio.format_bootstrap_tty_guide(dry_payload)

        # Assert
        assert "pending initial setup" in live_guide
        assert "http://persona-profile.localhost:8790/" in live_guide
        assert "zcg install-antigravity --agents" in live_guide
        assert "Antigravity Agents" in live_guide
        assert "Projects -> /home/persona/persona-profile -> New Conversation" in live_guide
        assert "cd /home/persona/persona-profile && agy" in live_guide
        assert "dry-run preview" in dry_guide
        assert "http://127.0.0.1:8725/" in dry_guide

    def test_markdown_draft_save_load_corrupt_discard_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Markdown draft CRUD, CRLF normalization, corrupt fallbacks, and bipolar guards."""
        # Arrange
        ws = tmp_path / "md-draft-ws"
        ws.mkdir()
        key = "doc:docs/guides/sop.md"

        # Act
        empty_key_load = onboarding_studio.load_markdown_draft(ws, "  ")
        missing_load = onboarding_studio.load_markdown_draft(ws, key)
        discard_empty_key = onboarding_studio.discard_markdown_draft(ws, "  ")
        discard_missing = onboarding_studio.discard_markdown_draft(ws, key)
        saved = onboarding_studio.save_markdown_draft(
            ws, draft_key=key, content="# SOP\r\nLine 2\n", rel_path="docs/guides/sop.md"
        )
        loaded = onboarding_studio.load_markdown_draft(ws, key)
        draft_file = next((ws / onboarding_studio.MARKDOWN_DRAFTS_REL_DIR).glob("*.json"))
        draft_file.write_text("{corrupt", encoding="utf-8")
        corrupt_load = onboarding_studio.load_markdown_draft(ws, key)
        draft_file.write_text("[1, 2]", encoding="utf-8")
        list_load = onboarding_studio.load_markdown_draft(ws, key)
        draft_file.write_text('{"content": "   "}', encoding="utf-8")
        blank_load = onboarding_studio.load_markdown_draft(ws, key)
        discarded = onboarding_studio.discard_markdown_draft(ws, key)

        # Assert
        assert empty_key_load["has_draft"] is False and missing_load["has_draft"] is False
        assert discard_empty_key == {"discarded": True, "draft_key": ""}
        assert discard_missing == {"discarded": True, "draft_key": key}
        assert saved["saved"] is True and saved["line_count"] == 2
        assert loaded["has_draft"] is True and loaded["content"] == "# SOP\nLine 2\n"
        assert loaded["rel_path"] == "docs/guides/sop.md" and loaded["updated_at"]
        assert corrupt_load["has_draft"] is False
        assert list_load["has_draft"] is False
        assert blank_load["has_draft"] is False
        assert discarded == {"discarded": True, "draft_key": key}
        assert not draft_file.exists()
        with pytest.raises(ValueError, match="INVALID_MARKDOWN_DRAFT"):
            onboarding_studio.save_markdown_draft(ws, draft_key="  ", content="# OK\n")
        with pytest.raises(ValueError, match="INVALID_MARKDOWN_DRAFT"):
            onboarding_studio.save_markdown_draft(ws, draft_key=key, content="   \n")
        with pytest.raises(ValueError, match="INVALID_MARKDOWN_DRAFT"):
            onboarding_studio.save_markdown_draft(
                ws,
                draft_key=key,
                content="x" * (onboarding_studio.MAX_MARKDOWN_DRAFT_CHARS + 1),
            )
