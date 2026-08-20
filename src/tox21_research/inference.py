# ABOUTME: Frozen-model batch inference shared by the research CLI and the FastAPI service.
# ABOUTME: Single implementation: ECFP4/MACCS featurization, frozen model files, TASKS endpoint order.
import hashlib
import json
from pathlib import Path
from typing import Callable, NamedTuple

import joblib
import numpy as np
from rdkit import Chem

from tox21_research.data import TASKS
from tox21_research.features import ecfp_matrix, maccs_matrix
from tox21_research.models import MultitaskMLP, predict_per_task

REPO_ROOT = Path(__file__).resolve().parents[2]
# Pinned sha256 of every frozen artifact the loader reads (paths relative to
# results/final). Shipped beside the code so the container image carries it.
INTEGRITY_MANIFEST = Path(__file__).resolve().parent / "model_integrity.json"
# Input-complexity caps for the service path. The frozen dataset maxima are 342
# characters and 28 ring-closure digits (7,831 molecules), so both caps keep a
# wide margin over real chemistry while bounding adversarial parse cost.
MAX_SMILES_LENGTH = 512
MAX_RING_CLOSURE_DIGITS = 64


class FrozenPredictor(NamedTuple):
    """Loaded frozen ensemble: matrix predictor, featurizer, and metadata."""

    predict_matrix: Callable
    featurize: Callable
    meta: dict


def _load_integrity_manifest():
    return json.loads(INTEGRITY_MANIFEST.read_text(encoding="utf-8"))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_artifact(root, relative, manifest):
    """Resolve one frozen artifact under results/final, enforcing directory
    containment and the pinned sha256 before any deserialization."""
    final_dir = (root / "results" / "final").resolve()
    path = (final_dir / relative).resolve()
    if not path.is_relative_to(final_dir):
        raise ValueError(f"frozen artifact escapes results/final: {relative!r}")
    expected = manifest.get(relative)
    if expected is None:
        raise ValueError(f"no pinned sha256 for frozen artifact: {relative!r}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(
            f"frozen artifact integrity failure: {relative!r}: {actual} != {expected}"
        )
    return path


def load_frozen_predictor(repo_root=None) -> FrozenPredictor:
    """Load the frozen ensemble from results/final (config + model files),
    verifying every artifact against the pinned integrity manifest first."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    manifest = _load_integrity_manifest()
    spec = json.loads(
        _verified_artifact(root, "frozen_config.json", manifest).read_text(encoding="utf-8")
    )
    featurize = ecfp_matrix if spec["feature_set"] == "ecfp4" else maccs_matrix
    n_bits = 2048 if spec["feature_set"] == "ecfp4" else 167

    predictors = []
    for seed in spec["seeds"]:
        if spec["family"] == "mlp_ecfp4_multitask":
            import torch

            module = MultitaskMLP(
                n_bits, len(TASKS),
                tuple(spec["params"]["hidden"]), spec["params"]["dropout"],
            )
            module.load_state_dict(
                torch.load(
                    _verified_artifact(root, f"model/model_seed{seed}.pt", manifest),
                    weights_only=True,
                )
            )
            module.eval()
            predictors.append(
                lambda X, m=module: torch.sigmoid(
                    m(torch.as_tensor(np.asarray(X, dtype=torch.float32)))
                ).detach().numpy()
            )
        else:
            models = joblib.load(
                _verified_artifact(root, f"model/model_seed{seed}.joblib", manifest)
            )
            predictors.append(lambda X, ms=models: predict_per_task(ms, X))

    def predict_matrix(X):
        return np.mean([p(X) for p in predictors], axis=0)

    meta = {
        "family": spec["family"],
        "feature_set": spec["feature_set"],
        "seeds": list(spec["seeds"]),
    }
    return FrozenPredictor(predict_matrix, featurize, meta)


def is_valid_smiles(smiles):
    """Same parse criterion the featurizer applies (MolFromSmiles), guarded by
    input-complexity caps (length, ring-closure digits) checked before parsing
    so one string cannot force expensive sanitization work. Parse failures that
    raise (e.g. lone UTF-16 surrogates) count as invalid, never as batch errors."""
    if not isinstance(smiles, str) or not 0 < len(smiles) <= MAX_SMILES_LENGTH:
        return False
    if sum(c.isdigit() for c in smiles) > MAX_RING_CLOSURE_DIGITS:
        return False
    try:
        return Chem.MolFromSmiles(smiles) is not None
    except Exception:
        return False


def predict_smiles(predictor, smiles_list):
    """Per-item results: [{'smiles', 'valid', 'probabilities': {task: p} or None}]."""
    smiles_list = list(smiles_list)
    valid_positions = [i for i, s in enumerate(smiles_list) if is_valid_smiles(s)]
    probs = {}
    if valid_positions:
        X = predictor.featurize([smiles_list[i] for i in valid_positions])
        matrix = predictor.predict_matrix(X)
        for k, i in enumerate(valid_positions):
            probs[i] = {task: float(matrix[k, j]) for j, task in enumerate(TASKS)}
    rows = []
    for i, smiles in enumerate(smiles_list):
        rows.append({
            "smiles": smiles,
            "valid": i in probs,
            "probabilities": probs.get(i),
        })
    return rows
