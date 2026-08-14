# ABOUTME: Tests for per-endpoint classification metrics and multi-task evaluation tables.
# ABOUTME: Uses hand-computed cases including missing labels (NaN) and degenerate single-class tasks.
import numpy as np
import pandas as pd
import pytest

from tox21_research.metrics import evaluate_matrix, task_metrics


class TestTaskMetrics:
    def test_perfect_scores(self):
        y = np.array([0, 0, 1, 1])
        s = np.array([0.1, 0.2, 0.8, 0.9])
        m = task_metrics(y, s)
        assert m["roc_auc"] == 1.0
        assert m["pr_auc"] == 1.0
        assert m["balanced_accuracy"] == 1.0

    def test_missing_labels_skipped(self):
        y = np.array([0.0, np.nan, 1.0])
        s = np.array([0.2, 0.99, 0.8])
        m = task_metrics(y, s)
        assert m["n_labeled"] == 2
        assert m["roc_auc"] == 1.0

    def test_single_class_task(self):
        y = np.array([0.0, 0.0, 0.0])
        s = np.array([0.1, 0.4, 0.3])
        m = task_metrics(y, s)
        assert m["roc_auc"] is None or np.isnan(m["roc_auc"])

    def test_balanced_accuracy_at_threshold(self):
        y = np.array([0, 0, 1, 1])
        s = np.array([0.4, 0.6, 0.4, 0.6])  # predictions: 0,1,0,1
        m = task_metrics(y, s, threshold=0.5)
        # TPR = 1/2, TNR = 1/2
        assert m["balanced_accuracy"] == 0.5


class TestEvaluateMatrix:
    def test_table_and_macro(self):
        rng = np.random.default_rng(0)
        n = 60
        Y = rng.choice([0.0, 1.0, np.nan], size=(n, 3), p=[0.6, 0.25, 0.15])
        P = rng.random((n, 3))
        table, macro = evaluate_matrix(Y, P)
        assert list(table.columns) == [
            "n_labeled", "n_active", "roc_auc", "pr_auc", "balanced_accuracy",
        ]
        assert len(table) == 3
        assert 0.0 <= macro["roc_auc_mean"] <= 1.0
        assert macro["n_tasks_scored"] == 3

    def test_one_degenerate_task_excluded_from_macro(self):
        Y = np.column_stack([
            np.array([0, 1, 0, 1, 0, 1]),        # healthy task
            np.array([0, 0, 0, 0, 0, 0]),        # single class -> AUC undefined
        ]).astype(float)
        P = np.column_stack([
            np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7]),
            np.array([0.5, 0.4, 0.6, 0.3, 0.7, 0.2]),
        ])
        table, macro = evaluate_matrix(Y, P)
        assert macro["n_tasks_scored"] == 1
        assert np.isnan(table.loc[1, "roc_auc"])
