# ABOUTME: Regression tests for the security-hardening fixes (audit findings F2, F1, P1, F3, F4, F5).
# ABOUTME: Each test class maps to one finding in reports/security_remediation.md; before/after
# ABOUTME: behavior is documented per class so the fix intent stays auditable.
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tox21_research.api import MAX_BODY_BYTES, create_app
from tox21_research.inference import (
    MAX_RING_CLOSURE_DIGITS,
    MAX_SMILES_LENGTH,
    load_frozen_predictor,
)

ROOT = Path(__file__).resolve().parents[1]

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


class TestSmilesComplexityLimit:
    """F1: inputs beyond the length/ring-closure caps must be marked invalid before parsing.

    Pre-fix behavior: the audit PoC payload parsed (~3.4 s CPU per string) and a
    batch of 8 pinned the CPU for ~26.5 s while starving /health.
    """

    def test_audit_poc_payload_invalid(self, client):
        r = post_raw(client, {"smiles": [PATHOLOGICAL]})
        assert r.status_code == 200
        item = r.json()["predictions"][0]
        assert item["valid"] is False
        assert item["probabilities"] is None

    def test_audit_poc_batch_completes_fast(self, client):
        t0 = time.perf_counter()
        r = post_raw(client, {"smiles": [PATHOLOGICAL] * 8})
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200
        assert all(p["valid"] is False for p in r.json()["predictions"])
        assert elapsed < 5.0  # ~26.5 s of CPU before the fix

    def test_max_batch_of_poison_stays_bounded(self, client):
        # largest pathological batch that still fits under the 2MB body cap:
        # all items invalid at the digit cap, no RDKit parsing
        r = post_raw(client, {"smiles": [PATHOLOGICAL] * 150})
        assert r.status_code == 200
        assert all(p["valid"] is False for p in r.json()["predictions"])

    def test_chemically_valid_chain_over_length_cap_invalid(self, client):
        # "C"*513 is a parsable alkyl chain; the length cap is an input-policy bound
        r = post_raw(client, {"smiles": ["C" * (MAX_SMILES_LENGTH + 1)]})
        assert r.json()["predictions"][0]["valid"] is False

    def test_chemically_valid_rings_over_digit_cap_invalid(self, client):
        # 66 ring-closure digits (reused 3-membered rings) parse fine chemically;
        # only the digit cap rejects them
        payload = "C1CC1" * 33
        assert len(payload) <= MAX_SMILES_LENGTH
        assert sum(c.isdigit() for c in payload) > MAX_RING_CLOSURE_DIGITS
        r = post_raw(client, {"smiles": [payload]})
        assert r.json()["predictions"][0]["valid"] is False

    def test_molecules_within_caps_stay_valid(self, client):
        fused = "C1CC2CCC1CC2"  # 4 ring digits
        steroid = "C[C@]12CC[C@H]3C[C@H]([C@@H]1CC[C@@]2(C)O)CCC3=O"  # 8 ring digits
        r = post_raw(client, {"smiles": [fused, steroid]})
        assert [p["valid"] for p in r.json()["predictions"]] == [True, True]


def copy_frozen_tree(tmp_path):
    """A writable clone of results/final under a fake repo root."""
    shutil.copytree(ROOT / "results" / "final", tmp_path / "results" / "final")
    return tmp_path


class TestModelIntegrity:
    """P1: frozen artifacts are sha256-verified and path-contained before pickle load.

    Pre-fix behavior: load_frozen_predictor joblib.load'ed whatever bytes sat at
    the fixed model paths, with no integrity or containment check.
    """

    def test_valid_copy_loads(self, tmp_path):
        predictor = load_frozen_predictor(copy_frozen_tree(tmp_path))
        assert predictor.meta["family"] == "lgbm_ecfp4"
        assert predictor.meta["seeds"] == [42]

    def test_tampered_model_rejected(self, tmp_path):
        root = copy_frozen_tree(tmp_path)
        model = root / "results" / "final" / "model" / "model_seed42.joblib"
        data = bytearray(model.read_bytes())
        data[-1] ^= 0xFF
        model.write_bytes(bytes(data))
        with pytest.raises(ValueError, match="integrity"):
            load_frozen_predictor(root)

    def test_tampered_config_rejected(self, tmp_path):
        root = copy_frozen_tree(tmp_path)
        config = root / "results" / "final" / "frozen_config.json"
        config.write_text(config.read_text(encoding="utf-8").replace("42", "43"), encoding="utf-8")
        with pytest.raises(ValueError, match="integrity"):
            load_frozen_predictor(root)

    def test_artifact_without_pinned_hash_rejected(self, tmp_path):
        from tox21_research.inference import _verified_artifact, _load_integrity_manifest

        root = copy_frozen_tree(tmp_path)
        with pytest.raises(ValueError, match="pinned sha256"):
            _verified_artifact(root, "model/model_seed999.joblib", _load_integrity_manifest())

    def test_escaping_path_rejected(self, tmp_path):
        from tox21_research.inference import _verified_artifact, _load_integrity_manifest

        root = copy_frozen_tree(tmp_path)
        with pytest.raises(ValueError, match="escapes"):
            _verified_artifact(root, "../../scripts/predict.py", _load_integrity_manifest())


class TestPerItemExceptionIsolation:
    """F3: an input that makes RDKit raise must fail alone, not the whole batch.

    Pre-fix behavior: a lone UTF-16 surrogate crashed the request twice over —
    UnicodeEncodeError inside Chem.MolFromSmiles, and (once that was contained)
    PydanticSerializationError while echoing the surrogate back in the response.
    """

    def test_lone_surrogate_invalid_not_batch_failure(self, client):
        r = post_raw(client, {"smiles": ["CCO", "\ud800", "CCN"]})
        assert r.status_code == 200
        preds = r.json()["predictions"]
        assert [p["valid"] for p in preds] == [True, False, True]
        assert preds[1]["probabilities"] is None
        assert preds[1]["smiles"] == "?"  # stdlib encode-replacement keeps the echo encodable

    def test_normal_echo_unchanged(self, client):
        r = post_raw(client, {"smiles": ["CCO"]})
        assert r.json()["predictions"][0]["smiles"] == "CCO"

    def test_is_valid_smiles_swallows_parse_exceptions(self):
        from tox21_research.inference import is_valid_smiles

        assert is_valid_smiles("\ud800") is False  # UnicodeEncodeError pre-fix
        assert is_valid_smiles("\udfff") is False


class TestLogSecurity:
    """F4: the service must not echo raw input (with newlines) into its log.

    Pre-fix behavior: RDKit printed "SMILES Parse Error: ... <raw input>" to
    stderr, so a payload containing '\\nINFO: ...' forged standalone log lines.
    """

    def test_invalid_input_not_echoed_to_log(self, client, capfd):
        payload = "INJ-START\nINFO:     127.0.0.1 - \"GET /admin HTTP/1.1\" 200 OK"
        r = post_raw(client, {"smiles": [payload]})
        assert r.status_code == 200
        assert r.json()["predictions"][0]["valid"] is False
        captured = capfd.readouterr()
        assert "INJ-START" not in captured.err + captured.out
        assert "SMILES Parse Error" not in captured.err


class TestDocsDisabled:
    """F5: capability-disclosure endpoints must not be exposed.

    Pre-fix behavior: GET /docs, /redoc and /openapi.json returned 200 without
    authentication, publishing the full request schema.
    """

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_docs_endpoints_return_404(self, client, path):
        assert client.get(path).status_code == 404
