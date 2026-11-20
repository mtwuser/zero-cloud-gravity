"""Unit tests for zcg.web.capabilities.crud_fields.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import pytest

from zcg.web.capabilities.crud_fields import (
    CollectionLayout,
    FieldKind,
    ResourceFieldSpec,
    validate_email_address,
    validate_http_url,
)


class TestCrudFields:
    """Verify scalar FieldKind coercion, length/numeric bounds, and WCAG 2.2 AA form rendering."""

    def test_all_eleven_field_kinds_coerce_nominal_and_optional_defaults_expected(self) -> None:
        """Verify coercion across all 11 FieldKinds plus optional/default blank handling."""
        # Arrange
        f_txt = ResourceFieldSpec("title", "Title", FieldKind.TEXT)
        f_ltxt = ResourceFieldSpec("notes", "Notes", FieldKind.LONG_TEXT, required=False)
        f_slug = ResourceFieldSpec("slug", "Slug", FieldKind.SLUG, default="general")
        f_choice = ResourceFieldSpec("stage", "Stage", FieldKind.CHOICE, choices=("draft", "live"))
        f_bool = ResourceFieldSpec("active", "Active", FieldKind.BOOL)
        f_int = ResourceFieldSpec("rank", "Rank", FieldKind.INT, required=False)
        f_flt = ResourceFieldSpec("score", "Score", FieldKind.FLOAT)
        f_mail = ResourceFieldSpec("email", "Email", FieldKind.EMAIL)
        f_url = ResourceFieldSpec("site", "Site", FieldKind.URL)
        f_uuid = ResourceFieldSpec("uid", "UID", FieldKind.UUID)
        f_date = ResourceFieldSpec("due", "Due", FieldKind.ISO_DATE)

        # Act
        res = {
            "txt": f_txt.coerce("Spec Alpha"),
            "ltxt_opt": f_ltxt.coerce(""),
            "ltxt_val": f_ltxt.coerce("Line 1\nLine 2"),
            "slug_def": f_slug.coerce(None),
            "slug_val": f_slug.coerce("iso-item"),
            "choice": f_choice.coerce("live"),
            "bool_s": f_bool.coerce("yes"),
            "bool_b": f_bool.coerce(1),
            "int_opt": f_int.coerce(""),
            "int_val": f_int.coerce("42"),
            "flt": f_flt.coerce("3.5"),
            "mail": f_mail.coerce("  Operator@Portal.Example.ORG "),
            "url_https": f_url.coerce("https://portal.example.org/docs"),
            "url_loop": f_url.coerce("http://app.localhost:8000/home"),
            "uuid": f_uuid.coerce("550E8400-E29B-41D4-A716-446655440000"),
            "date": f_date.coerce("2026-11-15"),
        }

        # Assert
        assert CollectionLayout.CARDS.value == "cards"
        assert res["txt"] == "Spec Alpha" and res["ltxt_opt"] == ""
        assert res["ltxt_val"] == "Line 1\nLine 2"
        assert res["slug_def"] == "general" and res["slug_val"] == "iso-item"
        assert res["choice"] == "live" and res["bool_s"] is True and res["bool_b"] is True
        assert res["int_opt"] is None and res["int_val"] == 42 and res["flt"] == 3.5
        assert res["mail"] == "operator@portal.example.org"
        assert res["url_https"] == "https://portal.example.org/docs"
        assert res["url_loop"] == "http://app.localhost:8000/home"
        assert res["uuid"] == "550e8400-e29b-41d4-a716-446655440000"
        assert res["date"] == "2026-11-15"

    def test_length_and_numeric_cutpoints_n_vs_n_plus_or_minus_one_expected(self) -> None:
        """Verify min_length/max_length (3..5) and min_value/max_value (0..10) cut-points."""
        # Arrange
        f_len = ResourceFieldSpec("code", "Code", FieldKind.SLUG, min_length=3, max_length=5)
        f_num = ResourceFieldSpec("qty", "Qty", FieldKind.INT, min_value=0, max_value=10)
        f_ratio = ResourceFieldSpec("ratio", "Ratio", FieldKind.FLOAT, min_value=0.0, max_value=1.0)

        # Act
        ok_min_len = f_len.coerce("abc")
        ok_max_len = f_len.coerce("abcde")
        ok_min_num = f_num.coerce(0)
        ok_max_num = f_num.coerce(10)
        ok_ratio = f_ratio.coerce(1.0)
        with pytest.raises(ValueError, match="length must be >= 3"):
            f_len.coerce("ab")
        with pytest.raises(ValueError, match="length must be <= 5"):
            f_len.coerce("abcdef")
        with pytest.raises(ValueError, match="must be >= 0"):
            f_num.coerce(-1)
        with pytest.raises(ValueError, match="must be <= 10"):
            f_num.coerce(11)

        # Assert
        assert ok_min_len == "abc" and ok_max_len == "abcde"
        assert ok_min_num == 0 and ok_max_num == 10 and ok_ratio == 1.0

    def test_bipolar_invalid_email_url_uuid_date_float_int_and_required_guards_expected(
        self,
    ) -> None:
        """Reject malformed emails, non-HTTPS public URLs, NaN, booleans for ints, and blanks."""
        # Arrange
        f_req = ResourceFieldSpec("title", "Title", FieldKind.TEXT)
        f_choice = ResourceFieldSpec("stage", "Stage", FieldKind.CHOICE, choices=("a",))
        f_int = ResourceFieldSpec("n", "N", FieldKind.INT)
        f_flt = ResourceFieldSpec("f", "F", FieldKind.FLOAT)
        f_uuid = ResourceFieldSpec("u", "U", FieldKind.UUID)
        f_date = ResourceFieldSpec("d", "D", FieldKind.ISO_DATE)

        # Act
        with pytest.raises(ValueError, match="is required") as e_req:
            f_req.coerce("   ")
        with pytest.raises(ValueError, match="must be one of"):
            f_choice.coerce("b")
        with pytest.raises(ValueError, match="must be an integer"):
            f_int.coerce(True)
        with pytest.raises(ValueError, match="must be an integer"):
            f_int.coerce("abc")
        with pytest.raises(ValueError, match="must be a finite number"):
            f_flt.coerce(False)
        with pytest.raises(ValueError, match="must be a finite number"):
            f_flt.coerce("not-float")
        with pytest.raises(ValueError, match="must be a finite number"):
            f_flt.coerce("nan")
        with pytest.raises(ValueError, match="must be a valid UUID"):
            f_uuid.coerce("not-a-uuid")
        with pytest.raises(ValueError, match="must be an ISO-8601"):
            f_date.coerce("15-11-2026")
        with pytest.raises(ValueError, match="valid email"):
            validate_email_address("mail", "missing-at.example.org")
        with pytest.raises(ValueError, match="valid email"):
            validate_email_address("mail", "user@.bad.org")
        with pytest.raises(ValueError, match="https:// or loopback") as e_url:
            validate_http_url("site", "http://evil.example.org/p")

        # Assert
        assert e_req.value is not None and e_url.value is not None

    def test_to_form_field_renders_accessible_html5_input_select_and_textarea_expected(
        self,
    ) -> None:
        """Render typed HTML5 input, select, and textarea controls with aria-invalid alerts."""
        # Arrange
        f_mail = ResourceFieldSpec("email", "Contact Email", FieldKind.EMAIL)
        f_sel = ResourceFieldSpec("stage", "Stage", FieldKind.CHOICE, choices=("draft", "live"))
        f_txt = ResourceFieldSpec("slug", "Slug", FieldKind.SLUG, required=False)

        # Act
        h_mail = f_mail.to_form_field(value="ops@example.org", error="Duplicate email").value
        h_sel = f_sel.to_form_field(value="live").value
        h_txt = f_txt.to_form_field(value="iso-01").value

        # Assert
        assert 'type="email"' in h_mail and 'aria-invalid="true"' in h_mail
        assert 'role="alert"' in h_mail and "Duplicate email" in h_mail
        assert '<select id="field-stage"' in h_sel and 'value="live" selected' in h_sel
        assert 'type="text"' in h_txt and "required" not in h_txt
