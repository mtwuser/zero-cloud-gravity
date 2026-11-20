"""Generic zero-dependency SQLite WAL repository adapter implementing RepositoryPort.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from zcg.core.domain import DomainEntity
from zcg.core.manifests import ensure_contained_path

type SQLiteMigrationStep = tuple[int, str | Callable[[sqlite3.Connection], None]]


def apply_sqlite_user_version_migrations(
    conn: sqlite3.Connection, migrations: Sequence[SQLiteMigrationStep]
) -> int:
    """Apply strictly ascending SQLite PRAGMA user_version schema migrations transactionally."""
    current_version = int(conn.execute("PRAGMA user_version;").fetchone()[0])
    prev_target = 0
    for target_version, step in migrations:
        if target_version <= prev_target:
            raise ValueError(
                f"SQLite migration versions must be strictly ascending > 0; got {target_version}"
            )
        prev_target = target_version
        if target_version <= current_version:
            continue
        if isinstance(step, str):
            conn.executescript(step)
        else:
            step(conn)
        conn.execute(f"PRAGMA user_version = {int(target_version)};")
        current_version = target_version
    return current_version


class SQLiteRepositoryAdapter[EntityT: DomainEntity, IdT](ABC):
    """L4 Hexagonal persistence adapter backed by parameterized SQLite WAL storage."""

    table_name: str = ""
    schema_migrations: ClassVar[tuple[SQLiteMigrationStep, ...]] = ()

    def __init__(self, db_path: Path, *, workspace_root: Path | None = None) -> None:
        if not (self.table_name and self.table_name.isascii() and self.table_name.isidentifier()):
            raise ValueError(f"Invalid repository table_name identifier: {self.table_name!r}")
        resolved_db = db_path.resolve()
        if workspace_root is not None:
            resolved_db = ensure_contained_path(resolved_db, workspace_root.resolve())
        self._db_path = resolved_db
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @property
    def db_path(self) -> Path:
        """Return the resolved SQLite database file path."""
        return self._db_path

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS domain_entity_records (
                    namespace TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (namespace, entity_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_domain_entity_namespace_created
                ON domain_entity_records (namespace, created_at_utc DESC)
                """
            )
            if self.schema_migrations:
                apply_sqlite_user_version_migrations(conn, self.schema_migrations)

    def get_schema_version(self) -> int:
        """Return current SQLite PRAGMA user_version integer for this database."""
        with self._connect() as conn:
            return int(conn.execute("PRAGMA user_version;").fetchone()[0])

    def extract_id(self, entity: EntityT) -> IdT:
        """Extract the typed identifier from a domain entity."""
        return cast(IdT, entity.id)

    def serialize_id(self, entity_id: IdT) -> str:
        """Serialize a typed entity identifier to its primary-key string form."""
        return str(entity_id)

    @abstractmethod
    def to_record(self, entity: EntityT) -> dict[str, Any]:
        """Serialize a domain entity into a JSON-compatible dictionary."""

    @abstractmethod
    def from_record(self, record: Mapping[str, Any]) -> EntityT:
        """Hydrate an immutable domain entity from a stored JSON dictionary."""

    def get_by_id(self, entity_id: IdT) -> EntityT | None:
        """Fetch a single domain entity by primary key, or return None if absent."""
        pk = self.serialize_id(entity_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT record_json FROM domain_entity_records
                WHERE namespace = ? AND entity_id = ?
                """,
                (self.table_name, pk),
            ).fetchone()
        if row is None:
            return None
        payload: dict[str, Any] = json.loads(str(row["record_json"]))
        return self.from_record(payload)

    def list_all(self) -> list[EntityT]:
        """Return all persisted entities in this namespace ordered newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT record_json FROM domain_entity_records
                WHERE namespace = ?
                ORDER BY created_at_utc DESC, rowid DESC
                """,
                (self.table_name,),
            ).fetchall()
        return [self.from_record(json.loads(str(r["record_json"]))) for r in rows]

    def create(self, entity: EntityT) -> EntityT:
        """Insert a new domain entity or raise ValueError on duplicate primary key."""
        pk = self.serialize_id(self.extract_id(entity))
        created_iso = entity.created_at.astimezone(UTC).isoformat()
        updated_iso = entity.updated_at.astimezone(UTC).isoformat()
        serialized = json.dumps(self.to_record(entity), sort_keys=True)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO domain_entity_records (
                        namespace, entity_id, created_at_utc, updated_at_utc, record_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.table_name, pk, created_iso, updated_iso, serialized),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Duplicate entity_id {pk!r} in {self.table_name}") from exc
        return self.from_record(json.loads(serialized))

    def update(self, entity: EntityT) -> EntityT | None:
        """Update an existing entity's payload and updated_at_utc; return None if missing."""
        pk = self.serialize_id(self.extract_id(entity))
        now_iso = datetime.now(UTC).isoformat()
        rec_dict = {**self.to_record(entity), "updated_at": now_iso}
        serialized = json.dumps(rec_dict, sort_keys=True)
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE domain_entity_records
                SET updated_at_utc = ?, record_json = ?
                WHERE namespace = ? AND entity_id = ?
                """,
                (now_iso, serialized, self.table_name, pk),
            )
            if cur.rowcount == 0:
                return None
        return self.from_record(rec_dict)

    def delete(self, entity_id: IdT) -> bool:
        """Delete an entity by primary key and return True if a row was removed."""
        pk = self.serialize_id(entity_id)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM domain_entity_records WHERE namespace = ? AND entity_id = ?",
                (self.table_name, pk),
            )
            return cur.rowcount > 0
