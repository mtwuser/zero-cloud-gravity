"""Unit tests for zcg.plugins.public_portals.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from zcg.plugins.portal_cv import (
    CVFieldEntry,
    CVProfileSpec,
    project_cv_by_disclosure_tier,
    render_cv_markdown,
    render_cv_print_a4_html,
)
from zcg.plugins.public_portals import (
    create_public_portal_router,
    render_public_portal_html,
)
from zcg.plugins.wallet_treasury import WalletRuntimeStore
from zcg.web.auth.security import SESSION_COOKIE
from zcg.web.auth.surface_access import (
    DISCLOSURE_TIER_HEADER,
    SURFACE_RING_HEADER,
    ExternalSubjectKind,
    SurfaceAccessPolicy,
    SurfaceRing,
    issue_scoped_surface_grant,
)
from zcg.web.http.factory import WebAppState, create_web_app
from zcg.web.http.request import ASGIApp, Message


async def _call_portal(
    app: ASGIApp,
    path: str,
    *,
    method: str = "GET",
    body: bytes = b"",
    query: str = "",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    raw_h = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
        "scheme": "https",
        "client": ("127.0.0.1", 52000),
    }
    sent = False
    out: list[Message] = []

    async def _recv() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def _send(msg: Message) -> None:
        out.append(msg)

    await app(scope, _recv, _send)
    st = int(out[0]["status"])
    resp_h = {
        bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
        for k, v in out[0].get("headers", [])
    }
    resp_b = b"".join(bytes(m.get("body", b"")) for m in out[1:])
    return st, resp_h, resp_b


class TestPublicPortals:
    """Verify 3-entity public R0 portals over base.html and ring-projected CV exports."""

    def test_cv_projection_markdown_print_a4_and_validation_guards_expected(self) -> None:
        """Verify monotonic R0..R3 CV field filtering, Markdown/A4 HTML output, and input guards."""
        # Arrange
        spec = CVProfileSpec.default_reference_spec(
            "pub-persona", public_domain="persona.example.org"
        )

        # Act
        p_r0 = project_cv_by_disclosure_tier(spec, effective_tier="core_summary")
        p_r1 = project_cv_by_disclosure_tier(spec, effective_tier="verified_competency")
        p_r3 = project_cv_by_disclosure_tier(spec, effective_tier="deep_context")
        md_txt = render_cv_markdown(p_r1)
        a4_html = render_cv_print_a4_html(p_r0)

        # Assert
        assert len(p_r0["disclosed_entries"]) == 2 and p_r0["withheld_count"] == 3
        assert len(p_r1["disclosed_entries"]) == 3 and p_r1["withheld_count"] == 2
        assert len(p_r3["disclosed_entries"]) == 5 and p_r3["withheld_count"] == 0
        assert "Verified Reference Systems" in md_txt and "contact@persona.example.org" in md_txt
        assert "@page{size:A4;margin:14mm;}" in str(a4_html)
        assert "@media print" in str(a4_html)
        with pytest.raises(ValueError, match="field_id"):
            CVFieldEntry(" ", "Lbl", "Val")
        with pytest.raises(ValueError, match="disclosure_tier"):
            CVFieldEntry("f1", "Lbl", "Val", disclosure_tier="unknown")
        with pytest.raises(ValueError, match="effective_tier"):
            project_cv_by_disclosure_tier(spec, effective_tier="bad_tier")

    def test_render_three_entity_portals_fragment_and_base_html_shell_expected(self) -> None:
        """Verify OSS, Personal CV, and Corporate portals render over base.html cleanly."""
        # Arrange
        oss_dom, oss_dev = "zerocloudgravity.org", "zerocloudgravity.dev"

        # Act
        oss_full = render_public_portal_html(
            portal_kind="oss-flagship-portal",
            node_id="zerocloudgravity",
            canonical_domain=oss_dom,
            secondary_domain=oss_dev,
            full_page=True,
        )
        cv_frag = render_public_portal_html(
            portal_kind="personal-portfolio-cv",
            node_id="pub-persona",
            canonical_domain="persona.example.org",
            caller_ring="R1",
            effective_tier="verified_competency",
            full_page=True,
        )
        corp_frag = render_public_portal_html(
            portal_kind="corporate-brand-portal",
            node_id="corp-alpha",
            canonical_domain="corp-alpha.example.com",
            secondary_domain="corp-alpha.example.net",
            caller_ring="R3",
            full_page=True,
        )
        corp_partial = render_public_portal_html(
            portal_kind="corporate-brand-portal",
            node_id="corp-alpha",
            canonical_domain="corp-alpha.example.com",
            full_page=False,
        )
        local_no_oidc = render_public_portal_html(
            portal_kind="personal-portfolio-cv",
            node_id="persona-work",
            canonical_domain="",
            full_page=True,
            login_enabled=False,
        )
        hub_disabled = render_public_portal_html(
            portal_kind="personal-constellation-hub",
            node_id="persona-profile",
            canonical_domain="persona-profile.localhost",
            manifest={"entity_kind": "individual", "public_exposure": {"mode": "disabled"}},
            full_page=True,
            login_enabled=False,
        )
        hub_facets = render_public_portal_html(
            portal_kind="personal-constellation-hub",
            node_id="persona-profile",
            canonical_domain="persona.example.org",
            manifest={
                "entity_kind": "individual",
                "public_exposure": {
                    "mode": "online",
                    "public_facets": [{"pillar": "work", "label": "Work", "summary": "CV"}],
                },
            },
            full_page=True,
            login_enabled=False,
        )

        # Assert
        assert "<!doctype html>" not in str(corp_partial)
        assert "Personal Root 0 Hub" in str(hub_disabled)
        assert 'id="contact"' not in str(hub_disabled)
        assert 'href="#overview"' not in str(cv_frag)
        assert "Subdomains &amp; Pillars" in str(hub_facets)
        assert 'id="contact"' in str(hub_facets)
        assert "<!doctype html>" in str(oss_full) and "zerocloudgravity.dev" in str(oss_full)
        assert 'data-zcg-plane="public-portal"' in str(oss_full)
        assert "Sign in with Google" in str(oss_full) and "zcg-burger" in str(oss_full)
        assert "Sign in with Google" not in str(local_no_oidc)
        assert "Home (persona-work)" in str(local_no_oidc)
        assert "Node Admin (/admin)" not in str(oss_full)
        assert 'data-island="spatial-atlas"' in str(oss_full)
        assert "/static/js/spatial-atlas.js" in str(oss_full)
        assert "2D/3D Spatial Atlas" in str(oss_full)
        assert "Download / Print A4 CV" in str(cv_frag) and "Caller Ring: R1" in str(cv_frag)
        assert "Account (R1)" in str(cv_frag) and "Node Admin (/admin)" not in str(cv_frag)
        assert "corp-alpha.example.net" in str(corp_frag) and "dept-finance" in str(corp_frag)
        assert "Node Admin (/admin)" in str(corp_frag) and "Account (R3)" in str(corp_frag)
        assert "Workspace (/)" in str(corp_frag) and "Session &amp; Identity" not in str(corp_frag)
        with pytest.raises(ValueError, match="portal_kind"):
            render_public_portal_html(
                portal_kind="invalid-kind", node_id="n", canonical_domain="x.org"
            )
        with pytest.raises(ValueError, match="portal_kind"):
            create_public_portal_router(portal_kind="invalid-kind")

    def test_portal_router_policy_elevation_stewardship_and_cv_downloads_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify /portal, /stewardship, /cv, /cv/print, /cv/download.md, and /cv/download.json."""
        # Arrange
        sess_k = "portal-sess-key"
        store = WalletRuntimeStore(tmp_path)
        store.register_watch_address(
            chain_family="evm",
            chain_reference="1",
            address="0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
            label="oss-reserve",
            ring_visibility="R0",
        )
        pol = SurfaceAccessPolicy(default_ring=SurfaceRing.R0_PUBLIC, session_key=sess_k)
        states: list[WebAppState] = []
        app_pol = create_web_app(
            routers=(
                create_public_portal_router(
                    portal_kind="personal-portfolio-cv",
                    node_id="pub-persona",
                    canonical_domain="persona.example.org",
                    workspace_dir=tmp_path,
                    policy=pol,
                ),
            ),
            state_out=states,
        )
        csrf_tok = states[0].csrf_token
        app_hdr = create_web_app(routers=(create_public_portal_router(),))
        r1_grant = issue_scoped_surface_grant(
            signing_key=sess_k,
            subject_id="recruiter@partner.example",
            ring=SurfaceRing.R1_SCOPED_EXTERNAL,
            external_kind=ExternalSubjectKind.GUEST,
        )
        r3_grant = issue_scoped_surface_grant(
            signing_key=sess_k, subject_id="owner@persona.example.org", ring=SurfaceRing.R3_OPERATOR
        )

        # Act
        st_html, _, b_html = asyncio.run(
            _call_portal(app_pol, "/portal", headers={"accept": "text/html"})
        )
        st_stew, _, b_stew = asyncio.run(_call_portal(app_pol, "/portal/stewardship"))
        st_stew_empty, _, b_stew_e = asyncio.run(_call_portal(app_hdr, "/portal/stewardship"))
        st_cv_r0, _, b_cv_r0 = asyncio.run(_call_portal(app_pol, "/portal/cv"))
        st_cv_r1, _, b_cv_r1 = asyncio.run(
            _call_portal(app_pol, "/portal/cv", headers={"cookie": f"{SESSION_COOKIE}={r1_grant}"})
        )
        st_cv_r3_prev, _, b_cv_prev = asyncio.run(
            _call_portal(
                app_pol,
                "/portal/cv",
                query="tier=core_summary",
                headers={"cookie": f"{SESSION_COOKIE}={r3_grant}"},
            )
        )
        st_hdr_cv, _, b_hdr_cv = asyncio.run(
            _call_portal(
                app_hdr,
                "/portal/cv",
                headers={
                    SURFACE_RING_HEADER: "R2",
                    DISCLOSURE_TIER_HEADER: "day1_onboarding",
                },
            )
        )
        st_prt, _, b_prt = asyncio.run(_call_portal(app_pol, "/portal/cv/print"))
        st_md, h_md, b_md = asyncio.run(_call_portal(app_pol, "/portal/cv/download.md"))
        st_js, h_js, b_js = asyncio.run(_call_portal(app_pol, "/portal/cv/download.json"))
        st_post_c, _, _ = asyncio.run(
            _call_portal(
                app_pol,
                "/portal/contact",
                method="POST",
                body=b"sender_name=Ada&sender_contact=ada%40example.org&message=Hello+CV",
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "x-zcg-csrf-token": csrf_tok,
                },
            )
        )

        # Assert
        assert st_post_c == 201
        assert st_html == 200 and b"<!doctype html>" in b_html
        assert st_stew == 200 and len(json.loads(b_stew)["public_reserve_accounts"]) == 1
        assert st_stew_empty == 200 and json.loads(b_stew_e)["public_reserve_accounts"] == []
        assert st_cv_r0 == 200 and json.loads(b_cv_r0)["effective_tier"] == "core_summary"
        assert st_cv_r1 == 200 and json.loads(b_cv_r1)["effective_tier"] == "verified_competency"
        assert st_cv_r3_prev == 200 and json.loads(b_cv_prev)["effective_tier"] == "core_summary"
        assert st_hdr_cv == 200 and json.loads(b_hdr_cv)["effective_tier"] == "day1_onboarding"
        assert st_prt == 200 and b"@page{size:A4;margin:14mm;}" in b_prt
        assert st_md == 200 and "pub-persona-cv-core_summary.md" in h_md["content-disposition"]
        assert b"# pub-persona Sovereign Architecture Profile" in b_md
        assert st_js == 200 and "pub-persona-cv-core_summary.json" in h_js["content-disposition"]
        assert json.loads(b_js)["withheld_count"] == 3
