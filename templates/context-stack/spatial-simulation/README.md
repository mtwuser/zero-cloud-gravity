# `spatial-simulation` (`context-stack`) — Tier 2 Spatial Scene Graphs, Digital Twins & `Zone.Z4` Blueprints

> Tier 2 domain specialization extending `science-base` for `SO(3)`/quaternion scene graphs, collision-free `[0.0..1.0]` radial explosion, analytical epoch propagation, `L0..L2` Digital Twins (`eBOM` / `glTF 2.0`), and `60 FPS` `Zone.Z4` Non-Photorealistic Blueprint atlases.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/spatial-simulation.md`](rules/spatial-simulation.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `spatial-simulation` | Domain specialization in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `context-stack` | Spatial Geometry, Simulation & Digital Twin Methodology Axis |
| **`tier`** | `2` (`Domain Specialization`) | Materialized into `.agents/rules/spatial-simulation.md` via `zcg sync-layer` |
| **`extends`** | `"science-base"` | Transitively resolves `universal-base -> science-base -> spatial-simulation` |
| **`rules_file`** | [`rules/spatial-simulation.md`](rules/spatial-simulation.md) | `SPATIAL-01..04` kinematics, membrane overlap $V_u \cap V_v$, and `60 FPS` `WCAG 2.2 AA` parity |

---

## 2. Core Mathematical & Rendering Invariants

The `spatial-simulation` specialization aligns interactive `Zone.Z4` web surfaces (`zcg.web.capabilities.spatial_atlas`) and engineering/scientific simulations (`sci-maths`, `sci-physics`, `sci-engineering`):

1. **Orthonormal Transforms & Analytical Epoch Evaluation**: Use `SO(3)` matrices or unit quaternions and evaluate closed-form trajectories at absolute SI epoch $t_{\text{next}}$ (`0` $\Delta t$ drift).
2. **Euclidean Relational Rest Distance & Membrane Intersection Lenses**: Map $W_{\text{rel}}(u, v) \in [0.0, 1.0]$ monotonically onto $d_0(u, v) = d_{\min} + (d_{\max} - d_{\min})(1 - W_{\text{rel}}(u, v))$ and sphere-lens intersection volume $V_u \cap V_v$.
3. **Decoupled `Float32Array` `60 FPS` Loop & `WCAG 2.2 AA` Parity**: Pre-allocate typed buffers, keep topological truth on the backend (*Dumb Renderer*), and expose full keyboard/table parity.

---

## 3. Mounting & Cross-References

Declare `spatial-simulation` in `system/zcg-node.json` under `default_stack_templates` and synchronize the workspace:

```bash
zcg sync-layer /path/to/simulation-or-atlas-node
```

- **Parent Human Stack**: [`templates/human-stack/science-base/README.md`](../../human-stack/science-base/README.md)
- **Web Engine Specification**: [`docs/architecture/06_web_and_api_application_engine.md`](../../../docs/architecture/06_web_and_api_application_engine.md)
- **Catalog Reference**: [`docs/reference/01_stack_and_plugin_matrix.md`](../../../docs/reference/01_stack_and_plugin_matrix.md)
