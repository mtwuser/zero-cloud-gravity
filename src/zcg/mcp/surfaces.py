"""3D surface governance projection and Lex Superior/Specialis weaving (resolve_surface_governance).

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from zcg.capsules.constants import (
    CHARS_PER_TOKEN_ESTIMATE,
    L2_EXCERPT_MAX_CHARS,
    L2_SECTION_MAX_CHARS,
    MAX_SURFACE_SECTIONS_PER_RULE,
    VALID_ARCHITECTURAL_PLANES,
    VALID_BINDING_MODES,
    VALID_RESOLUTIONS,
)
from zcg.capsules.markdown import (
    extract_axiom_skeleton,
    extract_l3_links,
    iter_markdown_sections,
    merge_unique_strings,
)
from zcg.capsules.surfaces import (
    binding_matches_surface,
    build_section_capsule,
    compute_binding_specificity,
    infer_plane_from_path,
    infer_scope_from_path,
)
from zcg.core.constants import ROLE_DEFAULT_PRECEDENCE, VALID_ENVIRONMENTS
from zcg.ephemeral.briefs import extract_ephemeral_advisories
from zcg.governance.consensus import collect_layer_effective_bindings
from zcg.mcp.unfold import UnfoldMixin
from zcg.topology.identity import resolve_node_entity_identity


class SurfaceGovernanceMixin(UnfoldMixin):
    """Implements 3D surface responsibility weaving across 0..N mounted layers."""

    def _resolve_binding_asset(
        self,
        rel_path: str,
        layer_dir: Path,
        layer_name: str,
        binding_id: str,
        asset_type: str,
        warnings_out: list[dict[str, Any]],
    ) -> Path | None:
        try:
            return self.resolve_safe_path(rel_path, layer_dir)
        except FileNotFoundError:
            warnings_out.append(
                self.emit_warning(
                    "WARN",
                    "SURFACE_ASSET_MISSING",
                    f"Binding {binding_id!r} in {layer_name!r} missing {asset_type} {rel_path!r}.",
                    {
                        "layer": layer_name,
                        "binding_id": binding_id,
                        "asset_type": asset_type,
                        "path": rel_path,
                    },
                )
            )
            return None

    def tool_resolve_surface_governance(self, args: dict[str, Any]) -> dict[str, Any]:
        """Project and weave governance rules across 0..N layers for a surface."""
        target_path = str(args.get("target_path", "")).strip()
        exp_plane = str(args.get("architectural_plane", "")).strip().lower()
        if exp_plane and exp_plane not in VALID_ARCHITECTURAL_PLANES:
            raise ValueError(f"Invalid architectural_plane {exp_plane!r}")
        exp_scope = str(args.get("scope", "")).strip().lower()
        traits_list = sorted(
            {str(t).strip().lower() for t in (args.get("traits") or []) if str(t).strip()}
        )
        traits_set = set(traits_list)
        if not (target_path or exp_plane or exp_scope or traits_set):
            raise ValueError("At least one surface selector must be provided")
        env_arg = str(args.get("environment", "")).strip().lower()
        if env_arg and env_arg not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment {env_arg!r}")
        res_override = str(args.get("resolution_override", "")).strip().upper()
        if res_override and res_override not in VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution_override {res_override!r}")
        include_capsules = bool(args.get("include_capsules", True))
        explicit_key = (
            str(args["resonance_key"]).strip() if args.get("resonance_key") is not None else ""
        )
        key_required = bool(explicit_key or os.environ.get("ZCG_RESONANCE_KEY", "").strip())
        secret, env_scope = self.resolve_resonance_secret(explicit_key or None), (env_arg or "all")
        issuer_id = str(self.load_layer_manifest().get("layer_id", "root"))
        eff_plane = exp_plane or infer_plane_from_path(target_path)
        eff_scope = exp_scope or infer_scope_from_path(target_path)

        layer_dirs = [
            self.repo_dir,
            *(self.repo_dir / str(m["relative_path"]) for m in self.discover_mounted_layers()),
        ]
        part_layers, pruned_layers = list[dict[str, Any]](), list[dict[str, Any]]()
        s_warns: list[dict[str, Any]] = []
        matched_recs: list[tuple[int, int, int, str, Path, str, str, dict[str, Any]]] = []
        layer_guards: list[tuple[int, list[str]]] = []

        for ldir in layer_dirs:
            lname = "root" if ldir == self.repo_dir else ldir.name
            manifest = self.load_layer_manifest(ldir)
            lid = str(manifest.get("layer_id", lname))
            lrole = str(manifest.get("layer_role", "service-node"))
            def_p = ROLE_DEFAULT_PRECEDENCE["corporate" if ldir == self.repo_dir else "squad"]
            l_prec = int(manifest.get("precedence", def_p))
            if not (0 <= l_prec <= 100):
                raise ValueError(f"Invalid layer precedence {l_prec} in {lname!r}: must be 0..100")
            raw_bindings = collect_layer_effective_bindings(ldir, manifest) or [
                {
                    "binding_id": f"{lname}-default-baseline",
                    "target_globs": ["**"],
                    "architectural_planes": ["*"],
                    "scopes": ["*"],
                    "traits": [],
                    "mode": "transversal",
                    "rule_files": ["antigravity/.gemini/config/AGENTS.md"],
                    "canonical_templates": [],
                    "invariants": list(manifest.get("baseline_guardrails", [])),
                }
            ]
            matched_in: list[dict[str, Any]] = []
            for b in raw_bindings:
                b_prec = int(b.get("precedence", l_prec))
                b_mode = str(b.get("mode", "transversal")).strip().lower()
                if not (0 <= b_prec <= 100):
                    raise ValueError(f"Invalid binding precedence {b_prec} in {lname!r}")
                if b_mode not in VALID_BINDING_MODES:
                    raise ValueError(f"Invalid surface_binding mode {b_mode!r}")
                if binding_matches_surface(b, target_path, eff_plane, eff_scope, traits_set):
                    matched_in.append(b)
            if not matched_in:
                pruned_layers.append(
                    {"layer": lname, "layer_id": lid, "layer_role": lrole, "precedence": l_prec}
                )
                continue
            has_auth = any(
                str(b.get("mode", "transversal")).strip().lower() == "authoritative"
                for b in matched_in
            )
            part_layers.append({
                "layer": lname, "layer_id": lid, "layer_role": lrole, "precedence": l_prec,
                "entity_identity": resolve_node_entity_identity(ldir, manifest),
                "has_authoritative_binding": has_auth, "matched_bindings_count": len(matched_in),
            })  # fmt: skip
            env_g = (
                manifest.get("environments", {}).get(env_arg, {}).get("default_guardrails", [])
                if env_arg
                else []
            )
            layer_guards.append((l_prec, [*manifest.get("baseline_guardrails", []), *env_g]))
            for b in matched_in:
                b_prec = int(b.get("precedence", l_prec))
                m_rank = (
                    0 if str(b.get("mode", "transversal")).strip().lower() == "authoritative" else 1
                )
                matched_recs.append(
                    (b_prec, m_rank, -compute_binding_specificity(b), lname, ldir, lid, lrole, b)
                )

        part_layers.sort(key=lambda i: (int(i["precedence"]), str(i["layer_id"])))
        matched_recs.sort(key=lambda r: (r[0], r[1], r[2], r[5], str(r[7].get("binding_id", ""))))
        layer_guards.sort(key=lambda i: i[0])
        col_groups: dict[tuple[int, str], list[str]] = {}
        for b_prec, m_rank, _, lname, *_ in matched_recs:
            ckey = (b_prec, "authoritative" if m_rank == 0 else "transversal")
            col_groups[ckey] = merge_unique_strings(col_groups.get(ckey, []), [lname])
        for (c_prec, c_mode), c_layers in sorted(col_groups.items()):
            if len(c_layers) > 1:
                s_warns.append(self.emit_warning(
                    "WARN", "SURFACE_PRECEDENCE_COLLISION",
                    f"Multiple layers {c_layers} matched at precedence={c_prec}, mode={c_mode!r}.",
                    {"precedence": c_prec, "mode": c_mode, "layers": c_layers},
                ))  # fmt: skip

        res_bindings = list[dict[str, Any]]()
        inv_groups, tpl_groups = [g for _, g in layer_guards], list[list[str]]()
        ret_toks = cap_toks = base_toks = 0
        s_trunc = False
        for b_prec, m_rank, neg_spec, lname, ldir, lid, lrole, b in matched_recs:
            mode = "authoritative" if m_rank == 0 else "transversal"
            b_res = str(b.get("default_resolution", "")).strip().upper()
            res = res_override or (
                b_res if b_res in VALID_RESOLUTIONS else ("L2" if mode == "authoritative" else "L1")
            )
            bid = str(b.get("binding_id", f"{lname}-binding"))
            b_invs = [str(inv) for inv in b.get("invariants", []) if str(inv).strip()]
            v_tpls = [
                str(t)
                for t in b.get("canonical_templates", [])
                if str(t).strip()
                and self._resolve_binding_asset(
                    str(t), ldir, lname, bid, "canonical_template", s_warns
                )
                is not None
            ]
            inv_groups.append(b_invs)
            tpl_groups.append([f"{lname}:{t}" for t in v_tpls])
            secs_out: list[dict[str, Any]] = []
            for rf_rel in b.get("rule_files", []):
                rf_p = self._resolve_binding_asset(
                    str(rf_rel), ldir, lname, bid, "rule_file", s_warns
                )
                if rf_p is None:
                    continue
                lines = rf_p.read_text(encoding="utf-8").splitlines()
                rel_in = str(rf_p.relative_to(ldir)).replace("\\", "/")
                all_secs = iter_markdown_sections(lines, rf_p.name)
                if len(all_secs) > MAX_SURFACE_SECTIONS_PER_RULE:
                    s_trunc = True
                for heading, s_ln, e_ln, body in all_secs[:MAX_SURFACE_SECTIONS_PER_RULE]:
                    joined = "\n".join(body)
                    if res == "L2" and len(joined) > L2_EXCERPT_MAX_CHARS:
                        s_trunc = True
                    l2_exc, l2_full = joined[:L2_EXCERPT_MAX_CHARS], joined[:L2_SECTION_MAX_CHARS]
                    l1_skel = extract_axiom_skeleton(heading, body)
                    l3_links = (
                        []
                        if lname == "ephemeral-project-bridge"
                        else extract_l3_links(rf_p, joined, ldir)
                    )
                    p_codon, c_tok = build_section_capsule(
                        issuer_id=issuer_id,
                        resolution=res,
                        layer_name=lname,
                        rel_in_layer=rel_in,
                        heading=heading,
                        start_line=s_ln,
                        end_line=e_ln,
                        scope=eff_scope or "all",
                        l1_skeleton=l1_skel,
                        l2_excerpt=l2_exc,
                        l2_full=l2_full,
                        l3_links=l3_links,
                        env_scope=env_scope,
                        secret=secret,
                        key_required=key_required,
                    )
                    sec_e: dict[str, Any] = {
                        "file": str(rf_p.relative_to(self.repo_dir)), "layer": lname,
                        "section": heading, "start_line": s_ln, "end_line": e_ln,
                        "resolution": res, "promoter_codon": p_codon,
                        "capsule_token": c_tok if include_capsules else None,
                    }  # fmt: skip
                    if res == "L0":
                        sec_e["surface_preview"] = (
                            f"{p_codon['codon']} ({', '.join(p_codon['tags'])})"
                        )
                    elif res == "L1":
                        sec_e["axiom_skeleton"] = l1_skel
                        sec_e["excerpt"] = l1_skel
                    else:
                        sec_e["excerpt"] = l2_exc
                    secs_out.append(sec_e)
                    ret_toks += int(p_codon["token_estimates"][res])
                    base_toks += int(p_codon["token_estimates"]["L2"])
                    if include_capsules:
                        cap_toks += len(c_tok) // CHARS_PER_TOKEN_ESTIMATE
            b_entry: dict[str, Any] = {
                "binding_id": bid, "layer": lname, "layer_id": lid, "layer_role": lrole,
                "precedence": b_prec, "specificity_score": -neg_spec, "mode": mode,
                "resolution": res, "invariants": b_invs, "canonical_templates": v_tpls,
                "sections": secs_out,
            }  # fmt: skip
            if isinstance(b.get("ephemeral_fork_policy"), dict):
                b_entry["ephemeral_fork_policy"] = dict(b["ephemeral_fork_policy"])
            res_bindings.append(b_entry)

        if s_trunc:
            s_warns.append(self.emit_warning(
                "WARN", "RESPONSE_TRUNCATED", "Surface governance sections truncated.",
                {"target_path": target_path},
            ))  # fmt: skip
        saved = max(0, base_toks - ret_toks)
        pct = round((saved / base_toks) * 100, 1) if base_toks else 0.0
        advisories = extract_ephemeral_advisories(res_bindings, target_path)
        payload = {
            "surface_query": {
                "target_path": target_path, "effective_plane": eff_plane or "all",
                "effective_scope": eff_scope or "all", "traits": traits_list,
                "environment": env_scope, "resolution_mode": res_override or "adaptive",
            },
            "precedence_policy": "Lex Superior (0..100), authoritative > transversal, Specialis.",
            "participating_layers_count": len(part_layers), "participating_layers": part_layers,
            "pruned_layers_count": len(pruned_layers), "pruned_layers": pruned_layers,
            "resolved_bindings_count": len(res_bindings), "resolved_bindings": res_bindings,
            "effective_invariants": merge_unique_strings(*inv_groups),
            "canonical_templates": merge_unique_strings(*tpl_groups),
            "ephemeral_delegation_advisories": advisories,
            "token_compaction_metrics": {
                "resolution": res_override or "adaptive", "returned_estimated_tokens": ret_toks,
                "capsule_overhead_tokens": cap_toks, "full_l2_baseline_tokens": base_toks,
                "tokens_saved": saved, "savings_pct": pct,
            },
            "truncated": s_trunc, "warnings": s_warns,
        }  # fmt: skip
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }
