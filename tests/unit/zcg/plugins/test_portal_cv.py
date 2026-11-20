"""Unit tests for zcg.plugins.portal_cv.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.plugins.portal_cv import (
    CVFieldEntry,
    CVProfileSpec,
    project_cv_by_disclosure_tier,
    render_cv_markdown,
    render_cv_print_a4_html,
    resolve_entity_portal_kind,
    resolve_personal_hub_context,
    resolve_workspace_cv_profile,
)


class TestPortalCv:
    """1:1 unit suite for CV disclosure projection, workspace profile synthesis, and Root 0 hub."""

    def test_cv_projection_markdown_print_a4_and_validation_guards_expected(self) -> None:
        """Verify monotonic R0..R3 CV filtering, Markdown/A4 HTML output, and validation guards."""
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
        with pytest.raises(ValueError, match="field_id"):
            CVFieldEntry(" ", "Lbl", "Val")
        with pytest.raises(ValueError, match="disclosure_tier"):
            CVFieldEntry("f1", "Lbl", "Val", disclosure_tier="unknown")
        with pytest.raises(ValueError, match="effective_tier"):
            project_cv_by_disclosure_tier(spec, effective_tier="bad_tier")

    def test_resolve_entity_portal_kind_and_workspace_cv_profile_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify entity/role portal selection and declarative vs. workspace-backed CV synthesis."""
        # Arrange
        work_ws = tmp_path / "persona-work"
        (work_ws / "system").mkdir(parents=True)
        (work_ws / "README.md").write_text(
            "# [Fill: Draft]\n# Operator Ventures Studio\n"
            "> Quote\nIndependent systems consultancy.\n",
            encoding="utf-8",
        )
        work_man = {
            "layer_id": "persona-work",
            "entity_kind": "individual",
            "layer_role": "squad",
            "default_stack_templates": ["business-base", "node-work-cockpit"],
            "public_channels": {"contact_email": "work@persona.example.org"},
            "linked_nodes": [{"id": "corp-iso"}],
            "cv_profile": {"entries": []},
        }
        (work_ws / "system/zcg-node.json").write_text(json.dumps(work_man), encoding="utf-8")
        custom_man = {
            "layer_id": "persona-work",
            "cv_profile": {
                "full_name": "Ada Lovelace",
                "headline": "Analytical Engine Architect",
                "public_contact": "ada@example.org",
                "entries": [{"field_id": "bio", "label": "Bio", "value": "Symbolic computing."}],
            },
        }

        # Act
        k_ent = resolve_entity_portal_kind({}, "enterprise")
        k_hub = resolve_entity_portal_kind({"layer_role": "workstation"}, "individual")
        k_cv = resolve_entity_portal_kind({"layer_role": "squad"}, "individual")
        k_oss = resolve_entity_portal_kind(None, "open-source")
        ref_cv = resolve_workspace_cv_profile(None, None, node_id="pub-persona", public_domain="")
        ws_cv = resolve_workspace_cv_profile(
            work_ws, None, node_id="persona-work", public_domain="work.persona.example.org"
        )
        decl_cv = resolve_workspace_cv_profile(
            work_ws, custom_man, node_id="persona-work", public_domain=""
        )

        # Assert
        assert (k_ent, k_hub, k_cv, k_oss) == (
            "corporate-brand-portal",
            "personal-constellation-hub",
            "personal-portfolio-cv",
            "oss-flagship-portal",
        )
        assert ref_cv.full_name.startswith("pub-persona")
        assert ws_cv.full_name == "Operator Ventures Studio"
        assert ws_cv.public_contact == "work@persona.example.org"
        assert "Independent systems consultancy." in ws_cv.headline
        assert decl_cv.full_name == "Ada Lovelace" and len(decl_cv.entries) == 1

    def test_resolve_personal_hub_context_discovers_exposed_pillars_only_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Root 0 hub delegates only to exposed child pillars across local and prod URLs."""
        # Arrange
        profile_ws = tmp_path / "persona-profile"
        (profile_ws / "system").mkdir(parents=True)
        (profile_ws / "README.md").write_text("# Operator Personal Hub\n", encoding="utf-8")
        work_ws = tmp_path / "Projects/persona-work"
        (work_ws / "system").mkdir(parents=True)
        (work_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "persona-work",
                    "entity_kind": "individual",
                    "precedence": 87,
                    "public_exposure": {"mode": "online"},
                }
            ),
            encoding="utf-8",
        )
        tutor_ws = tmp_path / "persona-tutor"
        (tutor_ws / "system").mkdir(parents=True)
        (tutor_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {"layer_id": "persona-tutor", "entity_kind": "individual", "precedence": 86}
            ),
            encoding="utf-8",
        )
        wallet_ws = tmp_path / "persona-wallet"
        (wallet_ws / "system").mkdir(parents=True)
        (wallet_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "entity_kind": "individual",
                    "precedence": 88,
                    "public_exposure": {"mode": "online"},
                }
            ),
            encoding="utf-8",
        )
        base_f = [
            {
                "pillar": "game",
                "label": "Game Lab",
                "summary": "Matches",
                "purpose": "game-match-invite",
                "public_url": "#contact",
            }
        ]

        # Act
        hub_none = resolve_personal_hub_context(
            None, None, node_id="persona-profile", canonical_domain="persona-profile.localhost"
        )
        hub_local = resolve_personal_hub_context(
            profile_ws,
            {},
            node_id="persona-profile",
            canonical_domain="persona-profile.localhost",
            base_facets=base_f,
        )
        hub_prod = resolve_personal_hub_context(
            profile_ws, {}, node_id="persona-profile", canonical_domain="persona.example.org"
        )

        # Assert
        assert hub_none["public_facets"] == []
        pillars_local = {f["pillar"]: f["public_url"] for f in hub_local["public_facets"]}
        assert set(pillars_local) == {"game", "work", "wallet"}
        assert "tutor" not in pillars_local
        assert "pro.persona-work.persona-profile.localhost:8787/portal" in pillars_local["work"]
        pillars_prod = {f["pillar"]: f["public_url"] for f in hub_prod["public_facets"]}
        assert pillars_prod["work"] == "https://work.persona.example.org/portal?format=html"
        assert pillars_prod["wallet"] == "https://wallet.persona.example.org/portal/stewardship"
