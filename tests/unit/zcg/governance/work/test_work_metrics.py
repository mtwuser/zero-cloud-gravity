"""Unit tests for zcg.governance.work.work_metrics.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from zcg.governance.work.work_metrics import (
    METRICS_CONTRACT_REV,
    VALID_METRICS_SCOPES,
    collect_workspace_metrics,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_node(
    node_dir: Path,
    manifest: dict[str, object],
    *,
    worktask: str = "",
    backlog: str = "",
    readme: str = "",
) -> None:
    (node_dir / "system").mkdir(parents=True, exist_ok=True)
    (node_dir / "system/zcg-node.json").write_text(json.dumps(manifest), encoding="utf-8")
    if worktask:
        (node_dir / "WORKTASK.md").write_text(worktask, encoding="utf-8")
    if backlog:
        (node_dir / "BACKLOG.md").write_text(backlog, encoding="utf-8")
    if readme:
        (node_dir / "README.md").write_text(readme, encoding="utf-8")


class TestWorkMetrics:
    """Verify pure-filesystem work, knowledge, vault, and Git sync metrics across 3 scopes."""

    def test_collect_node_scope_work_docs_vault_and_sync_hygiene_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify node metrics across tasks, frontmatter visibilities, vault blobs, and sync."""
        # Arrange
        ws = tmp_path / "corp-iso"
        _write_node(
            ws,
            {"layer_id": "corp-iso", "layer_role": "corporate"},
            worktask="# Tasks\n- [ ] Todo A\n- [/] Active B\n- [x] Done C\n- [x] Done D\n",
            backlog="# Backlog\n- [ ] Open B1\n- [x] Closed B2\n",
            readme="# Corp Root\n",
        )
        (ws / "WORKROAD.md").write_text("# Road\n- [x] M1\n- [ ] M2\n", encoding="utf-8")
        (ws / "WORKVALI.md").write_text("# Vali\n- [x] V1\n", encoding="utf-8")
        (ws / "docs").mkdir()
        (ws / "docs/private.md").write_text(
            "---\nvisibility: internal-r3\n---\n# Secret\n", encoding="utf-8"
        )
        (ws / "docs/public.md").write_text(
            "---\nvisibility: public-r0\n---\n# Public\n", encoding="utf-8"
        )
        (ws / "docs/shared.md").write_text(
            "---\nstatus: draft\nvisibility: invalid-val\n---\n# Shared\n", encoding="utf-8"
        )
        (ws / "docs/unclosed.md").write_text("---\ntitle: NoEnd\n", encoding="utf-8")
        (ws / "docs/plain.md").write_text("", encoding="utf-8")
        vdir = ws / ".agents/telemetry/vault_blobs/sub"
        vdir.mkdir(parents=True)
        (vdir / "doc.pdf").write_bytes(b"0123456789")
        (vdir / "meta.json").write_text("{}", encoding="utf-8")
        (ws / "surfaces/data").mkdir(parents=True)
        (ws / "surfaces/data/node_scope.json").write_text(
            json.dumps(
                {
                    "representation_context": {
                        "node_health": {
                            "dimensions": {"sync_safety": {"dirty": 2, "ahead": 1, "behind": 3}}
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        # Act
        report = collect_workspace_metrics(ws, scope="node")
        fallback = collect_workspace_metrics(ws, scope="unknown-scope")

        # Assert
        assert report["contract_rev"] == METRICS_CONTRACT_REV
        assert VALID_METRICS_SCOPES == ("all", "node", "network", "corpora")
        assert report["scope"] == "node" and fallback["scope"] == "node"
        assert report["work"] == {
            "todo_count": 1,
            "in_progress_count": 1,
            "done_count": 2,
            "total_count": 4,
            "completion_pct": 50,
            "backlog_open_count": 1,
            "backlog_total_count": 2,
            "roadmap_total_count": 2,
            "roadmap_done_count": 1,
            "validation_total_count": 1,
            "validation_verified_count": 1,
            "inbox_pending_count": 0,
        }
        assert report["knowledge"] == {
            "total_docs": 6,
            "r3_count": 1,
            "r2_count": 3,
            "r0_count": 2,
        }
        assert report["vault"] == {"vault_files": 1, "vault_bytes": 10}
        assert report["git_sync"] == {"git_dirty_count": 2, "git_ahead": 1, "git_behind": 3}

    def test_collect_network_and_corpora_scopes_with_wallet_airlock_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 1-hop network/corpora discovery, linked_nodes, and wallet R3 exclusion."""
        # Arrange
        parent_ws = tmp_path / "persona-profile"
        child_ws = parent_ws / "layers/persona-work"
        wallet_ws = tmp_path / "persona-wallet"
        sibling_ws = tmp_path / "persona-tutor"
        unrelated_ws = tmp_path / "other-org"
        corpus_ws = tmp_path / "sci-physics"
        corpus_role_ws = tmp_path / "custom-lib"
        empty_dir = tmp_path / "not-a-node"
        empty_dir.mkdir()
        (tmp_path / "stray-file.txt").write_text("x", encoding="utf-8")

        _write_node(
            corpus_ws,
            {"layer_id": "sci-physics", "layer_role": "project"},
            readme="# Physics\n",
        )
        (corpus_ws / "docs").mkdir()
        (corpus_ws / "docs/law.md").write_text("# Law\n", encoding="utf-8")
        _write_node(
            corpus_role_ws,
            {"layer_id": "custom-lib", "layer_role": "knowledge"},
            readme="# Custom Knowledge\n",
        )
        _write_node(
            parent_ws,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "linked_nodes": [
                    str(corpus_ws),
                    {"path": str(corpus_role_ws)},
                    {"path": str(tmp_path / "missing-dir")},
                    "",
                ],
            },
            worktask="- [x] Parent done\n",
        )
        (parent_ws / "layers").mkdir(parents=True, exist_ok=True)
        (parent_ws / "layers/readme.txt").write_text("skip", encoding="utf-8")
        (parent_ws / "layers/plain-dir").mkdir(parents=True)
        _write_node(
            child_ws,
            {
                "layer_id": "persona-work",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
            worktask="- [ ] Child open\n",
        )
        _write_node(
            wallet_ws,
            {
                "layer_id": "persona-wallet",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
            worktask="- [ ] Wallet secret\n",
        )
        _write_node(
            sibling_ws,
            {
                "layer_id": "persona-tutor",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
            worktask="- [x] Tutor done\n",
        )
        _write_node(
            unrelated_ws,
            {"layer_id": "other-org", "layer_role": "corporate", "governing_root_id": "other-org"},
            worktask="- [ ] Other\n",
        )

        # Act
        net_from_parent = collect_workspace_metrics(parent_ws, scope="network")
        all_from_parent = collect_workspace_metrics(parent_ws, scope="all")
        net_from_child = collect_workspace_metrics(child_ws, scope="network", parent_dir=parent_ws)
        net_from_sibling = collect_workspace_metrics(sibling_ws, scope="network")
        corp_report = collect_workspace_metrics(parent_ws, scope="corpora")
        empty_corp = collect_workspace_metrics(unrelated_ws, scope="corpora")

        # Assert
        parent_net_ids = [n["node_id"] for n in net_from_parent["nodes"]]
        parent_all_ids = [n["node_id"] for n in all_from_parent["nodes"]]
        child_net_ids = [n["node_id"] for n in net_from_child["nodes"]]
        sib_net_ids = [n["node_id"] for n in net_from_sibling["nodes"]]
        corp_ids = [n["node_id"] for n in corp_report["nodes"]]
        assert parent_net_ids == ["persona-profile", "persona-work", "persona-tutor"]
        assert parent_all_ids == [
            "persona-profile",
            "persona-work",
            "persona-tutor",
            "sci-physics",
            "custom-lib",
        ]
        assert "persona-wallet" not in parent_net_ids and "other-org" not in parent_net_ids
        assert "persona-profile" in child_net_ids and "persona-work" in child_net_ids
        assert "persona-tutor" in sib_net_ids and "persona-profile" in sib_net_ids
        assert corp_ids == ["sci-physics", "custom-lib"]
        assert corp_report["knowledge"]["r0_count"] == 3
        assert empty_corp["node_count"] == 0 and empty_corp["work"]["completion_pct"] == 0

    def test_lateral_sibling_metrics_respect_mesh_governance_policy_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify enterprise lateral siblings obey hierarchical-only vs curated-matrix channels."""
        # Arrange
        corp_root = tmp_path / "corp-root"
        dept_eng = tmp_path / "dept-eng"
        dept_ops = tmp_path / "dept-ops"
        corp_docs = tmp_path / "org-corp-docs"
        _write_node(
            corp_root,
            {
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "capability_policy": {"mesh_governance": {"topology_mode": "hierarchical-only"}},
            },
            worktask="- [x] Root\n",
        )
        _write_node(
            dept_eng,
            {
                "layer_id": "dept-eng",
                "layer_role": "department",
                "entity_kind": "enterprise",
                "governing_root_id": "corp-root",
            },
            worktask="- [ ] Eng\n",
        )
        _write_node(
            dept_ops,
            {
                "layer_id": "dept-ops",
                "layer_role": "department",
                "entity_kind": "enterprise",
                "governing_root_id": "corp-root",
            },
            worktask="- [ ] Ops\n",
        )
        _write_node(
            corp_docs,
            {
                "layer_id": "org-corp-docs",
                "layer_role": "knowledge",
                "entity_kind": "enterprise",
                "governing_root_id": "corp-root",
            },
            readme="# Corp Docs\n",
        )

        # Act
        hier_net = collect_workspace_metrics(dept_eng, scope="network", parent_dir=corp_root)
        _write_node(
            corp_root,
            {
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "capability_policy": {
                    "mesh_governance": {
                        "topology_mode": "curated-matrix",
                        "lateral_channels": [
                            {
                                "source_node": "dept-eng",
                                "target_node": "dept-ops",
                                "allowed_verbs": ["consult_context"],
                                "reciprocal": True,
                            }
                        ],
                    }
                },
            },
            worktask="- [x] Root\n",
        )
        curated_net = collect_workspace_metrics(dept_eng, scope="network", parent_dir=corp_root)
        curated_all = collect_workspace_metrics(dept_eng, scope="all", parent_dir=corp_root)

        # Assert
        assert [n["node_id"] for n in hier_net["nodes"]] == ["dept-eng", "corp-root"]
        assert [n["node_id"] for n in curated_net["nodes"]] == [
            "dept-eng",
            "corp-root",
            "dept-ops",
        ]
        assert "org-corp-docs" in [n["node_id"] for n in curated_all["nodes"]]

    def test_degraded_and_corrupted_node_scope_files_return_zero_defaults_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing trackers and malformed node_scope.json degrade to zero counters."""
        # Arrange
        ws_bad_json = tmp_path / "bad-json"
        (ws_bad_json / "surfaces/data").mkdir(parents=True)
        (ws_bad_json / "surfaces/data/node_scope.json").write_text("{broken", encoding="utf-8")

        ws_list = tmp_path / "list-json"
        (ws_list / "surfaces/data").mkdir(parents=True)
        (ws_list / "surfaces/data/node_scope.json").write_text("[1, 2]", encoding="utf-8")

        ws_empty = tmp_path / "empty-dict"
        (ws_empty / "surfaces/data").mkdir(parents=True)
        (ws_empty / "surfaces/data/node_scope.json").write_text("{}", encoding="utf-8")

        # Act
        r_bad = collect_workspace_metrics(ws_bad_json, scope="node")
        r_list = collect_workspace_metrics(ws_list, scope="node")
        r_empty = collect_workspace_metrics(ws_empty, scope="node")

        # Assert
        for rep in (r_bad, r_list, r_empty):
            assert rep["work"]["total_count"] == 0 and rep["work"]["completion_pct"] == 0
            assert rep["knowledge"]["total_docs"] == 0
            assert rep["vault"] == {"vault_files": 0, "vault_bytes": 0}
            assert rep["git_sync"] == {"git_dirty_count": 0, "git_ahead": 0, "git_behind": 0}
