# ABOUTME: One-shot frozen-model evaluation on the held-out test split; also persists fitted models and all split predictions.
# ABOUTME: The frozen model is the seed-averaged ensemble; must be run exactly once per frozen configuration.
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.metrics import evaluate_matrix  # noqa: E402
from tox21_research.models import (  # noqa: E402
    MultitaskMLP,
    fit_lgbm_per_task,
    fit_logreg_per_task,
    predict_per_task,
    train_multitask_mlp,
)

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "results" / "final"


def fit_family(family, params, seed, X_tr, Y_tr, X_va, Y_va):
    """Fit one model; returns (predictor, save_artifact) where save_artifact
    is ("joblib", models) or ("torch", module)."""
    if family == "logreg_ecfp4":
        models = fit_logreg_per_task(X_tr, Y_tr, C=params["C"], seed=seed)
        return (lambda X: predict_per_task(models, X)), ("joblib", models)
    if family == "lgbm_ecfp4":
        models = fit_lgbm_per_task(
            X_tr, Y_tr, num_leaves=params["num_leaves"],
            n_estimators=params["n_estimators"], learning_rate=params["learning_rate"],
            seed=seed,
        )
        return (lambda X: predict_per_task(models, X)), ("joblib", models)
    if family == "mlp_ecfp4_multitask":
        predictor = train_multitask_mlp(
            X_tr, Y_tr, X_va, Y_va,
            hidden=tuple(params["hidden"]), dropout=params["dropout"],
            lr=params["lr"], weight_decay=params["weight_decay"],
            batch_size=params["batch_size"], max_epochs=params["max_epochs"],
            patience=params["patience"], seed=seed,
        )
        return predictor, ("torch", predictor.module)
    raise ValueError(f"unknown family: {family}")


def main():
    spec = json.load(open(ROOT / "configs" / "final_model.json", encoding="utf-8"))
    data = np.load(ROOT / "data" / "processed" / "tox21_modeling.npz")
    tasks = list(data["tasks"])
    mol_ids = data["mol_ids"]
    Y = data["Y"]
    tr, va, te = data["train_idx"], data["valid_idx"], data["test_idx"]

    feature = "X_ecfp4" if spec["feature_set"] == "ecfp4" else "X_maccs"
    X = data[feature]
    X_tr, Y_tr = X[tr], Y[tr]
    X_va, Y_va = X[va], Y[va]
    X_te, Y_te = X[te], Y[te]

    model_dir = FINAL / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    split_frames = {s: [] for s in ["train", "valid", "test"]}
    per_seed_rows = []
    ensemble_probs = {s: [] for s in ["train", "valid", "test"]}

    for seed in spec["seeds"]:
        t0 = time.time()
        predictor, (kind, payload) = fit_family(
            spec["family"], spec["params"], seed, X_tr, Y_tr, X_va, Y_va
        )
        if kind == "joblib":
            joblib.dump(payload, model_dir / f"model_seed{seed}.joblib")
        else:
            torch.save(payload.state_dict(), model_dir / f"model_seed{seed}.pt")
        elapsed = time.time() - t0

        for split_name, Xs, Ys, idx in [
            ("train", X_tr, Y_tr, tr), ("valid", X_va, Y_va, va), ("test", X_te, Y_te, te),
        ]:
            P = predictor(Xs)
            ensemble_probs[split_name].append(P)
            table, macro = evaluate_matrix(Ys, P, task_names=tasks)
            table.to_csv(FINAL / f"{split_name}_metrics_seed{seed}.csv")
            if split_name == "test":
                per_seed_rows.append({"seed": seed, **macro, "seconds": round(elapsed, 1)})
            split_frames[split_name].append(
                pd.DataFrame(P, index=mol_ids[idx], columns=tasks).assign(seed=seed)
            )
        print(f"seed {seed}: test roc_auc={per_seed_rows[-1]['roc_auc_mean']:.4f} "
              f"pr_auc={per_seed_rows[-1]['pr_auc_mean']:.4f} "
              f"bacc={per_seed_rows[-1]['balanced_accuracy_mean']:.4f}")

    # frozen model = seed-averaged ensemble; evaluate exactly this object on test
    for split_name, probs in ensemble_probs.items():
        P = np.mean(probs, axis=0)
        idx = {"train": tr, "valid": va, "test": te}[split_name]
        Ys = Y[idx]
        table, macro = evaluate_matrix(Ys, P, task_names=tasks)
        table.to_csv(FINAL / f"{split_name}_metrics_ensemble.csv")
        pd.DataFrame(P, index=mol_ids[idx], columns=tasks).to_csv(
            FINAL / f"{split_name}_predictions_ensemble.csv"
        )
        if split_name == "test":
            ensemble_row = {"seed": "ensemble", **macro}
            print(f"ENSEMBLE: test roc_auc={macro['roc_auc_mean']:.4f} "
                  f"pr_auc={macro['pr_auc_mean']:.4f} "
                  f"bacc={macro['balanced_accuracy_mean']:.4f}")

    summary = pd.DataFrame(per_seed_rows + [ensemble_row])
    summary.to_csv(FINAL / "test_summary.csv", index=False)
    for split_name, frames in split_frames.items():
        pd.concat(frames).to_csv(FINAL / f"{split_name}_predictions_per_seed.csv")
    with open(FINAL / "frozen_config.json", "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print("done: results/final/")


if __name__ == "__main__":
    main()
