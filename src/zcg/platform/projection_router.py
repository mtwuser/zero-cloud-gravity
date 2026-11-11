"""Minimal-Disclosure Role Projection Web Router ('create_role_projection_router').

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, Final

from zcg.platform.projection import (
    DisclosureTier,
    ExchangeStage,
    PayloadFieldSegment,
    ProjectedRoleCapsule,
    RolePayloadProjector,
)
from zcg.web.channels import build_swap_response_headers
from zcg.web.components import render_card, render_kpi_stat, render_table
from zcg.web.request import Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

DEFAULT_PROJECTION_PREFIX: Final[str] = "/api/platform/projection"


def parse_payload_segments(
    raw_segments: Sequence[Mapping[str, Any]],
) -> tuple[PayloadFieldSegment, ...]:
    """Validate and convert JSON segment dictionaries into immutable PayloadFieldSegments."""
    if not raw_segments:
        raise WebAppError(
            "At least one PayloadFieldSegment is required for projection",
            error_code="EMPTY_PROJECTION_SEGMENTS",
            http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    parsed: list[PayloadFieldSegment] = []
    for item in raw_segments:
        raw_tier = str(item.get("tier", "")).strip()
        try:
            tier = DisclosureTier(raw_tier)
            seg = PayloadFieldSegment(
                field_id=str(item.get("field_id", "")),
                tier=tier,
                value=item.get("value"),
                citation_receipt=(
                    str(item["citation_receipt"])
                    if item.get("citation_receipt") is not None
                    else None
                ),
            )
        except ValueError as exc:
            raise WebAppError(
                f"Invalid PayloadFieldSegment: {exc}",
                error_code="INVALID_PROJECTION_SEGMENT",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc
        parsed.append(seg)
    return tuple(parsed)


def _parse_stage(raw_stage: str) -> ExchangeStage:
    try:
        return ExchangeStage(raw_stage.strip())
    except ValueError as exc:
        raise WebAppError(
            f"Invalid exchange stage: {raw_stage}",
            error_code="INVALID_EXCHANGE_STAGE",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        ) from exc


def _render_capsule_card(projected: ProjectedRoleCapsule) -> str:
    rows = [{"field": k, "value": v} for k, v in projected.disclosed_fields.items()]
    body_html = SafeHTML(
        render_kpi_stat(label="Stage", value=projected.stage.value).value
        + render_kpi_stat(label="Withheld", value=str(len(projected.withheld_field_ids))).value
        + render_table(
            columns=(("field", "Field"), ("value", "Disclosed Value")),
            rows=rows,
            empty_message="No fields disclosed at this stage.",
        ).value
    )
    return render_card(
        title=f"Role Projection ({projected.resource_id})",
        badge=projected.target_node_id,
        body=body_html,
    ).value


def create_role_projection_router(
    *,
    projector: RolePayloadProjector | None = None,
    default_segments: Sequence[PayloadFieldSegment] = (),
    resource_id: str = "sovereign-resource",
    shared_packs: Sequence[str] = (),
    prefix: str = DEFAULT_PROJECTION_PREFIX,
) -> APIRouter:
    """Create a domain-neutral RolePayloadProjector APIRouter without hardcoded profile data."""
    eff_projector = projector if projector is not None else RolePayloadProjector()
    eff_segments = tuple(default_segments)
    eff_packs = tuple(shared_packs)
    router = APIRouter(prefix=prefix, tags=("role-projection",))

    @router.get("", summary="Project configured PayloadFieldSegments for a target ExchangeStage")
    def project_configured_segments(req: Request) -> WebResponse:
        stage = _parse_stage(req.query("stage", ExchangeStage.CANDIDATE_APPLICATION.value))
        target = req.query("target", "peer-node").strip() or "peer-node"
        if not eff_segments:
            raise WebAppError(
                "No default segments configured; submit segments via POST",
                error_code="EMPTY_PROJECTION_SEGMENTS",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        projected = eff_projector.project(
            resource_id=resource_id,
            target_node_id=target,
            stage=stage,
            segments=eff_segments,
            shared_packs=eff_packs,
        )
        return respond(
            req,
            html_fragment=_render_capsule_card(projected),
            data={"capability": "role_projection", "capsule": projected.to_dict()},
            headers=build_swap_response_headers(trigger="roleProjected"),
        )

    @router.post("", summary="Project caller-supplied PayloadFieldSegments dynamically")
    def project_dynamic_segments(req: Request) -> WebResponse:
        payload = req.json() if req.body else None
        if not isinstance(payload, dict):
            raise WebAppError(
                "Projection payload must be a JSON object",
                error_code="INVALID_PROJECTION_PAYLOAD",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        stage = _parse_stage(str(payload.get("stage", ExchangeStage.CANDIDATE_APPLICATION.value)))
        raw_segs = payload.get("segments")
        if not isinstance(raw_segs, list) or not all(isinstance(s, dict) for s in raw_segs):
            raise WebAppError(
                "Field 'segments' must be a list of segment objects",
                error_code="EMPTY_PROJECTION_SEGMENTS",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        segments = parse_payload_segments(raw_segs)
        raw_packs = payload.get("shared_packs", eff_packs)
        packs = (
            tuple(str(p) for p in raw_packs) if isinstance(raw_packs, list | tuple) else eff_packs
        )
        projected = eff_projector.project(
            resource_id=str(payload.get("resource_id") or resource_id),
            target_node_id=str(payload.get("target_node_id") or "peer-node"),
            stage=stage,
            segments=segments,
            shared_packs=packs,
        )
        return respond(
            req,
            html_fragment=_render_capsule_card(projected),
            data={"capability": "role_projection", "capsule": projected.to_dict()},
            headers=build_swap_response_headers(trigger="roleProjected"),
        )

    return router
