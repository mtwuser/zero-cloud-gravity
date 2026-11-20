"""Declarative multi-capability Reference Dashboard composer ('enabled_modules' -> web app).

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.ops.posture_guard import evaluate_local_security_posture
from zcg.cockpit.routing.docs_router import create_docs_reader_router
from zcg.cockpit.routing.ledger_router import create_work_ledger_router
from zcg.cockpit.routing.mesh_router import create_node_mesh_router
from zcg.cockpit.routing.tool_router import create_tool_stack_router
from zcg.cockpit.views.spatial_bridge import build_live_node_spatial_presets
from zcg.platform.pipeline_router import create_data_pipeline_router
from zcg.platform.projection import DisclosureTier, PayloadFieldSegment
from zcg.platform.projection_router import create_role_projection_router
from zcg.plugins.portal_inbox import create_portal_inbox_router
from zcg.plugins.wallet_treasury import create_wallet_treasury_router
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities.crud import (
    CollectionLayout,
    CollectionSchema,
    FieldKind,
    ResourceFieldSpec,
    create_crud_router,
)
from zcg.web.capabilities.spatial_atlas import create_spatial_atlas_router
from zcg.web.capabilities.telemetry_router import create_telemetry_router
from zcg.web.capabilities.vault import create_vault_router
from zcg.web.http.factory import WebAppState
from zcg.web.http.router import APIRouter

VALID_DASHBOARD_MODULES: Final[tuple[str, ...]] = (
    "crud", "vault", "telemetry", "data_pipeline", "role_projection", "node_mesh",
    "work_ledger", "docs_reader", "wallet_treasury", "spatial_atlas", "tool_stack", "portal_inbox",
)  # fmt: skip

ARCHETYPE_DEFAULT_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "workstation-control-tower": ("work_ledger", "docs_reader", "spatial_atlas", "portal_inbox"),
    "academic-tutor-cockpit": (
        "work_ledger", "docs_reader", "crud", "vault", "spatial_atlas", "portal_inbox",
    ),
    "personal-work-cockpit": (
        "work_ledger", "docs_reader", "crud", "role_projection",
        "vault", "spatial_atlas", "portal_inbox",
    ),
    "corporate-root-hub": (
        "work_ledger", "docs_reader", "spatial_atlas", "portal_inbox", "data_pipeline",
    ),
    "departmental-ops-cockpit": (
        "work_ledger", "docs_reader", "crud", "data_pipeline", "vault", "spatial_atlas",
    ),
    "secops-mcp-guardian": ("work_ledger", "docs_reader", "crud", "vault", "spatial_atlas"),
    "knowledge-stewardship-portal": (
        "docs_reader", "work_ledger", "crud", "data_pipeline",
        "vault", "spatial_atlas", "portal_inbox",
    ),
    "sovereign-wallet-cockpit": (
        "wallet_treasury", "work_ledger", "docs_reader", "vault", "spatial_atlas",
    ),
}  # fmt: skip

ARCHETYPE_DEFAULT_PLUGIN: Final[dict[str, str]] = {
    "workstation-control-tower": "workstation-control-tower",
    "academic-tutor-cockpit": "tutor-study-cockpit",
    "personal-work-cockpit": "node-work-cockpit",
    "corporate-root-hub": "corporate-root-hub",
    "departmental-ops-cockpit": "node-work-cockpit",
    "secops-mcp-guardian": "secops-mcp-guardian",
    "knowledge-stewardship-portal": "knowledge-stewardship-portal",
    "sovereign-wallet-cockpit": "sovereign-wallet-cockpit",
}

MODULE_SWAP_URLS: Final[dict[str, str]] = {
    "crud": "/api/modules/crud?view=cards",
    "vault": "/api/modules/vault?view=cards",
    "telemetry": "/api/modules/telemetry",
    "data_pipeline": "/api/modules/data-pipeline",
    "role_projection": "/api/modules/role-projection?stage=candidate_application",
    "node_mesh": "/api/modules/node-mesh",
    "work_ledger": "/api/modules/work-ledger",
    "docs_reader": "/api/modules/docs-reader",
    "wallet_treasury": "/api/modules/wallet-treasury?ring=R3&privacy_shield=1",
    "spatial_atlas": "/api/modules/spatial-atlas",
    "tool_stack": "/api/tools",
    "portal_inbox": "/api/modules/portal-inbox?mode=workspace",
}

_ARCHETYPE_PANEL_TITLES: Final[dict[str, str]] = {
    "workstation-control-tower": "Personal & Workstation Hub",
    "academic-tutor-cockpit": "Study & Curriculum Lab",
    "personal-work-cockpit": "Career & Ventures",
    "corporate-root-hub": "Corporate Root 0 Hub",
    "departmental-ops-cockpit": "Department & Squad Operations",
    "secops-mcp-guardian": "Security & Governance",
    "knowledge-stewardship-portal": "Epistemic Knowledge Corpus",
    "sovereign-wallet-cockpit": "Treasury & Portfolio",
}

MODULE_ACTION_CATALOG: Final[dict[str, tuple[str, str, tuple[str, ...]]]] = {
    "crud": (
        "Domain Records", "/api/modules/crud",
        ("view-cards", "view-list", "view-table", "create-record"),
    ),
    "vault": ("Document Vault", "/api/modules/vault", ("list-files", "upload-sample")),
    "telemetry": (
        "Health & Telemetry", "/api/modules/telemetry",
        ("inspect-telemetry", "inspect-audit", "append-audit"),
    ),
    "data_pipeline": (
        "Data Pipeline", "/api/modules/data-pipeline",
        ("inspect-pipeline", "ingest-batch"),
    ),
    "role_projection": (
        "CV & Role Projection", "/api/modules/role-projection",
        ("candidate_application", "day1_onboarding", "b2b_proposal"),
    ),
    "node_mesh": ("Network & Links", "/api/modules/node-mesh", ("inspect-mesh",)),
    "work_ledger": (
        "Work Board", "/api/modules/work-ledger",
        ("inspect-ledger", "enqueue-job", "complete-job", "poll-286"),
    ),
    "docs_reader": (
        "Docs & Knowledge", "/api/modules/docs-reader", ("browse-docs", "read-doc"),
    ),
    "wallet_treasury": (
        "Treasury & Portfolio", "/api/modules/wallet-treasury", ("inspect-r3", "export-r0"),
    ),
    "spatial_atlas": (
        "Network Atlas", "/api/modules/spatial-atlas",
        ("inspect-atlas", "inspect-scene"),
    ),
    "tool_stack": (
        "Skills & Tools", "/api/tools",
        ("list-tools", "export-sarif", "evaluate-decision"),
    ),
    "portal_inbox": (
        "External Mailbox", "/api/modules/portal-inbox",
        ("inspect-inbox", "set-exposure", "triage-request"),
    ),
}  # fmt: skip


def resolve_archetype_crud_schema(view_archetype: str) -> CollectionSchema:
    """Return a default declarative CollectionSchema parameterized for a dashboard archetype."""
    if view_archetype == "academic-tutor-cockpit":
        return CollectionSchema(
            slug="study-drills", title="Socratic Curriculum Drills",
            default_layout=CollectionLayout.CARDS, title_field="title",
            subtitle_field="category", badge_field="stage", body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Drill Prompt", FieldKind.TEXT),
                ResourceFieldSpec("category", "Specialty", FieldKind.SLUG, default="maths"),
                ResourceFieldSpec(
                    "stage", "Mastery Stage", FieldKind.CHOICE,
                    choices=("M1", "M2", "M3", "M4"), filterable=True, default="M1",
                ),
                ResourceFieldSpec("summary", "Notes", FieldKind.LONG_TEXT, required=False),
            ),
        )  # fmt: skip
    if view_archetype == "knowledge-stewardship-portal":
        return CollectionSchema(
            slug="epistemic-entries", title="Epistemic Corpus Entries",
            default_layout=CollectionLayout.CARDS, title_field="title",
            subtitle_field="category", badge_field="grade", body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Entry Title", FieldKind.TEXT),
                ResourceFieldSpec("category", "Domain", FieldKind.SLUG, default="statutory"),
                ResourceFieldSpec(
                    "grade", "Epistemic Grade", FieldKind.CHOICE,
                    choices=("E3", "E2", "E1", "E0"), filterable=True, default="E2",
                ),
                ResourceFieldSpec("summary", "Summary", FieldKind.LONG_TEXT, required=False),
            ),
        )  # fmt: skip
    if view_archetype == "secops-mcp-guardian":
        return CollectionSchema(
            slug="security-controls", title="Security Controls & Risk Register",
            default_layout=CollectionLayout.CARDS, title_field="title",
            subtitle_field="scope", badge_field="severity", body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Control / Advisory", FieldKind.TEXT),
                ResourceFieldSpec(
                    "scope", "Security Domain", FieldKind.CHOICE,
                    choices=("constellation", "device", "patrimony", "travel"),
                    filterable=True, default="constellation",
                ),
                ResourceFieldSpec(
                    "severity", "Severity", FieldKind.CHOICE,
                    choices=("CRITICAL", "HIGH", "MEDIUM", "LOW"),
                    filterable=True, default="MEDIUM",
                ),
                ResourceFieldSpec(
                    "summary", "Mitigation Notes", FieldKind.LONG_TEXT, required=False
                ),
            ),
        )  # fmt: skip
    if view_archetype == "personal-work-cockpit":
        return CollectionSchema(
            slug="venture-opportunities", title="Ventures & Opportunity Log",
            default_layout=CollectionLayout.CARDS, title_field="title",
            subtitle_field="track", badge_field="status", body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Venture / Opportunity", FieldKind.TEXT),
                ResourceFieldSpec(
                    "track", "Track", FieldKind.CHOICE,
                    choices=("opportunity", "venture", "engagement"), filterable=True,
                    default="venture",
                ),
                ResourceFieldSpec(
                    "status", "Stage", FieldKind.CHOICE,
                    choices=("EXPLORING", "ACTIVE", "CLOSED"), filterable=True, default="ACTIVE",
                ),
                ResourceFieldSpec("summary", "Thesis / Notes", FieldKind.LONG_TEXT, required=False),
            ),
        )  # fmt: skip
    return CollectionSchema(
        slug="workspace-records", title="Operational Records",
        default_layout=CollectionLayout.CARDS, title_field="title",
        subtitle_field="category", badge_field="pinned", body_field="summary",
        fields=(
            ResourceFieldSpec("title", "Title", FieldKind.TEXT),
            ResourceFieldSpec(
                "category", "Category", FieldKind.SLUG, filterable=True, default="general"
            ),
            ResourceFieldSpec("summary", "Summary", FieldKind.LONG_TEXT, required=False),
            ResourceFieldSpec("pinned", "Pinned", FieldKind.BOOL, required=False, default=False),
        ),
    )  # fmt: skip


def _default_node_projection_segments(layer_label: str) -> tuple[PayloadFieldSegment, ...]:
    return (
        PayloadFieldSegment("headline", DisclosureTier.CORE_SUMMARY, f"{layer_label} Node"),
        PayloadFieldSegment("verified_domain", DisclosureTier.VERIFIED_COMPETENCY,
                            "Distributed Node Governance"),
        PayloadFieldSegment("onboarding_identifier", DisclosureTier.DAY1_ONBOARDING,
                            "RECORD-ONBOARD-01"),
        PayloadFieldSegment("collaboration_scope", DisclosureTier.DEEP_CONTEXT, "Peer Cloud Link"),
    )  # fmt: skip


def resolve_enabled_modules(
    view_archetype: str, manifest_modules: Sequence[str] | None = None
) -> tuple[str, ...]:
    """Resolve and validate the ordered tuple of capability modules for a node dashboard."""
    if manifest_modules is not None:
        cleaned: list[str] = []
        for raw in manifest_modules:
            slug = str(raw).strip()
            if slug not in VALID_DASHBOARD_MODULES:
                raise ValueError(
                    f"Unknown dashboard module {slug!r}; valid={VALID_DASHBOARD_MODULES}"
                )
            if slug not in cleaned:
                cleaned.append(slug)
        return tuple(cleaned)
    return ARCHETYPE_DEFAULT_MODULES.get(
        view_archetype, ARCHETYPE_DEFAULT_MODULES["departmental-ops-cockpit"]
    )


def build_modular_workbench_spec(
    view_archetype: str,
    use_case_overlay: str,
    enterprise_scale: str | None = None,
    enabled_modules: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build deterministic multi-capability Zone Z3 workbench metadata (0 host paths)."""
    resolved = resolve_enabled_modules(view_archetype, enabled_modules)
    title = _ARCHETYPE_PANEL_TITLES.get(
        view_archetype, _ARCHETYPE_PANEL_TITLES["departmental-ops-cockpit"]
    )
    if view_archetype == "academic-tutor-cockpit":
        mode = (
            "guided-socratic-m1-m2"
            if use_case_overlay == "school-student-m1-m2"
            else "specialty-dmcp-m2-m3"
        )
    elif view_archetype in ("corporate-root-hub", "departmental-ops-cockpit") and enterprise_scale:
        mode = f"enterprise-{enterprise_scale}"
    else:
        mode = use_case_overlay
    crud_title = resolve_archetype_crud_schema(view_archetype).title
    module_specs = [
        {
            "module_id": mod_id,
            "title": crud_title if mod_id == "crud" else MODULE_ACTION_CATALOG[mod_id][0],
            "endpoint": MODULE_ACTION_CATALOG[mod_id][1],
            "actions": list(MODULE_ACTION_CATALOG[mod_id][2]),
        }
        for mod_id in resolved
    ]
    return {
        "dashboard_id": view_archetype,
        "panel_title": title,
        "mode": mode,
        "enabled_modules": list(resolved),
        "modules": module_specs,
    }


