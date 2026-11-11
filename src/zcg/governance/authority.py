"""Role & identity authority, audit ledger, proposal staging, and 1-hop OSS gates.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    CONSUMER_ALLOWED_OPS,
    GIT_CMD_TIMEOUT_SECONDS,
    MAINTAINER_ALLOWED_OPS,
    MATERIALIZED_RULE_RE,
    NODE_MANIFEST_REL_PATH,
    OSS_WORKSTATION_IDS,
    OWNER_RESTRICTED_OPS,
    TEMPLATE_STACK_GROUP_DIRS,
    VALIDATOR_ALLOWED_OPS,
)  # fmt: skip
from zcg.core.manifests import is_oss_root_manifest, load_node_manifest, resolve_template_dir
from zcg.topology.identity import (
    classify_inter_layer_relationship,
    resolve_hierarchical_actor_profile,
    resolve_node_entity_identity,
)  # fmt: skip

GENERIC_EMAIL_DOMAINS: tuple[str, ...] = (
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "proton.me", "example.com",
)  # fmt: skip
GENERIC_LAYER_TOKENS: tuple[str, ...] = (
    "root", "corp", "dept", "squad", "unit", "team", "layer", "node", "project", "service",
    "workstation", "governance", "security", "tech", "eng", "legal", "finance", "design",
    "marketing", "bio", "lab", "ops", "gov", "sci", "geo", "org", "public", "private",
)  # fmt: skip
MIN_PRIVATE_TOKEN_LEN: int = 4


def append_tracker_line(ws: Path, tracker: str, line: str, title_id: str) -> None:
    """Idempotently append a Markdown checklist entry to <ws>/<tracker>."""
    trk_file = ws / tracker
    def_txt = f"# Active Work Tasks — {title_id}\n\n"
    cur = trk_file.read_text(encoding="utf-8") if trk_file.is_file() else def_txt
    if line not in cur:
        trk_file.write_text(f"{cur}{'' if cur.endswith('\n') else '\n'}{line}\n", encoding="utf-8")


def resolve_git_user_email(target_dir: Path) -> str:
    """Resolve active Git user.email for <target_dir> or ZCG_GIT_USER_EMAIL override."""
    if env_email := os.environ.get("ZCG_GIT_USER_EMAIL", "").strip():
        return env_email
    with contextlib.suppress(OSError):
        res = subprocess.run(  # noqa: S603
            ["git", "-C", str(target_dir), "config", "user.email"],  # noqa: S607
            capture_output=True, text=True, timeout=GIT_CMD_TIMEOUT_SECONDS, check=False,
        )  # fmt: skip
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    return ""


def resolve_actor_layer_role(
    target_dir: Path, *, actor_email: str | None = None, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Resolve effective actor role, read-only upstream inheritance, and hierarchical authority."""
    eff_email = resolve_git_user_email(target_dir) if actor_email is None else actor_email.strip()
    return resolve_hierarchical_actor_profile(
        target_dir, actor_email=eff_email, parent_dir=parent_dir
    )


def record_governance_event(
    workspace_dir: Path, *, operation: str, status: str, actor_email: str = "",
    target_layer: str = "", source_rel_path: str = "", reason_code: str = "",
    message: str = "", remediation: str = "", dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Persist a governance/permission event to logs/governance_audit.jsonl and SESSION.md."""
    ws = workspace_dir.resolve()
    layer_id = str(load_node_manifest(ws).get("layer_id", ws.name))
    event: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(), "workspace_dir": str(ws), "layer_id": layer_id,
        "operation": operation, "status": status, "actor_email": actor_email or "unspecified",
        "target_layer": target_layer or layer_id, "source_rel_path": source_rel_path,
        "reason_code": reason_code, "message": message, "remediation": remediation,
    }  # fmt: skip
    if not dry_run:
        log_file = ws / "logs" / "governance_audit.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        if status in ("blocked", "rejected", "deferred", "staged_proposal"):
            s_file = ws / ".agents" / "SESSION.md"
            s_file.parent.mkdir(parents=True, exist_ok=True)
            cur = s_file.read_text("utf-8") if s_file.is_file() else "# Session State Log\n"
            hdr = "## Governance Alerts & Pending Decisions"
            bullet = (
                f"- **[{status.upper()} · `{operation}`]** "
                f"(`{reason_code or 'GOVERNANCE_NOTICE'}`): {message}"
            )
            base = cur.rstrip() if hdr in cur else f"{cur.rstrip()}\n\n{hdr}"
            if bullet not in base:
                s_file.write_text(f"{base}\n{bullet}\n", encoding="utf-8")
    return event


def stage_non_destructive_proposal(
    target_dir: Path, *, scope_tag: str, file_name: str, content: str, operation: str,
    actor_email: str = "", reason_code: str = "EXISTING_FILE_PROTECTED", dry_run: bool = False,
) -> Path:  # fmt: skip
    """Stage a candidate governance file in .agents/proposals/<scope_tag>/ without overwriting."""
    ws = target_dir.resolve()
    staged_rel = Path(".agents") / "proposals" / scope_tag / file_name
    staged_file = ws / staged_rel
    msg = (
        f"Target file '{file_name}' is protected or already exists in '{ws.name}'; "
        f"staged non-destructively at '{staged_rel.as_posix()}' for human review (or pass --force)."
    )
    if not dry_run:
        staged_file.parent.mkdir(parents=True, exist_ok=True)
        staged_file.write_text(f"{content.rstrip()}\n", encoding="utf-8")
        entry = (
            f"- [ ] **[P0 · Staged Governance Proposal (`{scope_tag}`)]**: "
            f"Review `{staged_rel.as_posix()}` ({reason_code})"
        )
        append_tracker_line(ws, "WORKTASK.md", entry, ws.name)
    record_governance_event(
        ws, operation=operation, status="staged_proposal", actor_email=actor_email,
        source_rel_path=staged_rel.as_posix(), reason_code=reason_code,
        message=msg, dry_run=dry_run,
    )  # fmt: skip
    return staged_file


def configure_layer_authority(
    target_dir: Path, *, owner_role: str, authorized_emails: list[str],
    escalation_contact: str | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Configure or update layer_authority in <target_dir>/system/zcg-node.json."""
    mpath, cleaned_role = target_dir / NODE_MANIFEST_REL_PATH, owner_role.strip()
    if not mpath.is_file():
        raise ValueError(f"Missing node manifest: {mpath}")
    if not cleaned_role:
        raise ValueError("owner_role must be a non-empty string")
    cleaned_emails = [e.strip() for e in authorized_emails if e.strip()]
    manifest = load_node_manifest(target_dir)
    layer_id = str(manifest.get("layer_id", target_dir.name))
    contact = (escalation_contact or "").strip() or (
        f"{cleaned_role} ({layer_id})" + (f" <{cleaned_emails[0]}>" if cleaned_emails else "")
    )
    auth_blk: dict[str, Any] = {
        "owner_role": cleaned_role, "authorized_emails": cleaned_emails,
        "escalation_contact": contact, "consumer_allowed_ops": list(CONSUMER_ALLOWED_OPS),
        "owner_restricted_ops": list(OWNER_RESTRICTED_OPS),
    }  # fmt: skip
    manifest["layer_authority"] = auth_blk
    if not dry_run:
        mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return {
        "target_dir": str(target_dir), "layer_id": layer_id,
        "dry_run": dry_run, "layer_authority": auth_blk,
    }  # fmt: skip


def _detect_inherited_upstream_asset(
    target_dir: Path, manifest: dict[str, Any], target_rel_path: str
) -> tuple[bool, str]:
    rel = target_rel_path.replace("\\", "/").strip().lstrip("/").removeprefix("./")
    own_id, parts = str(manifest.get("layer_id", target_dir.name)), Path(rel).parts
    is_ag_rule = len(parts) == 3 and parts[:2] == (".agents", "rules")
    if is_ag_rule and (m_rule := MATERIALIZED_RULE_RE.match(parts[-1])):
        return True, f"layer:{m_rule.group(2)}"
    inh_tpls = [str(t) for t in manifest.get("default_stack_templates", []) if str(t) != own_id]
    if len(parts) >= 2 and parts[0] == "templates":
        cand = parts[2] if (len(parts) >= 3 and parts[1] in TEMPLATE_STACK_GROUP_DIRS) else parts[1]
        if cand in inh_tpls:
            return True, cand
    is_ag_skill = len(parts) == 4 and parts[:2] == (".agents", "skills") and parts[-1] == "SKILL.md"
    for tpl_name in inh_tpls:
        tdir = resolve_template_dir(target_dir, tpl_name)
        if tdir and (
            (is_ag_rule and (tdir / "rules" / parts[-1]).is_file())
            or (is_ag_skill and (tdir / "skills" / parts[2] / "SKILL.md").is_file())
        ):
            return True, tpl_name
    return False, ""


def verify_layer_operation_authority(
    target_dir: Path, *, operation: str, actor_email: str | None = None,
    target_rel_path: str | None = None, parent_dir: Path | None = None, record_blocked: bool = True,
) -> dict[str, Any]:  # fmt: skip
    """Verify whether actor_email may execute <operation> on <target_dir> / <target_rel_path>."""
    manifest = load_node_manifest(target_dir)
    layer_id = str(manifest.get("layer_id", target_dir.name))
    upstream = manifest.get("upstream_layer", {})
    upstream_id = str(upstream.get("layer_id", "root")) if isinstance(upstream, dict) else "root"
    raw_auth = manifest.get("layer_authority")
    auth: dict[str, Any] = raw_auth if isinstance(raw_auth, dict) else {}
    owner_role = str(auth.get("owner_role", f"Layer Owner ({layer_id})"))
    auth_emails = [str(e).strip() for e in auth.get("authorized_emails", []) if str(e).strip()]
    maint_emails = [str(e).strip() for e in auth.get("maintainer_emails", []) if str(e).strip()]
    val_emails = [str(e).strip() for e in auth.get("validator_emails", []) if str(e).strip()]
    ext_ops = (*MAINTAINER_ALLOWED_OPS, *VALIDATOR_ALLOWED_OPS)
    v_extra = val_emails if operation in VALIDATOR_ALLOWED_OPS else ()
    allowed_pool = list(
        dict.fromkeys(
            [*auth_emails, *maint_emails, *v_extra] if operation in ext_ops else auth_emails
        )
    )
    esc = str(auth.get("escalation_contact", f"{owner_role} ({layer_id})"))
    eff_email = resolve_git_user_email(target_dir) if actor_email is None else actor_email.strip()
    role_profile = resolve_hierarchical_actor_profile(
        target_dir, actor_email=eff_email, parent_dir=parent_dir
    )
    base_v = {
        "operation": operation, "layer_id": layer_id, "actor_email": eff_email,
        "owner_role": owner_role, "actor_role_profile": role_profile,
    }  # fmt: skip
    if target_rel_path:
        is_inh, origin_ref = _detect_inherited_upstream_asset(target_dir, manifest, target_rel_path)
        if is_inh:
            rem = (
                f"Blocked: '{target_rel_path}' is an inherited upstream asset (origin: "
                f"'{origin_ref}', upstream: '{upstream_id}'). Adapt in 'templates/{layer_id}/' or "
                f"run 'zcg promote-from-project {target_dir} --source {target_rel_path} "
                f"--to-layer {upstream_id} --create-pr' and coordinate with {esc}."
            )
            rc = "INHERITED_UPSTREAM_ASSET_IMMUTABLE"
            record_governance_event(
                target_dir, operation=operation, status="blocked", message=rem,
                actor_email=eff_email, source_rel_path=target_rel_path,
                remediation=rem, reason_code=rc,
            )  # fmt: skip
            return {
                **base_v, "allowed": False, "reason_code": rc, "remediation": rem,
                "target_rel_path": target_rel_path, "origin_source": origin_ref,
            }  # fmt: skip
    if operation in CONSUMER_ALLOWED_OPS:
        return {
            **base_v, "allowed": True,
            "reason_code": "CONSUMER_OPERATION_ALLOWED", "remediation": None,
        }  # fmt: skip
    hier_ok = bool(
        parent_dir is not None
        and role_profile["hierarchical_authority_granted"]
        and (
            role_profile["upstream_role"] == "owner"
            or (role_profile["upstream_role"] == "maintainer" and operation in ext_ops)
        )
    )
    in_pool = bool(
        eff_email and any(fnmatchcase(eff_email.lower(), pat.lower()) for pat in allowed_pool)
    )
    if hier_ok and not in_pool:
        return {
            **base_v, "allowed": True,
            "reason_code": "UPSTREAM_HIERARCHICAL_AUTHORITY", "remediation": None,
        }  # fmt: skip
    if allowed_pool and not in_pool:
        rem = (
            f"Blocked: Git user.email '{eff_email or '<unset>'}' is not authorized to run "
            f"'{operation}' on '{layer_id}' (owner: {owner_role}; authorized: "
            f"{', '.join(allowed_pool)}). Propose via 'zcg promote-from-project' to {esc}."
        )
        if record_blocked:
            record_governance_event(
                target_dir, operation=operation, status="blocked", actor_email=eff_email,
                reason_code="UNAUTHORIZED_ACTOR_EMAIL", message=rem, remediation=rem,
            )  # fmt: skip
        return {
            **base_v, "allowed": False, "reason_code": "UNAUTHORIZED_ACTOR_EMAIL",
            "authorized_emails": allowed_pool, "escalation_contact": esc, "remediation": rem,
        }  # fmt: skip
    return {**base_v, "allowed": True, "reason_code": "OWNER_AUTHORIZED", "remediation": None}


def verify_oss_promotion_agnosticism(project_dir: Path, content: str, source_rel: str) -> None:
    """Block promotion to an Open-Source root if content leaks private corporate identifiers."""
    proj_m = load_node_manifest(project_dir)
    private_tokens: set[str] = set()
    raw_ids: list[str] = [str(proj_m.get("layer_id", ""))]
    for m_entry in proj_m.get("mounted_layers") or []:
        if isinstance(m_entry, dict):
            raw_ids.extend((str(m_entry.get("name", "")), str(m_entry.get("layer_id", ""))))
    raw_auth = proj_m.get("layer_authority")
    auth_ems = raw_auth.get("authorized_emails") or [] if isinstance(raw_auth, dict) else []
    for pat in auth_ems:
        if isinstance(pat, str) and "@" in pat:
            dom = pat.split("@", 1)[1].lstrip("*.").lower()
            if dom and dom not in GENERIC_EMAIL_DOMAINS:
                private_tokens.add(dom)
                raw_ids.append(dom)
    tok_pat = rf"[a-z0-9]{{{MIN_PRIVATE_TOKEN_LEN},}}"
    for rid in raw_ids:
        private_tokens.update(
            t for t in re.findall(tok_pat, rid.lower()) if t not in GENERIC_LAYER_TOKENS
        )
    leaked = sorted(
        tok for tok in private_tokens if re.search(rf"\b{re.escape(tok)}\b", content, re.IGNORECASE)
    )
    if leaked:
        raise ValueError(
            f"OSS_AGNOSTICISM_VIOLATION: Refusing to promote '{source_rel}' to Open-Source "
            f"root because it contains private layer identifiers ({', '.join(leaked)})."
        )


def verify_single_hop_upstream(
    project_dir: Path, upstream_dir: Path, *, actor_email: str | None = None
) -> None:
    """Enforce 1-hop upstream, Root 0 OSS gateway, and horizontal Peer Root 0 promotion gates."""
    proj_m, up_m = load_node_manifest(project_dir), load_node_manifest(upstream_dir)
    up_cfg = proj_m.get("upstream_layer")
    expected_up_id = str(up_cfg.get("layer_id", "")).strip() if isinstance(up_cfg, dict) else ""
    actual_up_id = str(up_m.get("layer_id", "")).strip()
    src_meta = resolve_node_entity_identity(project_dir, proj_m)
    up_meta = resolve_node_entity_identity(upstream_dir, up_m)
    rel = classify_inter_layer_relationship(src_meta, up_meta)
    src_scope, up_scope = str(src_meta["visibility_scope"]), str(up_meta["visibility_scope"])
    is_src_root0 = bool(proj_m.get("layer_id")) and src_scope.endswith((":root-0", ":dev"))
    is_up_root0 = bool(up_m.get("layer_id")) and up_scope.endswith((":root-0", ":dev"))
    both_oss = (
        str(proj_m.get("layer_role", "")) == "corporate"
        or is_src_root0
        or bool(src_meta.get("is_knowledge_node") and src_meta.get("can_expose_to_oss"))
        or expected_up_id in OSS_WORKSTATION_IDS
    ) and is_oss_root_manifest(up_m)
    inter_root_peer = (
        not is_oss_root_manifest(up_m)
        and is_src_root0
        and is_up_root0
        and rel["mcp_communication_mode"] == "external-peer-root0-pr-and-readonly-mcp"
    )
    if (
        expected_up_id and actual_up_id and expected_up_id != actual_up_id
        and not both_oss and not inter_root_peer
    ):  # fmt: skip
        src_id = str(proj_m.get("layer_id", project_dir.name))
        raise ValueError(
            f"CROSS_TIER_PROMOTION_BYPASS: Layer '{src_id}' can only promote to "
            f"immediate upstream_layer '{expected_up_id}' (1-hop), not '{actual_up_id}'."
        )
    if is_oss_root_manifest(up_m) or inter_root_peer:
        verdict = verify_layer_operation_authority(
            project_dir, operation="release", actor_email=actor_email
        )
        if not verdict["allowed"]:
            code = (
                "UNAUTHORIZED_OSS_PROMOTION"
                if is_oss_root_manifest(up_m)
                else "UNAUTHORIZED_INTER_ROOT_PROMOTION"
            )
            raise ValueError(f"{code}: Root 0 owner required ({verdict['remediation']}).")
