"""Validated network directory, participation virtues, and public /portal communication channels.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final, NoReturn

from zcg.core.constants import DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import ensure_contained_path
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.template_ast import sanitize_url

CONTACT_INBOX_REL_PATH: Final[str] = ".zcg/runtime/portal/contact_inbox.jsonl"
HANDSHAKE_QUEUE_REL_PATH: Final[str] = ".zcg/runtime/portal/handshake_requests.jsonl"
MAX_PORTAL_MESSAGE_LEN: Final[int] = 1200
MAX_PORTAL_FIELD_LEN: Final[int] = 160
RECEIPT_ID_HEX_CHARS: Final[int] = 12

VALID_HANDSHAKE_PURPOSES: Final[tuple[str, ...]] = (
    "network-attestation",
    "personal-connection",
    "project-collaboration",
    "b2b-inquiry",
    "game-match-invite",
    "tutoring-session",
    "stewardship-support",
)

NETWORK_PARTICIPATION_VIRTUES: Final[tuple[dict[str, str], ...]] = (
    {
        "title": "Zero-Cloud Sovereignty & Git Portability",
        "summary": (
            "Own your rules, skills, and local SQLite WAL runtime on laptop, rootless OCI "
            "container, or scale-to-zero cloud with 0 vendor lock-in."
        ),
    },
    {
        "title": "Verifiable 2D/3D Network Discovery",
        "summary": (
            "Bind your public repository and domain via /.well-known/zcg-attestation.json to "
            "appear in the live 2D/3D Network Atlas horizon."
        ),
    },
    {
        "title": "Ring-Scoped Projection & Human Channels",
        "summary": (
            "Project tailored R0..R3 views (CV, brand, Vault downloads, contact & purpose "
            "handshakes) while keeping R3 personal circles 100% private."
        ),
    },
    {
        "title": "Native Antigravity + Gemini + MCP Symbiosis",
        "summary": (
            "Combine rcap1 context compaction, sovereign skill auditing, and 0-output-token "
            "calibrated decisions across reproducible workspaces."
        ),
    },
)


@dataclass(frozen=True, slots=True)
class AttestedNetworkNodeEntry:
    """Validated public network directory entry pairing repository and attested domain."""

    node_id: str
    public_domain: str
    repository_url: str
    entity_role: str
    surface_ring: str = "R0"
    attestation_status: str = "verified"

    def to_dict(self) -> dict[str, str]:
        """Serialize directory entry into a template-friendly string dictionary."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublicChannelsSpec:
    """Declarative communication and social channels exposed on a node's public /portal."""

    social_links: tuple[dict[str, str], ...]
    contact_email: str
    contact_phone: str
    peer_handshake_enabled: bool
    supported_purposes: tuple[str, ...]


def _raise_portal_input_error(msg: str, code: str) -> NoReturn:
    raise WebAppError(
        msg,
        error_code=code,
        http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
        severity=ErrorSeverity.WARNING,
        action=ErrorAction.FIX_INPUT,
    )


def _short_receipt_id(seed_text: str) -> str:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return "".join(ch for idx, ch in enumerate(digest) if idx < RECEIPT_ID_HEX_CHARS)


def resolve_validated_network_directory(
    manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], ...]:
    """Build the validated Repository <-> Public Domain directory for Root 0 and peer meshes."""
    entries: list[AttestedNetworkNodeEntry] = [
        AttestedNetworkNodeEntry(
            node_id="zero-cloud-gravity",
            public_domain="zerocloudgravity.org",
            repository_url="https://github.com/mtwuser/zero-cloud-gravity",
            entity_role="root-0-platform",
            attestation_status="verified-root-0",
        )
    ]
    for cid, meta in DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.items():
        repo_url = meta["public_url"].removesuffix(".git")
        entries.append(
            AttestedNetworkNodeEntry(
                node_id=cid,
                public_domain=f"{cid}.zerocloudgravity.org",
                repository_url=repo_url,
                entity_role=meta.get("knowledge_domain", "epistemic-corpus"),
                attestation_status=meta.get("stewardship_stage", "public-community"),
            )
        )
    raw_custom = manifest.get("attested_network_nodes") if isinstance(manifest, Mapping) else None
    if isinstance(raw_custom, list):
        seen = {e.node_id for e in entries}
        for item in raw_custom:
            if not isinstance(item, Mapping):
                continue
            nid = str(item.get("node_id") or "").strip()
            dom = str(item.get("public_domain") or "").strip()
            rep = sanitize_url(str(item.get("repository_url") or "").strip())
            if is_kebab_id(nid) and nid not in seen and dom and rep != "#":
                seen.add(nid)
                entries.append(
                    AttestedNetworkNodeEntry(
                        node_id=nid,
                        public_domain=dom,
                        repository_url=rep,
                        entity_role=str(item.get("entity_role") or "sovereign-peer").strip(),
                    )
                )
    return tuple(e.to_dict() for e in entries)


