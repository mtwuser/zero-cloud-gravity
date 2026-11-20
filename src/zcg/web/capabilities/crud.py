"""Declarative Frontend <-> Backend CRUD & Collection Persistence Engine ('create_crud_router').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import html
import itertools
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final, NoReturn

from zcg.core import domain
from zcg.core.sqlite_repo import SQLiteRepositoryAdapter
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.capabilities.crud_fields import CollectionLayout, FieldKind, ResourceFieldSpec
from zcg.web.http.channels import build_swap_response_headers
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui import components
from zcg.web.ui.templates import SafeHTML

DEFAULT_CRUD_PAGE_SIZE: Final[int] = 10
MAX_CRUD_PAGE_SIZE: Final[int] = 50

__all__ = [
    "DEFAULT_CRUD_PAGE_SIZE", "MAX_CRUD_PAGE_SIZE", "CollectionLayout", "CollectionRecord",
    "CollectionRepository", "CollectionSchema", "FieldKind", "ResourceFieldSpec",
    "create_crud_router",
]  # fmt: skip


@dataclass(frozen=True, slots=True)
class CollectionSchema:
    """Declarative resource schema driving SQLite WAL CRUD endpoints and collection views."""

    slug: domain.Slug
    title: domain.NaturalText
    fields: tuple[ResourceFieldSpec, ...]
    default_layout: CollectionLayout = CollectionLayout.CARDS
    title_field: str = ""
    subtitle_field: str = ""
    badge_field: str = ""
    body_field: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "slug", domain.validate_slug(self.slug))
        object.__setattr__(self, "title", domain.validate_natural_text(self.title))
        if not self.fields:
            raise ValueError("CollectionSchema.fields must not be empty")
        if not self.title_field:
            object.__setattr__(self, "title_field", self.fields[0].name)

    def validate_payload(
        self, payload: Mapping[str, Any], *, partial: bool = False,
        base_values: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:  # fmt: skip
        """Validate incoming payload fields into a clean dictionary."""
        seed = dict(base_values or {})
        return {
            f.name: seed[f.name]
            if partial and f.name not in payload and f.name in seed
            else f.coerce(payload.get(f.name))
            for f in self.fields
        }


@dataclass(frozen=True, kw_only=True)
class CollectionRecord(domain.DomainEntity):
    """Immutable L1 domain record persisted by CollectionRepository."""

    collection_slug: domain.Slug
    values: dict[str, Any]

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "collection_slug", domain.validate_slug(self.collection_slug))
        object.__setattr__(self, "values", dict(self.values))

    def to_dict(self) -> dict[str, Any]:
        """Serialize record with flattened field projections and ISO timestamps."""
        return {
            **self.values, "id": self.id, "collection_slug": self.collection_slug,
            "values": dict(self.values),
            "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(),
        }  # fmt: skip


class CollectionRepository(SQLiteRepositoryAdapter[CollectionRecord, str]):
    """Parameterized SQLite WAL repository for declarative CollectionRecord entities."""

    def __init__(self, db_path: Path, *, collection_slug: str, workspace_root: Path) -> None:
        self.table_name = f"crud_{domain.validate_slug(collection_slug).replace('-', '_')}"
        super().__init__(db_path, workspace_root=workspace_root)

    def to_record(self, entity: CollectionRecord) -> dict[str, Any]:
        """Serialize CollectionRecord for SQLite WAL storage."""
        return entity.to_dict()

    def from_record(self, record: Mapping[str, Any]) -> CollectionRecord:
        """Hydrate an immutable CollectionRecord from stored JSON fields."""
        raw_vals = record.get("values")
        return CollectionRecord(
            id=str(record["id"]), collection_slug=str(record["collection_slug"]),
            values=dict(raw_vals) if isinstance(raw_vals, Mapping) else {},
            created_at=datetime.fromisoformat(str(record["created_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
        )  # fmt: skip

    def query_records(
        self, *, schema: CollectionSchema, query: str = "",
        filters: Mapping[str, str] | None = None, page: int = 1,
        page_size: int = DEFAULT_CRUD_PAGE_SIZE,
    ) -> tuple[list[CollectionRecord], int, int]:  # fmt: skip
        """Search, filter, sort newest-first, and paginate records via itertools.islice."""
        q_norm = query.strip().lower()
        s_fields = tuple(f.name for f in schema.fields if f.searchable)
        eff_filters = {k: v.strip() for k, v in (filters or {}).items() if v.strip()}
        ordered = sorted(self.list_all(), key=lambda r: -r.created_at.timestamp())
        matched = [
            rec for rec in ordered
            if (not q_norm or any(q_norm in str(rec.values.get(fn, "")).lower() for fn in s_fields))
            and all(str(rec.values.get(fk, "")) == fv for fk, fv in eff_filters.items())
        ]  # fmt: skip
        eff_size = min(MAX_CRUD_PAGE_SIZE, max(1, page_size))
        total, total_pages = len(matched), max(1, math.ceil(len(matched) / eff_size))
        offset = (min(total_pages, max(1, page)) - 1) * eff_size
        return list(itertools.islice(matched, offset, offset + eff_size)), total, total_pages


def _extract_payload(req: Request) -> dict[str, Any]:
    if "application/x-www-form-urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body:
        return {}
    parsed = req.json()
    if not isinstance(parsed, dict):
        raise WebAppError(
            "CRUD payload must be a JSON object", error_code="INVALID_CRUD_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST), severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )  # fmt: skip
    return parsed


def _raise_not_found(schema: CollectionSchema, item_id: str) -> NoReturn:
    raise WebAppError(
        f"Record not found in {schema.slug}: {item_id}", error_code="CRUD_RECORD_NOT_FOUND",
        http_status=int(HTTPStatus.NOT_FOUND), severity=ErrorSeverity.WARNING,
    )  # fmt: skip


def _validate_or_422(
    schema: CollectionSchema, payload: Mapping[str, Any], *,
    partial: bool = False, base_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:  # fmt: skip
    try:
        return schema.validate_payload(payload, partial=partial, base_values=base_values)
    except ValueError as exc:
        raise WebAppError(
            str(exc), error_code="INVALID_CRUD_FIELDS",
            http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            severity=ErrorSeverity.WARNING, action=ErrorAction.FIX_INPUT,
        ) from exc  # fmt: skip


def _render_collection_body(
    schema: CollectionSchema, rows: list[dict[str, Any]], layout: CollectionLayout
) -> SafeHTML:
    msg, t_key = f"No {schema.title.lower()} recorded yet.", schema.title_field
    if layout == CollectionLayout.CARDS:
        return components.render_card_grid(
            items=rows, title_key=t_key, body_key=schema.body_field or t_key,
            subtitle_key=schema.subtitle_field, badge_key=schema.badge_field, empty_message=msg,
        )  # fmt: skip
    if layout == CollectionLayout.LIST:
        return components.render_item_list(
            items=rows, title_key=t_key, meta_key=schema.subtitle_field or schema.body_field,
            badge_key=schema.badge_field, empty_message=msg,
        )  # fmt: skip
    return components.render_table(
        columns=tuple((f.name, f.label) for f in schema.fields), rows=rows, empty_message=msg
    )


def _render_record_card(schema: CollectionSchema, rec: CollectionRecord) -> str:
    v = rec.values
    return components.render_card(
        title=str(v.get(schema.title_field, rec.id)),
        subtitle=str(v.get(schema.subtitle_field, "")) if schema.subtitle_field else "",
        badge=str(v.get(schema.badge_field, "")) if schema.badge_field else "",
        body=str(v.get(schema.body_field, "")) if schema.body_field else "",
        card_id=f"{schema.slug}-{rec.id}",
    ).value


def _render_crud_studio_controls(
    schema: CollectionSchema, pfx: str, tgt: str, q: str, flts: Mapping[str, str],
    layout: CollectionLayout, rows: list[dict[str, Any]],
) -> tuple[str, str]:  # fmt: skip
    pfx_h, tgt_h = html.escape(pfx, quote=True), html.escape(tgt, quote=True)
    f_ctrls: list[str] = []
    for f in (fld for fld in schema.fields if fld.filterable):
        cur_v = flts.get(f.name, "")
        opts_src = (
            f.choices if f.choices else (("true", "false") if f.kind == FieldKind.BOOL else ())
        )
        if opts_src:
            opts = "".join(
                f"<option value='{html.escape(c, quote=True)}'{' selected' if c == cur_v else ''}>"
                f"{html.escape(c)}</option>" for c in opts_src
            )  # fmt: skip
            f_ctrls.append(
                f"<select name='filter_{html.escape(f.name, quote=True)}' "
                f"aria-label='Filter {html.escape(f.label)}'>"
                f"<option value=''>All {html.escape(f.label)}</option>{opts}</select>"
            )
        else:
            f_ctrls.append(
                f"<input name='filter_{html.escape(f.name, quote=True)}' "
                f"value='{html.escape(cur_v, quote=True)}' "
                f"placeholder='Filter {html.escape(f.label)}'>"
            )
    v_opts = "".join(
        f"<option value='{lv.value}'{' selected' if lv == layout else ''}>"
        f"{lv.value.capitalize()}</option>" for lv in CollectionLayout
    )  # fmt: skip
    rst_btn = (
        f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='{pfx_h}' data-zcg-target='{tgt_h}'>Reset</button>"
        if q.strip() else ""
    )  # fmt: skip
    f_bar = (
        f"<form method='get' action='{pfx_h}' data-zcg-get='{pfx_h}' data-zcg-target='{tgt_h}' "
        f"class='zcg-filter-bar'><input type='search' name='q' value='{html.escape(q, quote=True)}' "  # noqa: E501
        f"placeholder='Search {html.escape(schema.title)}...'>{''.join(f_ctrls)}"
        f"<select name='view' aria-label='Layout view'>{v_opts}</select>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        f"Filter</button>{rst_btn}</form>"
    )
    in_fields: list[str] = []
    for f in schema.fields:
        fn_h, fl_h = html.escape(f.name, quote=True), html.escape(f.label)
        req_a = " required" if f.required and f.kind != FieldKind.BOOL else ""
        if f.choices:
            ch_o = "".join(f"<option value='{html.escape(c, quote=True)}'>{html.escape(c)}</option>" for c in f.choices)  # noqa: E501  # fmt: skip
            ctrl = f"<select name='{fn_h}'{req_a}>{ch_o}</select>"
        elif f.kind == FieldKind.LONG_TEXT:
            ctrl = f"<textarea name='{fn_h}' rows='2'{req_a}></textarea>"
        elif f.kind == FieldKind.BOOL:
            ctrl = f"<select name='{fn_h}'><option value='false'>No</option><option value='true'>Yes</option></select>"  # noqa: E501
        else:
            t_attr = "number" if f.kind == FieldKind.INT else "text"
            def_v = html.escape(str(f.default), quote=True) if f.default is not None else ""
            ctrl = f"<input type='{t_attr}' name='{fn_h}' value='{def_v}'{req_a}>"
        in_fields.append(f"<label>{fl_h}{ctrl}</label>")
    c_form = (
        "<details class='zcg-peer-channel' style='margin:0.55rem 0;'>"
        f"<summary class='zcg-peer-channel__head'><span><strong>+ Add {html.escape(schema.title)}"
        "</strong></span></summary><form method='post' "
        f"action='{pfx_h}' data-zcg-post='{pfx_h}' data-zcg-target='{tgt_h}' "
        f"class='zcg-peer-channel__body zcg-quick-add-bar'>{''.join(in_fields)}"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Create Record</button></form>"
        "</details>"
    )
    del_rows = "".join(
        f"<div id='crud-del-{html.escape(str(r['id']), quote=True)}' class='zcg-knowledge-row'>"
        f"<span><strong>{html.escape(str(r.get(schema.title_field, r['id'])))}</strong></span>"
        "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-delete='{pfx_h}/{html.escape(str(r['id']), quote=True)}' "
        f"data-zcg-target='{tgt_h}'>Delete</button></div>"
        for r in rows
    )
    del_sec = (
        f"<div class='zcg-knowledge-list' style='margin-top:0.55rem;'>{del_rows}</div>"
        if del_rows else ""
    )  # fmt: skip
    return f"{f_bar}{c_form}", del_sec


def create_crud_router(
    workspace_dir: Path, *, schema: CollectionSchema, prefix: str | None = None,
    rel_db_path: str | None = None, target_selector: str = "#zcg-capability-stage",
) -> APIRouter:  # fmt: skip
    """Create a declarative Frontend <-> Backend CRUD APIRouter for any CollectionSchema."""
    ws = workspace_dir.resolve()
    eff_prefix = prefix if prefix is not None else f"/api/collections/{schema.slug}"
    eff_db = rel_db_path or f".agents/telemetry/crud_{schema.slug}.sqlite3"
    repo = CollectionRepository(ws / eff_db, collection_slug=schema.slug, workspace_root=ws)
    router = APIRouter(prefix=eff_prefix, tags=(schema.slug,))

    def _render_panel(
        q: str = "", flts: Mapping[str, str] | None = None,
        layout: CollectionLayout | None = None, page: int = 1, size: int = DEFAULT_CRUD_PAGE_SIZE,
    ) -> tuple[str, dict[str, Any]]:  # fmt: skip
        eff_l, eff_f = layout or schema.default_layout, flts or {}
        items, total, pages = repo.query_records(schema=schema, query=q, filters=eff_f, page=page, page_size=size)  # noqa: E501  # fmt: skip
        eff_p, dicts = min(pages, page), [it.to_dict() for it in items]
        top_ui, del_ui = _render_crud_studio_controls(schema, eff_prefix, target_selector, q, eff_f, eff_l, dicts)  # noqa: E501  # fmt: skip
        pager = components.render_pagination(page=eff_p, total_pages=pages, base_url=eff_prefix, target_selector=target_selector)  # noqa: E501  # fmt: skip
        body_h = SafeHTML(top_ui + _render_collection_body(schema, dicts, eff_l).value + del_ui + pager.value)  # noqa: E501  # fmt: skip
        frag = (
            "<section class='zcg-card'><div class='zcg-card__header'>"
            f"<span class='zcg-muted-note'><code>{html.escape(schema.slug)}</code></span>"
            f"<span class='zcg-badge'>{total} records</span></div>{body_h.value}</section>"
            if target_selector == "#zcg-capability-stage"
            else components.render_card(title=schema.title, badge=str(total), body=body_h).value
        )
        return frag, {"collection": schema.slug, "layout": eff_l.value, "count": total, "page": eff_p, "total_pages": pages, "items": dicts}  # noqa: E501  # fmt: skip

    @router.get("", summary=f"Search, filter, and paginate {schema.title}")
    def list_items(req: Request) -> WebResponse:
        q, raw_v = req.query("q"), req.query("view", schema.default_layout.value).lower()
        layout = (
            CollectionLayout(raw_v) if raw_v in CollectionLayout._value2member_map_
            else schema.default_layout
        )  # fmt: skip
        rp, rs = req.query("page"), req.query("page_size")
        page = int(rp) if rp.isdigit() and int(rp) > 0 else 1
        size = int(rs) if rs.isdigit() and int(rs) > 0 else DEFAULT_CRUD_PAGE_SIZE
        flts = {f.name: req.query(f"filter_{f.name}") for f in schema.fields if f.filterable}
        frag, data = _render_panel(q, flts, layout, page, size)
        return respond(req, html_fragment=frag, data=data)

    @router.post("", summary=f"Create a {schema.title} record")
    def create_item(req: Request) -> WebResponse:
        vals = _validate_or_422(schema, _extract_payload(req))
        saved = repo.create(CollectionRecord(collection_slug=schema.slug, values=vals))
        hdrs = build_swap_response_headers(trigger=f"{schema.slug}Created")
        return respond(
            req, html_fragment=_render_panel()[0],
            data={"collection": schema.slug, "created": saved.to_dict()},
            status=int(HTTPStatus.CREATED), headers=hdrs,
        )  # fmt: skip

    @router.get("/{item_id}", summary=f"Retrieve a single {schema.title} record")
    def get_item(req: Request) -> WebResponse:
        found = repo.get_by_id(req.path_params["item_id"])
        if found is None:
            _raise_not_found(schema, req.path_params["item_id"])
        return respond(
            req, html_fragment=_render_record_card(schema, found),
            data={"collection": schema.slug, "item": found.to_dict()},
        )  # fmt: skip

    @router.put("/{item_id}", summary=f"Update an existing {schema.title} record")
    def update_item(req: Request) -> WebResponse:
        existing = repo.get_by_id(req.path_params["item_id"])
        if existing is None:
            _raise_not_found(schema, req.path_params["item_id"])
        merged = _validate_or_422(
            schema, _extract_payload(req), partial=True, base_values=existing.values
        )
        updated = CollectionRecord(
            id=existing.id, collection_slug=schema.slug, values=merged,
            created_at=existing.created_at, updated_at=datetime.now(UTC),
        )  # fmt: skip
        repo.update(updated)
        return respond(
            req, html_fragment=_render_record_card(schema, updated),
            data={"collection": schema.slug, "updated": updated.to_dict()},
            headers=build_swap_response_headers(trigger=f"{schema.slug}Updated"),
        )  # fmt: skip

    @router.delete("/{item_id}", summary=f"Delete a {schema.title} record")
    def delete_item(req: Request) -> WebResponse:
        item_id = req.path_params["item_id"]
        if not repo.delete(item_id):
            _raise_not_found(schema, item_id)
        hdrs = build_swap_response_headers(trigger=f"{schema.slug}Deleted")
        return respond(
            req, html_fragment=_render_panel()[0], headers=hdrs,
            data={"collection": schema.slug, "deleted": True, "id": item_id},
        )  # fmt: skip

    return router
