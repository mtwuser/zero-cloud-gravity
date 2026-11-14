"""Implementation contract suite verifying 1:1:1 symmetry, metadata, links, and ecosystem purity.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    KEBAB_ID_RE,
    NODE_MANIFEST_CONTRACT_REV,
    REPO_DIR,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)
from zcg.core.manifests import discover_templates_catalog, parse_skill_frontmatter

MAX_SOURCE_LINES: int = 384
MAX_DOC_OR_TEST_LINES: int = 464
EXPECTED_SOURCE_MODULES: int = 74
EXPECTED_TEMPLATES_COUNT: int = 16
EXPECTED_GLOBAL_SKILLS_COUNT: int = 8
EXPECTED_SCREENSHOTS_COUNT: int = 10
PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"
EXPECTED_SCREENSHOT_DIMENSIONS: tuple[int, int] = (1680, 980)

_SPEC_LINE_RE = re.compile(r"^Specification:\s+(docs/architecture/\S+\.md)\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)")
_H5_HEADING_RE = re.compile(r"^#{5,}\s+", re.MULTILINE)
_RETIRED_TOKENS_RE = re.compile(
    r"\b(jira|confluence|aws|azure|angular|django|fastapi|dotfiles|legacy|sgarciag|bkfex)\b",
    re.IGNORECASE,
)


class TestRepoContracts:
    """Verify repository-wide 1:1:1 contracts, OSS metadata, size caps, and ecosystem purity."""

    def test_semver_oss_metadata_and_dockerfile_contracts_expected(self) -> None:
        """Verify SemVer synchronization, required OSS files, and non-root Dockerfile contract."""
        # Arrange
        version_txt = (REPO_DIR / "VERSION").read_text(encoding="utf-8").strip()
        pyproject = tomllib.loads((REPO_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        readme_txt = (REPO_DIR / "README.md").read_text(encoding="utf-8")
        changelog_txt = (REPO_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        dockerfile_txt = (REPO_DIR / "Dockerfile").read_text(encoding="utf-8")
        makefile_txt = (REPO_DIR / "Makefile").read_text(encoding="utf-8")

        required_files = (
            "VERSION",
            "LICENSE",
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "CODE_OF_CONDUCT.md",
            "ACCESSIBILITY.md",
            "Makefile",
            "Dockerfile",
            ".dockerignore",
            "install.sh",
            "scripts/verify-repo.sh",
            "scripts/install-antigravity.sh",
            "scripts/workstation-sync.sh",
            "scripts/workstation-backup.sh",
            "scripts/workstation-audit.sh",
            "scripts/workstation-restore.sh",
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "system/zcg-node.json",
            "antigravity/.local/share/applications/antigravity-agents.desktop",
            "antigravity/.local/share/applications/antigravity-ide.desktop",
            "docs/README.md",
            ".github/workflows/ci.yml",
            ".github/FUNDING.yml",
            ".github/FUNDING.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
        )

        # Act
        missing = [rel for rel in required_files if not (REPO_DIR / rel).is_file()]

        # Assert
        assert not missing, f"Missing required OSS files: {missing}"
        assert pyproject["project"]["version"] == version_txt
        assert pyproject["project"]["dependencies"] == []
        assert f"version-{version_txt}-" in readme_txt
        assert f"## [{version_txt}]" in changelog_txt
        assert "USER zcg" in dockerfile_txt
        assert "ZCG_NO_BROWSER=1" in dockerfile_txt
        assert 'ENTRYPOINT ["zcg-mcp"]' in dockerfile_txt
        assert "push-branch:" in makefile_txt
        assert "promote-master:" in makefile_txt
        assert "[OSS_DEV_ONLY_BLOCKED]" in makefile_txt
        assert "publish-oss:" in makefile_txt

    def test_one_to_one_to_one_spec_test_code_and_line_budgets_expected(self) -> None:
        """Verify 1:1:1 (Spec <-> Unit <-> Code) mapping, 0-byte __init__.py, and line caps."""
        # Arrange
        src_modules = sorted(
            p for p in (REPO_DIR / "src/zcg").rglob("*.py") if p.name != "__init__.py"
        )
        init_files = [
            *sorted((REPO_DIR / "src").rglob("__init__.py")),
            *sorted((REPO_DIR / "tests").rglob("__init__.py")),
        ]
        all_tests = [
            p for p in sorted((REPO_DIR / "tests").rglob("*.py")) if p.name != "__init__.py"
        ]

        # Act
        assert len(src_modules) == EXPECTED_SOURCE_MODULES
        non_empty_inits = [str(p.relative_to(REPO_DIR)) for p in init_files if p.stat().st_size > 0]
        assert not non_empty_inits, f"Non-empty __init__.py files: {non_empty_inits}"

        for mod_path in src_modules:
            rel_mod = mod_path.relative_to(REPO_DIR)
            mod_txt = mod_path.read_text(encoding="utf-8")
            mod_lines = len(mod_txt.splitlines())
            assert mod_lines <= MAX_SOURCE_LINES, f"{rel_mod} has {mod_lines} lines (> 384)"

            spec_match = _SPEC_LINE_RE.search(mod_txt)
            assert spec_match is not None, f"{rel_mod} lacks Specification: header"
            spec_rel = spec_match.group(1)
            spec_path = REPO_DIR / spec_rel
            assert spec_path.is_file(), f"{rel_mod} points to missing spec {spec_rel}"
            spec_txt = spec_path.read_text(encoding="utf-8")
            assert str(rel_mod) in spec_txt, f"{spec_rel} 1:1:1 table omits {rel_mod}"

            sub_rel = mod_path.relative_to(REPO_DIR / "src/zcg")
            unit_path = REPO_DIR / "tests/unit/zcg" / sub_rel.parent / f"test_{mod_path.name}"
            assert unit_path.is_file(), f"Missing 1:1 unit suite for {rel_mod}: {unit_path}"
            unit_spec = _SPEC_LINE_RE.search(unit_path.read_text(encoding="utf-8"))
            assert unit_spec is not None and unit_spec.group(1) == spec_rel

        # Assert
        for test_path in all_tests:
            t_lines = len(test_path.read_text(encoding="utf-8").splitlines())
            assert t_lines <= MAX_DOC_OR_TEST_LINES, f"{test_path} exceeds 464 lines ({t_lines})"

    def test_markdown_links_heading_depth_and_doc_budgets_expected(self) -> None:
        """Verify relative Markdown links resolve, 0 H5+ headings exist, and docs < 465 lines."""
        # Arrange
        md_files = [
            REPO_DIR / "README.md",
            REPO_DIR / "CHANGELOG.md",
            REPO_DIR / "CONTRIBUTING.md",
            REPO_DIR / "SECURITY.md",
            REPO_DIR / ".github/FUNDING.md",
            REPO_DIR / "CODE_OF_CONDUCT.md",
            REPO_DIR / "ACCESSIBILITY.md",
            *sorted((REPO_DIR / "docs").rglob("*.md")),
            *sorted((REPO_DIR / "templates").rglob("README.md")),
        ]
        broken_links: list[str] = []

        # Act
        for md_path in md_files:
            txt = md_path.read_text(encoding="utf-8")
            line_count = len(txt.splitlines())
            assert line_count <= MAX_DOC_OR_TEST_LINES, f"{md_path} has {line_count} lines"
            assert _H5_HEADING_RE.search(txt) is None, f"Forbidden ##### heading in {md_path}"
            # Strip fenced code blocks before extracting links
            clean_txt = re.sub(r"```[\s\S]*?```", "", txt)
            for match in _MD_LINK_RE.finditer(clean_txt):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "zcg://")):
                    continue
                resolved = (md_path.parent / target).resolve()
                if not resolved.exists():
                    broken_links.append(f"{md_path.relative_to(REPO_DIR)} -> {target}")

        # Assert
        assert not broken_links, f"Broken relative Markdown links: {broken_links}"

    def test_antigravity_hooks_skills_templates_and_ecosystem_purity_expected(self) -> None:
        """Verify AGENTS.md cap, hooks, 1:1 SKILL.md parity, 16 templates, and Google purity."""
        # Arrange
        agents_md = REPO_DIR / "antigravity/.gemini/config/AGENTS.md"
        hooks_json = json.loads(
            (REPO_DIR / "antigravity/.gemini/config/hooks.json").read_text(encoding="utf-8")
        )
        node_manifest = json.loads((REPO_DIR / "system/zcg-node.json").read_text(encoding="utf-8"))
        global_skills = sorted((REPO_DIR / "antigravity/.gemini/config/skills").glob("*/SKILL.md"))
        all_skills = [
            *global_skills,
            *sorted((REPO_DIR / "templates").rglob("SKILL.md")),
        ]
        tpl_catalog = discover_templates_catalog(REPO_DIR)

        # Act
        assert agents_md.is_file() and agents_md.stat().st_size <= AGENTS_MD_MAX_BYTES
        assert node_manifest["schema_version"] == NODE_MANIFEST_CONTRACT_REV
        assert len(global_skills) == EXPECTED_GLOBAL_SKILLS_COUNT
        assert len(tpl_catalog) == EXPECTED_TEMPLATES_COUNT
        assert len(node_manifest["default_stack_templates"]) == EXPECTED_TEMPLATES_COUNT
        assert len(list((REPO_DIR / "templates").glob("*/*/README.md"))) == EXPECTED_TEMPLATES_COUNT

        cfg_dir = REPO_DIR / "antigravity/.gemini/config"
        seen_events: set[str] = set()
        for group_map in hooks_json.values():
            for evt_name, entries in group_map.items():
                seen_events.add(evt_name)
                for item in entries:
                    for hook in item.get("hooks", [item]):
                        script_path = (cfg_dir / str(hook["command"]).split()[-1]).resolve()
                        assert script_path.is_file() and os.access(script_path, os.X_OK)
        assert seen_events == {"PreToolUse", "PostToolUse", "PostInvocation", "Stop"}

        for sk_path in all_skills:
            fm = parse_skill_frontmatter(sk_path, REPO_DIR)
            assert KEBAB_ID_RE.match(str(fm["name"]))
            assert fm["name"] == sk_path.parent.name
            assert len(sk_path.read_text(encoding="utf-8").splitlines()) <= MAX_DOC_OR_TEST_LINES

        for tpl_json in sorted((REPO_DIR / "templates").rglob("template.json")):
            t_doc = json.loads(tpl_json.read_text(encoding="utf-8"))
            assert t_doc["schema_version"] == TEMPLATE_MANIFEST_CONTRACT_REV
            if t_doc.get("stack_group") == "plugin-stack":
                p_dir = tpl_json.parent
                assert (p_dir / "web/templates/index.html").is_file()
                assert (p_dir / "web/templates/partials/overview.html").is_file()
                assert (p_dir / "web/static/css/plugin.css").is_file()
                assert (p_dir / "web/static/js/islands/plugin-island.js").is_file()
                assert bool(t_doc["runtime_service"].get("enabled_modules"))

        excluded_dirs = {
            ".git",
            ".venv",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
        }
        purity_hits: list[str] = []
        self_rel = Path("tests/imp/test_repo_contracts.py")
        for path in sorted(REPO_DIR.rglob("*")):
            if not path.is_file() or any(part in excluded_dirs for part in path.parts):
                continue
            rel = path.relative_to(REPO_DIR)
            if rel == self_rel:
                continue
            txt = path.read_text(encoding="utf-8", errors="ignore")
            if hit := _RETIRED_TOKENS_RE.search(txt):
                purity_hits.append(f"{rel}: {hit.group(0)!r}")
        # Assert
        assert not purity_hits, f"Retired non-Google / framework tokens detected: {purity_hits}"

    def test_perspective_screenshots_png_headers_and_dimensions_expected(self) -> None:
        """Verify all 10 [CAP-01..CAP-10] widescreen PNG captures exist and embed cleanly."""
        # Arrange
        shots_dir = REPO_DIR / "docs/assets/screenshots"
        expected_names = (
            "cap_01_individual_workstation_control_tower.png",
            "cap_02_school_student_study_cockpit.png",
            "cap_03_university_specialty_studio.png",
            "cap_04_scientific_and_public_knowledge_portal.png",
            "cap_05_small_startup_compact_hub.png",
            "cap_06_medium_scaleup_departmental_hub.png",
            "cap_07_large_regulated_enterprise_secops.png",
            "cap_08_network_of_networks_panoramic_synthesis.png",
            "cap_09_personal_work_and_spinout_studio.png",
            "cap_10_departmental_plugin_and_public_pro_portal.png",
        )
        guides_corpus = "\n".join(
            p.read_text(encoding="utf-8") for p in sorted((REPO_DIR / "docs/guides").glob("*.md"))
        )

        # Act
        actual_pngs = tuple(p.name for p in sorted(shots_dir.glob("cap_*.png")))
        dimensions = {
            name: struct.unpack(">II", (shots_dir / name).read_bytes()[16:24])
            for name in actual_pngs
        }

        # Assert
        assert len(actual_pngs) == EXPECTED_SCREENSHOTS_COUNT
        assert actual_pngs == expected_names
        for name in expected_names:
            raw = (shots_dir / name).read_bytes()
            assert raw.startswith(PNG_SIGNATURE), f"Invalid PNG signature in {name}"
            assert dimensions[name] == EXPECTED_SCREENSHOT_DIMENSIONS
            assert "![CAP-" in guides_corpus and name in guides_corpus

    def test_makefile_oss_dev_targets_positive_and_bipolar_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify push-branch and promote-master succeed on dev-<repo> and block unsafe scopes."""
        # Arrange
        dev_repo = tmp_path / "dev-iso-engine"
        pub_repo = tmp_path / "iso-engine"
        for repo_dir in (dev_repo, pub_repo):
            (repo_dir / "system").mkdir(parents=True)
            shutil.copy2(REPO_DIR / "Makefile", repo_dir / "Makefile")
            (repo_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (repo_dir / "src").symlink_to(REPO_DIR / "src", target_is_directory=True)
            (repo_dir / "system/zcg-node.json").write_text(
                json.dumps(
                    {
                        "schema_version": "zcg-node-v1",
                        "layer_id": "zero-cloud-gravity-workstation",
                        "layer_role": "workstation",
                        "entity_kind": "open-source",
                        "precedence": 10,
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-b", "master"], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "config", "user.email", "iso@example.org"], cwd=repo_dir, check=True
            )
            subprocess.run(["git", "config", "user.name", "ISO"], cwd=repo_dir, check=True)
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "chore: init"], cwd=repo_dir, check=True)

        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:iso-org/dev-iso-engine.git"],
            cwd=dev_repo,
            check=True,
        )
        make_cmd = ["make", f"PYTHON={sys.executable}", "DRY_RUN=1"]

        # Act
        master_err = subprocess.run(
            [*make_cmd, "push-branch"], cwd=dev_repo, capture_output=True, text=True
        )
        subprocess.run(["git", "checkout", "-b", "fix/iso-guard"], cwd=dev_repo, check=True)
        push_ok = subprocess.run(
            [*make_cmd, "push-branch"], cwd=dev_repo, capture_output=True, text=True
        )
        promo_ok = subprocess.run(
            [*make_cmd, "promote-master"], cwd=dev_repo, capture_output=True, text=True
        )
        non_dev_err = subprocess.run(
            [*make_cmd, "push-branch"], cwd=pub_repo, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "remote", "set-url", "origin", "git@github.com:iso-org/iso-engine.git"],
            cwd=dev_repo,
            check=True,
        )
        origin_err = subprocess.run(
            [*make_cmd, "push-branch"], cwd=dev_repo, capture_output=True, text=True
        )

        # Assert
        assert push_ok.returncode == 0 and "[push-branch DRY_RUN=1]" in push_ok.stdout
        assert promo_ok.returncode == 0 and "[promote-master DRY_RUN=1]" in promo_ok.stdout
        assert master_err.returncode != 0 and "[OSS_BRANCH_REQUIRED]" in master_err.stderr
        assert non_dev_err.returncode != 0 and "[OSS_DEV_ONLY_BLOCKED]" in non_dev_err.stderr
        assert origin_err.returncode != 0 and "[OSS_DEV_ORIGIN_MISMATCH]" in origin_err.stderr
