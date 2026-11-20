"""Unit tests for zcg.governance.runtime.node_updates.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.runtime import node_updates


def _write_manifest(node_dir: Path, payload: dict[str, Any]) -> None:
    m_path = node_dir / NODE_MANIFEST_REL_PATH
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_engine(engine_dir: Path, version: str, notes: dict[str, Any] | None = None) -> None:
    engine_dir.mkdir(parents=True, exist_ok=True)
    (engine_dir / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    _write_manifest(
        engine_dir,
        {
            "layer_id": "zero-cloud-gravity-workstation",
            "layer_role": "workstation",
            "entity_kind": "open-source",
            "precedence": 10,
        },
    )
    if notes is not None:
        n_path = engine_dir / node_updates.UPGRADE_NOTES_REL_PATH
        n_path.parent.mkdir(parents=True, exist_ok=True)
        n_path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")


class TestNodeUpdates:
    """Verify 1-hop sovereign node update planning, upgrade notes, and reconciliation prompts."""

    def test_parse_version_tuple_and_read_engine_version_expected(self, tmp_path: Path) -> None:
        """Verify 0-regex SemVer parsing and VERSION file fallback semantics."""
        # Arrange
        eng = tmp_path / "engine"
        eng.mkdir()

        # Act
        valid_tuples = [
            node_updates.parse_version_tuple("1.2.0"),
            node_updates.parse_version_tuple("v2.5"),
            node_updates.parse_version_tuple("V1.3.4-rc.1+sha"),
        ]
        bad_tuples = [
            node_updates.parse_version_tuple(bad)
            for bad in (None, "", "  ", "1", "1.2.3.4", "a.b.c")
        ]
        missing_ver = node_updates.read_engine_version(eng)
        (eng / "VERSION").write_text("   \n", encoding="utf-8")
        blank_ver = node_updates.read_engine_version(eng)
        (eng / "VERSION").write_text("1.2.0\n", encoding="utf-8")
        live_ver = node_updates.read_engine_version(eng)

        # Assert
        assert valid_tuples == [(1, 2, 0), (2, 5, 0), (1, 3, 4)]
        assert all(item is None for item in bad_tuples)
        assert missing_ver == "0.0.0"
        assert blank_ver == "0.0.0"
        assert live_ver == "1.2.0"

    def test_load_upgrade_notes_validation_sorting_and_normalization_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify schema validation, corrupt guards, invalid entry filtering, and SemVer sorting."""
        # Arrange
        eng = tmp_path / "engine"
        n_path = eng / node_updates.UPGRADE_NOTES_REL_PATH

        # Act — missing, invalid JSON, wrong schema_version
        assert node_updates.load_upgrade_notes(eng) == []
        n_path.parent.mkdir(parents=True)
        n_path.write_text("{bad-json", encoding="utf-8")
        assert node_updates.load_upgrade_notes(eng) == []
        n_path.write_text(json.dumps({"schema_version": "wrong", "releases": []}), encoding="utf-8")
        assert node_updates.load_upgrade_notes(eng) == []

        # Valid manifest with unsorted, guided, direct, and malformed release items
        n_path.write_text(
            json.dumps(
                {
                    "schema_version": node_updates.UPGRADE_NOTES_CONTRACT_REV,
                    "releases": [
                        "not-a-dict",
                        {"version": "invalid"},
                        {
                            "version": "1.2.0",
                            "reconciliation_level": "guided",
                            "title": "Guided Release",
                            "highlights": ["H1", "  "],
                            "reconciliation_steps": ["S1"],
                        },
                        {
                            "version": "1.1.0",
                            "reconciliation_level": "direct",
                            "title": "Direct Release",
                            "highlights": "non-list",
                            "reconciliation_steps": "non-list",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        loaded = node_updates.load_upgrade_notes(eng)

        # Assert
        assert [item["version"] for item in loaded] == ["1.1.0", "1.2.0"]
        assert loaded[0]["reconciliation_level"] == "direct"
        assert loaded[0]["highlights"] == []
        assert loaded[0]["reconciliation_steps"] == []
        assert loaded[1]["reconciliation_level"] == "guided"
        assert loaded[1]["highlights"] == ["H1"]
        assert loaded[1]["reconciliation_steps"] == ["S1"]

    def test_build_reconciliation_prompt_with_and_without_notes_expected(self) -> None:
        """Verify deterministic prompt generation with release notes and empty-notes fallback."""
        # Arrange
        notes = [
            {
                "version": "1.2.0",
                "title": "Root 0 Mesh",
                "highlights": ["6-pillar constellation"],
                "reconciliation_steps": ["Run make sync STRATEGY=reconcile"],
            }
        ]

        # Act
        with_notes = node_updates.build_reconciliation_prompt(
            layer_id="persona-profile",
            layer_role="workstation",
            update_source_kind="oss-engine",
            update_source_id="zero-cloud-gravity",
            node_version=None,
            target_version="1.2.0",
            sync_cmd="zcg workstation sync",
            release_notes=notes,
        )
        without_notes = node_updates.build_reconciliation_prompt(
            layer_id="squad-iso",
            layer_role="squad",
            update_source_kind="governing-parent",
            update_source_id="corp-iso",
            node_version="1.1.0",
            target_version="1.2.0",
            sync_cmd="make -C /ws sync STRATEGY=reconcile",
            release_notes=[],
        )

        # Assert
        assert "`unversioned`" in with_notes
        assert "### v1.2.0 — Root 0 Mesh" in with_notes
        assert "1. Run make sync STRATEGY=reconcile" in with_notes
        assert "templates/persona-profile/rules/persona-profile.md" in with_notes
        assert "`1.1.0`" in without_notes
        assert "## Release Highlights" not in without_notes

    def test_inspect_node_update_plan_oss_workstation_and_1hop_parent_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify OSS self, Root 0 workstation, and 1-hop governing-parent update cascades."""
        # Arrange
        eng = tmp_path / "zcg-engine"
        _write_engine(
            eng,
            "1.2.0",
            {
                "schema_version": node_updates.UPGRADE_NOTES_CONTRACT_REV,
                "releases": [
                    {
                        "version": "1.1.0",
                        "reconciliation_level": "direct",
                        "title": "Baseline 1.1",
                        "highlights": ["Base"],
                        "reconciliation_steps": ["Sync"],
                    },
                    {
                        "version": "1.2.0",
                        "reconciliation_level": "guided",
                        "title": "6-Pillar Mesh",
                        "highlights": ["Constellation"],
                        "reconciliation_steps": ["Reconcile"],
                    },
                ],
            },
        )

        # Act — 1. OSS engine inspecting itself
        oss_plan = node_updates.inspect_node_update_plan(eng, engine_dir=eng)
        assert oss_plan["contract_rev"] == node_updates.NODE_UPDATES_CONTRACT_REV
        assert oss_plan["update_source_kind"] == "oss-engine"
        assert oss_plan["node_engine_version"] == "1.2.0"
        assert oss_plan["update_available"] is False
        assert oss_plan["reconciliation_level"] == "direct"
        assert oss_plan["pending_releases"] == []
        assert oss_plan["commands"]["pull_oss"] == f"git -C {eng.resolve()} pull --ff-only"
        assert oss_plan["commands"]["sync_node"] == f"zcg sync-layer {eng.resolve()}"
        assert "### v1.2.0 — 6-Pillar Mesh" in oss_plan["reconciliation_prompt"]

        # 2. Personal Root 0 workstation (outdated 1.1.0 -> 1.2.0 guided, direct OSS 1-hop)
        profile = tmp_path / "persona-profile"
        _write_manifest(
            profile,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "precedence": 90,
                "engine_version": "1.1.0",
            },
        )
        ws_plan = node_updates.inspect_node_update_plan(profile, parent_dir=eng, engine_dir=eng)
        assert ws_plan["update_source_kind"] == "oss-engine"
        assert ws_plan["update_available"] is True
        assert ws_plan["reconciliation_level"] == "guided"
        assert [r["version"] for r in ws_plan["pending_releases"]] == ["1.2.0"]
        assert ws_plan["commands"]["sync_node"] == "zcg workstation sync"

        # 3. Child squad governed by outdated personal Root 0 parent (with Makefile)
        squad = tmp_path / "persona-work"
        _write_manifest(
            squad,
            {
                "layer_id": "persona-work",
                "layer_role": "squad",
                "entity_kind": "individual",
                "precedence": 87,
                "governing_root_id": "persona-profile",
                "engine_version": "1.0.0",
            },
        )
        (squad / "Makefile").write_text("sync:\n\t@true\n", encoding="utf-8")
        sq_plan = node_updates.inspect_node_update_plan(squad, parent_dir=profile, engine_dir=eng)
        assert sq_plan["update_source_kind"] == "governing-parent"
        assert sq_plan["update_source_id"] == "persona-profile"
        assert sq_plan["parent_engine_version"] == "1.1.0"
        assert sq_plan["parent_update_required_first"] is True
        assert sq_plan["parent_admin_url"].endswith("/admin?tab=runtime")
        assert sq_plan["target_version"] == "1.1.0"
        assert sq_plan["update_available"] is True
        assert sq_plan["reconciliation_level"] == "direct"
        assert sq_plan["commands"]["pull_oss"] == ""
        assert (
            sq_plan["commands"]["sync_node"] == f"make -C {squad.resolve()} sync STRATEGY=reconcile"
        )

        # 4. Parent upgraded to 1.2.0, child without Makefile -> --parent-dir sync command
        _write_manifest(
            profile,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "precedence": 90,
                "engine_version": "1.2.0",
            },
        )
        child_nomk = tmp_path / "persona-game"
        _write_manifest(
            child_nomk,
            {
                "layer_id": "persona-game",
                "layer_role": "squad",
                "entity_kind": "individual",
                "precedence": 89,
                "governing_root_id": "persona-profile",
            },
        )
        nomk_plan = node_updates.inspect_node_update_plan(
            child_nomk, parent_dir=profile, engine_dir=eng
        )
        assert nomk_plan["parent_update_required_first"] is False
        assert nomk_plan["node_engine_version"] is None
        assert nomk_plan["update_available"] is True
        assert (
            nomk_plan["commands"]["sync_node"]
            == f"zcg sync-layer {child_nomk.resolve()} --parent-dir {profile.resolve()}"
        )

        # 5. Engine without upgrade notes (empty parsed_notes)
        bare_eng = tmp_path / "bare-engine"
        _write_engine(bare_eng, "1.2.0", notes=None)
        bare_plan = node_updates.inspect_node_update_plan(child_nomk, engine_dir=bare_eng)

        # Assert
        assert bare_plan["pending_releases"] == []
        assert "## Release Highlights" not in bare_plan["reconciliation_prompt"]
