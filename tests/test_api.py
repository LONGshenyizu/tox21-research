# ABOUTME: API and deployment tests for the FastAPI service wrapping the frozen Tox21 model.
# ABOUTME: Verifies schema stability, edge-case inputs, determinism across restarts, and
# ABOUTME: molecule-level agreement between the API and the frozen research inference path.
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tox21_research.api import MAX_BATCH, create_app
from tox21_research.data import TASKS
from tox21_research.inference import load_frozen_predictor, predict_smiles

ROOT = Path(__file__).resolve().parents[1]
SMOKE_SMILES = [
    "CCOc1ccc2nc(S(N)(=O)=O)sc2c1",                       # benzothiazole sulfonamide
    "C[C@]12CC[C@H]3C[C@H]([C@@H]1CC[C@@]2(C)O)CCC3=O",  # testosterone-like steroid
    "CC(=O)Oc1ccccc1C(=O)O",                              # aspirin
    "O=C([O-])c1cc(C(=O)O)cc(S(=O)(=O)[O-])c1.[Na+].[Na+]",  # mixture + charged
    "C[N+](C)(C)CC(=O)[O-]",                              # zwitterion
]


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


class TestHealth:
    def test_health_reports_loaded_model(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["model_loaded"] is True
        assert body["n_endpoints"] == 12
        assert body["family"] == "lgbm_ecfp4"


class TestSchema:
    def test_endpoint_order_complete_and_stable(self, client):
        r = client.post("/predict", json={"smiles": ["CCO"]})
        assert r.status_code == 200
        body = r.json()
        assert body["endpoints"] == TASKS
        assert set(body.keys()) == {"endpoints", "model", "predictions"}
        item = body["predictions"][0]
        assert set(item.keys()) == {"index", "smiles", "valid", "probabilities"}
        assert list(item["probabilities"].keys()) == TASKS

    def test_probabilities_valid_range(self, client):
        r = client.post("/predict", json={"smiles": SMOKE_SMILES})
        for item in r.json()["predictions"]:
            for value in item["probabilities"].values():
                assert 0.0 <= value <= 1.0

    def test_model_metadata(self, client):
        meta = client.post("/predict", json={"smiles": ["CCO"]}).json()["model"]
        assert meta["family"] == "lgbm_ecfp4"
        assert meta["feature_set"] == "ecfp4"
        assert meta["seeds"] == [42]


class TestInputs:
    def test_invalid_smiles_marked_not_crashing(self, client):
        r = client.post("/predict", json={"smiles": ["CCO", "not_a_smiles", "CC(=O)O"]})
        assert r.status_code == 200
        preds = r.json()["predictions"]
        assert [p["valid"] for p in preds] == [True, False, True]
        assert preds[1]["probabilities"] is None

    def test_empty_string_invalid(self, client):
        r = client.post("/predict", json={"smiles": [""]})
        assert r.status_code == 200
        assert r.json()["predictions"][0]["valid"] is False

    def test_empty_list(self, client):
        r = client.post("/predict", json={"smiles": []})
        assert r.status_code == 200
        assert r.json()["predictions"] == []

    def test_duplicates_get_identical_results(self, client):
        r = client.post("/predict", json={"smiles": ["CCO", "CCO"]})
        preds = r.json()["predictions"]
        assert [p["index"] for p in preds] == [0, 1]
        assert preds[0]["probabilities"] == preds[1]["probabilities"]

    def test_mixture_charged_stereo_valid(self, client):
        r = client.post("/predict", json={"smiles": SMOKE_SMILES})
        assert all(p["valid"] for p in r.json()["predictions"])

    def test_oversized_batch_rejected(self, client):
        r = client.post("/predict", json={"smiles": ["CCO"] * (MAX_BATCH + 1)})
        assert r.status_code == 413

    def test_malformed_body_rejected(self, client):
        assert client.post("/predict", json={"smiles": "CCO"}).status_code == 422
        assert client.post("/predict", json={}).status_code == 422
        assert client.post("/predict", data="not json",
                           headers={"Content-Type": "application/json"}).status_code == 422

    def test_oversized_single_smiles_invalid(self, client):
        r = client.post("/predict", json={"smiles": ["C" * 20000]})
        assert r.status_code == 200
        assert r.json()["predictions"][0]["valid"] is False


class TestResearchConsistency:
    def test_api_matches_frozen_inference_module(self, client):
        predictor = load_frozen_predictor()
        expected = predict_smiles(predictor, SMOKE_SMILES)
        got = client.post("/predict", json={"smiles": SMOKE_SMILES}).json()["predictions"]
        for row, item in zip(expected, got):
            assert item["valid"] == row["valid"]
            if row["valid"]:
                for task in TASKS:
                    assert item["probabilities"][task] == pytest.approx(row["probabilities"][task], abs=0.0)

    def test_api_matches_research_cli(self, client, tmp_path):
        smiles_file = tmp_path / "in.smiles"
        out_file = tmp_path / "out.csv"
        smiles_file.write_text("\n".join(SMOKE_SMILES), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "predict.py"),
             str(smiles_file), str(out_file)],
            capture_output=True, text=True, cwd=ROOT, check=True,
        )
        import pandas as pd
        cli = pd.read_csv(out_file, index_col=0)
        got = client.post("/predict", json={"smiles": SMOKE_SMILES}).json()["predictions"]
        for item in got:
            for task in TASKS:
                assert item["probabilities"][task] == pytest.approx(
                    float(cli.loc[item["smiles"], task]), rel=1e-12, abs=1e-15
                )

    def test_known_molecule_sanity(self, client):
        steroid = SMOKE_SMILES[1]
        probs = client.post("/predict", json={"smiles": [steroid]}).json()["predictions"][0]["probabilities"]
        assert probs["NR-AR"] > 0.5  # frozen model predicts androgen activity for the steroid
        aspirin = SMOKE_SMILES[2]
        probs2 = client.post("/predict", json={"smiles": [aspirin]}).json()["predictions"][0]["probabilities"]
        assert max(probs2.values()) < 0.01


class TestDeterminism:
    def test_restart_determinism(self, client):
        first = client.post("/predict", json={"smiles": SMOKE_SMILES}).json()
        with TestClient(create_app()) as second_client:
            second = second_client.post("/predict", json={"smiles": SMOKE_SMILES}).json()
        assert first["predictions"] == second["predictions"]

    def test_repeated_request_identical(self, client):
        r1 = client.post("/predict", json={"smiles": SMOKE_SMILES}).json()
        r2 = client.post("/predict", json={"smiles": SMOKE_SMILES}).json()
        assert r1 == r2
