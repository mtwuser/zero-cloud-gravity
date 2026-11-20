"""Unit tests for zcg.web.capabilities.appearance.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.auth.surface_access import SurfaceAccessPolicy, SurfaceRing
from zcg.web.capabilities.appearance import (
    DEFAULT_BRAND_LOGO_URL,
    UI_PREFS_COOKIE_NAME,
    build_appearance_template_context,
    can_viewer_travel_environments,
    create_appearance_router,
    encode_viewer_ui_prefs,
    parse_viewer_ui_prefs,
    resolve_plane_web_theme,
    sanitize_brand_logo_url,
)
from zcg.web.http.factory import WebAppState, create_web_app
from zcg.web.http.request import Message, Scope


async def _call(
    app: object,
    method: str,
    path: str,
    *,
    query: str = "",
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    in_hdrs = list(headers or [])
    if not any(k.lower() == b"host" for k, _ in in_hdrs):
        in_hdrs.append((b"host", b"portal.alpha.example"))
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": in_hdrs,
        "client": ("198.51.100.10", 44300),
    }
    sent: list[Message] = []
    consumed = False

    async def receive() -> Message:
        nonlocal consumed
        if consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)  # type: ignore[operator]
    resp_h = {
        bytes(k).decode("latin1"): bytes(v).decode("latin1") for k, v in sent[0].get("headers", [])
    }
    return int(sent[0]["status"]), resp_h, b"".join(bytes(m.get("body", b"")) for m in sent[1:])


class TestAppearance:
    """Verify two-layer web_theme + viewer accessibility prefs, env gating, and router mutations."""

    def test_theme_resolution_viewer_prefs_encoding_and_env_frame_gating_expected(self) -> None:
        """Verify plane theme overrides, logo sanitization, cookie parsing, and env gating."""
        # Arrange
        manifest = {
            "web_theme": {
                "preset": "nordic-slate",
                "accent": "emerald",
                "logo_url": "/avatar.png",
                "planes": {
                    "public_portal": {
                        "preset": "paper-light",
                        "accent": "sky",
                        "logo_url": "https://cdn.alpha.example/logo.svg",
                    }
                },
            }
        }

        # Act
        ws_theme = resolve_plane_web_theme(manifest, plane="workspace")
        pub_theme = resolve_plane_web_theme(manifest, plane="public_portal")
        fallback_theme = resolve_plane_web_theme({"web_theme": "invalid"}, plane="unknown")
        encoded = encode_viewer_ui_prefs(
            contrast="colorblind-safe", font_scale="112", motion="reduced"
        )
        parsed = parse_viewer_ui_prefs({UI_PREFS_COOKIE_NAME: encoded})
        parsed_def = parse_viewer_ui_prefs({UI_PREFS_COOKIE_NAME: "bad.999.bad"})
        pub_r0_ctx = build_appearance_template_context(
            manifest=manifest,
            cookies={UI_PREFS_COOKIE_NAME: encoded},
            plane="public_portal",
            active_env="dev",
            caller_ring="R0",
        )
        ws_r3_ctx = build_appearance_template_context(
            manifest=manifest,
            plane="workspace",
            active_env="dev",
            caller_ring="R3",
            allow_node_theme=True,
        )
        ws_bad_env_ctx = build_appearance_template_context(
            plane="workspace", active_env="unknown", caller_ring="R2"
        )

        # Assert
        assert sanitize_brand_logo_url("") == DEFAULT_BRAND_LOGO_URL
        assert sanitize_brand_logo_url("javascript:alert(1)") == DEFAULT_BRAND_LOGO_URL
        assert ws_theme == {
            "plane": "workspace",
            "preset": "nordic-slate",
            "accent": "emerald",
            "logo_url": "/avatar.png",
        }
        assert pub_theme["preset"] == "paper-light" and pub_theme["accent"] == "sky"
        assert fallback_theme["preset"] == "blueprint-dark"
        assert parsed == {
            "contrast": "colorblind-safe",
            "font_scale": "112",
            "motion": "reduced",
        }
        assert parsed_def == {"contrast": "inherit", "font_scale": "100", "motion": "standard"}
        with pytest.raises(ValueError, match="Invalid contrast"):
            encode_viewer_ui_prefs(contrast="neon")
        with pytest.raises(ValueError, match="Invalid font_scale"):
            encode_viewer_ui_prefs(font_scale="200")
        with pytest.raises(ValueError, match="Invalid motion"):
            encode_viewer_ui_prefs(motion="hyper")
        assert can_viewer_travel_environments(caller_ring="R0") is False
        assert can_viewer_travel_environments(caller_ring="R1") is False
        assert can_viewer_travel_environments(caller_ring="R2") is True
        assert can_viewer_travel_environments(caller_ring="R3") is True
        assert pub_r0_ctx["active_env_attr"] == "pro"
        assert str(pub_r0_ctx["env_frame_badge_html"]) == ""
        assert "Environment Travel" not in str(pub_r0_ctx["appearance_menu_html"])
        assert "Node Brand" not in str(pub_r0_ctx["appearance_menu_html"])
        assert ws_r3_ctx["active_env_attr"] == "dev"
        assert "DEV · Sandbox" in str(ws_r3_ctx["env_frame_badge_html"])
        assert "Environment Travel" in str(ws_r3_ctx["appearance_menu_html"])
        assert "Node Brand" in str(ws_r3_ctx["appearance_menu_html"])
        assert ws_bad_env_ctx["active_env_attr"] == "pro"

    def test_appearance_router_viewer_cookie_and_r3_node_theme_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET/POST /api/appearance endpoints, cookie domain scoping, and R3 guards."""
        # Arrange
        ws = tmp_path / "persona-profile"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "persona-profile", "layer_role": "workstation"}),
            encoding="utf-8",
        )
        states: list[WebAppState] = []
        app = create_web_app(
            routers=(create_appearance_router(ws, cookie_domains=("persona-profile.localhost",)),),
            state_out=states,
            allowed_hosts=("*",),
        )
        csrf_b = states[0].csrf_token.encode("ascii")

        pol = SurfaceAccessPolicy(default_ring=SurfaceRing.R0_PUBLIC, session_key="pol-sec-01")
        pol_states: list[WebAppState] = []
        no_ws_app = create_web_app(
            routers=(create_appearance_router(None, policy=pol),),
            state_out=pol_states,
            allowed_hosts=("*",),
        )
        pol_csrf_b = pol_states[0].csrf_token.encode("ascii")

        # Act
        st_get, _, b_get = asyncio.run(
            _call(app, "GET", "/api/appearance", headers=[(b"accept", b"application/json")])
        )
        st_pref_form, h_pref_form, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/viewer-prefs",
                body=b"contrast=high-contrast&font_scale=125&motion=reduced",
                headers=[
                    (b"host", b"dev.persona-profile.localhost:8790"),
                    (b"content-type", b"application/x-www-form-urlencoded"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_pref_bad, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/viewer-prefs",
                body=b'{"contrast":"invalid"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_pref_arr, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/viewer-prefs",
                body=b"[1, 2]",
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_pref_empty, h_pref_empty, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/viewer-prefs",
                body=b"",
                headers=[(b"x-zcg-csrf-token", csrf_b)],
            )
        )
        st_r0_forbid, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"all","preset":"paper-light"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_pol_forbid, _, _ = asyncio.run(
            _call(
                no_ws_app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"all","preset":"paper-light"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", pol_csrf_b),
                ],
            )
        )
        no_ws_r3_states: list[WebAppState] = []
        no_ws_r3_app = create_web_app(
            routers=(create_appearance_router(None),),
            state_out=no_ws_r3_states,
            allowed_hosts=("*",),
        )
        st_no_ws, _, _ = asyncio.run(
            _call(
                no_ws_r3_app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"all","preset":"paper-light"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-surface-ring", b"R3"),
                    (b"x-zcg-csrf-token", no_ws_r3_states[0].csrf_token.encode("ascii")),
                ],
            )
        )
        st_bad_theme, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"bad","preset":"paper-light"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-surface-ring", b"R3"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_bad_logo, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"all","preset":"paper-light","logo_url":"javascript:evil()"}',
                headers=[
                    (b"content-type", b"application/json"),
                    (b"x-zcg-surface-ring", b"R3"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_plane_ok, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"workspace","preset":"nordic-slate","accent":"emerald","logo_url":"/me.png"}',
                headers=[
                    (b"host", b"127.0.0.1:8790"),
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )
        st_all_ok, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=b'{"scope":"all","preset":"solar-warm","accent":"amber","logo_url":"/brand.svg"}',
                headers=[
                    (b"host", b"persona-profile.localhost:8790"),
                    (b"content-type", b"application/json"),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )

        mp_boundary = b"----ZcgBrandTestBoundary"
        mp_body = (
            b"------ZcgBrandTestBoundary\r\n"
            b'Content-Disposition: form-data; name="scope"\r\n\r\ncontrol_plane\r\n'
            b"------ZcgBrandTestBoundary\r\n"
            b'Content-Disposition: form-data; name="preset"\r\n\r\npaper-light\r\n'
            b"------ZcgBrandTestBoundary\r\n"
            b'Content-Disposition: form-data; name="brand_file"; filename="av.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
            b"\x89PNG\r\n\x1a\n1234\r\n"
            b"------ZcgBrandTestBoundary--\r\n"
        )
        st_mp_ok, _, _ = asyncio.run(
            _call(
                app,
                "POST",
                "/api/appearance/node-theme",
                body=mp_body,
                headers=[
                    (b"host", b"127.0.0.1:8790"),
                    (b"content-type", b"multipart/form-data; boundary=" + mp_boundary),
                    (b"x-zcg-csrf-token", csrf_b),
                ],
            )
        )

        # Assert
        assert (
            st_mp_ok == 200 and (ws / "surfaces/web/static/brand/control_plane-logo.png").is_file()
        )
        assert st_get == 200 and json.loads(b_get)["web_theme"]["preset"] == "blueprint-dark"
        assert st_pref_form == 200
        assert "zcg_ui_prefs=high-contrast.125.reduced" in h_pref_form["set-cookie"]
        assert "Domain=persona-profile.localhost" in h_pref_form["set-cookie"]
        assert st_pref_bad == 422
        assert st_pref_arr == 200
        assert st_pref_empty == 200 and "Domain=" not in h_pref_empty["set-cookie"]
        assert st_r0_forbid == 403 and st_pol_forbid == 403
        assert st_no_ws == 400
        assert st_bad_theme == 422 and st_bad_logo == 422
        assert st_plane_ok == 200 and st_all_ok == 200
        saved_m = json.loads((ws / NODE_MANIFEST_REL_PATH).read_text("utf-8"))
        assert saved_m["web_theme"]["preset"] == "solar-warm"
        assert saved_m["web_theme"]["logo_url"] == "/brand.svg"
