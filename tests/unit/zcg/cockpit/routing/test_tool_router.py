"""Unit tests for zcg.cockpit.routing.tool_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from zcg.cockpit.routing.tool_router import create_tool_stack_router
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import Message, Scope


async def _call_asgi(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
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


class TestToolRouter:
    """1:1 unit suite for /api/tools Skill Trust Studio and isolated .zcg/tools/ endpoints."""

    def test_create_tool_stack_router_asgi_endpoints_and_decisions_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify /api/tools list, provisioning, sovereign SARIF, and decisions evaluation."""
        # Arrange
        ws = tmp_path / "ws"
        ws.mkdir()
        tok = f"tok-{tmp_path.name}"
        app = create_web_app(title="tools", csrf_token=tok, routers=(create_tool_stack_router(ws),))
        csrf_h = {"x-zcg-csrf-token": tok, "accept": "application/json"}
        csrf_hx = {"x-zcg-csrf-token": tok, "hx-request": "true"}
        custom_dec = json.dumps(
            {
                "offline_override": True,
                "items": [
                    {
                        "item_id": "m1",
                        "task_kind": "choice",
                        "use_case": "model-routing",
                        "prompt": "Pick tier",
                        "choices": ["flash", "pro"],
                        "prior_score": 0.85,
                    }
                ],
            }
        ).encode("utf-8")

        # Act
        async def _exercise() -> list[tuple[int, bytes]]:
            return [
                await _call_asgi(app, "GET", "/api/tools", headers={"accept": "application/json"}),
                await _call_asgi(
                    app, "POST", "/api/tools/gemini-decisions/provision", headers=csrf_h
                ),
                await _call_asgi(
                    app, "POST", "/api/tools/wallet-analytics/provision", headers=csrf_hx
                ),
                await _call_asgi(app, "GET", "/api/tools", headers={"hx-request": "true"}),
                await _call_asgi(
                    app,
                    "GET",
                    "/api/tools/gemini-decisions/inspect",
                    headers={"hx-request": "true"},
                ),
                await _call_asgi(
                    app,
                    "GET",
                    "/api/tools/missing-tool/inspect",
                    headers={"accept": "application/json"},
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/wallet-analytics/deprovision",
                    query="mode=tools",
                    headers=csrf_hx,
                ),
                await _call_asgi(
                    app, "POST", "/api/tools/missing-tool/deprovision", headers=csrf_h
                ),
                await _call_asgi(app, "POST", "/api/tools/missing-tool/provision", headers=csrf_h),
                await _call_asgi(app, "GET", "/api/tools/skill-auditor/sarif"),
                await _call_asgi(app, "POST", "/api/tools/decisions/evaluate"),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/decisions/evaluate",
                    headers={"content-type": "application/json"},
                    body=custom_dec,
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/decisions/evaluate",
                    headers={"content-type": "application/json"},
                    body=b"[1, 2]",
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/decisions/evaluate",
                    headers={"content-type": "application/json"},
                    body=b'{"items": "not-a-list"}',
                ),
            ]

        (
            r_json,
            r_prov,
            r_prov_hx,
            r_hx,
            r_insp,
            r_insp_404,
            r_dep_hx,
            r_dep_404,
            r_404,
            r_sarif,
            r_dec_def,
            r_dec_c,
            r_bad_obj,
            r_bad_it,
        ) = asyncio.run(_exercise())

        # Assert
        list_doc = json.loads(r_json[1])
        tool_ids = {t["tool_id"] for t in list_doc["tools"]}
        assert "zcg-skill-auditor" in tool_ids and "wallet-analytics" in tool_ids
        assert r_json[0] == 200 and list_doc["skill_trust_score"] == 100
        assert list_doc["agent_guidance"]["profile_id"] == "personal-workstation"
        assert list_doc["agent_guidance"]["recommended_base_model"] == "Gemini 4 Neon (High)"
        assert r_prov[0] == 200 and json.loads(r_prov[1])["tool_id"] == "gemini-decisions"
        assert r_prov_hx[0] == 200 and b"Provisioned isolated tool runtime" in r_prov_hx[1]
        assert r_hx[0] == 200 and b"gemini-decisions</code> \xe2\x80\x94 ready" in r_hx[1]
        assert b"data-zcg-agent-guidance" in r_hx[1]
        assert b"Set-and-Forget Agent &amp; Automatic Swarm Policy" in r_hx[1]
        assert r_insp[0] == 200 and b"Offline LiteRT" in r_insp[1]
        assert r_insp_404[0] == 404 and r_dep_404[0] == 404
        assert r_dep_hx[0] == 200 and b"Disabled tool" in r_dep_hx[1]
        assert b"data-zcg-agent-guidance" not in r_dep_hx[1]
        assert b"Node Skills &amp; Inherited Capabilities" in r_hx[1]
        assert b"Select <strong>View</strong>" in r_hx[1] and b"<textarea" not in r_hx[1]
        assert b"Re-Provision" in r_hx[1] and b"zcg-tools-panel" in r_hx[1]
        assert r_404[0] == 404 and b"TOOL_NOT_FOUND" in r_404[1]
        sarif_doc = json.loads(r_sarif[1])
        assert r_sarif[0] == 200 and sarif_doc["sarif"]["version"] == "2.1.0"
        assert sarif_doc["sarif"]["runs"][0]["tool"]["driver"]["name"] == "zcg-skill-auditor"
        assert r_dec_def[0] == 200 and json.loads(r_dec_def[1])["item_count"] == 1
        assert r_dec_c[0] == 200
        assert json.loads(r_dec_c[1])["results"][0]["selected_choice"] == "pro"
        assert r_bad_obj[0] == 400 and b"INVALID_DECISIONS_PAYLOAD" in r_bad_obj[1]
        assert r_bad_it[0] == 400 and b"INVALID_DECISION_REQUEST" in r_bad_it[1]

    def test_skills_studio_save_select_commit_and_conflict_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Two-World skill save, selection HTML, scoped C3 commit, and 400/409/422 guards."""
        # Arrange
        ws = tmp_path / "tutor-iso"
        ws.mkdir()
        subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True
        )
        (ws / "README.md").write_text("# Init\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)
        (ws / ".agents/skills/sopen").mkdir(parents=True)
        (ws / ".agents/skills/sopen/SKILL.md").write_text(
            "---\nname: sopen\ndescription: Open session cleanly.\n---\n# Sopen\n",
            encoding="utf-8",
        )
        tok = f"tok-{tmp_path.name}"
        app = create_web_app(title="tools", csrf_token=tok, routers=(create_tool_stack_router(ws),))
        valid_sk = (
            "---\nname: drill-check\n"
            "description: Verify algebraic derivation steps deterministically.\n---\n# Drill\n"
        )
        csrf_h = {"x-zcg-csrf-token": tok}
        form_h = {**csrf_h, "content-type": "application/x-www-form-urlencoded"}
        json_h = {**csrf_h, "content-type": "application/json"}

        # Act
        async def _run() -> list[tuple[int, bytes]]:
            p_save = "/api/tools/skills/save"
            p_com = "/api/tools/skills/commit"
            p_del = "/api/tools/skills/delete"
            hx = {"hx-request": "true"}
            return [
                await _call_asgi(
                    app,
                    "POST",
                    p_save,
                    headers=form_h,
                    body=urlencode({"skill_slug": "drill-check", "content": valid_sk}).encode(),
                ),
                await _call_asgi(app, "GET", "/api/tools", query="action=new", headers=hx),
                await _call_asgi(
                    app, "GET", "/api/tools", query="skill=sopen&action=view", headers=hx
                ),
                await _call_asgi(
                    app, "GET", "/api/tools", query="skill=sopen&action=duplicate", headers=hx
                ),
                await _call_asgi(
                    app, "GET", "/api/tools", query="skill=drill-check&action=edit", headers=hx
                ),
                await _call_asgi(
                    app,
                    "POST",
                    p_save,
                    headers=json_h,
                    body=json.dumps(
                        {"skill_slug": "drill-check", "content": valid_sk, "expected_sha256": "bad"}
                    ).encode(),
                ),
                await _call_asgi(app, "POST", p_save, headers=csrf_h),
                await _call_asgi(app, "POST", p_save, headers=json_h, body=b"[1]"),
                await _call_asgi(
                    app,
                    "POST",
                    p_com,
                    headers=json_h,
                    body=json.dumps(
                        {"skill_slug": "drill-check", "commit_message": "feat(skills): add drill"}
                    ).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    p_com,
                    headers=json_h,
                    body=json.dumps(
                        {"skill_slug": "drill-check", "commit_message": "feat(skills): repeat"}
                    ).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    p_com,
                    headers=json_h,
                    body=b'{"skill_slug": "drill-check", "commit_message": "bad"}',
                ),
                await _call_asgi(
                    app,
                    "POST",
                    p_del,
                    headers={**form_h, **hx},
                    body=urlencode({"skill_slug": "drill-check", "mode": "skills"}).encode(),
                ),
                await _call_asgi(
                    app, "POST", p_del, headers=json_h, body=b'{"skill_slug":"sopen"}'
                ),
            ]

        (
            r_save,
            r_new,
            r_view,
            r_dup,
            r_sel,
            r_409,
            r_422,
            r_400,
            r_com,
            r_c409,
            r_c422,
            r_del,
            r_del_422,
        ) = asyncio.run(_run())

        # Assert
        assert r_save[0] == 200 and json.loads(r_save[1])["slug"] == "drill-check"
        assert r_new[0] == 200 and b"+ Create New Node Skill" in r_new[1]
        assert b"custom-node-skill" in r_new[1] and b"Commit Saved Skill" not in r_new[1]
        assert r_view[0] == 200 and b"Viewing Read-Only Skill" in r_view[1]
        assert b"Duplicate as Node Skill" in r_view[1] and b"<textarea" not in r_view[1]
        assert r_dup[0] == 200 and b"Duplicate as Node Skill" in r_dup[1]
        assert b"name: tutor-iso-sopen" in r_dup[1] and b"<textarea" in r_dup[1]
        assert r_sel[0] == 200 and b"Node-Owned" in r_sel[1] and b"Core / Stack" in r_sel[1]
        assert b"Editing Node Skill" in r_sel[1] and b"Commit Saved Skill" in r_sel[1]
        assert r_409[0] == 409 and r_422[0] == 422 and r_400[0] == 400
        assert r_com[0] == 200 and len(json.loads(r_com[1])["commit_sha"]) >= 7
        assert r_c409[0] == 409 and r_c422[0] == 422
        assert r_del[0] == 200 and b"Deleted node skill" in r_del[1]
        assert b"data-zcg-agent-guidance" in r_del[1]
        assert r_del_422[0] == 422

    def test_list_tools_resolves_manifest_agent_guidance_expected(self, tmp_path: Path) -> None:
        """Verify GET /api/tools resolves manifest profile into JSON and skills-mode HTML."""
        # Arrange
        ws = tmp_path / "engine-iso"
        (ws / "system").mkdir(parents=True)
        (ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "engine-iso", "layer_role": "engine"}), encoding="utf-8"
        )
        tok = f"tok-{tmp_path.name}"
        app = create_web_app(title="tools", csrf_token=tok, routers=(create_tool_stack_router(ws),))

        # Act
        async def _fetch() -> list[tuple[int, bytes]]:
            return [
                await _call_asgi(app, "GET", "/api/tools", headers={"accept": "application/json"}),
                await _call_asgi(
                    app,
                    "GET",
                    "/api/tools",
                    query="mode=skills",
                    headers={"hx-request": "true"},
                ),
                await _call_asgi(
                    app,
                    "GET",
                    "/api/tools",
                    query="mode=tools",
                    headers={"hx-request": "true"},
                ),
            ]

        r_json, r_skills, r_tools = asyncio.run(_fetch())

        # Assert
        doc = json.loads(r_json[1])
        assert r_json[0] == 200
        assert doc["agent_guidance"]["profile_id"] == "software-engineering"
        assert doc["agent_guidance"]["recommended_base_model"] == "Gemini 4 Carbon (High)"
        assert r_skills[0] == 200 and b"data-zcg-agent-guidance" in r_skills[1]
        assert b"Gemini 4 Carbon (High)" in r_skills[1]
        assert r_tools[0] == 200 and b"data-zcg-agent-guidance" not in r_tools[1]

    def test_skills_draft_discard_and_atomic_commit_now_expected(self, tmp_path: Path) -> None:
        """Verify /skills/draft, /skills/draft/discard, and /skills/save with commit_now=1."""
        # Arrange
        ws = tmp_path / "skill-draft-iso"
        ws.mkdir()
        subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True
        )
        (ws / "README.md").write_text("# Init\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)
        tok = f"tok-{tmp_path.name}"
        app = create_web_app(title="tools", csrf_token=tok, routers=(create_tool_stack_router(ws),))
        sk_v1 = "---\nname: check-law\ndescription: Verify law deterministically.\n---\n# V1\n"
        sk_v2 = "---\nname: check-law\ndescription: Verify law deterministically.\n---\n# V2\n"
        json_h = {"x-zcg-csrf-token": tok, "content-type": "application/json"}
        form_h = {
            "x-zcg-csrf-token": tok,
            "hx-request": "true",
            "content-type": "application/x-www-form-urlencoded",
        }

        # Act
        async def _run() -> list[tuple[int, bytes]]:
            return [
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/skills/draft",
                    headers=json_h,
                    body=json.dumps({"draft_key": "skill:check-law", "content": sk_v1}).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/skills/draft",
                    headers=json_h,
                    body=b'{"draft_key": "", "content": ""}',
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/skills/draft/discard",
                    headers=form_h,
                    body=urlencode({"draft_key": "skill:check-law", "action": "new"}).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/skills/save",
                    headers=form_h,
                    body=urlencode(
                        {
                            "skill_slug": "check-law",
                            "content": sk_v1,
                            "commit_now": "1",
                            "commit_message": "feat(skills): atomic check-law",
                        }
                    ).encode(),
                ),
                await _call_asgi(
                    app,
                    "POST",
                    "/api/tools/skills/save",
                    headers=form_h,
                    body=urlencode(
                        {
                            "skill_slug": "check-law",
                            "content": sk_v2,
                            "commit_now": "1",
                            "commit_message": "bad message",
                        }
                    ).encode(),
                ),
            ]

        r_dr, r_dr_422, r_disc, r_atom, r_bad_com = asyncio.run(_run())

        # Assert
        assert r_dr[0] == 200 and json.loads(r_dr[1])["saved"] is True
        assert r_dr_422[0] == 422
        assert r_disc[0] == 200 and b"Discarded unapplied draft." in r_disc[1]
        assert r_atom[0] == 200 and b"and committed <code>" in r_atom[1]
        assert r_bad_com[0] == 422
