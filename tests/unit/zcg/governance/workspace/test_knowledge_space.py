"""Unit tests for zcg.governance.workspace.knowledge_space.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from zcg.governance.workspace.knowledge_space import (
    MAX_SOURCE_FILES,
    extract_doc_visibility,
    list_workspace_markdown_files,
    render_doc_starter_template,
    resolve_knowledge_space_sources,
    save_knowledge_document,
    search_knowledge_space,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestKnowledgeSpace:
    """1:1 unit suite for 3-origin discovery, SQLite FTS5 search, and path-contained authoring."""

    def test_three_origin_discovery_and_sqlite_fts5_search_across_filters_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify node/network/corpus grouping, parent root discovery, and FTS5 search filters."""
        # Arrange
        parent_ws = tmp_path / "corp-root"
        (parent_ws / "system").mkdir(parents=True)
        (parent_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "corp-root", "layer_role": "corporate"}), encoding="utf-8"
        )
        (parent_ws / "README.md").write_text(
            "# Corporate Charter\n\nGlobal treasury policy.\n", encoding="utf-8"
        )
        (parent_ws / "WORKROAD.md").write_text("#Excluded Workroad\n", encoding="utf-8")
        (parent_ws / "docs").mkdir()
        (parent_ws / "docs/secret.md").write_text(
            "---\nvisibility: internal-r3\n---\n# Secret\n", encoding="utf-8"
        )
        (parent_ws / "docs/shared-adr.md").write_text(
            "---\nvisibility: public-r0\n---\n# Shared\n", encoding="utf-8"
        )
        child_ws = tmp_path / "Projects/dept-eng-child"
        (child_ws / "system").mkdir(parents=True)
        (child_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "dept-eng-child", "governing_root_id": "dept-eng"}),
            encoding="utf-8",
        )
        (child_ws / "README.md").write_text("# Child Docs\n", encoding="utf-8")
        wallet_child = tmp_path / "Projects/dept-wallet"
        (wallet_child / "system").mkdir(parents=True)
        (wallet_child / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "dept-wallet", "governing_root_id": "dept-eng"}),
            encoding="utf-8",
        )
        (wallet_child / "README.md").write_text("# Private Wallet\n", encoding="utf-8")

        corpus_ws = tmp_path / "sci-physics"
        (corpus_ws / "system").mkdir(parents=True)
        (corpus_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "sci-physics", "layer_role": "knowledge"}), encoding="utf-8"
        )
        (corpus_ws / "docs").mkdir()
        (corpus_ws / "docs/orbital.md").write_text("Keplerian orbital mechanics.\n", "utf-8")

        ws = tmp_path / "dept-eng"
        (ws / "system").mkdir(parents=True)
        (ws / "layers/sub-squad").mkdir(parents=True)
        (ws / "layers/empty-squad").mkdir(parents=True)
        (ws / "layers/ignore.txt").write_text("x", encoding="utf-8")
        (ws / "layers/sub-squad/README.md").write_text("# Squad Runbook\n", encoding="utf-8")
        (ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "dept-eng",
                    "layer_role": "department",
                    "governing_root_id": "corp-root",
                    "mounted_layers": [{"layer_id": "sci-physics"}, {"layer_id": ""}],
                    "linked_nodes": [
                        {
                            "node_id": "sci-physics",
                            "layer_role": "knowledge",
                            "relation": "knowledge-feed",
                            "target_ref": str(corpus_ws),
                        },
                        {
                            "node_id": "gov-iso",
                            "layer_role": "knowledge",
                            "relation": "knowledge-feed",
                            "target_ref": str(tmp_path / "missing-gov"),
                        },
                        {"node_id": "dept-ops", "layer_role": "department", "relation": "peer"},
                        {"node_id": "ext-wallet", "layer_role": "squad", "relation": "peer"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        save_knowledge_document(ws, rel_path="guides/deploy-sop", template_kind="adr", title="CD")

        # Act
        sources = resolve_knowledge_space_sources(ws, parent_dir=parent_ws)
        hits_all = search_knowledge_space(ws, "Keplerian", parent_dir=parent_ws)
        hits_net = search_knowledge_space(
            ws, "treasury", origin_filter="network", parent_dir=parent_ws
        )
        hits_blank = search_knowledge_space(ws, "   ")
        (ws / "docs/guides/deploy-sop.md").unlink()
        hits_after_unlink = search_knowledge_space(ws, "Keplerian", parent_dir=parent_ws)

        # Assert
        by_id = {s["source_id"]: s["origin_group"] for s in sources}
        assert by_id == {
            "self": "node",
            "corp-root": "network",
            "dept-eng-child": "network",
            "sub-squad": "network",
            "sci-physics": "corpus",
        }
        corp_files = next(s["files"] for s in sources if s["source_id"] == "corp-root")
        assert "WORKROAD.md" not in corp_files and "docs/secret.md" not in corp_files
        assert "docs/shared-adr.md" in corp_files
        assert extract_doc_visibility("---\nstatus: draft\n") == "network-r2"
        assert (
            extract_doc_visibility("---\nstatus: draft\nvisibility: invalid\n---\n") == "network-r2"
        )
        many_ws = tmp_path / "many-docs"
        (many_ws / "docs").mkdir(parents=True)
        for idx in range(MAX_SOURCE_FILES + 2):
            (many_ws / f"docs/d{idx:03d}.md").write_text("# Doc\n", encoding="utf-8")
        assert (
            len(list_workspace_markdown_files(many_ws, include_private_r3=False))
            == MAX_SOURCE_FILES
        )
        assert len(hits_all) == 1 and hits_all[0]["title"] == "docs/orbital.md"
        assert len(hits_net) == 1 and hits_net[0]["source_id"] == "corp-root"
        assert hits_blank == []
        assert len(hits_after_unlink) == 1

    def test_save_knowledge_document_templates_containment_and_budget_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify starter templates, path normalization, traversal blocks, and 464-line cap."""
        # Arrange
        ws = tmp_path / "tutor-ws"
        ws.mkdir()

        # Act
        bare_sources = resolve_knowledge_space_sources(ws)
        tpl_note = render_doc_starter_template("note", "")
        saved_tpl = save_knowledge_document(
            ws, rel_path="docs/notes/study.md", template_kind="unknown", title="Linear Algebra"
        )
        saved_custom = save_knowledge_document(
            ws, rel_path="runbook", content="# Custom Runbook\n\nBody.\n"
        )

        # Assert
        assert len(bare_sources) == 1 and bare_sources[0]["source_id"] == "self"
        assert "New Knowledge Document" in tpl_note
        assert saved_tpl["doc"] == "docs/notes/study.md"
        assert saved_tpl["template_kind"] == "guide"
        assert "Linear Algebra" in (ws / "docs/notes/study.md").read_text(encoding="utf-8")
        assert saved_custom["doc"] == "docs/runbook.md"
        with pytest.raises(ValueError, match="UNSAFE_DOC_PATH"):
            save_knowledge_document(ws, rel_path="   ")
        with pytest.raises(ValueError, match="UNSAFE_DOC_PATH"):
            save_knowledge_document(ws, rel_path="docs/../../outside.md")
        with pytest.raises(ValueError, match="UNSAFE_DOC_PATH"):
            save_knowledge_document(ws, rel_path="docs/.hidden/secret.md")
        with pytest.raises(ValueError, match="DOC_LINE_BUDGET_EXCEEDED"):
            save_knowledge_document(ws, rel_path="docs/huge.md", content="line\n" * 465)

    def test_lateral_sibling_discovery_obeys_mesh_relation_grants_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify governed lateral peers surface only when consult_context is granted."""
        # Arrange
        corp_root = tmp_path / "corp-root"
        dept_eng = tmp_path / "dept-eng"
        dept_ops = tmp_path / "dept-ops"
        dept_fin = tmp_path / "dept-fin"
        dept_wallet = tmp_path / "dept-wallet"
        for d, payload, body in (
            (
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
                                },
                                {
                                    "source_node": "dept-eng",
                                    "target_node": "dept-fin",
                                    "allowed_verbs": ["propose_work"],
                                    "reciprocal": True,
                                },
                            ],
                        }
                    },
                },
                "# Root\n",
            ),
            (
                dept_eng,
                {
                    "layer_id": "dept-eng",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "governing_root_id": "corp-root",
                },
                "# Eng\n",
            ),
            (
                dept_ops,
                {
                    "layer_id": "dept-ops",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "governing_root_id": "corp-root",
                },
                "# Ops Runbook\n",
            ),
            (
                dept_fin,
                {
                    "layer_id": "dept-fin",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "governing_root_id": "corp-root",
                },
                "# Fin Runbook\n",
            ),
            (
                dept_wallet,
                {
                    "layer_id": "dept-wallet",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "governing_root_id": "corp-root",
                },
                "# Secret Wallet\n",
            ),
        ):
            (d / "system").mkdir(parents=True)
            (d / "system/zcg-node.json").write_text(json.dumps(payload), encoding="utf-8")
            (d / "README.md").write_text(body, encoding="utf-8")

        # Act
        sources = resolve_knowledge_space_sources(dept_eng, parent_dir=corp_root)

        # Assert
        src_ids = {s["source_id"] for s in sources}
        assert "dept-ops" in src_ids
        assert "dept-fin" not in src_ids and "dept-wallet" not in src_ids