def parse_public_channels_spec(
    manifest: Mapping[str, Any] | None,
    *,
    portal_kind: str,
    canonical_domain: str,
) -> PublicChannelsSpec:
    """Parse system/zcg-node.json -> public_channels with safe URL/field normalization."""
    raw = manifest.get("public_channels") if isinstance(manifest, Mapping) else None
    cfg = raw if isinstance(raw, Mapping) else {}
    is_oss = portal_kind == "oss-flagship-portal"

    links: list[dict[str, str]] = []
    raw_links = cfg.get("social_links")
    if isinstance(raw_links, list):
        for item in raw_links:
            if not isinstance(item, Mapping):
                continue
            lbl = str(item.get("label") or "").strip()
            safe_u = sanitize_url(str(item.get("url") or "").strip())
            if lbl and safe_u != "#":
                links.append({"label": lbl, "url": safe_u})
    elif is_oss:
        links.append(
            {
                "label": "GitHub Repository",
                "url": "https://github.com/mtwuser/zero-cloud-gravity",
            }
        )

    default_email = f"contact@{canonical_domain}" if is_oss and "contact_email" not in cfg else ""
    raw_email = str(cfg.get("contact_email", default_email)).strip()
    _, sep, domain_part = raw_email.partition("@")
    clean_email = raw_email if sep and "." in domain_part else ""

    raw_phone = str(cfg.get("contact_phone") or "").strip()
    clean_phone = raw_phone if len(raw_phone) <= 40 else ""

    hs_enabled = bool(cfg.get("peer_handshake_enabled", True))
    raw_purp = cfg.get("supported_purposes")
    purposes = (
        tuple(str(p).strip() for p in raw_purp if str(p).strip() in VALID_HANDSHAKE_PURPOSES)
        if isinstance(raw_purp, list)
        else ()
    ) or VALID_HANDSHAKE_PURPOSES
    return PublicChannelsSpec(
        social_links=tuple(links),
        contact_email=clean_email,
        contact_phone=clean_phone,
        peer_handshake_enabled=hs_enabled,
        supported_purposes=purposes,
    )


def _append_runtime_jsonl(
    workspace_dir: Path | None, rel_path: str, record: dict[str, Any]
) -> None:
    if workspace_dir is None:
        return
    out_file = ensure_contained_path(Path(rel_path), workspace_dir.resolve())
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_portal_contact_message(
    workspace_dir: Path | None,
    *,
    sender_name: str,
    sender_contact: str,
    subject: str = "",
    message: str,
) -> dict[str, Any]:
    """Validate and persist a public R0 contact message into local .zcg/runtime/portal/."""
    c_name = sender_name.strip()
    c_contact = sender_contact.strip()
    c_subj = subject.strip() or "General Inquiry"
    c_msg = message.strip()
    if (
        not c_name
        or len(c_name) > MAX_PORTAL_FIELD_LEN
        or len(c_contact) < 3
        or len(c_contact) > MAX_PORTAL_FIELD_LEN
        or len(c_subj) > MAX_PORTAL_FIELD_LEN
        or not (1 <= len(c_msg) <= MAX_PORTAL_MESSAGE_LEN)
    ):
        _raise_portal_input_error(
            "Valid sender_name, sender_contact, and bounded message (1..1200 chars) are required",
            "INVALID_CONTACT_MESSAGE",
        )
    ts = dt.datetime.now(dt.UTC).isoformat()
    rec = {
        "receipt_id": f"msg-{_short_receipt_id(f'{ts}:{c_contact}:{c_msg}')}",
        "recorded_at": ts,
        "sender_name": c_name,
        "sender_contact": c_contact,
        "subject": c_subj,
        "message": c_msg,
        "stored_locally": workspace_dir is not None,
    }
    _append_runtime_jsonl(workspace_dir, CONTACT_INBOX_REL_PATH, rec)
    return rec


