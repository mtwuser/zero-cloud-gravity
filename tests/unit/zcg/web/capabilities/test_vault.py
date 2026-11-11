"""Unit tests for zcg.web.capabilities.vault.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest

from zcg.web.capabilities.vault import LocalFileVault, StoredFileRecord, create_vault_router
from zcg.web.factory import create_web_app
from zcg.web.resilience import DeferredJobQueue

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": headers or [],
    }
    await app(scope, receive, send)
    hdrs = {k.decode("latin1"): v.decode("latin1") for k, v in sent[0].get("headers", [])}
    return int(sent[0]["status"]), hdrs, b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestVault:
    """Verify StoredFileRecord, LocalFileVault containment, multipart upload, and 286 polling."""

    def test_stored_file_record_guard_and_local_vault_missing_blob_handling_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify negative size_bytes rejection, blank filename fallback, and missing blob None."""
        # Arrange
        vault = LocalFileVault(tmp_path)

        # Act
        stored = vault.store(filename="   ", content=b"abc", media_type="")
        (tmp_path / stored.blob_rel_path).unlink()
        missing_blob = vault.read_bytes(stored.id)
        missing_id = vault.read_bytes("unknown")
        with pytest.raises(ValueError, match="size_bytes must be >= 0") as exc_size:
            StoredFileRecord(filename="x.bin", size_bytes=-1, blob_rel_path="blobs/x.bin")

        # Assert
        assert stored.filename == "artifact.bin"
        assert stored.media_type == "application/octet-stream"
        assert missing_blob is None and missing_id is None
        assert exc_size.value is not None

    def test_multipart_and_json_upload_with_cards_list_and_table_views_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify multipart/form-data and JSON uploads plus cards, list, and table HTML views."""
        # Arrange
        tok = "vault-csrf-token"
        app = create_web_app(routers=(create_vault_router(tmp_path),), csrf_token=tok)
        boundary = "zcgVaultBoundary"
        mp_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="spec.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            f"Verified Vault Payload\r\n--{boundary}--\r\n"
        ).encode()
        mp_hdrs = [
            (b"hx-request", b"true"),
            (b"x-zcg-csrf-token", tok.encode()),
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
        ]
        swap = [(b"hx-request", b"true")]

        async def _scenario() -> dict[str, Any]:
            s_mp, _, b_mp = await _call(app, "POST", "/api/vault", headers=mp_hdrs, body=mp_body)
            s_js, _, b_js = await _call(
                app,
                "POST",
                "/api/vault",
                body=json.dumps({"filename": "doc.md", "content": "# Doc"}).encode(),
            )
            _, _, b_cards = await _call(app, "GET", "/api/vault", query="view=cards", headers=swap)
            _, _, b_list = await _call(app, "GET", "/api/vault", query="view=list", headers=swap)
            _, _, b_table = await _call(app, "GET", "/api/vault", query="view=table", headers=swap)
            _, _, b_json = await _call(app, "GET", "/api/vault")
            return {
                "s_mp": s_mp,
                "b_mp": b_mp,
                "s_js": s_js,
                "js": json.loads(b_js),
                "cards": b_cards,
                "list": b_list,
                "table": b_table,
                "list_json": json.loads(b_json),
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert out["s_mp"] == 201 and b"spec.txt" in out["b_mp"]
        assert out["s_js"] == 201 and out["js"]["uploaded"]["filename"] == "doc.md"
        assert b"zcg-card-grid" in out["cards"]
        assert b"zcg-list" in out["list"]
        assert b"zcg-table" in out["table"]
        assert out["list_json"]["count"] == 2

    def test_download_sha256_integrity_and_delete_json_and_swap_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify binary download headers/digest and JSON + partial-swap file deletion."""
        # Arrange
        tok = "vault-del-token"
        app = create_web_app(routers=(create_vault_router(tmp_path),), csrf_token=tok)
        swap_csrf = [(b"hx-request", b"true"), (b"x-zcg-csrf-token", tok.encode())]
        expected_sha = hashlib.sha256(b"payload-1").hexdigest()

        async def _scenario() -> dict[str, Any]:
            _, _, c1 = await _call(
                app,
                "POST",
                "/api/vault",
                body=json.dumps({"filename": "a.txt", "content": "payload-1"}).encode(),
            )
            _, _, c2 = await _call(
                app,
                "POST",
                "/api/vault",
                body=json.dumps({"filename": "b.txt", "content": "payload-2"}).encode(),
            )
            id1 = json.loads(c1)["uploaded"]["id"]
            id2 = json.loads(c2)["uploaded"]["id"]
            s_dl, h_dl, b_dl = await _call(app, "GET", f"/api/vault/{id1}/download")
            s_del1, _, b_del1 = await _call(app, "DELETE", f"/api/vault/{id1}")
            s_del2, _, b_del2 = await _call(app, "DELETE", f"/api/vault/{id2}", headers=swap_csrf)
            return {
                "s_dl": s_dl,
                "sha": h_dl.get("x-content-sha256"),
                "b_dl": b_dl,
                "s_del1": s_del1,
                "del1": json.loads(b_del1),
                "s_del2": s_del2,
                "b_del2": b_del2,
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert out["s_dl"] == 200 and out["b_dl"] == b"payload-1"
        assert out["sha"] == expected_sha
        assert out["s_del1"] == 200 and out["del1"]["deleted"] is True
        assert out["s_del2"] == 200 and out["b_del2"] == b""

    def test_deferred_job_auto_id_idempotent_repost_and_http_286_poll_stop_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify auto-generated job IDs, idempotent registration, and HTTP 200 -> 286 polling."""
        # Arrange
        queue = DeferredJobQueue()
        app = create_web_app(routers=(create_vault_router(tmp_path, job_queue=queue),))

        async def _scenario() -> dict[str, Any]:
            _, _, b_auto = await _call(app, "POST", "/api/vault/jobs", body=b"[]")
            _, _, b_reg1 = await _call(
                app, "POST", "/api/vault/jobs", body=json.dumps({"task_id": "idx-01"}).encode()
            )
            _, _, b_reg2 = await _call(
                app, "POST", "/api/vault/jobs", body=json.dumps({"task_id": "idx-01"}).encode()
            )
            s_p200, _, _ = await _call(app, "GET", "/api/vault/jobs/idx-01")
            await _call(
                app,
                "POST",
                "/api/vault/jobs",
                body=json.dumps({"task_id": "idx-01", "progress": 1.0}).encode(),
            )
            s_p286, _, b_p286 = await _call(app, "GET", "/api/vault/jobs/idx-01")
            return {
                "auto_id": json.loads(b_auto)["task_id"],
                "id1": json.loads(b_reg1)["task_id"],
                "id2": json.loads(b_reg2)["task_id"],
                "s_p200": s_p200,
                "s_p286": s_p286,
                "p286": json.loads(b_p286),
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert len(out["auto_id"]) == 36
        assert out["id1"] == "idx-01" and out["id2"] == "idx-01"
        assert out["s_p200"] == 200
        assert out["s_p286"] == 286 and out["p286"]["done"] is True

    def test_bipolar_upload_validation_csrf_and_404_error_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 403 CSRF, 400 non-dict JSON, 422 missing file/filename, and 404 missing IDs."""
        # Arrange
        app = create_web_app(routers=(create_vault_router(tmp_path),))
        boundary = "emptyBoundary"
        mp_no_file = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="note"\r\n\r\n'
            f"text\r\n--{boundary}--\r\n"
        ).encode()
        mp_hdr = [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())]

        async def _scenario() -> tuple[int, int, int, int, int, int, int, int]:
            s_csrf, _, _ = await _call(
                app, "POST", "/api/vault", headers=[(b"hx-request", b"true")], body=b"{}"
            )
            s_400, _, _ = await _call(app, "POST", "/api/vault", body=b"[1]")
            s_422_json, _, _ = await _call(app, "POST", "/api/vault", body=b"")
            s_422_mp, _, _ = await _call(app, "POST", "/api/vault", headers=mp_hdr, body=mp_no_file)
            s_dl_404, _, _ = await _call(app, "GET", "/api/vault/missing/download")
            s_del_404, _, _ = await _call(app, "DELETE", "/api/vault/missing")
            s_job_upd_404, _, _ = await _call(
                app,
                "POST",
                "/api/vault/jobs",
                body=json.dumps({"task_id": "x", "progress": 0.5}).encode(),
            )
            s_job_poll_404, _, _ = await _call(app, "GET", "/api/vault/jobs/missing")
            return (
                s_csrf,
                s_400,
                s_422_json,
                s_422_mp,
                s_dl_404,
                s_del_404,
                s_job_upd_404,
                s_job_poll_404,
            )

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (403, 400, 422, 422, 404, 404, 404, 404)
