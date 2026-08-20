# ABOUTME: FastAPI service exposing the frozen Tox21 model (POST /predict, GET /health).
# ABOUTME: Wraps the same inference implementation as the research CLI; no parallel prediction path.
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rdkit import RDLogger

from tox21_research.data import TASKS
from tox21_research.inference import load_frozen_predictor, predict_smiles

MAX_BATCH = 512
MAX_BODY_BYTES = 2 * 1024 * 1024


class _BodyTooLargeError(Exception):
    """Internal signal: the request body crossed the byte cap mid-stream."""


class BodySizeLimitMiddleware:
    """Reject requests whose body exceeds max_bytes (413) before the app buffers it.

    Content-Length is checked first so oversized declared bodies are refused
    without reading; streaming bodies without a length are counted and cut off
    at the cap. Bounded bodies also bound the response, which echoes its input.
    """

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = Headers(scope=scope).get("content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await self._send_too_large(scope, receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if response_started:
                raise
            await self._send_too_large(scope, receive, send)

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("request body too large", status_code=413)
        await response(scope, receive, send)


class PredictRequest(BaseModel):
    smiles: list[str] = Field(
        ...,
        description="SMILES strings to score; each item is capped at 512 characters "
        "and 64 ring-closure digits, beyond which it is reported as invalid",
    )


class PredictionItem(BaseModel):
    index: int
    smiles: str
    valid: bool
    probabilities: Optional[dict[str, float]] = None


class PredictResponse(BaseModel):
    endpoints: list[str]
    model: dict[str, Any]
    predictions: list[PredictionItem]


def _echo(smiles: str) -> str:
    """Response echo must be UTF-8 encodable; lone surrogates become U+FFFD."""
    return smiles.encode("utf-8", errors="replace").decode("utf-8")


def create_app(repo_root=None, max_body_bytes=MAX_BODY_BYTES) -> FastAPI:
    """Build the app with the frozen model loaded once at startup."""
    # RDKit echoes unparsable input verbatim to stderr; keep raw request bytes
    # out of the service log (the research scripts disable the same channel).
    RDLogger.DisableLog("rdApp.*")
    predictor = load_frozen_predictor(repo_root)
    app = FastAPI(
        title="Tox21 frozen-model inference",
        version="1.0.0",
        description="12-endpoint activity probabilities from the frozen LightGBM+ECFP4 model",
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_body_bytes)

    @app.get("/health")
    async def health():
        # async: served on the event loop so it never queues behind threadpool work
        return {
            "status": "ok",
            "model_loaded": True,
            "family": predictor.meta["family"],
            "feature_set": predictor.meta["feature_set"],
            "n_endpoints": len(TASKS),
        }

    @app.post("/predict", response_model=PredictResponse)
    async def predict(request: PredictRequest):
        if len(request.smiles) > MAX_BATCH:
            raise HTTPException(
                status_code=413,
                detail=f"batch too large: {len(request.smiles)} > {MAX_BATCH}",
            )
        rows = await run_in_threadpool(predict_smiles, predictor, request.smiles)
        items = [
            PredictionItem(
                index=i,
                smiles=_echo(row["smiles"]),
                valid=row["valid"],
                probabilities=row["probabilities"],
            )
            for i, row in enumerate(rows)
        ]
        return PredictResponse(endpoints=list(TASKS), model=predictor.meta, predictions=items)

    return app


app = create_app()
