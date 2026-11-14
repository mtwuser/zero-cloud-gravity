"""Unified Node x Layer x Network capability gate and static skill/config security linter.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import load_node_manifest
from zcg.governance.authority import (
    record_governance_event,
    resolve_git_user_email,
    verify_layer_operation_authority,
)
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

VALID_CAPABILITY_MODES: Final[tuple[str, ...]] = ("open", "curated-allowlist")
GATED_CAPABILITY_OPERATIONS: Final[tuple[str, ...]] = (
    "install-plugin", "uninstall-plugin", "activate-plugin", "deactivate-plugin",
    "deploy-plugin", "link", "unlink", "promote-from-project",
)  # fmt: skip
PLUGIN_ALLOWLIST_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"install-plugin", "activate-plugin", "deploy-plugin"}
)
OPERATION_ALIASES: Final[dict[str, str]] = {
    "install": "install-plugin", "uninstall": "uninstall-plugin",
    "activate": "activate-plugin", "deactivate": "deactivate-plugin",
    "deploy": "deploy-plugin", "promote": "promote-from-project",
}  # fmt: skip
LOOPBACK_EGRESS_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1"})
SECURITY_CONFIG_REL_PATHS: Final[tuple[str, ...]] = (
    "antigravity/.gemini/config/hooks.json", ".agents/hooks.json",
    ".agents/mcp_config.json", "mcp_config.json",
)  # fmt: skip
_DANGEROUS_UNICODE_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
)
_FENCED_BLOCK_RE: Final[re.Pattern[str]] = re.compile(r"```[\s\S]*?```")
_PIPE_TO_SHELL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", re.IGNORECASE
)
_EGRESS_URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://([a-zA-Z0-9.-]+)(?::[0-9]{1,5})?")


def _normalize_operation(operation: str) -> str:
    clean = operation.strip().lower()
    return OPERATION_ALIASES.get(clean, clean)


def _clean_str_set(raw_items: object) -> set[str]:
    return (
        {str(x).strip() for x in raw_items if str(x).strip()}
        if isinstance(raw_items, list)
        else set()
    )


def _verdict(
    allowed: bool, op: str, code: str, msg: str, ceiling: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "operation": op,
        "reason_code": code,
        "message": msg,
        "ceiling": ceiling,
        **extra,
    }


def resolve_effective_capability_ceiling(
    workspace_dir: Path, *, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Compute Lex Superior (Parent -> Node) capability and egress ceilings."""
    ws = workspace_dir.resolve()
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    chain: list[Path] = []
    for cand in (eff_parent, ws):
        if cand is not None and (cand / NODE_MANIFEST_REL_PATH).is_file():
            resolved = cand.resolve()
            if resolved not in chain:
                chain.append(resolved)

    plugin_policy, external_link_policy = "open", "open"
    allowed_plugins: set[str] | None = None
    allowed_link_targets: set[str] | None = None
    blocked_ops: set[str] = set()
    allowed_egress: set[str] | None = None
    lineage_layers: list[str] = []

    for node_dir in chain:
        m = load_node_manifest(node_dir)
        lineage_layers.append(str(m.get("layer_id") or node_dir.name))
        raw_cap = m.get("capability_policy")
        cap: Mapping[str, Any] = raw_cap if isinstance(raw_cap, Mapping) else {}
        blocked_ops.update(
            _normalize_operation(op) for op in _clean_str_set(cap.get("blocked_operations"))
        )
        if str(cap.get("plugin_policy") or "open").strip().lower() == "curated-allowlist":
            plugin_policy = "curated-allowlist"
            p_set = _clean_str_set(cap.get("allowed_plugins"))
            allowed_plugins = p_set if allowed_plugins is None else (allowed_plugins & p_set)
        if str(cap.get("external_link_policy") or "open").strip().lower() == "curated-allowlist":
            external_link_policy = "curated-allowlist"
            l_set = _clean_str_set(cap.get("allowed_link_targets"))
            allowed_link_targets = (
                l_set if allowed_link_targets is None else (allowed_link_targets & l_set)
            )
        raw_eg = m.get("network_egress_policy")
        eg: Mapping[str, Any] = raw_eg if isinstance(raw_eg, Mapping) else {}
        if isinstance(eg.get("allowed_domains"), list):
            d_set = {d.lower() for d in _clean_str_set(eg.get("allowed_domains"))}
            allowed_egress = d_set if allowed_egress is None else (allowed_egress & d_set)

    return {
        "lineage_layers": lineage_layers,
        "plugin_policy": plugin_policy,
        "allowed_plugins": sorted(allowed_plugins or ()),
        "external_link_policy": external_link_policy,
        "allowed_link_targets": sorted(allowed_link_targets or ()),
        "blocked_operations": sorted(blocked_ops),
        "egress_restricted": allowed_egress is not None,
        "allowed_egress_domains": sorted(allowed_egress or ()),
    }


