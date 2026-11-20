"""End-to-end journeys for mesh governance policies, scope lens, quick-add routing, and docs drafts.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zcg.cli.dispatcher import dispatch_zcg_cli
from zcg.cockpit.ops.asgi import create_node_cockpit_asgi_app
from zcg.core.constants import REPO_DIR
from zcg.governance.work.work_inbox import inspect_work_inbox
from zcg.web.auth.security import CSRF_HEADER
from zcg.web.http.request import Message, Scope


def _run_zcg(subcmd: str, *args: str, repo_dir: Path = REPO_DIR) -> dict[str, object]:
    code, payload, err = dispatch_zcg_cli(repo_dir, False, subcmd, list(args))
    assert code == 0, f"zcg {subcmd} {args} failed ({code}): {err}"
    assert payload is not None
    return payload


def _init_git_repo(repo_dir: Path) -> str:
    git_bin = shutil.which("git") or "/usr/bin/git"
    for args in (
        ["init", "-b", "master"],
        ["config", "user.email", "iso@example.org"],
        ["config", "user.name", "ISO Operator"],
        ["add", "."],
        ["commit", "-m", "chore: initial bootstrap"],
    ):
        subprocess.run([git_bin, "-C", str(repo_dir), *args], check=True, capture_output=True)
    return git_bin


async def _asgi_req(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": list(headers or ()),
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


class TestMeshAndDraftJourneys:
    """Verify live ASGI mesh policies, Scope Lens, cross-node Quick-Add, and docs drafts."""

    def test_mesh_policy_scope_lens_quick_add_and_docs_draft_commit_journey_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify mesh policy toggle, ws_scope lens, exchange_target routing, and doc save."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        monkeypatch.setenv("ZCG_NO_DAEMON", "1")
        root_dir = tmp_path / "corp-iso-root"
        eng_dir = root_dir / "layers/dept-eng"
        ops_dir = root_dir / "layers/dept-ops"

        _run_zcg(
            "bootstrap",
            str(root_dir),
            "--id",
            "corp-iso-root",
            "--purpose",
            "enterprise-network",
        )
        _run_zcg(
            "bootstrap",
            str(eng_dir),
            "--id",
            "dept-eng",
            "--purpose",
            "enterprise-network",
            "--role",
            "department",
            "--parent-dir",
            str(root_dir),
        )
        _run_zcg(
            "bootstrap",
            str(ops_dir),
            "--id",
            "dept-ops",
            "--purpose",
            "enterprise-network",
            "--role",
            "department",
            "--parent-dir",
            str(root_dir),
        )
        _run_zcg("register-subtree", "dept-eng", "", repo_dir=root_dir)
        _run_zcg("register-subtree", "dept-ops", "", repo_dir=root_dir)

        for nd in (root_dir, eng_dir, ops_dir):
            (nd / "README.md").write_text(f"# {nd.name}\n\nConfigured node.\n", encoding="utf-8")
            (nd / "WORKTASK.md").write_text(
                f"# Active Work Tasks — {nd.name}\n\n"
                "- [x] Complete `Layer Setup Blueprint`.\n"
                "- [ ] Own local audit task.\n",
                encoding="utf-8",
            )
        git_bin = _init_git_repo(eng_dir)

        # Act
        async def _drive_asgi_journey() -> dict[str, Any]:
            csrf_tok = "iso-e2e-csrf-token"
            app_root = create_node_cockpit_asgi_app(root_dir, csrf_token=csrf_tok)
            app_eng = create_node_cockpit_asgi_app(eng_dir, csrf_token=csrf_tok)
            json_hdr = [
                (b"content-type", b"application/json"),
                (CSRF_HEADER.encode("ascii"), csrf_tok.encode("ascii")),
            ]
            hx_hdr = [(b"hx-request", b"true")]

            # (a) Switch Root 0 mesh policy to hierarchical-only, confirm lateral block, then curate
            st_hier, b_hier = await _asgi_req(
                app_root,
                "POST",
                "/api/modules/node-mesh/policy",
                headers=json_hdr,
                body=json.dumps({"topology_mode": "hierarchical-only"}).encode("utf-8"),
            )
            st_blocked, b_blocked = await _asgi_req(
                app_eng,
                "POST",
                "/api/modules/work-ledger/tasks",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "action": "add",
                        "tracker": "WORKTASK.md",
                        "task_text": "Blocked lateral request",
                        "exchange_target": "dept-ops",
                    }
                ).encode("utf-8"),
            )
            st_cur, b_cur = await _asgi_req(
                app_root,
                "POST",
                "/api/modules/node-mesh/policy",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "topology_mode": "curated-matrix",
                        "action_kind": "add_channel",
                        "source": "dept-eng",
                        "target": "dept-ops",
                        "verbs": ["consult_context", "propose_work"],
                        "reciprocal": True,
                    }
                ).encode("utf-8"),
            )

            # (b) Workspace Scope Lens rendering across node, network, and corpora
            st_sc_node, b_sc_node = await _asgi_req(app_eng, "GET", "/", query="ws_scope=node")
            st_sc_net, b_sc_net = await _asgi_req(app_eng, "GET", "/", query="ws_scope=network")
            st_sc_corp, b_sc_corp = await _asgi_req(app_eng, "GET", "/", query="ws_scope=corpora")

            # (c) Quick-Add exchange_target cross-node task routing (lateral + downward)
            st_peer_tx, b_peer_tx = await _asgi_req(
                app_eng,
                "POST",
                "/api/modules/work-ledger/tasks",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "action": "add",
                        "tracker": "WORKTASK.md",
                        "task_text": "Sync telemetry schema across ops",
                        "exchange_target": "dept-ops",
                    }
                ).encode("utf-8"),
            )
            st_root_tx, b_root_tx = await _asgi_req(
                app_root,
                "POST",
                "/api/modules/work-ledger/tasks",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "action": "add",
                        "tracker": "WORKTASK.md",
                        "task_text": "Enforce quarterly SLA review",
                        "exchange_target": "dept-eng",
                    }
                ).encode("utf-8"),
            )

            # (d) Auto-draft persistence + reload + atomic save with commit_now="1"
            st_draft, b_draft = await _asgi_req(
                app_eng,
                "POST",
                "/api/modules/docs-reader/draft",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "draft_key": "doc:new",
                        "rel_path": "docs/guides/ops_runbook.md",
                        "content": "# Ops Runbook Draft\n\nPending validation.\n",
                    }
                ).encode("utf-8"),
            )
            st_new_ed, b_new_ed = await _asgi_req(
                app_eng,
                "GET",
                "/api/modules/docs-reader",
                query="action=new",
                headers=hx_hdr,
            )
            st_save, b_save = await _asgi_req(
                app_eng,
                "POST",
                "/api/modules/docs-reader/save",
                headers=json_hdr,
                body=json.dumps(
                    {
                        "rel_path": "docs/guides/ops_runbook.md",
                        "content": "# Ops Runbook\n\nVerified production runbook.\n",
                        "commit_now": "1",
                        "commit_message": "docs(guides): publish ops runbook",
                    }
                ).encode("utf-8"),
            )
            return {
                "hier": (st_hier, json.loads(b_hier)),
                "blocked": (st_blocked, b_blocked),
                "curated": (st_cur, json.loads(b_cur)),
                "scopes": ((st_sc_node, b_sc_node), (st_sc_net, b_sc_net), (st_sc_corp, b_sc_corp)),
                "peer_tx": (st_peer_tx, json.loads(b_peer_tx)),
                "root_tx": (st_root_tx, json.loads(b_root_tx)),
                "draft": (st_draft, json.loads(b_draft)),
                "new_ed": (st_new_ed, b_new_ed),
                "save": (st_save, json.loads(b_save)),
            }

        out = asyncio.run(_drive_asgi_journey())
        ops_inbox = inspect_work_inbox(ops_dir)
        git_subject = subprocess.run(
            [git_bin, "-C", str(eng_dir), "log", "-1", "--pretty=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Assert
        assert out["hier"][0] == 200 and out["hier"][1]["topology_mode"] == "hierarchical-only"
        assert out["blocked"][0] == 403 and b"MESH_RELATION_FORBIDDEN" in out["blocked"][1]
        assert out["curated"][0] == 200
        assert out["curated"][1]["topology_mode"] == "curated-matrix"
        assert out["curated"][1]["channel_count"] == 1

        (st_n, html_n), (st_net, html_net), (st_c, html_c) = out["scopes"]
        assert st_n == 200 and b"data-zcg-ws-scope='node'" in html_n
        assert st_net == 200 and b"data-zcg-ws-scope='network'" in html_net
        assert st_c == 200 and b"data-zcg-ws-scope='corpora'" in html_c
        assert b"Browse Connected Corpora" in html_c

        assert out["peer_tx"][0] == 200 and out["peer_tx"][1]["target_node"] == "dept-ops"
        assert any("Sync telemetry schema across ops" in it["summary"] for it in ops_inbox["items"])
        assert out["root_tx"][0] == 200
        assert "Enforce quarterly SLA review" in (eng_dir / "WORKTASK.md").read_text("utf-8")

        assert out["draft"][0] == 200 and out["draft"][1]["line_count"] == 3
        assert out["new_ed"][0] == 200 and b"Ops Runbook Draft" in out["new_ed"][1]
        assert out["save"][0] == 200 and out["save"][1]["doc"] == "docs/guides/ops_runbook.md"
        assert (eng_dir / "docs/guides/ops_runbook.md").is_file()
        assert not list((eng_dir / ".zcg/runtime/md_drafts").glob("*.json"))
        assert git_subject == "docs(guides): publish ops runbook"

    def test_runtime_updates_studio_one_hop_law_and_pure_local_onboarding_journey_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify /admin runtime tab, 1-Hop Upgrade Law warning, and pure-local Day-0 onboarding."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        monkeypatch.setenv("ZCG_NO_DAEMON", "1")
        parent_dir = tmp_path / "corp-parent"
        child_dir = parent_dir / "layers/dept-child"

        _run_zcg(
            "bootstrap",
            str(parent_dir),
            "--id",
            "corp-parent",
            "--purpose",
            "enterprise-network",
        )
        _run_zcg(
            "bootstrap",
            str(child_dir),
            "--id",
            "dept-child",
            "--purpose",
            "enterprise-network",
            "--role",
            "department",
            "--parent-dir",
            str(parent_dir),
        )
        for nd, ver in ((parent_dir, "0.9.0"), (child_dir, "0.8.0")):
            m_path = nd / "system/zcg-node.json"
            m_doc = json.loads(m_path.read_text(encoding="utf-8"))
            m_doc["engine_version"] = ver
            m_path.write_text(json.dumps(m_doc, indent=2) + "\n", encoding="utf-8")

        # Act
        async def _drive_runtime() -> dict[str, tuple[int, bytes]]:
            csrf_tok = f"iso-e2e-rt-{child_dir.name}"
            app_parent = create_node_cockpit_asgi_app(parent_dir, csrf_token=csrf_tok)
            app_child = create_node_cockpit_asgi_app(child_dir, csrf_token=csrf_tok)
            json_hdr = [
                (b"content-type", b"application/json"),
                (CSRF_HEADER.encode("ascii"), csrf_tok.encode("ascii")),
            ]
            hx_post_hdr = [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (CSRF_HEADER.encode("ascii"), csrf_tok.encode("ascii")),
                (b"hx-request", b"true"),
            ]
            return {
                "day0": await _asgi_req(app_child, "GET", "/"),
                "admin": await _asgi_req(app_child, "GET", "/admin"),
                "rt_html": await _asgi_req(
                    app_child,
                    "GET",
                    "/api/modules/runtime",
                    headers=[(b"hx-request", b"true")],
                ),
                "rt_json": await _asgi_req(app_child, "GET", "/api/modules/runtime"),
                "act_ok": await _asgi_req(
                    app_parent,
                    "POST",
                    "/api/modules/node-mesh/activate",
                    headers=json_hdr,
                    body=json.dumps({"target_id": "dept-child"}).encode("utf-8"),
                ),
                "act_hx": await _asgi_req(
                    app_parent,
                    "POST",
                    "/api/modules/node-mesh/activate",
                    headers=hx_post_hdr,
                    body=b"target_id=dept-child",
                ),
                "act_404": await _asgi_req(
                    app_parent,
                    "POST",
                    "/api/modules/node-mesh/activate",
                    headers=json_hdr,
                    body=json.dumps({"target_id": "dept-unknown"}).encode("utf-8"),
                ),
            }

        out = asyncio.run(_drive_runtime())
        rt_payload = json.loads(out["rt_json"][1])
        act_payload = json.loads(out["act_ok"][1])

        # Assert
        assert out["day0"][0] == 200
        assert b"data-island='draft-studio'" in out["day0"][1]
        assert b"Remote Chrome" not in out["day0"][1]
        assert out["admin"][0] == 200
        assert b'data-admin-tab="runtime"' in out["admin"][1]
        assert b'data-admin-fetch="/api/modules/runtime"' in out["admin"][1]
        assert out["rt_html"][0] == 200
        assert b"Local Antigravity Environment" in out["rt_html"][1]
        assert b"ZeroCloudGravity 1-Hop Node Update" in out["rt_html"][1]
        assert b"1-Hop Upgrade Law" in out["rt_html"][1]
        assert b"Open Parent Runtime &amp; Updates" in out["rt_html"][1]
        assert out["rt_json"][0] == 200
        assert rt_payload["update_plan"]["update_source_kind"] == "governing-parent"
        assert rt_payload["update_plan"]["parent_update_required_first"] is True
        assert out["act_ok"][0] == 200
        assert act_payload["capability"] == "node_mesh_activate"
        assert act_payload["activated_node_id"] == "dept-child"
        assert act_payload["workspace_dir"] == str(child_dir.resolve())
        assert (child_dir / "surfaces/web/index.html").is_file()
        assert out["act_hx"][0] == 200 and b"Activated <code>dept-child</code>" in out["act_hx"][1]
        assert b"Open Workspace" in out["act_hx"][1]
        assert out["act_404"][0] == 404 and b"TARGET_WORKSPACE_NOT_FOUND" in out["act_404"][1]
