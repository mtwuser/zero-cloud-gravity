"""Implementation contract suite verifying 1:1:1 symmetry, metadata, links, and ecosystem purity.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    KEBAB_ID_RE,
    NODE_MANIFEST_CONTRACT_REV,
    REPO_DIR,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)
from zcg.core.manifests import discover_templates_catalog, parse_skill_frontmatter
from zcg.topology.identity import resolve_node_entity_identity

MAX_SOURCE_LINES: int = 384
MAX_DOC_OR_TEST_LINES: int = 464
EXPECTED_SOURCE_MODULES: int = 80
EXPECTED_TEMPLATES_COUNT: int = 16
EXPECTED_GLOBAL_SKILLS_COUNT: int = 8
EXPECTED_SCREENSHOTS_COUNT: int = 10
PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"
EXPECTED_SCREENSHOT_DIMENSIONS: tuple[int, int] = (1680, 980)

_SPEC_LINE_RE = re.compile(r"^Specification:\s+(docs/architecture/\S+\.md)\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)")
_H5_HEADING_RE = re.compile(r"^#{5,}\s+", re.MULTILINE)
_RETIRED_TOKENS_RE = re.compile(
    r"\b(jira|confluence|aws|azure|angular|django|fastapi|dotfiles|legacy|osa|sgarciag|bkfex)\b",
    re.IGNORECASE,
)


class TestRepoContracts:
    """Verify repository-wide 1:1:1 contracts, OSS metadata, size caps, and ecosystem purity."""

    def test_semver_oss_metadata_and_dockerfile_contracts_expected(self) -> None:
        """Verify SemVer synchronization, required OSS files, and non-root Dockerfile contract."""
        # Arrange
        version_txt = (REPO_DIR / "VERSION").read_text(encoding="utf-8").strip()
        pyproject = tomllib.loads((REPO_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        server_json = json.loads((REPO_DIR / "server.json").read_text(encoding="utf-8"))
        readme_txt = (REPO_DIR / "README.md").read_text(encoding="utf-8")
        changelog_txt = (REPO_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        dockerfile_txt = (REPO_DIR / "Dockerfile").read_text(encoding="utf-8")
        makefile_txt = (REPO_DIR / "Makefile").read_text(encoding="utf-8")
        oss_mk_txt = (REPO_DIR / "mk/oss-contrib.mk").read_text(encoding="utf-8")

        required_files = (
            "VERSION", "LICENSE", "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
            "CODE_OF_CONDUCT.md", "ACCESSIBILITY.md", "Makefile", "mk/oss-contrib.mk",
            "Dockerfile", ".dockerignore", "install.sh", "scripts/verify-repo.sh",
            "scripts/install-antigravity.sh", "scripts/workstation-sync.sh",
            "scripts/workstation-backup.sh", "scripts/workstation-audit.sh",
            "scripts/workstation-restore.sh", "scripts/stage-showcase.sh", "pyproject.toml",
            "requirements.txt", "requirements-dev.txt", "server.json", "system/zcg-node.json",
            "antigravity/.local/share/applications/antigravity-agents.desktop",
            "antigravity/.local/share/applications/antigravity-ide.desktop", "docs/README.md",
            ".github/workflows/ci.yml", ".github/FUNDING.yml",
            ".github/FUNDING.md", ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml", ".github/DISCUSSION_TEMPLATE/q-a.yml",
            ".github/DISCUSSION_TEMPLATE/ideas.yml",
        )  # fmt: skip

        # Act
        missing = [rel for rel in required_files if not (REPO_DIR / rel).is_file()]
        is_dev_clone = (
            resolve_node_entity_identity(REPO_DIR).get("visibility_scope")
            == "private:open-source:dev"
        )

        # Assert
        assert not missing, f"Missing required OSS files: {missing}"
        assert not is_dev_clone or (REPO_DIR / ".github/dependabot.yml").is_file()
        assert pyproject["project"]["version"] == version_txt
        assert server_json["version"] == version_txt
        assert server_json["packages"][0]["version"] == version_txt
        assert "<!-- mcp-name: io.github.mtwuser/zero-cloud-gravity -->" in readme_txt
        assert pyproject["project"]["dependencies"] == []
        assert f"version-{version_txt}-" in readme_txt
        assert f"## [{version_txt}]" in changelog_txt
        assert "USER zcg" in dockerfile_txt
        assert "ZCG_NO_BROWSER=1" in dockerfile_txt
        assert 'ENTRYPOINT ["zcg-mcp"]' in dockerfile_txt
        assert "-include mk/oss-contrib.mk" in makefile_txt
        assert "push-branch:" not in makefile_txt and "publish-oss:" not in makefile_txt
        assert "oss-push-branch:" in oss_mk_txt
        assert "oss-promote-master:" in oss_mk_txt
        assert "oss-publish:" in oss_mk_txt

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
        """Verify Markdown links, 0 H5+ headings, < 465-line caps, and CLI walkthrough flags."""
        # Arrange
        md_files = [
            REPO_DIR / "README.md", REPO_DIR / "CHANGELOG.md", REPO_DIR / "CONTRIBUTING.md",
            REPO_DIR / "SECURITY.md", REPO_DIR / ".github/FUNDING.md",
            REPO_DIR / "CODE_OF_CONDUCT.md", REPO_DIR / "ACCESSIBILITY.md",
            *sorted((REPO_DIR / "docs").rglob("*.md")),
            *sorted((REPO_DIR / "templates").rglob("README.md")),
        ]  # fmt: skip
        global_flags = {"--dry-run", "--json", "--help", "--version", "--repo-dir"}
        cli_flags: dict[str, set[str]] = {}
        fallbacks = {
            "dispatch_c1": ("consult-layer",), "dispatch_c2": ("register-subtree",),
            "dispatch_c3": ("record-decision",), "dispatch_oss": ("oss",),
            "dispatch_subtree": ("subtree", "subtree-list", "subtree-pull-all"),
        }  # fmt: skip

        def _strs(nodes: Sequence[ast.AST], rx: str = "") -> list[str]:
            vals = [
                c.value
                for root in nodes
                for c in ast.walk(root)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            ]
            return [v for v in vals if not rx or re.fullmatch(rx, v)]

        for cli_py in ("src/zcg/cli/discovery.py", "src/zcg/cli/commands.py"):
            tree = ast.parse((REPO_DIR / cli_py).read_text("utf-8"))
            for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
                rem = [s for s in fn.body if not isinstance(s, ast.If)]
                for stmt in (s for s in fn.body if isinstance(s, ast.If)):
                    fl = set(_strs(stmt.body, r"--[a-z0-9-]+"))
                    for nm in _strs([stmt.test]):
                        cli_flags.setdefault(nm, set()).update(fl)
                fb_fl = set(_strs(rem, r"--[a-z0-9-]+"))
                for nm in fallbacks.get(fn.name, ()):
                    cli_flags.setdefault(nm, set()).update(fb_fl)
        for sh in (REPO_DIR / "scripts").glob("*.sh"):
            cli_flags[sh.stem] = set(re.findall(r"--[a-z][a-z0-9-]*", sh.read_text("utf-8")))
        broken_links, bad_cli_flags = list[str](), list[str]()

        # Act
        for md_path in md_files:
            txt = md_path.read_text(encoding="utf-8")
            line_count = len(txt.splitlines())
            assert line_count <= MAX_DOC_OR_TEST_LINES, f"{md_path} has {line_count} lines"
            assert _H5_HEADING_RE.search(txt) is None, f"Forbidden ##### heading in {md_path}"
            rel_md = md_path.relative_to(REPO_DIR)
            for block in re.findall(r"```(?:bash|sh)\n([\s\S]*?)```", txt):
                for ln in re.sub(r"\\\n\s*", " ", block).splitlines():
                    s = ln.split("#", 1)[0].strip()
                    if m := re.match(r"^(?:~/.local/bin/)?zcg\s+([a-z][a-z0-9-]*)\b(.*)$", s):
                        sub, rest_s = m.group(1), m.group(2)
                        allowed = cli_flags.get(sub, set()) | global_flags
                        bad_cli_flags.extend(
                            f"{rel_md}: zcg {sub} {flg}"
                            for flg in re.findall(r"(?<!\S)(--[a-z][a-z0-9-]*)", rest_s)
                            if flg not in allowed
                        )
            clean_txt = re.sub(r"```[\s\S]*?```", "", txt)
            for match in _MD_LINK_RE.finditer(clean_txt):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "zcg://")):
                    continue
                if not (md_path.parent / target).resolve().exists():
                    broken_links.append(f"{rel_md} -> {target}")

        # Assert
        assert not broken_links, f"Broken relative Markdown links: {broken_links}"
        assert not bad_cli_flags, f"Invalid CLI subcommand flags in docs: {bad_cli_flags}"

    def test_antigravity_hooks_skills_templates_and_ecosystem_purity_expected(self) -> None:
        """Verify AGENTS.md cap, hooks, 1:1 SKILL.md parity, 16 templates, and Google purity."""
        # Arrange
        cfg_dir = REPO_DIR / "antigravity/.gemini/config"
        agents_md = cfg_dir / "AGENTS.md"
        hooks_json = json.loads((cfg_dir / "hooks.json").read_text(encoding="utf-8"))
        node_manifest = json.loads((REPO_DIR / "system/zcg-node.json").read_text(encoding="utf-8"))
        global_skills = sorted((cfg_dir / "skills").glob("*/SKILL.md"))
        all_skills = [*global_skills, *sorted((REPO_DIR / "templates").rglob("SKILL.md"))]
        tpl_catalog = discover_templates_catalog(REPO_DIR)

        # Act
        assert agents_md.is_file() and agents_md.stat().st_size <= AGENTS_MD_MAX_BYTES
        assert node_manifest["schema_version"] == NODE_MANIFEST_CONTRACT_REV
        assert len(global_skills) == EXPECTED_GLOBAL_SKILLS_COUNT
        assert len(tpl_catalog) == EXPECTED_TEMPLATES_COUNT
        assert len(node_manifest["default_stack_templates"]) == EXPECTED_TEMPLATES_COUNT
        assert len(list((REPO_DIR / "templates").glob("*/*/README.md"))) == EXPECTED_TEMPLATES_COUNT

        seen_events: set[str] = set()
        for group_map in hooks_json.values():
            for evt_name, entries in group_map.items():
                seen_events.add(evt_name)
                for item in entries:
                    for hook in item.get("hooks", [item]):
                        script_path = (cfg_dir / str(hook["command"]).split()[-1]).resolve()
                        assert script_path.is_file() and os.access(script_path, os.X_OK)
        assert seen_events == {
            "SessionStart", "PreToolUse", "PostToolUse", "PostInvocation", "Stop",
        }  # fmt: skip
        sess_res = subprocess.run(
            [sys.executable, str(cfg_dir / "scripts/session_start_orientation.py")],
            input=json.dumps({"cwd": str(REPO_DIR)}), capture_output=True, text=True, check=True,
        )  # fmt: skip
        stop_res = subprocess.run(
            [sys.executable, str(cfg_dir / "scripts/stop_verify_tests.py")],
            input=json.dumps({"continuationActive": True}),
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        assert "injectSteps" in json.loads(sess_res.stdout)
        assert json.loads(stop_res.stdout) == {"decision": "stop"}

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

        excl = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
        binary_exts = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2"}
        purity_hits: list[str] = []
        self_rel = Path("tests/imp/test_repo_contracts.py")
        for path in sorted(REPO_DIR.rglob("*")):
            if (
                not path.is_file()
                or path.suffix.lower() in binary_exts
                or any(part in excl for part in path.parts)
            ):
                continue
            rel = path.relative_to(REPO_DIR)
            hit = _RETIRED_TOKENS_RE.search(path.read_text("utf-8", "ignore"))
            if rel != self_rel and hit:
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
        """Verify oss-* targets conditionally appear in help and enforce dev-<repo> guards."""
        # Arrange
        dev_repo = tmp_path / "dev-iso-engine"
        pub_repo = tmp_path / "iso-engine"
        node_doc = json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "zero-cloud-gravity-workstation",
                "layer_role": "workstation",
                "entity_kind": "open-source",
                "precedence": 10,
            }
        )
        for repo_dir in (dev_repo, pub_repo):
            (repo_dir / "system").mkdir(parents=True)
            (repo_dir / "mk").mkdir(parents=True)
            shutil.copy2(REPO_DIR / "Makefile", repo_dir / "Makefile")
            shutil.copy2(REPO_DIR / "mk/oss-contrib.mk", repo_dir / "mk/oss-contrib.mk")
            (repo_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (repo_dir / "src").symlink_to(REPO_DIR / "src", target_is_directory=True)
            (repo_dir / "system/zcg-node.json").write_text(node_doc, encoding="utf-8")
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

        def _mk(cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([*make_cmd, *extra], cwd=cwd, capture_output=True, text=True)

        # Act
        pub_help = _mk(pub_repo, "help")
        pub_help_oss = _mk(pub_repo, "OSS_CONTRIB=1", "help")
        dev_help = _mk(dev_repo, "help")
        master_err = _mk(dev_repo, "oss-push-branch")
        subprocess.run(["git", "checkout", "-b", "fix/iso-guard"], cwd=dev_repo, check=True)
        push_ok = _mk(dev_repo, "oss-push-branch")
        promo_ok = _mk(dev_repo, "oss-promote-master")
        non_dev_err = _mk(pub_repo, "oss-push-branch")
        subprocess.run(
            ["git", "remote", "set-url", "origin", "git@github.com:iso-org/iso-engine.git"],
            cwd=dev_repo,
            check=True,
        )
        origin_err = _mk(dev_repo, "oss-push-branch")

        # Assert
        assert "oss-push-branch" not in pub_help.stdout
        assert "oss-push-branch" in pub_help_oss.stdout and "oss-push-branch" in dev_help.stdout
        assert push_ok.returncode == 0 and "[oss-push-branch DRY_RUN=1]" in push_ok.stdout
        assert promo_ok.returncode == 0 and "[oss-promote-master DRY_RUN=1]" in promo_ok.stdout
        assert master_err.returncode != 0 and "[OSS_BRANCH_REQUIRED]" in master_err.stderr
        assert non_dev_err.returncode != 0 and "[OSS_DEV_ONLY_BLOCKED]" in non_dev_err.stderr
        assert origin_err.returncode != 0 and "[OSS_DEV_ORIGIN_MISMATCH]" in origin_err.stderr

    def test_installer_ephemeral_archive_and_showcase_stager_contracts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify install-antigravity --from-archive hygiene and stage-showcase dry-run."""
        # Arrange
        dl_dir = tmp_path / "Downloads"
        dl_dir.mkdir()
        dest_dir = tmp_path / "opt-ide"
        src_bundle = tmp_path / "pkg/Antigravity IDE"
        (src_bundle / "resources/app").mkdir(parents=True)
        (src_bundle / "antigravity-ide").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (src_bundle / "resources/app/package.json").write_text(
            json.dumps({"version": "2.32.1"}), encoding="utf-8"
        )
        archive_path = tmp_path / "manual-ide-2.32.1.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(src_bundle, arcname="Antigravity IDE")
        inst_env = {
            **os.environ,
            "ANTIGRAVITY_DOWNLOADS_DIR": str(dl_dir),
            "ANTIGRAVITY_IDE_DEST": str(dest_dir),
        }
        inst_sh = str(REPO_DIR / "scripts/install-antigravity.sh")
        show_sh = str(REPO_DIR / "scripts/stage-showcase.sh")
        show_dir = tmp_path / "zcg-showcase"

        # Act
        ambig_err = subprocess.run(
            [inst_sh, "--from-archive", str(archive_path)],
            env=inst_env, capture_output=True, text=True,
        )  # fmt: skip
        offline_ok = subprocess.run(
            [inst_sh, "--ide", "--from-archive", str(archive_path)],
            env=inst_env, capture_output=True, text=True,
        )  # fmt: skip
        dry_showcase = subprocess.run(
            [show_sh, "--dry-run", "--dir", str(show_dir)], capture_output=True, text=True
        )
        status_showcase = subprocess.run(
            [show_sh, "--status", "--dir", str(show_dir)], capture_output=True, text=True
        )

        # Assert
        assert ambig_err.returncode != 0
        assert offline_ok.returncode == 0
        assert list(dl_dir.iterdir()) == []
        assert archive_path.is_file()
        assert (dest_dir / ".installed-version").read_text(encoding="utf-8").strip() == "2.32.1"
        assert dry_showcase.returncode == 0 and "[CAP-01]" in dry_showcase.stdout
        assert "[CAP-10]" in dry_showcase.stdout and not show_dir.exists()
        assert status_showcase.returncode == 0 and "not staged" in status_showcase.stdout.lower()
