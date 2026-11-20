"""Unit tests for zcg.web.capabilities.spatial_layout.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import math

import pytest

from zcg.web.capabilities.spatial_layout import (
    DEFAULT_CORE_RADIUS,
    DEFAULT_MAX_REST_DISTANCE,
    DEFAULT_MIN_REST_DISTANCE,
    MAX_EXPLOSION_FACTOR,
    MIN_EXPLOSION_FACTOR,
    SpatialEdgeSpec,
    SpatialNodeSpec,
    build_reference_spatial_presets,
    clamp_explosion_factor,
    compute_euclidean_rest_distance,
    compute_exploded_scene_layout,
    compute_jaccard_affinity,
    compute_relational_weight,
    compute_sphere_intersection_volume,
)


class TestSpatialLayout:
    """Verify pure 3D spatial poses, [0..1] radial explosion, collisions, and sphere lenses."""

    def test_clamp_explosion_factor_cut_points_and_non_finite_guard_expected(self) -> None:
        """Verify [0.0..1.0] clamping across N vs N+-1 cut-points and NaN/Inf rejection."""
        # Arrange
        low_val, mid_val, high_val = -0.25, 0.5, 1.75

        # Act
        clamped_low = clamp_explosion_factor(low_val)
        clamped_zero = clamp_explosion_factor(MIN_EXPLOSION_FACTOR)
        clamped_mid = clamp_explosion_factor(mid_val)
        clamped_one = clamp_explosion_factor(MAX_EXPLOSION_FACTOR)
        clamped_high = clamp_explosion_factor(high_val)

        # Assert
        assert clamped_low == 0.0
        assert clamped_zero == 0.0
        assert clamped_mid == 0.5
        assert clamped_one == 1.0
        assert clamped_high == 1.0
        with pytest.raises(ValueError, match="finite"):
            clamp_explosion_factor(math.nan)
        with pytest.raises(ValueError, match="finite"):
            clamp_explosion_factor(math.inf)

    def test_jaccard_affinity_and_relational_weight_hierarchy_expected(self) -> None:
        """Verify Jaccard capability overlap and 1-hop > linked-peer > knowledge-feed > horizon."""
        # Arrange
        tags_a = ("science-base", "software-engineering", "spatial-simulation")
        tags_b = ("science-base", "spatial-simulation", "google-cloud-iac")
        e_hop = SpatialEdgeSpec("root", "dept", "1-hop-hierarchy", 0.8, ("science-base",))
        e_peer = SpatialEdgeSpec("dept", "peer", "linked-peer", 0.8, ("science-base",))
        e_feed = SpatialEdgeSpec("dept", "sci-maths", "knowledge-feed", 0.8, ())
        e_hor = SpatialEdgeSpec("dept", "ext", "unconnected-horizon", 0.0, ())
        e_bad = SpatialEdgeSpec("dept", "ext", "invalid-kind", 0.5, ())

        # Act
        empty_jaccard = compute_jaccard_affinity((), ())
        partial_jaccard = compute_jaccard_affinity(tags_a, tags_b)
        w_hop = compute_relational_weight(e_hop, tags_a, tags_b)
        w_peer = compute_relational_weight(e_peer, tags_a, tags_b)
        w_feed = compute_relational_weight(e_feed, tags_a, tags_b)
        w_hor = compute_relational_weight(e_hor, tags_a, tags_b)

        # Assert
        assert empty_jaccard == 0.0
        assert partial_jaccard == pytest.approx(0.5)
        assert 1.0 >= w_hop > w_peer > w_feed > w_hor > 0.0
        with pytest.raises(ValueError, match="Unsupported relation_kind"):
            compute_relational_weight(e_bad)

    def test_euclidean_rest_distance_and_cut_point_guards_expected(self) -> None:
        """Verify d0 = d_min + (d_max - d_min)*(1 - W_rel) and invalid bound rejection."""
        # Arrange
        w_max, w_half, w_zero = 1.0, 0.5, 0.0

        # Act
        d_closest = compute_euclidean_rest_distance(w_max)
        d_mid = compute_euclidean_rest_distance(w_half)
        d_farthest = compute_euclidean_rest_distance(w_zero)

        # Assert
        assert d_closest == pytest.approx(DEFAULT_MIN_REST_DISTANCE)
        assert d_mid == pytest.approx((DEFAULT_MIN_REST_DISTANCE + DEFAULT_MAX_REST_DISTANCE) / 2.0)
        assert d_farthest == pytest.approx(DEFAULT_MAX_REST_DISTANCE)
        with pytest.raises(ValueError, match="Rest distance"):
            compute_euclidean_rest_distance(0.5, d_min=0.0, d_max=100.0)
        with pytest.raises(ValueError, match="Rest distance"):
            compute_euclidean_rest_distance(0.5, d_min=200.0, d_max=100.0)
        with pytest.raises(ValueError, match="finite"):
            compute_euclidean_rest_distance(math.nan)

    def test_sphere_intersection_volume_three_regimes_and_bipolar_guards_expected(self) -> None:
        """Verify disjoint, tangent, partial lens, and contained sphere intersection regimes."""
        # Arrange
        r_big, r_small = 30.0, 20.0
        expected_contained = (4.0 / 3.0) * math.pi * (r_small**3)

        # Act
        vol_zero_radius = compute_sphere_intersection_volume(0.0, r_small, 5.0)
        vol_disjoint = compute_sphere_intersection_volume(r_big, r_small, 55.0)
        vol_tangent = compute_sphere_intersection_volume(r_big, r_small, 50.0)
        vol_partial = compute_sphere_intersection_volume(r_big, r_small, 35.0)
        vol_contained_edge = compute_sphere_intersection_volume(r_big, r_small, 10.0)
        vol_concentric = compute_sphere_intersection_volume(r_big, r_small, 0.0)

        # Assert
        assert vol_zero_radius == 0.0
        assert vol_disjoint == 0.0
        assert vol_tangent == 0.0
        assert 0.0 < vol_partial < expected_contained
        assert vol_contained_edge == pytest.approx(expected_contained)
        assert vol_concentric == pytest.approx(expected_contained)
        with pytest.raises(ValueError, match="non-negative finite"):
            compute_sphere_intersection_volume(-1.0, r_small, 10.0)
        with pytest.raises(ValueError, match="non-negative finite"):
            compute_sphere_intersection_volume(r_big, r_small, math.inf)

    def test_exploded_scene_layout_core_vs_horizon_collisions_and_presets_expected(self) -> None:
        """Verify Connected Core vs Horizon halo, [0..1] radial expansion, and rigid separation."""
        # Arrange
        nodes = (
            SpatialNodeSpec(
                "persona-profile",
                "Personal Root 0",
                "workstation",
                90,
                membrane_radius=60.0,
                capability_tags=("universal-base", "science-base"),
            ),
            SpatialNodeSpec(
                "persona-tutor",
                "Personal Tutor",
                "department",
                86,
                membrane_radius=55.0,
                capability_tags=("universal-base", "academic-base"),
                parent_id="persona-profile",
            ),
            SpatialNodeSpec(
                "persona-dup",
                "Coincident Sibling",
                "department",
                86,
                membrane_radius=55.0,
                capability_tags=("science-base",),
                parent_id="persona-profile",
            ),
            SpatialNodeSpec(
                "sci-physics",
                "Physics Corpus",
                "knowledge",
                20,
                surface_ring="R0",
                membrane_radius=50.0,
                capability_tags=("science-base", "spatial-simulation"),
                is_connected=False,
            ),
        )
        edges = (
            SpatialEdgeSpec(
                "persona-profile", "persona-tutor", "1-hop-hierarchy", 0.9, ("universal-base",)
            ),
            SpatialEdgeSpec(
                "persona-profile", "persona-dup", "1-hop-hierarchy", 0.9, ("science-base",)
            ),
            SpatialEdgeSpec("persona-profile", "ghost-node", "linked-peer", 0.4, ()),
        )
        coincident_roots = (
            SpatialNodeSpec("root-a", "Root A", "corporate", 10, posture="managed"),
            SpatialNodeSpec("root-b", "Root B", "corporate", 10, posture="managed"),
        )

        # Act
        empty_scene = compute_exploded_scene_layout((), (), explosion=0.0, seed=7)
        compact_scene = compute_exploded_scene_layout(nodes, edges, explosion=0.0, seed=7)
        exploded_scene = compute_exploded_scene_layout(nodes, edges, explosion=1.0, seed=7)
        managed_scene = compute_exploded_scene_layout(coincident_roots, (), explosion=0.25, seed=11)
        presets = build_reference_spatial_presets()

        # Assert
        assert empty_scene["nodes"] == [] and empty_scene["edges"] == []
        assert len(compact_scene["edges"]) == 2
        by_id_0 = {n["node_id"]: n for n in compact_scene["nodes"]}
        by_id_1 = {n["node_id"]: n for n in exploded_scene["nodes"]}
        assert by_id_0["persona-profile"]["zone_band"] == "connected-core"
        assert by_id_0["sci-physics"]["zone_band"] == "unconnected-horizon"
        horizon_r0 = math.dist(
            (0.0, 0.0, 0.0),
            (by_id_0["sci-physics"]["x"], by_id_0["sci-physics"]["y"], by_id_0["sci-physics"]["z"]),
        )
        tutor_r0 = math.dist(
            (0.0, 0.0, 0.0),
            (
                by_id_0["persona-tutor"]["x"],
                by_id_0["persona-tutor"]["y"],
                by_id_0["persona-tutor"]["z"],
            ),
        )
        tutor_r1 = math.dist(
            (0.0, 0.0, 0.0),
            (
                by_id_1["persona-tutor"]["x"],
                by_id_1["persona-tutor"]["y"],
                by_id_1["persona-tutor"]["z"],
            ),
        )
        assert tutor_r0 <= DEFAULT_CORE_RADIUS < horizon_r0
        assert tutor_r1 > tutor_r0
        p_t, p_d = by_id_0["persona-tutor"], by_id_0["persona-dup"]
        rigid_dist = math.dist((p_t["x"], p_t["y"], p_t["z"]), (p_d["x"], p_d["y"], p_d["z"]))
        assert rigid_dist >= (p_t["rigid_radius"] + p_d["rigid_radius"]) - 1e-6
        assert len(compact_scene["lenses"]) == 2
        n_a, n_b = managed_scene["nodes"][0], managed_scene["nodes"][1]
        sep = math.dist((n_a["x"], n_a["y"], n_a["z"]), (n_b["x"], n_b["y"], n_b["z"]))
        assert sep >= (n_a["rigid_radius"] + n_b["rigid_radius"]) - 1e-6
        assert managed_scene["federation_posture"] == "managed"
        assert len(presets) == 4
