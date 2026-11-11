# Accessibility Statement (`WCAG 2.2 AA`)

**ZeroCloudGravity (`zero-cloud-gravity`)** is committed to ensuring that every Zero-Cloud Node Cockpit (`surfaces/web/index.html`), CLI output (`zcg`), and documentation surface (`docs/`) is accessible, keyboard-navigable, and screen-reader friendly.

---

## Zero-Build HTML5 Cockpit Accessibility Contract

All five role-default `plugin-stack` cockpits rendered by [surfaces.py](src/zcg/cockpit/surfaces.py) comply with **WCAG 2.2 Level AA** standards:

| Accessibility Dimension | Concrete Implementation |
| :--- | :--- |
| **Semantic Landmarks** | Uses native `<header>`, `<main>`, `<section>`, `<table>`, `<thead>`, and `<th scope="col">` elements with explicit `<html lang="en">` metadata. |
| **Color Contrast** | High-contrast slate/sky palette (`#f8fafc` primary text on `#0f172a`/`#1e293b` surfaces, contrast ratio `> 11:1`, exceeding the `4.5:1` AA minimum). |
| **Keyboard & Screen Readers** | Zero client-side JS traps, focus-stealing modals, or unlabeled icon-only controls; all interactive intranet links carry descriptive visible text. |
| **Zero Unsolicited Browser Spawns** | Automated scripts, CI pipelines, `pytest`, and `zcg-mcp` honor `ZCG_NO_BROWSER=1` and `NO_COLOR=1` for predictable terminal and assistive-technology workflows. |

---

## Documentation & Cognitive Accessibility (`human-stack` `M1..M4`)

- **Progressive Disclosure**: Documentation follows a strict 3-tier hierarchy (`README.md` $\rightarrow$ `docs/guides/` $\rightarrow$ `docs/{architecture,reference}/`) with `#..####` headings (`0` `#####`) and 1-line lead sentences preceding every table, diagram, and code block.
- **Cognitive Adaptation (`M1..M4`)**: Through `human-stack` profiles (`universal-base`, `academic-base`, `science-base`, `business-base`) and `--lang <en|es|it|fr|de|pt>`, Antigravity agents adapt explanation density from step-by-step scaffolding (`M1`) to concise peer synthesis (`M4`).
