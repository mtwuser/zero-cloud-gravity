---
trigger: always_on
description: "Spatial scene graphs, SO(3)/quaternion transforms, AABB/OBB radial explosion, analytical epoch propagation, L0..L2 Digital Twins, and 60 FPS Zone.Z4 Blueprint rendering (spatial-simulation)."
---

# Spatial Geometry, Digital Twins & `Zone.Z4` Simulation Rules (`spatial-simulation`)

> Governs 2D/3D spatial atlases, CAD/`eBOM` Digital Twins, orbital/kinematic simulations, and `Zone.Z4` Non-Photorealistic Blueprint surfaces (`context-stack`, `extends: science-base`).

---

## Scope & Surface Target

- **Template Pack**: `templates/context-stack/spatial-simulation/` (`context-stack`, `extends: science-base`).
- **Applies**: Engineering, simulation, robotics, aerospace, territorial (`geo-*`), and multi-node topology workspaces rendering `Zone.Z4` (`IMMERSIVE_SYNC..IMMERSIVE_PIPELINE`) spatial surfaces or `glTF 2.0` / `eBOM` Digital Twins.

---

## Normative Invariants

1. **`SPATIAL-01` — Rigorous `SO(3)` / Quaternion Kinematics & Analytical Epoch Propagation (`0` $\Delta t$ Drift)**:
   - Represent 3D orientations via orthonormal $SO(3)$ matrices ($\det(\mathbf{R}) = +1$, $\mathbf{R}^\top \mathbf{R} = \mathbf{I}$) or unit quaternions $q = (w, x, y, z)$ ($\|q\|_2 = 1$) composed into $4 \times 4$ homogeneous scene-graph transforms; never chain unconstrained Euler angles susceptible to gimbal lock.
   - Evaluate deterministic analytical trajectories (e.g., two-body Keplerian elements or closed-form parametric paths) as direct functions of absolute SI epoch $t_{\text{next}}$ (`0` cumulative $\Delta t$ integration drift); reserve explicit adaptive/symplectic numerical integrators (Cowell / Runge-Kutta-Fehlberg) strictly for non-conservative perturbed regimes, declaring step tolerances in SI units.
2. **`SPATIAL-02` — Collision-Free Radial Explosion (`[0.0..1.0]`), Relational Distance & Membrane Overlap (`V_u ∩ V_v`)**:
   - Displace hierarchical child assemblies radially from parent centroid $\mathbf{c}$ along bounded `AABB/OBB` rays $\mathbf{p}(\alpha) = \mathbf{c} + (1 + \lambda \alpha)(\mathbf{p}_0 - \mathbf{c})$ for $\alpha \in [0.0, 1.0]$ while preserving rigid inner-core separation (`0` interpenetrating inner cores).
   - Encode topological relational weight $W_{\text{rel}}(u, v) \in [0.0, 1.0]$ directly in spatial geometry via monotonic Euclidean rest distance $d_0(u, v) = d_{\min} + (d_{\max} - d_{\min})(1 - W_{\text{rel}}(u, v))$ (`1-hop` $>$ `linked-peer` $>$ `knowledge-feed` inside $R_{\text{core}}$; Jaccard capability affinity in the outer horizon $r > R_{\text{core}}$) and analytical 3D sphere-lens intersection volume $V_u \cap V_v$ rendered as translucent Non-Photorealistic Blueprint membranes (`20–40%` alpha + crisp wireframe edges).
3. **`SPATIAL-03` — `L0 -> L1 -> L2` Digital Twin Property Architecture & Backend Topological Truth (*Dumb Renderer*)**:
   - Separate spatial entity state across three orthogonal layers: **`L0` (`Atomic / Dynamic`)** real-time pose/telemetry streams, **`L1` (`Canonical / Structural`)** `eBOM` / `glTF 2.0` / node-manifest identity and invariant mass/geometry bounds, and **`L2` (`Visual / Logical`)** Blueprint shaders, selection highlights, and bilateral proximity actions (`+A`, `-A`, `±A`).
   - Keep the backend as the sole source of topological and physical truth (*Dumb Renderer* contract): clients never invent authoritative links or bypass server-side capability gates.
4. **`SPATIAL-04` — `16.67 ms` (`60 FPS`) Decoupled Render Loop, `Float32Array` Buffers & `WCAG 2.2 AA` Tabular Parity**:
   - Decouple the `requestAnimationFrame` render loop (`<= 16.67 ms` budget) from DOM layout/reflow mutations, pre-allocate contiguous `Float32Array` pose/vertex buffers (`0` per-frame heap churn), seed force/radial layouts deterministically, and pair every `Zone.Z4` canvas with a keyboard-operable `WCAG 2.2 AA` accessible tabular view.

---

## Verification & Sign-Off Gates

- [ ] Analytical geometry, rest-distance, and sphere-intersection cut-points (`d >= r1 + r2`, `d <= |r1 - r2|`, partial overlap) pass `100.00%` isolated `AAA` unit coverage.
- [ ] Every `Zone.Z4` spatial view exposes a `WCAG 2.2 AA` accessible table/keyboard toggle and deterministic layout seed.
