"""Implementation contract suite verifying 1:1:1 symmetry, metadata, links, and ecosystem purity.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import ast
import json
import os
import struct
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from zcg.cockpit.views.dashboard_app import ARCHETYPE_DEFAULT_MODULES
from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    BASE_SKILL_TAXONOMY,
    NODE_MANIFEST_CONTRACT_REV,
    REPO_DIR,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import discover_templates_catalog, parse_skill_frontmatter
from zcg.core.markdown_scan import contains_token_id, extract_markdown_links, iter_unfenced_lines
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.posture import VALID_SETUP_PURPOSES

MAX_SOURCE_LINES: int = 384
MAX_DOC_OR_TEST_LINES: int = 464
EXPECTED_SOURCE_MODULES: int = 143
EXPECTED_TEMPLATES_COUNT: int = 19
EXPECTED_GLOBAL_SKILLS_COUNT: int = 8
EXPECTED_SCREENSHOTS_COUNT: int = 10
PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"
EXPECTED_SCREENSHOT_DIMENSIONS: tuple[int, int] = (1680, 980)
_RETIRED_TOKENS: tuple[str, ...] = (
    "jira", "confluence", "aws", "azure", "angular", "django",
    "fastapi", "dotfiles", "legacy", "osa", "sgarciag", "bkfex", "skillspector", "alex",
)  # fmt: skip


def _extract_spec_header(txt: str) -> str | None:
    for ln in txt.splitlines():
        if ln.startswith("Specification:"):
            val = ln.removeprefix("Specification:").strip()
            if val.startswith("docs/architecture/") and val.endswith(".md") and " " not in val:
                return val
    return None


def _iter_shell_commands(md_txt: str) -> list[str]:
    cmds, in_sh, buf = list[str](), False, ""
    for raw in md_txt.splitlines():
        st = raw.strip()
        if not in_sh:
            in_sh = st in ("```bash", "```sh")
        elif st == "```":
            in_sh, buf = False, ""
        elif raw.endswith("\\"):
            buf += raw[:-1] + " "
        else:
            full = (buf + raw).split("#", 1)[0].strip()
            buf = ""
            if full:
                cmds.append(full)
    return cmds


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

        required_files = (
            "VERSION", "LICENSE", "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
            "CODE_OF_CONDUCT.md", "ACCESSIBILITY.md", "Makefile",
            "Dockerfile", ".dockerignore", "install.sh", "scripts/verify-repo.sh",
            "scripts/install-antigravity.sh", "scripts/workstation-sync.sh",
            "scripts/workstation-backup.sh", "scripts/workstation-audit.sh",
            "scripts/workstation-restore.sh", "scripts/stage-showcase.sh", "pyproject.toml",
            "requirements.txt", "requirements-dev.txt", "server.json", "system/zcg-node.json",
            "antigravity/.local/share/applications/antigravity-agents.desktop",
            "antigravity/.local/share/applications/antigravity-ide.desktop", "docs/README.md",
            "docs/WHITEPAPER.md", "docs/assets/diagrams/01_four_stack_triadic_architecture.svg",
            "docs/assets/diagrams/02_capability_rings_and_oidc_tls_plane.svg",
            "docs/assets/diagrams/03_v1_to_v2_cryptographic_bridge.svg",
            ".github/workflows/ci.yml", ".github/workflows/cd-environments.yml",
            ".github/FUNDING.yml", ".github/FUNDING.md", ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml", ".github/DISCUSSION_TEMPLATE/q-a.yml",
            ".github/DISCUSSION_TEMPLATE/ideas.yml", ".github/workflows/publish-mcp.yml",
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
        assert not (REPO_DIR / "mk").exists()
        assert not (REPO_DIR / "templates/framework-stack").exists()
        assert not any(
            ln.startswith(("push-branch:", "promote-master:", "publish-oss:"))
            for ln in makefile_txt.splitlines()
        )
        assert "oss-push-branch:" in makefile_txt
        assert "oss-promote-master:" in makefile_txt
        assert "oss-publish:" in makefile_txt

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

            spec_rel = _extract_spec_header(mod_txt)
            assert spec_rel is not None, f"{rel_mod} lacks Specification: header"
            spec_path = REPO_DIR / spec_rel
            assert spec_path.is_file(), f"{rel_mod} points to missing spec {spec_rel}"
            spec_txt = spec_path.read_text(encoding="utf-8")
            assert str(rel_mod) in spec_txt, f"{spec_rel} 1:1:1 table omits {rel_mod}"

            sub_rel = mod_path.relative_to(REPO_DIR / "src/zcg")
            unit_path = REPO_DIR / "tests/unit/zcg" / sub_rel.parent / f"test_{mod_path.name}"
            assert unit_path.is_file(), f"Missing 1:1 unit suite for {rel_mod}: {unit_path}"
            unit_rel = unit_path.relative_to(REPO_DIR)
            assert str(unit_rel) in spec_txt, f"{spec_rel} 1:1:1 table omits {unit_rel}"
            assert _extract_spec_header(unit_path.read_text(encoding="utf-8")) == spec_rel

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

        def _strs(nodes: Sequence[ast.AST], *, flags_only: bool = False) -> list[str]:
            vals = [
                c.value
                for root in nodes
                for c in ast.walk(root)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            ]
            return [
                v for v in vals if not flags_only or (v.startswith("--") and is_kebab_id(v[2:]))
            ]

        for cli_py in ("src/zcg/cli/discovery.py", "src/zcg/cli/commands.py"):
            tree = ast.parse((REPO_DIR / cli_py).read_text("utf-8"))
            for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
                rem = [s for s in fn.body if not isinstance(s, ast.If)]
                for stmt in (s for s in fn.body if isinstance(s, ast.If)):
                    fl = set(_strs(stmt.body, flags_only=True))
                    for nm in _strs([stmt.test]):
                        cli_flags.setdefault(nm, set()).update(fl)
                fb_fl = set(_strs(rem, flags_only=True))
                for nm in fallbacks.get(fn.name, ()):
                    cli_flags.setdefault(nm, set()).update(fb_fl)
        for sh in (REPO_DIR / "scripts").glob("*.sh"):
            sh_norm = "".join(
                c if (c.isascii() and (c.islower() or c.isdigit() or c == "-")) else " "
                for c in sh.read_text("utf-8")
            )
            cli_flags[sh.stem] = {
                w for w in sh_norm.split() if w.startswith("--") and is_kebab_id(w[2:])
            }
        broken_links, bad_cli_flags, stale_py_refs, bad_purposes = (
            list[str](),
            list[str](),
            list[str](),
            list[str](),
        )

        # Act
        for md_path in md_files:
            txt = md_path.read_text(encoding="utf-8")
            line_count = len(txt.splitlines())
            assert line_count <= MAX_DOC_OR_TEST_LINES, f"{md_path} has {line_count} lines"
            assert not any(
                (hl := len(ln) - len(ln.lstrip("#"))) >= 5 and ln[hl : hl + 1].isspace()
                for ln in txt.splitlines()
            ), f"Forbidden ##### heading in {md_path}"
            rel_md = md_path.relative_to(REPO_DIR)
            if md_path.name != "CHANGELOG.md":
                norm = txt.translate(str.maketrans("`|()[]", "      "))
                for raw_tok in norm.split():
                    cand = raw_tok.rstrip(".,:;").removeprefix("../../").removeprefix("../")
                    if (
                        cand.startswith(("src/zcg/", "tests/"))
                        and cand.endswith(".py")
                        and not any(ch in cand for ch in ("*", "<", "{"))
                        and not (REPO_DIR / cand).is_file()
                    ):
                        stale_py_refs.append(f"{rel_md} -> {cand}")
            for cmd in _iter_shell_commands(txt):
                parts = cmd.split()
                if (
                    len(parts) >= 2
                    and parts[0] in ("zcg", "~/.local/bin/zcg")
                    and is_kebab_id(parts[1])
                ):
                    sub, allowed = parts[1], cli_flags.get(parts[1], set()) | global_flags
                    bad_cli_flags.extend(
                        f"{rel_md}: zcg {sub} {flg}"
                        for tok in parts[2:]
                        if (flg := tok.partition("=")[0]).startswith("--")
                        and is_kebab_id(flg[2:])
                        and flg not in allowed
                    )
            if md_path == REPO_DIR / "README.md" or md_path.parent == REPO_DIR / "docs/guides":
                p_toks = txt.translate(str.maketrans("`|()[]\"'", "        ")).split()
                for idx, tok in enumerate(p_toks):
                    val = (
                        tok.partition("=")[2]
                        if tok.startswith("--purpose=")
                        else (
                            p_toks[idx + 1] if tok == "--purpose" and idx + 1 < len(p_toks) else ""
                        )
                    ).rstrip(".,:;\\")
                    if (
                        val
                        and val[0].isalnum()
                        and not any(c in val for c in "<>[]/")
                        and val not in VALID_SETUP_PURPOSES
                    ):
                        bad_purposes.append(f"{rel_md}: --purpose {val}")
            unfenced = "\n".join(ln for _, ln in iter_unfenced_lines(txt))
            for _, raw_target in extract_markdown_links(unfenced):
                target = raw_target.partition("#")[0]
                if (
                    not target
                    or any(c.isspace() for c in target)
                    or target.startswith(("http://", "https://", "mailto:", "zcg://"))
                ):
                    continue
                if not (md_path.parent / target).resolve().exists():
                    broken_links.append(f"{rel_md} -> {target}")

        # Assert
        assert not broken_links, f"Broken relative Markdown links: {broken_links}"
        assert not bad_cli_flags, f"Invalid CLI subcommand flags in docs: {bad_cli_flags}"
        assert not stale_py_refs, f"Stale .py references in docs: {stale_py_refs}"
        assert not bad_purposes, f"Invalid --purpose tokens in docs: {bad_purposes}"

    def test_antigravity_hooks_skills_templates_and_ecosystem_purity_expected(self) -> None:
        """Verify AGENTS.md cap, hooks, 1:1 SKILL.md parity, 19 templates, and Google purity."""
        # Arrange
        cfg_dir = REPO_DIR / "antigravity/.gemini/config"
        agents_md = cfg_dir / "AGENTS.md"
        hooks_json = json.loads((cfg_dir / "hooks.json").read_text(encoding="utf-8"))
        node_manifest = json.loads((REPO_DIR / "system/zcg-node.json").read_text(encoding="utf-8"))
        upgrade_notes_path = REPO_DIR / "system/upgrade-notes.json"
        global_skills = sorted((cfg_dir / "skills").glob("*/SKILL.md"))
        all_skills = [*global_skills, *sorted((REPO_DIR / "templates").rglob("SKILL.md"))]
        tpl_catalog = discover_templates_catalog(REPO_DIR)

        # Act
        assert agents_md.is_file() and agents_md.stat().st_size <= AGENTS_MD_MAX_BYTES
        assert node_manifest["schema_version"] == NODE_MANIFEST_CONTRACT_REV
        assert upgrade_notes_path.is_file()
        upgrade_notes = json.loads(upgrade_notes_path.read_text(encoding="utf-8"))
        assert upgrade_notes["schema_version"] == "zcg-upgrade-notes-v1"
        assert isinstance(upgrade_notes.get("releases"), list) and upgrade_notes["releases"]
        assert len(global_skills) == EXPECTED_GLOBAL_SKILLS_COUNT
        assert len(tpl_catalog) == EXPECTED_TEMPLATES_COUNT
        assert {
            d["template_name"]: tuple(d["associated_global_skills"])
            for d in tpl_catalog
            if d["kind"] == "human-stack"
        } == BASE_SKILL_TAXONOMY
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
        sess_doc = json.loads(sess_res.stdout)
        assert "injectSteps" in sess_doc
        sess_pin = sess_doc["injectSteps"][0]["systemMessage"]["metadata"]["session_pin"]
        assert sess_pin["schema_version"] == "zcg-session-pin-v1"
        assert len(sess_pin["rules_merkle_digest"]) == 16
        assert json.loads(stop_res.stdout) == {"decision": "stop"}

        for sk_path in all_skills:
            fm = parse_skill_frontmatter(sk_path, REPO_DIR)
            assert is_kebab_id(str(fm["name"]))
            assert fm["name"] == sk_path.parent.name
            assert len(sk_path.read_text(encoding="utf-8").splitlines()) <= MAX_DOC_OR_TEST_LINES

        pack_arch_map = {
            "tutor-study-cockpit": "academic-tutor-cockpit",
            "node-work-cockpit": "departmental-ops-cockpit",
        }
        for tpl_json in sorted((REPO_DIR / "templates").rglob("template.json")):
            t_doc = json.loads(tpl_json.read_text(encoding="utf-8"))
            assert t_doc["schema_version"] == TEMPLATE_MANIFEST_CONTRACT_REV
            if t_doc.get("stack_group") == "plugin-stack":
                p_dir = tpl_json.parent
                sc_doc = json.loads((p_dir / "assets/service_contract.json").read_text("utf-8"))
                arch_key = pack_arch_map.get(p_dir.name, p_dir.name)
                expected_mods = list(ARCHETYPE_DEFAULT_MODULES[arch_key])
                assert (p_dir / "web/templates/index.html").is_file()
                assert (p_dir / "web/templates/partials/overview.html").is_file()
                assert (p_dir / "web/static/css/plugin.css").is_file()
                assert (p_dir / "web/static/js/islands/plugin-island.js").is_file()
                assert t_doc["runtime_service"]["enabled_modules"] == expected_mods
                assert sc_doc["enabled_modules"] == expected_mods

        excl = {
            ".git", ".venv", ".zcg", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        }  # fmt: skip
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
            low_txt = path.read_text("utf-8", "ignore").lower()
            hit = next(
                (
                    tok
                    for tok in _RETIRED_TOKENS
                    if tok in low_txt and contains_token_id(low_txt, tok)
                ),
                None,
            )
            if rel != self_rel and hit is not None:
                purity_hits.append(f"{rel}: {hit!r}")
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
