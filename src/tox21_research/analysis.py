# ABOUTME: Error-analysis helpers over a labeled/scored matrix: confident mistakes and per-task rankings.
# ABOUTME: Pure functions on numpy arrays so they are unit-testable without models.
import numpy as np
import pandas as pd


def confident_errors(Y_true, P_score, task_names, max_per_task=10):
    """Most confident false positives and false negatives per task at a threshold.

    Returns a long DataFrame: task, mol_pos (row), kind (FP/FN), label, score.
    Rows with missing labels (NaN) are skipped.
    """
    records = []
    for j, task in enumerate(task_names):
        y, p = Y_true[:, j], P_score[:, j]
        mask = ~np.isnan(y)
        pred = p >= 0.5
        fp = np.where(mask & (y == 0) & pred)[0]
        fn = np.where(mask & (y == 1) & ~pred)[0]
        # most confident = highest score among FPs, lowest among FNs
        fp = fp[np.argsort(-p[fp])][:max_per_task]
        fn = fn[np.argsort(p[fn])][:max_per_task]
        for i in fp:
            records.append({"task": task, "row": int(i), "kind": "FP",
                            "label": 0.0, "score": float(p[i])})
        for i in fn:
            records.append({"task": task, "row": int(i), "kind": "FN",
                            "label": 1.0, "score": float(p[i])})
    return pd.DataFrame(records)


def rank_tasks(table, column="roc_auc", ascending=True):
    """Order the per-task metric table from worst to best."""
    return table.sort_values(column, ascending=ascending)
