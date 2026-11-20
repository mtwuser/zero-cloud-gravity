#!/usr/bin/env python3
"""PreToolUse hook: deterministic Zero-Cloud safety and architectural guard.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import ast
import json
import shlex
import sys
from pathlib import Path, PurePosixPath

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
_LAYER_RULE_PREFIX = "layer-"
_LAYER_RULE_SUFFIX = ".md"
_LAYER_RANK_DIGITS = 2
_PYTHON_WRITE_ATTRS = frozenset(
    {"write_text", "write_bytes", "open", "write", "move", "replace", "rename"}
)
_SUBPROCESS_EXEC_ATTRS = frozenset({"run", "call", "check_call", "check_output", "Popen"})


def _is_materialized_layer_rule(norm: str) -> bool:
    parts = PurePosixPath(norm).parts
    if len(parts) < 3 or parts[-3:-1] != (".agents", "rules"):
        return False
    fname = parts[-1]
    if not (fname.startswith(_LAYER_RULE_PREFIX) and fname.endswith(_LAYER_RULE_SUFFIX)):
        return False
    stem = fname.removeprefix(_LAYER_RULE_PREFIX).removesuffix(_LAYER_RULE_SUFFIX)
    rank, sep, slug = stem.partition("-")
    return (
        bool(sep)
        and len(rank) == _LAYER_RANK_DIGITS
        and rank.isdigit()
        and bool(slug)
        and all(c.islower() or c.isdigit() or c == "-" for c in slug)
    )


def _classify_protected_path(raw_path: str) -> str | None:
    cleaned = raw_path.replace("\\", "/").strip().strip("'\"")
    while cleaned.startswith("./"):
        cleaned = cleaned.removeprefix("./")
    norm = cleaned if cleaned.startswith("/") else f"/{cleaned}"
    if "/alembic/versions/" in norm and norm.endswith(".py"):
        return "alembic_file"
    if _is_materialized_layer_rule(norm):
        return "materialized_layer_rule"
    if norm.endswith("/__init__.py") and (
        "/tests/" in norm or ("/src/" in norm and "_framework/" not in norm)
    ):
        return "init_purity"
    return None


def _extract_quoted_literals(text: str) -> list[str]:
    literals: list[str] = []
    quote = ""
    buf: list[str] = []
    escaped = False
    for ch in text:
        if escaped:
            if quote:
                buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif not quote and ch in ("'", '"'):
            quote = ch
            buf = []
        elif ch == quote:
            if buf:
                literals.append("".join(buf))
            quote = ""
        elif quote:
            buf.append(ch)
    return literals


def _analyze_python_inline_code(code: str) -> tuple[bool, bool, list[str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True, True, _extract_quoted_literals(code)
    has_write = False
    has_exec = False
    str_literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            str_literals.append(node.value)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else (fn.attr if isinstance(fn, ast.Attribute) else "")
            )
            owner = (
                fn.value.id
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                else ""
            )
            if name in _PYTHON_WRITE_ATTRS or name.startswith("copy"):
                has_write = True
            if (owner == "os" and name == "system") or (
                owner == "subprocess" and name in _SUBPROCESS_EXEC_ATTRS
            ):
                has_exec = True
    return has_write, has_exec, str_literals


def _extract_command_substitutions(cmd: str) -> list[str]:
    subs: list[str] = []
    n = len(cmd)
    idx = 0
    open_len = len("$(")
    while idx < n:
        if cmd.startswith("$(", idx):
            depth = 1
            cur = idx + open_len
            while cur < n and depth > 0:
                if cmd.startswith("$(", cur):
                    depth += 1
                    cur += open_len
                    continue
                if cmd[cur] == "(":
                    depth += 1
                elif cmd[cur] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                cur += 1
            subs.append(cmd[idx + open_len : cur])
            idx = cur + 1
        elif cmd[idx] == "`":
            end = cmd.find("`", idx + 1)
            if end == -1:
                subs.append(cmd[idx + 1 :])
                break
            subs.append(cmd[idx + 1 : end])
            idx = end + 1
        else:
            idx += 1
    return [s.strip() for s in subs if s.strip()]


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
        if prog.startswith("python") and tok == "-c":
            _, has_exec, str_literals = _analyze_python_inline_code(tokens[idx + 1])
            if has_exec:
                return " ".join(str_literals)
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
        op = tok if tok in _OUTPUT_REDIRECT_OPS else tok.lstrip("0123456789")
        if op in _OUTPUT_REDIRECT_OPS and (hit := _classify_protected_path(raw_tokens[idx + 1])):
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
        has_write, _, str_literals = _analyze_python_inline_code(code)
        if has_write:
            for candidate in str_literals:
                if hit := _classify_protected_path(candidate):
                    return hit
    return None


def _inspect_command_string(cmd: str) -> str | None:
    for inner_cmd in _extract_command_substitutions(cmd):
        if inner_hit := _inspect_command_string(inner_cmd):
            return inner_hit
    try:
        segments = _split_shell_segments(cmd)
    except ValueError:
        dequoted = cmd.replace("'", " ").replace('"', " ").replace("`", " ")
        segments = _split_shell_segments(dequoted)
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
