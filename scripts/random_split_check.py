# ABOUTME: Robustness check of the frozen model family under random 80/10/10 splits (3 seeds), run after the frozen test evaluation.
# ABOUTME: Uses its own splits; the frozen scaffold test set is not involved and results feed no model changes.
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.metrics import evaluate_matrix  # noqa: E402
from tox21_research.models import (  # noqa: E402
    fit_lgbm_per_task,
    fit_logreg_per_task,
    predict_per_task,
    train_multitask_mlp,
)

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "results" / "final"


def fit_and_predict(family, params, seed, X_tr, Y_tr, X_va, Y_va, X_te):
    if family == "logreg_ecfp4":
        models = fit_logreg_per_task(X_tr, Y_tr, C=params["C"], seed=seed)
        return predict_per_task(models, X_te)
    if family == "lgbm_ecfp4":
        models = fit_lgbm_per_task(
            X_tr, Y_tr, num_leaves=params["num_leaves"],
            n_estimators=params["n_estimators"], learning_rate=params["learning_rate"],
            seed=seed,
        )
        return predict_per_task(models, X_te)
    if family == "mlp_ecfp4_multitask":
        predictor = train_multitask_mlp(
            X_tr, Y_tr, X_va, Y_va, hidden=tuple(params["hidden"]),
            dropout=params["dropout"], lr=params["lr"],
            weight_decay=params["weight_decay"], batch_size=params["batch_size"],
            max_epochs=params["max_epochs"], patience=params["patience"], seed=seed,
        )
        return predictor(X_te)
    raise ValueError(f"unknown family: {family}")


def main():
    spec = json.load(open(ROOT / "configs" / "final_model.json", encoding="utf-8"))
    data = np.load(ROOT / "data" / "processed" / "tox21_modeling.npz")
    X = data["X_ecfp4"] if spec["feature_set"] == "ecfp4" else data["X_maccs"]
    Y, tasks = data["Y"], list(data["tasks"])
    n = len(Y)

    rows = []
    for seed in spec.get("random_split_seeds", [0, 1, 2]):
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n)
        n_tr, n_va = int(n * 0.8), int(n * 0.1)
        tr, va, te = perm[:n_tr], perm[n_tr : n_tr + n_va], perm[n_tr + n_va :]
        P = fit_and_predict(spec["family"], spec["params"], seed,
                            X[tr], Y[tr], X[va], Y[va], X[te])
        table, macro = evaluate_matrix(Y[te], P, task_names=tasks)
        table.to_csv(FINAL / f"random_split_metrics_seed{seed}.csv")
        rows.append({"split_seed": seed, "split": "random",
                     **{k: round(v, 4) for k, v in macro.items()}})
        print(f"random seed {seed}: test roc_auc={macro['roc_auc_mean']:.4f}")

    scaffold = pd.read_csv(FINAL / "test_summary.csv")
    for _, r in scaffold.iterrows():
        rows.append({"split_seed": r["seed"], "split": "scaffold(frozen)",
                     "roc_auc_mean": r["roc_auc_mean"], "pr_auc_mean": r["pr_auc_mean"],
                     "balanced_accuracy_mean": r["balanced_accuracy_mean"],
                     "n_tasks_scored": r["n_tasks_scored"]})
    out = pd.DataFrame(rows)
    out.to_csv(FINAL / "random_split_sensitivity.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
