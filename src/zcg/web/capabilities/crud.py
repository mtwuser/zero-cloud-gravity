"""Declarative Frontend <-> Backend CRUD & Collection Persistence Engine ('create_crud_router').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

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
from zcg.web import components
from zcg.web.channels import BaseStrEnum, build_swap_response_headers
from zcg.web.request import Request, WebResponse, respond, respond_empty
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

DEFAULT_CRUD_PAGE_SIZE: Final[int] = 10
MAX_CRUD_PAGE_SIZE: Final[int] = 50


class FieldKind(BaseStrEnum):
    """Typed scalar domains supported by declarative CRUD resource fields."""

    TEXT, LONG_TEXT, SLUG = "text", "long_text", "slug"
    CHOICE, BOOL, INT = "choice", "bool", "int"


class CollectionLayout(BaseStrEnum):
    """Presentation layouts supported by collection endpoints."""

    CARDS, LIST, TABLE = "cards", "list", "table"


@dataclass(frozen=True, slots=True)
class ResourceFieldSpec:
    """Declarative validation and query contract for a single resource field."""

    name: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    required: bool = True
    choices: tuple[str, ...] = ()
    searchable: bool = True
    filterable: bool = False
    default: Any = None

    def coerce(self, raw: object) -> Any:
        """Validate and coerce an incoming scalar value according to FieldKind."""
        if raw is None or (
            isinstance(raw, str) and not raw.strip() and self.kind != FieldKind.BOOL
        ):
            if self.default is not None:
                return self.default
            if not self.required:
                return "" if self.kind in (FieldKind.TEXT, FieldKind.LONG_TEXT) else None
            raise ValueError(f"Field '{self.name}' is required")
        if self.kind == FieldKind.TEXT:
            return domain.validate_natural_text(str(raw))
        if self.kind == FieldKind.LONG_TEXT:
            return domain.validate_long_text(str(raw))
        if self.kind == FieldKind.SLUG:
            return domain.validate_slug(str(raw).strip())
        if self.kind == FieldKind.CHOICE:
            val = str(raw).strip()
            if val not in self.choices:
                raise ValueError(f"Field '{self.name}' must be one of {self.choices}")
            return val
        if self.kind == FieldKind.BOOL:
            return (
                raw.strip().lower() in ("1", "true", "yes", "on")
                if isinstance(raw, str)
                else bool(raw)
            )
        try:
            return int(str(raw).strip())
        except ValueError as exc:
            raise ValueError(f"Field '{self.name}' must be an integer") from exc


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
        self,
        payload: Mapping[str, Any],
        *,
        partial: bool = False,
        base_values: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
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
            **self.values,
            "id": self.id,
            "collection_slug": self.collection_slug,
            "values": dict(self.values),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


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
            id=str(record["id"]),
            collection_slug=str(record["collection_slug"]),
            values=dict(raw_vals) if isinstance(raw_vals, Mapping) else {},
            created_at=datetime.fromisoformat(str(record["created_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
        )

    def query_records(
        self,
        *,
        schema: CollectionSchema,
        query: str = "",
        filters: Mapping[str, str] | None = None,
        page: int = 1,
        page_size: int = DEFAULT_CRUD_PAGE_SIZE,
    ) -> tuple[list[CollectionRecord], int, int]:
        """Search, filter, sort newest-first, and paginate records via itertools.islice."""
        q_norm = query.strip().lower()
        s_fields = tuple(f.name for f in schema.fields if f.searchable)
        eff_filters = {k: v.strip() for k, v in (filters or {}).items() if v.strip()}
        ordered = sorted(self.list_all(), key=lambda r: -r.created_at.timestamp())
        matched = [
            rec
            for rec in ordered
            if (not q_norm or any(q_norm in str(rec.values.get(fn, "")).lower() for fn in s_fields))
            and all(str(rec.values.get(fk, "")) == fv for fk, fv in eff_filters.items())
        ]
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
            "CRUD payload must be a JSON object",
            error_code="INVALID_CRUD_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return parsed


def _raise_not_found(schema: CollectionSchema, item_id: str) -> NoReturn:
    raise WebAppError(
        f"Record not found in {schema.slug}: {item_id}",
        error_code="CRUD_RECORD_NOT_FOUND",
        http_status=int(HTTPStatus.NOT_FOUND),
        severity=ErrorSeverity.WARNING,
    )


def _validate_or_422(
    schema: CollectionSchema,
    payload: Mapping[str, Any],
    *,
    partial: bool = False,
    base_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return schema.validate_payload(payload, partial=partial, base_values=base_values)
    except ValueError as exc:
        raise WebAppError(
            str(exc),
            error_code="INVALID_CRUD_FIELDS",
            http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        ) from exc


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


def create_crud_router(
    workspace_dir: Path,
    *,
    schema: CollectionSchema,
    prefix: str | None = None,
    rel_db_path: str | None = None,
    target_selector: str = "#v_out",
) -> APIRouter:
    """Create a declarative Frontend <-> Backend CRUD APIRouter for any CollectionSchema."""
    ws = workspace_dir.resolve()
    eff_prefix = prefix if prefix is not None else f"/api/collections/{schema.slug}"
    eff_db = rel_db_path or f".agents/telemetry/crud_{schema.slug}.sqlite3"
    repo = CollectionRepository(ws / eff_db, collection_slug=schema.slug, workspace_root=ws)
    router = APIRouter(prefix=eff_prefix, tags=(schema.slug,))

    @router.get("", summary=f"Search, filter, and paginate {schema.title}")
    def list_items(req: Request) -> WebResponse:
        q, raw_v = req.query("q"), req.query("view", schema.default_layout.value).lower()
        layout = (
            CollectionLayout(raw_v)
            if raw_v in CollectionLayout._value2member_map_
            else schema.default_layout
        )
        rp, rs = req.query("page"), req.query("page_size")
        page = int(rp) if rp.isdigit() and int(rp) > 0 else 1
        size = int(rs) if rs.isdigit() and int(rs) > 0 else DEFAULT_CRUD_PAGE_SIZE
        flts = {f.name: req.query(f"filter_{f.name}") for f in schema.fields if f.filterable}
        items, total, pages = repo.query_records(
            schema=schema, query=q, filters=flts, page=page, page_size=size
        )
        eff_p, dicts = min(pages, page), [it.to_dict() for it in items]
        sbar = components.render_search_bar(
            action_url=eff_prefix, target_selector=target_selector, query=q
        )
        pager = components.render_pagination(
            page=eff_p, total_pages=pages, base_url=eff_prefix, target_selector=target_selector
        )
        body_h = SafeHTML(
            sbar.value + _render_collection_body(schema, dicts, layout).value + pager.value
        )
        frag = components.render_card(title=schema.title, badge=str(total), body=body_h).value
        data = {
            "collection": schema.slug, "layout": layout.value, "count": total,
            "page": eff_p, "total_pages": pages, "items": dicts,
        }  # fmt: skip
        return respond(req, html_fragment=frag, data=data)

    @router.post("", summary=f"Create a {schema.title} record")
    def create_item(req: Request) -> WebResponse:
        vals = _validate_or_422(schema, _extract_payload(req))
        saved = repo.create(CollectionRecord(collection_slug=schema.slug, values=vals))
        hdrs = build_swap_response_headers(trigger=f"{schema.slug}Created")
        return respond(
            req, html_fragment=_render_record_card(schema, saved),
            data={"collection": schema.slug, "created": saved.to_dict()},
            status=int(HTTPStatus.CREATED), headers=hdrs,
        )  # fmt: skip

    @router.get("/{item_id}", summary=f"Retrieve a single {schema.title} record")
    def get_item(req: Request) -> WebResponse:
        found = repo.get_by_id(req.path_params["item_id"])
        if found is None:
            _raise_not_found(schema, req.path_params["item_id"])
        return respond(
            req,
            html_fragment=_render_record_card(schema, found),
            data={"collection": schema.slug, "item": found.to_dict()},
        )

    @router.put("/{item_id}", summary=f"Update an existing {schema.title} record")
    def update_item(req: Request) -> WebResponse:
        existing = repo.get_by_id(req.path_params["item_id"])
        if existing is None:
            _raise_not_found(schema, req.path_params["item_id"])
        merged = _validate_or_422(
            schema, _extract_payload(req), partial=True, base_values=existing.values
        )
        updated = CollectionRecord(
            id=existing.id,
            collection_slug=schema.slug,
            values=merged,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
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
        if req.is_partial_swap:
            return respond_empty(headers=hdrs)
        return respond(
            req,
            html_fragment="",
            data={"collection": schema.slug, "deleted": True, "id": item_id},
            headers=hdrs,
        )

    return router
