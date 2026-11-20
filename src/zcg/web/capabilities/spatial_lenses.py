"""Pure 5-Lens Analytical Projector for Zone.Z4 2D/3D Spatial Atlas Scenes.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Final

from zcg.web.capabilities.spatial_layout import (
    SpatialEdgeSpec,
    SpatialNodeSpec,
    compute_exploded_scene_layout,
    compute_sphere_intersection_volume,
)

DEFAULT_SPATIAL_LENS: Final[str] = "relational-affinity"
VALID_SPATIAL_LENSES: Final[tuple[str, ...]] = (
    "relational-affinity",
    "permission-ring-hierarchy",
    "structural-lineage",
    "operational-posture",
    "geographic-residency",
)
SPATIAL_LENS_DESCRIPTIONS: Final[dict[str, str]] = {
    "relational-affinity": (
        "Relational Affinity: Connected Core inside inner ring + Discoverable Horizon ordered by "
        "stack Jaccard overlap and Euclidean rest distance d0."
    ),
    "permission-ring-hierarchy": (
        "Permission Ring Hierarchy: Concentric capability strata from private local R3 core "
        "outward through internal R2, partner R1, and public R0."
    ),
    "structural-lineage": (
        "Structural Lineage: Top-down governance and AST package tiers (Root 0 / Core -> "
        "Department / Subsystem -> Squad / Consumer)."
    ),
    "operational-posture": (
        "Operational Posture: Dual-hemisphere separation between Sovereign local/public nodes "
        "(left) and Managed enterprise intranet nodes (right)."
    ),
    "geographic-residency": (
        "Coarse Jurisdictional Residency: Groups local loopback, statutory gov-/geo- corpora, "
        "enterprise intranet zones, and global open commons (0 GPS coordinates)."
    ),
}
_RING_RADII: Final[dict[str, float]] = {"R3": 44.0, "R2": 108.0, "R1": 172.0, "R0": 236.0}
_RING_Z: Final[dict[str, float]] = {"R3": -78.0, "R2": -26.0, "R1": 26.0, "R0": 78.0}
_RESIDENCY_CENTERS: Final[dict[str, tuple[float, float, float]]] = {
    "local-loopback": (-115.0, -75.0, -48.0),
    "jurisdictional-statutory": (115.0, -75.0, 32.0),
    "enterprise-intranet": (-115.0, 80.0, -16.0),
    "global-open-commons": (115.0, 80.0, 56.0),
}


def classify_coarse_residency_band(node_id: str, *, surface_ring: str, posture: str) -> str:
    """Classify a node into a coarse jurisdictional residency band without fine GPS tracking."""
    low = node_id.lower()
    if low.startswith(("gov-", "geo-", "admin-", "state-")):
        return "jurisdictional-statutory"
    if surface_ring == "R3":
        return "local-loopback"
    if posture == "managed" or surface_ring in ("R2", "R1"):
        return "enterprise-intranet"
    return "global-open-commons"


def _lineage_tier(spec: SpatialNodeSpec) -> int:
    if spec.parent_id is None and spec.precedence <= 20:
        return 0
    if spec.parent_id is None or spec.precedence <= 55:
        return 1
    return 2


def project_scene_with_lens(
    nodes: Sequence[SpatialNodeSpec],
    edges: Sequence[SpatialEdgeSpec],
    *,
    lens: str = DEFAULT_SPATIAL_LENS,
    explosion: float = 0.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Project an authoritative SpatialNodeSpec topology through one of the 5 analytical lenses."""
    if lens not in VALID_SPATIAL_LENSES:
        raise ValueError(f"Unsupported spatial lens: {lens!r}")
    scene = compute_exploded_scene_layout(nodes, edges, explosion=explosion, seed=seed)
    scene["lens"] = lens
    scene["lens_summary"] = SPATIAL_LENS_DESCRIPTIONS[lens]
    raw_nodes: list[dict[str, Any]] = scene["nodes"]
    if not raw_nodes:
        return scene
    if lens == "relational-affinity":
        for nd in raw_nodes:
            nd["lens_group"] = str(nd["zone_band"])
        return scene

    spec_by_id = {n.node_id: n for n in nodes}
    scale = 1.0 + 0.75 * float(scene["explosion"])
    buckets: dict[str, list[dict[str, Any]]] = {}
    for nd in raw_nodes:
        spec = spec_by_id[str(nd["node_id"])]
        if lens == "permission-ring-hierarchy":
            grp = f"ring-{spec.surface_ring}"
        elif lens == "structural-lineage":
            grp = f"tier-{_lineage_tier(spec)}"
        elif lens == "operational-posture":
            grp = f"{spec.posture}:{nd['zone_band']}"
        else:
            grp = classify_coarse_residency_band(
                spec.node_id, surface_ring=spec.surface_ring, posture=spec.posture
            )
        nd["lens_group"] = grp
        buckets.setdefault(grp, []).append(nd)

    for grp, members in buckets.items():
        cnt = len(members)
        for idx, nd in enumerate(members):
            spec = spec_by_id[str(nd["node_id"])]
            ang = (2.0 * math.pi * idx / cnt) + ((seed % 17) * 0.07)
            if lens == "permission-ring-hierarchy":
                rad = _RING_RADII.get(spec.surface_ring, 140.0) * scale
                px = 0.0 if cnt == 1 and spec.surface_ring == "R3" else rad * math.cos(ang)
                py = 0.0 if cnt == 1 and spec.surface_ring == "R3" else rad * math.sin(ang)
                pz = _RING_Z.get(spec.surface_ring, 0.0) * scale
            elif lens == "structural-lineage":
                tier = _lineage_tier(spec)
                spread = (idx - (cnt - 1) / 2.0) * 96.0 * scale
                px = spread
                py = (-112.0 + tier * 112.0) * scale
                pz = float((idx % 3 - 1) * 28.0) * scale
            elif lens == "operational-posture":
                hemi_x = -118.0 if spec.posture == "sovereign" else 118.0
                band_y = -52.0 if spec.is_connected else 88.0
                px = (hemi_x + 42.0 * math.cos(ang)) * scale
                py = (band_y + 42.0 * math.sin(ang)) * scale
                pz = (-24.0 if spec.posture == "sovereign" else 24.0) * scale
            else:
                cx, cy, cz = _RESIDENCY_CENTERS[grp]
                orbit = 0.0 if cnt == 1 else 46.0
                px = (cx + orbit * math.cos(ang)) * scale
                py = (cy + orbit * math.sin(ang)) * scale
                pz = (cz + float((idx % 2) * 18 - 9)) * scale
            nd["x"] = round(px, 4)
            nd["y"] = round(py, 4)
            nd["z"] = round(pz, 4)

    pose_map = {str(nd["node_id"]): nd for nd in raw_nodes}
    for ls in scene["lenses"]:
        sa = pose_map[str(ls["source_id"])]
        sb = pose_map[str(ls["target_id"])]
        dist = math.dist((sa["x"], sa["y"], sa["z"]), (sb["x"], sb["y"], sb["z"]))
        vol = compute_sphere_intersection_volume(
            float(sa["membrane_radius"]), float(sb["membrane_radius"]), dist
        )
        ls["euclidean_distance"] = round(dist, 4)
        ls["intersection_volume"] = round(vol, 4)
    return scene
