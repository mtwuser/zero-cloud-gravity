"""Unit tests for zcg.web.components.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import pytest

from zcg.web.components import (
    render_alert,
    render_card,
    render_card_grid,
    render_file_dropzone,
    render_form_field,
    render_island,
    render_item_list,
    render_kpi_stat,
    render_modal,
    render_pagination,
    render_progress_bar,
    render_search_bar,
    render_table,
    render_tabs,
)


class TestComponents:
    """Verify WCAG 2.2 AA HTML5 UI & Collection Macros across nominal, empty, and guard states."""

    def test_card_and_card_grid_render_nominal_records_and_empty_fallback_expected(self) -> None:
        """Verify render_card and render_card_grid populate badges/subtitles and empty fallbacks."""
        # Arrange
        rows = [{"title": "Spec <1>", "body": "Summary", "sub": "E3", "badge": "ACTIVE"}]

        # Act
        single = render_card(
            title="Node", body="Body", subtitle="Sub", badge="OK", footer="Foot", card_id="c-1"
        )
        grid_full = render_card_grid(
            items=rows, subtitle_key="sub", badge_key="badge", grid_id="g-1"
        )
        grid_plain = render_card_grid(items=[{"title": "Only", "body": "Text"}])
        grid_empty = render_card_grid(items=(), empty_message="Nothing here.", grid_id="g-empty")

        # Assert
        assert 'id="c-1"' in single.value and "zcg-card__footer" in single.value
        assert 'id="g-1"' in grid_full.value and "Spec &lt;1&gt;" in grid_full.value
        assert "ACTIVE" in grid_full.value and "E3" in grid_full.value
        assert "zcg-card__subtitle" not in grid_plain.value
        assert 'id="g-empty"' in grid_empty.value and "Nothing here." in grid_empty.value

    def test_item_list_and_table_render_collections_and_empty_states_expected(self) -> None:
        """Verify render_item_list and render_table escape cells and emit empty placeholders."""
        # Arrange
        items = [{"title": "Entry A", "meta": "v1", "status": "READY"}, {"title": "Entry B"}]
        cols = (("id", "ID"), ("title", "Title"))

        # Act
        lst_full = render_item_list(items=items, meta_key="meta", badge_key="status", list_id="l-1")
        lst_empty = render_item_list(items=(), empty_message="Empty list", list_id="l-0")
        tbl_full = render_table(columns=cols, rows=[{"id": "1", "title": "A & B"}], table_id="t-1")
        tbl_empty = render_table(columns=cols, rows=(), empty_message="Empty table")

        # Assert
        assert 'id="l-1"' in lst_full.value and "zcg-list__meta" in lst_full.value
        assert "READY" in lst_full.value and "Entry B" in lst_full.value
        assert 'id="l-0"' in lst_empty.value and "Empty list" in lst_empty.value
        assert 'id="t-1"' in tbl_full.value and "<td>A &amp; B</td>" in tbl_full.value
        assert 'colspan="2"' in tbl_empty.value and "Empty table" in tbl_empty.value

    def test_pagination_and_search_bar_handle_boundary_pages_and_query_separators_expected(
        self,
    ) -> None:
        """Verify render_pagination N vs N±1 page boundaries and '?' vs '&' query separators."""
        # Arrange
        url_plain = "/api/items"
        url_filtered = "/api/items?view=list"

        # Act
        first_page = render_pagination(
            page=1, total_pages=3, base_url=url_plain, target_selector="#out"
        )
        mid_page = render_pagination(
            page=2, total_pages=3, base_url=url_filtered, target_selector="#out"
        )
        last_page = render_pagination(
            page=3, total_pages=3, base_url=url_plain, target_selector="#out"
        )
        search = render_search_bar(action_url=url_plain, target_selector="#out", query="iso")

        # Assert
        assert "Previous" not in first_page.value and "?page=2" in first_page.value
        assert "&amp;page=1" in mid_page.value and "&amp;page=3" in mid_page.value
        assert "Previous" in last_page.value and "Next" not in last_page.value
        assert 'value="iso"' in search.value and 'type="search"' in search.value

    def test_forms_modals_tabs_alerts_and_dropzones_render_accessible_attributes_expected(
        self,
    ) -> None:
        """Verify form input/textarea/select variants, modal, tabs, alert, and dropzone markup."""
        # Arrange
        tabs_spec = (("cards", "Cards", "/items?view=cards"), ("list", "List", "/items?view=list"))

        # Act
        f_text = render_form_field(name="title", label="Title", required=True, error="Required")
        f_area = render_form_field(name="notes", label="Notes", field_type="textarea", value="Hi")
        f_sel = render_form_field(
            name="tier",
            label="Tier",
            field_type="select",
            value="M2",
            options=(("M1", "M1"), ("M2", "M2")),
        )
        modal = render_modal(modal_id="m-edit", title="Edit Record", body="Form")
        tabs = render_tabs(tabs=tabs_spec, active_tab="cards", target_selector="#out")
        alert = render_alert(message="Denied", severity="ERROR", code="E_AUTH", hint="Retry")
        alert_min = render_alert(message="Info")
        drop = render_file_dropzone(action_url="/upload", target_selector="#out", accept=".md")
        drop_min = render_file_dropzone(action_url="/upload", target_selector="#out")

        # Assert
        assert 'aria-invalid="true"' in f_text.value and 'role="alert"' in f_text.value
        assert "<textarea" in f_area.value and ">Hi</textarea>" in f_area.value
        assert '<option value="M2" selected>' in f_sel.value
        assert '<dialog id="m-edit"' in modal.value
        assert 'aria-selected="true"' in tabs.value and 'aria-selected="false"' in tabs.value
        assert 'data-error-code="E_AUTH"' in alert.value and "Retry" in alert.value
        assert "data-error-code" not in alert_min.value
        assert 'accept=".md"' in drop.value and "accept=" not in drop_min.value

    def test_progress_bar_kpi_stat_and_island_hydration_cutpoints_and_guards_expected(self) -> None:
        """Verify progress polling cutoff at 1.0, KPI stat delta, and island strategy validation."""
        # Arrange
        island_props = {"count": 3}

        # Act
        prog_active = render_progress_bar(
            progress_ratio=0.45, label="Syncing", poll_url="/jobs/1", poll_interval_ms=500
        )
        prog_done = render_progress_bar(progress_ratio=1.2, poll_url="/jobs/1")
        kpi_delta = render_kpi_stat(label="Score", value="98.5", delta="+2.1", tone="positive")
        kpi_plain = render_kpi_stat(label="Nodes", value="4")
        island_mod = render_island(
            name="chart", props=island_props, strategy="eager", module_src="/static/js/c.js"
        )
        island_min = render_island(name="clock")
        with pytest.raises(ValueError, match="Invalid hydration strategy") as exc_strat:
            render_island(name="bad", strategy="unknown")

        # Assert
        assert 'data-zcg-poll="/jobs/1"' in prog_active.value and "(45%)" in prog_active.value
        assert "data-zcg-poll" not in prog_done.value and 'value="100"' in prog_done.value
        assert "+2.1" in kpi_delta.value and "zcg-kpi__delta" not in kpi_plain.value
        assert 'data-hydrate="eager"' in island_mod.value and "data-module=" in island_mod.value
        assert (
            'data-hydrate="visible"' in island_min.value and "data-module" not in island_min.value
        )
        assert "unknown" in str(exc_strat.value)
