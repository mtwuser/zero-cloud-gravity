"""Pure 3D Zone.Z4 Spatial Layout, Radial Explosion, and Sphere Intersection Math.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

MIN_EXPLOSION_FACTOR: Final[float] = 0.0
MAX_EXPLOSION_FACTOR: Final[float] = 1.0
DEFAULT_EXPLOSION_RADIAL_GAIN: Final[float] = 1.35
DEFAULT_MIN_REST_DISTANCE: Final[float] = 80.0
DEFAULT_MAX_REST_DISTANCE: Final[float] = 320.0
DEFAULT_CORE_RADIUS: Final[float] = 220.0
DEFAULT_HORIZON_RADIUS: Final[float] = 330.0
DEFAULT_RIGID_CORE_RATIO: Final[float] = 0.35

VALID_EDGE_RELATIONS: Final[tuple[str, ...]] = (
    "1-hop-hierarchy",
    "linked-peer",
    "knowledge-feed",
    "unconnected-horizon",
)
_RELATION_BANDS: Final[dict[str, tuple[float, float]]] = {
    "1-hop-hierarchy": (0.85, 0.15),
    "linked-peer": (0.55, 0.29),
    "knowledge-feed": (0.35, 0.19),
    "unconnected-horizon": (0.05, 0.25),
}
_PRESET_SPECS: Final[dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "constellation-4-pillar": (
        (
            "persona-profile|Personal Root 0|workstation|90|R3|54|universal-base||1|S",
            "persona-tutor|Personal Tutor|department|86|R3|48|academic-base|persona-profile|1|S",
            "persona-work|Career Hub|department|87|R3|48|software-engineering|persona-profile|1|S",
            "persona-wallet|Wallet Airlock|department|88|R3|46|science-base|persona-profile|1|S",
            "pub-persona|Public Twin|knowledge|20|R0|44|software-engineering|persona-work|1|S",
            "sci-economic|Econ Corpus|knowledge|20|R0|42|science-base||0|S",
        ),
        (
            "persona-profile|persona-tutor|1-hop-hierarchy|0.92|universal-base",
            "persona-profile|persona-work|1-hop-hierarchy|0.90|universal-base",
            "persona-profile|persona-wallet|1-hop-hierarchy|0.88|universal-base",
            "persona-work|pub-persona|linked-peer|0.78|software-engineering",
        ),
    ),
    "enterprise-dual-zone": (
        (
            "corp-alpha|Enterprise Root|corporate|10|R2|56|business-base||1|M",
            "dept-legal|Legal & SecOps|domain-policy|5|R2|50|nist-csf-security|corp-alpha|1|M",
            "dept-tech|Cloud & Eng|department|25|R2|50|spatial-simulation|corp-alpha|1|M",
            "org-alpha|Public Brand|knowledge|20|R0|44|business-base|corp-alpha|1|M",
        ),
        (
            "corp-alpha|dept-legal|1-hop-hierarchy|0.95|corporate-operations",
            "corp-alpha|dept-tech|1-hop-hierarchy|0.90|software-engineering",
            "corp-alpha|org-alpha|linked-peer|0.82|business-base",
        ),
    ),
    "epistemic-corpora-mesh": (
        (
            "sci-maths|Formal Maths|knowledge|20|R0|52|science-base,spatial-simulation||1|S",
            "sci-physics|Orbital Physics|knowledge|20|R0|52|spatial-simulation|sci-maths|1|S",
            "sci-engineering|CAD/eBOM Corpus|knowledge|20|R0|48|spatial-simulation|sci-maths|1|S",
            "gov-es|Statutory Corpus|knowledge|20|R0|46|business-base||0|S",
        ),
        (
            "sci-maths|sci-physics|knowledge-feed|0.88|spatial-simulation",
            "sci-maths|sci-engineering|knowledge-feed|0.84|spatial-simulation",
        ),
    ),
    "attested-public-federation": (
        (
            "zcg-org|zerocloudgravity.org|workstation|10|R0|58|spatial-simulation||1|S",
            "zcg-dev|zerocloudgravity.dev|service-node|20|R0|48|software-engineering|zcg-org|1|S",
            "pub-persona|Personal Twin (CV)|knowledge|20|R0|46|software-engineering|zcg-org|1|S",
            "org-corp-alpha|Enterprise Twin|knowledge|20|R0|46|business-base|zcg-org|1|S",
        ),
        (
            "zcg-org|zcg-dev|1-hop-hierarchy|0.96|software-engineering",
            "zcg-org|pub-persona|linked-peer|0.74|universal-base",
            "zcg-org|org-corp-alpha|linked-peer|0.72|software-engineering",
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class SpatialNodeSpec:
    """Authoritative topological node specification for Zone.Z4 spatial projection."""

    node_id: str
    label: str
    layer_role: str
    precedence: int
    surface_ring: str = "R3"
    membrane_radius: float = 48.0
    capability_tags: tuple[str, ...] = ()
    parent_id: str | None = None
    is_connected: bool = True
    posture: str = "sovereign"


@dataclass(frozen=True, slots=True)
class SpatialEdgeSpec:
    """Authoritative relational link or 1-hop hierarchy edge between two spatial nodes."""

    source_id: str
    target_id: str
    relation_kind: str = "1-hop-hierarchy"
    interaction_weight: float = 0.5
    shared_packs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComputedNodePose:
    """Deterministic 3D Euclidean pose, rigid inner radius, and Blueprint membrane envelope."""

    node_id: str
    label: str
    layer_role: str
    precedence: int
    surface_ring: str
    zone_band: str
    x: float
    y: float
    z: float
    rigid_radius: float
    membrane_radius: float
    jaccard_affinity: float
    capability_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize pose to a JSON-compatible dictionary."""
        return {
            "node_id": self.node_id,
            "label": self.label,
            "layer_role": self.layer_role,
            "precedence": self.precedence,
            "surface_ring": self.surface_ring,
            "zone_band": self.zone_band,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
            "rigid_radius": round(self.rigid_radius, 4),
            "membrane_radius": round(self.membrane_radius, 4),
            "jaccard_affinity": round(self.jaccard_affinity, 4),
            "capability_tags": list(self.capability_tags),
        }


