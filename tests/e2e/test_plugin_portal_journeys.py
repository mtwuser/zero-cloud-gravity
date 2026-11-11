"""End-to-end plugin portal, project spinout, and public sovereign twin (org-* & pub-*) journeys.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zcg.cli.dispatcher import dispatch_zcg_cli
from zcg.cockpit.asgi import create_node_cockpit_asgi_app
from zcg.core.constants import NODE_MANIFEST_REL_PATH, REPO_DIR
from zcg.topology.identity import resolve_node_entity_identity
from zcg.web.request import Message, Scope
from zcg.web.security import CSRF_HEADER


def _run_zcg(repo_dir: Path, subcmd: str, *args: str) -> dict[str, Any]:
    code, payload, err = dispatch_zcg_cli(repo_dir, False, subcmd, list(args))
    if code != 0 or payload is None:
        raise RuntimeError(f"zcg {subcmd} {args} failed ({code}): {err}")
    return payload


async def _asgi_req(
    app: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_h,
    }
    sent: list[Message] = []
    consumed = False

    async def receive() -> Message:
        nonlocal consumed
        chunk = b"" if consumed else body
        consumed = True
        return {"type": "http.request", "body": chunk, "more_body": False}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(bytes(m.get("body", b"")) for m in sent[1:])


class TestPluginPortalJourneys:
    """Verify departmental plugin portals on org-* pro and personal spinout + pub-* pro portals."""

    def test_departmental_plugin_portal_promoted_to_org_public_twin_pro_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify dept-tech scaffolds custom plugin + module and deploys to org-alpha pro."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        corp_root = tmp_path / "corp-alpha-root"
        dept_tech = corp_root / "layers/dept-tech"
        org_alpha = tmp_path / "org-alpha"
        csrf_val = f"tok-{tmp_path.name}"

        # Act — 1. Bootstrap Root 0, dept-tech, and org-alpha Public Sovereign Twin
        _run_zcg(
            REPO_DIR, "bootstrap", str(corp_root), "--id", "corp-alpha-root", "--role", "corporate"
        )
        _run_zcg(corp_root, "set-authority", "--owner-role", "CTO", "--emails", "cto@alpha.example")
        _run_zcg(
            REPO_DIR, "bootstrap", str(dept_tech), "--id", "dept-tech",
            "--role", "department", "--parent-dir", str(corp_root),
        )  # fmt: skip
        _run_zcg(
            REPO_DIR, "bootstrap", str(org_alpha), "--id", "org-alpha",
            "--role", "knowledge", "--governing-root", "corp-alpha-root",
        )  # fmt: skip
        org_m_path = org_alpha / NODE_MANIFEST_REL_PATH
        org_m = json.loads(org_m_path.read_text(encoding="utf-8"))
        org_m["visibility"] = "public"
        org_m["public_url"] = "https://github.com/alpha-example/org-alpha.git"
        org_m_path.write_text(json.dumps(org_m, indent=2) + "\n", encoding="utf-8")
        (org_alpha / "WORKTASK.md").write_text("# Tasks\n- [x] Ready\n", encoding="utf-8")
        (org_alpha / "WORKVALI.md").write_text("# Validation\n- [x] Verified\n", encoding="utf-8")
        (org_alpha / "CHANGELOG.md").write_text("# Changelog\n## [Unreleased]\n", encoding="utf-8")

        # 2. Scaffold custom plugin-stack pack + Hexagonal module in dept-tech
        _run_zcg(dept_tech, "scaffold-template", "alpha-public-portal", "--kind", "plugin-stack")
        _run_zcg(dept_tech, "scaffold-plugin-module", "alpha-public-portal", "batch-verifier")
        pack_dir = dept_tech / "templates/alpha-public-portal"
        (pack_dir / "web/templates/partials").mkdir(parents=True, exist_ok=True)
        (pack_dir / "web/static/css").mkdir(parents=True, exist_ok=True)
        (pack_dir / "web/templates/partials/overview.html").write_text(
            "<section id='alpha-hero'>Alpha Public Portal ({{ active_env }})</section>",
            encoding="utf-8",
        )
        (pack_dir / "web/static/css/plugin.css").write_text(
            ":root { --zcg-accent: #f59e0b; }\n", encoding="utf-8"
        )

        # 3. Install & activate alpha-public-portal on org-alpha in pro (public-remote-live)
        _run_zcg(
            REPO_DIR, "apply-project", str(org_alpha),
            "--template", "alpha-public-portal",
            "--service-action", "install",
            "--parent-dir", str(dept_tech),
        )  # fmt: skip
        act_res = _run_zcg(
            REPO_DIR, "apply-project", str(org_alpha),
            "--template", "alpha-public-portal",
            "--service-action", "activate",
            "--env", "pro",
            "--email", "cto@alpha.example",
            "--parent-dir", str(corp_root),
        )  # fmt: skip
        app = create_node_cockpit_asgi_app(org_alpha, csrf_token=csrf_val)

        async def _verify_live_portal() -> dict[str, tuple[int, bytes]]:
            return {
                "dash": await _asgi_req(app, "GET", "/dashboard"),
                "css": await _asgi_req(app, "GET", "/static/css/plugin.css"),
                "post": await _asgi_req(
                    app,
                    "POST",
                    "/api/plugins/batch-verifier",
                    headers={CSRF_HEADER: csrf_val, "content-type": "application/json"},
                    body=b'{"title":"Lot-2026-01","summary":"Verified external batch"}',
                ),
                "list": await _asgi_req(app, "GET", "/api/plugins/batch-verifier"),
            }

        http_out = asyncio.run(_verify_live_portal())

        # Assert
        svc = act_res["services"][0]
        assert svc["environment"] == "pro"
        assert svc["intranet_topology"]["environment_reachability"]["pro"] == "public-remote-live"
        assert (
            svc["intranet_topology"]["active_subdomain_url"] == "https://org-alpha.knowledge.local"
        )
        assert (
            svc["intranet_topology"]["remote_production_url"]
            == "https://github.com/alpha-example/org-alpha.git"
        )
        assert http_out["dash"][0] == 200
        assert b"Alpha Public Portal (pro)" in http_out["dash"][1]
        assert http_out["css"][0] == 200 and b"#f59e0b" in http_out["css"][1]
        assert http_out["post"][0] == 201
        assert http_out["list"][0] == 200
        assert len(json.loads(http_out["list"][1])["items"]) == 1
        assert (org_alpha / ".zcg/runtime/alpha-public-portal_batch_verifier.sqlite3").is_file()
        assert list((org_alpha / "templates").rglob("*.sqlite3")) == []

    def test_personal_sovereign_spinout_project_and_pub_twin_pro_portal_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify alex-pc stays private while venture spins out and pub-alex serves pro."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        alex_pc = tmp_path / "alex-pc"
        alex_work = tmp_path / "alex-work"
        micro_saas = tmp_path / "micro-saas"
        pub_alex = tmp_path / "pub-alex"

        # Act — 1. Bootstrap private alex-pc (:8790) & alex-work (:8787) and spinout venture/*
        _run_zcg(
            REPO_DIR, "bootstrap", str(alex_pc), "--id", "alex-pc",
            "--role", "workstation", "--entity-kind", "individual", "--precedence", "90",
        )  # fmt: skip
        _run_zcg(
            REPO_DIR, "bootstrap", str(alex_work), "--id", "alex-work",
            "--role", "department", "--entity-kind", "individual",
            "--governing-root", "alex-pc", "--precedence", "87",
        )  # fmt: skip
        subprocess.run(
            ["git", "init", "-b", "master"], cwd=alex_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "alex@example.org"], cwd=alex_work, check=True
        )
        subprocess.run(["git", "config", "user.name", "Alex"], cwd=alex_work, check=True)
        subprocess.run(["git", "add", "."], cwd=alex_work, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=alex_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "venture/micro-saas"],
            cwd=alex_work, check=True, capture_output=True,
        )  # fmt: skip
        (alex_work / "app.py").write_text("READY = True\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=alex_work, check=True)
        subprocess.run(
            ["git", "commit", "-m", "mvp"], cwd=alex_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "master"], cwd=alex_work, check=True, capture_output=True
        )

        spin_res = _run_zcg(
            REPO_DIR, "spinout-project", str(micro_saas),
            "--source-dir", str(alex_work),
            "--id", "micro-saas", "--from-branch", "venture/micro-saas",
        )  # fmt: skip

        # 2. Bootstrap pub-alex Public Sovereign Twin governed by alex-pc & activate in pro
        _run_zcg(
            REPO_DIR, "bootstrap", str(pub_alex), "--id", "pub-alex",
            "--role", "knowledge", "--governing-root", "alex-pc",
        )  # fmt: skip
        pub_m_path = pub_alex / NODE_MANIFEST_REL_PATH
        pub_m = json.loads(pub_m_path.read_text(encoding="utf-8"))
        pub_m["visibility"] = "public"
        pub_m["public_url"] = "https://github.com/alex-example/pub-alex.git"
        pub_m_path.write_text(json.dumps(pub_m, indent=2) + "\n", encoding="utf-8")
        (pub_alex / "WORKTASK.md").write_text("# Tasks\n- [x] Ready\n", encoding="utf-8")
        (pub_alex / "WORKVALI.md").write_text("# Validation\n- [x] Verified\n", encoding="utf-8")
        (pub_alex / "CHANGELOG.md").write_text("# Changelog\n## [Unreleased]\n", encoding="utf-8")

        pub_act = _run_zcg(
            REPO_DIR, "apply-project", str(pub_alex),
            "--template", "knowledge-stewardship-portal",
            "--service-action", "activate", "--env", "pro",
        )  # fmt: skip
        pc_id = resolve_node_entity_identity(alex_pc)
        pub_id = resolve_node_entity_identity(pub_alex)
        proj_m = json.loads((micro_saas / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8"))
        pub_app = create_node_cockpit_asgi_app(pub_alex)
        pub_dash = asyncio.run(_asgi_req(pub_app, "GET", "/dashboard"))

        # Assert
        assert spin_res["project_id"] == "micro-saas"
        assert proj_m["layer_role"] == "project"
        assert proj_m["precedence"] == 80
        assert (micro_saas / "app.py").is_file()
        assert pc_id["visibility"] == "private"
        assert pub_id["entity_kind"] == "individual"
        assert pub_id["visibility"] == "public"
        assert pub_id["public_node_identity"]["bridge_mode"] == "private-to-public-twin"
        assert pub_id["public_node_identity"]["canonical_domain"] == "pub-alex.knowledge.local"
        pub_svc = pub_act["services"][0]
        assert (
            pub_svc["intranet_topology"]["environment_reachability"]["pro"] == "public-remote-live"
        )
        assert (
            pub_svc["intranet_topology"]["active_subdomain_url"]
            == "https://pub-alex.knowledge.local"
        )
        assert (
            pub_svc["intranet_topology"]["remote_production_url"]
            == "https://github.com/alex-example/pub-alex.git"
        )
        assert pub_dash[0] == 200 and b"knowledge-stewardship-portal" in pub_dash[1]