def build_dashboard_routers(
    workspace_dir: Path, *, enabled_modules: Sequence[str], layer_label: str, state: WebAppState,
    view_archetype: str = "departmental-ops-cockpit", crud_schema: CollectionSchema | None = None,
    pipeline_seed_records: Sequence[Mapping[str, Any]] = (),
    projection_segments: Sequence[PayloadFieldSegment] | None = None,
    policy: SurfaceAccessPolicy | None = None,
) -> tuple[APIRouter, ...]:  # fmt: skip
    """Instantiate selected capability APIRouters parameterized for a node dashboard."""
    ws = workspace_dir.resolve()
    resolved = resolve_enabled_modules(view_archetype, enabled_modules)
    eff_schema = crud_schema or resolve_archetype_crud_schema(view_archetype)
    eff_segs = (
        tuple(projection_segments) if projection_segments is not None
        else _default_node_projection_segments(layer_label)
    )  # fmt: skip
    built: list[APIRouter] = []
    for mod_id in resolved:
        if mod_id == "crud":
            built.append(create_crud_router(ws, schema=eff_schema, prefix="/api/modules/crud"))
        elif mod_id == "vault":
            built.append(
                create_vault_router(ws, job_queue=state.job_queue, prefix="/api/modules/vault")
            )
        elif mod_id == "telemetry":
            built.append(create_telemetry_router(
                ws, surface_label=layer_label, signal_collector=state.signal_collector,
                jitter_tracker=state.jitter_tracker, bulkhead=state.bulkhead,
                security_posture_provider=partial(evaluate_local_security_posture, ws),
                prefix="/api/modules/telemetry",
            ))  # fmt: skip
        elif mod_id == "data_pipeline":
            built.append(create_data_pipeline_router(
                source_label=layer_label, seed_records=pipeline_seed_records,
                prefix="/api/modules/data-pipeline",
            ))  # fmt: skip
        elif mod_id == "role_projection":
            built.append(create_role_projection_router(
                default_segments=eff_segs, resource_id=f"{layer_label}-profile",
                shared_packs=("universal-base",), prefix="/api/modules/role-projection",
            ))  # fmt: skip
        elif mod_id == "node_mesh":
            built.append(create_node_mesh_router(ws, prefix="/api/modules/node-mesh"))
        elif mod_id == "wallet_treasury":
            built.append(create_wallet_treasury_router(
                ws, surface_label=layer_label, prefix="/api/modules/wallet-treasury"
            ))  # fmt: skip
        elif mod_id == "spatial_atlas":
            built.append(create_spatial_atlas_router(
                presets=build_live_node_spatial_presets(ws),
                prefix="/api/modules/spatial-atlas", csrf_token=state.csrf_token,
            ))  # fmt: skip
        elif mod_id == "tool_stack":
            built.append(create_tool_stack_router(ws))
        elif mod_id == "portal_inbox":
            built.append(
                create_portal_inbox_router(ws, policy=policy, prefix="/api/modules/portal-inbox")
            )
        elif mod_id == "docs_reader":
            built.append(
                create_docs_reader_router(ws, policy=policy, prefix="/api/modules/docs-reader")
            )
        else:
            built.append(create_work_ledger_router(
                ws, job_queue=state.job_queue, prefix="/api/modules/work-ledger"
            ))  # fmt: skip
    return tuple(built)
