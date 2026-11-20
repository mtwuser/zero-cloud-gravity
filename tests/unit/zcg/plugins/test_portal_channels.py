"""Unit tests for zcg.plugins.portal_channels.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from zcg.plugins.portal_channels import (
    CONTACT_INBOX_REL_PATH,
    HANDSHAKE_QUEUE_REL_PATH,
    MAX_PORTAL_FIELD_LEN,
    VALID_HANDSHAKE_PURPOSES,
    build_portal_channels_context,
    create_portal_channels_router,
    parse_public_channels_spec,
    record_portal_contact_message,
    record_portal_handshake_request,
    resolve_validated_network_directory,
)
from zcg.web.auth.security import WebAppError
from zcg.web.http.request import Request, WebResponse


def _make_req(
    path: str,
    *,
    body: bytes = b"",
    content_type: str = "application/x-www-form-urlencoded",
    hx: bool = False,
) -> Request:
    hdrs = [(b"content-type", content_type.encode("latin1"))]
    if hx:
        hdrs.append((b"hx-request", b"true"))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": hdrs,
    }
    return Request(scope, body)


class TestPortalChannels:
    """Verify validated network directory, participation virtues, and /portal channels."""

    def test_directory_and_public_channels_parsing_across_oss_and_custom_nodes_expected(
        self,
    ) -> None:
        """Verify Root 0 directory, custom attested nodes, and safe channel normalization."""
        # Arrange
        manifest = {
            "attested_network_nodes": [
                "skip-non-dict",
                {
                    "node_id": "pub-persona",
                    "public_domain": "persona.example.org",
                    "repository_url": "https://github.com/iso/pub-persona",
                    "entity_role": "personal-twin",
                },
                {
                    "node_id": "pub-persona",
                    "public_domain": "dup.example.org",
                    "repository_url": "https://github.com/iso/dup",
                },
                {
                    "node_id": "Bad_ID",
                    "public_domain": "bad.example.org",
                    "repository_url": "javascript:alert(1)",
                },
            ],
            "public_channels": {
                "social_links": [
                    "skip-str",
                    {"label": "GitHub", "url": "https://github.com/iso/node"},
                    {"label": "Unsafe", "url": "javascript:void(0)"},
                    {"label": "", "url": "https://example.org"},
                ],
                "contact_email": "hello@persona.example.org",
                "contact_phone": "+34 900 123 456",
                "peer_handshake_enabled": False,
                "supported_purposes": ["project-collaboration", "invalid-purpose"],
            },
        }
        overlong_manifest = {
            "public_channels": {
                "contact_email": "not-an-email",
                "contact_phone": "1" * 50,
                "supported_purposes": ["invalid-only"],
            }
        }

        # Act
        oss_ctx = build_portal_channels_context(
            None, portal_kind="oss-flagship-portal", canonical_domain="zerocloudgravity.org"
        )
        cv_ctx = build_portal_channels_context(
            manifest, portal_kind="personal-portfolio-cv", canonical_domain="persona.example.org"
        )
        overlong_spec = parse_public_channels_spec(
            overlong_manifest,
            portal_kind="corporate-brand-portal",
            canonical_domain="corp.example.org",
        )
        full_dir = resolve_validated_network_directory(manifest)

        # Assert
        assert len(oss_ctx["network_virtues"]) == 4
        assert oss_ctx["validated_directory"][0]["node_id"] == "zero-cloud-gravity"
        assert oss_ctx["contact_email"] == "contact@zerocloudgravity.org"
        assert oss_ctx["social_links"][0]["label"] == "GitHub Repository"
        assert cv_ctx["validated_directory"] == []
        assert cv_ctx["social_links"] == [{"label": "GitHub", "url": "https://github.com/iso/node"}]
        assert cv_ctx["contact_phone"] == "+34 900 123 456"
        assert cv_ctx["peer_handshake_enabled"] is False
        assert cv_ctx["supported_purposes"] == ["project-collaboration"]
        assert overlong_spec.contact_email == "" and overlong_spec.contact_phone == ""
        assert overlong_spec.supported_purposes == VALID_HANDSHAKE_PURPOSES
        assert any(e["node_id"] == "pub-persona" for e in full_dir)

    def test_contact_and_handshake_recording_router_and_bipolar_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify JSONL persistence, stateless mode, router handlers, and 422 input guards."""
        # Arrange
        guarded_paths: list[str] = []
        router = create_portal_channels_router(workspace_dir=tmp_path)
        g_router = create_portal_channels_router(
            workspace_dir=tmp_path, exposure_guard=lambda r: guarded_paths.append(r.path)
        )
        m_contact, _ = router.resolve("POST", "/contact")
        m_hs, _ = router.resolve("POST", "/handshake")
        gm_contact, _ = g_router.resolve("POST", "/contact")
        gm_hs, _ = g_router.resolve("POST", "/handshake")
        assert m_contact is not None and m_hs is not None
        assert gm_contact is not None and gm_hs is not None

        req_c_form = _make_req(
            "/contact",
            body=b"sender_name=Ada&sender_contact=ada%40example.org&message=Hello+Node",
            hx=True,
        )
        req_hs_json = _make_req(
            "/handshake",
            body=json.dumps(
                {
                    "peer_node_id": "peer-alpha",
                    "purpose": "network-attestation",
                    "peer_domain_or_repo": "alpha.example.org",
                    "note": "Attest public surface",
                }
            ).encode("utf-8"),
            content_type="application/json",
        )
        req_bad_json = _make_req("/contact", body=b"[1, 2]", content_type="application/json")

        # Act
        res_c = m_contact.route.handler(req_c_form)
        res_hs = m_hs.route.handler(req_hs_json)
        gm_contact.route.handler(req_c_form)
        gm_hs.route.handler(req_hs_json)
        stateless_c = record_portal_contact_message(
            None, sender_name="Bob", sender_contact="bob@example.org", message="Stateless"
        )
        stateless_hs = record_portal_handshake_request(
            None, peer_node_id="bob-profile", purpose="personal-connection"
        )

        # Assert
        assert isinstance(res_c, WebResponse) and isinstance(res_hs, WebResponse)
        assert guarded_paths == ["/contact", "/handshake"]
        assert res_c.status == 201 and b"Message queued" in res_c.body
        assert res_hs.status == 201 and b"queued-human-triage" in res_hs.body
        assert (tmp_path / CONTACT_INBOX_REL_PATH).is_file()
        assert (tmp_path / HANDSHAKE_QUEUE_REL_PATH).is_file()
        assert stateless_c["stored_locally"] is False
        assert stateless_hs["v2_protocol_seam"] == "ed25519+symbolic-stake-ready"

        with pytest.raises(WebAppError) as err_c:
            m_contact.route.handler(req_bad_json)
        assert err_c.value.error_code == "INVALID_CONTACT_MESSAGE"

        with pytest.raises(WebAppError) as err_pid:
            record_portal_handshake_request(
                tmp_path, peer_node_id="Bad_Node", purpose="b2b-inquiry"
            )
        assert err_pid.value.error_code == "INVALID_HANDSHAKE_PEER_ID"

        with pytest.raises(WebAppError) as err_purp:
            record_portal_handshake_request(tmp_path, peer_node_id="ok-node", purpose="spam")
        assert err_purp.value.error_code == "INVALID_HANDSHAKE_PURPOSE"

        with pytest.raises(WebAppError) as err_len:
            record_portal_handshake_request(
                tmp_path,
                peer_node_id="ok-node",
                purpose="b2b-inquiry",
                peer_domain_or_repo="x" * (MAX_PORTAL_FIELD_LEN + 1),
            )
        assert err_len.value.error_code == "INVALID_HANDSHAKE_NOTE"
