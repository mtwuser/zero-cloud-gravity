"""Progressive rcap1 capsule decapsulation and Merkle chain verification (L0->L1->L2->L3).

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import zlib
from typing import Any

from zcg.capsules.codec import (
    CapsuleError,
    compute_digest16,
    derive_chain_key,
    parse_capsule_envelope,
    seal_single_capsule,
    xor_keystream,
)
from zcg.capsules.constants import (
    AGENT_TIER_RANK,
    CAPSULE_ALERT_PREFIX_CHARS,
    L2_SECTION_MAX_CHARS,
    L3_EXCERPT_MAX_CHARS,
    LEVEL_INDEX,
    LEVEL_MIN_TIER,
    MAX_UNFOLDED_L3_LINKS,
    NEXT_LEVEL_MAP,
    VALID_CAPSULE_LEVELS,
)
from zcg.capsules.markdown import (
    extract_axiom_skeleton,
    extract_l3_links,
    iter_markdown_sections,
    merge_unique_strings,
)
from zcg.core.constants import (
    CAPSULE_HMAC_HEX_LEN,
    NODE_MANIFEST_REL_PATH,
    VALID_AGENT_TIERS,
    VALID_ENVIRONMENTS,
)
from zcg.ephemeral.lifecycle import default_ephemeral_root, reap_expired_ephemeral_forks
from zcg.mcp.compaction import CompactionMixin


class UnfoldMixin(CompactionMixin):
    """Implements ephemeral issuer lookup and unfold_context_capsule across L0->L3."""

    def resolve_ephemeral_issuer_meta(
        self, cap_issuer: str, expected_issuer: str
    ) -> dict[str, Any] | None:
        """Resolve active ephemeral metadata from memory store or on-disk zcg-node.json."""
        if not cap_issuer.startswith("eph-"):
            return None
        self.reap_expired_memory_forks()
        reap_expired_ephemeral_forks(self.repo_dir)
        mem_entry = self.ephemeral_memory_store.get(cap_issuer)
        if mem_entry and str(mem_entry.get("parent_layer_id", "")) == expected_issuer:
            return dict(mem_entry.get("manifest", {}).get("ephemeral_metadata", mem_entry))
        m_path = default_ephemeral_root(self.repo_dir) / cap_issuer / NODE_MANIFEST_REL_PATH
        if m_path.is_file():
            data = json.loads(m_path.read_text(encoding="utf-8"))
            meta = dict(data.get("ephemeral_metadata", {}))
            if str(meta.get("parent_layer_id", "")) == expected_issuer:
                return meta
        return None

    def tool_unfold_context_capsule(self, args: dict[str, Any]) -> dict[str, Any]:
        """Decrypt and decompress an rcap1 capsule across L0->L1->L2->L3 levels."""
        raw_token = str(args.get("capsule_token", "")).strip()
        try:
            header, signing_prefix, cipher_bytes, sig_hex = parse_capsule_envelope(raw_token)
        except ValueError as exc:
            self.emit_warning(
                "WARN",
                "CAPSULE_CHAIN_BROKEN",
                str(exc),
                {"capsule_prefix": raw_token[:CAPSULE_ALERT_PREFIX_CHARS]},
            )
            raise CapsuleError(f"{exc} [Recovery: Re-run query_governance_rules.]") from exc
        cur_lvl = str(header["lvl"])
        target_level = (
            str(args.get("target_level") or header.get("next", NEXT_LEVEL_MAP[cur_lvl]))
            .strip()
            .upper()
        )
        if target_level not in VALID_CAPSULE_LEVELS:
            raise ValueError(f"Invalid target_level {target_level!r}: in {VALID_CAPSULE_LEVELS}")
        agent_tier = str(args.get("agent_tier", "inherit")).strip().lower() or "inherit"
        if agent_tier not in VALID_AGENT_TIERS:
            raise ValueError(f"Invalid agent_tier {agent_tier!r}: in {VALID_AGENT_TIERS}")
        env_arg = str(args.get("environment", "")).strip().lower()
        if env_arg and env_arg not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment {env_arg!r}: in {VALID_ENVIRONMENTS}")

        expected_issuer = str(self.load_layer_manifest().get("layer_id", "root"))
        cap_issuer = str(header.get("iss") or expected_issuer)
        eph_meta = (
            self.resolve_ephemeral_issuer_meta(cap_issuer, expected_issuer)
            if cap_issuer != expected_issuer
            else None
        )
        if cap_issuer != expected_issuer and eph_meta is None:
            msg = f"Cross-node mismatch: issued by {cap_issuer!r}, expected {expected_issuer!r}."
            self.emit_warning(
                "WARN", "CAPSULE_RESONANCE_DENIED", msg, {"reason": "issuer_node_mismatch"}
            )
            raise CapsuleError(msg)
        cap_env = str(header.get("env", "all"))
        if cap_env != "all" and env_arg != cap_env:
            msg = f"Capsule bound to env {cap_env!r}; received {env_arg or 'unspecified'!r}."
            self.emit_warning(
                "WARN", "CAPSULE_RESONANCE_DENIED", msg, {"reason": "environment_mismatch"}
            )
            raise CapsuleError(msg)
        explicit_key = (
            str(args["resonance_key"]).strip()
            if args.get("resonance_key") is not None
            else str((eph_meta or {}).get("session_resonance_key") or "").strip()
        )
        if header.get("kr") is True and not (
            explicit_key or os.environ.get("ZCG_RESONANCE_KEY", "").strip()
        ):
            msg = "Capsule requires explicit resonance_key (header.kr=true) or ZCG_RESONANCE_KEY."
            self.emit_warning(
                "WARN", "CAPSULE_RESONANCE_DENIED", msg, {"reason": "missing_resonance_key"}
            )
            raise CapsuleError(msg)

        secret = self.resolve_resonance_secret(explicit_key or None)
        hdr_layer = str(header.get("lyr", "root"))
        step_key = derive_chain_key(secret, hdr_layer, cur_lvl, str(header.get("ph", "")), cap_env)
        exp_sig = hmac.new(step_key, signing_prefix.encode("ascii"), hashlib.sha256).hexdigest()[
            :CAPSULE_HMAC_HEX_LEN
        ]
        if not hmac.compare_digest(sig_hex, exp_sig):
            msg = "Capsule resonance signature verification failed."
            self.emit_warning("WARN", "CAPSULE_RESONANCE_DENIED", msg, {"reason": "hmac_mismatch"})
            raise CapsuleError(msg)

        if target_level == "L0":
            res_l0 = {
                "unfolded_level": "L0", "unfold_chain": [], "decrypted_hops": 0,
                "chain_verified": True, "truncated": False, "warnings": [],
                "promoter_codon": header, "next_capsule_token": raw_token,
            }  # fmt: skip
            return {
                "content": [{"type": "text", "text": json.dumps(res_l0, indent=2)}],
                "isError": False,
            }
        if LEVEL_INDEX[target_level] <= LEVEL_INDEX[cur_lvl]:
            raise ValueError(f"target_level {target_level!r} must be deeper than {cur_lvl!r}")
        req_tier = (
            "pro" if (cap_env == "pro" and target_level == "L3") else LEVEL_MIN_TIER[target_level]
        )
        if AGENT_TIER_RANK[agent_tier] < AGENT_TIER_RANK[req_tier]:
            msg = (
                f"Agent tier {agent_tier!r} insufficient for {target_level!r} (needs {req_tier!r})."
            )
            self.emit_warning(
                "WARN", "CAPSULE_CAPABILITY_INSUFFICIENT", msg, {"agent_tier": agent_tier}
            )
            raise CapsuleError(msg)

        try:
            inner = json.loads(
                zlib.decompress(xor_keystream(cipher_bytes, step_key)).decode("utf-8")
            )
        except Exception as exc:
            msg = f"Failed to decompress capsule interior at {cur_lvl}: {exc}"
            self.emit_warning("WARN", "CAPSULE_CHAIN_BROKEN", msg, {"level": cur_lvl})
            raise CapsuleError(msg) from exc
        if not isinstance(inner, dict) or inner.get("ph") != header.get("ph"):
            msg = f"Capsule parent hash mismatch inside decrypted payload at {cur_lvl}."
            self.emit_warning("WARN", "CAPSULE_CHAIN_BROKEN", msg, {"level": cur_lvl})
            raise CapsuleError(msg)

        is_eph_bridge = bool(
            eph_meta
            and hdr_layer in ("ephemeral-project-bridge", str(eph_meta.get("bridge_layer_id", "")))
            and eph_meta.get("bridge_agents_md")
        )
        layer_dir = self.repo_dir if is_eph_bridge else self.resolve_layer_dir(hdr_layer)
        rel_file, heading = str(inner.get("f", "")), str(header.get("sec", ""))
        if is_eph_bridge and eph_meta is not None:
            target_file = self.repo_dir / "antigravity/.gemini/config/AGENTS.md"
            all_lines = str(eph_meta["bridge_agents_md"]).splitlines()
        else:
            target_file = self.resolve_safe_path(rel_file, layer_dir)
            all_lines = target_file.read_text(encoding="utf-8").splitlines()
        s_ln = max(1, int(inner.get("s", 1)))
        e_ln = min(len(all_lines), int(inner.get("e", len(all_lines))))
        sec_lines = all_lines[s_ln - 1 : e_ln]
        l1_skel = extract_axiom_skeleton(heading, sec_lines)
        live_h0 = compute_digest16(hdr_layer, rel_file, heading)
        live_h1, relocated = compute_digest16(live_h0, l1_skel), False
        if live_h1 != inner.get("h1"):
            _, s_ln, e_ln, sec_lines = next(
                (
                    sec
                    for sec in iter_markdown_sections(all_lines, target_file.name)
                    if sec[0] == heading
                ),
                (heading, s_ln, e_ln, sec_lines),
            )
            l1_skel = extract_axiom_skeleton(heading, sec_lines)
            live_h1 = compute_digest16(live_h0, l1_skel)
            relocated = live_h1 == inner.get("h1")
        joined_sec = "\n".join(sec_lines)
        l3_links = [] if is_eph_bridge else extract_l3_links(target_file, joined_sec, layer_dir)
        live_h2 = compute_digest16(live_h1, joined_sec[:L2_SECTION_MAX_CHARS])
        live_h3 = compute_digest16(live_h2, *(f"{i['path']}:{i['sha256']}" for i in l3_links))
        d_map = {"L0": live_h0, "L1": live_h1, "L2": live_h2, "L3": live_h3}
        hd = inner["hd"] if isinstance(inner.get("hd"), dict) else {}
        step_lvl, unfold_chain = cur_lvl, list[str]()
        while step_lvl != target_level:
            nxt = NEXT_LEVEL_MAP[step_lvl]
            if hd.get(step_lvl) != d_map[step_lvl] or hd.get(nxt) != d_map[nxt]:
                msg = f"Capsule chain digest mismatch at {step_lvl}->{nxt}: section drifted."
                self.emit_warning(
                    "WARN",
                    "CAPSULE_CHAIN_BROKEN",
                    msg,
                    {"file": rel_file, "hop": f"{step_lvl}->{nxt}"},
                )
                raise CapsuleError(msg)
            unfold_chain.append(f"{step_lvl}->{nxt}")
            step_lvl = nxt

        next_tok: str | None = None
        if target_level in ("L1", "L2"):
            nxt_after, next_ph = NEXT_LEVEL_MAP[target_level], d_map[target_level]
            m_tier = (
                "pro" if (cap_env == "pro" and nxt_after == "L3") else LEVEL_MIN_TIER[nxt_after]
            )
            next_hdr = {
                **header,
                "lvl": target_level,
                "next": nxt_after,
                "cap": m_tier,
                "ph": next_ph,
            }
            next_ck = derive_chain_key(secret, hdr_layer, target_level, next_ph, cap_env)
            next_tok = seal_single_capsule(next_hdr, {**inner, "ph": next_ph}, next_ck)

        l3_paths = [str(i["path"]) for i in l3_links]
        is_trunc = (target_level in ("L2", "L3") and len(joined_sec) > L2_SECTION_MAX_CHARS) or (
            target_level == "L3"
            and (
                len(l3_paths) > MAX_UNFOLDED_L3_LINKS
                or any(
                    int(i["bytes"]) > L3_EXCERPT_MAX_CHARS for i in l3_links[:MAX_UNFOLDED_L3_LINKS]
                )
            )
        )
        u_warns = (
            [
                self.emit_warning(
                    "WARN",
                    "RESPONSE_TRUNCATED",
                    f"Unfolded {target_level} truncated.",
                    {"section": heading},
                )
            ]
            if is_trunc
            else []
        )
        rel_f_str = str(target_file.relative_to(self.repo_dir))
        if target_level == "L1":
            body: dict[str, Any] = {
                "file": rel_f_str, "layer": hdr_layer, "section": heading,
                "start_line": s_ln, "end_line": e_ln,
                "axiom_skeleton": l1_skel, "l3_links_count": len(l3_links),
            }  # fmt: skip
        elif target_level == "L2":
            body = {
                "file": rel_f_str, "layer": hdr_layer, "section": heading,
                "start_line": s_ln, "end_line": e_ln,
                "full_section": joined_sec[:L2_SECTION_MAX_CHARS], "l3_links": l3_links,
            }  # fmt: skip
        else:
            l_docs = [
                {
                    "path": str(
                        (lf := self.resolve_safe_path(lp, layer_dir)).relative_to(self.repo_dir)
                    ),
                    "line_count": len((lt := lf.read_text(encoding="utf-8")).splitlines()),
                    "excerpt": lt[:L3_EXCERPT_MAX_CHARS],
                }
                for lp in l3_paths[:MAX_UNFOLDED_L3_LINKS]
            ]
            r_man = self.load_layer_manifest()
            l_man = (
                dict(eph_meta["bridge_manifest"])
                if (is_eph_bridge and eph_meta and "bridge_manifest" in eph_meta)
                else self.load_layer_manifest(layer_dir)
            )
            eff_e = env_arg or (cap_env if cap_env != "all" else "")
            r_eg = (
                r_man.get("environments", {}).get(eff_e, {}).get("default_guardrails", [])
                if eff_e
                else []
            )
            l_eg = (
                l_man.get("environments", {}).get(eff_e, {}).get("default_guardrails", [])
                if eff_e
                else []
            )
            guards = merge_unique_strings(
                r_man.get("baseline_guardrails", []),
                l_man.get("baseline_guardrails", []),
                r_eg,
                l_eg,
            )
            body = {
                "file": rel_f_str, "layer": hdr_layer, "section": heading,
                "full_section": joined_sec[:L2_SECTION_MAX_CHARS],
                "linked_l3_documents": l_docs, "effective_guardrails": guards,
                "federated_mcps": l_man.get("federated_mcps", []),
            }  # fmt: skip
        payload = {
            "unfolded_level": target_level, "unfold_chain": unfold_chain,
            "decrypted_hops": len(unfold_chain), "chain_verified": True,
            "line_drift_relocated": relocated, "agent_tier": agent_tier, "environment": cap_env,
            "parent_digest": header.get("ph"), "level_digest": d_map[target_level],
            "truncated": bool(u_warns), "warnings": u_warns, "promoter_codon": header,
            "content": body, "next_capsule_token": next_tok,
        }  # fmt: skip
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }
