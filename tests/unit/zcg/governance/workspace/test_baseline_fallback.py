"""Unit tests for zcg.governance.workspace.baseline_fallback.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcg.core.constants import REPO_DIR
from zcg.governance.work import horizon
from zcg.governance.workspace import baseline_fallback, scaffolder


def _seed_engine_baseline(engine_dir: Path) -> None:
    ub_rules = engine_dir / "templates/human-stack/universal-base/rules"
    ub_rules.mkdir(parents=True, exist_ok=True)
    (engine_dir / "templates/human-stack/universal-base/template.json").write_text(
        '{"template_id": "universal-base", "kind": "human-stack"}\n', encoding="utf-8"
    )
    (ub_rules / "universal-base.md").write_text(
        "# ZeroCloudGravity Universal Rules\n- Always verify.\n", encoding="utf-8"
    )
    for sk in ("sopen", "continue", "sclose", "review", "enrich", "governance", "architecture"):
        sk_dir = engine_dir / "antigravity/.gemini/config/skills" / sk
        sk_dir.mkdir(parents=True, exist_ok=True)
        (sk_dir / "SKILL.md").write_text(
            f'---\nname: {sk}\ndescription: "Execute {sk} workflow."\n---\n# {sk}\n',
            encoding="utf-8",
        )


class TestBaselineFallback:
    """Verify $HOME baseline detection, local workspace fallback, and safe deduplication."""

    def test_has_global_zcg_baseline_detection_and_pytest_guard_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify pytest default guard, forced probe, and $HOME marker/sopen checks."""
        # Arrange
        bare_home = tmp_path / "bare-home"
        bare_home.mkdir()

        # Act — default pytest hermetic guard returns True when home_dir is None
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "unit")
        monkeypatch.delenv("ZCG_FORCE_HOME_PROBE", raising=False)
        guard_res = baseline_fallback.has_global_zcg_baseline(None)

        # Assert
        assert guard_res is True

        # Forced probe inspects Path.home()
        monkeypatch.setenv("ZCG_FORCE_HOME_PROBE", "1")
        monkeypatch.setattr(Path, "home", lambda: bare_home)
        assert baseline_fallback.has_global_zcg_baseline(None) is False

        # Explicit home_dir checks missing files, foreign AGENTS.md, and valid ZCG baseline
        assert baseline_fallback.has_global_zcg_baseline(bare_home) is False
        cfg = bare_home / ".gemini/config"
        (cfg / "skills/sopen").mkdir(parents=True)
        (cfg / "AGENTS.md").write_text("# Other Agent Config\n", encoding="utf-8")
        assert baseline_fallback.has_global_zcg_baseline(bare_home) is False
        (cfg / "skills/sopen/SKILL.md").write_text("# sopen\n", encoding="utf-8")
        assert baseline_fallback.has_global_zcg_baseline(bare_home) is False
        (cfg / "AGENTS.md").write_text("# ZeroCloudGravity Universal Rules\n", encoding="utf-8")
        assert baseline_fallback.has_global_zcg_baseline(bare_home) is True

    def test_reconcile_workspace_global_baseline_materialize_and_prune_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local fallback materialization when $HOME is bare and safe pruning when set."""
        # Arrange
        eng = tmp_path / "engine"
        proj = tmp_path / "standalone-ws"
        bare_home = tmp_path / "bare-home"
        ready_home = tmp_path / "ready-home"
        _seed_engine_baseline(eng)
        proj.mkdir()
        bare_home.mkdir()
        (ready_home / ".gemini/config/skills/sopen").mkdir(parents=True)
        (ready_home / ".gemini/config/AGENTS.md").write_text(
            "# ZeroCloudGravity Universal Rules\n", encoding="utf-8"
        )
        (ready_home / ".gemini/config/skills/sopen/SKILL.md").write_text("# sopen\n", "utf-8")

        # Act — resolve base skills including business-base, science-base, and blank entries
        sk_list = baseline_fallback.resolve_fallback_base_skills(
            ["", "business-base", "science-base", "business-base", "academic-base"]
        )
        assert "sopen" in sk_list
        assert "governance" in sk_list
        assert "architecture" in sk_list
        assert (
            "audit" in sk_list
        )  # audit missing on disk in _seed_engine_baseline tests skip branch

        # Empty engine without universal-base template
        empty_eng = tmp_path / "empty-eng"
        empty_eng.mkdir()
        m0, p0 = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=empty_eng,
            active_template_ids=(),
            already_copied=(),
            home_dir=bare_home,
        )
        assert m0 == [] and p0 == []

        # Dry-run fallback materialization
        m_dry, p_dry = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=("business-base", "science-base"),
            already_copied=(".agents/skills/enrich/SKILL.md",),
            home_dir=bare_home,
            dry_run=True,
        )
        assert ".agents/rules/universal-base.md" in m_dry
        assert ".agents/skills/sopen/SKILL.md" in m_dry
        assert ".agents/skills/enrich/SKILL.md" not in m_dry
        assert p_dry == []
        assert not (proj / ".agents/rules/universal-base.md").exists()

        # Live fallback materialization + already_copied rule skip check
        m_live, _ = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=("business-base", "science-base"),
            already_copied=(),
            home_dir=bare_home,
            dry_run=False,
        )
        assert ".agents/rules/universal-base.md" in m_live
        assert (proj / ".agents/rules/universal-base.md").is_file()
        assert (proj / ".agents/skills/governance/SKILL.md").is_file()

        m_skip, _ = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=(),
            already_copied=(".agents/rules/universal-base.md", ".agents/skills/sopen/SKILL.md"),
            home_dir=bare_home,
        )
        assert ".agents/rules/universal-base.md" not in m_skip

        # Modify one fallback skill locally to prove user edits are NEVER pruned
        (proj / ".agents/skills/review/SKILL.md").write_text("# Custom user review\n", "utf-8")

        # Dry-run prune when $HOME is configured
        _, pr_dry = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=(),
            already_copied=(".agents/skills/sclose/SKILL.md",),
            home_dir=ready_home,
            dry_run=True,
        )
        assert "universal-base" in pr_dry
        assert "skill:sopen" in pr_dry
        assert "skill:sclose" not in pr_dry
        assert "skill:review" not in pr_dry
        assert (proj / ".agents/rules/universal-base.md").is_file()

        # Live prune when $HOME is configured (plus modified universal-base preservation check)
        _, pr_live = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=(),
            already_copied=(),
            home_dir=ready_home,
            dry_run=False,
        )
        # Assert
        assert "universal-base" in pr_live
        assert not (proj / ".agents/rules/universal-base.md").exists()
        assert not (proj / ".agents/skills/sopen").exists()
        assert (proj / ".agents/skills/review/SKILL.md").is_file()

        # Re-run when universal-base.md is already absent (exercises false branch)
        _, pr_noop = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=(),
            already_copied=(),
            home_dir=ready_home,
            dry_run=False,
        )
        assert pr_noop == []

        # Modified universal-base.md is preserved when $HOME becomes ready
        (proj / ".agents/rules").mkdir(parents=True, exist_ok=True)
        (proj / ".agents/rules/universal-base.md").write_text("# Custom local rule\n", "utf-8")
        _, pr_keep = baseline_fallback.reconcile_workspace_global_baseline(
            proj,
            engine_dir=eng,
            active_template_ids=(),
            already_copied=(),
            home_dir=ready_home,
            dry_run=False,
        )
        assert "universal-base" not in pr_keep
        assert (proj / ".agents/rules/universal-base.md").is_file()

    def test_scaffolder_and_horizon_standalone_fallback_zero_drift_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify standalone apply_templates_to_project + diff_project report 0 drift."""
        # Arrange
        proj = tmp_path / "solo-node"
        bare_home = tmp_path / "bare-home"
        proj.mkdir()
        bare_home.mkdir()
        scaffolder.configure_node_manifest(proj, layer_id="solo-node", layer_role="project")

        # Act
        res = scaffolder.apply_templates_to_project(
            proj, proj, template_ref="science-base", engine_dir=REPO_DIR, home_dir=bare_home
        )
        diff = horizon.diff_project_against_layers(proj, proj)

        # Assert
        assert ".agents/rules/universal-base.md" in res["files_materialized"]
        assert ".agents/skills/sopen/SKILL.md" in res["files_materialized"]
        assert diff["novel_in_project"] == []
        assert diff["modified_in_project"] == []
