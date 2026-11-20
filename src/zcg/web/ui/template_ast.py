"""Deterministic regex-free HTML template AST compiler, evaluator, SafeHTML, and sanitize_url.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import html
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from string.templatelib import Interpolation, Template
from typing import Final
from urllib.parse import urlsplit

MAX_TEMPLATE_INCLUDE_DEPTH: Final[int] = 4


@dataclass(frozen=True, slots=True)
class SafeHTML:
    """Trusted pre-escaped HTML fragment exempt from secondary escaping."""

    value: str

    def __str__(self) -> str:
        """Return raw HTML string."""
        return self.value


def escape_html(value: object) -> str:
    """Return SafeHTML verbatim or escape untrusted values via html.escape."""
    return value.value if isinstance(value, SafeHTML) else html.escape(str(value), quote=True)


def sanitize_url(raw_url: object, *, allow_mailto: bool = False) -> str:
    """Allow relative paths, https://, or loopback http://; replace unsafe schemes with '#'."""
    raw = str(raw_url).strip()
    if not raw:
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return "#"
    if raw.startswith(("#", "?")):
        return raw
    if raw.startswith("/"):
        return "#" if raw.startswith(("//", "/\\")) else raw
    head = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" not in head and not raw.startswith("\\"):
        return raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if allow_mailto and scheme == "mailto" and "@" in parts.path:
        return raw
    host = (parts.hostname or "").lower()
    if "@" in parts.netloc or not host:
        return "#"
    if scheme == "https":
        return raw
    is_loopback = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")
    return raw if scheme == "http" and is_loopback else "#"


def html_t(template: Template) -> SafeHTML:
    """Render a PEP 750 t-string into SafeHTML with auto-escaping and URL/iterable specs."""
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
            continue
        interp: Interpolation[object] = item
        spec = interp.format_spec
        if spec == "":
            parts.append(escape_html(interp.value))
        elif spec == "url":
            parts.append(escape_html(sanitize_url(interp.value)))
        elif spec == "mailto_url":
            parts.append(escape_html(sanitize_url(interp.value, allow_mailto=True)))
        elif spec == "join":
            val = interp.value
            if isinstance(val, Iterable) and not isinstance(val, (str, bytes, Mapping)):
                parts.append("".join(escape_html(v) for v in val))
            else:
                raise ValueError("html_t ':join' requires a non-string Iterable")
        else:
            raise ValueError(f"Unsupported html_t format_spec: {spec!r}")
    return SafeHTML("".join(parts))


@dataclass(frozen=True, slots=True)
class TemplateASTNode:
    """Immutable AST node representing text, variable, block, if/else, for, or include."""

    kind: str
    value: str = ""
    extra: str = ""
    negate: bool = False
    children: tuple[TemplateASTNode, ...] = ()
    alt_children: tuple[TemplateASTNode, ...] = ()


@dataclass(slots=True)
class _CompileFrame:
    kind: str
    arg: str
    primary: list[TemplateASTNode]
    secondary: list[TemplateASTNode]
    arg2: str = ""
    negate: bool = False
    in_else: bool = False


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    """Immutable compiled template unit with optional extends parent and named blocks."""

    extends_name: str | None
    nodes: tuple[TemplateASTNode, ...]
    blocks: Mapping[str, tuple[TemplateASTNode, ...]]


def _is_ident(tok: str) -> bool:
    return bool(tok) and not tok.startswith("_") and all(c.isalnum() or c == "_" for c in tok)


def _is_dotted_ident(tok: str) -> bool:
    return bool(tok) and all(_is_ident(seg) for seg in tok.split("."))


def _next_tag_span(source: str, pos: int) -> tuple[int, int, str, str] | None:
    v_i, s_i = source.find("{{", pos), source.find("{%", pos)
    hits = [(i, k, c) for i, k, c in ((v_i, "var", "}}"), (s_i, "stmt", "%}")) if i != -1]
    if not hits:
        return None
    start, kind, close_tok = min(hits, key=lambda item: item[0])
    end = source.find(close_tok, start + 2)
    if end == -1:
        raise ValueError(f"Unclosed template tag starting at offset {start}")
    return start, end + 2, kind, source[start + 2 : end].strip()


def _parse_var_expr(expr: str) -> TemplateASTNode:
    raw_var, sep, raw_flt = expr.partition("|")
    var_path, flt = raw_var.strip(), raw_flt.strip()
    if not _is_dotted_ident(var_path):
        raise ValueError(f"Invalid template variable identifier: {expr!r}")
    if sep and flt != "safe_url":
        raise ValueError(f"Unsupported template filter: {flt!r}")
    return TemplateASTNode("var", value=var_path, extra=flt)


def _parse_stmt_directive(expr: str) -> tuple[str, str, str]:
    if expr in ("endblock", "else", "endif", "endfor"):
        return (expr, "", "")
    parts = expr.split(None, 1)
    if len(parts) == 2:
        op, rest = parts[0], parts[1].strip()
        if op == "block" and _is_ident(rest):
            return ("block", rest, "")
        is_q = (
            len(rest) >= 3 and rest.startswith('"') and rest.endswith('"') and '"' not in rest[1:-1]
        )
        if op in ("extends", "include") and is_q:
            return (op, rest[1:-1], "")
        if op == "if":
            neg = rest.startswith("not ")
            cond = rest[4:].strip() if neg else rest
            if _is_dotted_ident(cond):
                return ("if", cond, "not" if neg else "")
        if op == "for":
            fp = rest.split()
            if len(fp) == 3 and fp[1] == "in" and _is_ident(fp[0]) and _is_dotted_ident(fp[2]):
                return ("for", fp[0], fp[2])
    raise ValueError(f"Unsupported or malformed template statement: {expr!r}")


