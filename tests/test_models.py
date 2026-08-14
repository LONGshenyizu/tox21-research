# ABOUTME: Tests for the three model families (per-task logistic regression, per-task LightGBM, multi-task MLP).
# ABOUTME: Synthetic but real-data-shaped inputs: binary features, multiple tasks, NaN labels (not tested).
import numpy as np
import pytest

from tox21_research.models import fit_lgbm_per_task, fit_logreg_per_task, train_multitask_mlp

RNG_SEED = 7


def _synthetic(n=300, n_features=64, n_tasks=4, signal=0.9, seed=RNG_SEED):
    """Binary features; each task is a learnable noisy function of a few features."""
    rng = np.random.default_rng(seed)
    X = (rng.random((n, n_features)) > 0.5).astype(np.float32)
    w = rng.normal(size=(n_features, n_tasks))
    logits = X @ w * signal
    p = 1 / (1 + np.exp(-logits))
    Y = (rng.random((n, n_tasks)) < p).astype(float)
    Y[rng.random((n, n_tasks)) < 0.15] = np.nan  # some not-tested entries
    return X, Y


def _all_finite_probs(P):
    return P.shape[1] == 4 and np.isfinite(P).all() and ((P >= 0) & (P <= 1)).all()


class TestLogreg:
    def test_fit_predict(self):
        X, Y = _synthetic()
        models = fit_logreg_per_task(X, Y, C=1.0, seed=0)
        assert len(models) == 4
        P = np.column_stack([m.predict_proba(X)[:, 1] for m in models])
        assert _all_finite_probs(P)
        # learnable synthetic relation must beat chance on training rows
        from sklearn.metrics import roc_auc_score
        for j in range(4):
            mask = ~np.isnan(Y[:, j])
            assert roc_auc_score(Y[mask, j], P[mask, j]) > 0.85

    def test_class_weight_passed(self):
        X, Y = _synthetic()
        models = fit_logreg_per_task(X, Y, C=1.0, seed=0)
        assert models[0].class_weight == "balanced"


class TestLgbm:
    def test_fit_predict(self):
        X, Y = _synthetic()
        models = fit_lgbm_per_task(
            X, Y, num_leaves=15, n_estimators=50, learning_rate=0.1, seed=0
        )
        P = np.column_stack([m.predict_proba(X)[:, 1] for m in models])
        assert _all_finite_probs(P)
        from sklearn.metrics import roc_auc_score
        mask = ~np.isnan(Y[:, 0])
        assert roc_auc_score(Y[mask, 0], P[mask, 0]) > 0.85


class TestMultitaskMlp:
    def test_train_predict_learns(self):
        X, Y = _synthetic()
        predictor = train_multitask_mlp(
            X, Y, X, Y, hidden=(32,), dropout=0.1, lr=5e-3,
            batch_size=64, max_epochs=30, patience=10, seed=0,
        )
        P = predictor(X)
        assert _all_finite_probs(P)
        from sklearn.metrics import roc_auc_score
        mask = ~np.isnan(Y[:, 0])
        assert roc_auc_score(Y[mask, 0], P[mask, 0]) > 0.85

    def test_seed_changes_result(self):
        X, Y = _synthetic(n=150, signal=0.5)
        p1 = train_multitask_mlp(X, Y, None, None, hidden=(16,), dropout=0.0,
                                 lr=5e-3, batch_size=64, max_epochs=5, patience=5, seed=1)(X)
        p2 = train_multitask_mlp(X, Y, None, None, hidden=(16,), dropout=0.0,
                                 lr=5e-3, batch_size=64, max_epochs=5, patience=5, seed=2)(X)
        assert not np.allclose(p1, p2)
