"""Unit tests for zcg.core.domain.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime

import pytest

from zcg.core.domain import (
    MAX_LONG_TEXT_LEN,
    MAX_NATURAL_TEXT_LEN,
    MAX_SLUG_LEN,
    DomainEntity,
    Identifier,
    RepositoryPort,
    ensure_tz_aware,
    extract_ticket_ids,
    generate_identifier,
    identifier_to_uuid,
    is_kebab_id,
    is_safe_git_ref,
    is_safe_git_remote,
    is_safe_host,
    normalize_cdn_origins,
    parse_materialized_rule_filename,
    uuid_to_identifier,
    validate_identifier,
    validate_long_text,
    validate_natural_text,
    validate_slug,
    validate_temporal,
)


@dataclass(frozen=True, kw_only=True)
class _VentureEntity(DomainEntity):
    title: str


class _InMemoryVentureRepo:
    def __init__(self) -> None:
        self._items: dict[Identifier, _VentureEntity] = {}

    def get_by_id(self, entity_id: Identifier) -> _VentureEntity | None:
        return self._items.get(entity_id)

    def list_all(self) -> list[_VentureEntity]:
        return list(self._items.values())

    def create(self, entity: _VentureEntity) -> _VentureEntity:
        self._items[entity.id] = entity
        return entity

    def update(self, entity: _VentureEntity) -> _VentureEntity | None:
        return entity if entity.id in self._items else None

    def delete(self, entity_id: Identifier) -> bool:
        return self._items.pop(entity_id, None) is not None


class TestDomain:
    """Verify L1..L2 semantic primitives, frozen DomainEntity, and PEP 695 RepositoryPort."""

    def test_semantic_primitives_cutpoints_and_timezone_helpers_expected(self) -> None:
        """Verify UUID, NaturalText, LongText, Slug, and Temporal N vs N+1 cut-points."""
        # Arrange
        raw_uuid = uuid.uuid4()
        naive_dt = datetime(2026, 11, 10, 12, 0, 0)
        aware_dt = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Act
        gen_id = generate_identifier()
        norm_id = validate_identifier(f"  {str(raw_uuid).upper()}  ")
        roundtrip_id = uuid_to_identifier(identifier_to_uuid(norm_id))
        nat_ok = validate_natural_text("x" * MAX_NATURAL_TEXT_LEN)
        long_empty = validate_long_text("   ")
        long_max = validate_long_text("y" * MAX_LONG_TEXT_LEN)
        slug_ok = validate_slug(f"  {'a' * MAX_SLUG_LEN}  ")
        tz_none = ensure_tz_aware(None)
        tz_promoted = ensure_tz_aware(naive_dt)
        tz_preserved = ensure_tz_aware(aware_dt)

        # Assert
        assert len(validate_identifier(gen_id)) == 36
        assert norm_id == str(raw_uuid) and roundtrip_id == str(raw_uuid)
        assert len(nat_ok) == MAX_NATURAL_TEXT_LEN
        assert long_empty == "" and len(long_max) == MAX_LONG_TEXT_LEN
        assert len(slug_ok) == MAX_SLUG_LEN
        assert tz_none is None and tz_promoted == aware_dt and tz_preserved == aware_dt
        assert validate_temporal(aware_dt) == aware_dt
        with pytest.raises(ValueError, match="must not be empty"):
            validate_identifier("   ")
        with pytest.raises(ValueError, match="NaturalText"):
            validate_natural_text("x" * (MAX_NATURAL_TEXT_LEN + 1))
        with pytest.raises(ValueError, match="LongText"):
            validate_long_text("y" * (MAX_LONG_TEXT_LEN + 1))
        with pytest.raises(ValueError, match="Slug"):
            validate_slug("Invalid_Slug")
        with pytest.raises(ValueError, match="Slug"):
            validate_slug("a" * (MAX_SLUG_LEN + 1))
        with pytest.raises(ValueError, match="timezone-aware"):
            validate_temporal(naive_dt)

    def test_domain_entity_immutability_and_repository_port_conformance_expected(self) -> None:
        """Verify frozen DomainEntity validation and runtime_checkable RepositoryPort."""
        # Arrange
        repo = _InMemoryVentureRepo()
        naive_dt = datetime(2026, 11, 10, 12, 0, 0)

        # Act
        entity = _VentureEntity(title="Record #001")
        created = repo.create(entity)
        fetched = repo.get_by_id(entity.id)
        listed = repo.list_all()
        updated = repo.update(entity)
        deleted = repo.delete(entity.id)

        # Assert
        assert isinstance(repo, RepositoryPort)
        assert created == entity and fetched == entity and listed == [entity]
        assert updated == entity and deleted is True
        with pytest.raises(FrozenInstanceError):
            entity.title = "Mutated"  # type: ignore[misc]
        with pytest.raises(ValueError, match="timezone-aware"):
            _VentureEntity(title="Bad TZ", created_at=naive_dt)

    def test_normalize_cdn_origins_deduplication_loopback_and_rejection_guards_expected(
        self,
    ) -> None:
        """Verify CDN origin normalization accepts HTTPS/loopback and rejects spoofing/paths."""
        # Arrange
        cdn = "https://CDN.Iso.Example"

        # Act
        norm = normalize_cdn_origins(
            ("", f"{cdn}/", "https://cdn.iso.example", "http://127.0.0.1:8720")
        )

        # Assert
        assert norm == ("https://cdn.iso.example", "http://127.0.0.1:8720")
        for bad in (
            "http://cdn.iso.example",
            "https://*.iso.example",
            "https://user@cdn.iso.example",
            "https://cdn.iso.example/sub",
            "ftp://cdn.iso.example",
        ):
            with pytest.raises(ValueError, match="Invalid CDN origin"):
                normalize_cdn_origins((bad,))

    def test_regex_free_kebab_git_host_materialized_rule_and_ticket_validators_expected(
        self,
    ) -> None:
        """Verify trailing-newline immunity, TCP port bounds, rule filenames, and ticket IDs."""
        # Arrange
        body = "Completed [BKL-001] and **GOV-2026-A** plus (OPS-102-3); skip bad_BKL-009 and A-1"

        # Act
        mat_ok = parse_materialized_rule_filename("layer-10-corp-root.md")
        tks_all = extract_ticket_ids(body)
        tks_digits = extract_ticket_ids(body, digits_only_suffix=True)

        # Assert
        assert is_kebab_id("corp-root-01") and not is_kebab_id("")
        assert not is_kebab_id("corp-root\n") and not is_kebab_id("-bad")
        assert is_safe_git_ref("feature/ok-1.0_rc") and not is_safe_git_ref("feature/bad\n")
        assert is_safe_host("portal.iso.example:8443") and is_safe_host("localhost")
        assert not is_safe_host("") and not is_safe_host("bad host")
        assert not is_safe_host("portal.iso.example:0")
        assert not is_safe_host("portal.iso.example:70000")
        assert not is_safe_host(":8080") and not is_safe_host("-bad.example")
        assert is_safe_git_remote("https://github.com/iso-org/repo.git")
        assert is_safe_git_remote("ssh://git@github.com:2222/iso-org/repo.git")
        assert is_safe_git_remote("git@github.com:iso-org/repo.git")
        assert is_safe_git_remote("file:///tmp/repo.git")
        assert not is_safe_git_remote("") and not is_safe_git_remote("-oProxyCommand=evil")
        assert not is_safe_git_remote("ftp://github.com/repo.git")
        assert not is_safe_git_remote("https://github.com/repo.git?bad=1")
        assert not is_safe_git_remote("file://")
        assert mat_ok == ("10", "corp-root")
        assert parse_materialized_rule_filename("other.md") is None
        assert parse_materialized_rule_filename("layer-10.md") is None
        assert parse_materialized_rule_filename("layer-xx-root.md") is None
        assert parse_materialized_rule_filename("layer-10-Bad_Id.md") is None
        assert tks_all == ["BKL-001", "GOV-2026-A", "OPS-102-3"]
        assert tks_digits == ["BKL-001", "OPS-102-3"]
