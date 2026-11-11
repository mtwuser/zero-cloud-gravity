"""Unit tests for zcg.governance.arch_linter.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core.constants import NODE_MANIFEST_REL_PATH, REPO_DIR
from zcg.governance.arch_linter import (
    check_domain_module,
    check_test_suite,
    lint_architecture,
)


class TestArchLinter:
    """Verify AST Hexagonal Functional Core isolation, excluded contexts, and 1:1:1 test gates."""

    def test_dogfood_zero_cloud_gravity_repo_passes_with_zero_violations_expected(self) -> None:
        """Verify the live ZeroCloudGravity repository passes lint_architecture cleanly."""
        # Arrange
        target = REPO_DIR

        # Act
        report = lint_architecture(target)

        # Assert
        assert report["passed"] is True
        assert report["violation_count"] == 0
        assert report["violations"] == []

    def test_domain_module_type_checking_exemption_and_violation_rules_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify TYPE_CHECKING exemptions, syntax errors, and infra/IO domain violations."""
        # Arrange
        dom_dir = tmp_path / "src/orders/domain"
        dom_dir.mkdir(parents=True)
        clean_dom = dom_dir / "models.py"
        clean_dom.write_text(
            "from __future__ import annotations\n"
            "import typing\n"
            "from typing import TYPE_CHECKING\n"
            "from . import local_vo\n"
            "if TYPE_CHECKING:\n"
            "    import sqlite3\n"
            "if typing.TYPE_CHECKING:\n"
            "    from orders.infrastructure.repository import OrderRepo\n",
            encoding="utf-8",
        )
        dirty_dom = dom_dir / "service.py"
        dirty_dom.write_text(
            "import sqlite3\nfrom orders.infrastructure.repository import OrderRepo\n",
            encoding="utf-8",
        )
        broken_dom = dom_dir / "entities.py"
        broken_dom.write_text("def broken(:\n", encoding="utf-8")
        non_dom = tmp_path / "src/orders/helper.py"
        non_dom.write_text("import sqlite3\n", encoding="utf-8")
        txt_file = dom_dir / "notes.txt"
        txt_file.write_text("plain", encoding="utf-8")

        # Act
        v_clean = check_domain_module(clean_dom)
        v_dirty = check_domain_module(dirty_dom)
        v_broken = check_domain_module(broken_dom)
        v_non_dom = check_domain_module(non_dom)
        v_txt = check_domain_module(txt_file)
        v_missing = check_domain_module(dom_dir / "absent.py")

        # Assert
        assert v_clean == [] and v_non_dom == [] and v_txt == [] and v_missing == []
        assert [v.rule for v in v_dirty] == [
            "domain-imports-io-package",
            "domain-imports-infrastructure",
        ]
        assert [v.rule for v in v_broken] == ["syntax-error"]

    def test_excluded_contexts_init_files_and_test_suite_rules_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify non-empty __init__.py, excluded_contexts, and all check_test_suite rules."""
        # Arrange
        proj = tmp_path / "svc-iso"
        (proj / "src/billing/__pycache__").mkdir(parents=True)
        (proj / "src/catalog").mkdir(parents=True)
        (proj / "src/.venv/billing").mkdir(parents=True)
        (proj / "system").mkdir(parents=True)
        (proj / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"excluded_contexts": {"billing": ["catalog"]}}), encoding="utf-8"
        )
        (proj / "src/billing/__init__.py").write_text("# non-empty\n", encoding="utf-8")
        (proj / "src/billing/__pycache__/__init__.py").write_text("# skipped\n", encoding="utf-8")
        (proj / "src/billing/__pycache__/cached.py").write_text(
            "import catalog\n", encoding="utf-8"
        )
        (proj / "src/.venv/billing/ignored.py").write_text("import catalog.api\n", encoding="utf-8")
        (proj / "src/billing/use_case.py").write_text(
            "import json\nfrom catalog.pricing import quote\n", encoding="utf-8"
        )
        (proj / "src/billing/broken.py").write_text("def bad(:\n", encoding="utf-8")
        (proj / "src/matched.py").write_text("X = 1\n", encoding="utf-8")

        t_dir = proj / "tests"
        (t_dir / "unit").mkdir(parents=True)
        (t_dir / "imp").mkdir(parents=True)
        (t_dir / ".venv").mkdir(parents=True)
        (t_dir / ".venv/test_skip.py").write_text("x = 1\n", encoding="utf-8")
        (t_dir / "test_flat.py").write_text("class TestFlat:\n    pass\n", encoding="utf-8")
        (t_dir / "unit/test_orphan.py").write_text("class TestOrph:\n    pass\n", encoding="utf-8")
        (t_dir / "unit/test_matched.py").write_text(
            "def helper() -> None:\n    pass\n\n"
            "class TestMatched:\n"
            "    def test_no_aaa(self, db_session: object) -> None:\n"
            "        assert db_session is not None\n",
            encoding="utf-8",
        )
        (t_dir / "imp/test_zero.py").write_text("X = 1\n", encoding="utf-8")
        (t_dir / "imp/test_two.py").write_text(
            "class TestOne:\n    pass\nclass TestTwo:\n    pass\n", encoding="utf-8"
        )
        (t_dir / "imp/test_syn.py").write_text("def bad(:\n", encoding="utf-8")

        flat_proj = tmp_path / "flat-proj"
        flat_proj.mkdir()
        (flat_proj / "system").mkdir()
        (flat_proj / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"excluded_contexts": "invalid"}), encoding="utf-8"
        )
        src_only_proj = tmp_path / "src-only-unmanifested"
        (src_only_proj / "src").mkdir(parents=True)

        # Act
        full_rep = lint_architecture(proj)
        no_test_rep = lint_architecture(proj, check_tests=False)
        flat_rep = lint_architecture(flat_proj)
        src_only_rep = lint_architecture(src_only_proj)
        missing_tests = check_test_suite(tmp_path / "no-such-tests")

        # Assert
        rules = {v["rule"] for v in full_rep["violations"]}
        assert full_rep["passed"] is False
        assert {
            "non-empty-init-file",
            "excluded-context-import",
            "flat-test-file",
            "orphan-test-file",
            "db-fixture-in-unit-test",
            "missing-aaa-comments",
            "one-test-class-per-file",
            "syntax-error",
        }.issubset(rules)
        assert "flat-test-file" not in {v["rule"] for v in no_test_rep["violations"]}
        assert flat_rep["passed"] is True and src_only_rep["passed"] is True
        assert missing_tests == []
