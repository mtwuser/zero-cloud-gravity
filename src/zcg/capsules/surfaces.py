"""3D surface selector matching, section capsule minting, and multi-layer pattern comparison.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from zcg.capsules.citations import build_citation_receipt, infer_epistemic_grade
from zcg.capsules.codec import compute_digest16, derive_chain_key, seal_single_capsule
from zcg.capsules.constants import (
    CAPSULE_ABSTRACTION_LAYERS,
    CHARS_PER_TOKEN_ESTIMATE,
    GLOB_WILDCARD_SUFFIX_LEN,
    L1_FALLBACK_EST_TOKENS,
    LEVEL_MIN_TIER,
    MIN_ROUTING_KEYWORD_LEN,
    NEXT_LEVEL_MAP,
    PLANE_PATH_RULES,
    SPECIFICITY_WEIGHT_GLOB,
    SPECIFICITY_WEIGHT_PLANE,
    SPECIFICITY_WEIGHT_SCOPE,
    SPECIFICITY_WEIGHT_TRAIT,
    STRUCTURAL_PATH_SEGMENTS,
)
from zcg.capsules.markdown import extract_codon_tags, slugify_codon
from zcg.core.constants import AGENTS_MD_MAX_BYTES, MATERIALIZED_RULE_RE
from zcg.core.manifests import iter_layer_template_dirs, parse_skill_frontmatter
from zcg.governance.consensus import collect_layer_effective_bindings


def infer_plane_from_path(rel_path: str) -> str:
    """Infer stack-agnostic architectural plane from a relative path."""
    norm = rel_path.strip().replace("\\", "/").lstrip("/").lower()
    return next((p for p, toks in PLANE_PATH_RULES if any(t in norm for t in toks)), "")


def infer_scope_from_path(rel_path: str) -> str:
    """Infer bounded-context or feature scope segment from a relative path."""
    segs = rel_path.strip().replace("\\", "/").strip("/").split("/")
    parts = [p for p in segs if p and "." not in p and p.lower() not in STRUCTURAL_PATH_SEGMENTS]
    return parts[0].lower() if parts else ""


def _glob_matches(rel_path: str, pattern: str) -> bool:
    norm_path = rel_path.strip().replace("\\", "/").lstrip("/")
    norm_pat = pattern.strip().replace("\\", "/").lstrip("/")
    collapsed = norm_pat.replace("/**/", "/").removeprefix("**/")
    return bool(
        norm_pat == "**"
        or fnmatch.fnmatchcase(norm_path, norm_pat)
        or fnmatch.fnmatchcase(norm_path, collapsed)
        or (norm_pat.endswith("/**") and norm_path.startswith(norm_pat[:-GLOB_WILDCARD_SUFFIX_LEN]))
    )


def binding_matches_surface(
    binding: dict[str, Any], target_path: str, plane: str, scope: str, traits: set[str]
) -> bool:
    """Return True when binding selectors match target_path, plane, scope, and traits."""
    globs = [str(g) for g in binding.get("target_globs", ["**"])]
    planes = [str(p).lower() for p in binding.get("architectural_planes", ["*"])]
    scopes = [str(s).lower() for s in binding.get("scopes", ["*"])]
    req_traits = {str(t).lower() for t in binding.get("traits", [])}
    glob_ok = not target_path or any(_glob_matches(target_path, g) for g in globs)
    plane_ok = not plane or "*" in planes or plane in planes
    glob_seg_ok = bool(
        target_path
        and scope
        and any(
            _glob_matches(target_path, g) and scope in g.lower().replace("\\", "/").split("/")
            for g in globs
            if g not in ("*", "**")
        )
    )
    scope_ok = not scope or "*" in scopes or scope in scopes or glob_seg_ok
    traits_ok = not req_traits or "*" in req_traits or bool(req_traits & traits)
    return glob_ok and plane_ok and scope_ok and traits_ok


def compute_binding_specificity(binding: dict[str, Any]) -> int:
    """Compute deterministic Lex Specialis selector specificity score."""
    globs = [str(g).strip() for g in binding.get("target_globs", ["**"]) if str(g).strip()]
    planes = [
        str(p).strip().lower() for p in binding.get("architectural_planes", ["*"]) if str(p).strip()
    ]
    scopes = [str(s).strip().lower() for s in binding.get("scopes", ["*"]) if str(s).strip()]
    traits = [str(t).strip().lower() for t in binding.get("traits", []) if str(t).strip(" *")]
    g_pts = SPECIFICITY_WEIGHT_GLOB if (globs and "**" not in globs and "*" not in globs) else 0
    p_pts = SPECIFICITY_WEIGHT_PLANE if (planes and "*" not in planes) else 0
    s_pts = SPECIFICITY_WEIGHT_SCOPE if (scopes and "*" not in scopes) else 0
    return g_pts + p_pts + s_pts + (SPECIFICITY_WEIGHT_TRAIT * len(traits))


def build_section_capsule(
    *,
    issuer_id: str,
    resolution: str,
    layer_name: str,
    rel_in_layer: str,
    heading: str,
    start_line: int,
    end_line: int,
    scope: str,
    l1_skeleton: str,
    l2_excerpt: str,
    l2_full: str,
    l3_links: list[dict[str, Any]],
    env_scope: str,
    secret: bytes,
    key_required: bool = False,
    heading_depth: int = 1,
    section_path: str = "",
) -> tuple[dict[str, Any], str]:
    """Build promoter codon metadata and seal an rcap1 capsule for a Markdown section."""
    l0_summary = f"[{layer_name}] {rel_in_layer} :: {heading}"
    l3_tokens = sum(int(item["estimated_tokens"]) for item in l3_links) + L1_FALLBACK_EST_TOKENS
    cost_map = {
        "L0": max(1, len(l0_summary) // CHARS_PER_TOKEN_ESTIMATE),
        "L1": max(1, len(l1_skeleton) // CHARS_PER_TOKEN_ESTIMATE),
        "L2": max(1, len(l2_excerpt) // CHARS_PER_TOKEN_ESTIMATE),
        "L3": l3_tokens,
    }
    tags = extract_codon_tags(heading, l2_excerpt)
    ep_grade, ep_label = infer_epistemic_grade(rel_in_layer, heading, l2_excerpt)
    l3_targets = [{"path": str(i["path"]), "sha256_prefix": str(i["sha256"])} for i in l3_links]
    h0 = compute_digest16(layer_name, rel_in_layer, heading)
    h1 = compute_digest16(h0, l1_skeleton)
    h2 = compute_digest16(h1, l2_full)
    h3 = compute_digest16(h2, *(f"{i['path']}:{i['sha256']}" for i in l3_links))
    promoter_codon = {
        "codon": f"AUG:{scope}:{slugify_codon(heading)}:UAA",
        "layer": layer_name,
        "epistemic_grade": ep_grade,
        "epistemic_label": ep_label,
        "abstraction_layer": CAPSULE_ABSTRACTION_LAYERS[resolution],
        "heading_depth": heading_depth,
        "section_path": section_path or heading,
        "tags": tags,
        "has_l3_substrate": bool(l3_targets),
        "l3_links_count": len(l3_links),
        "l3_targets": l3_targets,
        "token_estimates": cost_map,
        "citation_receipt": build_citation_receipt(layer_name, rel_in_layer, heading, h2, ep_grade),
    }
    digest_by_level = {"L0": h0, "L1": h1, "L2": h2, "L3": h3}
    nxt, ph = NEXT_LEVEL_MAP[resolution], digest_by_level[resolution]
    min_tier = "pro" if (env_scope == "pro" and nxt == "L3") else LEVEL_MIN_TIER[nxt]
    hdr = {
        "lvl": resolution,
        "next": nxt,
        "iss": issuer_id,
        "lyr": layer_name,
        "sec": heading,
        "eg": ep_grade,
        "cap": min_tier,
        "env": env_scope,
        "kr": key_required,
        "ph": ph,
    }
    inner_lvl = {
        "ph": ph,
        "f": rel_in_layer,
        "s": start_line,
        "e": end_line,
        "h1": h1,
        "hd": digest_by_level,
    }
    ck = derive_chain_key(secret, layer_name, resolution, ph, env_scope)
    return promoter_codon, seal_single_capsule(hdr, inner_lvl, ck)


def compare_project_patterns_multilayer(
    repo_dir: Path,
    mounted_layers: list[dict[str, Any]],
    *,
    project_rules: list[str],
    project_skills: list[str],
    target_dirs: list[tuple[str, Path, dict[str, Any]]],
) -> dict[str, Any]:
    """Compare consumer project rules/skills across 1..N layers and route promotions."""
    layer_a_skills, layer_b_rules, layer_b_skills = set[str](), set[str](), set[str]()
    layer_records: list[dict[str, Any]] = []
    for lname, ldir, manifest in target_dirs:
        for sf in (ldir / "antigravity/.gemini/config/skills").glob("*/SKILL.md"):
            for s_id in (parse_skill_frontmatter(sf, ldir)["name"], sf.parent.name):
                layer_a_skills.add(s_id)
        tpl_names: list[str] = []
        for tname, tdir in iter_layer_template_dirs(ldir):
            tpl_names.append(tname)
            for rf in (tdir / "rules").glob("*.md"):
                layer_b_rules.add(rf.name)
            for sf in (tdir / "skills").glob("*/SKILL.md"):
                for s_id in (parse_skill_frontmatter(sf, ldir)["name"], sf.parent.name):
                    layer_b_skills.add(s_id)
        kw = {
            t
            for t in re.split(r"[-_]", f"{lname}-{manifest.get('layer_id', '')}".lower())
            if len(t) >= MIN_ROUTING_KEYWORD_LEN
        }
        for b in collect_layer_effective_bindings(ldir, manifest):
            for k in ("scopes", "traits"):
                for v in b.get(k, []):
                    if v != "*":
                        kw.add(str(v).lower())
        layer_records.append(
            {
                "name": lname,
                "layer_id": manifest.get("layer_id", lname),
                "layer_role": manifest.get("layer_role", "workstation"),
                "templates": tpl_names,
                "keywords": kw,
            }
        )
    mat_rules = [r for r in project_rules if MATERIALIZED_RULE_RE.match(r)]
    filt_rules = [r for r in project_rules if not MATERIALIZED_RULE_RE.match(r)]
    novel_rules = sorted(r for r in filt_rules if r not in layer_b_rules)
    novel_skills = sorted(s for s in project_skills if s not in (layer_a_skills | layer_b_skills))
    root_ag = repo_dir / "antigravity/.gemini/config/AGENTS.md"
    headroom = max(0, AGENTS_MD_MAX_BYTES - (root_ag.stat().st_size if root_ag.is_file() else 0))

    def _route(item_name: str, item_kind: str) -> dict[str, Any]:
        stem = item_name.removesuffix(".md").lower()
        tokens = {t for t in re.split(r"[-_.]", stem) if len(t) >= MIN_ROUTING_KEYWORD_LEN}
        for rec in layer_records:
            lname = str(rec["name"])
            if lname != "root" and (lname in stem or bool(tokens & set(rec["keywords"]))):
                tpls = list(rec["templates"])
                sfx = "AGENTS.md" if item_kind == "rules" else f"skills/{stem}/SKILL.md"
                dest = (
                    f"layers/{lname}/templates/{tpls[0]}/{item_kind}/{item_name}"
                    if tpls
                    else f"layers/{lname}/antigravity/.gemini/config/{sfx}"
                )
                return {
                    "item": item_name,
                    "kind": item_kind,
                    "target_layer": lname,
                    "target_role": rec["layer_role"],
                    "target_destination": dest,
                    "subtree_push_command": f"zcg subtree-push {lname} feat/promote-{stem}",
                }
        r_tpls = list(layer_records[0]["templates"])
        if item_kind == "rules" and r_tpls:
            dest, scope = (
                f"templates/{r_tpls[0]}/rules/{item_name}",
                f"template-pack:root:{r_tpls[0]}",
            )
        elif item_kind == "skills":
            dest, scope = f"antigravity/.gemini/config/skills/{stem}/SKILL.md", "global-skills-root"
        else:
            dest, scope = "antigravity/.gemini/config/AGENTS.md", "global-agents-root"
        return {
            "item": item_name,
            "kind": item_kind,
            "target_layer": "root",
            "target_scope": scope,
            "target_role": layer_records[0]["layer_role"],
            "target_destination": dest,
            "root_agents_md_headroom_bytes": headroom,
        }

    routing = [
        *(_route(r, "rules") for r in novel_rules),
        *(_route(s, "skills") for s in novel_skills),
    ]
    return {
        "compared_against_layer": (
            target_dirs[0][2].get("layer_id") if len(target_dirs) == 1 else "all"
        ),
        "promotion_routing": routing,
        "layers_scanned": [r["name"] for r in layer_records],
        "mounted_layers_count": len(mounted_layers),
        "materialized_layer_rules": sorted(mat_rules),
        "already_in_layer_a_skills": sorted(s for s in project_skills if s in layer_a_skills),
        "already_in_layer_b_templates": {
            "rules": sorted(r for r in filt_rules if r in layer_b_rules),
            "skills": sorted(s for s in project_skills if s in layer_b_skills),
        },
        "candidates_for_upward_promotion": {
            "novel_rules": novel_rules,
            "novel_skills": novel_skills,
        },
        "available_in_layer_b_but_missing_in_project": {
            "rules": sorted(r for r in layer_b_rules if r not in filt_rules),
            "skills": sorted(s for s in layer_b_skills if s not in project_skills),
        },
    }
