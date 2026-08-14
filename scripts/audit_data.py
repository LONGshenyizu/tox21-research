# ABOUTME: Data audit for the Tox21 study: structure/label checks on the MoleculeNet CSV,
# ABOUTME: cross-version comparison with the 2014 challenge SDF by explicit compound id,
# ABOUTME: and leakage/similarity checks on the exact modeling frame and split used for training
# ABOUTME: (guarded by a tripwire against divergence from the cached npz).
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.AllChem import GetMorganFingerprintAsBitVect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tox21_research.compare import (  # noqa: E402
    AGGREGATIONS,
    intra_compound_disagreement,
    label_agreement,
    structure_match,
)
from tox21_research.data import (  # noqa: E402
    TASKS,
    load_challenge_sdf,
    load_moleculenet_csv,
    load_modeling_data,
)

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "interim" / "audit"
CSV_PATH = ROOT / "data" / "raw" / "tox21_moleculenet.csv.gz"
CHALLENGE_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_data_all.sdf"
TEST_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_challenge_test.sdf"
SCORE_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_challenge_score.sdf"
MODELING_NPZ = ROOT / "data" / "processed" / "tox21_modeling.npz"

ORGANOGENIC = {"C", "N", "O", "S", "P", "F", "Cl", "Br", "I", "B", "Si", "Se"}


def describe_molecules(smiles_list):
    """Parse SMILES with RDKit; return per-molecule flags and descriptors."""
    flags = {
        "valid": [], "is_mixture": [], "has_stereo": [], "is_charged": [],
        "unusual_elements": [], "has_wildcard": [],
        "canonical": [], "inchikey": [],
        "mw": [], "logp": [], "tpsa": [], "hbd": [], "hba": [],
        "ring_count": [], "rotatable": [], "heavy_atoms": [],
    }
    for smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            for key in flags:
                flags[key].append(np.nan)
            flags["valid"][-1] = False
            continue
        symbols = {atom.GetSymbol() for atom in mol.GetAtoms()}
        flags["valid"].append(True)
        flags["is_mixture"].append("." in smi)
        flags["has_stereo"].append("@" in Chem.MolToSmiles(mol))
        flags["is_charged"].append(Chem.GetFormalCharge(mol) != 0)
        flags["unusual_elements"].append(not symbols <= ORGANOGENIC)
        flags["has_wildcard"].append("*" in smi)
        flags["canonical"].append(Chem.MolToSmiles(mol))
        flags["inchikey"].append(Chem.MolToInchiKey(mol))
        flags["mw"].append(Descriptors.MolWt(mol))
        flags["logp"].append(Descriptors.MolLogP(mol))
        flags["tpsa"].append(Descriptors.TPSA(mol))
        flags["hbd"].append(rdMolDescriptors.CalcNumHBD(mol))
        flags["hba"].append(rdMolDescriptors.CalcNumHBA(mol))
        flags["ring_count"].append(rdMolDescriptors.CalcNumRings(mol))
        flags["rotatable"].append(rdMolDescriptors.CalcNumRotatableBonds(mol))
        flags["heavy_atoms"].append(mol.GetNumHeavyAtoms())
    return pd.DataFrame(flags)


def task_summary(df):
    """Per-task active/inactive/missing counts and active rate."""
    rows = []
    for task in TASKS:
        col = df[task]
        n_active = int((col == 1).sum())
        n_inactive = int((col == 0).sum())
        n_missing = int(col.isna().sum())
        labeled = n_active + n_inactive
        rows.append({
            "task": task,
            "n_labeled": labeled,
            "n_active": n_active,
            "n_inactive": n_inactive,
            "n_missing": n_missing,
            "active_rate": round(n_active / labeled, 4) if labeled else np.nan,
        })
    return pd.DataFrame(rows)


def duplicate_report(df):
    """Duplicate structures (same InChIKey) and conflicting labels within them."""
    groups = df.groupby("inchikey").groups
    dup_keys = {k for k, v in groups.items() if len(v) > 1}
    conflicts = 0
    conflict_tasks = Counter()
    for key in dup_keys:
        sub = df.loc[list(groups[key])]
        for task in TASKS:
            vals = set(sub[task].dropna().tolist())
            if {0.0, 1.0} <= vals:
                conflicts += 1
                conflict_tasks[task] += 1
    return {
        "n_duplicate_structure_groups": len(dup_keys),
        "n_rows_in_duplicate_groups": int(sum(len(groups[k]) for k in dup_keys)),
        "n_task_label_conflicts_within_duplicates": conflicts,
        "conflict_tasks": dict(conflict_tasks),
    }


