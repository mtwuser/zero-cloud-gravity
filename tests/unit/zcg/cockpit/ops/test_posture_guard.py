"""Unit tests for zcg.cockpit.ops.posture_guard.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

from zcg.cockpit.ops.posture_guard import (
    POSTURE_CONTRACT_REV,
    evaluate_local_security_posture,
    filter_safe_overlay_template_dirs,
    load_overlay_routers_with_quarantine,
)
from zcg.web.http.factory import WebAppState, create_web_app


class TestPostureGuard:
    """1:1 unit suite for Golden-Image overlay quarantine and 0..100 security posture scoring."""

    def test_filter_safe_overlay_template_dirs_clean_absent_and_quarantined_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify broken surfaces/web/templates HTML is quarantined while Golden Core survives."""
        # Arrange
        ws = tmp_path / "node"
        golden = tmp_path / "golden-templates"
        golden.mkdir(parents=True)
        overlay_tpl = ws / "surfaces/web/templates"
        overlay_tpl.mkdir(parents=True)
        (overlay_tpl / "ok.html").write_text("<div>{{ title }}</div>", encoding="utf-8")

        ws_bad = tmp_path / "node-bad"
        bad_tpl = ws_bad / "surfaces/web/templates"
        bad_tpl.mkdir(parents=True)
        (bad_tpl / "broken.html").write_text("{% if x %}unclosed", encoding="utf-8")

        # Act
        absent_dirs, absent_q = filter_safe_overlay_template_dirs(ws, (golden.resolve(),))
        clean_dirs, clean_q = filter_safe_overlay_template_dirs(
            ws, (overlay_tpl.resolve(), golden.resolve())
        )
        safe_dirs, bad_q = filter_safe_overlay_template_dirs(
            ws_bad, (bad_tpl.resolve(), golden.resolve())
        )

        # Assert
        assert absent_q["quarantined"] is False and absent_dirs == (golden.resolve(),)
        assert clean_q["quarantined"] is False and len(clean_dirs) == 2
        assert bad_q["status"] == "OVERLAY_BOOT_QUARANTINED" and bad_q["quarantined"] is True
        assert safe_dirs == (golden.resolve(),)

    def test_load_overlay_routers_with_quarantine_clean_and_syntax_error_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify syntax-broken surfaces/web/routers/*.py quarantines without crashing boot."""
        # Arrange
        states: list[WebAppState] = []
        create_web_app(state_out=states)
        st = states[0]
        clean_ws = tmp_path / "clean-ws"
        clean_ws.mkdir()
        bad_ws = tmp_path / "bad-ws"
        (bad_ws / "surfaces/web/routers").mkdir(parents=True)
        (bad_ws / "surfaces/web/routers/broken.py").write_text("def broken(:\n", encoding="utf-8")

        # Act
        ok_rtrs, ok_q = load_overlay_routers_with_quarantine(clean_ws, state=st)
        bad_rtrs, bad_q = load_overlay_routers_with_quarantine(bad_ws, state=st)

        # Assert
        assert ok_rtrs == () and ok_q["status"] == "CLEAN"
        assert bad_rtrs == () and bad_q["status"] == "OVERLAY_BOOT_QUARANTINED"

    def test_evaluate_local_security_posture_hardened_guarded_and_action_required_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 0..100 posture score cut-points (HARDENED, GUARDED, ACTION_REQUIRED)."""
        # Arrange
        hard_ws = tmp_path / "hardened"
        (hard_ws / "system").mkdir(parents=True)
        (hard_ws / "surfaces/web/routers").mkdir(parents=True)
        (hard_ws / "surfaces/web/templates").mkdir(parents=True)
        (hard_ws / "surfaces/web/routers/r.py").write_text("X = 1\n", encoding="utf-8")
        (hard_ws / "surfaces/web/templates/t.html").write_text("<p>ok</p>", encoding="utf-8")
        (hard_ws / ".gitignore").write_text(".zcg/\n", encoding="utf-8")
        (hard_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {"layer_id": "persona-profile", "layer_role": "workstation", "precedence": 90}
            ),
            encoding="utf-8",
        )

        guarded_ws = tmp_path / "guarded"
        (guarded_ws / "system").mkdir(parents=True)
        (guarded_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {"layer_id": "persona-profile", "layer_role": "workstation", "precedence": 90}
            ),
            encoding="utf-8",
        )

        weak_ws = tmp_path / "weak"
        (weak_ws / "system").mkdir(parents=True)
        (weak_ws / "surfaces/web/routers").mkdir(parents=True)
        w_rtr = weak_ws / "surfaces/web/routers/world.py"
        w_rtr.write_text("X = 1\n", encoding="utf-8")
        w_rtr.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IWOTH)
        (weak_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "org-open",
                    "layer_role": "knowledge",
                    "entity_kind": "enterprise",
                    "visibility": "public",
                }
            ),
            encoding="utf-8",
        )

        bad_tpl_ws = tmp_path / "bad-tpl"
        (bad_tpl_ws / "surfaces/web/templates").mkdir(parents=True)
        (bad_tpl_ws / "surfaces/web/templates/bad.html").write_text("{% if a %}", encoding="utf-8")

        # Act
        res_hard = evaluate_local_security_posture(hard_ws)
        res_guard = evaluate_local_security_posture(guarded_ws)
        res_weak = evaluate_local_security_posture(weak_ws)
        res_btpl = evaluate_local_security_posture(bad_tpl_ws)

        # Assert
        w_rtr.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert res_hard["contract_rev"] == POSTURE_CONTRACT_REV
        assert res_hard["score"] == 100 and res_hard["grade"] == "HARDENED"
        assert res_hard["recommendations"] == []
        assert res_guard["score"] == 80 and res_guard["grade"] == "GUARDED"
        assert res_weak["score"] == 20 and res_weak["grade"] == "ACTION_REQUIRED"
        assert len(res_weak["recommendations"]) == 4
        assert res_btpl["checks"]["overlay_integrity"] is False
