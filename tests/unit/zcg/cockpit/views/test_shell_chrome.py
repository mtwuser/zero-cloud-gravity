"""Unit tests for zcg.cockpit.views.shell_chrome.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from zcg.cockpit.views import shell_chrome
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.auth.security import WebAppError
from zcg.web.auth.surface_access import SURFACE_RING_HEADER, SurfaceAccessPolicy, SurfaceRing
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import Message


async def _invoke_http(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    client_host: str = "127.0.0.1",
) -> tuple[int, dict[str, str], bytes]:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    sent: list[Message] = []

    async def _recv() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def _send(msg: Message) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode(),
        "headers": raw_headers,
        "client": (client_host, 51000),
    }
    await app(scope, _recv, _send)
    hdrs = {
        bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
        for k, v in sent[0].get("headers", [])
    }
    out = b"".join(bytes(m.get("body", b"")) for m in sent if m["type"] == "http.response.body")
    return int(sent[0]["status"]), hdrs, out


class TestShellChrome:
    """Verify human role labels, cross-node user preferences, user menu, and settings router."""

    def test_resolve_human_role_label_and_avatar_initials_across_entities_expected(self) -> None:
        """Verify personal constellation pillars avoid corporate jargon and resolve initials."""
        # Arrange
        ind_cases = (
            ("persona-hub", "workstation", "Personal Hub"),
            ("profile", "project", "Personal Hub"),
            ("persona-profile", "project", "Personal Hub"),
            ("persona-security", "squad", "Personal Security"),
            ("custom-guard", "domain-policy", "Personal Security"),
            ("persona-tutor", "department", "Study & Tutor"),
            ("persona-work", "department", "Career & Ventures"),
            ("persona-wallet", "squad", "Patrimony & Wallet"),
            ("persona-game", "squad", "Game & Lab"),
            ("persona-custom", "squad", "Personal Pillar"),
            ("gov-es", "knowledge", "Knowledge Corpus"),
            ("sci-economic", "department", "Knowledge Corpus"),
        )
        org_cases = (
            ("corp-iso", "corporate", "Corporate Root 0"),
            ("dept-ops", "department", "Department"),
            ("sec-pol", "domain-policy", "Domain Policy"),
            ("squad-api", "squad", "Squad"),
            ("svc-billing", "project", "Project"),
            ("ws-dev", "workstation", "Workstation Hub"),
            ("edge-1", "service-node", "Service Node"),
            ("eu-west", "environment-cluster", "Environment Cluster"),
            ("custom-unit", "guild-lead", "Guild Lead"),
        )

        # Act
        ind_out = [
            shell_chrome.resolve_human_role_label(nid, role, entity_kind="individual")
            for nid, role, _ in ind_cases
        ]
        org_out = [
            shell_chrome.resolve_human_role_label(nid, role, entity_kind="enterprise")
            for nid, role, _ in org_cases
        ]
        initials = (
            shell_chrome.resolve_avatar_initials("persona.owner@example.org"),
            shell_chrome.resolve_avatar_initials("persona-wallet"),
            shell_chrome.resolve_avatar_initials("z"),
            shell_chrome.resolve_avatar_initials("   ---   "),
        )

        # Assert
        assert ind_out == [exp for _, _, exp in ind_cases]
        assert org_out == [exp for _, _, exp in org_cases]
        assert initials == ("PO", "PW", "Z", "OP")

    def test_user_preferences_resolution_persistence_and_validation_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify user preferences cascade (manifest -> Root 0 runtime -> cookie) and validation."""
        # Arrange
        root_ws = tmp_path / "persona-profile"
        child_ws = tmp_path / "persona-wallet"
        (root_ws / "system").mkdir(parents=True)
        (child_ws / "system").mkdir(parents=True)
        (root_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-profile",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "governing_root_id": "persona-profile",
                    "interaction_language": "es",
                }
            ),
            encoding="utf-8",
        )
        child_manifest = {
            "layer_id": "persona-wallet",
            "layer_role": "squad",
            "entity_kind": "individual",
            "governing_root_id": "persona-profile",
            "upstream_layer": {"layer_id": "persona-profile"},
        }
        (child_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(child_manifest), encoding="utf-8")

        # Act
        default_prefs = shell_chrome.resolve_effective_user_prefs(child_ws, child_manifest)
        saved = shell_chrome.persist_user_prefs(
            child_ws,
            child_manifest,
            language="es",
            contrast="dark",
            font_scale="112",
            motion="reduced",
            persist_local=True,
            is_https=True,
            request_host="pro.wallet.persona-profile.localhost",
            cookie_domains=("persona-profile.localhost",),
        )
        from_disk = shell_chrome.resolve_effective_user_prefs(child_ws, child_manifest)
        from_cookie = shell_chrome.resolve_effective_user_prefs(
            child_ws,
            child_manifest,
            cookies={"zcg_ui_prefs": "light.125.standard.fr"},
        )
        three_part_cookie = shell_chrome.resolve_effective_user_prefs(
            child_ws,
            child_manifest,
            cookies={"zcg_ui_prefs": "high-contrast.100.reduced"},
        )
        cookie_only = shell_chrome.persist_user_prefs(
            child_ws,
            child_manifest,
            language="de",
            contrast="inherit",
            font_scale="100",
            motion="standard",
            persist_local=False,
            is_https=False,
            request_host="127.0.0.1",
            cookie_domains=("persona-profile.localhost",),
        )
        # Corrupt runtime file falls back cleanly
        prefs_file = root_ws / shell_chrome.USER_PREFS_REL_PATH
        prefs_file.write_text("[]", encoding="utf-8")
        non_dict_fallback = shell_chrome.resolve_effective_user_prefs(
            root_ws, {"interaction_language": "invalid"}
        )
        prefs_file.write_text("{bad-json", encoding="utf-8")
        bad_json_fallback = shell_chrome.resolve_effective_user_prefs(root_ws, {})

        # Assert
        assert default_prefs["language"] == "en"
        assert saved["prefs"] == {
            "contrast": "dark",
            "font_scale": "112",
            "motion": "reduced",
            "language": "es",
        }
        assert "Domain=persona-profile.localhost" in saved["set_cookie_header"]
        assert from_disk["language"] == "es" and from_disk["contrast"] == "dark"
        assert from_cookie == {
            "contrast": "light",
            "font_scale": "125",
            "motion": "standard",
            "language": "fr",
        }
        assert three_part_cookie["contrast"] == "high-contrast"
        assert three_part_cookie["language"] == "es"
        assert "Domain=" not in cookie_only["set_cookie_header"]
        assert non_dict_fallback["language"] == "en"
        assert bad_json_fallback["contrast"] == "inherit"

        for lg_v, c_v, s_v, m_v in (
            ("xx", "inherit", "100", "standard"),
            ("en", "neon", "100", "standard"),
            ("en", "inherit", "200", "standard"),
            ("en", "inherit", "100", "turbo"),
        ):
            with pytest.raises(ValueError, match="Invalid"):
                shell_chrome.persist_user_prefs(
                    root_ws, {}, language=lg_v, contrast=c_v, font_scale=s_v, motion=m_v
                )

    def test_render_user_account_menu_and_brand_card_across_rings_expected(self) -> None:
        """Verify R0 sign-in CTA vs R1/R2 member avatar vs R3 operator menu and brand card."""
        # Arrange
        brand_theme = {
            "preset": "paper-light", "accent": "emerald", "logo_url": "/static/img/logo.svg",
        }  # fmt: skip

        # Act
        r0_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="pub-persona", entity_kind="individual", layer_role="knowledge", caller_ring="R0",  # noqa: E501
        ))  # fmt: skip
        r0_no_oidc_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="pub-persona", caller_ring="R0", login_enabled=False,
        ))  # fmt: skip
        sample_const = (
            "<details class='zcg-menu-constellation' open><summary class='zcg-burger__divider "
            "zcg-menu-constellation__toggle'>1-Hop Nodes (1) <span aria-hidden='true'>▾</span>"
            "</summary><div class='zcg-menu-constellation__list'></div></details>"
        )
        r2_child_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="dept-ops", entity_kind="enterprise", layer_role="department",
            caller_ring="R2", subject_id="ops@corp.example", root_node_id="corp-root",
            root_href="http://dev.corp-root.localhost:8710/", public_portal_enabled=True,
            health_state="OPTIMAL", language_code="en", has_active_session=True,
            constellation_html=sample_const, active_plane="portal",
        ))  # fmt: skip
        r2_off_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="dept-eng", root_node_id="corp-root",
            root_href="http://corp.localhost:8710/", root_online=False, caller_ring="R2",
            public_portal_enabled=False,
        ))  # fmt: skip
        r3_root_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="persona-profile", entity_kind="individual", layer_role="workstation",
            caller_ring="R3", subject_id="", root_node_id="persona-profile", root_href="",
            public_portal_enabled=False, health_state="ATTENTION", language_code="es",
            health_notes=("sync_safety: dirty=2",), active_plane="admin",
        ))  # fmt: skip
        atlas_html = str(shell_chrome.render_user_account_menu_html(
            layer_id="persona-profile", entity_kind="individual", layer_role="workstation",
            caller_ring="R3", active_plane="atlas",
        ))  # fmt: skip
        brand_card = str(
            shell_chrome.render_node_brand_settings_card_html(theme=brand_theme, plane="workspace")
        )

        # Assert
        assert "Sign in with Google" in r0_html and "/settings" not in r0_html
        assert r0_no_oidc_html == ""
        assert "/admin" not in r0_html
        assert "Account (R2)" in r2_child_html and "↑ corp-root</a>" in r2_child_html
        assert "zcg-settings-btn" in r2_child_html and "zcg-atlas-icon-btn" in r2_child_html
        assert "aria-label='Network Atlas (/atlas)'" in r2_child_html
        assert "data-zcg-nav-view='atlas'" not in r2_child_html
        assert r2_child_html.index("zcg-user-menu__head") < r2_child_html.index(
            "aria-label='Network Atlas (/atlas)'"
        )
        assert r2_child_html.index("Workspace (/)") < r2_child_html.index("1-Hop Nodes (1)")
        assert r2_child_html.index("1-Hop Nodes (1)") < r2_child_html.index("Sign Out")
        assert "Docs &amp; Knowledge" not in r2_child_html and "Node Surfaces" not in r2_child_html
        assert "User Scope" not in r2_child_html
        assert "corp-root · Offline" in r2_off_html and "aria-disabled='true'" in r2_off_html
        assert "<a class='is-active' aria-current='page' href='/'>" in r2_off_html
        assert "Public Web (/portal)" not in r2_off_html
        assert "1-Hop Nodes" not in r2_off_html and "aria-label='Network Atlas (/atlas)'" in (
            r2_off_html
        )
        assert "<a class='is-active' aria-current='page' href='/portal?format=html'>" in (
            r2_child_html
        )
        assert "/admin" not in r2_child_html
        assert "Account (R3)" in r3_root_html and "Personal Hub" in r3_root_html
        assert "★ Root 0</span><strong>persona-profile</strong>" in r3_root_html
        assert "Sign Out" not in r3_root_html and "Public Web (/portal)" not in r3_root_html
        assert "<a class='is-active' aria-current='page' href=\"/admin\">" in r3_root_html
        assert "sync_safety: dirty=2" in r3_root_html
        assert "zcg-atlas-icon-btn is-active' href='/atlas' aria-current='page'" in atlas_html
        assert "<a class='is-active' aria-current='page' href='/'>" not in atlas_html
        assert "/api/appearance/node-theme" in brand_card and "paper-light" in brand_card

    def test_shell_chrome_router_admin_and_user_settings_endpoints_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET /admin (R3 gate) and GET/POST /settings (HTML, JSON, errors)."""
        # Arrange
        ws = tmp_path / "persona-profile"
        ws_child = tmp_path / "persona-work"
        (ws / "system").mkdir(parents=True)
        (ws_child / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({
                "layer_id": "persona-profile", "layer_role": "workstation",
                "entity_kind": "individual", "governing_root_id": "persona-profile",
            }),
            encoding="utf-8",
        )  # fmt: skip
        (ws_child / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({
                "layer_id": "persona-work", "layer_role": "department",
                "entity_kind": "individual", "governing_root_id": "persona-profile",
            }),
            encoding="utf-8",
        )  # fmt: skip
        csrf = "csrf-ui1-token"
        pol = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R0_PUBLIC,
            session_key="sess-secret-key",
            loopback_operator_bypass=False,
        )

        def _fake_settings(env_code: str, ring: str, cookies: dict[str, str]) -> bytes:
            lang = cookies.get("lang_probe", "none")
            return f"<!doctype html><meta name=\"zcg-csrf-token\" content=\"\"><body data-env='{env_code}' data-ring='{ring}'>{lang}</body>".encode()  # noqa: E501

        rtr_guarded = shell_chrome.create_shell_chrome_router(
            ws, csrf_token=csrf, active_env="pro", policy=pol,
            cookie_domains=("persona-profile.localhost",), settings_renderer=_fake_settings,
        )  # fmt: skip
        app_guarded = create_web_app(
            title="Guarded", version="1.2.0", routers=(rtr_guarded,), csrf_token=csrf
        )
        rtr_open = shell_chrome.create_shell_chrome_router(
            ws, csrf_token=csrf, active_env="dev", policy=None,
            cookie_domains=("persona-profile.localhost",), settings_renderer=_fake_settings,
        )  # fmt: skip
        app_open = create_web_app(
            title="Open", version="1.2.0", routers=(rtr_open,), csrf_token=csrf
        )
        rtr_child = shell_chrome.create_shell_chrome_router(
            ws_child, csrf_token=csrf, active_env="pro", policy=None, settings_renderer=_fake_settings  # noqa: E501
        )  # fmt: skip
        app_child = create_web_app(
            title="Child", version="1.2.0", routers=(rtr_child,), csrf_token=csrf
        )

        async def _exercise() -> dict[str, Any]:
            base_c = {"x-zcg-csrf-token": csrf, "cookie": f"zcg_csrf={csrf}"}
            json_c = {"content-type": "application/json", **base_c}
            st_403, _, b_403 = await _invoke_http(app_guarded, "GET", "/admin", client_host="198.51.100.10")  # noqa: E501  # fmt: skip
            st_set_403, _, b_set_403 = await _invoke_http(app_guarded, "GET", "/settings", client_host="198.51.100.10")  # noqa: E501  # fmt: skip
            st_set, _, b_set = await _invoke_http(app_open, "GET", "/admin", query="env=tst", headers={SURFACE_RING_HEADER: "R3", "cookie": "lang_probe=ok"})  # noqa: E501  # fmt: skip
            st_pref_html, _, b_pref_html = await _invoke_http(app_open, "GET", "/settings", headers={"accept": "text/html", SURFACE_RING_HEADER: "R3"})  # noqa: E501  # fmt: skip
            st_pref_json, _, b_pref_json = await _invoke_http(app_child, "GET", "/settings", headers={"accept": "application/json", SURFACE_RING_HEADER: "R1"})  # noqa: E501  # fmt: skip
            st_post_form, h_post_form, _ = await _invoke_http(
                app_open, "POST", "/settings",
                headers={"content-type": "application/x-www-form-urlencoded", "host": "persona-profile.localhost:8790", SURFACE_RING_HEADER: "R3", **base_c},  # noqa: E501
                body=b"language=es&contrast=dark&font_scale=112&motion=reduced",
            )  # fmt: skip
            st_post_json, _, b_post_json = await _invoke_http(
                app_open, "POST", "/settings", headers={SURFACE_RING_HEADER: "R2", **json_c},
                body=b'{"language":"fr","contrast":"light","font_scale":"100","motion":"standard"}',
            )  # fmt: skip
            st_post_empty, _, _ = await _invoke_http(app_open, "POST", "/settings", headers={SURFACE_RING_HEADER: "R1", **base_c}, body=b"")  # noqa: E501  # fmt: skip
            st_bad_json, _, _ = await _invoke_http(app_open, "POST", "/settings", headers=json_c, body=b"[]")  # noqa: E501  # fmt: skip
            st_bad_val, _, _ = await _invoke_http(app_open, "POST", "/settings", headers=json_c, body=b'{"language":"invalid"}')  # noqa: E501  # fmt: skip
            return {
                "st_403": st_403, "b_403": b_403, "st_set_403": st_set_403,
                "b_set_403": b_set_403, "st_set": st_set, "b_set": b_set,
                "st_pref_html": st_pref_html, "b_pref_html": b_pref_html,
                "st_pref_json": st_pref_json, "b_pref_json": b_pref_json,
                "st_post_form": st_post_form, "h_post_form": h_post_form,
                "st_post_json": st_post_json, "b_post_json": b_post_json,
                "st_post_empty": st_post_empty, "st_bad_json": st_bad_json,
                "st_bad_val": st_bad_val,
            }  # fmt: skip

        # Act
        res = asyncio.run(_exercise())

        # Assert
        assert res["st_403"] == 403 and b"NODE_ADMIN_OPERATOR_REQUIRED" in res["b_403"]
        assert res["st_set_403"] == 403 and b"USER_SETTINGS_AUTH_REQUIRED" in res["b_set_403"]
        assert res["st_set"] == 200 and b"csrf-ui1-token" in res["b_set"]
        assert b"data-env='tst'" in res["b_set"] and b"ok" in res["b_set"]
        assert res["st_pref_html"] == 200 and b"User Settings" in res["b_pref_html"]
        assert (
            b"zcg-settings-btn is-active' href='/settings' aria-current='page'"
            in res["b_pref_html"]
        )
        assert b'href="/settings"' in res["b_pref_html"]
        assert b"Environment Inspection" not in res["b_pref_html"]
        assert b"Back to persona-profile" not in res["b_pref_html"]
        assert res["st_pref_json"] == 200
        assert json.loads(res["b_pref_json"])["scope"] == "user_settings"
        assert res["st_post_form"] == 200
        assert "zcg_ui_prefs=dark.112.reduced.es" in res["h_post_form"]["set-cookie"]
        assert res["h_post_form"]["hx-refresh"] == "true"
        assert res["st_post_json"] == 200
        assert json.loads(res["b_post_json"])["prefs"]["language"] == "fr"
        assert res["st_post_empty"] == 200
        assert res["st_bad_json"] == 422
        assert res["st_bad_val"] == 422

        # Direct WebAppError sanity check on non-R3 settings guard helper
        with pytest.raises(WebAppError, match="Operator"):
            shell_chrome.require_operator_settings_ring("R2")
