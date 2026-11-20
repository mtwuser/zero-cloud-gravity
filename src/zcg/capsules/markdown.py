"""Markdown section, promoter codon, L1 exon skeleton, and L3 substrate link extractors.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from zcg.capsules.constants import (
    ALLOWED_READ_PREFIXES,
    ALLOWED_ROOT_FILES,
    CHARS_PER_TOKEN_ESTIMATE,
    CODON_MAX_SEMANTIC_TAGS,
    CODON_SLUG_MAX_CHARS,
    CODON_STOPWORDS,
    EXON_BULLET_MAX_CHARS,
    EXON_HEADING_MAX_CHARS,
    EXON_MAX_BULLETS,
)
from zcg.core.constants import CAPSULE_DIGEST_HEX_LEN
from zcg.core.markdown_scan import (
    extract_bold_terms,
    extract_citation_receipt_refs,
    extract_inline_code_paths,
    extract_markdown_links,
    is_markdown_list_item,
    slugify_heading,
    tokenize_alnum,
)


def read_non_empty_lines(path: Path) -> list[str]:
    """Read non-empty, non-comment lines from path when present."""
    if not path.is_file():
        return []
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def merge_unique_strings(*groups: list[Any]) -> list[str]:
    """Preserve first-seen order across multiple string lists while deduplicating."""
    out, seen = list[str](), set[str]()
    for grp in groups:
        for item in grp:
            val = str(item).strip()
            if val and val not in seen:
                seen.add(val)
                out.append(val)
    return out


def slugify_codon(text: str) -> str:
    """Convert heading text into a bounded lowercase kebab-case codon slug."""
    return slugify_heading(text, max_chars=CODON_SLUG_MAX_CHARS, fallback="section")


def extract_codon_tags(heading: str, body_text: str) -> list[str]:
    """Extract up to CODON_MAX_SEMANTIC_TAGS distinct semantic tags from heading and bold terms."""
    tags: list[str] = []
    for chunk in (heading, *extract_bold_terms(body_text)):
        for word in tokenize_alnum(chunk, min_len=3):
            if word not in CODON_STOPWORDS and word not in tags:
                tags.append(word)
                if len(tags) == CODON_MAX_SEMANTIC_TAGS:
                    return tags
    return tags


def extract_axiom_skeleton(heading: str, body_lines: list[str]) -> str:
    """Fold code/tables/details and retain top-level mandates and bullets for L1 exons."""
    exons: list[str] = [f"## {heading}"]
    bullets, folded, in_code = 0, 0, False
    for raw in body_lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            folded += 1
            continue
        if in_code or not stripped or stripped.startswith(("#", "|", "---")):
            if stripped and not stripped.startswith("#"):
                folded += 1
            continue
        if stripped.startswith(">") or stripped.startswith(("**Mandate", "**Description")):
            exons.append(stripped[:EXON_HEADING_MAX_CHARS])
        elif not raw.startswith(("  ", "\t")) and is_markdown_list_item(stripped):
            if bullets < EXON_MAX_BULLETS:
                exons.append(stripped[:EXON_BULLET_MAX_CHARS])
                bullets += 1
            else:
                folded += 1
        elif len(exons) == 1:
            exons.append(stripped[:EXON_HEADING_MAX_CHARS])
        else:
            folded += 1
    if folded > 0:
        exons.append(f"[+{folded} detail/table/code lines folded in rcap1:L1]")
    return "\n".join(exons)


def iter_markdown_sections(
    lines: list[str], default_heading: str
) -> list[tuple[str, int, int, list[str]]]:
    """Partition Markdown lines into (heading, start_line, end_line, section_lines) tuples."""
    sections: list[tuple[str, int, int, list[str]]] = []
    sec_lines: list[str] = []
    cur_heading, sec_start, in_code = default_heading, 1, False
    for idx, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith(("## ", "### ", "#### ")) and sec_lines:
            sections.append((cur_heading, sec_start, idx - 1, sec_lines))
            cur_heading, sec_start, sec_lines = line.lstrip("#").strip(), idx, [line]
        else:
            if not in_code and line.startswith("# ") and idx == 1:
                cur_heading = line.lstrip("#").strip()
            sec_lines.append(line)
    if sec_lines:
        sections.append((cur_heading, sec_start, len(lines), sec_lines))
    return sections


def resolve_section_hierarchy(lines: list[str], start_line: int, heading: str) -> tuple[int, str]:
    """Return (heading_depth 1..4, hierarchical 'H1 > H2 > H3 > H4' section_path)."""
    ancestors: dict[int, str] = {}
    depth, in_code = 1, False
    for line in lines[: max(0, start_line)]:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and line.startswith(("# ", "## ", "### ", "#### ")):
            lvl = len(line) - len(line.lstrip("#"))
            ancestors[lvl] = line.lstrip("#").strip()
            for deeper in range(lvl + 1, 5):
                ancestors.pop(deeper, None)
            depth = lvl
    crumb = " > ".join(ancestors[k] for k in sorted(ancestors))
    return depth, crumb or heading


def extract_l3_links(
    source_file: Path, section_text: str, layer_root: Path
) -> list[dict[str, Any]]:
    """Discover path-contained L3 substrate files referenced by Markdown links or receipts."""
    raw_refs = [
        target.partition("#")[0].strip() for _lbl, target in extract_markdown_links(section_text)
    ]
    raw_refs.extend(p.strip() for p in extract_inline_code_paths(section_text))
    for layer_id, rel_p in extract_citation_receipt_refs(section_text):
        raw_refs.extend((f"layers/{layer_id}/{rel_p}", rel_p))
    seen, links, root_resolved = set[str](), list[dict[str, Any]](), layer_root.resolve()
    for ref in raw_refs:
        if not ref or ref.startswith(("http://", "https://", "mailto:")):
            continue
        for base in (source_file.parent, root_resolved):
            cand = (base / ref).resolve()
            if cand.is_file() and cand.is_relative_to(root_resolved):
                rel_str = str(cand.relative_to(root_resolved)).replace("\\", "/")
                if rel_str not in seen and (
                    rel_str in ALLOWED_ROOT_FILES
                    or any(rel_str.startswith(p) for p in ALLOWED_READ_PREFIXES)
                ):
                    seen.add(rel_str)
                    raw_bytes = cand.read_bytes()
                    size = len(raw_bytes)
                    links.append(
                        {
                            "path": rel_str,
                            "bytes": size,
                            "estimated_tokens": max(1, size // CHARS_PER_TOKEN_ESTIMATE),
                            "sha256": hashlib.sha256(raw_bytes).hexdigest()[
                                :CAPSULE_DIGEST_HEX_LEN
                            ],
                        }
                    )
                break
    return links
