"""Vendor-neutral RFC 7636 OIDC S256 PKCE session elevation, identity bar, and APIRouter.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import hmac
import html
import secrets
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Final, NoReturn

from zcg.web.auth import oidc_tokens, security, surface_access
from zcg.web.auth.oidc_tokens import JwtSignatureVerifier, VerifiedOidcClaims
from zcg.web.auth.surface_access import (
    ExternalSubjectKind,
    SurfaceAccessPolicy,
    SurfacePrincipal,
    SurfaceRing,
)
from zcg.web.auth.tls import format_set_cookie_header
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import HTML_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, TemplateCatalog, render_icon

PKCE_COOKIE: Final[str] = "zcg_oidc_pkce"
DEFAULT_PKCE_TTL_SEC: Final[int] = 600
DEFAULT_SESSION_TTL_SEC: Final[int] = 28_800
VALID_ELEVATION_RINGS: Final[tuple[str, ...]] = ("R0", "R1", "R2", "R3")
_RING_BY_CODE: Final[dict[str, SurfaceRing]] = {
    "R1": SurfaceRing.R1_SCOPED_EXTERNAL, "R2": SurfaceRing.R2_NETWORK_MEMBER,
    "R3": SurfaceRing.R3_OPERATOR,
}  # fmt: skip
_DEV_PERSONAS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("R0", "anonymous", "", "R0 Public"), ("R1", "guest@partner.example", "", "R1 Scoped Guest"),
    ("R2", "finance@corp-alpha.example", "dept-finance", "R2 Finance"),
    ("R2", "ops@corp-alpha.example", "dept-ops", "R2 Operations"),
    ("R3", "operator@zerocloudgravity.org", "maintainers", "R3 Operator"),
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class OidcSessionConfig:
    """Vendor-neutral RFC 7636 OIDC S256 PKCE and R0..R3 progressive session configuration."""

    session_signing_key: str
    provider_id: str = "generic-oidc"
    provider_label: str = "OIDC Identity"
    authorization_endpoint: str = ""
    allowed_issuers: tuple[str, ...] = ()
    client_id: str = ""
    redirect_uri: str = "/auth/oidc/callback"
    domain_hint: str = ""
    domain_hint_param: str = "login_hint"
    infer_domain_from_email: bool = False
    domain_infer_issuers: tuple[str, ...] = ()
    expected_audience: str = ""
    jwt_assertion_key: str = ""
    jwt_verifier: JwtSignatureVerifier | None = None
    allowed_workspace_domains: tuple[str, ...] = ()
    allowed_workspace_groups: tuple[str, ...] = ()
    operator_emails: tuple[str, ...] = ()
    member_emails: tuple[str, ...] = ()
    scoped_external_emails: tuple[str, ...] = ()
    cookie_domains: tuple[str, ...] = ()
    allow_dev_persona_switch: bool = False

    def __post_init__(self) -> None:
        if not self.session_signing_key.strip():
            raise ValueError("session_signing_key must be non-blank")

    @property
    def login_enabled(self) -> bool:
        """Return True when both OAuth 2.0 client_id and authorization_endpoint are configured."""
        return bool(self.client_id.strip() and self.authorization_endpoint.strip())

    @property
    def effective_audience(self) -> str:
        """Return explicit expected_audience or fall back to client_id."""
        return self.expected_audience.strip() or self.client_id.strip()


def _fail(
    msg: str, code: str, status: HTTPStatus | int,
    act: security.ErrorAction = security.ErrorAction.NONE,
) -> NoReturn:  # fmt: skip
    raise security.WebAppError(
        msg, error_code=code, http_status=int(status),
        severity=security.ErrorSeverity.WARNING, action=act,
    )  # fmt: skip


def _sanitize_return_to(raw_path: str) -> str:
    clean = raw_path.strip()
    bad = not clean.startswith("/") or clean.startswith("//") or any(c in clean for c in "\\\r\n")
    return "/dashboard" if bad else clean


def _extract_host_only(req: Request) -> str:
    return req.headers.get("host", "").partition(":")[0].strip().lower().strip("[]")


def _is_loopback_request(req: Request) -> bool:
    host = _extract_host_only(req)
    return bool(host) and (
        host in surface_access.LOOPBACK_CLIENT_HOSTS or host.endswith(".localhost")
    )


def _matching_cookie_domain(req: Request, cookie_domains: tuple[str, ...]) -> str:
    host = _extract_host_only(req)
    for raw in cookie_domains:
        dom = raw.strip().lower().lstrip(".")
        if dom and (host == dom or host.endswith(f".{dom}")):
            return dom
    return ""


def _clear_session_cookie(is_https: bool, domain: str = "") -> str:
    return format_set_cookie_header(
        security.SESSION_COOKIE, "", is_https=is_https, same_site="Lax", max_age=0, domain=domain
    )


def _issue_session_cookie(
    p: SurfacePrincipal, *, signing_key: str, is_https: bool, now_ts: float, domain: str = ""
) -> str:  # fmt: skip
    grant = surface_access.issue_scoped_surface_grant(
        signing_key=signing_key, subject_id=p.subject_id, ring=p.ring,
        external_kind=p.external_kind, disclosure_tier=p.max_disclosure_tier,
        groups=p.groups, expires_at=now_ts + DEFAULT_SESSION_TTL_SEC,
    )  # fmt: skip
    return format_set_cookie_header(
        security.SESSION_COOKIE, grant, is_https=is_https,
        same_site="Lax", max_age=DEFAULT_SESSION_TTL_SEC, domain=domain,
    )  # fmt: skip


def resolve_oidc_principal_from_claims(
    claims: VerifiedOidcClaims, config: OidcSessionConfig
) -> SurfacePrincipal:
    """Map verified OIDC claims onto monotonic R0..R3 SurfacePrincipal rings."""
    ops = {e.strip().lower() for e in config.operator_emails if e.strip()}
    mems = {e.strip().lower() for e in config.member_emails if e.strip()}
    exts = {e.strip().lower() for e in config.scoped_external_emails if e.strip()}
    doms = {d.strip().lower() for d in config.allowed_workspace_domains if d.strip()}
    grps = {g.strip().lower() for g in config.allowed_workspace_groups if g.strip()}
    em, gt = claims.email, claims.groups
    if em in ops:
        return SurfacePrincipal(
            SurfaceRing.R3_OPERATOR, em, max_disclosure_tier="deep_context", groups=gt
        )
    dom_ok = bool(doms) and claims.hosted_domain in doms
    if em in mems or (dom_ok and (not grps or bool(grps.intersection(gt)))):
        return SurfacePrincipal(
            SurfaceRing.R2_NETWORK_MEMBER, em, max_disclosure_tier="day1_onboarding", groups=gt
        )
    if em in exts:
        return SurfacePrincipal(
            SurfaceRing.R1_SCOPED_EXTERNAL, em, ExternalSubjectKind.GUEST,
            max_disclosure_tier="verified_competency", groups=gt,
        )  # fmt: skip
    return SurfacePrincipal(SurfaceRing.R0_PUBLIC, "anonymous")


def render_identity_posture_bar_html(
    principal: SurfacePrincipal, *, login_enabled: bool, dev_switch_enabled: bool,
    is_https: bool, prefix: str = "/auth", provider_label: str = "OIDC Identity",
) -> SafeHTML:  # fmt: skip
    """Render WCAG 2.2 AA progressive OIDC identity and R0..R3 ring posture bar."""
    tls_lbl = "HTTPS / TLS 1.3 Verified" if is_https else "Loopback Secure Context"
    tls_ic = render_icon("lock" if is_https else "shield")
    grps_s = ", ".join(principal.groups) or "none"
    pref_h = html.escape(prefix.rstrip("/"), quote=True)
    prov_h = html.escape(provider_label.strip() or "OIDC Identity")
    login_b = (
        f"<a class='zcg-btn zcg-btn--sm' href='{pref_h}/oidc/login'>{render_icon('globe')} "
        f"Sign in with {prov_h} (PKCE S256)</a>" if login_enabled
        else "<span class='zcg-chip'>OIDC Client Unconfigured (Zero-Secret Mode)</span>"
    )  # fmt: skip
    logout_b = (
        f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' data-zcg-post="
        f"'{pref_h}/logout' data-zcg-target='#zcg-identity-bar'>{render_icon('lock')} "
        "Sign Out (Reset R0)</button>" if principal.ring != SurfaceRing.R0_PUBLIC else ""
    )  # fmt: skip
    dev_b = (
        "<div class='zcg-tabs' style='margin-top:0.55rem;' role='group' aria-label="
        "'Loopback validation persona switcher'><small style='align-self:center;margin-right:.4rem'"
        ">Loopback QA Personas:</small>" + "".join(
            f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' data-zcg-post="
            f"'{pref_h}/dev-elevate?ring={r}&amp;subject_id={s}&amp;groups={g}' "
            f"data-zcg-target='#zcg-identity-bar'>{lbl}</button>" for r, s, g, lbl in _DEV_PERSONAS
        ) + "</div>" if dev_switch_enabled else ""
    )  # fmt: skip
    rv, rl = html.escape(principal.ring.value), html.escape(principal.ring.label)
    sb, dt = html.escape(principal.subject_id), html.escape(principal.max_disclosure_tier)
    return SafeHTML(
        "<section id='zcg-identity-bar' class='zcg-card' data-zcg-surface='cockpit' aria-label="
        "'Identity and Surface Ring Posture'><div class='zcg-card__header'><h2>"
        f"{render_icon('shield')} Progressive Identity &amp; Ring Posture</h2><span class="
        f"'zcg-badge'>{tls_ic} {tls_lbl}</span></div><p><strong>Active Ring:</strong> <code>{rv}"
        f"</code> ({rl}) · <strong>Subject:</strong> <code>{sb}</code> · <strong>Groups:</strong> "
        f"<code>{html.escape(grps_s)}</code> · <strong>Disclosure Ceiling:</strong> <code>{dt}"
        f"</code></p><div class='zcg-tabs'>{login_b}{logout_b}</div>{dev_b}</section>"
    )


def _redirect_302(url: str, cookie_h: str) -> WebResponse:
    return WebResponse(
        int(HTTPStatus.FOUND), HTML_CONTENT_TYPE, b"",
        DeliveryChannel.ISLAND_SYNC, {"location": url, "set-cookie": cookie_h},
    )  # fmt: skip


def _wrap_full_identity_page(fragment: SafeHTML, csrf_token: str = "") -> str:
    nav = (
        "<div class='zcg-tabs' style='margin-bottom:0.85rem;'>"
        "<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/'>← Workspace (/)</a>"
        "<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/portal?format=html'>"
        "Public Web (/portal)</a></div>"
    )
    ctx = {
        "csrf_token": csrf_token, "title": "Identity & Surface Ring Session",
        "content": SafeHTML(f"<div class='zcg-stage'>{nav}{fragment}</div>"),
    }  # fmt: skip
    return str(TemplateCatalog().render("base.html", ctx))


def _parse_elevate_payload(req: Request) -> tuple[str, str, tuple[str, ...]]:
    ct = req.content_type.lower()
    parsed = req.json() if (req.body and "application/json" in ct) else None
    raw: dict[str, Any] = parsed if isinstance(parsed, dict) else (req.form() if req.body else {})
    ring_s = str(raw.get("ring") or req.query("ring", "")).strip().upper()
    sub_s = str(raw.get("subject_id") or req.query("subject_id", "")).strip()
    raw_g = raw.get("groups") if "groups" in raw else req.query("groups", "")
    items = raw_g if isinstance(raw_g, list) else str(raw_g).split(",")
    return ring_s, sub_s, tuple(str(x).strip().lower() for x in items if str(x).strip())


def create_oidc_session_router(
    config: OidcSessionConfig, *,
    policy: SurfaceAccessPolicy | None = None, prefix: str = "/auth", csrf_token: str = "",
) -> APIRouter:  # fmt: skip
    """Create composable RFC OIDC S256 PKCE and session inspection APIRouter."""
    clean_pref = prefix.rstrip("/") or "/auth"
    eff_pol = policy or SurfaceAccessPolicy(
        default_ring=SurfaceRing.R0_PUBLIC, session_key=config.session_signing_key
    )
    router = APIRouter(prefix=clean_pref, tags=("oidc-session",))

    def _session_response(
        req: Request, p: SurfacePrincipal, extra_hdrs: dict[str, str] | None = None
    ) -> WebResponse:
        dev_on = config.allow_dev_persona_switch and _is_loopback_request(req)
        frag = render_identity_posture_bar_html(
            p, login_enabled=config.login_enabled, dev_switch_enabled=dev_on,
            is_https=req.is_secure, prefix=clean_pref, provider_label=config.provider_label,
        )  # fmt: skip
        fmt, acc = req.query("format", "").lower(), req.headers.get("accept", "").lower()
        wants_html = fmt == "html" or (fmt != "json" and "text/html" in acc)
        data = {
            "ring": p.ring.value, "ring_label": p.ring.label, "subject_id": p.subject_id,
            "groups": list(p.groups), "max_disclosure_tier": p.max_disclosure_tier,
            "is_https": req.is_secure, "provider_id": config.provider_id,
            "login_enabled": config.login_enabled, "dev_switch_enabled": dev_on,
        }  # fmt: skip
        full_h = _wrap_full_identity_page(frag, csrf_token) if wants_html else None
        return respond(
            req, html_fragment=str(frag), data=data, headers=extra_hdrs, full_html=full_h
        )

    @router.get("/session", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect active R0..R3 ring")
    def get_session(req: Request) -> WebResponse:
        p = eff_pol.authenticate_request(
            headers=req.headers, cookies=req.cookies, client_host=_extract_host_only(req)
        )
        return _session_response(req, p)

    @router.get("/oidc/login", channel=DeliveryChannel.ISLAND_SYNC, summary="Start OIDC PKCE")
    def start_oidc_login(req: Request) -> WebResponse:
        if not config.login_enabled:
            _fail(
                "OIDC unconfigured", "OIDC_NOT_CONFIGURED", 503,
                security.ErrorAction.CONTACT_SUPPORT,
            )  # fmt: skip
        verifier, state_tok = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
        challenge = oidc_tokens.compute_pkce_s256_challenge(verifier)
        ret_to = _sanitize_return_to(req.query("return_to", "/dashboard"))
        redir = config.redirect_uri.strip()
        abs_redir = (
            f"{req.scheme}://{req.headers.get('host', 'localhost')}{redir}"
            if redir.startswith("/") else redir
        )  # fmt: skip
        auth_url = oidc_tokens.build_oidc_pkce_authorize_url(
            authorization_endpoint=config.authorization_endpoint, client_id=config.client_id,
            redirect_uri=abs_redir, state=state_tok, code_challenge=challenge,
            domain_hint=config.domain_hint, domain_hint_param=config.domain_hint_param,
        )  # fmt: skip
        pkce_tok = security.sign_cookie_value(
            {"state": state_tok, "challenge": challenge, "return_to": ret_to,
             "exp": time.time() + DEFAULT_PKCE_TTL_SEC}, config.session_signing_key,
        )  # fmt: skip
        c_dom = _matching_cookie_domain(req, config.cookie_domains)
        cookie_h = format_set_cookie_header(
            PKCE_COOKIE, pkce_tok, is_https=req.is_secure,
            same_site="Lax", max_age=DEFAULT_PKCE_TTL_SEC, domain=c_dom,
        )  # fmt: skip
        return _redirect_302(auth_url, cookie_h)

    @router.get("/oidc/callback", channel=DeliveryChannel.ISLAND_SYNC, summary="Complete PKCE")
    def finish_oidc_callback(req: Request) -> WebResponse:
        pkce_k = config.session_signing_key
        pkce_doc = security.verify_cookie_value(req.cookies.get(PKCE_COOKIE, ""), pkce_k)
        state_in, ver_in = req.query("state", "").strip(), req.query("code_verifier", "").strip()
        now_ts = time.time()
        exp_state = str(pkce_doc.get("state") or "") if pkce_doc else ""
        exp_chal = str(pkce_doc.get("challenge") or "") if pkce_doc else ""
        if (
            pkce_doc is None or now_ts > float(pkce_doc.get("exp") or 0.0)
            or not state_in or not hmac.compare_digest(state_in, exp_state)
            or not oidc_tokens.verify_pkce_s256(ver_in, exp_chal)
        ):  # fmt: skip
            _fail("Bad PKCE state", "OIDC_PKCE_VALIDATION_FAILED", 400, security.ErrorAction.RETRY)
        claims = oidc_tokens.verify_oidc_or_proxy_jwt(
            req.query("id_token", ""), expected_audience=config.effective_audience,
            allowed_issuers=config.allowed_issuers, assertion_key=config.jwt_assertion_key,
            signature_verifier=config.jwt_verifier,
            infer_domain_from_email=config.infer_domain_from_email,
            domain_infer_issuers=config.domain_infer_issuers, now=now_ts,
        )  # fmt: skip
        if claims is None:
            _fail("OIDC ID token verification failed", "OIDC_TOKEN_INVALID", 401)
        p = resolve_oidc_principal_from_claims(claims, config)
        c_dom = _matching_cookie_domain(req, config.cookie_domains)
        ret_to = _sanitize_return_to(str(pkce_doc.get("return_to") or "/dashboard"))
        sess_h = (
            _clear_session_cookie(req.is_secure, c_dom) if p.ring == SurfaceRing.R0_PUBLIC
            else _issue_session_cookie(
                p, signing_key=pkce_k, is_https=req.is_secure, now_ts=now_ts, domain=c_dom
            )
        )  # fmt: skip
        return _redirect_302(ret_to, sess_h)

    def _reset_r0(req: Request) -> WebResponse:
        c_dom = _matching_cookie_domain(req, config.cookie_domains)
        hdr = {
            "set-cookie": _clear_session_cookie(req.is_secure, c_dom),
            **build_swap_response_headers(refresh=True),
        }
        return _session_response(req, SurfacePrincipal(SurfaceRing.R0_PUBLIC, "anonymous"), hdr)

    @router.post("/dev-elevate", channel=DeliveryChannel.SWAP_SYNC, summary="Loopback ring switch")
    def elevate_dev_persona(req: Request) -> WebResponse:
        if not (config.allow_dev_persona_switch and _is_loopback_request(req)):
            _fail("Loopback persona switch disabled", "DEV_ELEVATION_FORBIDDEN", 403)
        ring_s, sub_in, grps = _parse_elevate_payload(req)
        if ring_s not in VALID_ELEVATION_RINGS:
            _fail(
                f"Invalid ring {ring_s!r}", "INVALID_SURFACE_RING",
                422, security.ErrorAction.FIX_INPUT,
            )  # fmt: skip
        if ring_s == "R0":
            return _reset_r0(req)
        r_en, c_dom = _RING_BY_CODE[ring_s], _matching_cookie_domain(req, config.cookie_domains)
        ext_k = ExternalSubjectKind.GUEST if r_en == SurfaceRing.R1_SCOPED_EXTERNAL else None
        sub = sub_in or f"dev-{ring_s.lower()}@localhost"
        tier = surface_access.RING_DEFAULT_DISCLOSURE_TIER[r_en]
        p = SurfacePrincipal(r_en, sub, ext_k, ("*",), tier, grps)
        set_h = _issue_session_cookie(
            p, signing_key=config.session_signing_key,
            is_https=req.is_secure, now_ts=time.time(), domain=c_dom,
        )  # fmt: skip
        return _session_response(req, p, {"set-cookie": set_h})

    @router.post("/logout", channel=DeliveryChannel.SWAP_SYNC, summary="Clear session cookie")
    def logout_session(req: Request) -> WebResponse:
        return _reset_r0(req)

    return router
