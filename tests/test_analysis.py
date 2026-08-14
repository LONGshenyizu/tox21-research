# ABOUTME: Tests for error-analysis helpers on small hand-built matrices.
import numpy as np

from tox21_research.analysis import confident_errors, rank_tasks
import pandas as pd


class TestConfidentErrors:
    def test_fp_fn_selection(self):
        Y = np.array([[0.0], [0.0], [1.0], [1.0]])
        P = np.array([[0.9], [0.3], [0.2], [0.8]])  # row0=FP, row2=FN, rows ok
        out = confident_errors(Y, P, ["NR-AR"])
        assert set(out["kind"]) == {"FP", "FN"}
        fp = out[out["kind"] == "FP"].iloc[0]
        fn = out[out["kind"] == "FN"].iloc[0]
        assert fp["row"] == 0 and fp["score"] == 0.9
        assert fn["row"] == 2 and fn["score"] == 0.2

    def test_missing_labels_ignored(self):
        Y = np.array([[np.nan], [1.0]])
        P = np.array([[0.99], [0.1]])
        out = confident_errors(Y, P, ["SR-p53"])
        assert len(out) == 1 and out.iloc[0]["row"] == 1

    def test_per_task_limit(self):
        Y = np.zeros((5, 1))
        P = np.full((5, 1), 0.9)
        out = confident_errors(Y, P, ["SR-MMP"], max_per_task=2)
        assert len(out) == 2


class TestRankTasks:
    def test_worst_first(self):
        table = pd.DataFrame(
            {"roc_auc": [0.9, 0.5, 0.7]}, index=["a", "b", "c"]
        )
        assert list(rank_tasks(table).index) == ["b", "c", "a"]
