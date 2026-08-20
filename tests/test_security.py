# ABOUTME: Regression tests for the security-hardening fixes (audit findings F2, F1, P1, F3, F4, F5).
# ABOUTME: Each test class maps to one finding in reports/security_remediation.md; before/after
# ABOUTME: behavior is documented per class so the fix intent stays auditable.
import json

import pytest
from fastapi.testclient import TestClient

from tox21_research.api import MAX_BODY_BYTES, create_app

JSON_HEADERS = {"Content-Type": "application/json"}
# F1 audit PoC payload: 9,998 chars of alternating ring closures, ~3.4 s CPU per string pre-fix.
PATHOLOGICAL = "C1=C" * 2499 + "C1"


def post_raw(client, payload):
    """POST a JSON body sent as raw bytes (lets tests embed lone surrogates)."""
    body = json.dumps(payload, ensure_ascii=True).encode("ascii")
    return client.post("/predict", content=body, headers=JSON_HEADERS)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


class TestBodySizeLimit:
    """F2: bodies over MAX_BODY_BYTES must be rejected 413 before the app parses them."""

    def test_body_over_cap_rejected_413(self, client):
        # ~2.6 MB of JSON: far over the cap, previously parsed fully and answered 200/413 late.
        r = post_raw(client, {"smiles": ["C" * 5000] * 512})
        assert r.status_code == 413
        assert "too large" in r.text.lower()

    def test_body_under_cap_accepted(self, client):
        r = post_raw(client, {"smiles": ["CCO"]})
        assert r.status_code == 200

    def test_content_length_over_cap_rejected_without_invoking_app(self):
        from tox21_research.api import BodySizeLimitMiddleware

        invoked = []

        async def app(scope, receive, send):
            invoked.append(True)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        captured = []

        async def send(message):
            captured.append(message)

        async def receive():
            raise AssertionError("body must not be read when Content-Length already exceeds the cap")

        scope = {
            "type": "http", "asgi": {"version": "2.0"}, "http_version": "1.1",
            "method": "POST", "path": "/predict",
            "headers": [(b"content-length", str(MAX_BODY_BYTES + 1).encode())],
        }

        async def run():
            await BodySizeLimitMiddleware(app, MAX_BODY_BYTES)(scope, receive, send)

        import anyio

        anyio.run(run)
        assert not invoked, "app must not run when Content-Length exceeds the cap"
        assert captured[0]["type"] == "http.response.start"
        assert captured[0]["status"] == 413

    def test_streamed_body_without_content_length_aborted_at_cap(self):
        from tox21_research.api import BodySizeLimitMiddleware

        read = {"count": 0}
        completed = []

        async def app(scope, receive, send):
            # like starlette's Request.body(): loop until more_body is False
            while True:
                message = await receive()
                if not message.get("more_body"):
                    completed.append(True)
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})

        captured = []

        async def send(message):
            captured.append(message)

        chunks = [
            {"type": "http.request", "body": b"x" * 100, "more_body": True},
            {"type": "http.request", "body": b"x" * 100, "more_body": True},
            {"type": "http.request", "body": b"x" * 100, "more_body": False},
        ]

        async def receive():
            message = chunks[min(read["count"], len(chunks) - 1)]
            read["count"] += 1
            return message

        scope = {"type": "http", "asgi": {"version": "2.0"}, "http_version": "1.1",
                 "method": "POST", "path": "/predict", "headers": []}

        async def run():
            # cap 150: second 100-byte chunk crosses it, third chunk must never arrive
            await BodySizeLimitMiddleware(app, 150)(scope, receive, send)

        import anyio

        anyio.run(run)
        assert not completed, "body read loop must abort instead of consuming the stream"
        assert read["count"] == 2
        assert captured[0]["type"] == "http.response.start"
        assert captured[0]["status"] == 413
