"""Unit tests for zcg.governance.links.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import links


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    target = node_dir / NODE_MANIFEST_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestLinks:
    """Verify declarative link/unlink management, directory resolution, and branch spin-out."""

    def test_link_unlink_and_resolve_linked_node_dir_across_cases_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify link_node, unlink_node, sibling discovery, remote URLs, and validation guards."""
        # Arrange
        work_dir = tmp_path / "alex-work"
        _write_manifest(
            work_dir,
            {
                "layer_id": "alex-work",
                "layer_role": "department",
                "precedence": 87,
                "entity_kind": "individual",
                "governing_root_id": "alex-pc",
                "linked_nodes": ["not-a-dict"],
            },
        )
        tutor_dir = tmp_path / "alex-tutor"
        _write_manifest(
            tutor_dir,
            {
                "layer_id": "alex-tutor",
                "layer_role": "department",
                "precedence": 86,
                "entity_kind": "individual",
                "governing_root_id": "alex-pc",
            },
        )
        rel_sub = work_dir / "peers/client-node"
        _write_manifest(
            rel_sub,
            {"layer_id": "client-node", "layer_role": "squad", "precedence": 50},
        )

        # Act — validation guards
        with pytest.raises(ValueError, match="Invalid target_id"):
            links.link_node(work_dir, target_id="INVALID_ID")
        with pytest.raises(ValueError, match="Invalid relation"):
            links.link_node(work_dir, target_id="org-alpha", relation="unknown-rel")
        with pytest.raises(ValueError, match="Missing node manifest"):
            links.link_node(tmp_path / "missing-ws", target_id="org-alpha")
        with pytest.raises(ValueError, match="Cannot link node"):
            links.link_node(work_dir, target_id="alex-work")
        with pytest.raises(ValueError, match="Invalid shared_pack"):
            links.link_node(work_dir, target_id="org-alpha", shared_packs=["BAD_PACK"])

        # Sibling auto-discovery, relative local ref, remote knowledge URL, and dry-run
        res_sib = links.link_node(
            work_dir,
            target_id="alex-tutor",
            relation="",
            shared_packs=["academic-base", " "],
            description="Socratic learning peer",
        )
        res_rel = links.link_node(
            work_dir,
            target_id="client-node",
            relation="b2b-collaboration",
            target_ref="peers/client-node",
            shared_packs=["software-engineering"],
        )
        res_abs = links.link_node(
            work_dir,
            target_id="client-node",
            relation="b2b-collaboration",
            target_ref=str(rel_sub.resolve()),
        )
        res_rem = links.link_node(
            work_dir,
            target_id="org-alpha",
            relation="hr-process",
            target_ref="https://org-alpha.knowledge.local",
            cockpit_url="https://org-alpha.knowledge.local",
        )
        res_unlinked_local = links.link_node(
            work_dir,
            target_id="ghost-peer",
            relation="lateral-peer",
            target_ref="nonexistent/ghost-peer",
        )
        res_dry = links.link_node(
            work_dir, target_id="gov-es", relation="knowledge-feed", dry_run=True
        )

        # Resolve linked dirs
        resolved_sib = links.resolve_linked_node_dir(work_dir, "alex-tutor")
        resolved_abs = links.resolve_linked_node_dir(work_dir, "client-node")
        # Test sibling fallback when target_ref is empty
        links.link_node(
            work_dir,
            target_id="alex-tutor",
            relation="lateral-peer",
            target_ref="https://remote.only.local",
        )
        resolved_sib_fb = links.resolve_linked_node_dir(work_dir, "alex-tutor")
        # Test relative target_ref resolution in resolve_linked_node_dir
        links.link_node(
            work_dir,
            target_id="client-node",
            relation="b2b-collaboration",
            target_ref="peers/client-node",
        )
        resolved_rel = links.resolve_linked_node_dir(work_dir, "client-node")
        resolved_rem = links.resolve_linked_node_dir(work_dir, "org-alpha")
        resolved_ghost = links.resolve_linked_node_dir(work_dir, "ghost-peer")
        resolved_none = links.resolve_linked_node_dir(work_dir, "never-linked")

        # Unlink guards, dry-run, removal, and idempotent miss
        with pytest.raises(ValueError, match="Invalid target_id"):
            links.unlink_node(work_dir, target_id="BAD_ID")
        with pytest.raises(ValueError, match="Missing node manifest"):
            links.unlink_node(tmp_path / "missing-ws", target_id="org-alpha")
        un_dry = links.unlink_node(work_dir, target_id="org-alpha", dry_run=True)
        un_ok = links.unlink_node(work_dir, target_id="org-alpha")
        un_miss = links.unlink_node(work_dir, target_id="org-alpha")

        # Assert
        assert res_sib["linked_node"]["precedence"] == 86
        assert (
            res_sib["linked_node"]["cockpit_url"] == "http://dev.alex-tutor.alex-pc.localhost:8786"
        )
        assert res_sib["linked_node"]["description"] == "Socratic learning peer"
        assert res_rel["linked_node"]["precedence"] == 50
        assert res_abs["linked_node"]["precedence"] == 50
        assert res_rem["linked_node"]["layer_role"] == "knowledge"
        assert res_unlinked_local["linked_node"]["layer_role"] == "project"
        assert res_dry["dry_run"] is True
        assert resolved_sib == tutor_dir.resolve()
        assert resolved_sib_fb == tutor_dir.resolve()
        assert resolved_abs == rel_sub.resolve()
        assert resolved_rel == rel_sub.resolve()
        assert resolved_rem is None
        assert resolved_ghost is None
        assert resolved_none is None
        assert un_dry["removed"] is True and un_dry["dry_run"] is True
        assert un_ok["removed"] is True
        assert un_miss["removed"] is False

    def test_spinout_branch_to_project_git_non_git_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify spinout_branch_to_project extracts git branch files and links bidirectionally."""
        # Arrange
        repo_dir = tmp_path / "engine"
        _write_manifest(repo_dir, {"layer_id": "root", "layer_role": "workstation"})

        work_git = tmp_path / "alex-work"
        work_git.mkdir()
        subprocess.run(
            ["git", "init", "-b", "master"], cwd=work_git, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "alex@example.org"], cwd=work_git, check=True
        )
        subprocess.run(["git", "config", "user.name", "Alex"], cwd=work_git, check=True)
        _write_manifest(
            work_git,
            {
                "layer_id": "alex-work",
                "layer_role": "department",
                "precedence": 87,
                "entity_kind": "individual",
                "governing_root_id": "alex-pc",
                "interaction_language": "es",
            },
        )
        (work_git / "Makefile").write_text("# Master Makefile\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work_git, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init master"], cwd=work_git, check=True, capture_output=True
        )

        subprocess.run(
            ["git", "checkout", "-b", "venture/saas-billing"],
            cwd=work_git,
            check=True,
            capture_output=True,
        )
        (work_git / "src").mkdir()
        (work_git / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (work_git / ".agents").mkdir()
        (work_git / ".agents/SESSION.md").write_text("skip me\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work_git, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add venture prototype"],
            cwd=work_git,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "checkout", "master"], cwd=work_git, check=True, capture_output=True)

        out_proj = tmp_path / "saas-billing"

        def _fake_bootstrap(
            _r: Path,
            target_dir: Path,
            *,
            layer_id: str,
            layer_role: str = "service-node",
            precedence: int = 80,
            dry_run: bool = False,
            **_kw: object,
        ) -> dict[str, object]:
            if not dry_run:
                _write_manifest(
                    target_dir,
                    {"layer_id": layer_id, "layer_role": layer_role, "precedence": precedence},
                )
            return {"layer_id": layer_id, "dry_run": dry_run}

        # Act — validation guards
        with pytest.raises(ValueError, match="Invalid project_id"):
            links.spinout_branch_to_project(
                repo_dir, work_git, out_proj, project_id="BAD_ID", from_branch="venture/x"
            )
        with pytest.raises(ValueError, match="non-default context branch"):
            links.spinout_branch_to_project(
                repo_dir, work_git, out_proj, project_id="saas-billing", from_branch="master"
            )
        with pytest.raises(ValueError, match="distinct from source_workspace_dir"):
            links.spinout_branch_to_project(
                repo_dir, work_git, work_git, project_id="saas-billing", from_branch="venture/x"
            )
        with pytest.raises(ValueError, match="Missing source node manifest"):
            links.spinout_branch_to_project(
                repo_dir,
                tmp_path / "no-src",
                out_proj,
                project_id="saas-billing",
                from_branch="venture/x",
            )
        with pytest.raises(ValueError, match="not found"):
            links.spinout_branch_to_project(
                repo_dir,
                work_git,
                out_proj,
                project_id="saas-billing",
                from_branch="venture/missing",
            )

        with patch("zcg.governance.links.bootstrap_node_workspace", side_effect=_fake_bootstrap):
            dry_spin = links.spinout_branch_to_project(
                repo_dir,
                work_git,
                out_proj,
                project_id="saas-billing",
                from_branch="venture/saas-billing",
                shared_packs=["software-engineering"],
                dry_run=True,
            )
            real_spin = links.spinout_branch_to_project(
                repo_dir,
                work_git,
                out_proj,
                project_id="saas-billing",
                from_branch="venture/saas-billing",
                shared_packs=["software-engineering"],
            )
            non_git_src = tmp_path / "plain-work"
            _write_manifest(non_git_src, {"layer_id": "plain-work", "layer_role": "department"})
            plain_spin = links.spinout_branch_to_project(
                repo_dir,
                non_git_src,
                tmp_path / "plain-out",
                project_id="plain-out",
                from_branch="venture/plain",
            )

        # Assert
        assert dry_spin["dry_run"] is True
        assert dry_spin["extracted_files"] == ["src/app.py"]
        assert real_spin["extracted_files"] == ["src/app.py"]
        assert (out_proj / "src/app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert not (out_proj / ".agents/SESSION.md").exists()
        assert (
            real_spin["bidirectional_links"]["from_source"]["linked_node"]["node_id"]
            == "saas-billing"
        )
        assert (
            real_spin["bidirectional_links"]["from_project"]["linked_node"]["node_id"]
            == "alex-work"
        )
        assert plain_spin["extracted_files"] == []
