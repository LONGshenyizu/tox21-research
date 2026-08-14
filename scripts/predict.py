# ABOUTME: Inference entry point: predicts 12-endpoint activity probabilities for a file of SMILES (one per line).
# ABOUTME: Rebuilds the frozen ensemble from results/final/model and reproduces the evaluated seed-averaged predictions.
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.features import ecfp_matrix, maccs_matrix  # noqa: E402
from tox21_research.models import MultitaskMLP, predict_per_task  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load_models():
    spec = json.load(open(ROOT / "results" / "final" / "frozen_config.json", encoding="utf-8"))
    model_dir = ROOT / "results" / "final" / "model"
    predictors = []
    for seed in spec["seeds"]:
        if spec["family"] == "mlp_ecfp4_multitask":
            module = MultitaskMLP(
                2048 if spec["feature_set"] == "ecfp4" else 167,
                12, tuple(spec["params"]["hidden"]), spec["params"]["dropout"],
            )
            module.load_state_dict(torch.load(model_dir / f"model_seed{seed}.pt", weights_only=True))
            module.eval()
            predictors.append(
                lambda X, m=module: torch.sigmoid(
                    m(torch.as_tensor(np.asarray(X, dtype=np.float32)))
                ).detach().numpy()
            )
        else:
            models = joblib.load(model_dir / f"model_seed{seed}.joblib")
            predictors.append(lambda X, ms=models: predict_per_task(ms, X))
    return spec, predictors


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/predict.py <input_smiles.txt> <output.csv>")
    in_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    smiles = [line.strip() for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    spec, predictors = load_models()
    featurize = ecfp_matrix if spec["feature_set"] == "ecfp4" else maccs_matrix
    X = featurize(smiles)
    probs = np.mean([p(X) for p in predictors], axis=0)
    tasks = [
        "NR-AR", "NR-AR-LBD", "NR-AhR", "NR-Aromatase", "NR-ER", "NR-ER-LBD",
        "NR-PPAR-gamma", "SR-ARE", "SR-ATAD5", "SR-HSE", "SR-MMP", "SR-p53",
    ]
    pd.DataFrame(probs, index=smiles, columns=tasks).to_csv(out_path)
    print(f"wrote {len(smiles)} predictions to {out_path}")


if __name__ == "__main__":
    main()
