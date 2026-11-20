"""Sovereign 3-Origin Knowledge Space, SQLite FTS5 Search & Corpus Reader APIRouter.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final, NoReturn
from urllib.parse import quote

from zcg.cockpit.ops.metrics_studio import render_cli_transparency_hint
from zcg.cockpit.views.docs_view import (
    VISIBILITY_BADGES,
    render_doc_dirty_banner_html,
    render_doc_editor_html,
    render_knowledge_space_chrome,
    render_markdown_document_html,
)
from zcg.core.manifests import ensure_contained_path
from zcg.governance.workspace.knowledge_space import (
    VALID_ORIGIN_GROUPS,
    extract_doc_visibility,
    resolve_knowledge_space_sources,
    save_knowledge_document,
    search_knowledge_space,
)
from zcg.governance.workspace.onboarding_studio import (
    discard_markdown_draft,
    load_markdown_draft,
    save_markdown_draft,
)
from zcg.governance.workspace.surface_mutations import (
    commit_scoped_workspace_paths,
    is_workspace_path_dirty,
)
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities.appearance import resolve_request_ring
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter

DEFAULT_DOCS_READER_PREFIX: Final[str] = "/api/modules/docs-reader"
_COMMIT_CONFLICTS: frozenset[str] = frozenset({"INDEX_HAS_STAGED_FILES", "NOTHING_TO_COMMIT"})
_WS_SCOPE_TO_ORIGIN: Final[dict[str, str]] = {
    "all": "all", "node": "node", "network": "network", "corpora": "corpus",
}  # fmt: skip


def discover_readable_sources(workspace_dir: Path) -> list[dict[str, Any]]:
    """Return sanitized metadata and relative Markdown file lists for readable node/corpus roots."""
    return [
        {k: s[k] for k in ("source_id", "label", "kind", "origin_group", "files")}
        for s in resolve_knowledge_space_sources(workspace_dir.resolve())
    ]


def _extract_body_map(req: Request) -> dict[str, Any]:
    if "urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body.strip():
        return {}
    parsed = req.json()
    if not isinstance(parsed, Mapping):
        raise WebAppError(
            "Docs request body must be a JSON object",
            error_code="INVALID_DOCS_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return dict(parsed)


def create_docs_reader_router(
    workspace_dir: Path,
    *,
    policy: SurfaceAccessPolicy | None = None,
    prefix: str = DEFAULT_DOCS_READER_PREFIX,
) -> APIRouter:
    """Create the Sovereign 3-Origin Knowledge Space & Connected Corpus APIRouter."""
    ws = workspace_dir.resolve()
    clean_pfx = prefix.rstrip("/") or DEFAULT_DOCS_READER_PREFIX
    router = APIRouter(prefix=clean_pfx, tags=("docs-reader",))

    def _require_r3(req: Request) -> None:
        if resolve_request_ring(req, policy) != "R3":
            raise WebAppError(
                "Authoring or committing local knowledge documents requires R3 operator authority",
                error_code="R3_OPERATOR_REQUIRED",
                http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )

    def _raise_commit_error(exc: ValueError) -> NoReturn:
        msg = str(exc)
        code = msg.partition(":")[0] or "COMMIT_REJECTED"
        st = HTTPStatus.CONFLICT if code in _COMMIT_CONFLICTS else HTTPStatus.UNPROCESSABLE_ENTITY
        raise WebAppError(msg, error_code=code, http_status=int(st)) from exc

    def _render_space_response(
        req: Request, *, want_src: str = "", force_doc: str = "",
        force_action: str = "", notice: str = "",
    ) -> WebResponse:  # fmt: skip
        all_sources = resolve_knowledge_space_sources(ws)
        raw_org = req.query("origin", "").strip().lower()
        origin_q = raw_org or _WS_SCOPE_TO_ORIGIN.get(
            req.query("ws_scope", "").strip().lower(), "all"
        )
        eff_origin = origin_q if origin_q in VALID_ORIGIN_GROUPS else "all"
        vis_sources = [
            s for s in all_sources if eff_origin == "all" or s["origin_group"] == eff_origin
        ] or all_sources
        src_map = {s["source_id"]: s for s in all_sources}
        eff_src = (want_src or req.query("source", "").strip()) or vis_sources[0]["source_id"]
        if eff_src not in src_map:
            raise WebAppError(
                f"Unknown documentation source: {eff_src}",
                error_code="DOC_SOURCE_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        cur_s = src_map[eff_src]
        files: list[str] = cur_s["files"]
        def_doc = "README.md" if "README.md" in files else (files[0] if files else "")
        sel_doc = force_doc or req.query("doc", "").strip() or def_doc
        pfx = html.escape(clean_pfx, quote=True)
        q_str = req.query("q", "").strip()
        act_q = (force_action or req.query("action", "")).strip().lower()
        is_r3 = resolve_request_ring(req, policy) == "R3"
        hits = search_knowledge_space(ws, q_str, origin_filter=eff_origin) if q_str else []
        src_pills, search_block = render_knowledge_space_chrome(
            prefix=clean_pfx, eff_origin=eff_origin, eff_src=eff_src, vis_sources=vis_sources,
            query_str=q_str, hits=hits, is_r3=is_r3,
        )  # fmt: skip
        pills_bar = (
            f"<div class='zcg-chip-list' style='margin-bottom:0.75rem;'>{src_pills}</div>"
            if src_pills
            else ""
        )
        cli_hint = render_cli_transparency_hint(
            ("README.md", "docs/**/*.md"), ('zcg consult-layer . --query "<topic>"', "zcg status .")
        )
        editor_html = ""
        if act_q == "new" and is_r3:
            new_dr = load_markdown_draft(ws, "doc:new")
            editor_html = render_doc_editor_html(
                pfx, str(new_dr["rel_path"]), str(new_dr["content"]), is_new=True,
                has_draft=bool(new_dr["has_draft"]), updated_at=str(new_dr["updated_at"]),
            )  # fmt: skip

        if not sel_doc:
            frag = (
                "<div id='zcg-docs-panel'><section class='zcg-card'>"
                f"{notice}{search_block}{pills_bar}"
                "<p class='zcg-muted-note'>No Markdown documents found in this space yet.</p>"
                f"{editor_html}{cli_hint}</section></div>"
            )
            return respond(
                req, html_fragment=frag,
                data={"capability": "docs_reader", "source": eff_src, "doc": "", "toc": [], "hits": hits},  # noqa: E501
            )  # fmt: skip
        src_root: Path = cur_s["root_dir"]
        try:
            doc_path = ensure_contained_path(src_root / sel_doc, src_root)
        except ValueError as exc:
            raise WebAppError(
                str(exc),
                error_code="PATH_CONTAINMENT_VIOLATION",
                http_status=int(HTTPStatus.FORBIDDEN),
            ) from exc
        rel_norm = str(doc_path.relative_to(src_root))
        if doc_path.suffix.lower() != ".md" or not doc_path.is_file():
            raise WebAppError(
                f"Markdown document not found: {sel_doc}",
                error_code="DOC_FILE_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        raw_md = doc_path.read_text(encoding="utf-8")
        doc_vis = extract_doc_visibility(raw_md)
        if cur_s["origin_group"] == "network" and doc_vis == "internal-r3":
            raise WebAppError(
                f"Document {rel_norm!r} is marked private (internal-r3) to its owning node",
                error_code="PRIVATE_DOC_R3_ONLY",
                http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )
        rendered_html, toc = render_markdown_document_html(raw_md)
        vis_chip = (
            f" <span class='zcg-chip'>{VISIBILITY_BADGES[doc_vis]}</span>"
            if eff_src == "self"
            else ""
        )
        can_edit = is_r3 and eff_src == "self" and rel_norm.startswith("docs/")
        if act_q == "edit" and can_edit:
            edit_dr = load_markdown_draft(ws, f"doc:{rel_norm}")
            ed_body = str(edit_dr["content"]) if edit_dr["has_draft"] else raw_md
            editor_html = render_doc_editor_html(
                pfx,
                rel_norm,
                ed_body,
                is_new=False,
                has_draft=bool(edit_dr["has_draft"]),
                updated_at=str(edit_dr["updated_at"]),
            )
        dirty_banner = (
            render_doc_dirty_banner_html(pfx, rel_norm)
            if (can_edit and is_workspace_path_dirty(ws, rel_norm))
            else ""
        )
        edit_btn = (
            f" <button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-get='{pfx}?source=self&amp;doc={quote(rel_norm)}&amp;action=edit' "
            "data-zcg-target='#zcg-docs-panel'>✏️ Edit</button>"
            if can_edit
            else (" <span class='zcg-badge'>Read-Only</span>" if eff_src != "self" else "")
        )
        src_q = quote(eff_src)
        file_links = "".join(
            f"<a class='zcg-tree__item{' zcg-tree__item--self' if f == rel_norm else ''}' "
            f"href='{pfx}?origin={eff_origin}&amp;source={src_q}&amp;doc={quote(f)}' "
            f"data-zcg-get='{pfx}?origin={eff_origin}&amp;source={src_q}&amp;doc={quote(f)}' "
            f"data-zcg-target='#zcg-docs-panel'><code>{html.escape(f)}</code></a>"
            for f in files
        )
        toc_links = " · ".join(
            f"<a href='#{html.escape(sl, True)}'>{html.escape(tx)}</a>" for sl, tx in toc
        )
        toc_bar = (
            "<nav class='zcg-doc-toc' aria-label='Document sections'>"
            f"<strong>On this page:</strong> {toc_links}</nav>"
            if len(toc) >= 2
            else ""
        )
        lbl_h = html.escape(str(cur_s["label"]))
        frag = (
            "<div id='zcg-docs-panel'><section class='zcg-card'>"
            f"{notice}{search_block}{pills_bar}"
            f"{editor_html}<div class='zcg-docs-reader'>"
            f"<aside class='zcg-docs-nav' aria-label='Document files'>{file_links}</aside>"
            "<article class='zcg-docs-article'>"
            f"<div class='zcg-doc-meta'><span class='zcg-badge'>{lbl_h}</span> "
            f"<code>{html.escape(rel_norm)}</code>{vis_chip}{edit_btn}</div>{toc_bar}"
            f"{dirty_banner}<div class='zcg-doc-body'>{rendered_html.value}</div>"
            f"</article></div>{cli_hint}</section></div>"
        )
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "docs_reader",
                "origin": eff_origin,
                "source": eff_src,
                "source_kind": cur_s["kind"],
                "doc": rel_norm,
                "hits": hits,
                "sources": discover_readable_sources(ws),
                "toc": [{"slug": sl, "title": tx} for sl, tx in toc],
            },
        )

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Browse and search knowledge space")
    def read_knowledge_doc(req: Request) -> WebResponse:
        return _render_space_response(req)

    @router.post("/draft", channel=DeliveryChannel.SWAP_SYNC, summary="Auto-save docs draft")
    def save_doc_draft(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_body_map(req)
        try:
            saved = save_markdown_draft(
                ws,
                draft_key=str(pl.get("draft_key") or ""),
                content=str(pl.get("content") or ""),
                rel_path=str(pl.get("rel_path") or ""),
            )
        except ValueError as exc:
            code = str(exc).partition(":")[0] or "INVALID_MARKDOWN_DRAFT"
            raise WebAppError(
                str(exc),
                error_code=code,
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                action=ErrorAction.FIX_INPUT,
            ) from exc
        frag = f"<div class='zcg-alert'>Draft saved ({saved['line_count']} lines).</div>"
        return respond(req, html_fragment=frag, data=saved)

    @router.post("/draft/discard", channel=DeliveryChannel.SWAP_SYNC, summary="Discard docs draft")
    def discard_doc_draft(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_body_map(req)
        draft_key = str(pl.get("draft_key") or req.query("draft_key", "")).strip()
        discard_markdown_draft(ws, draft_key)
        doc_hint = str(pl.get("doc") or req.query("doc", "")).strip()
        act_hint = str(pl.get("action") or req.query("action", "")).strip().lower()
        return _render_space_response(
            req,
            want_src="self" if doc_hint else "",
            force_doc=doc_hint,
            force_action=act_hint,
            notice="<div class='zcg-alert'>Discarded unapplied draft.</div>",
        )

    @router.post("/save", channel=DeliveryChannel.SWAP_SYNC, summary="Create or save docs/*.md")
    def save_doc(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_body_map(req)
        try:
            saved = save_knowledge_document(
                ws,
                rel_path=str(pl.get("rel_path") or ""),
                content=str(pl.get("content") or ""),
                template_kind=str(pl.get("template_kind") or "guide"),
                title=str(pl.get("title") or ""),
            )
        except ValueError as exc:
            code = str(exc).partition(":")[0] or "INVALID_DOC_SAVE"
            raise WebAppError(
                str(exc),
                error_code=code,
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                action=ErrorAction.FIX_INPUT,
            ) from exc
        saved_doc = str(saved["doc"])
        discard_markdown_draft(ws, "doc:new")
        discard_markdown_draft(ws, f"doc:{saved_doc}")
        d_h = html.escape(saved_doc)
        if str(pl.get("commit_now") or "") == "1":
            msg = str(pl.get("commit_message") or "").strip() or (
                f"docs(knowledge): update {saved_doc}"
            )
            try:
                com = commit_scoped_workspace_paths(ws, rel_paths=(saved_doc,), commit_message=msg)
            except ValueError as exc:
                _raise_commit_error(exc)
            sha_h = html.escape(str(com["commit_sha"]))
            note = (
                f"<div class='zcg-alert'>Saved <code>{d_h}</code> ({saved['lines']} lines) "
                f"and committed <code>{sha_h}</code>.</div>"
            )
        else:
            note = (
                f"<div class='zcg-alert'>Saved <code>{d_h}</code> ({saved['lines']} lines).</div>"
            )
        return _render_space_response(req, want_src="self", force_doc=saved_doc, notice=note)

    @router.post("/commit", channel=DeliveryChannel.SWAP_SYNC, summary="Commit docs/*.md path")
    def commit_doc(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_body_map(req)
        rel_p = str(pl.get("rel_path") or "").strip()
        try:
            res = commit_scoped_workspace_paths(
                ws, rel_paths=(rel_p,), commit_message=str(pl.get("commit_message") or "")
            )
        except ValueError as exc:
            _raise_commit_error(exc)
        sha_h = html.escape(res["commit_sha"])
        return respond(
            req,
            html_fragment=f"<div class='zcg-alert'>Committed <code>{sha_h}</code>.</div>",
            data=res,
        )

    return router
