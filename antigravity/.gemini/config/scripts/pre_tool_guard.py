#!/usr/bin/env python3
"""PreToolUse hook: deterministic Zero-Cloud safety and architectural guard.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

_FILE_WRITE_TOOLS = frozenset({"write_file", "edit_file"})
_SEPARATOR_CHARS = frozenset(";&|()\n")
_OUTPUT_REDIRECT_OPS = frozenset({">", ">>", ">|", "&>", "&>>", ">&"})
_FILE_MUTATING_PROGS = frozenset({"tee", "cp", "mv", "install", "touch", "truncate"})
_INPLACE_EDIT_PROGS = frozenset({"sed", "perl"})
_COMMAND_WRAPPERS = frozenset(
    {
        "env",
        "command",
        "sudo",
        "nohup",
        "nice",
        "time",
        "timeout",
        "stdbuf",
        "ionice",
        "chrt",
        "taskset",
    }
)
_WRAPPER_FLAGS_WITH_ARG: dict[str, frozenset[str]] = {
    "sudo": frozenset({"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D"}),
    "env": frozenset({"-u", "-C", "-S"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "ionice": frozenset({"-c", "-n", "-p", "-P", "-u"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "chrt": frozenset({"-p"}),
    "taskset": frozenset({"-c", "-p"}),
}
_SHELL_BINARIES = frozenset({"sh", "bash", "zsh", "dash"})
_GIT_FLAGS_WITH_ARG = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
)
_ALEMBIC_FLAGS_WITH_ARG = frozenset({"-c", "--config", "-n", "--name", "-x"})

_ZERO_TOUCH_MIGRATION_MSG = (
    "Blocked by pre_tool_guard (Zero-Touch Migration Policy): "
    "Never create or modify files in alembic/versions/*.py manually. "
    "Ask the user to run the database migration CLI interactively."
)
_INIT_PURITY_MSG = (
    "Blocked by pre_tool_guard (__init__.py Purity): "
    "Consumer src/**/__init__.py and tests/**/__init__.py files must remain 0 bytes."
)
_MATERIALIZED_LAYER_RULE_MSG = (
    "Blocked by pre_tool_guard (Inherited Layer Rule Immutability): "
    "Never edit materialized upstream layer rules (.agents/rules/layer-<NN>-*.md) directly. "
    "Promote rule updates upward via 'zcg promote-from-project <dir> --source <file> "
    "--to-layer <layer-id> --create-pr'."
)
_MATERIALIZED_LAYER_RULE_RE = re.compile(r"(?:^|/)\.agents/rules/layer-\d{2}-[a-z0-9-]+\.md$")
_MUTATING_GIT_RE = re.compile(
    r"(?:^|[;&|(`]\s*|\$\(\s*|\n\s*)git\s+"
    r"(?:(?:-[Cc]|--git-dir|--work-tree)\s+\S+\s+|-\S+\s+)*"
    r"(?:add|commit|push|reset\s+--hard|clean\s+-[a-zA-Z]*f|subtree\s+(?:add|pull|push|merge))\b"
)
_ALEMBIC_MUTATE_RE = re.compile(
    r"(?:^|[;&|(`]\s*|\$\(\s*|\n\s*)(?:python[0-9.]*\s+-m\s+)?alembic\s+"
    r"(?:-[cnxh]\s+\S+\s+|-\S+\s+)*(?:revision|upgrade|downgrade)\b"
)
_PYTHON_WRITE_CALL_RE = re.compile(
    r"\b(?:write_text|write_bytes|open|write|copy\w*|move|replace|rename)\s*\("
)
_PYTHON_EXEC_CALL_RE = re.compile(
    r"\b(?:os\.system|subprocess\.(?:run|call|check_call|check_output|Popen))\s*\("
)
_INLINE_PATH_TOKEN_RE = re.compile(r"['\"]([^'\"]+)['\"]")
_SHELL_WRITE_FALLBACK_RE = re.compile(
    r"(?:[0-9]*>>?|[0-9]*>\|?|&>>?|\btee\s+(?:-\S+\s+)*"
    r"|\b(?:cp|mv|install)\s+(?:-\S+\s+)*\S+\s+|\bdd\s+[^;&|`\n]*?\bof=)"
    r"\s*['\"]?([^\s'\";&|()`<>]+)"
)


def _classify_protected_path(raw_path: str) -> str | None:
    cleaned = raw_path.replace("\\", "/").strip().strip("'\"")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    norm = cleaned if cleaned.startswith("/") else f"/{cleaned}"
    if "/alembic/versions/" in norm and norm.endswith(".py"):
        return "alembic_file"
    if _MATERIALIZED_LAYER_RULE_RE.search(norm):
        return "materialized_layer_rule"
    if norm.endswith("/__init__.py") and (
        "/tests/" in norm or ("/src/" in norm and "_framework/" not in norm)
    ):
        return "init_purity"
    return None


def _split_shell_segments(cmd: str) -> list[list[str]]:
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    segments, current = list[list[str]](), list[str]()
    for token in lexer:
        if set(token) <= _SEPARATOR_CHARS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _strip_leading_env_and_wrappers(tokens: list[str]) -> list[str]:
    idx, n = 0, len(tokens)
    while idx < n:
        tok = tokens[idx]
        if "=" in tok and not tok.startswith("-"):
            idx += 1
            continue
        prog = tok.rsplit("/", 1)[-1]
        if prog in _COMMAND_WRAPPERS:
            arg_flags = _WRAPPER_FLAGS_WITH_ARG.get(prog, frozenset())
            idx += 1
            while idx < n and tokens[idx].startswith("-"):
                flag = tokens[idx]
                idx += 1 + (1 if flag in arg_flags else 0)
            if prog == "timeout" and idx < n:
                idx += 1
            continue
        if prog.startswith("python") and idx + 1 < n and tokens[idx + 1] == "-m":
            idx += 2
            continue
        if prog in {"uv", "poetry"} and idx + 1 < n and tokens[idx + 1] == "run":
            idx += 2
            continue
        break
    return tokens[idx:]


def _extract_subshell_command(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    prog = tokens[0].rsplit("/", 1)[-1]
    for idx in range(1, len(tokens) - 1):
        tok = tokens[idx]
        if prog in _SHELL_BINARIES and (
            tok == "-c" or (tok.startswith("-") and not tok.startswith("--") and tok.endswith("c"))
        ):
            return tokens[idx + 1]
        if (
            prog.startswith("python")
            and tok == "-c"
            and _PYTHON_EXEC_CALL_RE.search(tokens[idx + 1])
        ):
            return " ".join(_INLINE_PATH_TOKEN_RE.findall(tokens[idx + 1]))
    return None


def _is_mutating_git_segment(tokens: list[str]) -> bool:
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
        return False
    idx, n = 1, len(tokens)
    while idx < n and tokens[idx].startswith("-"):
        flag = tokens[idx]
        idx += 1 + (1 if flag in _GIT_FLAGS_WITH_ARG else 0)
    if idx >= n:
        return False
    subcmd, rest = tokens[idx], tokens[idx + 1 :]
    if subcmd in {"add", "commit", "push"}:
        return True
    if subcmd == "reset":
        return "--hard" in rest
    if subcmd == "clean":
        return any(
            t == "--force" or (t.startswith("-") and not t.startswith("--") and "f" in t)
            for t in rest
        )
    if subcmd == "subtree":
        return any(t in {"add", "pull", "push", "merge"} for t in rest)
    return False


def _is_mutating_alembic_segment(tokens: list[str]) -> bool:
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "alembic":
        return False
    idx, n = 1, len(tokens)
    while idx < n and tokens[idx].startswith("-"):
        flag = tokens[idx]
        idx += 1 + (1 if flag in _ALEMBIC_FLAGS_WITH_ARG else 0)
    return idx < n and tokens[idx] in {"revision", "upgrade", "downgrade"}


def _detect_protected_write_in_segment(
    raw_tokens: list[str], stripped_tokens: list[str]
) -> str | None:
    for idx, tok in enumerate(raw_tokens[:-1]):
        if tok in _OUTPUT_REDIRECT_OPS and (hit := _classify_protected_path(raw_tokens[idx + 1])):
            return hit
    if not stripped_tokens:
        return None
    prog, args = stripped_tokens[0].rsplit("/", 1)[-1], stripped_tokens[1:]
    is_inplace = prog in _INPLACE_EDIT_PROGS and any(
        a == "--in-place" or (a.startswith("-") and not a.startswith("--") and "i" in a)
        for a in args
    )
    if prog in _FILE_MUTATING_PROGS or is_inplace:
        targets = [a for a in args if not a.startswith("-")]
        for arg in targets if prog == "tee" else targets[-1:]:
            if hit := _classify_protected_path(arg):
                return hit
    elif prog == "dd":
        for arg in args:
            if arg.startswith("of=") and (hit := _classify_protected_path(arg.removeprefix("of="))):
                return hit
    elif prog.startswith("python") and "-c" in args:
        code = " ".join(args[args.index("-c") + 1 :])
        if _PYTHON_WRITE_CALL_RE.search(code):
            for candidate in _INLINE_PATH_TOKEN_RE.findall(code):
                if hit := _classify_protected_path(candidate):
                    return hit
    return None


def _inspect_command_string(cmd: str) -> str | None:
    has_cmd_subst = "$(" in cmd or "`" in cmd
    try:
        segments = _split_shell_segments(cmd)
    except ValueError:
        segments, has_cmd_subst = [], True
    for raw_seg in segments:
        seg = _strip_leading_env_and_wrappers(raw_seg)
        if (sub_cmd := _extract_subshell_command(seg)) and (
            nested := _inspect_command_string(sub_cmd)
        ):
            return nested
        if _is_mutating_git_segment(seg):
            return "git"
        if _is_mutating_alembic_segment(seg):
            return "alembic"
        if write_hit := _detect_protected_write_in_segment(raw_seg, seg):
            return write_hit
    if has_cmd_subst:
        if _MUTATING_GIT_RE.search(cmd):
            return "git"
        if _ALEMBIC_MUTATE_RE.search(cmd):
            return "alembic"
        for match in _SHELL_WRITE_FALLBACK_RE.finditer(cmd):
            if hit := _classify_protected_path(match.group(1)):
                return hit
    return None


def _init_write_leaves_non_empty(target: str, args: dict[str, object]) -> bool:
    content = str(args.get("Content") or args.get("Replacement") or "")
    if content:
        return True
    p = Path(target)
    existing = p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else ""
    if not existing:
        return False
    if bool(args.get("Append")):
        return True
    if "Target" in args:
        return bool(existing.replace(str(args.get("Target") or ""), ""))
    return False


def _check_file_write(args: dict[str, object]) -> tuple[bool, str]:
    target = str(args.get("Path") or "").replace("\\", "/")
    if not target:
        return True, ""
    kind = _classify_protected_path(target)
    if kind == "alembic_file":
        return False, _ZERO_TOUCH_MIGRATION_MSG
    if kind == "materialized_layer_rule":
        return False, _MATERIALIZED_LAYER_RULE_MSG
    if kind == "init_purity" and _init_write_leaves_non_empty(target, args):
        return False, _INIT_PURITY_MSG
    return True, ""


def _check_command(args: dict[str, object]) -> tuple[bool, str]:
    cmd = str(args.get("CommandLine") or "")
    if not cmd:
        return True, ""
    hit = _inspect_command_string(cmd)
    if hit == "git":
        return False, (
            "Blocked by pre_tool_guard (Commit Discipline): "
            "Never auto-run mutating git commands (git add, git commit, git push, "
            "git reset --hard, git clean -f, git subtree). Present commit blocks at full stop."
        )
    if hit == "alembic":
        return False, (
            "Blocked by pre_tool_guard (Migration Policy): "
            "Never run 'alembic revision/upgrade/downgrade' directly."
        )
    if hit == "alembic_file":
        return False, _ZERO_TOUCH_MIGRATION_MSG
    if hit == "materialized_layer_rule":
        return False, _MATERIALIZED_LAYER_RULE_MSG
    if hit == "init_purity":
        return False, _INIT_PURITY_MSG
    return True, ""


def main() -> None:
    """Evaluate PreToolUse safety and architectural guard rules."""
    payload = json.load(sys.stdin)
    tool_call = payload.get("toolCall", {})
    tool_name = str(tool_call.get("name") or "")
    args = tool_call.get("args") or {}
    allowed, reason = True, ""
    if tool_name in _FILE_WRITE_TOOLS and isinstance(args, dict):
        allowed, reason = _check_file_write(args)
    elif tool_name == "run_command" and isinstance(args, dict):
        allowed, reason = _check_command(args)
    out = {"decision": "allow"} if allowed else {"decision": "deny", "reason": reason}
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
