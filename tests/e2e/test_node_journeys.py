"""End-to-end persona journeys across enterprise hierarchies, study labs, and zcg-mcp stdio.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zcg.capsules.citations import verify_epistemic_context_claims
from zcg.cli.dispatcher import dispatch_zcg_cli
from zcg.cockpit.asgi import create_node_cockpit_asgi_app
from zcg.core.constants import REPO_DIR
from zcg.mcp.server import ZeroCloudMCPServer, run_stdio_loop
from zcg.web.request import Message, Scope


def _run_zcg(subcmd: str, *args: str) -> dict[str, object]:
    code, payload, err = dispatch_zcg_cli(REPO_DIR, False, subcmd, list(args))
    assert code == 0, f"zcg {subcmd} {args} failed ({code}): {err}"
    assert payload is not None
    return payload


async def _asgi_req(
    app: Any, method: str, path: str, *, query: str = "", body: bytes = b""
) -> tuple[int, bytes]:
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": [],
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


class TestNodeJourneys:
    """Verify end-to-end Zero-Cloud Node workflows for Enterprise and Academic/MCP personas."""

    def test_enterprise_root_department_squad_work_ledger_journey_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Root 0 -> Department -> Squad bootstrap, 1-hop delegation, task, and promotion."""
        # Arrange
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        root_dir = tmp_path / "corp-iso-root"
        dept_dir = root_dir / "layers/dept-iso-eng"
        squad_dir = dept_dir / "layers/squad-iso-grid"

        # Act — 1. Bootstrap 3-tier corporate hierarchy
        root_boot = _run_zcg(
            "bootstrap", str(root_dir), "--id", "corp-iso-root", "--role", "corporate",
            "--entity-kind", "enterprise", "--templates", "business-base,corporate-operations",
        )  # fmt: skip
        dept_boot = _run_zcg(
            "bootstrap", str(dept_dir), "--id", "dept-iso-eng", "--role", "department",
            "--parent-dir", str(root_dir),
            "--templates", "science-base,software-engineering,google-cloud-iac",
        )  # fmt: skip
        squad_boot = _run_zcg(
            "bootstrap", str(squad_dir), "--id", "squad-iso-grid", "--role", "squad",
            "--parent-dir", str(dept_dir),
            "--templates", "science-base,scientific-methodology,google-cloud-iac",
        )  # fmt: skip

        # 2. Delegate 1-hop directive Root 0 -> Department -> Squad
        _run_zcg(
            "delegate-to-child", str(root_dir), "--to-child", "dept-iso-eng",
            "--ticket", "DIR-ISO-01", "--task", "Enforce Google Cloud Run IAM least privilege",
        )  # fmt: skip
        _run_zcg(
            "delegate-to-child", str(dept_dir), "--to-child", "squad-iso-grid",
            "--ticket", "DIR-ISO-02", "--task", "Provision BigQuery telemetry dataset contract",
        )  # fmt: skip

        # 3. Claim and complete task in Squad work ledger, promote rule 1-hop to Department, sync
        _run_zcg("start-task", str(squad_dir), "--task", "DIR-ISO-02")
        done_res = _run_zcg("complete-task", str(squad_dir), "--task", "DIR-ISO-02")
        prom_res = _run_zcg(
            "promote-from-project",
            str(squad_dir),
            "--source",
            ".agents/rules/squad-iso-grid.md",
            "--upstream-dir",
            str(dept_dir),
            "--to-template",
            "dept-iso-eng",
            "--force",
        )
        sync_res = _run_zcg("sync-layer", str(squad_dir), "--parent-dir", str(dept_dir))
        squad_status = _run_zcg("status", str(squad_dir), "--parent-dir", str(dept_dir))
        diff_res = _run_zcg("diff-project", str(squad_dir))

        # Assert
        assert root_boot["active_cockpit_url"] == "http://127.0.0.1:8710/?env=dev"
        assert dept_boot["layer_role"] == "department"
        assert squad_boot["active_cockpit_url"] == "http://127.0.0.1:8750/?env=dev"
        assert done_res["task_status"] == "completed"
        assert prom_res["target_template"] == "dept-iso-eng"
        assert sync_res["layer_id"] == "squad-iso-grid"
        ent = squad_status["entity_identity"]
        assert isinstance(ent, dict) and ent["governing_root_id"] == "corp-iso-root"
        assert diff_res["modified_in_project"] == [] and bool(diff_res["in_sync"])
        assert (squad_dir / "surfaces/web/index.html").is_file()

    def test_academic_tutor_lab_and_zcg_mcp_stdio_capsule_ephemeral_journey_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify personal tutor lab (--lang es) and full zcg-mcp stdio capsule + fork journey."""
        # Arrange
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        monkeypatch.setenv("ZCG_RESONANCE_KEY", "iso-test-resonance-secret-key")
        lab_dir = tmp_path / "neuro-iso-lab"

        _run_zcg(
            "bootstrap",
            str(lab_dir),
            "--id",
            "neuro-iso-lab",
            "--role",
            "department",
            "--precedence",
            "88",
            "--entity-kind",
            "individual",
            "--lang",
            "es",
            "--templates",
            "academic-base,academic-curriculum,sci-biology",
        )
        (lab_dir / "docs/architecture").mkdir(parents=True, exist_ok=True)
        (lab_dir / "docs/architecture/cortical_signal_spec.md").write_text(
            "# Cortical Signal Spec\n\n"
            "## Sampling Theorem Law [E3]\n\n"
            "**Mandate:** Nyquist rate must exceed 2000 Hz for motor unit telemetry.\n",
            encoding="utf-8",
        )

        # Act — Drive ZeroCloudMCPServer over JSON-RPC 2.0 stdio framing
        srv = ZeroCloudMCPServer(repo_dir=lab_dir, log_dir=lab_dir / "logs")
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_layer_overview", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "query_governance_rules",
                    "arguments": {
                        "query": "Nyquist",
                        "scope": "docs",
                        "resolution": "L1",
                        "min_epistemic_grade": "E3",
                    },
                },
            },
        ]
        in_stream = io.BytesIO(b"".join((json.dumps(r) + "\n").encode("utf-8") for r in requests))
        out_stream = io.BytesIO()
        run_stdio_loop(srv, stdin_buf=in_stream, stdout_buf=out_stream)
        responses = [
            json.loads(line)
            for line in out_stream.getvalue().decode("utf-8").splitlines()
            if line.strip()
        ]

        query_payload = json.loads(responses[3]["result"]["content"][0]["text"])
        first_match = query_payload["matches"][0]
        capsule_tok = first_match["capsule_token"]
        receipt = first_match["citation_receipt"]

        unfold_res = srv.call_tool(
            "unfold_context_capsule",
            {"capsule_token": capsule_tok, "target_level": "L3"},
        )
        unfolded = json.loads(unfold_res["content"][0]["text"])
        verified = verify_epistemic_context_claims(
            [
                {
                    "claim_id": "nyquist-law",
                    "epistemic_grade": "E3",
                    "citation_receipt": receipt,
                    "official_digest": str(receipt).rsplit("@", 1)[1].split(":", 1)[0],
                }
            ],
            lab_dir,
        )

        spawn_res = srv.call_tool(
            "orchestrate_ephemeral_fork",
            {"action": "spawn", "bot_role": "dept-specialist-bot", "one_shot": False},
        )
        spawned = json.loads(spawn_res["content"][0]["text"])
        fork_id = spawned["fork_id"]
        reap_res = srv.call_tool(
            "orchestrate_ephemeral_fork", {"action": "reap", "fork_id": fork_id}
        )
        reaped = json.loads(reap_res["content"][0]["text"])

        # Assert
        assert len(responses) == 4
        assert len(responses[1]["result"]["resources"]) == 9
        overview = json.loads(responses[2]["result"]["content"][0]["text"])
        ch1 = overview["channel_1_node_and_system_state"]
        assert ch1["entity_identity"]["public_node_identity"]["canonical_domain"].endswith(
            ".personal.local"
        )
        assert "2000 Hz" in unfolded["content"]["full_section"]
        assert verified["verified"] is True
        assert fork_id in reaped["reaped_forks"]

    def test_personal_sovereign_triad_links_spinout_and_five_vertical_cockpits_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Personal Triad (:8790/:8786/:8787), spinout, links, and V1..V5 ASGI cockpits."""
        # Arrange
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("ZCG_NO_BROWSER", "1")
        monkeypatch.setenv("ZCG_NO_DAEMON", "1")
        monkeypatch.setenv("ZCG_RESONANCE_KEY", "iso-triad-resonance-key")
        pc_dir = tmp_path / "alex-pc"
        tutor_dir = tmp_path / "alex-tutor"
        work_dir = tmp_path / "alex-work"
        org_dir = tmp_path / "org-alpha"
        sec_dir = tmp_path / "secops-alpha"
        spin_dir = tmp_path / "saas-spinout"
        git_bin = shutil.which("git") or "/usr/bin/git"

        _run_zcg(
            "bootstrap", str(pc_dir), "--id", "alex-pc", "--role", "workstation",
            "--precedence", "90", "--entity-kind", "individual", "--lang", "es",
            "--templates", "universal-base,workstation-control-tower",
        )  # fmt: skip
        _run_zcg(
            "bootstrap", str(tutor_dir), "--id", "alex-tutor", "--role", "department",
            "--precedence", "86", "--entity-kind", "individual", "--parent-dir", str(pc_dir),
            "--lang", "es", "--templates", "academic-base,academic-curriculum,tutor-study-cockpit",
        )  # fmt: skip
        _run_zcg(
            "bootstrap", str(work_dir), "--id", "alex-work", "--role", "department",
            "--precedence", "87", "--entity-kind", "individual", "--parent-dir", str(pc_dir),
            "--lang", "es", "--templates", "business-base,software-engineering,node-work-cockpit",
        )  # fmt: skip
        _run_zcg(
            "bootstrap", str(org_dir), "--id", "org-alpha", "--role", "knowledge",
            "--precedence", "20", "--templates", "business-base,corporate-operations",
        )  # fmt: skip
        _run_zcg(
            "bootstrap", str(sec_dir), "--id", "secops-alpha", "--role", "domain-policy",
            "--precedence", "5", "--templates", "nist-csf-security,secops-mcp-guardian",
        )  # fmt: skip

        (tutor_dir / "docs/guides").mkdir(parents=True, exist_ok=True)
        (tutor_dir / "docs/guides/01_spectral_mastery.md").write_text(
            "# Spectral Mastery\n\n## Self-Adjoint Axiom [E3]\n\n"
            "**Mandate:** Every Hermitian operator possesses real eigenvalues.\n",
            encoding="utf-8",
        )

        # Act — 1. Context branches (opportunity/*, venture/*, engagement/*) + spinout-project
        for args in (
            ["init", "-b", "master"],
            ["config", "user.email", "alex@personal.local"],
            ["config", "user.name", "Alex"],
            ["add", "."],
            ["commit", "-m", "chore: bootstrap alex-work"],
        ):
            subprocess.run([git_bin, "-C", str(work_dir), *args], check=True, capture_output=True)

        for branch_name, rel_doc, title in (
            ("opportunity/senior-platform-role", "docs/opportunity_brief.md", "Platform Role"),
            ("venture/autonomous-audit-saas", "docs/venture_mvp.md", "Autonomous Audit SaaS"),
            ("engagement/client-data-mesh", "docs/engagement_sow.md", "Client Data Mesh SOW"),
        ):
            subprocess.run(
                [git_bin, "-C", str(work_dir), "checkout", "-b", branch_name, "master"],
                check=True,
                capture_output=True,
            )
            doc_p = work_dir / rel_doc
            doc_p.parent.mkdir(parents=True, exist_ok=True)
            doc_p.write_text(f"# {title}\n", encoding="utf-8")
            subprocess.run([git_bin, "-C", str(work_dir), "add", rel_doc], check=True)
            subprocess.run(
                [git_bin, "-C", str(work_dir), "commit", "-m", f"feat: {branch_name}"],
                check=True,
                capture_output=True,
            )
        subprocess.run(
            [git_bin, "-C", str(work_dir), "checkout", "master"], check=True, capture_output=True
        )

        spin_res = _run_zcg(
            "spinout-project", str(spin_dir), "--source-dir", str(work_dir),
            "--from-branch", "venture/autonomous-audit-saas", "--id", "saas-spinout",
            "--packs", "business-base,software-engineering",
        )  # fmt: skip

        # 2. Bidirectional tutor <-> work links, HR & B2B links, and citation_receipt proof
        _run_zcg(
            "link", str(work_dir), "--target", "alex-tutor", "--relation", "knowledge-feed",
            "--ref", str(tutor_dir), "--packs", "academic-curriculum",
        )  # fmt: skip
        _run_zcg(
            "link", str(tutor_dir), "--target", "alex-work", "--relation", "knowledge-feed",
            "--ref", str(work_dir),
        )  # fmt: skip
        _run_zcg(
            "link", str(work_dir), "--target", "org-alpha", "--relation", "hr-process",
            "--ref", str(org_dir), "--packs", "corporate-operations",
        )  # fmt: skip
        _run_zcg(
            "apply-project", str(work_dir), "--template", "node-work-cockpit",
            "--service-action", "activate",
        )  # fmt: skip

        consult_res = _run_zcg(
            "consult-layer", str(work_dir), "--layer", "alex-tutor", "--query", "Hermitian"
        )
        tutor_mcp = ZeroCloudMCPServer(repo_dir=tutor_dir, log_dir=tutor_dir / "logs")
        q_raw = tutor_mcp.call_tool(
            "query_governance_rules",
            {
                "query": "Hermitian",
                "scope": "docs",
                "resolution": "L1",
                "min_epistemic_grade": "E3",
            },
        )
        receipt = json.loads(q_raw["content"][0]["text"])["matches"][0]["citation_receipt"]
        claim_ok = verify_epistemic_context_claims(
            [
                {
                    "claim_id": "tutor-work-proof",
                    "epistemic_grade": "E3",
                    "citation_receipt": receipt,
                    "official_digest": str(receipt).rsplit("@", 1)[1].split(":", 1)[0],
                }
            ],
            tutor_dir,
        )

        # 3. Validate composable multi-module Reference Dashboards end-to-end across the node fleet
        async def _verify_composable_dashboards() -> dict[str, Any]:
            app_tutor = create_node_cockpit_asgi_app(tutor_dir)
            app_pc = create_node_cockpit_asgi_app(pc_dir)
            app_work = create_node_cockpit_asgi_app(work_dir)
            app_spin = create_node_cockpit_asgi_app(spin_dir)
            app_sec = create_node_cockpit_asgi_app(sec_dir)
            app_org = create_node_cockpit_asgi_app(org_dir)

            _, h_tutor = await _asgi_req(app_tutor, "GET", "/")
            _, h_pc = await _asgi_req(app_pc, "GET", "/")
            _, h_work = await _asgi_req(app_work, "GET", "/")
            _, h_sec = await _asgi_req(app_sec, "GET", "/")
            _, h_org = await _asgi_req(app_org, "GET", "/")

            # Tutor combines crud (cards/list/table) + vault + node_mesh + telemetry
            st1, b1 = await _asgi_req(
                app_tutor, "POST", "/api/modules/crud", body=b'{"title":"Eigenvalue Drill"}'
            )
            st_l, b_l = await _asgi_req(app_tutor, "GET", "/api/modules/crud", query="view=list")
            st_f, b_f = await _asgi_req(
                app_tutor, "POST", "/api/modules/vault", body=b'{"filename":"sheet.md"}'
            )
            st2, b2 = await _asgi_req(app_pc, "GET", "/api/modules/telemetry")
            st3_c, b3_c = await _asgi_req(
                app_work, "GET", "/api/modules/role-projection", query="stage=candidate_application"
            )
            st3_d, b3_d = await _asgi_req(
                app_work, "GET", "/api/modules/role-projection", query="stage=day1_onboarding"
            )
            await _asgi_req(
                app_spin, "POST", "/api/modules/work-ledger/jobs", body=b'{"task_id":"j9"}'
            )
            st_p1, _ = await _asgi_req(app_spin, "GET", "/api/poll/status")
            await _asgi_req(
                app_spin, "POST", "/api/modules/work-ledger/jobs/j9/progress",
                body=b'{"progress":1.0}',
            )  # fmt: skip
            st_p2, _ = await _asgi_req(app_spin, "GET", "/api/poll/status")
            st4, b4 = await _asgi_req(
                app_sec, "POST", "/api/modules/telemetry/audit", body=b'{"rationale":"Gate OK"}'
            )
            st5, b5 = await _asgi_req(
                app_org, "POST", "/api/modules/data-pipeline",
                body=b'{"records":[{"id":"r1","code":"ISO-01","score":99.5}]}',
            )  # fmt: skip
            st_db, b_db = await _asgi_req(app_org, "GET", "/dashboard")
            st_css, b_css = await _asgi_req(app_org, "GET", "/static/css/plugin.css")
            return {
                "htmls": (h_tutor, h_pc, h_work, h_sec, h_org),
                "codes": (
                    st1, st_l, st_f, st2, st3_c, st3_d, st_p1, st_p2, st4, st5, st_db, st_css
                ),
                "cand": json.loads(b3_c)["capsule"], "day1": json.loads(b3_d)["capsule"],
                "crud": json.loads(b1), "crud_l": json.loads(b_l), "file": json.loads(b_f),
                "tel": json.loads(b2), "audit": json.loads(b4), "pipe": json.loads(b5),
                "dash": b_db, "css": b_css,
            }  # fmt: skip

        v_out = asyncio.run(_verify_composable_dashboards())

        # Assert
        assert (spin_dir / "docs/venture_mvp.md").is_file()
        assert spin_res["project_id"] == "saas-spinout"
        assert consult_res["target_layer"] == "alex-tutor" and consult_res["capsule_matches"]
        assert claim_ok["verified"] is True
        assert v_out["codes"] == (201, 200, 201, 200, 200, 200, 200, 286, 201, 200, 200, 200)
        assert b"knowledge-stewardship-portal" in v_out["dash"] and b"#2dd4bf" in v_out["css"]
        assert v_out["cand"]["withheld_field_ids"] == ["onboarding_identifier"]
        assert "onboarding_identifier" in v_out["day1"]["disclosed_fields"]
        assert v_out["crud"]["collection"] == "study-drills" and v_out["crud_l"]["layout"] == "list"
        assert v_out["file"]["capability"] == "vault"
        assert v_out["tel"]["capability"] == "telemetry"
        assert v_out["audit"]["integrity_verified"] is True
        assert v_out["pipe"]["batch_cdc_events"] == 1
        assert b"crud" in v_out["htmls"][0] and b"vault" in v_out["htmls"][0]
        exp_mods = (
            b"crud", b"telemetry", b"role_projection", b"telemetry", b"data_pipeline"
        )  # fmt: skip
        for expected_mod, raw_html in zip(exp_mods, v_out["htmls"], strict=True):
            assert expected_mod in raw_html
