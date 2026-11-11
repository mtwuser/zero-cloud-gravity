"""Multi-resolution governance rule search and rcap1 compaction (query_governance_rules).

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from zcg.capsules.constants import (
    CHARS_PER_TOKEN_ESTIMATE,
    CODON_STOPWORDS,
    L2_EXCERPT_MAX_CHARS,
    L2_SECTION_MAX_CHARS,
    MAX_QUERY_GOVERNANCE_MATCHES,
    VALID_RESOLUTIONS,
)
from zcg.capsules.grcc import list_git_branch_markdown_files
from zcg.capsules.markdown import (
    extract_axiom_skeleton,
    extract_l3_links,
    iter_markdown_sections,
    resolve_section_hierarchy,
)
from zcg.capsules.surfaces import build_section_capsule
from zcg.core.constants import EPISTEMIC_GRADE_RANK, VALID_ENVIRONMENTS, VALID_EPISTEMIC_GRADES
from zcg.core.epistemics import resolve_effective_human_stack
from zcg.core.manifests import iter_layer_template_dirs, read_version
from zcg.mcp.node_base import MCPNodeBase


def _normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


class CompactionMixin(MCPNodeBase):
    """Implements session secret resolution and multi-resolution query_governance_rules."""

    def resolve_resonance_secret(self, explicit_key: str | None = None) -> bytes:
        """Resolve session secret from explicit arg, ZCG_RESONANCE_KEY, or version fallback."""
        raw_key = (
            (explicit_key or "").strip()
            or os.environ.get("ZCG_RESONANCE_KEY", "").strip()
            or f"zcg-resonance-v1:{read_version(self.repo_dir)}"
        )
        return raw_key.encode("utf-8")

    def _collect_disk_markdown_sources(
        self, layer_dirs: list[Path], scope: str, raw_tpath: str
    ) -> list[tuple[str, Path, Path, str]]:
        cands: list[tuple[str, Path, Path]] = []
        for ldir in layer_dirs:
            lname = "root" if ldir == self.repo_dir else ldir.name
            if raw_tpath:
                cands.append((lname, ldir, ldir / raw_tpath))
            if scope in ("all", "global"):
                cands.append((lname, ldir, ldir / "antigravity/.gemini/config/AGENTS.md"))
            if scope in ("all", "templates"):
                for _tname, tdir in iter_layer_template_dirs(ldir):
                    cands.extend((lname, ldir, tf) for tf in sorted((tdir / "rules").glob("*.md")))
                    if scope == "all":
                        cands.extend(
                            (lname, ldir, sf) for sf in sorted((tdir / "skills").rglob("*.md"))
                        )
            if scope in ("all", "docs"):
                if scope == "all":
                    cands.append((lname, ldir, ldir / "README.md"))
                for sub in ("docs", "corporate", "surfaces") if scope == "all" else ("docs",):
                    cands.extend((lname, ldir, df) for df in sorted((ldir / sub).rglob("*.md")))
        seen_files: set[tuple[str, Path]] = set()
        out: list[tuple[str, Path, Path, str]] = []
        for lname, ldir, fp in cands:
            res_fp = fp.resolve()
            if (
                fp.suffix == ".md"
                and fp.is_file()
                and res_fp.is_relative_to(ldir.resolve())
                and (lname, res_fp) not in seen_files
            ):
                seen_files.add((lname, res_fp))
                out.append((lname, ldir, fp, fp.read_text(encoding="utf-8")))
        return out

    def tool_query_governance_rules(self, args: dict[str, Any]) -> dict[str, Any]:
        """Search node rules, templates, and docs with L0/L1/L2 rcap1 compaction."""
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("'query' must be a non-empty string")
        scope = str(args.get("scope", "all"))
        resolution = str(args.get("resolution", "L2")).strip().upper() or "L2"
        if resolution not in VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution {resolution!r}: must be in {VALID_RESOLUTIONS}")
        env_arg = str(args.get("environment", "")).strip().lower()
        if env_arg and env_arg not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment {env_arg!r}: must be in {VALID_ENVIRONMENTS}")
        min_ep_arg = str(args.get("min_epistemic_grade") or "E0").strip().upper()
        if min_ep_arg not in VALID_EPISTEMIC_GRADES:
            raise ValueError(f"Invalid min_epistemic_grade {min_ep_arg!r}")
        min_ep_rank, env_scope = EPISTEMIC_GRADE_RANK[min_ep_arg], (env_arg or "all")
        include_capsules = bool(args.get("include_capsules", True))
        explicit_key = (
            str(args["resonance_key"]).strip() if args.get("resonance_key") is not None else ""
        )
        key_required = bool(explicit_key or os.environ.get("ZCG_RESONANCE_KEY", "").strip())
        secret = self.resolve_resonance_secret(explicit_key or None)
        issuer_id = str(self.load_layer_manifest().get("layer_id", "root"))
        layer_arg = str(args.get("layer", "all")).strip() or "all"
        layer_dirs = (
            [
                self.repo_dir,
                *(self.repo_dir / str(m["relative_path"]) for m in self.discover_mounted_layers()),
            ]
            if layer_arg == "all"
            else [self.resolve_layer_dir(layer_arg)]
        )
        raw_tpath = str(args.get("target_path", "")).strip()
        branch_ref = str(args.get("branch_ref") or "").strip()
        dmcp_projection: dict[str, Any] | None = None
        if branch_ref:
            source_items: list[tuple[str, Path, Path, str]] = []
            branch_sha = ""
            for ldir in layer_dirs:
                lname = "root" if ldir == self.repo_dir else ldir.name
                b_sha, b_docs = list_git_branch_markdown_files(
                    ldir, branch_ref, scope=scope, target_path=raw_tpath
                )
                branch_sha = branch_sha or b_sha
                source_items.extend((lname, ldir, ldir / rel_p, txt) for rel_p, txt in b_docs)
            dmcp_projection = {
                "branch_ref": branch_ref,
                "commit_sha": branch_sha,
                "zero_checkout": True,
            }
        else:
            source_items = self._collect_disk_markdown_sources(layer_dirs, scope, raw_tpath)

        matches, excerpt_truncated = list[dict[str, Any]](), False
        q_low = _normalize_ascii(query)
        q_tokens = [t for t in re.findall(r"[a-z0-9_-]{3,}", q_low) if t not in CODON_STOPWORDS]
        t_set = {(ldir / raw_tpath).resolve() for ldir in layer_dirs} if raw_tpath else set()
        for lname, ldir, fp, doc_text in source_items:
            min_toks = 1 if (fp.resolve() in t_set and len(q_tokens) >= 3) else 2
            lines = doc_text.splitlines()
            for heading, s_ln, e_ln, body in iter_markdown_sections(lines, fp.name):
                h_depth, sec_path = resolve_section_hierarchy(lines, s_ln, heading)
                joined = "\n".join(body)
                haystack = _normalize_ascii(f"{sec_path}\n{joined}")
                if q_low in haystack or (
                    len(q_tokens) >= 2 and sum(1 for t in q_tokens if t in haystack) >= min_toks
                ):
                    l2_exc, l2_full = joined[:L2_EXCERPT_MAX_CHARS], joined[:L2_SECTION_MAX_CHARS]
                    l1_skel = extract_axiom_skeleton(heading, body)
                    l3_links = extract_l3_links(fp, joined, ldir)
                    rel_in = str(fp.relative_to(ldir)).replace("\\", "/")
                    p_codon, cap_tok = build_section_capsule(
                        issuer_id=issuer_id,
                        resolution=resolution,
                        layer_name=lname,
                        rel_in_layer=rel_in,
                        heading=heading,
                        start_line=s_ln,
                        end_line=e_ln,
                        scope=scope,
                        l1_skeleton=l1_skel,
                        l2_excerpt=l2_exc,
                        l2_full=l2_full,
                        l3_links=l3_links,
                        env_scope=env_scope,
                        secret=secret,
                        key_required=key_required,
                        heading_depth=h_depth,
                        section_path=sec_path,
                    )
                    ep_grade = str(p_codon["epistemic_grade"])
                    if EPISTEMIC_GRADE_RANK[ep_grade] < min_ep_rank:
                        continue
                    if resolution == "L2" and len(joined) > L2_EXCERPT_MAX_CHARS:
                        excerpt_truncated = True
                    entry: dict[str, Any] = {
                        "file": str(fp.relative_to(self.repo_dir)), "layer": lname,
                        "section": heading, "section_path": sec_path, "heading_depth": h_depth,
                        "epistemic_grade": ep_grade, "epistemic_label": p_codon["epistemic_label"],
                        "abstraction_layer": p_codon["abstraction_layer"],
                        "citation_receipt": p_codon["citation_receipt"],
                        "l3_targets": p_codon["l3_targets"], "start_line": s_ln, "end_line": e_ln,
                        "promoter_codon": {
                            "codon": p_codon["codon"], "tags": p_codon["tags"],
                            "has_l3_substrate": p_codon["has_l3_substrate"],
                            "l3_links_count": p_codon["l3_links_count"],
                            "token_estimates": p_codon["token_estimates"],
                        },
                        "capsule_token": cap_tok if include_capsules else None,
                    }  # fmt: skip
                    if resolution == "L0":
                        entry["surface_preview"] = (
                            f"{p_codon['codon']} ({', '.join(p_codon['tags'])})"
                        )
                    elif resolution == "L1":
                        entry["axiom_skeleton"] = l1_skel
                        entry["excerpt"] = l1_skel
                    else:
                        entry["excerpt"] = l2_exc
                    matches.append(entry)

        hs_facets = resolve_effective_human_stack(self.repo_dir)["facets"]
        is_acad = any(f.endswith((":M1", ":M2")) or f == "soft-socratic-coach" for f in hs_facets)
        matches.sort(
            key=lambda m: (
                0 if (is_acad and "docs/guides/" in str(m["file"])) else 1,
                -EPISTEMIC_GRADE_RANK[str(m["epistemic_grade"])],
                int(m["heading_depth"]) if resolution in ("L0", "L1") else 0,
                int(m["start_line"]),
            )
        )
        total_m = len(matches)
        ret_m = matches[:MAX_QUERY_GOVERNANCE_MATCHES]
        ret_toks = sum(int(m["promoter_codon"]["token_estimates"][resolution]) for m in ret_m)
        cap_toks = (
            sum(len(str(m["capsule_token"])) // CHARS_PER_TOKEN_ESTIMATE for m in ret_m)
            if include_capsules
            else 0
        )
        base_toks = sum(int(m["promoter_codon"]["token_estimates"]["L2"]) for m in ret_m)
        saved = max(0, base_toks - ret_toks)
        q_warns = (
            [
                self.emit_warning(
                    "WARN",
                    "RESPONSE_TRUNCATED",
                    f"Query matched {total_m} section(s); narrow 'query', 'scope', or 'layer'.",
                    {"query": query, "total_matches": total_m},
                )
            ]
            if (total_m > MAX_QUERY_GOVERNANCE_MATCHES or excerpt_truncated)
            else []
        )
        viewpoint = "academic-tutor-m1-m2" if is_acad else "professional-scientific-m3-m4"
        pct = round((saved / base_toks) * 100, 1) if base_toks else 0.0
        payload = {
            "query": query, "scope": scope, "layer": layer_arg, "resolution": resolution,
            "min_epistemic_grade": min_ep_arg, "consumer_viewpoint": viewpoint,
            "include_capsules": include_capsules, "dmcp_projection": dmcp_projection,
            "token_compaction_metrics": {
                "resolution": resolution, "returned_estimated_tokens": ret_toks,
                "capsule_overhead_tokens": cap_toks, "full_l2_baseline_tokens": base_toks,
                "tokens_saved": saved, "savings_pct": pct,
            },
            "total_matches_found": total_m, "match_count": len(ret_m),
            "truncated": bool(q_warns), "warnings": q_warns, "matches": ret_m,
        }  # fmt: skip
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }
