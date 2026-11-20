"""Implementation contracts for native web package assets, ES2024 syntax, and strict Zone CSP.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import ast
import asyncio
import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from zcg.cockpit.ops.asgi import create_node_cockpit_asgi_app
from zcg.cockpit.views.surfaces import (
    materialize_node_data_scopes,
    resolve_node_intranet_topology,
)
from zcg.core.constants import REPO_DIR
from zcg.governance.policy.arch_linter import ALLOWED_REGEX_MODULES
from zcg.governance.workspace.bootstrap import bootstrap_node_workspace
from zcg.web.auth.security import build_zone_security_headers
from zcg.web.http.channels import Zone
from zcg.web.ui.static_files import BUILTIN_STATIC_ASSETS
from zcg.web.ui.templates import BUILTIN_TEMPLATES

if TYPE_CHECKING:
    from pathlib import Path

MAX_JS_SOURCE_LINES: int = 384


async def _asgi_get(
    app: Any, path: str, *, query: str = "", host: str, hx: bool = False
) -> tuple[int, str]:
    hdrs: list[tuple[bytes, bytes]] = [(b"host", host.encode("latin1"))]
    if hx:
        hdrs.append((b"hx-request", b"true"))
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": hdrs,
    }
    await app(scope, receive, send)
    body = b"".join(m.get("body", b"") for m in sent if "body" in m).decode("utf-8")
    return int(sent[0]["status"]), body


class TestWebAssetContracts:
    """Verify importlib.resources web assets, ES2024 node --check syntax, and strict Z1..Z4 CSP."""

    def test_es2024_assets_syntax_line_budgets_and_dom_safety_expected(self) -> None:
        """Verify every engine and plugin .js file passes node --check and DOM safety contracts."""
        # Arrange
        engine_js = sorted((REPO_DIR / "src/zcg/web/assets/js").glob("*.js"))
        plugin_js = sorted((REPO_DIR / "templates").rglob("*.js"))
        all_js = [*engine_js, *plugin_js]
        node_bin = shutil.which("node")

        # Act
        checked_results = [
            (
                js_path,
                js_path.read_text(encoding="utf-8"),
                subprocess.run([node_bin, "--check", str(js_path)], capture_output=True)
                if node_bin is not None
                else None,
            )
            for js_path in all_js
        ]

        # Assert
        assert len(engine_js) == 5
        assert len(plugin_js) == 7
        for js_path, src_txt, proc in checked_results:
            line_count = len(src_txt.splitlines())
            assert line_count <= MAX_JS_SOURCE_LINES, f"{js_path} exceeds 384 lines ({line_count})"
            if proc is not None:
                assert proc.returncode == 0, f"ES2024 syntax error in {js_path}: {proc.stderr!r}"
        assert ".innerHTML =" not in BUILTIN_STATIC_ASSETS["js/spatial-atlas.js"][1]
        assert ".innerHTML =" not in BUILTIN_STATIC_ASSETS["js/cockpit-shell.js"][1]

    def test_strict_zone_csp_zero_unsafe_inline_script_src_and_templates_expected(self) -> None:
        """Verify Z1..Z4 CSP policies emit 0 'unsafe-inline' in script-src and templates load."""
        # Arrange
        zones = (Zone.Z1, Zone.Z2, Zone.Z3, Zone.Z4)
        cdn = ("https://cdn.iso.example",)

        # Act
        policies = [
            (
                z,
                build_zone_security_headers(z),
                build_zone_security_headers(z, allowed_cdn_origins=cdn)["content-security-policy"],
            )
            for z in zones
        ]

        # Assert
        assert set(BUILTIN_TEMPLATES) == {
            "base.html",
            "plugin_shell.html",
            "portal_shell.html",
            "cockpit_passport.html",
        }
        for zone, base_headers, cdn_csp in policies:
            assert "permissions-policy" in base_headers
            assert base_headers["cross-origin-resource-policy"] == "same-origin"
            for csp_str in (base_headers["content-security-policy"], cdn_csp):
                directives = {
                    part.strip().split()[0]: part.strip()
                    for part in csp_str.split(";")
                    if part.strip()
                }
                assert "'unsafe-inline'" not in directives["script-src"], f"{zone}: {csp_str}"

    def test_deterministic_parsers_and_zero_uncached_regex_compilation_expected(self) -> None:
        """Verify 0 regex imports outside ALLOWED_REGEX_MODULES and deterministic guard hooks."""
        # Arrange
        guard_script = REPO_DIR / "antigravity/.gemini/config/scripts/pre_tool_guard.py"
        py_files = sorted((REPO_DIR / "src/zcg").rglob("*.py"))
        aux_py_files = [
            *sorted((REPO_DIR / "antigravity/.gemini/config/scripts").glob("*.py")),
            *sorted((REPO_DIR / "tests").rglob("*.py")),
        ]

        def _eval_guard(tool_name: str, args: dict[str, object]) -> str:
            payload = json.dumps({"toolCall": {"name": tool_name, "args": args}})
            proc = subprocess.run(
                [sys.executable, str(guard_script)],
                input=payload,
                text=True,
                capture_output=True,
                check=True,
            )
            return str(json.loads(proc.stdout)["decision"])

        # Act
        regex_imports = [
            str(f.relative_to(REPO_DIR))
            for f in aux_py_files
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
            if (isinstance(n, ast.Import) and any(a.name == "re" for a in n.names))
            or (isinstance(n, ast.ImportFrom) and n.module == "re")
        ]
        actual_regex_mods = {
            ".".join(p.relative_to(REPO_DIR / "src").with_suffix("").parts)
            for p in py_files
            if p.name != "__init__.py"
            and any(
                (isinstance(n, ast.Import) and any(a.name == "re" for a in n.names))
                or (isinstance(n, ast.ImportFrom) and n.module == "re")
                for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
            )
        }
        uncached_fn_compiles: list[str] = []
        for py_path in py_files:
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                is_cached = any(
                    (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "lru_cache")
                    or getattr(d, "id", "") == "lru_cache"
                    for d in fn.decorator_list
                )
                if is_cached:
                    continue
                for sub in ast.walk(fn):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "re"
                        and sub.func.attr == "compile"
                    ):
                        uncached_fn_compiles.append(f"{py_path.name}:{fn.name}:{sub.lineno}")
        decisions = {
            "allow_git_status": _eval_guard("run_command", {"CommandLine": "git status --short"}),
            "allow_empty_init": _eval_guard(
                "write_file", {"Path": "src/demo/__init__.py", "Content": ""}
            ),
            "deny_git_commit": _eval_guard("run_command", {"CommandLine": "git commit -m 'x'"}),
            "deny_subst_push": _eval_guard("run_command", {"CommandLine": "echo $(git push)"}),
            "deny_backtick_alembic": _eval_guard(
                "run_command", {"CommandLine": "echo `alembic upgrade head`"}
            ),
            "deny_py_init_write": _eval_guard(
                "run_command",
                {"CommandLine": "python3 -c \"open('src/a/__init__.py', 'w').write('x')\""},
            ),
            "deny_layer_rule": _eval_guard(
                "write_file",
                {"Path": ".agents/rules/layer-10-root.md", "Content": "# Rule\n"},
            ),
        }

        # Assert
        assert not ALLOWED_REGEX_MODULES
        assert regex_imports == []
        assert actual_regex_mods == set()
        assert uncached_fn_compiles == []
        assert decisions == {
            "allow_git_status": "allow",
            "allow_empty_init": "allow",
            "deny_git_commit": "deny",
            "deny_subst_push": "deny",
            "deny_backtick_alembic": "deny",
            "deny_py_init_write": "deny",
            "deny_layer_rule": "deny",
        }

    def test_web_and_cockpit_subpackages_hold_zero_flat_root_modules_expected(self) -> None:
        """Verify web/ and cockpit/ organize all modules inside cohesive subpackages."""
        # Arrange
        web_root = REPO_DIR / "src/zcg/web"
        cockpit_root = REPO_DIR / "src/zcg/cockpit"

        # Act
        flat_web = [p.name for p in web_root.glob("*.py") if p.name != "__init__.py"]
        flat_cockpit = [p.name for p in cockpit_root.glob("*.py") if p.name != "__init__.py"]
        web_subpkgs = {
            p.name for p in web_root.iterdir() if p.is_dir() and (p / "__init__.py").is_file()
        }
        cockpit_subpkgs = {
            p.name for p in cockpit_root.iterdir() if p.is_dir() and (p / "__init__.py").is_file()
        }

        # Assert
        assert flat_web == []
        assert flat_cockpit == []
        assert web_subpkgs == {"http", "auth", "ui", "ops", "capabilities"}
        assert cockpit_subpkgs == {"ops", "routing", "views"}

    def test_workspace_and_admin_dom_deduplication_and_1to1_hints_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 0 duplicate headings/scope bars, 1:1 WORK* hints, and staged-only gates."""
        # Arrange
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        ws_personal = tmp_path / "persona-profile"
        ws_corp = tmp_path / "corp-acme"
        boot_p = bootstrap_node_workspace(
            REPO_DIR,
            ws_personal,
            layer_id="persona-profile",
            layer_role="workstation",
            entity_kind="individual",
            home_dir=home_dir,
        )
        boot_c = bootstrap_node_workspace(
            REPO_DIR,
            ws_corp,
            layer_id="corp-acme",
            layer_role="corporate",
            entity_kind="enterprise",
            home_dir=home_dir,
        )
        for ws_dir, manifest, pid in (
            (ws_personal, boot_p["manifest"], "workstation-control-tower"),
            (ws_corp, boot_c["manifest"], "corporate-root-hub"),
        ):
            lid = str(manifest["layer_id"])
            topo = resolve_node_intranet_topology(manifest, layer_id=lid)
            materialize_node_data_scopes(
                ws_dir,
                manifest,
                {"plugin_id": pid, "environment": "dev", "intranet_topology": topo},
            )
        (ws_personal / "surfaces/data/network_scope.json").write_text(
            json.dumps(
                {
                    "network_representation_links": {
                        "downward_child_nodes": [
                            {
                                "node_id": "persona-work",
                                "layer_role": "department",
                                "cockpit_url": "http://persona-work.localhost:8787/",
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        app_personal = create_node_cockpit_asgi_app(ws_personal)
        app_corp = create_node_cockpit_asgi_app(ws_corp)
        p_host, c_host = "persona-profile.localhost:8790", "corp-acme.localhost:8720"

        async def _collect() -> dict[str, tuple[int, str]]:
            return {
                "admin": await _asgi_get(app_personal, "/admin", host=p_host),
                "ws_root": await _asgi_get(app_personal, "/", query="view=workspace", host=p_host),
                "pending_setup": await _asgi_get(
                    app_personal, "/", query="setup=studio", host=p_host
                ),
                "atlas": await _asgi_get(app_personal, "/atlas", host=p_host),
                "atlas_alias": await _asgi_get(app_personal, "/", query="view=atlas", host=p_host),
                "docs": await _asgi_get(
                    app_personal, "/api/modules/docs-reader", host=p_host, hx=True
                ),
                "dashboard": await _asgi_get(
                    app_personal,
                    "/api/modules/work-ledger",
                    query="section=dashboard",
                    host=p_host,
                    hx=True,
                ),
                "backlog": await _asgi_get(
                    app_personal,
                    "/api/modules/work-ledger",
                    query="section=backlog",
                    host=p_host,
                    hx=True,
                ),
                "roadmaps": await _asgi_get(
                    app_personal,
                    "/api/modules/work-ledger",
                    query="section=roadmaps",
                    host=p_host,
                    hx=True,
                ),
                "validations_direct": await _asgi_get(
                    app_personal,
                    "/api/modules/work-ledger",
                    query="section=validations",
                    host=p_host,
                    hx=True,
                ),
                "validations_staged": await _asgi_get(
                    app_corp,
                    "/api/modules/work-ledger",
                    query="section=validations",
                    host=c_host,
                    hx=True,
                ),
                "metrics": await _asgi_get(
                    app_personal,
                    "/api/modules/work-ledger",
                    query="section=metrics",
                    host=p_host,
                    hx=True,
                ),
                "crud": await _asgi_get(app_personal, "/api/modules/crud", host=p_host, hx=True),
            }

        # Act
        pages = asyncio.run(_collect())
        admin_h, atlas_h, pend_h = pages["admin"][1], pages["atlas"][1], pages["pending_setup"][1]
        docs_h, dash_h, bkl_h = pages["docs"][1], pages["dashboard"][1], pages["backlog"][1]
        road_h, met_h, crud_h = pages["roadmaps"][1], pages["metrics"][1], pages["crud"][1]
        val_dir_h, val_stg_h = pages["validations_direct"][1], pages["validations_staged"][1]
        all_frags = "".join((docs_h, dash_h, bkl_h, road_h, val_dir_h, val_stg_h, met_h, crud_h))

        # Assert
        assert all(status == 200 for status, _ in pages.values())
        assert "<h2>Health &amp; Telemetry</h2>" not in admin_h
        assert "<h2>Brand &amp; Identity</h2>" not in admin_h
        assert 'id="admin-remote-title"' not in admin_h and '<h1 id="title"' in admin_h
        assert "data-zcg-ws-scope" in pages["ws_root"][1]
        assert "zcg-atlas-icon-btn is-active' href='/atlas' aria-current='page'" in atlas_h
        assert "<a class='is-active' aria-current='page' href='/'>" not in atlas_h
        assert "<h3>2D/3D Network Atlas</h3>" not in atlas_h
        assert "data-zcg-ws-scope" not in atlas_h and 'data-island="spatial-atlas"' in atlas_h
        assert "id='zcg-atlas-stage'" in pages["atlas_alias"][1]
        assert "1-Hop Nodes" in pend_h and "persona-work" in pend_h
        for forbidden in (
            "<h3>Docs &amp; Knowledge</h3>",
            "<h3>Queued Backlog",
            "<h3>Strategic Roadmaps",
            "<h3>Validation",
            "metrics_scope=",
            "<select name='scope'",
        ):
            assert forbidden not in all_frags
        assert "records</span>" in crud_h and '<header class="zcg-card__header"><h3>' not in crud_h
        assert "Tracked files:" in docs_h and "README.md" in docs_h
        assert "Tracked files:" in dash_h and "WORKTASK.md" in dash_h and "[TASK-NNN]" in dash_h
        assert "BACKLOG.md" not in dash_h
        assert "Tracked files:" in bkl_h and "BACKLOG.md" in bkl_h and "[BKL-NNN]" in bkl_h
        assert "WORKTASK.md" not in bkl_h
        assert "Tracked files:" in road_h and "WORKROAD.md" in road_h and "[ROAD-NNN]" in road_h
        assert "Tracked files:" in val_dir_h and "WORKVALI.md" in val_dir_h
        assert "[VAL-NNN]" in val_dir_h
        assert "Gate [DEV]" not in val_dir_h and "Gate [PRO]" not in val_dir_h
        assert "Gate [DEV]" in val_stg_h and "Gate [PRO]" in val_stg_h
