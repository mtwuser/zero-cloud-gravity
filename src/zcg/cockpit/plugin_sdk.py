"""Plugin Application SDK: contained plugin routers loader and Hexagonal module scaffolder.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

from zcg.core.constants import KEBAB_ID_RE, REPO_DIR
from zcg.core.manifests import ensure_contained_path, resolve_template_dir
from zcg.web.factory import WebAppState
from zcg.web.router import APIRouter

_HASH_SLICE_LEN: int = 8


def resolve_plugin_pack_dir(
    workspace_dir: Path, plugin_id: str, *, engine_dir: Path = REPO_DIR
) -> Path | None:
    """Resolve a validated plugin-stack directory from workspace_dir or engine_dir."""
    clean_id = plugin_id.strip()
    if not clean_id or not KEBAB_ID_RE.match(clean_id):
        return None
    ws, eng = workspace_dir.resolve(), engine_dir.resolve()
    cand = resolve_template_dir(ws, clean_id) or resolve_template_dir(eng, clean_id)
    if cand is None or not (tj_path := cand / "template.json").is_file():
        return None
    raw = json.loads(tj_path.read_text(encoding="utf-8"))
    return cand.resolve() if isinstance(raw, dict) and raw.get("kind") == "plugin-stack" else None


def _ensure_synthetic_package(pkg_name: str, pkg_dir: Path) -> None:
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_dir)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg


def load_plugin_routers(
    workspace_dir: Path, plugin_dir: Path, *, state: WebAppState
) -> tuple[APIRouter, ...]:
    """Load path-contained, permission-checked routers/*.py inside an isolated package namespace."""
    ws, pdir = workspace_dir.resolve(), plugin_dir.resolve()
    routers_dir = pdir / "routers"
    if not routers_dir.is_dir():
        return ()
    digest = hashlib.sha256(str(pdir).encode("utf-8")).hexdigest()[:_HASH_SLICE_LEN]
    root_pkg = f"_zcg_plugin_{pdir.name.replace('-', '_')}_{digest}"
    _ensure_synthetic_package(root_pkg, pdir)
    _ensure_synthetic_package(f"{root_pkg}.routers", routers_dir)
    if (mods_dir := pdir / "modules").is_dir():
        _ensure_synthetic_package(f"{root_pkg}.modules", mods_dir)
    loaded: list[APIRouter] = []
    for entry in sorted(routers_dir.iterdir()):
        if entry.suffix != ".py" or entry.name.startswith("_"):
            continue
        contained = ensure_contained_path(entry, pdir)
        if contained.stat().st_mode & stat.S_IWOTH:
            raise ValueError(
                f"UNSAFE_PLUGIN_ROUTER_PERMISSIONS: {contained.name} is world-writable"
            )
        mod_fqn = f"{root_pkg}.routers.{contained.stem}"
        loader = SourceFileLoader(mod_fqn, str(contained))
        spec = importlib.util.spec_from_loader(mod_fqn, loader)
        module = types.ModuleType(mod_fqn)
        module.__file__ = str(contained)
        module.__package__ = f"{root_pkg}.routers"
        module.__spec__ = spec
        sys.modules[mod_fqn] = module
        loader.exec_module(module)
        factory = getattr(module, "build_router", None) or getattr(module, "create_router", None)
        router_obj = factory(ws, state) if callable(factory) else getattr(module, "router", None)
        if not isinstance(router_obj, APIRouter):
            raise ValueError(
                f"INVALID_PLUGIN_ROUTER_CONTRACT: {contained.name} must expose "
                "build_router(workspace_dir, state) or router: APIRouter"
            )
        loaded.append(router_obj)
    return tuple(loaded)


def _render_scaffold_sources(
    *, plugin_id: str, clean_mod: str, mod_pkg: str, pascal: str, eff_prefix: str, desc: str
) -> dict[str, str]:
    models_src = (
        f'"""Domain entities for plugin module {clean_mod!r} ({desc})."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n"
        "from zcg.core.domain import DomainEntity\n\n\n"
        "@dataclass(frozen=True, kw_only=True)\n"
        f"class {pascal}Record(DomainEntity):\n"
        f'    """Immutable Functional Core entity for {clean_mod}."""\n\n'
        "    title: str\n"
        '    summary: str = ""\n'
        '    status: str = "verified"\n'
    )
    service_src = (
        f'"""Functional Core service for plugin module {clean_mod!r}."""\n\n'
        "from __future__ import annotations\n\n"
        "from zcg.core.domain import generate_identifier, validate_natural_text\n\n"
        f"from .models import {pascal}Record\n\n\n"
        f"class {pascal}Service:\n"
        f'    """Pure validation and creation service for {pascal}Record (0 I/O)."""\n\n'
        "    def create_record(\n"
        '        self, *, title: str, summary: str = "", status: str = "verified"\n'
        f"    ) -> {pascal}Record:\n"
        '        """Validate fields and return an immutable record."""\n'
        "        clean_title = validate_natural_text(title)\n"
        f"        return {pascal}Record(\n"
        "            id=generate_identifier(),\n"
        "            title=clean_title,\n"
        "            summary=summary.strip(),\n"
        '            status=status.strip() or "verified",\n'
        "        )\n"
    )
    router_src = (
        f'"""Native ASGI APIRouter adapter for plugin module {clean_mod!r}."""\n\n'
        "from __future__ import annotations\n\n"
        "import html\n"
        "from collections.abc import Mapping\n"
        "from datetime import datetime\n"
        "from http import HTTPStatus\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from zcg.core.sqlite_repo import SQLiteRepositoryAdapter\n"
        "from zcg.web.channels import DeliveryChannel\n"
        "from zcg.web.factory import WebAppState\n"
        "from zcg.web.request import Request, WebResponse, respond\n"
        "from zcg.web.router import APIRouter\n"
        "from zcg.web.security import WebAppError\n"
        "from zcg.web.templates import SafeHTML\n\n"
        f"from ..modules.{mod_pkg}.models import {pascal}Record\n"
        f"from ..modules.{mod_pkg}.service import {pascal}Service\n\n\n"
        f"class _{pascal}Repo(SQLiteRepositoryAdapter[{pascal}Record, str]):\n"
        f'    table_name = "{mod_pkg}_records"\n\n'
        f"    def to_record(self, entity: {pascal}Record) -> dict[str, Any]:\n"
        "        return {\n"
        '            "id": entity.id,\n'
        '            "title": entity.title,\n'
        '            "summary": entity.summary,\n'
        '            "status": entity.status,\n'
        '            "created_at": entity.created_at.isoformat(),\n'
        '            "updated_at": entity.updated_at.isoformat(),\n'
        "        }\n\n"
        f"    def from_record(self, record: Mapping[str, Any]) -> {pascal}Record:\n"
        f"        return {pascal}Record(\n"
        '            id=str(record["id"]),\n'
        '            title=str(record["title"]),\n'
        '            summary=str(record.get("summary", "")),\n'
        '            status=str(record.get("status", "verified")),\n'
        '            created_at=datetime.fromisoformat(str(record["created_at"])),\n'
        '            updated_at=datetime.fromisoformat(str(record["updated_at"])),\n'
        "        )\n\n\n"
        "def build_router(workspace_dir: Path, state: WebAppState) -> APIRouter:\n"
        '    """Mount contained plugin endpoints keeping runtime SQLite data outside Git."""\n'
        f'    db_file = workspace_dir / ".zcg/runtime/{plugin_id}_{mod_pkg}.sqlite3"\n'
        f"    repo = _{pascal}Repo(db_file, workspace_root=workspace_dir)\n"
        f"    svc = {pascal}Service()\n"
        f'    router = APIRouter(prefix="{eff_prefix}", tags=("{clean_mod}",))\n\n'
        "    def _render_fragment(records: list[Any]) -> str:\n"
        "        items = ''.join(\n"
        '            f"<li><strong>{html.escape(r.title)}</strong> "'
        '\n            f"({html.escape(r.status)})</li>"\n'
        "            for r in records\n"
        "        )\n"
        '        body_s = f"<ul>{items}</ul>" if items else "<p>0 records</p>"\n'
        "        ctx = {\n"
        f'            "module_title": "{pascal}",\n'
        '            "record_count": len(records),\n'
        '            "items_html": SafeHTML(body_s),\n'
        "        }\n"
        f'        return str(state.templates.render("partials/{clean_mod}.html", ctx))\n\n'
        f'    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="List {clean_mod}")\n'
        "    def list_records(req: Request) -> WebResponse:\n"
        "        rows = repo.list_all()\n"
        "        return respond(\n"
        "            req,\n"
        "            html_fragment=_render_fragment(rows),\n"
        '            data={"module": "'
        + clean_mod
        + '", "items": [repo.to_record(r) for r in rows]},\n'
        "        )\n\n"
        f'    @router.post("", channel=DeliveryChannel.SWAP_SYNC, summary="Create {clean_mod}")\n'
        "    def create_record_endpoint(req: Request) -> WebResponse:\n"
        '        ctype = req.headers.get("content-type", "")\n'
        '        raw = req.json() if "application/json" in ctype else req.form()\n'
        "        payload = raw if isinstance(raw, dict) else {}\n"
        "        try:\n"
        "            created = repo.create(\n"
        "                svc.create_record(\n"
        '                    title=str(payload.get("title", "")),\n'
        '                    summary=str(payload.get("summary", "")),\n'
        '                    status=str(payload.get("status", "verified")),\n'
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
        "            html_fragment=_render_fragment(rows),\n"
        '            data={"created": repo.to_record(created), "count": len(rows)},\n'
        "            status=int(HTTPStatus.CREATED),\n"
        "        )\n\n"
        "    return router\n"
    )
    partial_html = (
        f'<section class="zcg-card" data-plugin-module="{clean_mod}">\n'
        "  <header><h3>{{ module_title }} ({{ record_count }})</h3></header>\n"
        "  <div>{{ items_html }}</div>\n"
        "</section>\n"
    )
    return {
        "modules/__init__.py": "",
        f"modules/{mod_pkg}/__init__.py": "",
        f"modules/{mod_pkg}/models.py": models_src,
        f"modules/{mod_pkg}/service.py": service_src,
        "routers/__init__.py": "",
        f"routers/{mod_pkg}.py": router_src,
        f"web/templates/partials/{clean_mod}.html": partial_html,
    }


def scaffold_plugin_module(
    repo_dir: Path,
    *,
    plugin_id: str,
    module_name: str,
    route_prefix: str | None = None,
    description: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scaffold a Hexagonal module + APIRouter + HTML partial inside a plugin-stack pack."""
    clean_plugin, clean_mod = plugin_id.strip(), module_name.strip()
    if not KEBAB_ID_RE.match(clean_plugin):
        raise ValueError(f"Invalid plugin_id {plugin_id!r}: must match kebab-case")
    if not KEBAB_ID_RE.match(clean_mod):
        raise ValueError(f"Invalid module_name {module_name!r}: must match kebab-case")
    eff_prefix = (route_prefix or f"/api/plugins/{clean_mod}").strip()
    if not eff_prefix.startswith("/") or ".." in eff_prefix or " " in eff_prefix:
        raise ValueError(f"Invalid route_prefix {route_prefix!r}: must be a clean '/...' URI path")
    root = repo_dir.resolve()
    tpl_dir = resolve_plugin_pack_dir(root, clean_plugin, engine_dir=root)
    if tpl_dir is None:
        raise ValueError(f"Plugin pack {clean_plugin!r} (kind='plugin-stack') not found in {root}")
    mod_pkg = clean_mod.replace("-", "_")
    if (tpl_dir / "routers" / f"{mod_pkg}.py").exists():
        raise ValueError(f"Plugin module router already exists: routers/{mod_pkg}.py")
    pascal = "".join(part.capitalize() for part in clean_mod.split("-"))
    desc = (description or f"{clean_mod} module for {clean_plugin}").strip()
    rel_base = str(tpl_dir.relative_to(root)).replace("\\", "/")
    rel_files = {
        f"{rel_base}/{sub_rel}": body
        for sub_rel, body in _render_scaffold_sources(
            plugin_id=clean_plugin,
            clean_mod=clean_mod,
            mod_pkg=mod_pkg,
            pascal=pascal,
            eff_prefix=eff_prefix,
            desc=desc,
        ).items()
    }
    if not dry_run:
        for rel_p, content in rel_files.items():
            dest = ensure_contained_path(root / rel_p, root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        tj_path = tpl_dir / "template.json"
        tj_doc: dict[str, Any] = json.loads(tj_path.read_text(encoding="utf-8"))
        rs = dict(tj_doc.get("runtime_service") or {})
        existing = [str(r) for r in rs.get("plugin_routers", []) if str(r).strip()]
        router_rel = f"routers/{mod_pkg}.py"
        rs["plugin_routers"] = list(dict.fromkeys([*existing, router_rel]))
        tj_doc["runtime_service"] = rs
        tj_path.write_text(json.dumps(tj_doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return {
        "plugin_id": clean_plugin,
        "module_name": clean_mod,
        "module_package": mod_pkg,
        "route_prefix": eff_prefix,
        "dry_run": dry_run,
        "files_created": sorted(rel_files.keys()),
    }
