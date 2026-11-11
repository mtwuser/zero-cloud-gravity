"""Unit tests for zcg.core.manifests.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core import manifests
from zcg.core.constants import (
    MISSING_VERSION_SENTINEL,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)


class TestManifests:
    """Verify path containment, manifest loading, schema stamping, and template catalogs."""

    def test_ensure_contained_path_valid_and_traversal_violation_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify relative/absolute containment succeeds and parent escape raises ValueError."""
        # Arrange
        sub = tmp_path / "docs" / "spec.md"
        sub.parent.mkdir(parents=True)
        sub.write_text("# Spec\n", encoding="utf-8")

        # Act
        rel_ok = manifests.ensure_contained_path(Path("docs/spec.md"), tmp_path)
        abs_ok = manifests.ensure_contained_path(sub, tmp_path)

        # Assert
        assert rel_ok == sub.resolve()
        assert abs_ok == sub.resolve()
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            manifests.ensure_contained_path(Path("../escape.txt"), tmp_path)

    def test_version_os_container_and_sha256_helpers_cover_all_branches_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify version, OS release, container marker, and sha256 helpers across fallbacks."""
        # Arrange
        os_file = tmp_path / "os-release"
        os_file.write_text('NAME=Ubuntu\nPRETTY_NAME="Ubuntu 26.04 LTS"\n', encoding="utf-8")
        no_pretty = tmp_path / "os-minimal"
        no_pretty.write_text("ID=linux\n", encoding="utf-8")
        ver_dir = tmp_path / "ver_repo"
        ver_dir.mkdir()
        (ver_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        marker = tmp_path / ".dockerenv"
        marker.write_text("", encoding="utf-8")

        # Act
        ver_present = manifests.read_version(ver_dir)
        ver_missing = manifests.read_version(tmp_path)
        os_pretty = manifests.read_os_pretty_name(os_file)
        os_fb_missing = manifests.read_os_pretty_name(tmp_path / "absent")
        os_fb_nopretty = manifests.read_os_pretty_name(no_pretty)
        in_c = manifests.is_running_in_container(marker)
        out_c = manifests.is_running_in_container(tmp_path / "no-docker")
        digest = manifests.sha256_file(os_file)

        # Assert
        assert ver_present == "1.0.0"
        assert ver_missing == MISSING_VERSION_SENTINEL
        assert os_pretty == "Ubuntu 26.04 LTS"
        assert len(os_fb_missing) > 0
        assert os_fb_nopretty == os_fb_missing
        assert in_c is True and out_c is False
        assert len(digest) == 64

    def test_read_git_commit_handles_git_success_failure_oserror_and_missing_git_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify read_git_commit covers git rev-parse success, nonzero, OSError, and no git."""
        # Arrange
        monkeypatch.setenv("ZCG_GIT_COMMIT", "abc1234")

        # Act
        with patch("zcg.core.manifests.shutil.which", return_value=None):
            assert manifests.read_git_commit(tmp_path) == "abc1234"
            monkeypatch.delenv("ZCG_GIT_COMMIT", raising=False)
            assert manifests.read_git_commit(tmp_path) == "unknown"

        ok_proc = subprocess.CompletedProcess(["git"], 0, stdout="deadbeef\n", stderr="")
        bad_proc = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="err")
        # Assert
        with (
            patch("zcg.core.manifests.shutil.which", return_value="/usr/bin/git"),
            patch("zcg.core.manifests.subprocess.run", side_effect=[ok_proc, bad_proc, OSError()]),
        ):
            assert manifests.read_git_commit(tmp_path) == "deadbeef"
            assert manifests.read_git_commit(tmp_path) == "unknown"
            monkeypatch.setenv("ZCG_GIT_COMMIT", "fb99999")
            assert manifests.read_git_commit(tmp_path) == "fb99999"

    def test_load_node_manifest_and_is_oss_root_manifest_branches_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify load_node_manifest handles missing/list/dict files and OSS root detection."""
        # Arrange
        missing_m = manifests.load_node_manifest(tmp_path)
        m_path = tmp_path / NODE_MANIFEST_REL_PATH
        m_path.parent.mkdir(parents=True)
        m_path.write_text("[1, 2]", encoding="utf-8")
        list_m = manifests.load_node_manifest(tmp_path)
        m_path.write_text(
            json.dumps({"layer_id": "root", "layer_role": "workstation", "precedence": 10}),
            encoding="utf-8",
        )

        # Act
        dict_m = manifests.load_node_manifest(tmp_path)
        ind_m = {"layer_id": "user-pc", "layer_role": "workstation", "entity_kind": "individual"}
        high_prec_m = {"layer_id": "lab", "layer_role": "workstation", "precedence": 90}

        # Assert
        assert missing_m == {} and list_m == {}
        assert manifests.is_oss_root_manifest(dict_m) is True
        assert manifests.is_oss_root_manifest(ind_m) is False
        assert manifests.is_oss_root_manifest(high_prec_m) is False
        assert (
            manifests.is_oss_root_manifest({"layer_id": "d", "layer_role": "department"}) is False
        )

    def test_skill_and_rule_frontmatter_and_schema_stamping_expected(self, tmp_path: Path) -> None:
        """Verify SKILL.md parsing, rule frontmatter injection, and stale schema normalization."""
        # Arrange
        sk_with_fm = tmp_path / "skills" / "audit" / "SKILL.md"
        sk_with_fm.parent.mkdir(parents=True)
        sk_with_fm.write_text(
            '---\nname: "audit"\ndescription: "Run C2 audit"\n---\n# Body\n', encoding="utf-8"
        )
        sk_minimal_fm = tmp_path / "skills" / "minimal" / "SKILL.md"
        sk_minimal_fm.parent.mkdir(parents=True)
        sk_minimal_fm.write_text("---\ntrigger: manual\n---\n# Body\n", encoding="utf-8")
        sk_unclosed = tmp_path / "skills" / "raw" / "SKILL.md"
        sk_unclosed.parent.mkdir(parents=True)
        sk_unclosed.write_text("---\ntitle: only\n", encoding="utf-8")
        sk_plain = tmp_path / "skills" / "plain" / "SKILL.md"
        sk_plain.parent.mkdir(parents=True)
        sk_plain.write_text("", encoding="utf-8")

        rule_h1 = tmp_path / "rule_h1.md"
        rule_h1.write_text('Intro\n# Core "Rule"\nBody\n', encoding="utf-8")
        rule_no_h1 = tmp_path / "rule_plain.md"
        rule_no_h1.write_text("Plain text\n", encoding="utf-8")

        tpl_json = tmp_path / "templates" / "plugin-stack" / "demo" / "template.json"
        tpl_json.parent.mkdir(parents=True)
        tpl_json.write_text(
            json.dumps({"schema_version": "old", "kind": "invalid-kind", "target_role": "invalid"}),
            encoding="utf-8",
        )
        custom_json = tmp_path / "templates" / "custom" / "sub" / "template.json"
        custom_json.parent.mkdir(parents=True)
        custom_json.write_text("[1]", encoding="utf-8")
        valid_json = tmp_path / "valid.json"
        valid_json.write_text(
            json.dumps(
                {
                    "schema_version": TEMPLATE_MANIFEST_CONTRACT_REV,
                    "kind": "context-stack",
                    "target_role": "department",
                }
            ),
            encoding="utf-8",
        )
        node_json = tmp_path / "zcg-node.json"
        node_json.write_text(
            json.dumps({"layer_id": "demo", "schema_version": "old"}), encoding="utf-8"
        )
        ver_only_json = tmp_path / "ver-only.json"
        ver_only_json.write_text(
            json.dumps({"schema_version": "old", "kind": "context-stack", "target_role": "squad"}),
            encoding="utf-8",
        )

        # Act
        fm1 = manifests.parse_skill_frontmatter(sk_with_fm, tmp_path)
        fm_min = manifests.parse_skill_frontmatter(sk_minimal_fm, tmp_path)
        fm2 = manifests.parse_skill_frontmatter(sk_unclosed, tmp_path)
        fm3 = manifests.parse_skill_frontmatter(sk_plain, tmp_path)
        preview = manifests.ensure_rule_file_frontmatter(rule_no_h1, sync_in_place=False)
        synced = manifests.ensure_rule_file_frontmatter(rule_h1, sync_in_place=True)
        idempotent = manifests.ensure_rule_file_frontmatter(rule_h1, sync_in_place=True)
        no_stale = manifests.has_stale_schema(
            tmp_path / "none.json", TEMPLATE_MANIFEST_CONTRACT_REV
        )
        manifests.stamp_schema_rev(tpl_json, TEMPLATE_MANIFEST_CONTRACT_REV)
        manifests.stamp_schema_rev(custom_json, TEMPLATE_MANIFEST_CONTRACT_REV)
        manifests.stamp_schema_rev(valid_json, TEMPLATE_MANIFEST_CONTRACT_REV)
        manifests.stamp_schema_rev(node_json, NODE_MANIFEST_CONTRACT_REV)
        manifests.stamp_schema_rev(ver_only_json, TEMPLATE_MANIFEST_CONTRACT_REV)

        # Assert
        assert fm1["name"] == "audit" and fm1["description"] == "Run C2 audit"
        assert fm_min["name"] == "minimal" and fm_min["description"] == ""
        assert fm2["name"] == "raw" and fm3["line_count"] == 0
        assert "Governance rules for rule_plain" in preview
        assert rule_no_h1.read_text(encoding="utf-8") == "Plain text\n"
        assert "Core 'Rule'" in synced and idempotent == synced
        assert no_stale is False
        stamped_p = json.loads(tpl_json.read_text(encoding="utf-8"))
        stamped_c = json.loads(custom_json.read_text(encoding="utf-8"))
        stamped_n = json.loads(node_json.read_text(encoding="utf-8"))
        stamped_v = json.loads(ver_only_json.read_text(encoding="utf-8"))
        assert stamped_p["kind"] == "plugin-stack" and stamped_p["target_role"] == "squad"
        assert stamped_c["kind"] == "context-stack" and stamped_c["target_role"] == "department"
        assert stamped_n == {"layer_id": "demo", "schema_version": NODE_MANIFEST_CONTRACT_REV}
        assert stamped_v["schema_version"] == TEMPLATE_MANIFEST_CONTRACT_REV

    def test_template_discovery_and_dest_resolution_cover_all_layouts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify template iteration, resolution, destination paths, and mounted discovery."""
        # Arrange
        assert manifests.iter_layer_template_dirs(tmp_path) == []
        t_root = tmp_path / "templates"
        (t_root / ".hidden").mkdir(parents=True)
        (t_root / "README.txt").write_text("ignore file", encoding="utf-8")
        (t_root / "human-stack" / ".dot").mkdir(parents=True)
        hb = t_root / "human-stack" / "science-base"
        (hb / "rules").mkdir(parents=True)
        (hb / "rules" / "science-base.md").write_text("# Science\n", encoding="utf-8")
        (hb / "assets" / "sub").mkdir(parents=True)
        (hb / "assets" / "contract.json").write_text("{}", encoding="utf-8")
        (hb / "template.json").write_text(
            json.dumps({"kind": "human-stack", "target_role": "department"}), encoding="utf-8"
        )
        flat = t_root / "sovereign-pack"
        flat.mkdir()
        (flat / "template.json").write_text("[1]", encoding="utf-8")
        child = tmp_path / "layers" / "dept-a" / "templates" / "context-stack" / "dept-ops"
        child.mkdir(parents=True)

        # Act
        names = manifests.discover_layer_template_names(tmp_path)
        cat = manifests.discover_templates_catalog(
            tmp_path,
            [
                {"name": "dept-a", "relative_path": "layers/dept-a"},
                {"name": "skip", "relative_path": ""},
            ],
        )

        # Assert
        assert names == ["science-base", "sovereign-pack"]
        assert manifests.resolve_template_dir(tmp_path, "") is None
        assert manifests.resolve_template_dir(tmp_path, "human-stack") is None
        assert manifests.resolve_template_dir(tmp_path, "science-base") == hb
        assert (
            manifests.resolve_template_dest_dir(tmp_path, "new-a", src_tpl=hb).parent.name
            == "human-stack"
        )
        assert manifests.resolve_template_dest_dir(tmp_path, "science-base") == hb
        assert (
            manifests.resolve_template_dest_dir(tmp_path, "new-b", kind="plugin-stack").parent.name
            == "plugin-stack"
        )
        assert manifests.resolve_template_dest_dir(tmp_path, "new-c") == t_root / "new-c"
        assert len(cat) == 3

    def test_canonicalize_local_node_url_across_loopback_external_and_guards_expected(
        self,
    ) -> None:
        """Verify RFC 6761 *.localhost upgrade across loopback, external, and empty-port guards."""
        # Arrange
        raw_ext = "https://portal.example.org/docs"

        # Act
        empty_id = manifests.canonicalize_local_node_url("http://127.0.0.1:8786", node_id=" ")
        no_port = manifests.canonicalize_local_node_url("http://127.0.0.1", node_id="alex-tutor")
        ext = manifests.canonicalize_local_node_url(raw_ext, node_id="org-alpha")
        sub_dev = manifests.canonicalize_local_node_url(
            "http://127.0.0.1:8786",
            node_id="alex-tutor",
            local_dev_zone="alex-pc.localhost",
        )
        know_pro = manifests.canonicalize_local_node_url(
            "http://127.0.0.1:8720/?env=pro",
            node_id="org-alpha",
            layer_role="knowledge",
        )
        root_fb = manifests.canonicalize_local_node_url(
            "",
            node_id="alex-pc",
            layer_role="workstation",
            fallback_port=8790,
        )

        # Assert
        assert empty_id == "" and no_port == ""
        assert ext == "https://portal.example.org"
        assert sub_dev == "http://dev.alex-tutor.alex-pc.localhost:8786"
        assert know_pro == "http://org-alpha.localhost:8720"
        assert root_fb == "http://dev.alex-pc.localhost:8790"