@dataclass(frozen=True, slots=True)
class MembraneOverlapLens:
    """Computed Euclidean rest distance d0 and sphere intersection lens volume V_u cap V_v."""

    source_id: str
    target_id: str
    relation_kind: str
    relational_weight: float
    rest_distance: float
    euclidean_distance: float
    intersection_volume: float
    shared_packs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize membrane intersection lens to a JSON-compatible dictionary."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_kind": self.relation_kind,
            "relational_weight": round(self.relational_weight, 4),
            "rest_distance": round(self.rest_distance, 4),
            "euclidean_distance": round(self.euclidean_distance, 4),
            "intersection_volume": round(self.intersection_volume, 4),
            "shared_packs": list(self.shared_packs),
        }


def clamp_explosion_factor(value: float) -> float:
    """Clamp radial explosion factor into [0.0, 1.0], rejecting NaN or infinite inputs."""
    if not math.isfinite(value):
        raise ValueError("Explosion factor must be a finite float")
    return max(MIN_EXPLOSION_FACTOR, min(MAX_EXPLOSION_FACTOR, value))


def compute_jaccard_affinity(tags_a: Sequence[str], tags_b: Sequence[str]) -> float:
    """Compute capability-fingerprint Jaccard similarity |A cap B| / |A cup B| in [0.0, 1.0]."""
    set_a, set_b = set(tags_a), set(tags_b)
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def compute_relational_weight(
    edge: SpatialEdgeSpec, tags_a: Sequence[str] = (), tags_b: Sequence[str] = ()
) -> float:
    """Rank relational weight strictly as 1-hop > linked-peer > knowledge-feed > horizon."""
    if edge.relation_kind not in _RELATION_BANDS:
        raise ValueError(f"Unsupported relation_kind: {edge.relation_kind!r}")
    base, span = _RELATION_BANDS[edge.relation_kind]
    w_inter = clamp_explosion_factor(edge.interaction_weight)
    affinity = compute_jaccard_affinity(tags_a, tags_b)
    pack_bonus = min(1.0, len(edge.shared_packs) * 0.25)
    return min(1.0, base + span * (0.55 * w_inter + 0.30 * affinity + 0.15 * pack_bonus))


