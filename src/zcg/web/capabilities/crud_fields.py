"""Declarative CRUD field scalar domains, stdlib validators, and WCAG 2.2 AA form controls.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from zcg.core import domain
from zcg.web.http.channels import BaseStrEnum
from zcg.web.ui import components
from zcg.web.ui.templates import SafeHTML


class FieldKind(BaseStrEnum):
    """Typed scalar domains supported by declarative CRUD resource fields."""

    TEXT = "text"
    LONG_TEXT = "long_text"
    SLUG = "slug"
    CHOICE = "choice"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    EMAIL = "email"
    URL = "url"
    UUID = "uuid"
    ISO_DATE = "iso_date"


class CollectionLayout(BaseStrEnum):
    """Presentation layouts supported by collection endpoints."""

    CARDS = "cards"
    LIST = "list"
    TABLE = "table"


_KIND_INPUT_TYPES: Final[dict[FieldKind, str]] = {
    FieldKind.LONG_TEXT: "textarea",
    FieldKind.CHOICE: "select",
    FieldKind.BOOL: "checkbox",
    FieldKind.INT: "number",
    FieldKind.FLOAT: "number",
    FieldKind.EMAIL: "email",
    FieldKind.URL: "url",
    FieldKind.ISO_DATE: "date",
}


def _parse_scalar[T](parser: Callable[[str], T], raw: str, error_msg: str) -> T:
    try:
        return parser(raw.strip())
    except ValueError as exc:
        raise ValueError(error_msg) from exc


def validate_email_address(field_name: str, raw: str) -> str:
    """Validate and normalize an email address deterministically without regex backtracking."""
    clean = raw.strip().lower()
    local, sep, host = clean.partition("@")
    bad_host = "." not in host or host.startswith(".") or host.endswith(".") or "@" in host
    if not sep or not local or not host or " " in clean or bad_host:
        raise ValueError(f"Field '{field_name}' must be a valid email address")
    return clean


def validate_http_url(field_name: str, raw: str) -> str:
    """Validate an https:// or loopback http:// URL via stdlib urllib.parse.urlsplit."""
    clean = raw.strip()
    parts = urlsplit(clean)
    host = (parts.hostname or "").lower()
    is_loop = host in {"127.0.0.1", "::1", "localhost"} or host.endswith(".localhost")
    ok_scheme = parts.scheme == "https" or (parts.scheme == "http" and is_loop)
    if not host or not ok_scheme or any(ord(c) < 33 for c in clean):
        raise ValueError(f"Field '{field_name}' must be an https:// or loopback http:// URL")
    return clean


@dataclass(frozen=True, slots=True)
class ResourceFieldSpec:
    """Declarative validation, bounds, and form-control contract for a single resource field."""

    name: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    required: bool = True
    choices: tuple[str, ...] = ()
    searchable: bool = True
    filterable: bool = False
    default: Any = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int = 0
    max_length: int | None = None

    def _check_len(self, val: str) -> str:
        if len(val) < self.min_length:
            raise ValueError(f"Field '{self.name}' length must be >= {self.min_length}")
        if self.max_length is not None and len(val) > self.max_length:
            raise ValueError(f"Field '{self.name}' length must be <= {self.max_length}")
        return val

    def _check_bounds[N: (int, float)](self, val: N) -> N:
        if self.min_value is not None and val < self.min_value:
            raise ValueError(f"Field '{self.name}' must be >= {self.min_value}")
        if self.max_value is not None and val > self.max_value:
            raise ValueError(f"Field '{self.name}' must be <= {self.max_value}")
        return val

    def coerce(self, raw: object) -> Any:
        """Validate and coerce an incoming scalar value according to FieldKind."""
        is_blank_str = isinstance(raw, str) and not raw.strip() and self.kind != FieldKind.BOOL
        if raw is None or is_blank_str:
            if self.default is not None:
                return self.default
            if not self.required:
                return "" if self.kind in (FieldKind.TEXT, FieldKind.LONG_TEXT) else None
            raise ValueError(f"Field '{self.name}' is required")
        if self.kind == FieldKind.TEXT:
            return self._check_len(domain.validate_natural_text(str(raw)))
        if self.kind == FieldKind.LONG_TEXT:
            return self._check_len(domain.validate_long_text(str(raw)))
        if self.kind == FieldKind.SLUG:
            return self._check_len(domain.validate_slug(str(raw).strip()))
        if self.kind == FieldKind.CHOICE:
            val = str(raw).strip()
            if val not in self.choices:
                raise ValueError(f"Field '{self.name}' must be one of {self.choices}")
            return val
        if self.kind == FieldKind.BOOL:
            if isinstance(raw, str):
                return raw.strip().lower() in ("1", "true", "yes", "on")
            return bool(raw)
        if self.kind == FieldKind.EMAIL:
            return self._check_len(validate_email_address(self.name, str(raw)))
        if self.kind == FieldKind.URL:
            return self._check_len(validate_http_url(self.name, str(raw)))
        if self.kind == FieldKind.UUID:
            return str(_parse_scalar(UUID, str(raw), f"Field '{self.name}' must be a valid UUID"))
        if self.kind == FieldKind.ISO_DATE:
            err = f"Field '{self.name}' must be an ISO-8601 YYYY-MM-DD date"
            return _parse_scalar(date.fromisoformat, str(raw), err).isoformat()
        if self.kind == FieldKind.FLOAT:
            err = f"Field '{self.name}' must be a finite number"
            if isinstance(raw, bool):
                raise ValueError(err)
            fval = _parse_scalar(float, str(raw), err)
            if not math.isfinite(fval):
                raise ValueError(err)
            return self._check_bounds(fval)
        err_i = f"Field '{self.name}' must be an integer"
        if isinstance(raw, bool):
            raise ValueError(err_i)
        return self._check_bounds(_parse_scalar(int, str(raw), err_i))

    def to_form_field(self, *, value: str = "", error: str = "") -> SafeHTML:
        """Render a WCAG 2.2 AA HTML5 form control matching this field's kind and choices."""
        ftype = _KIND_INPUT_TYPES.get(self.kind, "text")
        return components.render_form_field(
            name=self.name,
            label=self.label,
            field_type=ftype,
            value=value,
            required=self.required,
            options=tuple((c, c) for c in self.choices),
            error=error,
        )
