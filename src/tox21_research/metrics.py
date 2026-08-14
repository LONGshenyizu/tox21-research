# ABOUTME: Per-endpoint binary classification metrics (ROC-AUC, PR-AUC, balanced accuracy) for multi-task matrices.
# ABOUTME: NaN labels mean "not tested" and are excluded per task; tasks with a single observed class get NaN AUCs.
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    roc_auc_score,
)


def task_metrics(y_true, y_score, threshold=0.5):
    """Metrics for one endpoint. y_true may contain NaN (not tested)."""
    mask = ~np.isnan(y_true)
    y = y_true[mask]
    s = y_score[mask]
    n_active = int((y == 1).sum())
    out = {
        "n_labeled": int(mask.sum()),
        "n_active": n_active,
        "roc_auc": float("nan"),
        "pr_auc": float("nan"),
        "balanced_accuracy": float("nan"),
    }
    if len(np.unique(y)) < 2:
        return out
    out["roc_auc"] = float(roc_auc_score(y, s))
    out["pr_auc"] = float(average_precision_score(y, s))
    pred = (s >= threshold).astype(int)
    out["balanced_accuracy"] = float(balanced_accuracy_score(y, pred))
    return out


def evaluate_matrix(Y_true, P_score, threshold=0.5, task_names=None):
    """Evaluate an (n_molecules, n_tasks) score matrix against labels.

    Returns (per_task_table, macro_summary): per-task metrics indexed by task,
    and macro means over tasks where ROC-AUC is defined.
    """
    Y_true = np.asarray(Y_true, dtype=float)
    P_score = np.asarray(P_score, dtype=float)
    if Y_true.shape != P_score.shape:
        raise ValueError("label and score matrices must have the same shape")
    n_tasks = Y_true.shape[1]
    rows = {}
    for j in range(n_tasks):
        rows[j] = task_metrics(Y_true[:, j], P_score[:, j], threshold)
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "task"
    if task_names is not None:
        table.index = pd.Index(task_names, name="task")
    scored = table["roc_auc"].dropna()
    macro = {
        "roc_auc_mean": float(scored.mean()) if len(scored) else float("nan"),
        "pr_auc_mean": float(table["pr_auc"].dropna().mean()),
        "balanced_accuracy_mean": float(table["balanced_accuracy"].dropna().mean()),
        "n_tasks_scored": int(len(scored)),
    }
    return table, macro
