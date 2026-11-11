"""Unit test suite for src/zcg/platform/cdc.py.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import pytest

from zcg.platform.cdc import (
    CDCPipelineConfig,
    ChangeDataCapture,
    ChangeType,
    DataConnectorPort,
    DeltaDetector,
    InMemoryDataConnector,
)


class TestCDC:
    """Verify CDCPipelineConfig, InMemoryDataConnector, DeltaDetector, and ChangeDataCapture."""

    def test_config_and_connector_validation_guards_expected(self) -> None:
        """Verify bipolar input validation on CDCPipelineConfig, Connector, and DeltaDetector."""
        # Arrange
        connector = InMemoryDataConnector(source_name="atlas_feed")

        # Act
        valid_cfg = CDCPipelineConfig(source_name="atlas_feed", batch_size=2)

        # Assert
        assert isinstance(connector, DataConnectorPort)
        assert valid_cfg.batch_size == 2
        with pytest.raises(ValueError, match="source_name"):
            CDCPipelineConfig(source_name="  ")
        with pytest.raises(ValueError, match="batch_size"):
            CDCPipelineConfig(source_name="ok", batch_size=0)
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            CDCPipelineConfig(source_name="ok", poll_interval_seconds=0.0)
        with pytest.raises(ValueError, match="max_retries"):
            CDCPipelineConfig(source_name="ok", max_retries=-1)
        with pytest.raises(ValueError, match="source_name"):
            InMemoryDataConnector(source_name=" ")
        with pytest.raises(ValueError, match="key_field and source"):
            DeltaDetector(key_field="", source="ok")

    def test_delta_detector_insert_update_unchanged_delete_and_missing_key_expected(self) -> None:
        """Verify INSERT, UPDATE field diffs, unchanged no-op, DELETE toggle, and missing key."""
        # Arrange
        detector = DeltaDetector(key_field="id", source="gov_corpus")

        # Act
        ins_events = detector.detect([{"id": "art-1", "title": "V1"}, {"id": "art-2", "v": 10}])
        noop_events = detector.detect([{"id": "art-1", "title": "V1"}, {"id": "art-2", "v": 10}])
        partial_no_delete = detector.detect(
            [{"id": "art-1", "title": "V2", "extra": True}], detect_deletes=False
        )
        del_events = detector.detect([{"id": "art-1", "title": "V2", "extra": True}])

        # Assert
        assert [e.change_type for e in ins_events] == [ChangeType.INSERT, ChangeType.INSERT]
        assert noop_events == []
        assert len(partial_no_delete) == 1
        assert partial_no_delete[0].change_type == ChangeType.UPDATE
        assert partial_no_delete[0].changed_fields == ("extra", "title")
        assert partial_no_delete[0].to_dict()["change_type"] == "update"
        assert detector.known_keys == frozenset({"art-1"})
        assert len(del_events) == 1
        assert del_events[0].change_type == ChangeType.DELETE
        assert del_events[0].record_key == "art-2"
        with pytest.raises(ValueError, match="missing non-empty key_field"):
            detector.detect([{"title": "no-id"}])

    def test_cdc_pipeline_chunked_acknowledgement_and_reset_expected(self) -> None:
        """Verify ChangeDataCapture chunked acks, auto_acknowledge=False, and reset."""
        # Arrange
        connector = InMemoryDataConnector(source_name="hr_roles")
        connector.push([{"id": "r1", "role": "swe"}, {"id": "r2", "role": "sre"}, {"id": "r3"}])
        cfg = CDCPipelineConfig(source_name="hr_roles", batch_size=2)
        pipeline = ChangeDataCapture(connector=connector, config=cfg, auto_acknowledge=True)
        no_ack_pipe = ChangeDataCapture(connector=connector, auto_acknowledge=False)

        # Act
        tick1 = pipeline.tick()
        tick2_noop = pipeline.tick()
        no_ack_events = no_ack_pipe.tick()
        saved_config = pipeline.config
        saved_events = pipeline.total_events
        saved_ticks = pipeline.total_ticks
        pipeline.reset()

        # Assert
        assert len(tick1) == 3
        assert tick2_noop == []
        assert len(no_ack_events) == 3
        assert len(connector.acknowledged_ids) == 3
        assert saved_config == cfg
        assert saved_events == 3
        assert saved_ticks == 2
        assert pipeline.total_events == 0
        assert pipeline.total_ticks == 0
