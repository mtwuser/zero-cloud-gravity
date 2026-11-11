"""Unit tests for zcg.core.sqlite_repo.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from zcg.core.domain import DomainEntity, Identifier, RepositoryPort
from zcg.core.sqlite_repo import SQLiteRepositoryAdapter


@dataclass(frozen=True, kw_only=True)
class _CandidateApplication(DomainEntity):
    role_slug: str
    stage: str


class _CandidateSQLiteRepo(SQLiteRepositoryAdapter[_CandidateApplication, Identifier]):
    table_name = "candidate_applications"

    def to_record(self, entity: _CandidateApplication) -> dict[str, Any]:
        return {
            "id": entity.id,
            "role_slug": entity.role_slug,
            "stage": entity.stage,
            "created_at": entity.created_at.isoformat(),
            "updated_at": entity.updated_at.isoformat(),
        }

    def from_record(self, record: Mapping[str, Any]) -> _CandidateApplication:
        return _CandidateApplication(
            id=str(record["id"]),
            role_slug=str(record["role_slug"]),
            stage=str(record["stage"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
        )


class _InvalidTableRepo(_CandidateSQLiteRepo):
    table_name = "invalid-table!"


class TestSqliteRepo:
    """Verify SQLiteRepositoryAdapter WAL CRUD, ordering, containment, and duplicate guards."""

    def test_sqlite_repository_adapter_crud_ordering_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify create, get_by_id, list_all DESC, update, delete, and security guards."""
        # Arrange
        ws = tmp_path / "alex-work"
        ws.mkdir()
        db_file = ws / ".agents/data/work.sqlite3"
        repo = _CandidateSQLiteRepo(db_file, workspace_root=ws)
        unscoped_repo = _CandidateSQLiteRepo(tmp_path / "standalone.sqlite3")
        t0 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
        t1 = t0 + timedelta(minutes=5)
        first = _CandidateApplication(
            role_slug="platform-engineer", stage="applied", created_at=t0, updated_at=t0
        )
        second = _CandidateApplication(
            role_slug="staff-architect", stage="screening", created_at=t1, updated_at=t1
        )
        ghost = _CandidateApplication(role_slug="ghost-role", stage="draft")

        # Act
        saved_first = repo.create(first)
        saved_second = repo.create(second)
        listed = repo.list_all()
        found_first = repo.get_by_id(first.id)
        missing_lookup = repo.get_by_id(ghost.id)
        promoted_input = _CandidateApplication(
            id=first.id,
            role_slug=first.role_slug,
            stage="onboarding-day-1",
            created_at=first.created_at,
            updated_at=first.updated_at,
        )
        updated_first = repo.update(promoted_input)
        missing_update = repo.update(ghost)
        deleted_ok = repo.delete(second.id)
        deleted_again = repo.delete(second.id)

        # Assert
        assert isinstance(repo, RepositoryPort)
        assert repo.db_path == db_file.resolve()
        assert unscoped_repo.list_all() == []
        assert saved_first.id == first.id and saved_second.id == second.id
        assert [x.id for x in listed] == [second.id, first.id]
        assert found_first == first and missing_lookup is None
        assert updated_first is not None and updated_first.stage == "onboarding-day-1"
        assert missing_update is None
        assert deleted_ok is True and deleted_again is False
        with pytest.raises(ValueError, match="Duplicate entity_id"):
            repo.create(first)
        with pytest.raises(ValueError, match="Invalid repository table_name"):
            _InvalidTableRepo(tmp_path / "bad.sqlite3")
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            _CandidateSQLiteRepo(tmp_path / "escape.sqlite3", workspace_root=ws)
