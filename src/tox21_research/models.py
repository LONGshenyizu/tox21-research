# ABOUTME: Model families for the 12-endpoint Tox21 task: per-task logistic regression, per-task LightGBM, and a shared-representation multi-task MLP.
# ABOUTME: All fitters consume rows with NaN labels (not tested) per task; predictors return activity probabilities in [0, 1].
import numpy as np
import torch
import torch.nn as nn
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression

from tox21_research.metrics import evaluate_matrix


def _task_mask(Y, j):
    return ~np.isnan(Y[:, j])


def fit_logreg_per_task(X, Y, C=1.0, seed=0, max_iter=2000):
    """One balanced logistic regression per task, fitted on that task's labeled rows."""
    models = []
    for j in range(Y.shape[1]):
        mask = _task_mask(Y, j)
        model = LogisticRegression(
            C=C, class_weight="balanced", max_iter=max_iter, random_state=seed
        )
        model.fit(X[mask], Y[mask, j].astype(int))
        models.append(model)
    return models


def predict_per_task(models, X):
    """Stack per-task positive-class probabilities into an (n, n_tasks) matrix."""
    return np.column_stack([m.predict_proba(X)[:, 1] for m in models])


def fit_lgbm_per_task(X, Y, num_leaves=31, n_estimators=500, learning_rate=0.05, seed=0):
    """One LightGBM classifier per task with balanced class weighting."""
    models = []
    for j in range(Y.shape[1]):
        mask = _task_mask(Y, j)
        y = Y[mask, j].astype(int)
        pos_weight = (len(y) - y.sum()) / max(y.sum(), 1)
        model = LGBMClassifier(
            num_leaves=num_leaves,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            scale_pos_weight=pos_weight,
            random_state=seed,
            n_jobs=4,
            verbosity=-1,
            force_row_wise=True,
        )
        model.fit(X[mask], y)
        models.append(model)
    return models


class MultitaskMLP(nn.Module):
    """Shared-representation network: fingerprint in, one logit per endpoint."""

    def __init__(self, n_features, n_tasks, hidden, dropout):
        super().__init__()
        layers = []
        in_dim = n_features
        for width in hidden:
            layers += [nn.Linear(in_dim, width), nn.ReLU(), nn.Dropout(dropout)]
            in_dim = width
        layers.append(nn.Linear(in_dim, n_tasks))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def train_multitask_mlp(
    X_train, Y_train, X_valid, Y_valid,
    hidden=(512, 256), dropout=0.2, lr=1e-3, weight_decay=1e-4,
    batch_size=256, max_epochs=100, patience=10, seed=0,
):
    """Train a shared-representation MLP on all 12 tasks jointly.

    BCE-with-logits per task; missing labels are masked out of the loss.
    Early stopping (and best-model restore) on validation macro ROC-AUC when a
    validation set is given, otherwise trains for max_epochs. Returns a
    predictor mapping an (n, n_features) matrix to task probabilities.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    X_t = torch.as_tensor(X_train, dtype=torch.float32)
    Y_t = torch.as_tensor(Y_train, dtype=torch.float32)
    mask_t = ~torch.isnan(Y_t)
    Y_filled = torch.nan_to_num(Y_t, nan=0.0)
    n_pos = torch.stack([(Y_t[mask_t[:, j], j]).sum() for j in range(Y_t.shape[1])])
    n_neg = mask_t.sum(dim=0) - n_pos
    pos_weight = torch.clamp(n_neg / torch.clamp(n_pos, min=1.0), min=1.0)

    model = MultitaskMLP(X_t.shape[1], Y_t.shape[1], hidden, dropout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    n = X_t.shape[0]
    best_state, best_auc, bad_epochs = None, -np.inf, 0
    generator = torch.Generator().manual_seed(seed)
    for _epoch in range(max_epochs):
        model.train()
        order = torch.randperm(n, generator=generator)
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            logits = model(X_t[idx])
            loss = nn.functional.binary_cross_entropy_with_logits(
                logits, Y_filled[idx], weight=mask_t[idx].float(), pos_weight=pos_weight,
                reduction="sum",
            ) / mask_t[idx].float().sum()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        if X_valid is not None:
            model.eval()
            with torch.no_grad():
                prob = torch.sigmoid(model(torch.as_tensor(X_valid, dtype=torch.float32))).numpy()
            _, macro = evaluate_matrix(Y_valid, prob)
            auc = macro["roc_auc_mean"]
            if np.isnan(auc):
                auc = -np.inf
            if auc > best_auc:
                best_auc, bad_epochs = auc, 0
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            else:
                bad_epochs += 1
                if bad_epochs >= patience:
                    break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()

    def predict(X):
        with torch.no_grad():
            tensor = torch.as_tensor(np.asarray(X, dtype=np.float32))
            return torch.sigmoid(model(tensor)).numpy()

    predict.module = model
    return predict
