"""Hexagonal L1..L2 Functional Core semantic primitives, DomainEntity, and RepositoryPort.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from typing import Final, Protocol, runtime_checkable
from urllib.parse import urlsplit

MAX_NATURAL_TEXT_LEN: Final[int] = 500
MAX_LONG_TEXT_LEN: Final[int] = 50_000
MAX_SLUG_LEN: Final[int] = 128
MATERIALIZED_RULE_PREFIX: Final[str] = "layer-"
MATERIALIZED_RULE_SUFFIX: Final[str] = ".md"
MATERIALIZED_PRECEDENCE_LEN: Final[int] = 2
MIN_TICKET_PREFIX_LEN: Final[int] = 2
MAX_TICKET_PREFIX_LEN: Final[int] = 12
MIN_TICKET_DIGITS_LEN: Final[int] = 2
MAX_TICKET_DIGITS_LEN: Final[int] = 6
MAX_TICKET_SUFFIX_LEN: Final[int] = 20
MAX_DNS_HOST_LEN: Final[int] = 253
MAX_DNS_LABEL_LEN: Final[int] = 63
MAX_TCP_PORT: Final[int] = 65_535
VALID_GIT_REMOTE_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https", "ssh", "git", "file"})
LOOPBACK_HTTP_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})

type Identifier = str
type NaturalText = str
type LongText = str
type Slug = str
type Temporal = datetime


def generate_identifier() -> Identifier:
    """Generate a canonical lowercase UUID4 identifier string."""
    return str(uuid.uuid4())


def utc_now() -> Temporal:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def validate_identifier(value: str) -> Identifier:
    """Validate and normalize a UUID string identifier."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("Identifier must not be empty")
    return str(uuid.UUID(stripped))


def identifier_to_uuid(value: Identifier) -> uuid.UUID:
    """Convert a validated Identifier string into a stdlib uuid.UUID instance."""
    return uuid.UUID(validate_identifier(value))


def uuid_to_identifier(value: uuid.UUID) -> Identifier:
    """Convert a stdlib uuid.UUID instance into a canonical Identifier string."""
    return str(value)


def validate_natural_text(value: str) -> NaturalText:
    """Strip and validate non-empty human-readable text (1..500 chars)."""
    stripped = value.strip()
    if not (1 <= len(stripped) <= MAX_NATURAL_TEXT_LEN):
        raise ValueError(
            f"NaturalText length must be in [1, {MAX_NATURAL_TEXT_LEN}], got {len(stripped)}"
        )
    return stripped


def validate_long_text(value: str) -> LongText:
    """Strip and validate extended Markdown/body text (0..50,000 chars)."""
    stripped = value.strip()
    if len(stripped) > MAX_LONG_TEXT_LEN:
        raise ValueError(f"LongText length must be <= {MAX_LONG_TEXT_LEN}, got {len(stripped)}")
    return stripped


def is_kebab_id(value: str) -> bool:
    """Return True when value is lowercase ASCII kebab-case ('a-z0-9' segments joined by '-')."""
    return bool(value) and all(
        seg and all(("a" <= ch <= "z") or ("0" <= ch <= "9") for ch in seg)
        for seg in value.split("-")
    )


def is_safe_git_ref(value: str) -> bool:
    """Return True when value contains only ASCII alphanumeric or '._/-' git-ref characters."""
    return bool(value) and all(ch.isascii() and (ch.isalnum() or ch in "._/-") for ch in value)


def is_safe_host(value: str) -> bool:
    """Return True when value is a safe ASCII '<hostname>[:<1..65535>]' authority."""
    if not value or any(ch.isspace() for ch in value):
        return False
    host, sep, port_str = value.rpartition(":") if ":" in value else (value, "", "")
    if sep and (
        not port_str.isascii() or not port_str.isdigit() or not (1 <= int(port_str) <= MAX_TCP_PORT)
    ):
        return False
    if not (1 <= len(host) <= MAX_DNS_HOST_LEN):
        return False
    return all(
        1 <= len(lbl) <= MAX_DNS_LABEL_LEN
        and not lbl.startswith("-")
        and not lbl.endswith("-")
        and all(ch.isascii() and (ch.isalnum() or ch == "-") for ch in lbl)
        for lbl in host.split(".")
    )


def is_safe_git_remote(value: str) -> bool:
    """Return True when value is a valid http(s)/ssh/git/file URL or 'git@<host>:<path>' remote."""
    if not value or value.startswith("-") or any(ch.isspace() for ch in value):
        return False
    if value.startswith("git@") and "://" not in value:
        host_part, sep, repo_path = value.removeprefix("git@").partition(":")
        return bool(sep) and is_safe_host(host_part) and is_safe_git_ref(repo_path)
    parts = urlsplit(value)
    if parts.scheme not in VALID_GIT_REMOTE_SCHEMES or parts.query or parts.fragment:
        return False
    if parts.scheme == "file":
        return bool(parts.path)
    host_auth = parts.netloc.rpartition("@")[2] if "@" in parts.netloc else parts.netloc
    return is_safe_host(host_auth)


