"""Declarative multi-capability Reference Dashboard composer ('enabled_modules' -> web app).

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.ledger_router import create_work_ledger_router
from zcg.cockpit.mesh_router import create_node_mesh_router
from zcg.platform.pipeline_router import create_data_pipeline_router
from zcg.platform.projection import DisclosureTier, PayloadFieldSegment
from zcg.platform.projection_router import create_role_projection_router
from zcg.web.capabilities.crud import (
    CollectionLayout,
    CollectionSchema,
    FieldKind,
    ResourceFieldSpec,
    create_crud_router,
)
from zcg.web.capabilities.telemetry_router import create_telemetry_router
from zcg.web.capabilities.vault import create_vault_router
from zcg.web.factory import WebAppState
from zcg.web.router import APIRouter

VALID_DASHBOARD_MODULES: Final[tuple[str, ...]] = (
    "crud",
    "vault",
    "telemetry",
    "data_pipeline",
    "role_projection",
    "node_mesh",
    "work_ledger",
)

ARCHETYPE_DEFAULT_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "workstation-control-tower": ("node_mesh", "telemetry", "work_ledger", "vault"),
    "academic-tutor-cockpit": ("crud", "vault", "node_mesh", "telemetry"),
    "personal-work-cockpit": ("role_projection", "crud", "vault", "work_ledger", "node_mesh"),
    "corporate-root-hub": ("node_mesh", "work_ledger", "crud", "vault", "data_pipeline"),
    "departmental-ops-cockpit": ("work_ledger", "crud", "vault", "node_mesh", "data_pipeline"),
    "secops-mcp-guardian": ("telemetry", "node_mesh", "work_ledger"),
    "knowledge-stewardship-portal": ("data_pipeline", "crud", "vault", "node_mesh"),
}

ARCHETYPE_DEFAULT_PLUGIN: Final[dict[str, str]] = {
    "workstation-control-tower": "workstation-control-tower",
    "academic-tutor-cockpit": "tutor-study-cockpit",
    "personal-work-cockpit": "node-work-cockpit",
    "corporate-root-hub": "corporate-root-hub",
    "departmental-ops-cockpit": "node-work-cockpit",
    "secops-mcp-guardian": "secops-mcp-guardian",
    "knowledge-stewardship-portal": "knowledge-stewardship-portal",
}

MODULE_SWAP_URLS: Final[dict[str, str]] = {
    "crud": "/api/modules/crud?view=cards",
    "vault": "/api/modules/vault?view=cards",
    "telemetry": "/api/modules/telemetry",
    "data_pipeline": "/api/modules/data-pipeline",
    "role_projection": "/api/modules/role-projection?stage=candidate_application",
    "node_mesh": "/api/modules/node-mesh",
    "work_ledger": "/api/modules/work-ledger",
}

_ARCHETYPE_PANEL_TITLES: Final[dict[str, str]] = {
    "workstation-control-tower": "Workstation Control Tower — Composable Capabilities (:8790)",
    "academic-tutor-cockpit": "Socratic Study & Collections Lab — Composable Capabilities (:8786)",
    "personal-work-cockpit": "Personal Career & Projection — Composable Capabilities (:8787)",
    "corporate-root-hub": "Corporate Root 0 Hub — Composable Capabilities (:8710)",
    "departmental-ops-cockpit": "Departmental & Squad Operations — Composable Capabilities",
    "secops-mcp-guardian": "Fiduciary SecOps & Audit Guardian — Composable Capabilities (:8705)",
    "knowledge-stewardship-portal": "Epistemic Corpus & Data Pipeline — Capabilities (:8720)",
}

MODULE_ACTION_CATALOG: Final[dict[str, tuple[str, str, tuple[str, ...]]]] = {
    "crud": (
        "Declarative CRUD Collection",
        "/api/modules/crud",
        ("view-cards", "view-list", "view-table", "create-record"),
    ),
    "vault": (
        "Content-Addressed Vault",
        "/api/modules/vault",
        ("list-files", "upload-sample"),
    ),
    "telemetry": (
        "Telemetry & Audit DAG",
        "/api/modules/telemetry",
        ("inspect-telemetry", "inspect-audit", "append-audit"),
    ),
    "data_pipeline": (
        "Data Pipeline (CDC/CVS)",
        "/api/modules/data-pipeline",
        ("inspect-pipeline", "ingest-batch"),
    ),
    "role_projection": (
        "Minimal-Disclosure Projection",
        "/api/modules/role-projection",
        ("candidate_application", "day1_onboarding", "b2b_proposal"),
    ),
    "node_mesh": ("1-Hop & Cloud Mesh", "/api/modules/node-mesh", ("inspect-mesh",)),
    "work_ledger": (
        "Work Ledger & T2 Jobs",
        "/api/modules/work-ledger",
        ("inspect-ledger", "enqueue-job", "complete-job", "poll-286"),
    ),
}

MODULAR_WORKBENCH_JS: Final[str] = (
    "let ACTIVE_MOD='';"
    "function selectModule(mid){ACTIVE_MOD=mid;renderModularWorkbench(MW,R.dual_world_contract);}"
    "async function runModuleAction(mid,act){"
    "const m=(MW.modules||[]).find(x=>x.module_id===mid)||{};"
    "let u=m.endpoint||'/healthz',opt={method:'GET'};"
    "if(mid==='role_projection')u+=`?stage=${act}`;"
    "else if(act==='view-cards')u+='?view=cards';"
    "else if(act==='view-list')u+='?view=list';"
    "else if(act==='view-table')u+='?view=table';"
    "else if(act==='create-record')opt={method:'POST',body:JSON.stringify("
    "{title:'Verified Entry',category:'spec',summary:'Declarative CRUD record'})};"
    "else if(act==='upload-sample')opt={method:'POST',body:JSON.stringify("
    "{filename:'artifact.md',content:'# Verified Asset',media_type:'text/markdown'})};"
    "else if(act==='inspect-audit')u+='/audit';"
    "else if(act==='append-audit'){u+='/audit';opt={method:'POST',body:JSON.stringify("
    "{rationale:'Fiduciary gate verified',volume_ratio:0.95})};}"
    "else if(act==='enqueue-job'){u+='/jobs';opt={method:'POST',body:JSON.stringify("
    "{task_id:'sprint-sync-01'})};}"
    "else if(act==='complete-job'){u+='/jobs/sprint-sync-01/progress';"
    "opt={method:'POST',body:JSON.stringify({progress:1.0})};}"
    "else if(act==='poll-286')u='/api/poll/status';"
    "else if(act==='ingest-batch')opt={method:'POST',body:JSON.stringify("
    "{records:[{id:'rec-01',code:'ISO-01',metric:99.2}]})};"
    "const r=await fetch(u,opt),tx=await r.text();"
    "document.getElementById('v_out').innerHTML=`<code>[HTTP ${r.status}] ${tx}</code>`;"
    "window.IslandBus.emit('module:action',{module:mid,act,status:r.status});}"
    "function renderModularWorkbench(MW,DW){"
    "const mods=MW.modules||[];if(!ACTIVE_MOD&&mods.length)ACTIVE_MOD=mods[0].module_id;"
    "const cur=mods.find(x=>x.module_id===ACTIVE_MOD)||mods[0]||{actions:[]};"
    "document.getElementById('v_hdr').textContent="
    "`${MW.panel_title||'Modular Workbench'} [${MW.mode||''}]`;"
    'const tabs=mods.map(m=>`<button class=\'pill ${m.module_id===cur.module_id?"active":""}\' '
    "data-mod-select='${m.module_id}'>[${m.module_id}] ${m.title}</button>`).join('')+"
    "\"<a class='pill' href='/dashboard'>Editable Dashboard (/dashboard)</a>\";"
    "const acts=(cur.actions||[]).map(a=>`<button class='pill active' "
    "data-mod-id='${cur.module_id}' data-mod-act='${a}'>${a}</button>`).join('');"
    "document.getElementById('v_btns').innerHTML="
    "`<div>${tabs}</div><div style='margin-top:8px'>${acts}</div>`;"
    "document.getElementById('v_out').innerHTML=`<code>Active Capability: ${cur.module_id||'none'}"
    " (${cur.endpoint||'/healthz'}) · Overlay: ${DW.use_case_overlay}</code>`;}"
    "document.addEventListener('click',ev=>{const ms=ev.target.closest('[data-mod-select]');"
    "if(ms){selectModule(ms.dataset.modSelect);return;}"
    "const ma=ev.target.closest('[data-mod-act]');"
    "if(ma)runModuleAction(ma.dataset.modId,ma.dataset.modAct);});"
)


def resolve_archetype_crud_schema(view_archetype: str) -> CollectionSchema:
    """Return a default declarative CollectionSchema parameterized for a dashboard archetype."""
    if view_archetype == "academic-tutor-cockpit":
        return CollectionSchema(
            slug="study-drills",
            title="Socratic Curriculum Drills",
            default_layout=CollectionLayout.CARDS,
            title_field="title",
            subtitle_field="category",
            badge_field="stage",
            body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Drill Prompt", FieldKind.TEXT),
                ResourceFieldSpec("category", "Specialty", FieldKind.SLUG, default="maths"),
                ResourceFieldSpec(
                    "stage",
                    "Mastery Stage",
                    FieldKind.CHOICE,
                    choices=("M1", "M2", "M3", "M4"),
                    filterable=True,
                    default="M1",
                ),
                ResourceFieldSpec("summary", "Notes", FieldKind.LONG_TEXT, required=False),
            ),
        )
    if view_archetype == "knowledge-stewardship-portal":
        return CollectionSchema(
            slug="epistemic-entries",
            title="Epistemic Corpus Entries",
            default_layout=CollectionLayout.CARDS,
            title_field="title",
            subtitle_field="category",
            badge_field="grade",
            body_field="summary",
            fields=(
                ResourceFieldSpec("title", "Entry Title", FieldKind.TEXT),
                ResourceFieldSpec("category", "Domain", FieldKind.SLUG, default="statutory"),
                ResourceFieldSpec(
                    "grade",
                    "Epistemic Grade",
                    FieldKind.CHOICE,
                    choices=("E3", "E2", "E1", "E0"),
                    filterable=True,
                    default="E2",
                ),
                ResourceFieldSpec("summary", "Summary", FieldKind.LONG_TEXT, required=False),
            ),
        )
    return CollectionSchema(
        slug="workspace-records",
        title="Workspace Records",
        default_layout=CollectionLayout.CARDS,
        title_field="title",
        subtitle_field="category",
        badge_field="pinned",
        body_field="summary",
        fields=(
            ResourceFieldSpec("title", "Title", FieldKind.TEXT),
            ResourceFieldSpec(
                "category", "Category", FieldKind.SLUG, filterable=True, default="general"
            ),
            ResourceFieldSpec("summary", "Summary", FieldKind.LONG_TEXT, required=False),
            ResourceFieldSpec("pinned", "Pinned", FieldKind.BOOL, required=False, default=False),
        ),
    )


def _default_node_projection_segments(layer_label: str) -> tuple[PayloadFieldSegment, ...]:
    return (
        PayloadFieldSegment("headline", DisclosureTier.CORE_SUMMARY, f"{layer_label} Node"),
        PayloadFieldSegment(
            "verified_domain",
            DisclosureTier.VERIFIED_COMPETENCY,
            "Distributed Node Governance",
        ),
        PayloadFieldSegment(
            "onboarding_identifier", DisclosureTier.DAY1_ONBOARDING, "RECORD-ONBOARD-01"
        ),
        PayloadFieldSegment("collaboration_scope", DisclosureTier.DEEP_CONTEXT, "Peer Cloud Link"),
    )


def resolve_enabled_modules(
    view_archetype: str, manifest_modules: Sequence[str] | None = None
) -> tuple[str, ...]:
    """Resolve and validate the ordered tuple of capability modules for a node dashboard."""
    if manifest_modules:
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
    module_specs = [
        {
            "module_id": mod_id,
            "title": MODULE_ACTION_CATALOG[mod_id][0],
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
    workspace_dir: Path,
    *,
    enabled_modules: Sequence[str],
    layer_label: str,
    state: WebAppState,
    view_archetype: str = "departmental-ops-cockpit",
    crud_schema: CollectionSchema | None = None,
    pipeline_seed_records: Sequence[Mapping[str, Any]] = (),
    projection_segments: Sequence[PayloadFieldSegment] | None = None,
) -> tuple[APIRouter, ...]:
    """Instantiate selected capability APIRouters parameterized for a node dashboard."""
    ws = workspace_dir.resolve()
    resolved = resolve_enabled_modules(view_archetype, enabled_modules)
    eff_schema = crud_schema or resolve_archetype_crud_schema(view_archetype)
    eff_segs = (
        tuple(projection_segments)
        if projection_segments is not None
        else _default_node_projection_segments(layer_label)
    )
    built: list[APIRouter] = []
    for mod_id in resolved:
        if mod_id == "crud":
            built.append(create_crud_router(ws, schema=eff_schema, prefix="/api/modules/crud"))
        elif mod_id == "vault":
            built.append(
                create_vault_router(ws, job_queue=state.job_queue, prefix="/api/modules/vault")
            )
        elif mod_id == "telemetry":
            built.append(
                create_telemetry_router(
                    ws,
                    surface_label=layer_label,
                    signal_collector=state.signal_collector,
                    jitter_tracker=state.jitter_tracker,
                    bulkhead=state.bulkhead,
                    prefix="/api/modules/telemetry",
                )
            )
        elif mod_id == "data_pipeline":
            built.append(
                create_data_pipeline_router(
                    source_label=layer_label,
                    seed_records=pipeline_seed_records,
                    prefix="/api/modules/data-pipeline",
                )
            )
        elif mod_id == "role_projection":
            built.append(
                create_role_projection_router(
                    default_segments=eff_segs,
                    resource_id=f"{layer_label}-profile",
                    shared_packs=("universal-base",),
                    prefix="/api/modules/role-projection",
                )
            )
        elif mod_id == "node_mesh":
            built.append(create_node_mesh_router(ws, prefix="/api/modules/node-mesh"))
        else:
            built.append(
                create_work_ledger_router(
                    ws, job_queue=state.job_queue, prefix="/api/modules/work-ledger"
                )
            )
    return tuple(built)
