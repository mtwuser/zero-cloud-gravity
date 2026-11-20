"""Regex-free CommonMark fence-aware structural Markdown scanner.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

MAX_MARKDOWN_HEADING_LEVEL: Final[int] = 6
DEFAULT_SECTION_MAX_LEVEL: Final[int] = 4
CHECKBOX_BRACKET_MIN_LEN: Final[int] = 4
CHECKBOX_BODY_OFFSET: Final[int] = 3
VALID_CHECKBOX_STATES: Final[frozenset[str]] = frozenset({" ", "/", "x", "X"})
BOLD_TERM_MIN_LEN: Final[int] = 3
BOLD_TERM_MAX_LEN: Final[int] = 48
MIN_RECEIPT_DIGEST_LEN: Final[int] = 8
MAX_RECEIPT_DIGEST_LEN: Final[int] = 64
VALID_RECEIPT_GRADES: Final[frozenset[str]] = frozenset({"E0", "E1", "E2", "E3"})


@dataclass(frozen=True, slots=True)
class CheckboxItem:
    """Parsed Markdown task-list checkbox item located outside fenced code blocks."""

    lineno: int
    indent: str
    state: str
    body: str

    @property
    def is_open(self) -> bool:
        """Return True when the checkbox is unchecked ('[ ]')."""
        return self.state == " "

    @property
    def is_in_progress(self) -> bool:
        """Return True when the checkbox is marked in-progress ('[/]')."""
        return self.state == "/"

    @property
    def is_done(self) -> bool:
        """Return True when the checkbox is completed ('[x]')."""
        return self.state == "x"

    def format_line(self, *, state: str | None = None, body: str | None = None) -> str:
        """Render the checkbox item back into a canonical Markdown task line."""
        eff_state = self.state if state is None else state
        eff_body = self.body if body is None else body
        return f"{self.indent}- [{eff_state}] {eff_body}"


@dataclass(frozen=True, slots=True)
class HeadingItem:
    """Parsed ATX Markdown heading item located outside fenced code blocks."""

    lineno: int
    level: int
    text: str


def _parse_fence_marker(stripped: str) -> tuple[str, int] | None:
    if not stripped.startswith(("```", "~~~")):
        return None
    ch = stripped[0]
    return ch, len(stripped) - len(stripped.lstrip(ch))


def iter_unfenced_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (1-based lineno, raw_line) for lines outside ``` or ~~~ code fences."""
    fence_char = ""
    fence_len = 0
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        marker = _parse_fence_marker(stripped)
        if not fence_char:
            if marker is not None:
                fence_char, fence_len = marker
                continue
            yield lineno, raw_line
        elif (
            marker is not None
            and marker[0] == fence_char
            and marker[1] >= fence_len
            and not stripped.lstrip(fence_char).strip()
        ):
            fence_char, fence_len = "", 0


def extract_fenced_blocks(text: str) -> list[str]:
    """Return raw inner contents of all ``` or ~~~ fenced code blocks in text."""
    blocks: list[str] = []
    cur_lines: list[str] = []
    fence_char = ""
    fence_len = 0
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        marker = _parse_fence_marker(stripped)
        if not fence_char:
            if marker is not None:
                fence_char, fence_len = marker
                cur_lines = []
        elif (
            marker is not None
            and marker[0] == fence_char
            and marker[1] >= fence_len
            and not stripped.lstrip(fence_char).strip()
        ):
            blocks.append("\n".join(cur_lines))
            fence_char, fence_len = "", 0
        else:
            cur_lines.append(raw_line)
    return blocks


