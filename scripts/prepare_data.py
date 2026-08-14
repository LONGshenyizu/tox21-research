# ABOUTME: Builds the modeling dataset: drops the 8 unparseable SMILES, computes fingerprints, and caches the scaffold split.
# ABOUTME: Output is data/processed/tox21_modeling.npz + manifest.json (records dropped ids and split sizes).
import json
import sys
from pathlib import Path

import numpy as np
from rdkit import RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.data import TASKS, load_modeling_data  # noqa: E402
from tox21_research.features import ecfp_matrix, maccs_matrix  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "tox21_moleculenet.csv.gz"
OUT_DIR = ROOT / "data" / "processed"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame, train, val, test, dropped = load_modeling_data(CSV)
    frame = frame.reset_index()
    smiles = frame["smiles"].tolist()

    print(f"features: ECFP4-2048 for {len(smiles)} molecules ...")
    X_ecfp = ecfp_matrix(smiles)
    print("features: MACCS-167 ...")
    X_maccs = maccs_matrix(smiles)
    Y = frame[TASKS].to_numpy(dtype=float)

    np.savez_compressed(
        OUT_DIR / "tox21_modeling.npz",
        X_ecfp4=X_ecfp,
        X_maccs=X_maccs,
        Y=Y,
        mol_ids=frame["mol_id"].to_numpy(dtype=str),
        tasks=np.array(TASKS),
        train_idx=np.array(train),
        valid_idx=np.array(val),
        test_idx=np.array(test),
    )
    manifest = {
        "source_csv": str(CSV.name),
        "n_total_rows": len(frame) + len(dropped),
        "n_dropped_invalid_smiles": len(dropped),
        "dropped_mol_ids": dropped,
        "n_modeling": len(smiles),
        "split_sizes": {"train": len(train), "valid": len(val), "test": len(test)},
        "split": "murcko scaffold 80/10/10 (DeepChem-equivalent, deterministic)",
        "features": {"ecfp4": "Morgan radius 2, 2048 bits", "maccs": "167 keys"},
    }
    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
