"""Zero-dependency Change Data Capture (CDC) Delta Detector and Pipeline.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import hashlib
import itertools
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

DEFAULT_CDC_BATCH_SIZE: Final[int] = 100
DEFAULT_CDC_POLL_INTERVAL_SECONDS: Final[float] = 5.0
DEFAULT_CDC_MAX_RETRIES: Final[int] = 3


class ChangeType(StrEnum):
    """Deterministic record mutation kinds emitted by DeltaDetector."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """Immutable change event emitted when a tracked record mutates."""

    source: str
    change_type: ChangeType
    record_key: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed_fields: tuple[str, ...] = ()
    state_digest: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        """Serialize change event to a JSON-compatible dictionary."""
        return {
            "event_id": self.event_id,
            "source": self.source,
            "change_type": self.change_type.value,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "record_key": self.record_key,
            "before": self.before,
            "after": self.after,
            "changed_fields": list(self.changed_fields),
            "state_digest": self.state_digest,
        }


@dataclass(frozen=True, slots=True)
class CDCPipelineConfig:
    """Bounded operational configuration for a ChangeDataCapture pipeline."""

    source_name: str
    batch_size: int = DEFAULT_CDC_BATCH_SIZE
    poll_interval_seconds: float = DEFAULT_CDC_POLL_INTERVAL_SECONDS
    max_retries: int = DEFAULT_CDC_MAX_RETRIES

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise ValueError("source_name must not be blank")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.poll_interval_seconds <= 0.0:
            raise ValueError("poll_interval_seconds must be > 0.0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


@runtime_checkable
class DataConnectorPort(Protocol):
    """Hexagonal port for polling record batches and acknowledging CDC events."""

    @property
    def source_name(self) -> str:
        """Return unique identifier of this data source."""

    def poll(self) -> Sequence[Mapping[str, Any]]:
        """Fetch the current snapshot or batch of records from the source."""

    def acknowledge(self, event_ids: Sequence[str]) -> None:
        """Acknowledge processed event identifiers."""


class InMemoryDataConnector:
    """Deterministic in-memory DataConnectorPort adapter for local pipelines and tests."""

    def __init__(self, *, source_name: str = "memory") -> None:
        if not source_name.strip():
            raise ValueError("source_name must not be blank")
        self._source_name = source_name.strip()
        self._records: list[dict[str, Any]] = []
        self._acknowledged: list[str] = []

    @property
    def source_name(self) -> str:
        """Return unique identifier of this data source."""
        return self._source_name

    def push(self, records: Sequence[Mapping[str, Any]]) -> None:
        """Load a new batch of records to be returned on subsequent polls."""
        self._records = [dict(rec) for rec in records]

    def poll(self) -> list[dict[str, Any]]:
        """Return defensive copies of currently loaded records."""
        return [dict(rec) for rec in self._records]

    def acknowledge(self, event_ids: Sequence[str]) -> None:
        """Record acknowledged event IDs."""
        self._acknowledged.extend(event_ids)

    @property
    def acknowledged_ids(self) -> tuple[str, ...]:
        """Return all acknowledged event IDs in arrival order."""
        return tuple(self._acknowledged)


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(dict(payload), sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _diff_fields(old: Mapping[str, Any], new: Mapping[str, Any]) -> tuple[str, ...]:
    all_keys = sorted(set(old) | set(new))
    return tuple(k for k in all_keys if k not in old or k not in new or old[k] != new[k])


class DeltaDetector:
    """Pure Functional Core service comparing record snapshots via SHA-256 digests."""

    def __init__(self, *, key_field: str = "id", source: str = "default") -> None:
        if not key_field.strip() or not source.strip():
            raise ValueError("key_field and source must not be blank")
        self._key_field = key_field.strip()
        self._source = source.strip()
        self._state: dict[str, dict[str, Any]] = {}
        self._digests: dict[str, str] = {}

    @property
    def known_keys(self) -> frozenset[str]:
        """Return currently tracked primary keys."""
        return frozenset(self._state)

    def reset(self) -> None:
        """Clear all tracked record state and digests."""
        self._state.clear()
        self._digests.clear()

    def detect(
        self, records: Sequence[Mapping[str, Any]], *, detect_deletes: bool = True
    ) -> list[ChangeEvent]:
        """Compare incoming records against tracked state and emit ChangeEvent items."""
        events: list[ChangeEvent] = []
        seen_keys: set[str] = set()
        for raw in records:
            rec = dict(raw)
            key = str(rec.get(self._key_field, "")).strip()
            if not key:
                raise ValueError(f"Record missing non-empty key_field {self._key_field!r}")
            seen_keys.add(key)
            digest = _canonical_digest(rec)
            if key not in self._state:
                events.append(
                    ChangeEvent(
                        source=self._source,
                        change_type=ChangeType.INSERT,
                        record_key=key,
                        before=None,
                        after=rec,
                        changed_fields=tuple(sorted(rec)),
                        state_digest=digest,
                    )
                )
                self._state[key] = rec
                self._digests[key] = digest
            elif self._digests[key] != digest:
                prev = self._state[key]
                events.append(
                    ChangeEvent(
                        source=self._source,
                        change_type=ChangeType.UPDATE,
                        record_key=key,
                        before=prev,
                        after=rec,
                        changed_fields=_diff_fields(prev, rec),
                        state_digest=digest,
                    )
                )
                self._state[key] = rec
                self._digests[key] = digest
        if detect_deletes:
            for gone_key in sorted(set(self._state) - seen_keys):
                prev = self._state.pop(gone_key)
                prev_digest = self._digests.pop(gone_key)
                events.append(
                    ChangeEvent(
                        source=self._source,
                        change_type=ChangeType.DELETE,
                        record_key=gone_key,
                        before=prev,
                        after=None,
                        changed_fields=tuple(sorted(prev)),
                        state_digest=prev_digest,
                    )
                )
        return events


class ChangeDataCapture:
    """Deterministic CDC pipeline orchestrating poll -> delta detect -> chunked ack."""

    def __init__(
        self,
        *,
        connector: DataConnectorPort,
        key_field: str = "id",
        config: CDCPipelineConfig | None = None,
        auto_acknowledge: bool = True,
    ) -> None:
        self._connector = connector
        self._config = config or CDCPipelineConfig(source_name=connector.source_name)
        self._detector = DeltaDetector(key_field=key_field, source=self._config.source_name)
        self._auto_acknowledge = auto_acknowledge
        self._total_events = 0
        self._total_ticks = 0

    @property
    def config(self) -> CDCPipelineConfig:
        """Return active pipeline configuration."""
        return self._config

    @property
    def total_events(self) -> int:
        """Return cumulative change events emitted across ticks."""
        return self._total_events

    @property
    def total_ticks(self) -> int:
        """Return total poll-detect cycles executed."""
        return self._total_ticks

    def tick(self) -> list[ChangeEvent]:
        """Execute one poll-detect-acknowledge cycle."""
        records = self._connector.poll()
        events = self._detector.detect(records)
        if self._auto_acknowledge and events:
            iterator = (ev.event_id for ev in events)
            while batch := list(itertools.islice(iterator, self._config.batch_size)):
                self._connector.acknowledge(batch)
        self._total_events += len(events)
        self._total_ticks += 1
        return events

    def reset(self) -> None:
        """Reset tracked delta state and tick/event counters."""
        self._detector.reset()
        self._total_events = 0
        self._total_ticks = 0
