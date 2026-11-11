"""Content-Addressed Binary Blob & Multipart Transport Engine ('LocalFileVault', 'APIRouter').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import (
    DomainEntity,
    NaturalText,
    generate_identifier,
    validate_natural_text,
)
from zcg.core.manifests import ensure_contained_path
from zcg.core.sqlite_repo import SQLiteRepositoryAdapter
from zcg.web.capabilities.crud import CollectionLayout
from zcg.web.channels import DeliveryChannel, Tier, build_swap_response_headers
from zcg.web.components import (
    render_card,
    render_card_grid,
    render_file_dropzone,
    render_item_list,
    render_progress_bar,
    render_table,
)
from zcg.web.request import Request, WebResponse, respond, respond_empty, respond_poll
from zcg.web.resilience import DeferredJobQueue, DeferredTaskStatus
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

DEFAULT_VAULT_DB_REL_PATH: Final[str] = ".agents/telemetry/files_vault.sqlite3"
DEFAULT_VAULT_BLOBS_REL_DIR: Final[str] = ".agents/telemetry/vault_blobs"
DEFAULT_VAULT_PREFIX: Final[str] = "/api/vault"
DEFAULT_FILE_CONTENT_TYPE: Final[str] = "application/octet-stream"


@dataclass(frozen=True, kw_only=True)
class StoredFileRecord(DomainEntity):
    """Immutable L1 domain entity describing a content-addressed file in the local vault."""

    filename: NaturalText
    media_type: NaturalText = DEFAULT_FILE_CONTENT_TYPE
    size_bytes: int = 0
    sha256_hex: str = ""
    blob_rel_path: NaturalText

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "filename", validate_natural_text(self.filename))
        object.__setattr__(self, "media_type", validate_natural_text(self.media_type))
        object.__setattr__(self, "blob_rel_path", validate_natural_text(self.blob_rel_path))
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes must be >= 0, got {self.size_bytes}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize stored file metadata into a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256_hex": self.sha256_hex,
            "blob_rel_path": self.blob_rel_path,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FileVaultRepository(SQLiteRepositoryAdapter[StoredFileRecord, str]):
    """Parameterized SQLite WAL repository adapter for StoredFileRecord metadata."""

    table_name = "stored_files"

    def to_record(self, entity: StoredFileRecord) -> dict[str, Any]:
        """Serialize StoredFileRecord for SQLite WAL persistence."""
        return entity.to_dict()

    def from_record(self, record: Mapping[str, Any]) -> StoredFileRecord:
        """Hydrate an immutable StoredFileRecord from stored JSON fields."""
        return StoredFileRecord(
            id=str(record["id"]),
            filename=str(record["filename"]),
            media_type=str(record.get("media_type", DEFAULT_FILE_CONTENT_TYPE)),
            size_bytes=int(record.get("size_bytes", 0)),
            sha256_hex=str(record.get("sha256_hex", "")),
            blob_rel_path=str(record["blob_rel_path"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
        )


class LocalFileVault:
    """Path-contained local file vault pairing SQLite WAL metadata with SHA-256 blobs."""

    def __init__(
        self,
        workspace_dir: Path,
        *,
        rel_db_path: str = DEFAULT_VAULT_DB_REL_PATH,
        rel_blobs_dir: str = DEFAULT_VAULT_BLOBS_REL_DIR,
    ) -> None:
        self._ws = workspace_dir.resolve()
        self._blobs_dir = ensure_contained_path(self._ws / rel_blobs_dir, self._ws)
        self._blobs_dir.mkdir(parents=True, exist_ok=True)
        self._repo = FileVaultRepository(self._ws / rel_db_path, workspace_root=self._ws)

    @property
    def repository(self) -> FileVaultRepository:
        """Return underlying SQLite WAL metadata repository."""
        return self._repo

    def store(
        self, *, filename: str, content: bytes, media_type: str = DEFAULT_FILE_CONTENT_TYPE
    ) -> StoredFileRecord:
        """Store file bytes under contained vault directory and record SHA-256 metadata."""
        safe_name = Path(filename.replace("\\", "/")).name.strip() or "artifact.bin"
        rec_id = generate_identifier()
        blob_path = ensure_contained_path(
            self._blobs_dir / f"{rec_id}_{safe_name}", self._blobs_dir
        )
        blob_path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        entity = StoredFileRecord(
            id=rec_id,
            filename=safe_name,
            media_type=media_type or DEFAULT_FILE_CONTENT_TYPE,
            size_bytes=len(content),
            sha256_hex=digest,
            blob_rel_path=str(blob_path.relative_to(self._ws)),
        )
        return self._repo.create(entity)

    def read_bytes(self, file_id: str) -> tuple[StoredFileRecord, bytes] | None:
        """Fetch stored file metadata and raw bytes, or None when absent."""
        rec = self._repo.get_by_id(file_id)
        if rec is None:
            return None
        blob_path = ensure_contained_path(self._ws / rec.blob_rel_path, self._blobs_dir)
        if not blob_path.is_file():
            return None
        return rec, blob_path.read_bytes()

    def remove(self, file_id: str) -> bool:
        """Delete file blob and SQLite metadata record, returning True when removed."""
        rec = self._repo.get_by_id(file_id)
        if rec is None:
            return False
        blob_path = ensure_contained_path(self._ws / rec.blob_rel_path, self._blobs_dir)
        blob_path.unlink(missing_ok=True)
        return self._repo.delete(file_id)


def _extract_upload_inputs(req: Request) -> tuple[str, bytes, str]:
    if "multipart/form-data" in req.content_type.lower():
        up = req.multipart().get_file("file")
        if up is None:
            raise WebAppError(
                "Multipart upload requires a 'file' field",
                error_code="MISSING_UPLOAD_FILE",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        return up.filename, up.data, up.content_type
    parsed = req.json() if req.body else {}
    if not isinstance(parsed, dict):
        raise WebAppError(
            "File upload payload must be a JSON object",
            error_code="INVALID_FILE_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    fname = str(parsed.get("filename", "")).strip()
    if not fname:
        raise WebAppError(
            "Field 'filename' is required",
            error_code="MISSING_UPLOAD_FILE",
            http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    raw_content = str(parsed.get("content", "")).encode()
    mtype = str(parsed.get("media_type", DEFAULT_FILE_CONTENT_TYPE))
    return fname, raw_content, mtype


def _render_vault_items(rows: list[dict[str, Any]], view: str) -> SafeHTML:
    if view == CollectionLayout.CARDS.value:
        return render_card_grid(
            items=rows,
            title_key="filename",
            body_key="sha256_hex",
            subtitle_key="media_type",
            badge_key="size_bytes",
            empty_message="Vault is empty.",
        )
    if view == CollectionLayout.LIST.value:
        return render_item_list(
            items=rows,
            title_key="filename",
            meta_key="media_type",
            badge_key="size_bytes",
            empty_message="Vault is empty.",
        )
    return render_table(
        columns=(
            ("filename", "Filename"),
            ("media_type", "Media Type"),
            ("size_bytes", "Bytes"),
        ),
        rows=rows,
        empty_message="Vault is empty.",
    )


def create_vault_router(
    workspace_dir: Path,
    *,
    job_queue: DeferredJobQueue | None = None,
    prefix: str = DEFAULT_VAULT_PREFIX,
    target_selector: str = "#v_out",
) -> APIRouter:
    """Create a domain-neutral File Vault APIRouter with multipart upload and T2 polling."""
    vault = LocalFileVault(workspace_dir)
    eff_queue = job_queue if job_queue is not None else DeferredJobQueue()
    router = APIRouter(prefix=prefix, tags=("vault",))

    @router.get("", summary="List files stored in the workspace vault")
    def list_files(req: Request) -> WebResponse:
        view = req.query("view", CollectionLayout.TABLE.value).lower()
        items = vault.repository.list_all()
        rows = [f.to_dict() for f in items]
        body_html = SafeHTML(
            render_file_dropzone(action_url=prefix, target_selector=target_selector).value
            + _render_vault_items(rows, view).value
        )
        frag = render_card(title="File Vault", badge=str(len(items)), body=body_html)
        return respond(
            req,
            html_fragment=frag.value,
            data={"capability": "vault", "count": len(items), "files": rows},
        )

    @router.post("", summary="Upload file into workspace vault")
    def upload_file(req: Request) -> WebResponse:
        fname, content, mtype = _extract_upload_inputs(req)
        saved = vault.store(filename=fname, content=content, media_type=mtype)
        frag = render_card(
            title=saved.filename,
            subtitle=saved.media_type,
            badge=f"{saved.size_bytes} B",
            body=saved.sha256_hex,
            card_id=f"file-{saved.id}",
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={"capability": "vault", "uploaded": saved.to_dict()},
            status=int(HTTPStatus.CREATED),
            headers=build_swap_response_headers(trigger="fileUploaded"),
        )

    @router.get("/{file_id}/download", channel=DeliveryChannel.STATIC_SYNC, summary="Download file")
    def download_file(req: Request) -> WebResponse:
        file_id = req.path_params["file_id"]
        loaded = vault.read_bytes(file_id)
        if loaded is None:
            raise WebAppError(
                f"Stored file not found: {file_id}",
                error_code="FILE_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        rec, raw_bytes = loaded
        hdrs = {
            "content-disposition": f'attachment; filename="{rec.filename}"',
            "x-content-sha256": rec.sha256_hex,
        }
        return WebResponse(
            int(HTTPStatus.OK), rec.media_type, raw_bytes, DeliveryChannel.STATIC_SYNC, hdrs
        )

    @router.delete("/{file_id}", summary="Delete stored file")
    def delete_file(req: Request) -> WebResponse:
        file_id = req.path_params["file_id"]
        if not vault.remove(file_id):
            raise WebAppError(
                f"Stored file not found: {file_id}",
                error_code="FILE_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        hdrs = build_swap_response_headers(trigger="fileDeleted")
        if req.is_partial_swap:
            return respond_empty(headers=hdrs)
        return respond(
            req,
            html_fragment="",
            data={"capability": "vault", "deleted": True, "id": file_id},
            headers=hdrs,
        )

    @router.post("/jobs", summary="Register or update a T2 vault job")
    def manage_vault_job(req: Request) -> WebResponse:
        payload = req.json() if req.body else {}
        data = payload if isinstance(payload, dict) else {}
        tid = str(data.get("task_id") or "").strip() or generate_identifier()
        raw_prog = data.get("progress")
        if raw_prog is not None:
            if eff_queue.get(tid) is None:
                raise WebAppError(
                    f"Vault job not found: {tid}",
                    error_code="FILE_JOB_NOT_FOUND",
                    http_status=int(HTTPStatus.NOT_FOUND),
                    severity=ErrorSeverity.WARNING,
                )
            rec = eff_queue.update_progress(tid, float(raw_prog))
        else:
            rec = eff_queue.get(tid) or eff_queue.register(tid, tier=Tier.T2)
        prog = render_progress_bar(
            progress_ratio=rec.progress,
            label=rec.task_id,
            poll_url=f"{prefix}/jobs/{rec.task_id}",
        ).value
        return respond(
            req,
            html_fragment=prog,
            data={
                "capability": "vault",
                "task_id": rec.task_id,
                "status": rec.status.value,
                "progress": rec.progress,
                "active_jobs": eff_queue.active_count,
            },
        )

    @router.get("/jobs/{task_id}", channel=DeliveryChannel.SWAP_DEFERRED, summary="Poll vault job")
    def poll_vault_job(req: Request) -> WebResponse:
        tid = req.path_params["task_id"]
        rec = eff_queue.get(tid)
        if rec is None:
            raise WebAppError(
                f"Vault job not found: {tid}",
                error_code="FILE_JOB_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        done = rec.status == DeferredTaskStatus.COMPLETED
        frag = render_progress_bar(progress_ratio=rec.progress, label=rec.task_id).value
        return respond_poll(
            req,
            done=done,
            html_fragment=frag,
            data={"capability": "vault", "task_id": rec.task_id, "done": done},
        )

    return router
