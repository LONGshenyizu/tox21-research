# ABOUTME: Stage-2 model selection driver: trains every configured model family on the train split and evaluates on valid.
# ABOUTME: Writes one row per (family, params, seed) to results/interim/model_comparison.csv and prints the ranking.
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.data import TASKS  # noqa: E402
from tox21_research.metrics import evaluate_matrix  # noqa: E402
from tox21_research.models import (  # noqa: E402
    fit_lgbm_per_task,
    fit_logreg_per_task,
    predict_per_task,
    train_multitask_mlp,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "interim"


def run_logreg(X_tr, Y_tr, X_va, C, seed, max_iter):
    models = fit_logreg_per_task(X_tr, Y_tr, C=C, seed=seed, max_iter=max_iter)
    return predict_per_task(models, X_va)


def run_lgbm(X_tr, Y_tr, X_va, num_leaves, n_estimators, learning_rate, seed):
    models = fit_lgbm_per_task(
        X_tr, Y_tr, num_leaves=num_leaves, n_estimators=n_estimators,
        learning_rate=learning_rate, seed=seed,
    )
    return predict_per_task(models, X_va)


def run_mlp(X_tr, Y_tr, X_va, Y_va, cfg, seed):
    predictor = train_multitask_mlp(
        X_tr, Y_tr, X_va, Y_va,
        hidden=tuple(cfg["hidden"]), dropout=cfg["dropout"], lr=cfg["lr"],
        weight_decay=cfg["weight_decay"], batch_size=cfg["batch_size"],
        max_epochs=cfg["max_epochs"], patience=cfg["patience"], seed=seed,
    )
    return predictor(X_va)


def main():
    cfg = yaml.safe_load(open(ROOT / "configs" / "experiments.yaml", encoding="utf-8"))
    data = np.load(ROOT / "data" / "processed" / "tox21_modeling.npz", allow_pickle=False)
    X = data["X_ecfp4"] if cfg["feature_set"] == "ecfp4" else data["X_maccs"]
    X_maccs = data["X_maccs"]
    Y, tasks = data["Y"], list(data["tasks"])
    tr, va = data["train_idx"], data["valid_idx"]
    X_tr, Y_tr = X[tr], Y[tr]
    X_va, Y_va = X[va], Y[va]
    X_va_maccs = X_maccs[va]
    assert tasks == TASKS

    rows = []
    per_task_tables = {}

    def record(family, params, seed, P, elapsed):
        table, macro = evaluate_matrix(Y_va, P, task_names=tasks)
        rows.append({
            "family": family, "params": params, "seed": seed,
            "roc_auc_mean": round(macro["roc_auc_mean"], 4),
            "pr_auc_mean": round(macro["pr_auc_mean"], 4),
            "balanced_accuracy_mean": round(macro["balanced_accuracy_mean"], 4),
            "seconds": round(elapsed, 1),
        })
        per_task_tables[f"{family}|{params}|{seed}"] = table.round(4)
        print(f"{family:22s} {params:28s} seed={seed} "
              f"valid roc_auc={macro['roc_auc_mean']:.4f} pr_auc={macro['pr_auc_mean']:.4f} "
              f"({elapsed:.0f}s)")

    seed0 = cfg["seeds"][0]

    for C in cfg["logreg"]["C_grid"]:
        t0 = time.time()
        P = run_logreg(X_tr, Y_tr, X_va, C, seed0, cfg["logreg"]["max_iter"])
        record("logreg_ecfp4", f"C={C}", seed0, P, time.time() - t0)

    t0 = time.time()
    X_tr_maccs = X_maccs[tr]
    models = fit_logreg_per_task(X_tr_maccs, Y_tr, C=cfg["feature_check"]["C"], seed=seed0)
    record("logreg_maccs", f"C={cfg['feature_check']['C']}", seed0,
           predict_per_task(models, X_va_maccs), time.time() - t0)

    for g in cfg["lgbm"]["grid"]:
        t0 = time.time()
        P = run_lgbm(X_tr, Y_tr, X_va, g["num_leaves"], g["n_estimators"],
                     cfg["lgbm"]["learning_rate"], seed0)
        record("lgbm_ecfp4", f"leaves={g['num_leaves']},trees={g['n_estimators']}", seed0,
               P, time.time() - t0)

    for seed in cfg["seeds"]:
        t0 = time.time()
        P = run_mlp(X_tr, Y_tr, X_va, Y_va, cfg["mlp"], seed)
        record("mlp_ecfp4_multitask", "512-256,do0.2,adamw", seed, P, time.time() - t0)

    OUT.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(rows).sort_values("roc_auc_mean", ascending=False)
    comparison.to_csv(OUT / "model_comparison.csv", index=False)
    with pd.ExcelWriter(OUT / "valid_per_task_tables.xlsx") as writer:
        for name, table in per_task_tables.items():
            sheet = name.replace("|", "_")[:31]
            table.to_excel(writer, sheet_name=sheet)
    summary = (
        comparison.groupby(["family", "params"], as_index=False)
        .agg(roc_auc_mean=("roc_auc_mean", "mean"),
             roc_auc_std=("roc_auc_mean", "std"),
             pr_auc_mean=("pr_auc_mean", "mean"),
             seconds=("seconds", "mean"))
        .sort_values("roc_auc_mean", ascending=False)
    )
    summary.to_csv(OUT / "model_comparison_summary.csv", index=False)
    print("\n=== valid ranking (macro ROC-AUC, mean over seeds) ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