def assert_split_matches_cache(frame, train, valid, test):
    """Tripwire: the audited split must equal the cached modeling split."""
    if not MODELING_NPZ.exists():
        return
    npz = np.load(MODELING_NPZ)
    if [str(m) for m in npz["mol_ids"]] != list(frame.index):
        raise ValueError("audit frame differs from cached modeling npz molecule order")
    for name, idx in [("train_idx", train), ("valid_idx", valid), ("test_idx", test)]:
        if list(npz[name]) != list(idx):
            raise ValueError(f"audit split {name} differs from cached modeling npz")


def split_checks(frame, train, valid, test):
    """Sizes, per-split active rates, structure leakage, test-to-train similarity."""
    assert_split_matches_cache(frame, train, valid, test)
    sizes = {"train": len(train), "valid": len(valid), "test": len(test)}
    rates = []
    for name, idx in [("train", train), ("valid", valid), ("test", test)]:
        sub = frame.iloc[idx]
        for task in TASKS:
            labeled = sub[task].notna().sum()
            rates.append({
                "split": name, "task": task,
                "n_labeled": int(labeled),
                "n_active": int((sub[task] == 1).sum()),
                "active_rate": round(float((sub[task] == 1).sum() / labeled), 4) if labeled else np.nan,
            })
    labels = list(frame.index)
    split_of = {}
    for name, idx in [("train", train), ("valid", valid), ("test", test)]:
        for i in idx:
            split_of[labels[i]] = name
    key_splits = frame.groupby("inchikey").apply(
        lambda g: {split_of[k] for k in g.index if k in split_of},
        include_groups=False,
    )
    cross = sum(1 for s in key_splits if len(s) > 1)
    fps = []
    for smi in frame["smiles"]:
        mol = Chem.MolFromSmiles(smi)
        fps.append(GetMorganFingerprintAsBitVect(mol, 2, nBits=2048) if mol else None)
    train_fps = [fps[i] for i in train if fps[i] is not None]
    nn_sim = []
    for i in test:
        if fps[i] is None:
            continue
        sims = DataStructs.BulkTanimotoSimilarity(fps[i], train_fps)
        nn_sim.append({"mol_id": labels[i], "max_tanimoto_to_train": round(max(sims), 4)})
    nn_df = pd.DataFrame(nn_sim)
    leakage = {
        "n_inchikeys_spanning_multiple_splits": int(cross),
        "test_molecules_with_train_neighbor_ge_0.95": int((nn_df["max_tanimoto_to_train"] >= 0.95).sum()),
        "test_molecules_with_train_neighbor_ge_0.85": int((nn_df["max_tanimoto_to_train"] >= 0.85).sum()),
        "test_max_tanimoto_mean": round(float(nn_df["max_tanimoto_to_train"].mean()), 4),
        "test_max_tanimoto_median": round(float(nn_df["max_tanimoto_to_train"].median()), 4),
    }
    return sizes, pd.DataFrame(rates), leakage, nn_df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}

    # ---- MoleculeNet CSV (full 7,831-row version description) ----
    print("Loading MoleculeNet CSV ...")
    mn = load_moleculenet_csv(CSV_PATH)
    desc = describe_molecules(mn["smiles"].tolist())
    desc.index = mn.index
    mn_full = pd.concat([mn, desc], axis=1)
    mn_full.to_csv(OUT / "moleculenet_molecule_table.csv")

    ts = task_summary(mn)
    ts.to_csv(OUT / "moleculenet_task_summary.csv", index=False)
    summary["moleculenet"] = {
        "n_rows": len(mn),
        "n_valid_smiles": int(desc["valid"].sum()),
        "n_invalid_smiles": int((~desc["valid"].astype(bool)).sum()),
        "n_mixtures": int(desc["is_mixture"].fillna(False).sum()),
        "n_charged": int(desc["is_charged"].fillna(False).sum()),
        "n_with_stereo": int(desc["has_stereo"].fillna(False).sum()),
        "n_unusual_elements": int(desc["unusual_elements"].fillna(False).sum()),
        "n_wildcard_atoms": int(desc["has_wildcard"].fillna(False).sum()),
        "n_with_at_least_one_label": int(mn[TASKS].notna().any(axis=1).sum()),
        "n_all_labels_missing": int(mn[TASKS].isna().all(axis=1).sum()),
        "duplicates": duplicate_report(mn_full),
    }

    # ---- Modeling frame + split (single source of truth with prepare_data) ----
    print("Building modeling frame and split ...")
    frame, train, valid, test, dropped = load_modeling_data(CSV_PATH)
    frame_full = mn_full.loc[frame.index]
    summary["modeling_frame"] = {
        "n_modeling": len(frame),
        "n_dropped_unparseable": len(dropped),
        "dropped_mol_ids": dropped,
        "split_sizes": {"train": len(train), "valid": len(valid), "test": len(test)},
        "split": "murcko scaffold 80/10/10 on the modeling frame (deterministic)",
    }

    # ---- Challenge training SDF ----
    print("Loading challenge SDF ...")
    raw_records = CHALLENGE_SDF.read_text(encoding="utf-8", errors="ignore").count("$$$$")
    ch = load_challenge_sdf(CHALLENGE_SDF)
    ch.to_csv(OUT / "challenge_molecule_table.csv")
    ch_ts = task_summary(ch)
    ch_ts.to_csv(OUT / "challenge_task_summary.csv", index=False)
    intra_compound_disagreement(ch).to_csv(OUT / "challenge_sample_agreement.csv")
    samples_per_cid = ch.groupby("dsstox_cid").size()
    summary["challenge_train_sdf"] = {
        "n_raw_records": raw_records,
        "n_parsed": len(ch),
        "n_unique_dsstox_cid": int(ch["dsstox_cid"].nunique()),
        "n_cid_with_multiple_samples": int((samples_per_cid > 1).sum()),
        "max_samples_per_cid": int(samples_per_cid.max()),
        "n_unique_inchikey": int(ch["inchikey"].nunique()),
        "n_with_at_least_one_label": int(ch[TASKS].notna().any(axis=1).sum()),
        "sample_multiplicity_note": (
            "multiple NCGC sample records per DSSTox_CID are qHTS re-tests of the same "
            "compound; no canonical batch exists, so cross-version label comparison "
            "reports three aggregation conventions (see cross_version_label_agreement.csv)"
        ),
    }

    # ---- Challenge evaluation sets ----
    test_set = load_challenge_sdf(TEST_SDF)
    score_set = load_challenge_sdf(SCORE_SDF)
    summary["challenge_eval_sets"] = {
        "leaderboard_test": {
            "n": len(test_set),
            "n_in_data_all": int(test_set["inchikey"].isin(ch["inchikey"]).sum()),
            "n_in_moleculenet_csv": int(test_set["inchikey"].isin(mn_full["inchikey"]).sum()),
        },
        "final_score_set": {
            "n": len(score_set),
            "n_in_data_all": int(score_set["inchikey"].isin(ch["inchikey"]).sum()),
            "n_in_moleculenet_csv": int(score_set["inchikey"].isin(mn_full["inchikey"]).sum()),
            "note": "contains no assay labels (labels were never publicly released)",
        },
    }

    # ---- Cross-version comparison by compound id ----
    print("Cross-version comparison (compound-id mapping) ...")
    agreement_tables = {}
    totals = {}
    for aggregation in AGGREGATIONS:
        table, agg_totals = label_agreement(mn, ch, aggregation)
        agreement_tables[aggregation] = table
        totals[aggregation] = agg_totals
    long = pd.concat(
        [t.assign(aggregation=agg) for agg, t in agreement_tables.items()]
    ).reset_index()
    long.to_csv(OUT / "cross_version_label_agreement.csv", index=False)
    structure = structure_match(mn_full, ch)
    pd.DataFrame([structure]).to_csv(OUT / "cross_version_structure.csv", index=False)
    summary["cross_version"] = {
        "mapping": "mol_id TOX#### numeric part == DSSTox_CID (empirical 1:1 mapping)",
        "n_matched_rows": totals["first"]["n_matched_rows"],
        "label_conflicts_by_aggregation": {
            agg: totals[agg]["n_conflict_total"] for agg in AGGREGATIONS
        },
        "n_csv_only_labels_first": int(agreement_tables["first"]["n_csv_only"].sum()),
        "n_sdf_only_labels_first": int(agreement_tables["first"]["n_sdf_only"].sum()),
        "structure_diagnostic_inchikey": structure,
        "structure_diagnostic_note": (
            "InChIKey equality is a stricter identity than compound id: unmatched rows "
            "reflect structure-standardization differences (salt/protonation/tautomer "
            "spelling), not absent compounds"
        ),
    }

    # ---- Split / leakage checks on the modeling split ----
    print("Split and leakage checks (modeling split) ...")
    sizes, split_rates, leakage, nn_df = split_checks(frame_full, train, valid, test)
    split_rates.to_csv(OUT / "split_task_active_rates.csv", index=False)
    nn_df.to_csv(OUT / "test_train_tanimoto.csv", index=False)
    summary["split"] = {"sizes": sizes, **leakage}

    with open(OUT / "audit_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str)[:3500])


if __name__ == "__main__":
    main()
