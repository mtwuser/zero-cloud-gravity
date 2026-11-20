"""Unit tests for zcg.cockpit.routing.docs_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from zcg.cockpit.routing import docs_router
from zcg.web.http.factory import create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    hdrs = {"host": "persona-profile.localhost:8790", **(headers or {})}
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()]
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestDocsRouter:
    """1:1 unit suite for 3-origin browsing, FTS5 search, R3 authoring, and C3 commits."""

    def test_discover_sources_search_and_docs_reader_endpoints_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify multi-source discovery, origin filters, FTS5 search, and 403/404 guards."""
        # Arrange
        empty_ws = tmp_path / "empty-node"
        empty_ws.mkdir()
        sci_ws = tmp_path / "sci-maths"
        (sci_ws / "system").mkdir(parents=True)
        (sci_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "sci-maths", "layer_role": "knowledge"}), encoding="utf-8"
        )
        (sci_ws / "docs").mkdir()
        (sci_ws / "docs/law.md").write_text("#SingleHeading\n## Law 1\nEigenvalues\n", "utf-8")

        gov_ws = tmp_path / "gov-iso"
        (gov_ws / "system").mkdir(parents=True)
        (gov_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "gov-iso", "layer_role": "knowledge"}), encoding="utf-8"
        )
        (gov_ws / "README.md").write_text("# Statutory Corpus\n## Section A\n", encoding="utf-8")

        ws = tmp_path / "persona-wallet"
        (ws / "system").mkdir(parents=True)
        (ws / "docs").mkdir(parents=True)
        (ws / "layers/sub-pack").mkdir(parents=True)
        (ws / "layers/empty-pack").mkdir(parents=True)
        (ws / "layers/sub-pack/README.md").write_text("# Sub Pack\n", encoding="utf-8")
        (ws / "layers/sub-pack/docs").mkdir(parents=True)
        (ws / "layers/sub-pack/docs/priv.md").write_text(
            "---\nvisibility: internal-r3\n---\n# Secret\n", encoding="utf-8"
        )
        (ws / "README.md").write_text("# Wallet\n## Thesis\n## Rules\n", encoding="utf-8")
        (ws / "docs/not-md.txt").write_text("plain", encoding="utf-8")
        (ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "mounted_layers": [{"layer_id": "sci-maths"}],
                    "linked_nodes": [
                        {
                            "node_id": "gov-iso",
                            "layer_role": "knowledge",
                            "relation": "knowledge-feed",
                            "target_ref": str(gov_ws),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        app_empty = create_web_app(
            routers=(docs_router.create_docs_reader_router(empty_ws),), allowed_hosts=("*",)
        )
        app_rich = create_web_app(
            routers=(docs_router.create_docs_reader_router(ws),), allowed_hosts=("*",)
        )
        js_h = {"accept": "application/json"}

        async def _exercise() -> dict[str, tuple[int, bytes]]:
            return {
                "empty": await _call(
                    app_empty, "GET", "/api/modules/docs-reader", query="action=new", headers=js_h
                ),
                "self_def": await _call(app_rich, "GET", "/api/modules/docs-reader", headers=js_h),
                "search": await _call(
                    app_rich,
                    "GET",
                    "/api/modules/docs-reader",
                    query="origin=corpus&q=Eigenvalues",
                    headers=js_h,
                ),
                "ws_scope_corp": await _call(
                    app_rich,
                    "GET",
                    "/api/modules/docs-reader",
                    query="ws_scope=corpora",
                    headers=js_h,
                ),
                "corpus_hx": await _call(
                    app_rich,
                    "GET",
                    "/api/modules/docs-reader",
                    query="source=sci-maths",
                    headers={"hx-request": "true"},
                ),
                "bad_src": await _call(
                    app_rich, "GET", "/api/modules/docs-reader", query="source=missing"
                ),
                "traversal": await _call(
                    app_rich, "GET", "/api/modules/docs-reader", query="doc=../../etc/passwd"
                ),
                "non_md": await _call(
                    app_rich, "GET", "/api/modules/docs-reader", query="doc=docs/not-md.txt"
                ),
                "missing_md": await _call(
                    app_rich, "GET", "/api/modules/docs-reader", query="doc=docs/404.md"
                ),
                "priv_403": await _call(
                    app_rich,
                    "GET",
                    "/api/modules/docs-reader",
                    query="source=sub-pack&doc=docs/priv.md",
                ),
            }

        # Act
        sources = docs_router.discover_readable_sources(ws)
        res = asyncio.run(_exercise())

        # Assert
        assert [s["source_id"] for s in sources] == ["self", "sub-pack", "sci-maths", "gov-iso"]
        assert res["empty"][0] == 200 and json.loads(res["empty"][1])["doc"] == ""
        self_doc = json.loads(res["self_def"][1])
        assert res["self_def"][0] == 200 and self_doc["doc"] == "README.md"
        assert len(self_doc["toc"]) == 3
        search_doc = json.loads(res["search"][1])
        assert res["search"][0] == 200 and len(search_doc["hits"]) == 1
        assert res["ws_scope_corp"][0] == 200 and json.loads(res["ws_scope_corp"][1])["origin"] == (
            "corpus"
        )
        assert res["corpus_hx"][0] == 200 and b"Read-Only" in res["corpus_hx"][1]
        assert b"<h3>Docs &amp; Knowledge</h3>" not in res["corpus_hx"][1]
        assert b"zcg-chip-list" in res["corpus_hx"][1]
        assert b"data-zcg-cli-hint" in res["corpus_hx"][1] and b"README.md" in res["corpus_hx"][1]
        assert res["bad_src"][0] == 404
        assert res["traversal"][0] == 403
        assert res["non_md"][0] == 404 and res["missing_md"][0] == 404
        assert res["priv_403"][0] == 403 and b"PRIVATE_DOC_R3_ONLY" in res["priv_403"][1]

    def test_authoring_save_edit_commit_and_r3_guards_expected(self, tmp_path: Path) -> None:
        """Verify R3 POST /save, ?action=edit, POST /commit, and 400/403/409/422 guards."""
        # Arrange
        ws = tmp_path / "work-docs"
        ws.mkdir()
        subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True
        )
        (ws / "README.md").write_text("# Work\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)

        tok = f"tok-{tmp_path.name}"
        app = create_web_app(
            csrf_token=tok,
            routers=(docs_router.create_docs_reader_router(ws),),
            allowed_hosts=("*",),
        )
        csrf_h = {"x-zcg-csrf-token": tok}
        form_h = {
            **csrf_h,
            "hx-request": "true",
            "content-type": "application/x-www-form-urlencoded",
        }
        json_h = {**csrf_h, "content-type": "application/json"}

        # Act
        async def _run() -> list[tuple[int, bytes]]:
            return [
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/save",
                    headers={**csrf_h, "host": "ext.example.org"},
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/save",
                    headers=form_h,
                    body=urlencode(
                        {"rel_path": "docs/adr-01.md", "title": "Modular Caps"}
                    ).encode(),
                ),
                await _call(
                    app,
                    "GET",
                    "/api/modules/docs-reader",
                    query="source=self&doc=docs/adr-01.md&action=edit",
                    headers={"hx-request": "true"},
                ),
                await _call(app, "POST", "/api/modules/docs-reader/save", headers=csrf_h),
                await _call(
                    app, "POST", "/api/modules/docs-reader/save", headers=json_h, body=b"[1]"
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/commit",
                    headers={**form_h},
                    body=urlencode(
                        {
                            "rel_path": "docs/adr-01.md",
                            "commit_message": "docs(adr): add adr-01",
                        }
                    ).encode(),
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/commit",
                    headers=json_h,
                    body=b'{"rel_path":"docs/adr-01.md","commit_message":"docs(adr): repeat"}',
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/commit",
                    headers=json_h,
                    body=b'{"rel_path":"docs/adr-01.md","commit_message":"bad"}',
                ),
            ]

        r_403, r_save, r_edit, r_empty, r_bad_js, r_com, r_c409, r_c422 = asyncio.run(_run())

        # Assert
        assert r_403[0] == 403 and b"R3_OPERATOR_REQUIRED" in r_403[1]
        assert r_save[0] == 200 and b"Saved <code>docs/adr-01.md</code>" in r_save[1]
        assert b"zcg-dirty-banner" in r_save[1] and b"zcg-chip-list" not in r_save[1]
        assert b"<h3>Docs &amp; Knowledge</h3>" not in r_save[1] and b"docs/**/*.md" in r_save[1]
        assert r_edit[0] == 200 and b"Editing <code>docs/adr-01.md</code>" in r_edit[1]
        assert r_empty[0] == 422 and r_bad_js[0] == 400
        assert r_com[0] == 200 and b"Committed <code>" in r_com[1]
        assert r_c409[0] == 409 and r_c422[0] == 422

    def test_docs_draft_restore_discard_and_atomic_save_commit_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /draft, draft restore, /draft/discard, and save with commit_now=1."""
        # Arrange
        ws = tmp_path / "draft-docs"
        ws.mkdir()
        subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True
        )
        (ws / "docs").mkdir()
        (ws / "docs/sop.md").write_text("# SOP\nOriginal.\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)
        tok = f"tok-{tmp_path.name}"
        app = create_web_app(
            csrf_token=tok,
            routers=(docs_router.create_docs_reader_router(ws),),
            allowed_hosts=("*",),
        )
        csrf_h = {"x-zcg-csrf-token": tok}
        form_h = {
            **csrf_h,
            "hx-request": "true",
            "content-type": "application/x-www-form-urlencoded",
        }
        json_h = {**csrf_h, "content-type": "application/json"}

        # Act
        async def _run() -> list[tuple[int, bytes]]:
            return [
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/draft",
                    headers=json_h,
                    body=json.dumps(
                        {"draft_key": "doc:docs/sop.md", "content": "# SOP\nDraft body.\n"}
                    ).encode(),
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/draft",
                    headers=json_h,
                    body=b'{"draft_key": "", "content": ""}',
                ),
                await _call(
                    app,
                    "GET",
                    "/api/modules/docs-reader",
                    query="source=self&doc=docs/sop.md&action=edit",
                    headers={"hx-request": "true"},
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/draft/discard",
                    headers=form_h,
                    body=urlencode(
                        {"draft_key": "doc:docs/sop.md", "doc": "docs/sop.md", "action": "edit"}
                    ).encode(),
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/save",
                    headers=form_h,
                    body=urlencode(
                        {
                            "rel_path": "docs/sop.md",
                            "content": "# SOP\nCommitted atomically.\n",
                            "commit_now": "1",
                            "commit_message": "docs(knowledge): atomic sop update",
                        }
                    ).encode(),
                ),
                await _call(
                    app,
                    "POST",
                    "/api/modules/docs-reader/save",
                    headers=form_h,
                    body=urlencode(
                        {
                            "rel_path": "docs/sop.md",
                            "content": "# SOP\nBad commit msg.\n",
                            "commit_now": "1",
                            "commit_message": "bad message",
                        }
                    ).encode(),
                ),
            ]

        r_dr, r_dr_422, r_rest, r_disc, r_atom, r_bad_com = asyncio.run(_run())

        # Assert
        assert r_dr[0] == 200 and json.loads(r_dr[1])["saved"] is True
        assert r_dr_422[0] == 422
        assert r_rest[0] == 200 and b"Draft body." in r_rest[1] and b"Discard Draft" in r_rest[1]
        assert r_disc[0] == 200 and b"Discarded unapplied draft." in r_disc[1]
        assert b"Original." in r_disc[1]
        assert r_atom[0] == 200 and b"and committed <code>" in r_atom[1]
        assert b"zcg-dirty-banner" not in r_atom[1]
        assert r_bad_com[0] == 422
