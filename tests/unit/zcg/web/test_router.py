"""Unit tests for zcg.web.router.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import pytest

from zcg.web.channels import DeliveryChannel
from zcg.web.request import Request, WebResponse
from zcg.web.router import APIRouter


def _echo_item(request: Request) -> WebResponse:
    """Return encoded item_id parameter."""
    return WebResponse(body=request.path_params.get("item_id", "").encode())


class TestRouter:
    """Verify APIRouter decorators, nested composition, 404/405 resolution, and OpenAPI 3.1."""

    def test_http_method_decorators_and_nested_router_composition_expected(self) -> None:
        """Verify GET/POST/PUT/PATCH/DELETE decorators and include_router prefix composition."""
        # Arrange
        root = APIRouter()
        child = APIRouter(prefix="items", tags=("inventory",))

        @root.get("")
        def _home(req: Request) -> WebResponse:
            return WebResponse(body=b"home")

        @child.post("")
        def _create(req: Request) -> WebResponse:
            return WebResponse(body=b"created")

        @child.put("{item_id}")
        def _replace(req: Request) -> WebResponse:
            return _echo_item(req)

        @child.patch("{item_id}")
        def _patch(req: Request) -> WebResponse:
            return _echo_item(req)

        @child.delete("{item_id}")
        def _delete(req: Request) -> WebResponse:
            return _echo_item(req)

        # Act
        root.include_router(child, prefix="api", tags=("v1",))
        direct = APIRouter()
        direct.include_router(child)
        match_home, allow_home = root.resolve("GET", "/")

        # Assert
        assert child.prefix == "items"
        assert len(direct.routes) == 4 and len(root.routes) == 5
        assert match_home is not None and allow_home == ()

    def test_resolve_extracts_url_decoded_params_and_distinguishes_404_vs_405_expected(
        self,
    ) -> None:
        """Verify URL-decoded path_params extraction, 405 allowed methods, and 404 misses."""
        # Arrange
        router = APIRouter(prefix="/api/items")
        router.add_route("GET", "/featured", _echo_item, channel=DeliveryChannel.SWAP_SYNC)
        router.add_route("GET", "/{item_id}", _echo_item)
        router.add_route("DELETE", "/{item_id}", _echo_item)

        # Act
        match_param, allow_param = router.resolve("GET", "/api/items/record%2042/")
        match_405, allow_405 = router.resolve("POST", "/api/items/featured")
        match_404, allow_404 = router.resolve("GET", "/unknown/path")

        # Assert
        assert match_param is not None and match_param.path_params == {"item_id": "record 42"}
        assert allow_param == ()
        assert match_405 is None and allow_405 == ("GET", "DELETE")
        assert match_404 is None and allow_404 == ()

    def test_build_openapi_paths_synthesizes_tags_parameters_and_channel_metadata_expected(
        self,
    ) -> None:
        """Verify OpenAPI 3.1 path generation with and without tags or path parameters."""
        # Arrange
        root = APIRouter()
        tagged = APIRouter(prefix="/items", tags=("catalog",))
        root.add_route("GET", "/", _echo_item, summary="Root health")
        tagged.add_route("GET", "/{item_id}", _echo_item)
        root.include_router(tagged, prefix="/v1", tags=("public",))

        # Act
        paths = root.build_openapi_paths()

        # Assert
        assert "tags" not in paths["/"]["get"]
        assert "parameters" not in paths["/"]["get"]
        item_op = paths["/v1/items/{item_id}"]["get"]
        assert item_op["tags"] == ["public", "catalog"]
        assert item_op["parameters"][0]["name"] == "item_id"
        assert item_op["x-delivery-channel"] == DeliveryChannel.ISLAND_SYNC.value

    def test_add_route_rejects_unsupported_http_method_and_duplicate_param_names_expected(
        self,
    ) -> None:
        """Verify bipolar guard rejection on invalid HTTP verbs and duplicate {param} tokens."""
        # Arrange
        router = APIRouter()

        # Act
        with pytest.raises(ValueError, match="Unsupported HTTP method") as exc_verb:
            router.add_route("TRACE", "/trace", _echo_item)
        with pytest.raises(ValueError, match="Duplicate path parameter") as exc_dup:
            router.add_route("GET", "/dup/{slug}/{slug}", _echo_item)

        # Assert
        assert "TRACE" in str(exc_verb.value)
        assert "slug" in str(exc_dup.value)
