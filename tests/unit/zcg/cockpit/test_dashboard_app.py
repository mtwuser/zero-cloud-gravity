"""Unit tests for zcg.cockpit.dashboard_app.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from zcg.cockpit.dashboard_app import (
    ARCHETYPE_DEFAULT_PLUGIN,
    MODULE_SWAP_URLS,
    VALID_DASHBOARD_MODULES,
    build_dashboard_routers,
    build_modular_workbench_spec,
    resolve_archetype_crud_schema,
    resolve_enabled_modules,
)
from zcg.platform.projection import DisclosureTier, PayloadFieldSegment
from zcg.web.factory import WebAppState, create_web_app

if TYPE_CHECKING:
    from pathlib import Path


class TestDashboardApp:
    """Verify capability resolution, archetype CRUD schemas, workbench specs, and router wiring."""

    def test_resolve_enabled_modules_deduplicates_manifest_and_falls_back_expected(self) -> None:
        """Verify manifest deduplication, archetype defaults, and unknown archetype fallback."""
        # Arrange
        explicit = ("crud", "vault", "crud")

        # Act
        deduped = resolve_enabled_modules("workstation-control-tower", explicit)
        default_tutor = resolve_enabled_modules("academic-tutor-cockpit")
        fallback_unknown = resolve_enabled_modules("custom-archetype")

        # Assert
        assert deduped == ("crud", "vault")
        assert default_tutor == ("crud", "vault", "node_mesh", "telemetry")
        assert fallback_unknown == (
            "work_ledger",
            "crud",
            "vault",
            "node_mesh",
            "data_pipeline",
        )

    def test_resolve_enabled_modules_rejects_unknown_capability_slug_expected(self) -> None:
        """Verify bipolar guard rejects unrecognized capability module identifiers."""
        # Arrange
        invalid_list = ("crud", "unknown_capability")

        # Act
        with pytest.raises(ValueError, match="Unknown dashboard module") as exc_mod:
            resolve_enabled_modules("workstation-control-tower", invalid_list)

        # Assert
        assert "unknown_capability" in str(exc_mod.value)

    def test_archetype_crud_schema_and_modular_workbench_overlay_modes_expected(self) -> None:
        """Verify Socratic vs generic CRUD schemas and academic/enterprise/personal modes."""
        # Arrange
        tutor_arch = "academic-tutor-cockpit"

        # Act
        schema_tutor = resolve_archetype_crud_schema(tutor_arch)
        schema_know = resolve_archetype_crud_schema("knowledge-stewardship-portal")
        schema_default = resolve_archetype_crud_schema("workstation-control-tower")
        spec_school = build_modular_workbench_spec(tutor_arch, "school-student-m1-m2")
        spec_univ = build_modular_workbench_spec(tutor_arch, "university-specialty-m2-m3")
        spec_corp = build_modular_workbench_spec(
            "corporate-root-hub", "corporate-root-hub", enterprise_scale="medium-scaleup"
        )
        spec_work = build_modular_workbench_spec(
            "personal-work-cockpit", "personal-career-and-ventures"
        )

        # Assert
        assert schema_tutor.slug == "study-drills"
        assert schema_know.slug == "epistemic-entries"
        assert schema_default.slug == "workspace-records"
        assert ARCHETYPE_DEFAULT_PLUGIN["knowledge-stewardship-portal"] == (
            "knowledge-stewardship-portal"
        )
        assert set(MODULE_SWAP_URLS) == set(VALID_DASHBOARD_MODULES)
        assert spec_school["mode"] == "guided-socratic-m1-m2"
        assert spec_univ["mode"] == "specialty-dmcp-m2-m3"
        assert spec_corp["mode"] == "enterprise-medium-scaleup"
        assert spec_work["mode"] == "personal-career-and-ventures"

    def test_build_dashboard_routers_instantiates_all_seven_capabilities_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify build_dashboard_routers instantiates all 7 capability routers with overrides."""
        # Arrange
        states: list[WebAppState] = []
        create_web_app(state_out=states)
        state = states[0]
        custom_segs = (
            PayloadFieldSegment("headline", DisclosureTier.CORE_SUMMARY, "Custom Summary"),
        )

        # Act
        default_routers = build_dashboard_routers(
            tmp_path,
            enabled_modules=VALID_DASHBOARD_MODULES,
            layer_label="node-alpha",
            state=state,
        )
        custom_routers = build_dashboard_routers(
            tmp_path,
            enabled_modules=("crud", "role_projection"),
            layer_label="node-beta",
            state=state,
            view_archetype="academic-tutor-cockpit",
            projection_segments=custom_segs,
        )

        # Assert
        assert len(default_routers) == len(VALID_DASHBOARD_MODULES) == 7
        assert len(custom_routers) == 2