def _target_list(stack: list[_CompileFrame], root: list[TemplateASTNode]) -> list[TemplateASTNode]:
    return (stack[-1].secondary if stack[-1].in_else else stack[-1].primary) if stack else root


@lru_cache(maxsize=256)
def compile_template_source(source: str) -> CompiledTemplate:
    """Compile template source into an immutable AST in O(tokens) with 0 regular expressions."""
    root_nodes: list[TemplateASTNode] = []
    stack: list[_CompileFrame] = []
    blocks: dict[str, tuple[TemplateASTNode, ...]] = {}
    extends_name: str | None = None
    pos = 0
    while (span := _next_tag_span(source, pos)) is not None:
        start, next_pos, kind, expr = span
        target = _target_list(stack, root_nodes)
        if start > pos:
            target.append(TemplateASTNode("text", value=source[pos:start]))
        if kind == "var":
            target.append(_parse_var_expr(expr))
        else:
            op, arg, arg2 = _parse_stmt_directive(expr)
            if op == "extends":
                has_p = any(n.kind != "text" or bool(n.value.strip()) for n in root_nodes)
                if stack or extends_name is not None or has_p:
                    raise ValueError("{% extends %} must appear once at template start")
                extends_name = arg
            elif op == "include":
                target.append(TemplateASTNode("include", value=arg))
            elif op in ("block", "if", "for"):
                stack.append(_CompileFrame(op, arg, [], [], arg2=arg2, negate=(arg2 == "not")))
            elif op == "else":
                if not stack or stack[-1].kind != "if" or stack[-1].in_else:
                    raise ValueError("Unexpected {% else %} without matching {% if %}")
                stack[-1].in_else = True
            else:
                exp_k = op.removeprefix("end")
                if not stack or stack[-1].kind != exp_k:
                    raise ValueError(f"Unexpected {{% {op} %}} without matching {{% {exp_k} %}}")
                f = stack.pop()
                par = _target_list(stack, root_nodes)
                ch, alt = tuple(f.primary), tuple(f.secondary)
                if f.kind == "block":
                    blocks[f.arg] = ch
                    par.append(TemplateASTNode("block", value=f.arg, children=ch))
                elif f.kind == "if":
                    par.append(
                        TemplateASTNode(
                            "if", value=f.arg, negate=f.negate, children=ch, alt_children=alt
                        )
                    )
                else:
                    par.append(TemplateASTNode("for", value=f.arg, extra=f.arg2, children=ch))
        pos = next_pos
    if stack:
        raise ValueError(f"Unclosed template {stack[-1].kind}: {stack[-1].arg!r}")
    if pos < len(source):
        root_nodes.append(TemplateASTNode("text", value=source[pos:]))
    return CompiledTemplate(extends_name, tuple(root_nodes), blocks)


def _resolve_value(ctx: Mapping[str, object], path: str) -> object:
    segs = path.split(".")
    if segs[0] not in ctx:
        return ""
    cur: object = ctx[segs[0]]
    for seg in segs[1:]:
        if isinstance(cur, Mapping):
            cur = cur.get(seg, "")
        elif hasattr(cur, seg):
            cur = getattr(cur, seg)
        else:
            return ""
    return "" if cur is None else cur


def evaluate_template_nodes(
    nodes: Sequence[TemplateASTNode],
    blocks: Mapping[str, tuple[TemplateASTNode, ...]],
    merged_ctx: Mapping[str, object],
    resolve_source: Callable[[str], str],
    include_depth: int = 0,
) -> str:
    """Evaluate compiled AST nodes with auto-escaping, safe_url filtering, and bounded includes."""
    parts: list[str] = []
    for n in nodes:
        if n.kind == "text":
            parts.append(n.value)
        elif n.kind == "var":
            val = _resolve_value(merged_ctx, n.value)
            parts.append(
                escape_html(sanitize_url(val)) if n.extra == "safe_url" else escape_html(val)
            )
        elif n.kind == "block":
            blk_nodes = blocks.get(n.value, n.children)
            parts.append(
                evaluate_template_nodes(
                    blk_nodes, blocks, merged_ctx, resolve_source, include_depth
                )
            )
        elif n.kind == "if":
            cond = bool(_resolve_value(merged_ctx, n.value))
            chosen = n.children if (not cond if n.negate else cond) else n.alt_children
            parts.append(
                evaluate_template_nodes(chosen, blocks, merged_ctx, resolve_source, include_depth)
            )
        elif n.kind == "for":
            raw_seq = _resolve_value(merged_ctx, n.extra)
            seq = (
                list(raw_seq)
                if isinstance(raw_seq, Iterable) and not isinstance(raw_seq, (str, bytes, Mapping))
                else []
            )
            total = len(seq)
            for idx, item in enumerate(seq):
                lmeta = {
                    "index": idx + 1,
                    "index0": idx,
                    "first": idx == 0,
                    "last": idx == total - 1,
                }
                c_ctx = {**merged_ctx, n.value: item, "loop": lmeta}
                parts.append(
                    evaluate_template_nodes(
                        n.children, blocks, c_ctx, resolve_source, include_depth
                    )
                )
        else:
            if include_depth >= MAX_TEMPLATE_INCLUDE_DEPTH:
                raise ValueError(
                    "Template include exceeded "
                    f"MAX_TEMPLATE_INCLUDE_DEPTH={MAX_TEMPLATE_INCLUDE_DEPTH}"
                )
            inc = compile_template_source(resolve_source(n.value))
            parts.append(
                evaluate_template_nodes(
                    inc.nodes, blocks, merged_ctx, resolve_source, include_depth + 1
                )
            )
    return "".join(parts)