def parse_checkbox_line(line: str, *, lineno: int = 1) -> CheckboxItem | None:
    """Parse a single '- [ ] / - [/] / - [x]' task line, or return None."""
    lstripped = line.lstrip(" \t")
    if not lstripped.startswith("-"):
        return None
    indent = line[: len(line) - len(lstripped)]
    after_dash = lstripped[1:].lstrip(" \t")
    if (
        len(after_dash) < CHECKBOX_BRACKET_MIN_LEN
        or after_dash[0] != "["
        or after_dash[1] not in VALID_CHECKBOX_STATES
        or after_dash[2] != "]"
        or after_dash[CHECKBOX_BODY_OFFSET] not in (" ", "\t")
    ):
        return None
    body = after_dash[CHECKBOX_BODY_OFFSET:].strip()
    if not body:
        return None
    return CheckboxItem(lineno=lineno, indent=indent, state=after_dash[1].lower(), body=body)


def scan_markdown_checkboxes(text: str) -> list[CheckboxItem]:
    """Return all Markdown checkbox items located outside fenced code blocks."""
    return [
        item
        for lineno, raw_line in iter_unfenced_lines(text)
        if (item := parse_checkbox_line(raw_line, lineno=lineno)) is not None
    ]


def parse_heading_line(
    line: str, *, lineno: int = 1, max_level: int = MAX_MARKDOWN_HEADING_LEVEL
) -> HeadingItem | None:
    """Parse an ATX '#..###### Heading' line up to max_level, or return None."""
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    rest = stripped[level:]
    if level > max_level or not rest.startswith((" ", "\t")):
        return None
    return HeadingItem(lineno=lineno, level=level, text=rest.strip())


def scan_markdown_headings(
    text: str, *, max_level: int = MAX_MARKDOWN_HEADING_LEVEL
) -> list[HeadingItem]:
    """Return all ATX headings up to max_level located outside fenced code blocks."""
    return [
        item
        for lineno, raw_line in iter_unfenced_lines(text)
        if (item := parse_heading_line(raw_line, lineno=lineno, max_level=max_level)) is not None
    ]


def split_markdown_sections(text: str, *, max_level: int = DEFAULT_SECTION_MAX_LEVEL) -> list[str]:
    """Split Markdown text into raw section blocks at unfenced ATX headings (1..max_level)."""
    raw_lines = text.splitlines()
    if not raw_lines:
        return []
    heading_linenos = {h.lineno for h in scan_markdown_headings(text, max_level=max_level)}
    blocks: list[str] = []
    cur_lines: list[str] = []
    for lineno, line in enumerate(raw_lines, start=1):
        if lineno in heading_linenos and cur_lines:
            blocks.append("\n".join(cur_lines))
            cur_lines = [line]
        else:
            cur_lines.append(line)
    blocks.append("\n".join(cur_lines))
    return blocks


def tokenize_alnum(text: str, *, min_len: int = 1) -> list[str]:
    """Extract lowercase ASCII alphanumeric runs of length >= min_len."""
    cleaned = "".join(
        ch if (ch.isascii() and (ch.isalpha() or ch.isdigit())) else " " for ch in text.lower()
    )
    return [tok for tok in cleaned.split() if len(tok) >= min_len]


def slugify_heading(text: str, *, max_chars: int = 0, fallback: str = "") -> str:
    """Normalize text into an ASCII lowercase kebab-case slug without regular expressions."""
    slug = "-".join(tokenize_alnum(text))
    if max_chars > 0:
        slug = slug[:max_chars]
    return slug or fallback


def is_markdown_list_item(stripped_line: str) -> bool:
    """Return True for '- ', '* ', or '1. ' Markdown list item prefixes."""
    if stripped_line.startswith(("- ", "* ")):
        return True
    head, dot, rest = stripped_line.partition(".")
    return bool(dot and head.isdigit() and rest.startswith((" ", "\t")))


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def contains_token_id(text: str, token_id: str) -> bool:
    """Return True when token_id appears in text bounded by non-word characters."""
    if not token_id:
        return False
    start = 0
    tlen = len(token_id)
    n = len(text)
    while (idx := text.find(token_id, start)) != -1:
        left_ok = idx == 0 or not _is_word_char(text[idx - 1])
        end = idx + tlen
        right_ok = end == n or not _is_word_char(text[end])
        if left_ok and right_ok:
            return True
        start = idx + 1
    return False