def parse_materialized_rule_filename(filename: str) -> tuple[str, str] | None:
    """Parse 'layer-<dd>-<layer-id>.md' into (precedence_digits, layer_id), or return None."""
    if not (
        filename.startswith(MATERIALIZED_RULE_PREFIX)
        and filename.endswith(MATERIALIZED_RULE_SUFFIX)
    ):
        return None
    stem = filename.removeprefix(MATERIALIZED_RULE_PREFIX).removesuffix(MATERIALIZED_RULE_SUFFIX)
    prec, sep, layer_id = stem.partition("-")
    if (
        not sep
        or len(prec) != MATERIALIZED_PRECEDENCE_LEN
        or not (prec.isascii() and prec.isdigit())
        or not is_kebab_id(layer_id)
    ):
        return None
    return prec, layer_id


def _is_valid_ticket_suffix(suffix: str, *, digits_only: bool) -> bool:
    if digits_only:
        parts = suffix.split("-")
        return (
            len(parts) in (1, 2)
            and MIN_TICKET_DIGITS_LEN <= len(parts[0]) <= MAX_TICKET_DIGITS_LEN
            and parts[0].isascii()
            and parts[0].isdigit()
            and (
                len(parts) == 1
                or (
                    1 <= len(parts[1]) <= MAX_TICKET_DIGITS_LEN
                    and parts[1].isascii()
                    and parts[1].isdigit()
                )
            )
        )
    return (
        1 <= len(suffix) <= MAX_TICKET_SUFFIX_LEN
        and not suffix.startswith("-")
        and not suffix.endswith("-")
        and all(c.isascii() and (c.isupper() or c.isdigit() or c == "-") for c in suffix)
    )


def extract_ticket_ids(text: str, *, digits_only_suffix: bool = False) -> list[str]:
    """Extract word-bounded '[A-Z]{2,12}-...' ticket identifiers without regular expressions."""
    normalized = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "_-")) else " " for ch in text
    )
    found: list[str] = []
    for raw_tok in normalized.split():
        cand = raw_tok.strip("-")
        prefix, sep, suffix = cand.partition("-")
        if (
            sep
            and MIN_TICKET_PREFIX_LEN <= len(prefix) <= MAX_TICKET_PREFIX_LEN
            and prefix.isascii()
            and prefix.isalpha()
            and prefix.isupper()
            and _is_valid_ticket_suffix(suffix, digits_only=digits_only_suffix)
        ):
            found.append(cand)
    return found


def validate_slug(value: str) -> Slug:
    """Strip and validate a lowercase kebab-case URI/node slug (1..128 chars)."""
    stripped = value.strip()
    if not (1 <= len(stripped) <= MAX_SLUG_LEN) or not is_kebab_id(stripped):
        raise ValueError(f"Invalid kebab-case Slug: {value!r}")
    return stripped


def normalize_cdn_origins(origins: Sequence[str]) -> tuple[str, ...]:
    """Validate and deduplicate explicit HTTPS (or loopback HTTP) CDN origins."""
    out: list[str] = []
    for raw in origins:
        clean = raw.strip().rstrip("/")
        if not clean:
            continue
        parts = urlsplit(clean)
        host = (parts.hostname or "").lower()
        is_loop = host in LOOPBACK_HTTP_HOSTS or host.endswith(".localhost")
        if (
            "*" in clean or "@" in parts.netloc or not host
            or parts.path or parts.query or parts.fragment
            or parts.scheme not in ("https", "http") or (parts.scheme == "http" and not is_loop)
        ):  # fmt: skip
            raise ValueError(f"Invalid CDN origin {raw!r}: must be explicit HTTPS or loopback")
        norm = f"{parts.scheme}://{parts.netloc.lower()}"
        if norm not in out:
            out.append(norm)
    return tuple(out)


def validate_temporal(value: datetime) -> Temporal:
    """Ensure a datetime instance carries an explicit timezone offset."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Temporal values must be timezone-aware")
    return value


def ensure_tz_aware(value: datetime | None, tz: tzinfo = UTC) -> Temporal | None:
    """Attach tz (default UTC) to naive datetimes while preserving aware or None values."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=tz)
    return value


@dataclass(frozen=True, kw_only=True)
class DomainEntity:
    """Immutable PEP 703 free-threading-safe base entity for L1..L2 Functional Cores."""

    id: Identifier = field(default_factory=generate_identifier)
    created_at: Temporal = field(default_factory=utc_now)
    updated_at: Temporal = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id))
        validate_temporal(self.created_at)
        validate_temporal(self.updated_at)


@runtime_checkable
class RepositoryPort[EntityT: DomainEntity, IdT](Protocol):
    """Generic PEP 695 Hexagonal persistence port decoupled from storage drivers."""

    def get_by_id(self, entity_id: IdT) -> EntityT | None:
        """Fetch a single domain entity by identifier, or return None if absent."""

    def list_all(self) -> list[EntityT]:
        """Return all persisted domain entities ordered newest first."""

    def create(self, entity: EntityT) -> EntityT:
        """Persist a new domain entity and return its stored representation."""

    def update(self, entity: EntityT) -> EntityT | None:
        """Update an existing domain entity, or return None if not found."""

    def delete(self, entity_id: IdT) -> bool:
        """Delete an entity by identifier and return True if a record was removed."""
