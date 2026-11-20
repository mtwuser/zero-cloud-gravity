"""Unit tests for zcg.web.capabilities.spatial_atlas.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from zcg.web.auth.security import WebAppError
from zcg.web.capabilities.spatial_atlas import (
    VALID_PROXIMITY_ACTIONS,
    VALID_SPATIAL_RENDER_MODES,
    create_spatial_atlas_router,
    render_spatial_atlas_html,
)
from zcg.web.capabilities.spatial_layout import (
    SpatialNodeSpec,
    build_reference_spatial_presets,
    compute_exploded_scene_layout,
)
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse


def _make_request(
    method: str,
    path: str,
    *,
    query_string: str = "",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode("latin1"),
        "headers": raw_headers,
    }
    return Request(scope, body)


class TestSpatialAtlas:
    """Verify Zone.Z4 Non-Photorealistic Blueprint HTML5 Canvas, WCAG parity, and APIRouter."""

    def test_blueprint_html_render_modes_and_wcag_table_parity_expected(self) -> None:
        """Verify Float32Array Blueprint HTML fragment, full page, and WCAG table parity."""
        # Arrange
        presets = build_reference_spatial_presets()
        nodes, edges = presets["constellation-4-pillar"]
        scene = compute_exploded_scene_layout(nodes, edges, explosion=0.35, seed=42)
        csrf_val = "".join(("tok-", "123"))

        # Act
        frag_html = render_spatial_atlas_html(
            scene,
            preset_names=tuple(presets),
            active_preset="constellation-4-pillar",
            mode="blueprint-3d",
            full_page=False,
            csrf_token=csrf_val,
        )
        page_html = render_spatial_atlas_html(
            scene,
            preset_names=tuple(presets),
            active_preset="constellation-4-pillar",
            mode="accessible-table",
            full_page=True,
            csrf_token=csrf_val,
        )

        # Assert
        assert set(VALID_SPATIAL_RENDER_MODES) == {
            "blueprint-3d",
            "blueprint-2d",
            "accessible-table",
        }
        assert 'data-zcg-surface="cockpit"' in frag_html
        assert 'data-island="spatial-atlas"' in frag_html
        assert "data-atlas-lens" in frag_html
        assert "data-atlas-lens-desc" in frag_html
        assert 'data-hydrate="eager"' in frag_html
        assert "<h3>2D/3D Network Atlas</h3>" not in frag_html
        assert "<script" not in frag_html.lower()
        assert 'aria-label="Spatial Atlas Topological Parity Table"' in frag_html
        assert "<!doctype html>" in page_html.lower()
        assert "<h3>2D/3D Network Atlas</h3>" in page_html
        assert "/static/js/spatial-atlas.js" in page_html
        assert "hidden" in page_html
        with pytest.raises(ValueError, match="Unsupported spatial render mode"):
            render_spatial_atlas_html(scene, mode="vr-headset")
        with pytest.raises(ValueError, match="Unsupported spatial lens"):
            render_spatial_atlas_html(scene, active_lens="gps-fine")

    def test_spatial_atlas_router_html_json_scene_and_proximity_actions_expected(self) -> None:
        """Verify GET '', GET '/scene', and POST '/action' across HTML, JSON, and form inputs."""
        # Arrange
        router = create_spatial_atlas_router()
        m_get_root, _ = router.resolve("GET", "/api/spatial-atlas")
        m_get_scene, _ = router.resolve("GET", "/api/spatial-atlas/scene")
        m_post_act, _ = router.resolve("POST", "/api/spatial-atlas/action")
        assert m_get_root is not None and m_get_scene is not None and m_post_act is not None

        req_html = _make_request(
            "GET",
            "/api/spatial-atlas",
            query_string="preset=enterprise-dual-zone&explosion=0.4&mode=blueprint-2d",
            headers={"accept": "text/html"},
        )
        req_swap = _make_request(
            "GET",
            "/api/spatial-atlas",
            headers={"hx-request": "true"},
        )
        req_json = _make_request(
            "GET",
            "/api/spatial-atlas",
            query_string=(
                "format=json&preset=unknown-preset&lens=bad&explosion=bad&seed=bad&mode=bad"
            ),
        )
        req_scene = _make_request(
            "GET",
            "/api/spatial-atlas/scene",
            query_string=(
                "preset=attested-public-federation&lens=permission-ring-hierarchy"
                "&explosion=0.65&seed=99"
            ),
        )
        req_act_json = _make_request(
            "POST",
            "/api/spatial-atlas/action",
            body=json.dumps(
                {"action": "+A", "source_id": "persona-work", "target_id": "corp-alpha"}
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        req_act_form = _make_request(
            "POST",
            "/api/spatial-atlas/action",
            body=b"action=-A&source_id=persona-work&target_id=corp-alpha",
            headers={"content-type": "application/x-www-form-urlencoded", "hx-request": "true"},
        )
        req_act_reconcile = _make_request(
            "POST",
            "/api/spatial-atlas/action",
            body=json.dumps(
                {"action": "\u00b1A", "source_id": "persona-tutor", "target_id": "sci-maths"}
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

        # Act
        res_html = m_get_root.route.handler(req_html)
        res_swap = m_get_root.route.handler(req_swap)
        res_json = m_get_root.route.handler(req_json)
        res_scene = m_get_scene.route.handler(req_scene)
        res_act_json = m_post_act.route.handler(req_act_json)
        res_act_form = m_post_act.route.handler(req_act_form)
        res_act_rec = m_post_act.route.handler(req_act_reconcile)

        # Assert
        assert isinstance(res_html, WebResponse)
        assert isinstance(res_swap, WebResponse)
        assert isinstance(res_json, WebResponse)
        assert isinstance(res_scene, WebResponse)
        assert isinstance(res_act_json, WebResponse)
        assert isinstance(res_act_form, WebResponse)
        assert isinstance(res_act_rec, WebResponse)
        assert res_html.channel == DeliveryChannel.IMMERSIVE_SYNC
        assert b"<!doctype html>" in res_html.body.lower()
        assert res_swap.content_type.startswith("text/html")
        assert res_json.content_type.startswith("application/json")
        scene_doc = json.loads(res_scene.body.decode("utf-8"))
        assert scene_doc["preset"] == "attested-public-federation"
        assert scene_doc["lens"] == "permission-ring-hierarchy"
        assert scene_doc["explosion"] == pytest.approx(0.65)
        act_doc = json.loads(res_act_json.body.decode("utf-8"))
        assert act_doc["action"] in VALID_PROXIMITY_ACTIONS
        assert act_doc["intent"] == "link-propose"
        assert b"distance-decouple" in res_act_form.body
        rec_doc = json.loads(res_act_rec.body.decode("utf-8"))
        assert rec_doc["intent"] == "reconcile-diff-consult"

    def test_spatial_atlas_router_action_validation_errors_expected(self) -> None:
        """Verify POST '/action' rejects non-object JSON, invalid action codes, and self-links."""
        # Arrange
        custom_presets = {"minimal": ((SpatialNodeSpec("n1", "Node 1", "squad", 50),), ())}
        router = create_spatial_atlas_router(presets=custom_presets)
        m_post, _ = router.resolve("POST", "/api/spatial-atlas/action")
        assert m_post is not None
        req_list = _make_request(
            "POST",
            "/api/spatial-atlas/action",
            body=b"[1, 2]",
            headers={"content-type": "application/json"},
        )
        req_empty = _make_request("POST", "/api/spatial-atlas/action", body=b"")
        req_same = _make_request(
            "POST",
            "/api/spatial-atlas/action",
            body=json.dumps({"action": "+A", "source_id": "n1", "target_id": "n1"}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

        # Act
        with pytest.raises(WebAppError) as err_list:
            m_post.route.handler(req_list)
        with pytest.raises(WebAppError) as err_empty:
            m_post.route.handler(req_empty)
        with pytest.raises(WebAppError) as err_same:
            m_post.route.handler(req_same)

        # Assert
        assert err_list.value.error_code == "INVALID_SPATIAL_ACTION_PAYLOAD"
        assert err_empty.value.error_code == "INVALID_PROXIMITY_ACTION"
        assert err_same.value.error_code == "INVALID_PROXIMITY_ENDPOINTS"
