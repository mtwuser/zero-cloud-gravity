"""Unit tests for zcg.cockpit.provenance.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from zcg.cockpit import provenance

if TYPE_CHECKING:
    from pathlib import Path


class TestProvenance:
    """Verify Root 0 domain/DNS governance, *.localhost routing, origin links, and veracity."""

    def test_normalize_repo_web_url_across_ssh_http_and_invalid_inputs_expected(self) -> None:
        """Verify SCP SSH, ssh://, http(s):// normalization, and local filesystem rejection."""
        # Arrange
        raw_scp = "  git@GitHub.com:mtwuser/zero-cloud-gravity.git/ "
        raw_ssh = "ssh://git@GitLab.com:2222/alpha-group/portal.git/"
        raw_http = "http://forge.internal:3000/alpha/core.git"

        # Act
        out_empty = provenance.normalize_repo_web_url("   ")
        out_scp = provenance.normalize_repo_web_url(raw_scp)
        out_ssh = provenance.normalize_repo_web_url(raw_ssh)
        out_http = provenance.normalize_repo_web_url(raw_http)
        out_root_only = provenance.normalize_repo_web_url("https://github.com/")
        out_local = provenance.normalize_repo_web_url("/home/alex/private-repo")

        # Assert
        assert out_empty == ""
        assert out_scp == "https://github.com/mtwuser/zero-cloud-gravity"
        assert out_ssh == "https://gitlab.com/alpha-group/portal"
        assert out_http == "http://forge.internal:3000/alpha/core"
        assert out_root_only == ""
        assert out_local == ""

    def test_resolve_domain_governance_root0_inheritance_and_rfc6761_hosts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 3-hop Root 0 domain_governance inheritance, *.localhost URLs, and OSS guard."""
        # Arrange
        oss_ws = tmp_path / "oss-engine"
        (oss_ws / "system").mkdir(parents=True)
        (oss_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "zero-cloud-gravity-workstation",
                    "domain_governance": {"canonical_domain": "oss.invalid"},
                }
            ),
            encoding="utf-8",
        )
        root_ws = tmp_path / "corp-alpha-root"
        (root_ws / "system").mkdir(parents=True)
        root_m = {
            "layer_id": "corp-alpha-root",
            "layer_role": "corporate",
            "precedence": 10,
            "domain_governance": {
                "canonical_domain": "alpha.example",
                "local_dev_zone": "alpha",
                "dns_authority": {"delegated_operator_layer": "dept-tech-eng"},
            },
        }
        (root_ws / "system/zcg-node.json").write_text(json.dumps(root_m), encoding="utf-8")
        (root_ws / "Makefile").write_text(f"PARENT_DIR ?= {oss_ws}\n", encoding="utf-8")

        dept_ws = tmp_path / "dept-tech-eng"
        (dept_ws / "system").mkdir(parents=True)
        dept_m = {
            "layer_id": "dept-tech-eng",
            "layer_role": "department",
            "governing_root_id": "corp-alpha-root",
            "precedence": 25,
            "domain_governance": "invalid-non-dict",
        }
        (dept_ws / "system/zcg-node.json").write_text(json.dumps(dept_m), encoding="utf-8")
        (dept_ws / "Makefile").write_text(f"PARENT_DIR ?= {root_ws}\n", encoding="utf-8")

        squad_ws = tmp_path / "squad-web"
        (squad_ws / "system").mkdir(parents=True)
        squad_m = {
            "layer_id": "squad-web",
            "layer_role": "squad",
            "governing_root_id": "corp-alpha-root",
            "precedence": 50,
            "domain_governance": {"intranet_zone": "squads.alpha.example"},
        }
        (squad_ws / "system/zcg-node.json").write_text(json.dumps(squad_m), encoding="utf-8")
        (squad_ws / "Makefile").write_text(f"PARENT_DIR ?= {dept_ws}\n", encoding="utf-8")

        proj_ws = tmp_path / "proj-portal"
        (proj_ws / "system").mkdir(parents=True)
        proj_m = {
            "layer_id": "proj-portal",
            "layer_role": "project",
            "governing_root_id": "corp-alpha-root",
            "precedence": 80,
        }
        (proj_ws / "system/zcg-node.json").write_text(json.dumps(proj_m), encoding="utf-8")
        (proj_ws / "Makefile").write_text(f"PARENT_DIR ?= {squad_ws}\n", encoding="utf-8")

        twin_m = {
            "layer_id": "org-alpha",
            "layer_role": "knowledge",
            "visibility": "public",
            "governing_root_id": "corp-alpha-root",
            "precedence": 20,
        }

        # Act
        ind_dg = provenance.resolve_domain_governance(
            {"entity_kind": "individual", "precedence": 90}, layer_id="alex-pc", port=8790
        )
        sci_dg = provenance.resolve_domain_governance(
            {"layer_role": "knowledge", "visibility": "public", "precedence": 20},
            layer_id="sci-maths",
            active_env="pro",
            port=8720,
        )
        proj_dg = provenance.resolve_domain_governance(
            proj_m, layer_id="proj-portal", active_env="dev", port=8780, workspace_dir=proj_ws
        )
        twin_dg = provenance.resolve_domain_governance(
            twin_m, layer_id="org-alpha", active_env="pro", port=8720, workspace_dir=dept_ws
        )

        # Assert
        assert ind_dg["domain_governance"]["dns_publication"] == "disabled-private-loopback"
        assert ind_dg["domain_governance"]["dns_authority"]["provider"] == "loopback-only"
        assert ind_dg["local_subdomain_host"] == "dev.alex-pc.localhost"
        assert sci_dg["local_subdomain_host"] == "sci-maths.localhost"
        assert proj_dg["local_subdomain_host"] == "dev.proj-portal.alpha.localhost"
        assert proj_dg["domain_governance"]["canonical_domain"] == "alpha.example"
        assert proj_dg["domain_governance"]["intranet_zone"] == "squads.alpha.example"
        assert (
            proj_dg["domain_governance"]["dns_authority"]["delegated_operator_layer"]
            == "dept-tech-eng"
        )
        assert (
            twin_dg["local_subdomain_dashboard_url"] == "http://org-alpha.localhost:8720/dashboard"
        )
        assert twin_dg["domain_governance"]["intranet_zone"] == "intranet.alpha.example"

    def test_veracity_modes_and_source_origin_privacy_guards_expected(self, tmp_path: Path) -> None:
        """Verify all 3 veracity modes, worktree .git resolution, and pro privacy filtering."""
        # Arrange
        ws_git_dir = tmp_path / "dept-private"
        (ws_git_dir / ".git").mkdir(parents=True)
        (ws_git_dir / ".git/config").write_text(
            '[remote "origin"]\n\turl = git@github.com:alpha-private/dept-secret.git\n',
            encoding="utf-8",
        )
        ws_wt = tmp_path / "wt-public"
        ws_wt.mkdir()
        wt_store = tmp_path / "git-wt-store"
        wt_store.mkdir()
        (wt_store / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/alpha-org/org-alpha.git\n',
            encoding="utf-8",
        )
        (ws_wt / ".git").write_text("gitdir: ../git-wt-store\n", encoding="utf-8")

        ws_empty_ptr = tmp_path / "wt-broken"
        ws_empty_ptr.mkdir()
        (ws_empty_ptr / ".git").write_text("corrupt-pointer\n", encoding="utf-8")

        ws_no_origin = tmp_path / "git-no-origin"
        (ws_no_origin / ".git").mkdir(parents=True)
        (ws_no_origin / ".git/config").write_text("[core]\n\tbare = false\n", encoding="utf-8")

        # Act
        m_exp = provenance.resolve_surface_veracity_mode(
            {"surface_veracity_mode": "attestation-only"}
        )
        m_oss = provenance.resolve_surface_veracity_mode({"entity_kind": "open-source"})
        m_pub = provenance.resolve_surface_veracity_mode(
            {"layer_id": "org-alpha", "layer_role": "knowledge", "surface_veracity_mode": "invalid"}
        )
        m_priv = provenance.resolve_surface_veracity_mode({"layer_role": "department"})

        orig_dev = provenance.resolve_source_origin_metadata(
            ws_git_dir, {"layer_id": "dept-private"}, is_public_pro=False
        )
        orig_priv_pro = provenance.resolve_source_origin_metadata(
            ws_git_dir, {"layer_id": "dept-private", "visibility": "private"}, is_public_pro=True
        )
        orig_hidden = provenance.resolve_source_origin_metadata(
            ws_wt,
            {"layer_id": "org-alpha", "visibility": "public", "hide_source_repo_in_pro": True},
            is_public_pro=True,
        )
        orig_wt_pub = provenance.resolve_source_origin_metadata(
            ws_wt, {"layer_id": "org-alpha", "visibility": "public"}, is_public_pro=True
        )
        orig_forge = provenance.resolve_source_origin_metadata(
            ws_empty_ptr,
            {"layer_id": "sci-maths", "public_url": "https://github.com/mtwuser/sci-maths.git"},
        )
        orig_none = provenance.resolve_source_origin_metadata(ws_no_origin, {"layer_id": "solo"})

        # Assert
        assert (m_exp, m_oss, m_pub, m_priv) == (
            "attestation-only",
            "full-open-source",
            "curated-public-surface",
            "attestation-only",
        )
        assert orig_dev["source_repo_url"] == "https://github.com/alpha-private/dept-secret"
        assert orig_priv_pro["source_repo_url"] == ""
        assert orig_hidden["source_repo_url"] == ""
        assert orig_wt_pub["source_repo_label"] == "github.com/alpha-org/org-alpha"
        assert orig_forge["source_repo_url"] == "https://github.com/mtwuser/sci-maths"
        assert orig_none["source_repo_url"] == ""

    def test_materialize_dns_seal_and_footer_across_postures_expected(self, tmp_path: Path) -> None:
        """Verify DNS zone manifests, file_digest Merkle seals (skipping .py), and HTML footers."""
        # Arrange
        ws = tmp_path / "org-alpha"
        (ws / "surfaces/web").mkdir(parents=True)
        (ws / "surfaces/web/index.html").write_text("<h1>Portal</h1>\n", encoding="utf-8")
        (ws / "surfaces/web/router_secret.py").write_text("SECRET = 1\n", encoding="utf-8")
        pub_m = {
            "layer_id": "org-alpha",
            "layer_role": "knowledge",
            "visibility": "public",
            "copyright_holder": "Alpha Corp",
            "source_repo_url": "https://github.com/alpha-org/org-alpha",
        }
        pub_topo = provenance.resolve_domain_governance(
            {**pub_m, "domain_governance": {"canonical_domain": "alpha.example"}},
            layer_id="org-alpha",
            active_env="pro",
            port=8720,
        )
        pub_topo["visibility"] = "public"
        pub_topo["port"] = 8720

        intra_topo = {
            "node_host": "dept-ops.alpha.intranet.local",
            "local_subdomain_host": "dev.dept-ops.alpha.localhost",
            "domain_governance": {
                "dns_publication": "private-split-horizon",
                "intranet_zone": "intra.alpha.example",
            },
        }
        priv_topo = provenance.resolve_domain_governance(
            {"entity_kind": "individual", "precedence": 90}, layer_id="alex-pc", port=8790
        )

        # Act
        prov_bundle = provenance.materialize_node_provenance_surfaces(
            ws, pub_m, pub_topo, active_env="pro"
        )
        custom_seal = provenance.build_public_surface_seal(
            ws,
            pub_m,
            pub_topo,
            active_env="pro",
            web_dirs=(ws / "missing-dir", ws / "surfaces/web"),
            route_signatures=("GET /dashboard", "GET /healthz"),
        )
        dns_intra = provenance.materialize_dns_zone_manifest(
            tmp_path / "dept-ops", {"layer_id": "dept-ops"}, intra_topo
        )
        dns_intra_fb = provenance.materialize_dns_zone_manifest(
            tmp_path / "dept-fb",
            {"layer_id": "dept-fb"},
            {"domain_governance": {"dns_publication": "private-split-horizon"}},
        )
        dns_priv = provenance.materialize_dns_zone_manifest(
            tmp_path / "alex-pc", {"layer_id": "alex-pc", "entity_kind": "individual"}, priv_topo
        )
        ftr_pub = provenance.render_provenance_footer_html(ws, pub_m, pub_topo, active_env="pro")
        ftr_priv = provenance.render_provenance_footer_html(
            tmp_path / "alex-pc", {"layer_id": "alex-pc"}, {}, active_env="dev"
        )

        # Assert
        assert (ws / provenance.DNS_ZONE_MANIFEST_REL_PATH).is_file()
        assert (ws / provenance.PUBLIC_SURFACE_SEAL_REL_PATH).is_file()
        assert prov_bundle["surface_seal"]["served_assets_count"] == 1
        assert prov_bundle["surface_seal"]["code_exposure_required"] is False
        assert custom_seal["public_routes_count"] == 2
        assert dns_intra["records"][0]["name"] == "dept-ops.intra.alpha.example"
        assert dns_intra_fb["records"][0]["name"] == "dept-fb"
        assert dns_priv["records"] == []
        assert (
            "alpha.example" in ftr_pub.value and "github.com/alpha-org/org-alpha" in ftr_pub.value
        )
        assert "private-sovereign-repo" in ftr_priv.value