def record_portal_handshake_request(
    workspace_dir: Path | None,
    *,
    peer_node_id: str,
    purpose: str,
    peer_domain_or_repo: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Validate and queue a purpose-scoped P2P node handshake request for human R3 triage."""
    c_peer = peer_node_id.strip()
    c_purp = purpose.strip().lower()
    c_origin = peer_domain_or_repo.strip()
    c_note = note.strip()
    if not is_kebab_id(c_peer):
        _raise_portal_input_error(
            f"Invalid peer_node_id {peer_node_id!r}: must match lowercase kebab-case",
            "INVALID_HANDSHAKE_PEER_ID",
        )
    if c_purp not in VALID_HANDSHAKE_PURPOSES:
        _raise_portal_input_error(
            f"Unsupported handshake purpose {purpose!r}; valid={VALID_HANDSHAKE_PURPOSES}",
            "INVALID_HANDSHAKE_PURPOSE",
        )
    if len(c_origin) > MAX_PORTAL_FIELD_LEN or len(c_note) > MAX_PORTAL_MESSAGE_LEN:
        _raise_portal_input_error(
            "Handshake origin or note exceeds maximum allowed length",
            "INVALID_HANDSHAKE_NOTE",
        )
    ts = dt.datetime.now(dt.UTC).isoformat()
    rec = {
        "request_id": f"hs-{_short_receipt_id(f'{ts}:{c_peer}:{c_purp}')}",
        "recorded_at": ts,
        "peer_node_id": c_peer,
        "purpose": c_purp,
        "peer_domain_or_repo": c_origin,
        "note": c_note,
        "status": "queued-human-triage",
        "v2_protocol_seam": "ed25519+symbolic-stake-ready",
    }
    _append_runtime_jsonl(workspace_dir, HANDSHAKE_QUEUE_REL_PATH, rec)
    return rec


def build_portal_channels_context(
    manifest: Mapping[str, Any] | None,
    *,
    portal_kind: str,
    canonical_domain: str,
) -> dict[str, Any]:
    """Build template context variables for /portal virtues, directory, and channels."""
    ch = parse_public_channels_spec(
        manifest, portal_kind=portal_kind, canonical_domain=canonical_domain
    )
    is_oss = portal_kind == "oss-flagship-portal"
    return {
        "network_virtues": list(NETWORK_PARTICIPATION_VIRTUES),
        "validated_directory": list(resolve_validated_network_directory(manifest))
        if is_oss
        else [],
        "social_links": list(ch.social_links),
        "contact_email": ch.contact_email,
        "contact_phone": ch.contact_phone,
        "peer_handshake_enabled": ch.peer_handshake_enabled,
        "supported_purposes": list(ch.supported_purposes),
    }


def _extract_request_mapping(req: Request) -> Mapping[str, Any]:
    if "application/json" in req.content_type.lower():
        raw = req.json()
        return raw if isinstance(raw, Mapping) else {}
    return req.form()


def create_portal_channels_router(
    *,
    workspace_dir: Path | None = None,
    exposure_guard: Any = None,
) -> APIRouter:
    """Create composable POST /contact and POST /handshake sub-router for /portal."""
    router = APIRouter(tags=("portal-channels",))

    @router.post("/contact", channel=DeliveryChannel.SWAP_SYNC, summary="Submit public R0 contact")
    def post_portal_contact(req: Request) -> WebResponse:
        if exposure_guard is not None:
            exposure_guard(req)
        pl = _extract_request_mapping(req)
        rec = record_portal_contact_message(
            workspace_dir,
            sender_name=str(pl.get("sender_name", "")),
            sender_contact=str(pl.get("sender_contact", "")),
            subject=str(pl.get("subject", "")),
            message=str(pl.get("message", "")),
        )
        frag = f"<div class='zcg-chip'>Message queued: <code>{rec['receipt_id']}</code></div>"
        return respond(req, html_fragment=frag, data=rec, status=int(HTTPStatus.CREATED))

    @router.post("/handshake", channel=DeliveryChannel.SWAP_SYNC, summary="Request P2P handshake")
    def post_portal_handshake(req: Request) -> WebResponse:
        if exposure_guard is not None:
            exposure_guard(req)
        pl = _extract_request_mapping(req)
        rec = record_portal_handshake_request(
            workspace_dir,
            peer_node_id=str(pl.get("peer_node_id", "")),
            purpose=str(pl.get("purpose", "")),
            peer_domain_or_repo=str(pl.get("peer_domain_or_repo", "")),
            note=str(pl.get("note", "")),
        )
        frag = f"<div class='zcg-chip'>Handshake queued: <code>{rec['request_id']}</code></div>"
        return respond(req, html_fragment=frag, data=rec, status=int(HTTPStatus.CREATED))

    return router
