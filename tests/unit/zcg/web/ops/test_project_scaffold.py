"""Unit tests for zcg.web.ops.project_scaffold.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from zcg.governance.policy.arch_linter import lint_architecture
from zcg.web.auth.security import CSRF_HEADER
from zcg.web.http.request import ASGIApp, Message, Scope
from zcg.web.ops.project_scaffold import scaffold_web_app


async def _invoke_app(
    app: ASGIApp,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    raw_h = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_h,
    }
    consumed = False
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    status = int(sent[0]["status"])
    return status, b"".join(bytes(m.get("body", b"")) for m in sent[1:])


class TestProjectScaffold:
    """Verify standalone/networked zcg.web project generation, AST purity, and live ASGI routes."""

    def test_scaffold_web_app_dry_run_and_live_standalone_asgi_execution_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify scaffolded zcg.web project passes lint-arch and serves /, GET/POST /api/items."""
        # Arrange
        dry_dir = tmp_path / "dry-studio"
        app_dir = tmp_path / "iso-studio"
        csrf = "custom-web-csrf"

        # Act
        dry_res = scaffold_web_app(dry_dir, dry_run=True)
        live_res = scaffold_web_app(app_dir, title="ISO Studio Portal", port=8090, standalone=True)
        net_res = scaffold_web_app(
            tmp_path / "net-portal", app_id="net-portal", title="   ", standalone=False
        )
        arch_res = lint_architecture(app_dir, check_tests=True)

        monkeypatch.syspath_prepend(str(app_dir / "src"))
        spec = importlib.util.spec_from_file_location(
            "iso_studio.app", app_dir / "src/iso_studio/app.py"
        )
        assert spec is not None and spec.loader is not None
        app_mod = importlib.util.module_from_spec(spec)
        sys.modules["iso_studio.app"] = app_mod
        try:
            spec.loader.exec_module(app_mod)
            app = app_mod.create_custom_app(app_dir, csrf_token=csrf)
            cli_rc = app_mod.run_custom_app_cli(["--workspace", str(app_dir), "--self-test"])

            async def _exercise() -> dict[str, Any]:
                st_home, b_home = await _invoke_app(
                    app, "GET", "/", headers={"accept": "text/html"}
                )
                st_empty, b_empty = await _invoke_app(
                    app, "GET", "/api/items", headers={"hx-request": "true"}
                )
                st_bad, b_bad = await _invoke_app(
                    app,
                    "POST",
                    "/api/items",
                    headers={CSRF_HEADER: csrf, "content-type": "application/json"},
                    body=b'{"title": "   "}',
                )
                st_json, b_json = await _invoke_app(
                    app,
                    "POST",
                    "/api/items",
                    headers={CSRF_HEADER: csrf, "content-type": "application/json"},
                    body=b'{"title": "Launch V1", "summary": "Standalone"}',
                )
                st_form, b_form = await _invoke_app(
                    app,
                    "POST",
                    "/api/items",
                    headers={
                        CSRF_HEADER: csrf,
                        "hx-request": "true",
                        "content-type": "application/x-www-form-urlencoded",
                    },
                    body=b"title=Launch+V2&status=shipped",
                )
                st_list, b_list = await _invoke_app(app, "GET", "/api/items")
                return {
                    "home": (st_home, b_home),
                    "empty": (st_empty, b_empty),
                    "bad": (st_bad, b_bad),
                    "json": (st_json, json.loads(b_json)),
                    "form": (st_form, b_form),
                    "list": (st_list, json.loads(b_list)),
                }

            out = asyncio.run(_exercise())
        finally:
            for k in [m for m in sys.modules if m == "iso_studio" or m.startswith("iso_studio.")]:
                sys.modules.pop(k, None)

        # Assert
        assert dry_res["dry_run"] is True and not (dry_dir / "pyproject.toml").exists()
        assert live_res["mode"] == "standalone" and live_res["package_name"] == "iso_studio"
        assert net_res["mode"] == "networked" and net_res["title"] == "NetPortal"
        assert arch_res["passed"] is True and arch_res["violation_count"] == 0
        assert cli_rc == 0
        assert out["home"][0] == 200 and b"<!doctype html>" in out["home"][1]
        assert b"ISO Studio Portal" in out["home"][1]
        assert out["empty"][0] == 200 and b"0 items" in out["empty"][1]
        assert out["bad"][0] == 422 and b"VALIDATION_ERROR" in out["bad"][1]
        assert out["json"][0] == 201 and out["json"][1]["count"] == 1
        assert out["form"][0] == 201 and b"Launch V2" in out["form"][1]
        assert out["list"][0] == 200 and len(out["list"][1]["items"]) == 2
        assert (app_dir / ".zcg/runtime/iso_studio.sqlite3").is_file()

    def test_scaffold_web_app_bipolar_id_port_and_duplicate_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify validation errors on invalid kebab IDs, ports (0, 65536, bool), and duplicates."""
        # Arrange
        dup_dir = tmp_path / "dup-app"
        first_res = scaffold_web_app(dup_dir)
        caught_codes: list[str] = []

        # Act
        for bad_id in ("", "   ", "Bad_ID", "-leading"):
            with pytest.raises(ValueError, match="INVALID_WEB_APP_ID") as exc_id:
                scaffold_web_app(tmp_path / "x", app_id=bad_id)
            caught_codes.append(str(exc_id.value))
        for bad_port in (0, 65536, True):
            with pytest.raises(ValueError, match="INVALID_WEB_APP_PORT") as exc_port:
                scaffold_web_app(tmp_path / "y", app_id="ok-app", port=bad_port)
            caught_codes.append(str(exc_port.value))
        with pytest.raises(ValueError, match="WEB_APP_ALREADY_EXISTS") as exc_dup:
            scaffold_web_app(dup_dir)
        caught_codes.append(str(exc_dup.value))

        # Assert
        assert first_res["app_id"] == "dup-app"
        assert first_res["title"] == "Dup App"
        assert len(caught_codes) == 8
