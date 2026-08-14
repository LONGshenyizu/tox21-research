# ABOUTME: Validation-set error analysis for the selected model family: per-task ranking, confident mistakes, and known edge cases.
# ABOUTME: Runs strictly on the train/valid splits; the test split is never touched here.
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.analysis import confident_errors, rank_tasks  # noqa: E402
from tox21_research.data import load_moleculenet_csv  # noqa: E402
from tox21_research.metrics import evaluate_matrix  # noqa: E402
from tox21_research.models import fit_lgbm_per_task, predict_per_task  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "interim" / "error_analysis"


def main():
    spec = json.load(open(ROOT / "configs" / "final_model.json", encoding="utf-8"))
    assert spec["family"] == "lgbm_ecfp4", "script currently serves the lgbm family"
    data = np.load(ROOT / "data" / "processed" / "tox21_modeling.npz")
    X, Y, tasks = data["X_ecfp4"], data["Y"], list(data["tasks"])
    mol_ids = data["mol_ids"]
    tr, va, te = data["train_idx"], data["valid_idx"], data["test_idx"]

    models = fit_lgbm_per_task(
        X[tr], Y[tr], num_leaves=spec["params"]["num_leaves"],
        n_estimators=spec["params"]["n_estimators"],
        learning_rate=spec["params"]["learning_rate"], seed=spec["seeds"][0],
    )
    P_valid = predict_per_task(models, X[va])
    table, macro = evaluate_matrix(Y[va], P_valid, task_names=tasks)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "valid_task_metrics.csv")
    rank_tasks(table).to_csv(OUT / "valid_task_ranking.csv")

    csv = load_moleculenet_csv(ROOT / "data" / "raw" / "tox21_moleculenet.csv.gz")
    frame = csv.loc[mol_ids]

    errors = confident_errors(Y[va], P_valid, tasks)
    errors["mol_id"] = [mol_ids[va][r] for r in errors["row"]]
    errors["smiles"] = [frame.loc[m, "smiles"] for m in errors["mol_id"]]
    errors.drop(columns="row").to_csv(OUT / "valid_confident_errors.csv", index=False)

    # duplicate-structure groups (same InChIKey, i.e. same compound spelled differently):
    # where their members sit, and model scores for valid members
    inchikey = frame["smiles"].map(
        lambda s: Chem.MolToInchiKey(Chem.MolFromSmiles(s))
        if Chem.MolFromSmiles(s) is not None else None
    )
    split_of = np.empty(len(mol_ids), dtype=object)
    split_of[tr], split_of[va], split_of[te] = "train", "valid", "test"
    valid_score = {mol_ids[i]: P_valid[k] for k, i in enumerate(va)}
    rows = []
    for key, members in inchikey.groupby(inchikey).groups.items():
        if len(members) < 2:
            continue
        for mol_id in members:
            pos = mol_ids.tolist().index(mol_id)
            row = {
                "inchikey": key, "mol_id": mol_id, "smiles": frame.loc[mol_id, "smiles"],
                "split": split_of[pos],
                **{f"label_{t}": frame.loc[mol_id, t] for t in tasks},
            }
            if mol_id in valid_score:
                row.update({f"p_{t}": round(float(v), 3) for t, v in zip(tasks, valid_score[mol_id])})
            rows.append(row)
    pd.DataFrame(rows).to_csv(OUT / "duplicate_groups.csv", index=False)

    # per-task relation between AUC and number of actives in valid
    corr = float(np.corrcoef(table["n_active"], table["roc_auc"])[0, 1])
    print("valid macro:", json.dumps(macro))
    print(f"corr(n_active_valid, roc_auc) = {corr:.3f}")
    print(table.sort_values("roc_auc").to_string())


if __name__ == "__main__":
    main()
