# ABOUTME: FastAPI service exposing the frozen Tox21 model (POST /predict, GET /health).
# ABOUTME: Wraps the same inference implementation as the research CLI; no parallel prediction path.
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from tox21_research.data import TASKS
from tox21_research.inference import load_frozen_predictor, predict_smiles

MAX_BATCH = 512


class PredictRequest(BaseModel):
    smiles: list[str] = Field(..., description="SMILES strings to score")


class PredictionItem(BaseModel):
    index: int
    smiles: str
    valid: bool
    probabilities: Optional[dict[str, float]] = None


class PredictResponse(BaseModel):
    endpoints: list[str]
    model: dict[str, Any]
    predictions: list[PredictionItem]


def create_app(repo_root=None) -> FastAPI:
    """Build the app with the frozen model loaded once at startup."""
    predictor = load_frozen_predictor(repo_root)
    app = FastAPI(
        title="Tox21 frozen-model inference",
        version="1.0.0",
        description="12-endpoint activity probabilities from the frozen LightGBM+ECFP4 model",
    )

    @app.get("/health")
    def health():
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
                smiles=row["smiles"],
                valid=row["valid"],
                probabilities=row["probabilities"],
            )
            for i, row in enumerate(rows)
        ]
        return PredictResponse(endpoints=list(TASKS), model=predictor.meta, predictions=items)

    return app


app = create_app()
