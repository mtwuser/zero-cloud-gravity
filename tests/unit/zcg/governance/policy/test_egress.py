"""Unit tests for zcg.governance.policy.egress.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.policy.egress import (
    ArtifactMirrorConfig,
    extract_http_url_spans,
    find_unauthorized_egress_hosts,
    is_egress_host_allowed,
    resolve_effective_egress_policy,
)


class TestEgress:
    """Verify Lex Superior network_egress_policy, CDN origins, and private artifact mirrors."""

    def test_is_egress_host_allowed_and_mirror_env_projection_expected(self) -> None:
        """Verify loopback/fnmatch host checks and ArtifactMirrorConfig env var synthesis."""
        # Arrange
        full_mirrors = ArtifactMirrorConfig(
            container_registry="europe-west1-docker.pkg.dev/iso-corp/containers",
            pypi_index_url="https://europe-west1-python.pkg.dev/iso-corp/pypi/simple",
            apt_mirror_url="https://europe-west1-apt.pkg.dev/projects/iso-corp",
            require_private_mirrors=True,
        )
        airgap_mirrors = ArtifactMirrorConfig(require_private_mirrors=True)
        empty_mirrors = ArtifactMirrorConfig()

        # Act
        loop_ok = is_egress_host_allowed("127.0.0.1", ())
        sub_loop_ok = is_egress_host_allowed("dev.iso.localhost", ())
        pat_ok = is_egress_host_allowed("cdn.iso.example.", ("", "*.iso.example"))
        pat_deny = is_egress_host_allowed("untrusted.io", ("*.iso.example",))
        full_env = full_mirrors.to_env_vars()
        airgap_env = airgap_mirrors.to_env_vars()
        empty_env = empty_mirrors.to_env_vars()

        # Assert
        assert loop_ok is True and sub_loop_ok is True
        assert pat_ok is True and pat_deny is False
        assert full_env["ZCG_CONTAINER_REGISTRY"].startswith("europe-west1-docker.pkg.dev")
        assert full_env["PIP_INDEX_URL"].endswith("/simple")
        assert full_env["UV_DEFAULT_INDEX"] == full_env["PIP_INDEX_URL"]
        assert full_env["ZCG_APT_MIRROR_URL"].startswith("https://europe-west1-apt.pkg.dev")
        assert "PIP_NO_INDEX" not in full_env
        assert airgap_env == {"PIP_NO_INDEX": "1"}
        assert empty_env == {}
        assert full_mirrors.to_dict()["require_private_mirrors"] is True
        spans = extract_http_url_spans(
            "See https://cdn.iso.example/pkg.tgz, http://127.0.0.1:8790/healthz and "
            "https://cdn.iso.example@evil.example/spoof plus https:///no-host trailing."
        )
        blocked = find_unauthorized_egress_hosts(" ".join(spans), ("*.iso.example",))
        assert len(spans) == 4
        assert blocked == ["cdn.iso.example@evil.example", "https:///no-host"]

    def test_resolve_effective_egress_policy_hierarchy_cdn_and_locked_mirrors_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Parent -> Child intersection, canonical CDN synthesis, and lock_mirrors."""
        # Arrange
        root_ws = tmp_path / "corp-iso-root"
        child_ws = tmp_path / "dept-eng"
        open_ws = tmp_path / "open-node"
        (root_ws / "system").mkdir(parents=True)
        (child_ws / "system").mkdir(parents=True)
        open_ws.mkdir(parents=True)
        (root_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "corp-iso-root",
                    "entity_kind": "enterprise",
                    "layer_role": "corporate",
                    "precedence": 10,
                    "network_egress_policy": {
                        "allowed_domains": [
                            "",
                            "*.iso.example",
                            "*.pkg.dev",
                            "cdn.iso.example",
                            "api.github.com/v3",
                            "https://",
                        ],
                        "enable_canonical_cdn": True,
                        "artifact_mirrors": {
                            "container_registry": "europe-west1-docker.pkg.dev/iso/img",
                            "pypi_index_url": "https://europe-west1-python.pkg.dev/iso/pypi",
                            "apt_mirror_url": "https://europe-west1-apt.pkg.dev/projects/iso",
                            "require_private_mirrors": True,
                            "lock_mirrors": True,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (child_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "dept-eng",
                    "entity_kind": "enterprise",
                    "layer_role": "department",
                    "precedence": 25,
                    "network_egress_policy": {
                        "allowed_hosts": [
                            "https://*.iso.example",
                            "https://*.pkg.dev",
                            "https://cdn.iso.example",
                        ],
                        "allowed_domains": ["*.iso.example", "*.pkg.dev", "cdn.iso.example"],
                        "cdn_origins": ["https://cdn.iso.example"],
                        "artifact_mirrors": {
                            "pypi_index_url": "https://pypi.org/simple",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        # Act
        pol = resolve_effective_egress_policy(
            child_ws, parent_dir=root_ws, canonical_domain="iso.example"
        )
        local_pol = resolve_effective_egress_policy(
            open_ws,
            manifest={
                "layer_id": "open-node",
                "network_egress_policy": {
                    "enable_canonical_cdn": True,
                    "cdn_origins": ["https://cdn.open.example"],
                    "artifact_mirrors": {
                        "container_registry": "https://europe-docker.pkg.dev/open/img"
                    },
                },
            },
            canonical_domain="open.intranet.local",
        )
        pol_dict = pol.to_dict()

        # Assert
        assert pol.lineage_layers == ("corp-iso-root", "dept-eng")
        assert pol.default_csp_source == "'self'"
        assert pol.egress_restricted is True
        assert pol.cdn_origins == ("https://cdn.iso.example",)
        assert "https://cdn.iso.example" in pol.browser_allowlist_urls
        assert pol.artifact_mirrors.pypi_index_url.startswith("https://europe-west1-python.pkg.dev")
        assert pol_dict["egress_restricted"] is True
        assert local_pol.egress_restricted is False
        assert local_pol.cdn_origins == ("https://cdn.open.example",)
        assert local_pol.artifact_mirrors.container_registry == (
            "https://europe-docker.pkg.dev/open/img"
        )

    def test_wallet_isolation_and_unauthorized_cdn_or_mirror_rejections_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify R3 wallet loopback isolation and rejection of unapproved CDNs or mirrors."""
        # Arrange
        wallet_ws = tmp_path / "persona-wallet"
        wallet_ws.mkdir()
        restricted_ws = tmp_path / "sec-dept"
        restricted_ws.mkdir()

        # Act
        w_pol = resolve_effective_egress_policy(
            wallet_ws,
            manifest={
                "layer_id": "persona-wallet",
                "entity_kind": "individual",
                "layer_role": "squad",
                "precedence": 88,
                "network_egress_policy": {
                    "allowed_domains": ["iso.example"],
                    "cdn_origins": ["https://cdn.iso.example"],
                },
            },
        )

        # Assert
        assert w_pol.is_loopback_isolated is True
        assert w_pol.allowed_domains == () and w_pol.cdn_origins == ()
        assert w_pol.artifact_mirrors.to_env_vars() == {"PIP_NO_INDEX": "1"}
        with pytest.raises(ValueError, match="UNAUTHORIZED_CDN_EGRESS_ORIGIN"):
            resolve_effective_egress_policy(
                restricted_ws,
                manifest={
                    "network_egress_policy": {
                        "allowed_domains": ["api.iso.example"],
                        "cdn_origins": ["https://cdn.other.example"],
                    }
                },
            )
        with pytest.raises(ValueError, match="UNAUTHORIZED_ARTIFACT_MIRROR"):
            resolve_effective_egress_policy(
                restricted_ws,
                manifest={
                    "network_egress_policy": {
                        "allowed_domains": ["api.iso.example"],
                        "artifact_mirrors": {"pypi_index_url": "https://pypi.org/simple"},
                    }
                },
            )
        with pytest.raises(ValueError, match="UNAUTHORIZED_ARTIFACT_MIRROR"):
            resolve_effective_egress_policy(
                restricted_ws,
                manifest={
                    "network_egress_policy": {
                        "artifact_mirrors": {"apt_mirror_url": "http://insecure.mirror.io"}
                    }
                },
            )
