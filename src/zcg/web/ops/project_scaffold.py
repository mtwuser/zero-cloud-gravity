"""Zero-dependency Hexagonal zcg.web application scaffolder (standalone or networked).

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from zcg.core.domain import is_kebab_id
from zcg.core.manifests import ensure_contained_path

MIN_WEB_APP_PORT: Final[int] = 1
MAX_WEB_APP_PORT: Final[int] = 65535
DEFAULT_WEB_APP_PORT: Final[int] = 8080


def _render_web_project_sources(
    *, eff_id: str, pkg_name: str, pascal: str, eff_title: str, port: int, mode_label: str
) -> dict[str, str]:
    pyproject_src = (
        "[build-system]\n"
        'requires = ["setuptools>=68.0"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{eff_id}"\n'
        'version = "0.1.0"\n'
        f'description = "{eff_title} — Zero-Dependency Python 3.14 zcg.web Application"\n'
        'readme = "README.md"\n'
        'requires-python = ">=3.12"\n'
        "dependencies = []\n\n"
        "[tool.setuptools]\n"
        'package-dir = { "" = "src" }\n\n'
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    readme_src = (
        f"# {eff_title} (`{eff_id}` · `{mode_label}`)\n\n"
        f"Custom Hexagonal Python 3.14 web application built directly over `zcg.web` "
        "(`0` external runtime dependencies, `0` `zcg.cockpit` coupling).\n\n"
        "## Quick Start\n\n"
        "```bash\n"
        f"PYTHONPATH=src python3 -m {pkg_name}.app --workspace . --port {port}\n"
        "```\n"
    )
    models_src = (
        f'"""Immutable Functional Core entities for {eff_id}."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n"
        "from zcg.core.domain import DomainEntity\n\n\n"
        "@dataclass(frozen=True, kw_only=True)\n"
        f"class {pascal}Item(DomainEntity):\n"
        f'    """Domain item managed by {eff_title}."""\n\n'
        "    title: str\n"
        '    summary: str = ""\n'
        '    status: str = "active"\n'
    )
    service_src = (
        f'"""Pure Functional Core service for {eff_id} (0 I/O)."""\n\n'
        "from __future__ import annotations\n\n"
        "from zcg.core.domain import generate_identifier, validate_natural_text\n\n"
        f"from .models import {pascal}Item\n\n\n"
        f"class {pascal}Service:\n"
        f'    """Validate inputs and construct immutable {pascal}Item entities."""\n\n'
        "    def create_item(\n"
        '        self, *, title: str, summary: str = "", status: str = "active"\n'
        f"    ) -> {pascal}Item:\n"
        '        """Validate natural text title and return a frozen domain entity."""\n'
        "        clean_title = validate_natural_text(title)\n"
        f"        return {pascal}Item(\n"
        "            id=generate_identifier(),\n"
        "            title=clean_title,\n"
        "            summary=summary.strip(),\n"
        '            status=status.strip() or "active",\n'
        "        )\n"
    )
    router_src = (
        f'"""Composable zcg.web APIRouter and SQLite WAL repository for {eff_id}."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n"
        "from datetime import datetime\n"
        "from http import HTTPStatus\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from zcg.core.sqlite_repo import SQLiteRepositoryAdapter\n"
        "from zcg.web.auth.security import WebAppError\n"
        "from zcg.web.http.channels import DeliveryChannel\n"
        "from zcg.web.http.factory import WebAppState\n"
        "from zcg.web.http.request import Request, WebResponse, respond\n"
        "from zcg.web.http.router import APIRouter\n\n"
        f"from {pkg_name}.domain.models import {pascal}Item\n"
        f"from {pkg_name}.domain.service import {pascal}Service\n\n\n"
        f"class _{pascal}ItemRepo(SQLiteRepositoryAdapter[{pascal}Item, str]):\n"
        f'    table_name = "{pkg_name}_items"\n\n'
        f"    def to_record(self, entity: {pascal}Item) -> dict[str, Any]:\n"
        "        return {\n"
        '            "id": entity.id,\n'
        '            "title": entity.title,\n'
        '            "summary": entity.summary,\n'
        '            "status": entity.status,\n'
        '            "created_at": entity.created_at.isoformat(),\n'
        '            "updated_at": entity.updated_at.isoformat(),\n'
        "        }\n\n"
        f"    def from_record(self, record: Mapping[str, Any]) -> {pascal}Item:\n"
        f"        return {pascal}Item(\n"
        '            id=str(record["id"]),\n'
        '            title=str(record["title"]),\n'
        '            summary=str(record.get("summary", "")),\n'
        '            status=str(record.get("status", "active")),\n'
        '            created_at=datetime.fromisoformat(str(record["created_at"])),\n'
        '            updated_at=datetime.fromisoformat(str(record["updated_at"])),\n'
        "        )\n\n\n"
        "def build_items_router(workspace_dir: Path, state: WebAppState) -> APIRouter:\n"
        '    """Mount /api/items CRUD endpoints backed by .zcg/runtime/ SQLite WAL."""\n'
        f'    db_file = workspace_dir / ".zcg/runtime/{pkg_name}.sqlite3"\n'
        f"    repo = _{pascal}ItemRepo(db_file, workspace_root=workspace_dir)\n"
        f"    svc = {pascal}Service()\n"
        '    router = APIRouter(prefix="/api/items", tags=("items",))\n\n'
        "    def _render_items(rows: list[Any]) -> str:\n"
        "        ctx = {\n"
        f'            "app_title": {eff_title!r},\n'
        '            "item_count": len(rows),\n'
        '            "items": rows,\n'
        "        }\n"
        '        return str(state.templates.render("partials/items.html", ctx))\n\n'
        '    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="List items")\n'
        "    def list_items(req: Request) -> WebResponse:\n"
        "        rows = repo.list_all()\n"
        "        return respond(\n"
        "            req,\n"
        "            html_fragment=_render_items(rows),\n"
        '            data={"items": [repo.to_record(r) for r in rows]},\n'
        "        )\n\n"
        '    @router.post("", channel=DeliveryChannel.SWAP_SYNC, summary="Create item")\n'
        "    def create_item(req: Request) -> WebResponse:\n"
        '        ctype = req.headers.get("content-type", "")\n'
        '        raw = req.json() if "application/json" in ctype else req.form()\n'
        "        payload = raw if isinstance(raw, dict) else {}\n"
        "        try:\n"
        "            created = repo.create(\n"
        "                svc.create_item(\n"
        '                    title=str(payload.get("title", "")),\n'
        '                    summary=str(payload.get("summary", "")),\n'
        '                    status=str(payload.get("status", "active")),\n'
        "                )\n"
        "            )\n"
        "        except ValueError as exc:\n"
        "            raise WebAppError(\n"
        '                str(exc), error_code="VALIDATION_ERROR", '
        "http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY)\n"
        "            ) from exc\n"
        "        rows = repo.list_all()\n"
        "        return respond(\n"
        "            req,\n"
        "            html_fragment=_render_items(rows),\n"
        '            data={"created": repo.to_record(created), "count": len(rows)},\n'
        "            status=int(HTTPStatus.CREATED),\n"
        "        )\n\n"
        "    return router\n"
    )
    app_src = (
        f'"""Native Python 3.14 ASGI application entrypoint for {eff_id} over zcg.web."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from zcg.web.auth.security import DocsAccessMode\n"
        "from zcg.web.http.channels import DeliveryChannel\n"
        "from zcg.web.http.factory import WebAppState, create_web_app\n"
        "from zcg.web.http.request import ASGIApp, Request, WebResponse\n"
        "from zcg.web.http.router import APIRouter\n"
        "from zcg.web.http.server import run_server_cli\n\n"
        f"from {pkg_name}.routers.items import build_items_router\n\n\n"
        "def _build_home_router(state: WebAppState) -> APIRouter:\n"
        '    router = APIRouter(tags=("pages",))\n\n'
        '    @router.get("/", channel=DeliveryChannel.ISLAND_SYNC, summary="Home page")\n'
        "    def home(req: Request) -> WebResponse:\n"
        "        ctx = {\n"
        f'            "title": {eff_title!r},\n'
        f'            "app_title": {eff_title!r},\n'
        '            "csrf_token": state.csrf_token,\n'
        '            "item_count": 0,\n'
        '            "items": (),\n'
        "        }\n"
        "        return state.templates.respond_template(\n"
        '            req, template_name="index.html", block_name="content", context=ctx\n'
        "        )\n\n"
        "    return router\n\n\n"
        "def create_custom_app(\n"
        "    workspace_dir: Path,\n"
        "    *,\n"
        "    csrf_token: str | None = None,\n"
        "    docs_access_mode: DocsAccessMode = DocsAccessMode.PUBLIC,\n"
        ") -> ASGIApp:\n"
        f'    """Create the standalone zcg.web ASGI application for {eff_title}."""\n'
        "    ws = workspace_dir.resolve()\n"
        "    return create_web_app(\n"
        f"        title={eff_title!r},\n"
        "        router_factory=lambda st: (_build_home_router(st), build_items_router(ws, st)),\n"
        '        template_dirs=(ws / "web/templates",),\n'
        '        static_dirs=(ws / "web/static",),\n'
        "        csrf_token=csrf_token,\n"
        "        docs_access_mode=docs_access_mode,\n"
        "    )\n\n\n"
        "def run_custom_app_cli(argv: list[str] | None = None) -> int:\n"
        '    """Run the standalone loopback HTTP/TLS server for this zcg.web application."""\n'
        "    return run_server_cli(\n"
        "        argv, app_builder=lambda ws, mode: create_custom_app(ws, docs_access_mode=mode)\n"
        "    )\n\n\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(run_custom_app_cli())\n"
    )
    index_html = (
        '{% extends "base.html" %}\n'
        "{% block head_extra %}\n"
        '<link rel="stylesheet" href="/static/css/app.css">\n'
        "{% endblock %}\n"
        "{% block content %}\n"
        f'<main class="zcg-shell" data-zcg-custom-app="{eff_id}">\n'
        '  <header class="zcg-card"><h1>{{ app_title }}</h1></header>\n'
        '  {% include "partials/items.html" %}\n'
        "</main>\n"
        "{% endblock %}\n"
    )
    partial_html = (
        f'<section class="zcg-card" data-app-module="{eff_id}-items">\n'
        "  <header><h2>{{ app_title }} ({{ item_count }})</h2></header>\n"
        "  {% if items %}\n"
        "  <ul>\n"
        "    {% for item in items %}\n"
        "    <li><strong>{{ item.title }}</strong> ({{ item.status }})</li>\n"
        "    {% endfor %}\n"
        "  </ul>\n"
        "  {% else %}\n"
        "  <p>0 items</p>\n"
        "  {% endif %}\n"
        "</section>\n"
    )
    css_src = ":root {\n  --zcg-custom-surface-gap: 1rem;\n}\n"
    test_src = (
        f'"""Isolated AAA unit tests for {pkg_name}.domain.service."""\n\n'
        "from __future__ import annotations\n\n"
        "import pytest\n\n"
        f"from {pkg_name}.domain.service import {pascal}Service\n\n\n"
        "class TestService:\n"
        f'    """Verify {pascal}Service domain invariants."""\n\n'
        "    def test_create_item_nominal_and_blank_guard_expected(self) -> None:\n"
        '        """Verify valid item creation and blank-title rejection."""\n'
        "        # Arrange\n"
        f"        svc = {pascal}Service()\n\n"
        "        # Act\n"
        '        item = svc.create_item(title="First Milestone", summary="Ready")\n\n'
        "        # Assert\n"
        '        assert item.title == "First Milestone"\n'
        '        assert item.status == "active"\n'
        "        with pytest.raises(ValueError):\n"
        '            svc.create_item(title="   ")\n'
    )
    return {
        "pyproject.toml": pyproject_src,
        "README.md": readme_src,
        f"src/{pkg_name}/__init__.py": "",
        f"src/{pkg_name}/domain/__init__.py": "",
        f"src/{pkg_name}/domain/models.py": models_src,
        f"src/{pkg_name}/domain/service.py": service_src,
        f"src/{pkg_name}/routers/__init__.py": "",
        f"src/{pkg_name}/routers/items.py": router_src,
        f"src/{pkg_name}/app.py": app_src,
        "web/templates/index.html": index_html,
        "web/templates/partials/items.html": partial_html,
        "web/static/css/app.css": css_src,
        "tests/__init__.py": "",
        "tests/unit/__init__.py": "",
        f"tests/unit/{pkg_name}/__init__.py": "",
        f"tests/unit/{pkg_name}/domain/__init__.py": "",
        f"tests/unit/{pkg_name}/domain/test_service.py": test_src,
    }


def scaffold_web_app(
    target_dir: Path,
    *,
    app_id: str | None = None,
    title: str | None = None,
    port: int = DEFAULT_WEB_APP_PORT,
    standalone: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scaffold a custom Hexagonal zcg.web application (standalone or networked)."""
    root = target_dir.resolve()
    eff_id = (app_id if app_id is not None else root.name).strip()
    if not eff_id or not is_kebab_id(eff_id):
        raise ValueError(f"INVALID_WEB_APP_ID: {eff_id!r} must match kebab-case")
    if isinstance(port, bool) or not (MIN_WEB_APP_PORT <= port <= MAX_WEB_APP_PORT):
        raise ValueError(f"INVALID_WEB_APP_PORT: {port!r} must be in 1..65535")
    pkg_name = eff_id.replace("-", "_")
    app_entry = root / "src" / pkg_name / "app.py"
    if app_entry.exists():
        raise ValueError(f"WEB_APP_ALREADY_EXISTS: src/{pkg_name}/app.py already exists in {root}")
    pascal = "".join(part.capitalize() for part in eff_id.split("-"))
    eff_title = (title or eff_id.replace("-", " ").title()).strip() or pascal
    mode_label = "standalone" if standalone else "networked"
    rel_files = _render_web_project_sources(
        eff_id=eff_id,
        pkg_name=pkg_name,
        pascal=pascal,
        eff_title=eff_title,
        port=port,
        mode_label=mode_label,
    )
    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)
        for rel_path, content in rel_files.items():
            dest = ensure_contained_path(root / rel_path, root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
    return {
        "target_dir": str(root),
        "app_id": eff_id,
        "package_name": pkg_name,
        "title": eff_title,
        "port": port,
        "mode": mode_label,
        "standalone": standalone,
        "dry_run": dry_run,
        "files_created": sorted(rel_files.keys()),
    }
