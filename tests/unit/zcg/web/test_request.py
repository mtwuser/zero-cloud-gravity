"""Unit tests for zcg.web.request.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json

import pytest

from zcg.web.channels import DeliveryChannel
from zcg.web.request import (
    Message,
    Request,
    Scope,
    read_bounded_body,
    respond,
    respond_empty,
    respond_poll,
)
from zcg.web.security import WebAppError


def _make_scope(
    method: str = "GET",
    path: str = "/",
    query: str = "",
    headers: dict[str, str] | None = None,
) -> Scope:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
    }


class TestRequest:
    """Verify Request properties, JSON/form/multipart parsers, body bounds, and respond helpers."""

    def test_request_properties_cookies_json_form_and_bounded_body_expected(self) -> None:
        """Verify Request metadata, cookies, JSON/form parsing, and 413 payload size caps."""
        # Arrange
        scope = _make_scope(
            "post",
            "/items/%20alpha",
            query="page=2&empty=",
            headers={
                "cookie": "zcg_csrf=t1; zcg_session=s1",
                "content-type": "application/x-www-form-urlencoded",
                "hx-request": "true",
                "hx-boosted": "true",
                "hx-target": "#list",
            },
        )
        req = Request(scope, b"title=Note+One&tag=a&tag=b", path_params={"slug": "alpha"})
        empty_req = Request(_make_scope())
        bad_json_req = Request(_make_scope("POST"), b"{bad")

        async def _run_body_checks() -> bytes:
            chunks = [b"hello ", b"world"]
            idx = 0

            async def _recv() -> Message:
                nonlocal idx
                part = chunks[idx]
                idx += 1
                return {"type": "http.request", "body": part, "more_body": idx < len(chunks)}

            ok = await read_bounded_body(_recv, {"content-length": "11"}, 32)
            with pytest.raises(WebAppError, match="exceeds 4 bytes"):
                await read_bounded_body(_recv, {"content-length": "99"}, 4)

            idx = 0
            with pytest.raises(WebAppError, match="exceeds 8 bytes"):
                await read_bounded_body(_recv, {}, 8)
            return ok

        # Act
        body_ok = asyncio.run(_run_body_checks())
        json_val = Request(_make_scope("POST"), b'{"count":3}').json()

        # Assert
        assert body_ok == b"hello world"
        assert json_val == {"count": 3}
        assert req.method == "POST"
        assert req.path == "/items/ alpha"
        assert req.raw_query == "page=2&empty="
        assert req.query_params["page"] == ["2"]
        assert req.query("page") == "2" and req.query("missing", "1") == "1"
        assert req.path_params == {"slug": "alpha"}
        assert req.headers["hx-target"] == "#list"
        assert req.cookies == {"zcg_csrf": "t1", "zcg_session": "s1"}
        assert req.body == b"title=Note+One&tag=a&tag=b"
        assert req.content_type == "application/x-www-form-urlencoded"
        assert req.is_partial_swap is True and req.is_boosted is True
        assert req.swap_target == "#list"
        assert req.form() == {"title": "Note One", "tag": "a"}
        assert req.form_multi()["tag"] == ["a", "b"]
        assert empty_req.cookies == {} and empty_req.form() == {}
        with pytest.raises(WebAppError, match="Invalid JSON"):
            bad_json_req.json()

    def test_multipart_form_data_upload_sanitization_and_guards_expected(self) -> None:
        """Verify stdlib BytesFeedParser multipart extraction, filename sanitization, and 400."""
        # Arrange
        boundary = "----ZCGTestBoundary99"
        raw_mp = (
            f"--{boundary}\r\n"
            "Content-Disposition: form-data\r\n\r\nignored\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="title"\r\n\r\nSpec Document\r\n'
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="doc"; filename="../../etc/guide.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\nPDFDATA\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="anon"; filename=""\r\n'
            "Content-Type: application/octet-stream\r\n\r\nRAW\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        mp_req = Request(
            _make_scope(
                "POST",
                "/files",
                headers={"content-type": f"multipart/form-data; boundary={boundary}"},
            ),
            raw_mp,
        )
        bad_mp_req = Request(
            _make_scope("POST", "/files", headers={"content-type": "text/plain"}), b"abc"
        )

        # Act
        parsed = mp_req.multipart()
        doc_file = parsed.get_file("doc")
        anon_file = parsed.get_file("anon")

        # Assert
        assert parsed.get_field("title") == "Spec Document"
        assert parsed.get_field("absent", "fallback") == "fallback"
        assert parsed.get_file("absent") is None
        assert doc_file is not None and doc_file.filename == "guide.pdf"
        assert doc_file.size == 7 and doc_file.content_type == "application/pdf"
        assert anon_file is not None and anon_file.filename == "upload.bin"
        with pytest.raises(WebAppError, match="Expected multipart/form-data"):
            bad_mp_req.multipart()

    def test_respond_respond_poll_and_respond_empty_channels_expected(self) -> None:
        """Verify adaptive partial HTML, full HTML, JSON, HTTP 286 poll, and empty responses."""
        # Arrange
        req_swap = Request(_make_scope("GET", "/notes", headers={"hx-request": "true"}))
        req_boost = Request(
            _make_scope("GET", "/notes", headers={"hx-request": "true", "hx-boosted": "true"})
        )
        req_api = Request(_make_scope("GET", "/notes"))

        # Act
        r_frag = respond(req_swap, html_fragment="<li>A</li>", full_html="<html>Full</html>")
        r_boost_full = respond(req_boost, html_fragment="<li>A</li>", full_html="<html>Full</html>")
        r_boost_frag = respond(req_boost, html_fragment="<li>A</li>")
        r_full = respond(req_api, html_fragment="<li>A</li>", full_html="<html>Full</html>")
        r_json = respond(req_api, html_fragment="<li>A</li>", data={"items": ["A"]})
        r_poll_html = respond_poll(req_swap, done=True, html_fragment="<div>Done</div>")
        r_poll_json = respond_poll(req_api, done=False, html_fragment="<div>Wait</div>")
        r_empty = respond_empty(headers={"hx-trigger": "deleted"})

        # Assert
        assert r_frag.channel == DeliveryChannel.SWAP_SYNC and r_frag.body == b"<li>A</li>"
        assert r_boost_full.channel == DeliveryChannel.ISLAND_SYNC
        assert r_boost_full.body == b"<html>Full</html>"
        assert r_boost_frag.channel == DeliveryChannel.SWAP_SYNC
        assert r_full.body == b"<html>Full</html>"
        assert json.loads(r_json.body) == {"items": ["A"]}
        assert r_poll_html.status == 286 and r_poll_html.channel == DeliveryChannel.SWAP_DEFERRED
        assert r_poll_json.status == 200 and json.loads(r_poll_json.body)["done"] is False
        assert r_empty.body == b"" and r_empty.headers["hx-trigger"] == "deleted"
