"""Composable Node Admin APIRouter (/api/modules/runtime) for Antigravity and 1-Hop Updates.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from zcg.cockpit.ops.runtime_studio import render_runtime_and_updates_html
from zcg.core.constants import REPO_DIR
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.model_currency import resolve_node_agent_guidance
from zcg.governance.runtime.node_updates import inspect_node_update_plan
from zcg.providers.antigravity_runtime import (
    check_antigravity_online_releases,
    inspect_local_antigravity_runtime,
)
from zcg.web.auth.security import ErrorSeverity, WebAppError
from zcg.web.capabilities.appearance import resolve_request_ring
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from zcg.web.auth.surface_access import SurfaceAccessPolicy


def create_runtime_router(
    workspace_dir: Path,
    *,
    parent_dir: Path | None = None,
    engine_dir: Path = REPO_DIR,
    policy: SurfaceAccessPolicy | None = None,
    online_checker: Callable[..., dict[str, Any]] | None = None,
    prefix: str = "/api/modules/runtime",
) -> APIRouter:
    """Create R3-guarded APIRouter for Antigravity runtime inspection and 1-Hop node updates."""
    ws = workspace_dir.resolve()
    clean_pfx = prefix.rstrip("/") or "/api/modules/runtime"
    router = APIRouter(prefix=clean_pfx, tags=("runtime",))

    def _require_r3(req: Request) -> None:
        if policy is not None and resolve_request_ring(req, policy) != "R3":
            raise WebAppError(
                "Inspecting node runtime and updates requires R3 operator authority",
                error_code="NODE_ADMIN_OPERATOR_REQUIRED",
                http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )

    def _inspect_base() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        local_agy = inspect_local_antigravity_runtime(ws, engine_dir=engine_dir)
        update_plan = inspect_node_update_plan(ws, parent_dir=parent_dir, engine_dir=engine_dir)
        guidance = resolve_node_agent_guidance(load_node_manifest(ws))
        return local_agy, update_plan, guidance

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect local runtime & updates")
    def get_runtime_overview(req: Request) -> WebResponse:
        _require_r3(req)
        local_agy, update_plan, guidance = _inspect_base()
        frag = render_runtime_and_updates_html(local_agy, update_plan, agent_guidance=guidance)
        return respond(
            req,
            html_fragment=frag,
            data={
                "local_antigravity": local_agy,
                "update_plan": update_plan,
                "agent_guidance": guidance,
            },
        )

    @router.get(
        "/check-updates",
        channel=DeliveryChannel.SWAP_SYNC,
        summary="Check live Antigravity online releases",
    )
    def check_online_updates(req: Request) -> WebResponse:
        _require_r3(req)
        local_agy, update_plan, guidance = _inspect_base()
        checker = online_checker or check_antigravity_online_releases
        online = checker(ws, local_runtime=local_agy)
        frag = render_runtime_and_updates_html(
            local_agy, update_plan, online_check=online, agent_guidance=guidance
        )
        return respond(
            req,
            html_fragment=frag,
            data={
                "local_antigravity": local_agy,
                "update_plan": update_plan,
                "online_check": online,
                "agent_guidance": guidance,
            },
        )

    return router
