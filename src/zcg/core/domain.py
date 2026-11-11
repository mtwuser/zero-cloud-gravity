"""Hexagonal L1..L2 Functional Core semantic primitives, DomainEntity, and RepositoryPort.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from typing import Final, Protocol, runtime_checkable

from zcg.core.constants import KEBAB_ID_RE

MAX_NATURAL_TEXT_LEN: Final[int] = 500
MAX_LONG_TEXT_LEN: Final[int] = 50_000
MAX_SLUG_LEN: Final[int] = 128

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


def validate_slug(value: str) -> Slug:
    """Strip and validate a lowercase kebab-case URI/node slug (1..128 chars)."""
    stripped = value.strip()
    if not (1 <= len(stripped) <= MAX_SLUG_LEN) or not KEBAB_ID_RE.fullmatch(stripped):
        raise ValueError(f"Invalid kebab-case Slug: {value!r}")
    return stripped


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
