"""Unit tests for zcg.web.capabilities.spatial_lenses.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import pytest

from zcg.web.capabilities.spatial_layout import SpatialEdgeSpec, SpatialNodeSpec
from zcg.web.capabilities.spatial_lenses import (
    DEFAULT_SPATIAL_LENS,
    SPATIAL_LENS_DESCRIPTIONS,
    VALID_SPATIAL_LENSES,
    classify_coarse_residency_band,
    project_scene_with_lens,
)


class TestSpatialLenses:
    """Verify all 5 analytical Zone.Z4 spatial lenses, residency bands, and lens recomputation."""

    def test_classify_coarse_residency_band_all_four_regimes_expected(self) -> None:
        """Verify coarse jurisdictional grouping with 0 fine GPS coordinates."""
        # Arrange
        cases = (
            ("gov-es", "R0", "sovereign"),
            ("persona-profile", "R3", "sovereign"),
            ("corp-alpha", "R2", "managed"),
            ("sci-maths", "R0", "sovereign"),
        )

        # Act
        results = tuple(
            classify_coarse_residency_band(nid, surface_ring=ring, posture=pos)
            for nid, ring, pos in cases
        )

        # Assert
        assert results == (
            "jurisdictional-statutory",
            "local-loopback",
            "enterprise-intranet",
            "global-open-commons",
        )

    def test_project_scene_with_all_five_lenses_and_bipolar_guards_expected(self) -> None:
        """Verify empty scene, all 5 lenses (tiers/rings/postures/residency), and invalid guard."""
        # Arrange
        nodes = (
            SpatialNodeSpec(
                "corp-root",
                "Root 0",
                "corporate",
                10,
                surface_ring="R2",
                posture="managed",
                capability_tags=("business-base",),
            ),
            SpatialNodeSpec(
                "solo-profile",
                "Personal Profile",
                "workstation",
                90,
                surface_ring="R3",
                posture="sovereign",
                capability_tags=("universal-base",),
            ),
            SpatialNodeSpec(
                "dept-eng",
                "Dept Eng",
                "department",
                30,
                surface_ring="R2",
                parent_id="corp-root",
                posture="managed",
                capability_tags=("software-engineering",),
            ),
            SpatialNodeSpec(
                "squad-web",
                "Squad Web",
                "squad",
                80,
                surface_ring="R1",
                parent_id="dept-eng",
                posture="sovereign",
                capability_tags=("software-engineering",),
            ),
            SpatialNodeSpec(
                "gov-iso",
                "Statutory",
                "knowledge",
                20,
                surface_ring="R0",
                is_connected=False,
                posture="sovereign",
                capability_tags=("business-base",),
            ),
            SpatialNodeSpec(
                "sci-maths",
                "Maths",
                "knowledge",
                20,
                surface_ring="R0",
                is_connected=False,
                posture="sovereign",
                capability_tags=("science-base",),
            ),
            SpatialNodeSpec(
                "sci-physics",
                "Physics",
                "knowledge",
                20,
                surface_ring="R0",
                is_connected=False,
                posture="sovereign",
                capability_tags=("science-base",),
            ),
        )
        edges = (
            SpatialEdgeSpec("corp-root", "dept-eng", "1-hop-hierarchy", 0.9, ("business-base",)),
            SpatialEdgeSpec(
                "dept-eng", "squad-web", "1-hop-hierarchy", 0.85, ("software-engineering",)
            ),
        )

        # Act
        empty = project_scene_with_lens((), (), lens=DEFAULT_SPATIAL_LENS)
        by_lens = {
            ln: project_scene_with_lens(nodes, edges, lens=ln, explosion=0.3, seed=19)
            for ln in VALID_SPATIAL_LENSES
        }

        # Assert
        assert empty["nodes"] == [] and empty["lens"] == DEFAULT_SPATIAL_LENS
        assert set(SPATIAL_LENS_DESCRIPTIONS) == set(VALID_SPATIAL_LENSES)
        ring_nodes = {n["node_id"]: n for n in by_lens["permission-ring-hierarchy"]["nodes"]}
        assert ring_nodes["solo-profile"]["x"] == 0.0 and ring_nodes["solo-profile"]["y"] == 0.0
        assert ring_nodes["solo-profile"]["z"] < ring_nodes["gov-iso"]["z"]

        lin_nodes = {n["node_id"]: n for n in by_lens["structural-lineage"]["nodes"]}
        assert lin_nodes["corp-root"]["lens_group"] == "tier-0"
        assert lin_nodes["dept-eng"]["lens_group"] == "tier-1"
        assert lin_nodes["squad-web"]["lens_group"] == "tier-2"
        assert (
            lin_nodes["corp-root"]["y"] < lin_nodes["dept-eng"]["y"] < lin_nodes["squad-web"]["y"]
        )

        pos_nodes = {n["node_id"]: n for n in by_lens["operational-posture"]["nodes"]}
        assert pos_nodes["solo-profile"]["x"] < 0.0 < pos_nodes["corp-root"]["x"]

        geo_nodes = {n["node_id"]: n for n in by_lens["geographic-residency"]["nodes"]}
        assert geo_nodes["gov-iso"]["lens_group"] == "jurisdictional-statutory"
        assert geo_nodes["sci-maths"]["lens_group"] == "global-open-commons"
        assert len(by_lens["geographic-residency"]["lenses"]) == 2

        with pytest.raises(ValueError, match="Unsupported spatial lens"):
            project_scene_with_lens(nodes, edges, lens="gps-precise")
