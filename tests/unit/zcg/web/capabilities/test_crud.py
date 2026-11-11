"""Unit tests for zcg.web.capabilities.crud.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest

from zcg.web.capabilities.crud import (
    CollectionRecord,
    CollectionRepository,
    CollectionSchema,
    FieldKind,
    ResourceFieldSpec,
    create_crud_router,
)
from zcg.web.factory import create_web_app

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
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
        "headers": headers or [],
    }
    await app(scope, receive, send)
    hdrs = {k.decode("latin1"): v.decode("latin1") for k, v in sent[0].get("headers", [])}
    return int(sent[0]["status"]), hdrs, b"".join(m.get("body", b"") for m in sent if "body" in m)


def _sample_schema() -> CollectionSchema:
    return CollectionSchema(
        slug="catalog-items",
        title="Catalog Items",
        subtitle_field="category",
        badge_field="stage",
        body_field="notes",
        fields=(
            ResourceFieldSpec("title", "Title", FieldKind.TEXT),
            ResourceFieldSpec("category", "Category", FieldKind.SLUG, default="general"),
            ResourceFieldSpec(
                "stage",
                "Stage",
                FieldKind.CHOICE,
                choices=("draft", "active"),
                filterable=True,
                default="draft",
            ),
            ResourceFieldSpec("notes", "Notes", FieldKind.LONG_TEXT, required=False),
            ResourceFieldSpec(
                "featured", "Featured", FieldKind.BOOL, required=False, default=False
            ),
            ResourceFieldSpec("priority", "Priority", FieldKind.INT, required=False),
        ),
    )


class TestCrud:
    """Verify declarative FieldKind coercion, CollectionRepository, and CRUD router quadrants."""

    def test_field_spec_coercion_schema_defaults_and_repository_hydration_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify all 6 FieldKinds, optional defaults, schema guards, and repo hydration."""
        # Arrange
        schema = _sample_schema()
        minimal_schema = CollectionSchema(
            slug="minimal",
            title="Minimal",
            title_field="code",
            fields=(ResourceFieldSpec("code", "Code", FieldKind.SLUG),),
        )
        repo = CollectionRepository(
            tmp_path / ".agents/telemetry/min.sqlite3",
            collection_slug="minimal",
            workspace_root=tmp_path,
        )
        rec = CollectionRecord(collection_slug="minimal", values={"code": "iso-01"})

        # Act
        coerced = schema.validate_payload(
            {
                "title": "Specification A",
                "category": "",
                "stage": "active",
                "notes": None,
                "featured": "yes",
                "priority": "7",
            }
        )
        coerced_opt = schema.validate_payload(
            {"title": "Specification B", "category": "spec-a", "featured": True, "priority": ""}
        )
        hydrated_bad = repo.from_record(
            {
                "id": rec.id,
                "collection_slug": "minimal",
                "values": "not-a-dict",
                "created_at": rec.created_at.isoformat(),
                "updated_at": rec.updated_at.isoformat(),
            }
        )
        with pytest.raises(ValueError, match="must not be empty") as exc_empty:
            CollectionSchema(slug="bad", title="Bad", fields=())
        with pytest.raises(ValueError, match="must be one of") as exc_choice:
            schema.validate_payload({"title": "X", "stage": "invalid"})
        with pytest.raises(ValueError, match="must be an integer") as exc_int:
            schema.validate_payload({"title": "X", "priority": "nan"})

        # Assert
        assert minimal_schema.title_field == "code"
        assert coerced["category"] == "general" and coerced["notes"] == ""
        assert coerced["featured"] is True and coerced["priority"] == 7
        assert coerced_opt["priority"] is None and coerced_opt["stage"] == "draft"
        assert hydrated_bad.values == {}
        assert exc_empty.value is not None and exc_choice.value is not None
        assert exc_int.value is not None

    def test_collection_views_cards_list_table_search_and_filter_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify cards, list, and table HTML swaps plus JSON search and filter queries."""
        # Arrange
        tok = "csrf-crud-token-01"
        app = create_web_app(
            routers=(create_crud_router(tmp_path, schema=_sample_schema()),), csrf_token=tok
        )
        swap = [(b"hx-request", b"true")]
        swap_csrf = [*swap, (b"x-zcg-csrf-token", tok.encode())]
        form_hdr = [*swap_csrf, (b"content-type", b"application/x-www-form-urlencoded")]

        async def _scenario() -> dict[str, Any]:
            s_post1, _, _ = await _call(
                app,
                "POST",
                "/api/collections/catalog-items",
                body=json.dumps(
                    {"title": "Alpha Spec", "stage": "active", "notes": "Core"}
                ).encode(),
            )
            s_post2, _, b_post2 = await _call(
                app,
                "POST",
                "/api/collections/catalog-items",
                headers=form_hdr,
                body=urlencode({"title": "Beta Draft", "stage": "draft"}).encode(),
            )
            _, _, b_cards = await _call(
                app, "GET", "/api/collections/catalog-items", query="view=cards", headers=swap
            )
            _, _, b_list = await _call(
                app, "GET", "/api/collections/catalog-items", query="view=list", headers=swap
            )
            _, _, b_table = await _call(
                app, "GET", "/api/collections/catalog-items", query="view=table", headers=swap
            )
            _, _, b_fallback = await _call(
                app, "GET", "/api/collections/catalog-items", query="view=unknown"
            )
            _, _, b_flt = await _call(
                app,
                "GET",
                "/api/collections/catalog-items",
                query="q=alpha&filter_stage=active",
            )
            return {
                "s1": s_post1,
                "s2": s_post2,
                "p2": b_post2,
                "cards": b_cards,
                "list": b_list,
                "table": b_table,
                "fb": json.loads(b_fallback),
                "flt": json.loads(b_flt),
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert out["s1"] == 201 and out["s2"] == 201 and b"Beta Draft" in out["p2"]
        assert b"zcg-card-grid" in out["cards"]
        assert b"zcg-list" in out["list"]
        assert b"zcg-table" in out["table"]
        assert out["fb"]["layout"] == "cards" and out["fb"]["count"] == 2
        assert out["flt"]["count"] == 1 and out["flt"]["items"][0]["title"] == "Alpha Spec"

    def test_pagination_cutpoints_n_vs_n_plus_one_expected(self, tmp_path: Path) -> None:
        """Verify exact pagination cut-points when record count crosses page_size (2 vs 3)."""
        # Arrange
        minimal = CollectionSchema(
            slug="paged",
            title="Paged",
            fields=(ResourceFieldSpec("title", "Title", FieldKind.TEXT),),
        )
        app = create_web_app(
            routers=(create_crud_router(tmp_path, schema=minimal, prefix="/api/paged"),)
        )

        async def _scenario() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            for idx in range(2):
                await _call(
                    app, "POST", "/api/paged", body=json.dumps({"title": f"Item {idx}"}).encode()
                )
            _, _, raw_two = await _call(app, "GET", "/api/paged", query="page=1&page_size=2")
            await _call(app, "POST", "/api/paged", body=json.dumps({"title": "Item 2"}).encode())
            _, _, raw_three_p1 = await _call(app, "GET", "/api/paged", query="page=1&page_size=2")
            _, _, raw_three_p9 = await _call(app, "GET", "/api/paged", query="page=9&page_size=2")
            return json.loads(raw_two), json.loads(raw_three_p1), json.loads(raw_three_p9)

        # Act
        at_n, at_n_plus_1, clamped_last = asyncio.run(_scenario())

        # Assert
        assert at_n["total_pages"] == 1 and len(at_n["items"]) == 2
        assert at_n_plus_1["total_pages"] == 2 and len(at_n_plus_1["items"]) == 2
        assert clamped_last["page"] == 2 and len(clamped_last["items"]) == 1

    def test_single_item_get_partial_put_and_delete_json_and_swap_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET/{id}, partial PUT/{id}, JSON DELETE/{id}, and swap DELETE/{id}."""
        # Arrange
        tok = "csrf-crud-token-02"
        app = create_web_app(
            routers=(create_crud_router(tmp_path, schema=_sample_schema()),), csrf_token=tok
        )
        swap = [(b"hx-request", b"true")]
        swap_csrf = [*swap, (b"x-zcg-csrf-token", tok.encode())]

        async def _scenario() -> dict[str, Any]:
            _, _, c1 = await _call(
                app,
                "POST",
                "/api/collections/catalog-items",
                body=json.dumps({"title": "First", "stage": "draft"}).encode(),
            )
            _, _, c2 = await _call(
                app,
                "POST",
                "/api/collections/catalog-items",
                body=json.dumps({"title": "Second", "stage": "draft"}).encode(),
            )
            id1 = json.loads(c1)["created"]["id"]
            id2 = json.loads(c2)["created"]["id"]
            s_get, _, b_get = await _call(
                app, "GET", f"/api/collections/catalog-items/{id1}", headers=swap
            )
            s_put, _, b_put = await _call(
                app,
                "PUT",
                f"/api/collections/catalog-items/{id1}",
                body=json.dumps({"stage": "active"}).encode(),
            )
            s_del_json, _, b_del_json = await _call(
                app, "DELETE", f"/api/collections/catalog-items/{id1}"
            )
            s_del_swap, _, b_del_swap = await _call(
                app, "DELETE", f"/api/collections/catalog-items/{id2}", headers=swap_csrf
            )
            return {
                "s_get": s_get,
                "b_get": b_get,
                "s_put": s_put,
                "put": json.loads(b_put),
                "s_del_json": s_del_json,
                "del_json": json.loads(b_del_json),
                "s_del_swap": s_del_swap,
                "b_del_swap": b_del_swap,
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert out["s_get"] == 200 and b"First" in out["b_get"]
        assert out["s_put"] == 200 and out["put"]["updated"]["title"] == "First"
        assert out["put"]["updated"]["stage"] == "active"
        assert out["s_del_json"] == 200 and out["del_json"]["deleted"] is True
        assert out["s_del_swap"] == 200 and out["b_del_swap"] == b""

    def test_bipolar_csrf_validation_payload_and_404_not_found_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 403 CSRF on swap without token, 400 non-dict JSON, 422 missing field, and 404."""
        # Arrange
        app = create_web_app(routers=(create_crud_router(tmp_path, schema=_sample_schema()),))
        swap_no_csrf = [(b"hx-request", b"true")]

        async def _scenario() -> tuple[int, int, int, int, int, int]:
            s_csrf, _, _ = await _call(
                app, "POST", "/api/collections/catalog-items", headers=swap_no_csrf, body=b"{}"
            )
            s_400, _, _ = await _call(app, "POST", "/api/collections/catalog-items", body=b"[1, 2]")
            s_422, _, _ = await _call(app, "POST", "/api/collections/catalog-items", body=b"")
            s_get_404, _, _ = await _call(app, "GET", "/api/collections/catalog-items/missing")
            s_put_404, _, _ = await _call(
                app, "PUT", "/api/collections/catalog-items/missing", body=b"{}"
            )
            s_del_404, _, _ = await _call(app, "DELETE", "/api/collections/catalog-items/missing")
            return s_csrf, s_400, s_422, s_get_404, s_put_404, s_del_404

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (403, 400, 422, 404, 404, 404)