def compute_euclidean_rest_distance(
    weight: float,
    *,
    d_min: float = DEFAULT_MIN_REST_DISTANCE,
    d_max: float = DEFAULT_MAX_REST_DISTANCE,
) -> float:
    """Compute spring rest distance d0 = d_min + (d_max - d_min) * (1 - W_rel)."""
    if not all(map(math.isfinite, (weight, d_min, d_max))):
        raise ValueError("Rest distance inputs must be finite")
    if d_min <= 0.0 or d_max < d_min:
        raise ValueError("Rest distance bounds require 0 < d_min <= d_max")
    return d_min + (d_max - d_min) * (1.0 - clamp_explosion_factor(weight))


def compute_sphere_intersection_volume(r1: float, r2: float, distance: float) -> float:
    """Compute exact 3D spherical cap lens volume V_u cap V_v across all 3 distance regimes."""
    if not all(map(math.isfinite, (r1, r2, distance))) or min(r1, r2, distance) < 0.0:
        raise ValueError("Sphere radii and distance must be non-negative finite numbers")
    if r1 == 0.0 or r2 == 0.0 or distance >= r1 + r2:
        return 0.0
    if distance <= abs(r1 - r2):
        return (4.0 / 3.0) * math.pi * (min(r1, r2) ** 3)
    sum_r, diff_r = r1 + r2, r1 - r2
    num = (
        math.pi
        * ((sum_r - distance) ** 2)
        * (distance**2 + 2.0 * distance * sum_r - 3.0 * (diff_r**2))
    )
    return num / (12.0 * distance)


def _resolve_rigid_collisions(coords: list[list[float]], rigid_radii: Sequence[float]) -> None:
    for _ in range(4):
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                dx, dy, dz = (coords[j][k] - coords[i][k] for k in range(3))
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                min_sep = rigid_radii[i] + rigid_radii[j]
                if dist < 1e-6:
                    push = 0.5 * min_sep + 0.5
                    coords[i][0] -= push
                    coords[j][0] += push
                elif dist < min_sep:
                    overlap = 0.5 * (min_sep - dist + 0.25)
                    for k, delta in enumerate((dx, dy, dz)):
                        step = (delta / dist) * overlap
                        coords[i][k] -= step
                        coords[j][k] += step


