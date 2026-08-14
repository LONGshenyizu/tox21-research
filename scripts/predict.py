# ABOUTME: Inference CLI: predicts 12-endpoint activity probabilities for a file of SMILES (one per line).
# ABOUTME: Thin wrapper over tox21_research.inference -- the same implementation the FastAPI service uses.
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.data import TASKS  # noqa: E402
from tox21_research.inference import REPO_ROOT, load_frozen_predictor  # noqa: E402


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/predict.py <input_smiles.txt> <output.csv>")
    in_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    smiles = [line.strip() for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    predictor = load_frozen_predictor(REPO_ROOT)
    X = predictor.featurize(smiles)
    probs = predictor.predict_matrix(X)
    pd.DataFrame(probs, index=smiles, columns=TASKS).to_csv(out_path)
    print(f"wrote {len(smiles)} predictions to {out_path}")


if __name__ == "__main__":
    main()
