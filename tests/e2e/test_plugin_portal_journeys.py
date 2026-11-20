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
from zcg.cockpit.ops.asgi import create_node_cockpit_asgi_app
from zcg.cockpit.routing.surface_routing import project_ring_scoped_capsule
from zcg.core.constants import NODE_MANIFEST_REL_PATH, REPO_DIR, SIDECAR_MANIFEST_REL_PATH
from zcg.governance.policy.capabilities import compute_template_pack_sha256
from zcg.governance.runtime.tool_isolation import provision_isolated_tool_manifest
from zcg.mcp.http_transport import create_mcp_asgi_app
from zcg.mcp.server import ZeroCloudMCPServer
from zcg.platform.projection import DisclosureTier, PayloadFieldSegment
from zcg.topology.identity import resolve_node_entity_identity
from zcg.web.auth.security import CSRF_HEADER, compute_sri_sha384
from zcg.web.auth.surface_access import (
    DISCLOSURE_TIER_HEADER,
    GUEST_GRANT_HEADER,
    SURFACE_RING_HEADER,
    ExternalSubjectKind,
    SurfaceRing,
    issue_scoped_surface_grant,
)
from zcg.web.http.request import Message, Scope


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
        """Verify persona-profile stays private while venture spins out and pub-persona is pro."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        persona_profile = tmp_path / "persona-profile"
        persona_work = tmp_path / "persona-work"
        micro_saas = tmp_path / "micro-saas"
        pub_persona = tmp_path / "pub-persona"

        # Act — 1. Bootstrap private persona-profile & persona-work and spinout venture/*
        _run_zcg(
            REPO_DIR, "bootstrap", str(persona_profile), "--id", "persona-profile",
            "--role", "workstation", "--entity-kind", "individual", "--precedence", "90",
        )  # fmt: skip
        _run_zcg(
            REPO_DIR, "bootstrap", str(persona_work), "--id", "persona-work",
            "--role", "department", "--entity-kind", "individual",
            "--governing-root", "persona-profile", "--precedence", "87",
        )  # fmt: skip
        subprocess.run(
            ["git", "init", "-b", "master"], cwd=persona_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "persona@example.org"], cwd=persona_work, check=True
        )
        subprocess.run(["git", "config", "user.name", "Operator"], cwd=persona_work, check=True)
        subprocess.run(["git", "add", "."], cwd=persona_work, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=persona_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "venture/micro-saas"],
            cwd=persona_work, check=True, capture_output=True,
        )  # fmt: skip
        (persona_work / "app.py").write_text("READY = True\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=persona_work, check=True)
        subprocess.run(
            ["git", "commit", "-m", "mvp"], cwd=persona_work, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "master"], cwd=persona_work, check=True, capture_output=True
        )

        spin_res = _run_zcg(
            REPO_DIR, "spinout-project", str(micro_saas),
            "--source-dir", str(persona_work),
            "--id", "micro-saas", "--from-branch", "venture/micro-saas",
        )  # fmt: skip

        # 2. Bootstrap pub-persona Sovereign Twin governed by persona-profile & activate in pro
        _run_zcg(
            REPO_DIR, "bootstrap", str(pub_persona), "--id", "pub-persona",
            "--role", "knowledge", "--governing-root", "persona-profile",
        )  # fmt: skip
        pub_m_path = pub_persona / NODE_MANIFEST_REL_PATH
        pub_m = json.loads(pub_m_path.read_text(encoding="utf-8"))
        pub_m["visibility"] = "public"
        pub_m["public_url"] = "https://github.com/persona-example/pub-persona.git"
        pub_m_path.write_text(json.dumps(pub_m, indent=2) + "\n", encoding="utf-8")
        (pub_persona / "WORKTASK.md").write_text("# Tasks\n- [x] Ready\n", encoding="utf-8")
        (pub_persona / "WORKVALI.md").write_text("# Validation\n- [x] Verified\n", encoding="utf-8")
        (pub_persona / "CHANGELOG.md").write_text(
            "# Changelog\n## [Unreleased]\n", encoding="utf-8"
        )

        pub_act = _run_zcg(
            REPO_DIR, "apply-project", str(pub_persona),
            "--template", "knowledge-stewardship-portal",
            "--service-action", "activate", "--env", "pro",
        )  # fmt: skip
        profile_id = resolve_node_entity_identity(persona_profile)
        pub_id = resolve_node_entity_identity(pub_persona)
        proj_m = json.loads((micro_saas / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8"))
        pub_app = create_node_cockpit_asgi_app(pub_persona)
        pub_dash = asyncio.run(_asgi_req(pub_app, "GET", "/dashboard"))

        # Assert
        assert spin_res["project_id"] == "micro-saas"
        assert proj_m["layer_role"] == "project"
        assert proj_m["precedence"] == 80
        assert (micro_saas / "app.py").is_file()
        assert profile_id["visibility"] == "private"
        assert pub_id["entity_kind"] == "individual"
        assert pub_id["visibility"] == "public"
        assert pub_id["public_node_identity"]["bridge_mode"] == "private-to-public-twin"
        assert pub_id["public_node_identity"]["canonical_domain"] == "pub-persona.knowledge.local"
        pub_svc = pub_act["services"][0]
        assert (
            pub_svc["intranet_topology"]["environment_reachability"]["pro"] == "public-remote-live"
        )
        assert (
            pub_svc["intranet_topology"]["active_subdomain_url"]
            == "https://pub-persona.knowledge.local"
        )
        assert (
            pub_svc["intranet_topology"]["remote_production_url"]
            == "https://github.com/persona-example/pub-persona.git"
        )
        assert pub_dash[0] == 200 and b"knowledge-stewardship-portal" in pub_dash[1]

    def test_governed_portal_r0_to_r3_rings_keyless_cloud_deploy_and_cdn_sri_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify R0..R3 rings, SHA-256 plugin pinning, cloud_deployment_pro.json, and CDN SRI."""
        # Arrange
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        root_ws = tmp_path / "corp-iso-root"
        portal_ws = tmp_path / "org-iso"
        tpl_dir = REPO_DIR / "templates/plugin-stack/knowledge-stewardship-portal"
        tpl_sha = compute_template_pack_sha256(tpl_dir)
        sri_hash = compute_sri_sha384(b"export const portal = 1;")
        _run_zcg(
            REPO_DIR, "bootstrap", str(root_ws), "--id", "corp-iso-root",
            "--role", "corporate", "--precedence", "10",
        )  # fmt: skip
        root_m = json.loads((root_ws / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8"))
        root_m["domain_governance"] = {
            "canonical_domain": "iso.example",
            "intranet_zone": "intranet.iso.example",
        }
        root_m["capability_policy"] = {
            "plugin_policy": "curated-allowlist",
            "allowed_plugins": ["knowledge-stewardship-portal"],
            "allowed_plugin_digests": {"knowledge-stewardship-portal": f"sha256:{tpl_sha}"},
        }
        root_m["network_egress_policy"] = {
            "allowed_domains": ["*.iso.example", "*.pkg.dev"],
            "enable_canonical_cdn": True,
            "artifact_mirrors": {
                "container_registry": "europe-west1-docker.pkg.dev/iso-corp/containers",
                "pypi_index_url": "https://europe-west1-python.pkg.dev/iso-corp/pypi/simple",
                "require_private_mirrors": True,
            },
        }
        (root_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(root_m, indent=2) + "\n", "utf-8")

        _run_zcg(
            REPO_DIR, "bootstrap", str(portal_ws), "--id", "org-iso",
            "--role", "knowledge", "--governing-root", "corp-iso-root", "--precedence", "20",
        )  # fmt: skip
        portal_m = json.loads((portal_ws / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8"))
        portal_m["visibility"] = "public"
        portal_m["domain_governance"] = {
            "canonical_domain": "iso.example",
            "dns_publication": "public-authoritative",
        }
        portal_m["network_egress_policy"] = {
            "allowed_domains": ["*.iso.example", "*.pkg.dev"],
            "enable_canonical_cdn": True,
            "artifact_mirrors": {
                "pypi_index_url": "https://europe-west1-python.pkg.dev/iso-corp/pypi/simple",
            },
        }
        portal_m["cloud_deployment"] = {
            "project_id": "iso-cloud-01",
            "workload_identity_provider": "projects/100/locations/global/workloadIdentityPools/p1",
            "service_account_email": "portal@iso-cloud-01.iam.gserviceaccount.com",
        }
        portal_m["surface_access"] = {
            "default_ring": "public",
            "session_key": "e2e-portal-session-key",
            "route_rules": [
                {
                    "path_pattern": "/api/modules/crud*",
                    "ring": "scoped-external",
                    "disclosure_tier": "verified_competency",
                }
            ],
        }
        (portal_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(portal_m, indent=2) + "\n", "utf-8"
        )
        (portal_ws / "WORKTASK.md").write_text("# Tasks\n- [x] Ready\n", encoding="utf-8")
        (portal_ws / "WORKVALI.md").write_text("# Validation\n- [x] Ready\n", encoding="utf-8")
        (portal_ws / "CHANGELOG.md").write_text("# Changelog\n## [Unreleased]\n", encoding="utf-8")

        # Act
        _run_zcg(
            REPO_DIR, "apply-project", str(portal_ws), "--parent-dir", str(root_ws),
            "--template", "knowledge-stewardship-portal",
            "--service-action", "deploy", "--env", "pro",
        )  # fmt: skip
        cloud_doc = json.loads(
            (portal_ws / "surfaces/infra/cloud_deployment_pro.json").read_text(encoding="utf-8")
        )
        app = create_node_cockpit_asgi_app(portal_ws)
        guest_tok = issue_scoped_surface_grant(
            signing_key="e2e-portal-session-key",
            subject_id="partner-guest",
            ring=SurfaceRing.R1_SCOPED_EXTERNAL,
            external_kind=ExternalSubjectKind.GUEST,
            allowed_routes=("/api/modules/crud*",),
        )

        async def _check() -> tuple[int, dict[str, str], int, int, dict[str, str]]:
            async def _req_h(
                path: str, hdrs: dict[str, str] | None = None
            ) -> tuple[int, dict[str, str]]:
                raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (hdrs or {}).items()]
                sent: list[Message] = []

                async def _rcv() -> Message:
                    return {"type": "http.request", "body": b"", "more_body": False}

                async def _snd(msg: Message) -> None:
                    sent.append(msg)

                await app(
                    {
                        "type": "http",
                        "method": "GET",
                        "path": path,
                        "query_string": b"",
                        "headers": raw_h,
                        "client": ("198.51.100.25", 53000),
                    },
                    _rcv,
                    _snd,
                )
                resp_h = {
                    bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
                    for k, v in sent[0].get("headers", [])
                }
                return int(sent[0]["status"]), resp_h

            st_pub, h_pub = await _req_h("/dashboard")
            st_401, _ = await _req_h("/api/modules/crud")
            st_r1, h_r1 = await _req_h("/api/modules/crud", {GUEST_GRANT_HEADER: guest_tok})
            return st_pub, h_pub, st_401, st_r1, h_r1

        st_pub, h_pub, st_401, st_r1, h_r1 = asyncio.run(_check())
        tool_doc = provision_isolated_tool_manifest(portal_ws, "gemini-decisions", active_env="pro")
        mcp_app = create_mcp_asgi_app(ZeroCloudMCPServer(repo_dir=portal_ws))
        mcp_st, mcp_raw = asyncio.run(
            _asgi_req(
                mcp_app, "POST", "/mcp", body=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
            )
        )
        cap = project_ring_scoped_capsule(
            resource_id="res-01",
            target_node_id="partner-guest",
            effective_disclosure_tier=h_r1[DISCLOSURE_TIER_HEADER],
            segments=(
                PayloadFieldSegment("summary", DisclosureTier.CORE_SUMMARY, "Public"),
                PayloadFieldSegment("proof", DisclosureTier.VERIFIED_COMPETENCY, "Verified"),
                PayloadFieldSegment("ssn", DisclosureTier.DAY1_ONBOARDING, "Redacted"),
            ),
        )

        # Assert
        assert sri_hash.startswith("sha384-")
        assert cloud_doc["fqdn"] == "iso.example"
        assert cloud_doc["egress_and_cdn"]["cdn_origins"] == ["https://cdn.iso.example"]
        assert cloud_doc["cloud_run"]["env"]["PIP_INDEX_URL"].endswith("/simple")
        assert st_pub == 200 and h_pub[SURFACE_RING_HEADER] == "R0"
        assert "https://cdn.iso.example" in h_pub["content-security-policy"]
        assert st_401 == 401 and st_r1 == 200
        assert h_r1[SURFACE_RING_HEADER] == "R1"
        assert cap.disclosed_fields == {"summary": "Public", "proof": "Verified"}
        assert "ssn" in cap.withheld_field_ids
        assert (portal_ws / SIDECAR_MANIFEST_REL_PATH).is_file()
        assert tool_doc["runtime_dir"] == ".zcg/tools/gemini-decisions"
        assert mcp_st == 200 and len(json.loads(mcp_raw)["result"]["tools"]) == 9