def compute_exploded_scene_layout(
    nodes: Sequence[SpatialNodeSpec],
    edges: Sequence[SpatialEdgeSpec],
    *,
    explosion: float = 0.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Compute deterministic 3D poses, radial [0.0..1.0] explosion, and membrane lenses."""
    alpha = clamp_explosion_factor(explosion)
    meta = {
        "explosion": alpha,
        "seed": seed,
        "core_radius": DEFAULT_CORE_RADIUS,
        "horizon_radius": DEFAULT_HORIZON_RADIUS,
    }
    if not nodes:
        return {**meta, "federation_posture": "sovereign", "nodes": [], "edges": [], "lenses": []}
    posture = "managed" if any(n.posture == "managed" for n in nodes) else "sovereign"
    core_tags = tuple({tag for n in nodes if n.is_connected for tag in n.capability_tags})
    ordered: list[SpatialNodeSpec] = [
        *[n for n in nodes if n.is_connected],
        *sorted(
            (n for n in nodes if not n.is_connected),
            key=lambda it: (-compute_jaccard_affinity(it.capability_tags, core_tags), it.node_id),
        ),
    ]
    scale = 1.0 + DEFAULT_EXPLOSION_RADIAL_GAIN * alpha
    coords: list[list[float]] = []
    affinities = [compute_jaccard_affinity(n.capability_tags, core_tags) for n in ordered]
    rigid_radii = [max(8.0, n.membrane_radius * DEFAULT_RIGID_CORE_RATIO) for n in ordered]
    for idx, node in enumerate(ordered):
        if node.is_connected:
            if node.parent_id is None and (idx == 0 or node.precedence <= 10):
                coords.append([0.0, 0.0, 0.0])
            else:
                r_b = min(DEFAULT_CORE_RADIUS * 0.45, 52.0 + (node.precedence % 40) * 0.8)
                ang = (((seed * 13) + idx * 9) % 360) * (math.pi / 180.0)
                z0 = float((idx % 2) * 4 - 2)
                coords.append(
                    [r_b * math.cos(ang) * scale, r_b * math.sin(ang) * scale, z0 * scale]
                )
        else:
            r_h = (DEFAULT_HORIZON_RADIUS - 45.0 * affinities[idx]) * (1.0 + 0.35 * alpha)
            ang = (((seed * 29) + idx * 73) % 360) * (math.pi / 180.0)
            coords.append([r_h * math.cos(ang), r_h * math.sin(ang), 24.0 * (1.0 + alpha)])
    _resolve_rigid_collisions(coords, rigid_radii)
    pose_by_id: dict[str, ComputedNodePose] = {}
    spec_by_id: dict[str, SpatialNodeSpec] = {n.node_id: n for n in ordered}
    for idx, node in enumerate(ordered):
        px, py, pz = coords[idx]
        band = "connected-core" if node.is_connected else "unconnected-horizon"
        pose_by_id[node.node_id] = ComputedNodePose(
            node.node_id,
            node.label,
            node.layer_role,
            node.precedence,
            node.surface_ring,
            band,
            px,
            py,
            pz,
            rigid_radii[idx],
            node.membrane_radius,
            affinities[idx],
            node.capability_tags,
        )
    lenses: list[MembraneOverlapLens] = []
    for edge in edges:
        src, dst = pose_by_id.get(edge.source_id), pose_by_id.get(edge.target_id)
        if src is None or dst is None:
            continue
        w_rel = compute_relational_weight(
            edge, spec_by_id[src.node_id].capability_tags, spec_by_id[dst.node_id].capability_tags
        )
        d_now = math.dist((src.x, src.y, src.z), (dst.x, dst.y, dst.z))
        vol = compute_sphere_intersection_volume(src.membrane_radius, dst.membrane_radius, d_now)
        lenses.append(
            MembraneOverlapLens(
                edge.source_id,
                edge.target_id,
                edge.relation_kind,
                w_rel,
                compute_euclidean_rest_distance(w_rel),
                d_now,
                vol,
                edge.shared_packs,
            )
        )
    edge_dicts = [
        {"source_id": e.source_id, "target_id": e.target_id, "relation_kind": e.relation_kind}
        for e in edges
        if e.source_id in spec_by_id and e.target_id in spec_by_id
    ]
    return {
        **meta,
        "federation_posture": posture,
        "nodes": [p.to_dict() for p in pose_by_id.values()],
        "edges": edge_dicts,
        "lenses": [ls.to_dict() for ls in lenses],
    }


def _decode_node_row(row: str) -> SpatialNodeSpec:
    nid, lbl, role, pr, rg, rd, tg, pa, cn, po = row.split("|")
    tags = tuple(item for item in tg.split(",") if item)
    posture = "managed" if po == "M" else "sovereign"
    return SpatialNodeSpec(
        nid, lbl, role, int(pr), rg, float(rd), tags, pa or None, cn == "1", posture
    )


def _decode_edge_row(row: str) -> SpatialEdgeSpec:
    s, t, rel, w, pk = row.split("|")
    return SpatialEdgeSpec(s, t, rel, float(w), tuple(item for item in pk.split(",") if item))


def build_reference_spatial_presets() -> dict[
    str, tuple[tuple[SpatialNodeSpec, ...], tuple[SpatialEdgeSpec, ...]]
]:
    """Return 4 ISO-neutral reference topologies for Zone.Z4 exploration and public showcases."""
    return {
        name: (tuple(map(_decode_node_row, nr)), tuple(map(_decode_edge_row, er)))
        for name, (nr, er) in _PRESET_SPECS.items()
    }