def extract_markdown_links(text: str) -> list[tuple[str, str]]:
    """Extract inline '[label](target)' Markdown links without regular expressions."""
    links: list[tuple[str, str]] = []
    pos = 0
    n = len(text)
    while (open_br := text.find("[", pos)) != -1:
        close_br = text.find("]", open_br + 1)
        if close_br == -1:
            break
        eff_open = text.rfind("[", open_br, close_br)
        if close_br + 2 < n and text[close_br + 1] == "(":
            close_p = text.find(")", close_br + 2)
            if close_p == -1:
                break
            label = text[eff_open + 1 : close_br]
            target = text[close_br + 2 : close_p]
            if label and target and "\n" not in label and "\n" not in target:
                links.append((label, target))
            pos = close_p + 1
        else:
            pos = close_br + 1
    return links


def extract_inline_code_paths(text: str) -> list[str]:
    """Extract inline backtick file paths matching '<path>.<alnum_ext>'."""
    parts = text.split("`")
    paths: list[str] = []
    for cand in parts[1 : len(parts) - 1 : 2]:
        stem, dot, ext = cand.rpartition(".")
        if (
            dot
            and stem
            and ext
            and all(c.isascii() and (c.isalnum() or c in "_./-") for c in stem)
            and ext.isascii()
            and ext.isalnum()
        ):
            paths.append(cand)
    return paths


def extract_bold_terms(text: str) -> list[str]:
    """Extract '**...**' bold terms of length 3..48 without interior asterisks."""
    terms: list[str] = []
    pos = 0
    while (start := text.find("**", pos)) != -1:
        end = text.find("**", start + 2)
        if end == -1:
            break
        inner = text[start + 2 : end]
        if BOLD_TERM_MIN_LEN <= len(inner) <= BOLD_TERM_MAX_LEN and "*" not in inner:
            terms.append(inner)
            pos = end + 2
        else:
            pos = start + 2
    return terms


def _is_lower_kebab_chars(value: str) -> bool:
    return bool(value) and all(
        c.isascii() and (c.islower() or c.isdigit() or c == "-") for c in value
    )


def extract_citation_receipt_refs(text: str) -> list[tuple[str, str]]:
    """Extract (layer_id, rel_path) pairs from '<layer>::<path>#<slug>@<hex>:E<0..3>' receipts."""
    cleaned = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "_./:#@-")) else " " for ch in text
    )
    refs: list[tuple[str, str]] = []
    for raw_tok in cleaned.split():
        cand = raw_tok.strip("./:#@-")
        if "::" not in cand:
            continue
        layer, _, rest1 = cand.partition("::")
        rel_path, sep_h, rest2 = rest1.partition("#")
        slug, sep_a, rest3 = rest2.partition("@")
        digest, sep_g, grade = rest3.partition(":")
        if (
            sep_h
            and sep_a
            and sep_g
            and _is_lower_kebab_chars(layer)
            and bool(rel_path)
            and all(c.isascii() and (c.isalnum() or c in "_./-") for c in rel_path)
            and _is_lower_kebab_chars(slug)
            and MIN_RECEIPT_DIGEST_LEN <= len(digest) <= MAX_RECEIPT_DIGEST_LEN
            and all(c in "0123456789abcdef" for c in digest)
            and grade in VALID_RECEIPT_GRADES
        ):
            refs.append((layer, rel_path))
    return refs


def strip_ansi_csi(text: str) -> str:
    """Strip ANSI SGR escape sequences ('\\x1b[<digits;>m') without regular expressions."""
    if "\x1b[" not in text:
        return text
    out: list[str] = []
    pos = 0
    n = len(text)
    while (esc := text.find("\x1b[", pos)) != -1:
        out.append(text[pos:esc])
        cur = esc + 2
        while cur < n and (text[cur].isdigit() or text[cur] == ";"):
            cur += 1
        if cur < n and text[cur] == "m":
            pos = cur + 1
        else:
            out.append("\x1b[")
            pos = esc + 2
    out.append(text[pos:])
    return "".join(out)
