"""Unit tests for zcg.topology.exposure.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import pytest

from zcg.topology.exposure import (
    POSTURE_DEFAULT_RINGS,
    VALID_SURFACE_VERACITY_MODES,
    classify_exposure_posture,
    compile_local_trust_circle_grants,
    is_public_portal_enabled,
    resolve_active_env_stages,
    resolve_co_sovereign_union_contract,
    resolve_posture_default_ring,
    resolve_surface_veracity_mode,
)


class TestExposure:
    """Verify headless exposure posture, default ring, and veracity mode classification."""

    def test_classify_exposure_posture_and_default_ring_across_all_quadrants_expected(
        self,
    ) -> None:
        """Verify public-live, public-preview, private-personal, and private-intranet postures."""
        # Arrange
        know_manifest = {"layer_role": "knowledge"}
        ind_manifest = {"precedence": 90, "layer_role": "workstation"}
        corp_manifest = {"precedence": 25, "layer_role": "department"}

        # Act
        pub_live = classify_exposure_posture(know_manifest, active_env="pro")
        pub_prev = classify_exposure_posture(know_manifest, active_env=" ")
        priv_ind = classify_exposure_posture(ind_manifest)
        priv_ent = classify_exposure_posture(corp_manifest)

        # Assert
        assert pub_live["posture"] == "public-live"
        assert pub_prev["posture"] == "public-preview" and "dev" in pub_prev["badge"]
        assert priv_ind["posture"] == "private-personal"
        assert priv_ent["posture"] == "private-intranet"
        assert resolve_posture_default_ring("public-live") == "R0"
        assert resolve_posture_default_ring("private-personal") == "R3"
        assert resolve_posture_default_ring("unknown-posture") == "R2"
        assert set(POSTURE_DEFAULT_RINGS.values()) == {"R0", "R2", "R3"}
        assert is_public_portal_enabled(ind_manifest) is False
        assert is_public_portal_enabled(corp_manifest) is True
        assert is_public_portal_enabled({"public_exposure": {"mode": "disabled"}}) is False
        assert (
            is_public_portal_enabled({"precedence": 90, "public_exposure": {"mode": "online"}})
            is True
        )
        assert resolve_active_env_stages(ind_manifest) == ()
        assert resolve_active_env_stages(
            {"entity_kind": "individual", "public_exposure": {"mode": "online"}}
        ) == ("dev", "pro")
        assert resolve_active_env_stages(corp_manifest) == ("dev", "tst", "pre", "pro")
        assert resolve_active_env_stages(
            {
                "entity_kind": "individual",
                "domain_governance": {"canonical_domain": "persona.example.org"},
                "git_governance": {"environment_promotion_order": ["dev", "pro"]},
            }
        ) == ("dev", "pro")
        assert resolve_active_env_stages(
            {
                "entity_kind": "individual",
                "visibility": "public",
                "environment_promotion_order": ["invalid"],
            }
        ) == ("dev", "pro")

    def test_resolve_surface_veracity_mode_explicit_and_inferred_expected(self) -> None:
        """Verify explicit surface_veracity_mode override and OSS/public/private inference."""
        # Arrange
        explicit_m = {"surface_veracity_mode": "attestation-only", "entity_kind": "open-source"}
        oss_m = {"entity_kind": "open-source"}
        gov_m = {"layer_id": "gov-iso", "layer_role": "knowledge"}
        pub_org_m = {"layer_id": "org-iso", "layer_role": "knowledge"}
        priv_m = {"layer_id": "dept-ops", "layer_role": "department"}

        # Act
        modes = (
            resolve_surface_veracity_mode(explicit_m),
            resolve_surface_veracity_mode(oss_m),
            resolve_surface_veracity_mode(gov_m),
            resolve_surface_veracity_mode(pub_org_m),
            resolve_surface_veracity_mode(priv_m),
        )

        # Assert
        assert VALID_SURFACE_VERACITY_MODES == (
            "full-open-source",
            "curated-public-surface",
            "attestation-only",
        )
        assert modes == (
            "attestation-only",
            "full-open-source",
            "full-open-source",
            "curated-public-surface",
            "attestation-only",
        )

    def test_co_sovereign_union_and_local_trust_circles_zero_leak_expected(self) -> None:
        """Verify co-sovereign union guards and zero-label R2/R1 trust circle compilation."""
        # Arrange
        shared_m = {
            "layer_id": "household-shared",
            "precedence": 89,
            "co_sovereign_peers": ["persona-profile", "  "],
            "linked_nodes": [
                {"node_id": "dana-profile", "relation": "co-sovereign-union"},
                {"target_id": "", "relation": "co-sovereign-union"},
                {"node_id": "sci-maths", "relation": "knowledge-feed"},
                "skip-invalid",
            ],
            "local_trust_circles": {
                "inner-household": {"outward_ring": "R2", "emails": ["dana@example.org", ""]},
                "external-advisor": {"outward_ring": "R1", "emails": ["cpa@example.org"]},
                "public-readers": {"outward_ring": "R0", "emails": ["anon@example.org"]},
                "malformed-emails": {"outward_ring": "R2", "emails": "not-a-list"},
                "malformed-entry": "skip",
            },
        }
        list_circles_m = {
            "local_trust_circles": [{"outward_ring": "R1", "emails": ["guest@example.org"]}],
        }

        # Act
        union = resolve_co_sovereign_union_contract(shared_m)
        inactive = resolve_co_sovereign_union_contract({"layer_id": "solo-profile"})
        grants_map = compile_local_trust_circle_grants(shared_m)
        grants_list = compile_local_trust_circle_grants(list_circles_m)
        grants_none = compile_local_trust_circle_grants({})

        # Assert
        assert union == {
            "enabled": True,
            "peers": ("persona-profile", "dana-profile"),
            "lex_superior_over_personal_pc": False,
            "consensus_mode": "symmetric-peer-consent",
        }
        assert inactive["enabled"] is False and inactive["peers"] == ()
        assert grants_map == {
            "r2_member_emails": ("dana@example.org",),
            "r1_scoped_external_emails": ("cpa@example.org",),
        }
        assert grants_list["r1_scoped_external_emails"] == ("guest@example.org",)
        assert grants_none == {"r2_member_emails": (), "r1_scoped_external_emails": ()}
        with pytest.raises(ValueError, match="WALLET_CO_SOVEREIGN_UNION_FORBIDDEN"):
            resolve_co_sovereign_union_contract(
                {
                    "layer_id": "persona-wallet",
                    "precedence": 88,
                    "co_sovereign_peers": ["dana-profile"],
                }
            )
        with pytest.raises(ValueError, match="INVALID_CO_SOVEREIGN_PEER_ID"):
            resolve_co_sovereign_union_contract({"co_sovereign_peers": ["Bad_ID"]})
        with pytest.raises(ValueError, match="TRUST_CIRCLE_R3_EXPORT_FORBIDDEN"):
            compile_local_trust_circle_grants(
                {"local_trust_circles": {"secret": {"outward_ring": "R3", "emails": ["a@b.org"]}}}
            )