def evaluate_capability_gate(
    workspace_dir: Path, *, operation: str, actor_email: str | None = None,
    parent_dir: Path | None = None, plugin_id: str | None = None, link_target: str | None = None,
    link_relation: str | None = None, link_target_role: str | None = None,
    link_cockpit_url: str = "", check_actor_role: bool = True,
    record_blocked: bool = True, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Evaluate Actor Role ∩ Lex Superior Ceiling (+ R3 wallet airlock) for a node operation."""
    norm_op = _normalize_operation(operation)
    if norm_op not in GATED_CAPABILITY_OPERATIONS:
        raise ValueError(f"Unsupported capability-gated operation {operation!r}")
    ws = workspace_dir.resolve()
    has_manifest = (ws / NODE_MANIFEST_REL_PATH).is_file()
    eff_email = resolve_git_user_email(ws) if actor_email is None else actor_email.strip()
    ceiling = resolve_effective_capability_ceiling(ws, parent_dir=parent_dir)

    if has_manifest and norm_op == "link":
        posture = resolve_governance_posture(ws, parent_dir=parent_dir)
        is_epistemic = (
            link_relation == "knowledge-feed"
            and link_target_role == "knowledge"
            and not link_cockpit_url.strip()
        )
        if not posture["allow_external_peer_links"] and not is_epistemic:
            msg = (
                f"WALLET_EXTERNAL_LINK_BLOCKED: node {posture['node_id']!r} is R3 local-only; "
                "only read-only knowledge-feed links to knowledge corpora are permitted "
                "(route peer or settlement links via <persona>-work)"
            )
            if record_blocked:
                record_governance_event(
                    ws, operation=norm_op, status="blocked", actor_email=eff_email,
                    reason_code="WALLET_EXTERNAL_LINK_BLOCKED", message=msg,
                    remediation=msg, dry_run=dry_run,
                )  # fmt: skip
            return _verdict(False, norm_op, "WALLET_EXTERNAL_LINK_BLOCKED", msg, ceiling)

    if has_manifest and check_actor_role:
        auth_v = verify_layer_operation_authority(
            ws, operation=norm_op, actor_email=eff_email,
            parent_dir=parent_dir, record_blocked=record_blocked and not dry_run,
        )  # fmt: skip
        if not auth_v["allowed"]:
            return _verdict(
                False, norm_op, "CAPABILITY_ACTOR_ROLE_BLOCKED",
                str(auth_v["remediation"]), ceiling, authority_reason_code=auth_v["reason_code"],
            )  # fmt: skip

    block_code, block_msg = "", ""
    clean_plug, clean_tgt = (plugin_id or "").strip(), (link_target or "").strip()
    if norm_op in ceiling["blocked_operations"]:
        block_code = "CAPABILITY_CEILING_OP_BLOCKED"
        block_msg = f"{block_code}: {norm_op!r} forbidden across {ceiling['lineage_layers']}"
    elif (
        clean_plug and norm_op in PLUGIN_ALLOWLIST_OPERATIONS
        and ceiling["plugin_policy"] == "curated-allowlist"
        and clean_plug not in ceiling["allowed_plugins"]
    ):  # fmt: skip
        block_code = "CAPABILITY_CEILING_PLUGIN_BLOCKED"
        block_msg = f"{block_code}: plugin {clean_plug!r} not in {ceiling['allowed_plugins']}"
    elif (
        clean_tgt and norm_op == "link"
        and ceiling["external_link_policy"] == "curated-allowlist"
        and link_relation != "knowledge-feed"
        and clean_tgt not in ceiling["allowed_link_targets"]
    ):  # fmt: skip
        block_code = "CAPABILITY_CEILING_LINK_BLOCKED"
        block_msg = f"{block_code}: target {clean_tgt!r} not in {ceiling['allowed_link_targets']}"

    if block_code:
        if record_blocked and has_manifest:
            record_governance_event(
                ws, operation=norm_op, status="blocked", actor_email=eff_email,
                reason_code=block_code, message=block_msg, remediation=block_msg, dry_run=dry_run,
            )  # fmt: skip
        return _verdict(False, norm_op, block_code, block_msg, ceiling)
    return _verdict(True, norm_op, "CAPABILITY_GATE_PASSED", "", ceiling)


def enforce_capability_gate(
    workspace_dir: Path, *, operation: str, actor_email: str | None = None,
    parent_dir: Path | None = None, plugin_id: str | None = None, link_target: str | None = None,
    link_relation: str | None = None, link_target_role: str | None = None,
    link_cockpit_url: str = "", check_actor_role: bool = True,
    record_blocked: bool = True, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Enforce evaluate_capability_gate, raising ValueError on any blocked verdict."""
    verdict = evaluate_capability_gate(
        workspace_dir, operation=operation, actor_email=actor_email, parent_dir=parent_dir,
        plugin_id=plugin_id, link_target=link_target, link_relation=link_relation,
        link_target_role=link_target_role, link_cockpit_url=link_cockpit_url,
        check_actor_role=check_actor_role, record_blocked=record_blocked, dry_run=dry_run,
    )  # fmt: skip
    if not verdict["allowed"]:
        msg, code = str(verdict["message"]), str(verdict["reason_code"])
        raise ValueError(msg if code in msg else f"{code}: {msg}")
    return verdict


def _host_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    clean_h = host.lower()
    if clean_h in LOOPBACK_EGRESS_HOSTS or clean_h.endswith(".localhost"):
        return True
    return any(fnmatchcase(clean_h, pat.lower()) for pat in allowed_domains)


def _iter_command_tokens(node: object) -> Iterator[str]:
    if isinstance(node, Mapping):
        for key, val in node.items():
            if key in ("command", "script") and isinstance(val, str):
                yield from val.split()
            elif key == "args" and isinstance(val, list):
                yield from (item for item in val if isinstance(item, str))
            else:
                yield from _iter_command_tokens(val)
    elif isinstance(node, list):
        for elem in node:
            yield from _iter_command_tokens(elem)


def _scan_text_hazards(
    rel_file: str, raw_txt: str, *, fenced_only: bool,
    allowed_domains: tuple[str, ...], egress_restricted: bool,
) -> list[dict[str, str]]:  # fmt: skip
    out: list[dict[str, str]] = []
    if _DANGEROUS_UNICODE_RE.search(raw_txt.removeprefix("\ufeff")):
        out.append({
            "file": rel_file, "rule": "BIDI_OR_ZERO_WIDTH_UNICODE",
            "message": "Hidden zero-width or bidirectional Unicode detected",
        })  # fmt: skip
    shell_targets = _FENCED_BLOCK_RE.findall(raw_txt) if fenced_only else [raw_txt]
    if any(_PIPE_TO_SHELL_RE.search(seg) for seg in shell_targets):
        out.append({
            "file": rel_file, "rule": "PIPE_TO_SHELL_EXECUTION",
            "message": "Unverified curl/wget pipe-to-shell command detected",
        })  # fmt: skip
    if egress_restricted:
        for match in _EGRESS_URL_RE.finditer(raw_txt):
            host = match.group(1)
            if not _host_allowed(host, allowed_domains):
                out.append({
                    "file": rel_file, "rule": "UNAUTHORIZED_EGRESS_URL",
                    "message": f"Egress host {host!r} is outside network_egress_policy",
                })  # fmt: skip
    return out


def lint_single_skill_file(
    skill_path: Path, scan_root: Path, *,
    allowed_egress_domains: tuple[str, ...] = (), egress_restricted: bool = False,
) -> list[dict[str, str]]:  # fmt: skip
    """Run < 50 ms static security checks on a single SKILL.md file."""
    resolved_skill, resolved_root = skill_path.resolve(), scan_root.resolve()
    rel = (
        resolved_skill.relative_to(resolved_root).as_posix()
        if resolved_skill.is_relative_to(resolved_root)
        else resolved_skill.name
    )
    return _scan_text_hazards(
        rel, resolved_skill.read_text(encoding="utf-8"), fenced_only=True,
        allowed_domains=allowed_egress_domains, egress_restricted=egress_restricted,
    )  # fmt: skip


def lint_skills_security(
    workspace_dir: Path, *, target_dir: Path | None = None, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Scan SKILL.md, hooks.json, and mcp_config.json for injection, egress, and path escapes."""
    ws = workspace_dir.resolve()
    scan_root = target_dir.resolve() if target_dir is not None else ws
    ceiling = resolve_effective_capability_ceiling(ws, parent_dir=parent_dir)
    eg_domains = tuple(ceiling["allowed_egress_domains"])
    eg_restricted = bool(ceiling["egress_restricted"])
    tpl_skills = (
        scan_root.joinpath("templates").rglob("SKILL.md")
        if (scan_root / "templates").is_dir()
        else ()
    )
    skill_files = (
        sorted(scan_root.rglob("SKILL.md"))
        if target_dir is not None
        else sorted(
            {
                *scan_root.glob(".agents/skills/*/SKILL.md"),
                *scan_root.glob("antigravity/.gemini/config/skills/*/SKILL.md"),
                *tpl_skills,
            }
        )
    )
    violations: list[dict[str, str]] = []
    for sk_file in skill_files:
        violations.extend(
            lint_single_skill_file(
                sk_file,
                scan_root,
                allowed_egress_domains=eg_domains,
                egress_restricted=eg_restricted,
            )
        )

    cfg_files = [
        scan_root / rel for rel in SECURITY_CONFIG_REL_PATHS if (scan_root / rel).is_file()
    ]
    for cfg_file in cfg_files:
        rel_cfg = cfg_file.relative_to(scan_root).as_posix()
        raw_cfg = cfg_file.read_text(encoding="utf-8")
        violations.extend(
            _scan_text_hazards(
                rel_cfg,
                raw_cfg,
                fenced_only=False,
                allowed_domains=eg_domains,
                egress_restricted=eg_restricted,
            )
        )
        try:
            parsed = json.loads(raw_cfg)
        except json.JSONDecodeError:
            violations.append({
                "file": rel_cfg, "rule": "INVALID_SECURITY_CONFIG_JSON",
                "message": "Malformed JSON in hooks.json or mcp_config.json",
            })  # fmt: skip
            continue
        for tok in _iter_command_tokens(parsed):
            if ".." in Path(tok).parts and not (cfg_file.parent / tok).resolve().is_relative_to(
                scan_root
            ):
                violations.append({
                    "file": rel_cfg, "rule": "CONFIG_PATH_ESCAPES_WORKSPACE",
                    "message": f"Relative command path {tok!r} escapes {scan_root.name!r}",
                })  # fmt: skip

    return {
        "workspace_dir": str(ws), "scan_root": str(scan_root),
        "scanned_skill_count": len(skill_files), "scanned_config_count": len(cfg_files),
        "violation_count": len(violations), "passed": not violations, "violations": violations,
    }  # fmt: skip
