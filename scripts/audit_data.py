# ABOUTME: Stage-1 data audit: runs structural, label, cross-version, and split-leakage checks on both Tox21 data versions.
# ABOUTME: Writes machine-readable tables to results/interim/audit/ and headline numbers to audit_summary.json.
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
from tox21_research.data import TASKS, load_challenge_sdf, load_moleculenet_csv  # noqa: E402
from tox21_research.splits import scaffold_split_indices  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "interim" / "audit"
CSV_PATH = ROOT / "data" / "raw" / "tox21_moleculenet.csv.gz"
CHALLENGE_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_data_all.sdf"
TEST_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_challenge_test.sdf"
SCORE_SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_challenge_score.sdf"

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
        "n_rows_in_duplicate_groups": int(
            sum(len(groups[k]) for k in dup_keys)
        ),
        "n_task_label_conflicts_within_duplicates": conflicts,
        "conflict_tasks": dict(conflict_tasks),
    }


def cross_version_agreement(mn, ch):
    """Join MoleculeNet rows to challenge SDF by InChIKey; per-task label agreement."""
    joined = mn.join(ch, rsuffix="_ch", how="left")
    matched = joined["inchikey"].notna()
    rows = []
    for task in TASKS:
        a, b = joined[task], joined[f"{task}_ch"]
        both = matched & a.notna() & b.notna()
        rows.append({
            "task": task,
            "n_csv_labeled": int(a.notna().sum()),
            "n_matched": int(matched.sum()),
            "n_both_labeled": int(both.sum()),
            "n_agree": int((a[both] == b[both]).sum()),
            "n_conflict": int((a[both] != b[both]).sum()),
            "n_csv_only_labeled": int((matched & a.notna() & b.isna()).sum()),
            "n_sdf_only_labeled": int((matched & a.isna() & b.notna()).sum()),
        })
    return pd.DataFrame(rows), joined


def split_audit(df):
    """Scaffold split on the CSV order; sizes, per-split active rates, leakage checks."""
    train, valid, test, skipped = scaffold_split_indices(df["smiles"].tolist())
    sizes = {
        "train": len(train), "valid": len(valid), "test": len(test),
        "skipped_invalid_smiles": len(skipped),
    }
    rates = []
    for name, idx in [("train", train), ("valid", valid), ("test", test)]:
        sub = df.iloc[idx]
        for task in TASKS:
            labeled = sub[task].notna().sum()
            rates.append({
                "split": name, "task": task,
                "n_labeled": int(labeled),
                "n_active": int((sub[task] == 1).sum()),
                "active_rate": round(float((sub[task] == 1).sum() / labeled), 4) if labeled else np.nan,
            })
    # structure leakage: same InChIKey appearing in different splits
    # scaffold indices are positional; translate them to row labels once
    labels = list(df.index)
    split_of = {}
    for name, idx in [("train", train), ("valid", valid), ("test", test)]:
        for i in idx:
            split_of[labels[i]] = name
    key_splits = df.groupby("inchikey").apply(
        lambda g: {split_of[k] for k in g.index if k in split_of},
        include_groups=False,
    )
    cross = sum(1 for s in key_splits if len(s) > 1)
    # fingerprint similarity of test to train (ECFP4, 2048 bits)
    fps = []
    for smi in df["smiles"]:
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

    # ---- MoleculeNet CSV ----
    print("Loading MoleculeNet CSV ...")
    mn = load_moleculenet_csv(CSV_PATH)
    desc = describe_molecules(mn["smiles"].tolist())
    desc.index = mn.index
    mn_full = pd.concat([mn, desc], axis=1)
    mn_full.to_csv(OUT / "moleculenet_molecule_table.csv")

    ts = task_summary(mn)
    ts.to_csv(OUT / "moleculenet_task_summary.csv", index=False)
    prefix_counts = Counter(str(i).split("-")[0][:3] for i in mn.index)
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
        "mol_id_prefixes": dict(prefix_counts),
        "duplicates": duplicate_report(mn_full),
        "descriptors": {
            k: {
                "min": round(float(desc[k].min()), 2),
                "median": round(float(desc[k].median()), 2),
                "max": round(float(desc[k].max()), 2),
            }
            for k in ["mw", "logp", "tpsa", "heavy_atoms", "ring_count", "rotatable"]
        },
    }

    # ---- Challenge training SDF ----
    print("Loading challenge SDF ...")
    raw_records = CHALLENGE_SDF.read_text(encoding="utf-8", errors="ignore").count("$$$$")
    ch = load_challenge_sdf(CHALLENGE_SDF)
    ch.to_csv(OUT / "challenge_molecule_table.csv")
    ch_ts = task_summary(ch)
    ch_ts.to_csv(OUT / "challenge_task_summary.csv", index=False)
    roots = [s.rsplit("-", 1)[0] for s in ch.index]
    summary["challenge_train_sdf"] = {
        "n_raw_records": raw_records,
        "n_parsed": len(ch),
        "n_unique_inchikey": int(ch["inchikey"].nunique()),
        "n_duplicate_inchikey_groups": int((ch.groupby("inchikey").size() > 1).sum()),
        "n_compound_roots_with_multiple_samples": int(
            (pd.Series(roots).value_counts() > 1).sum()
        ),
        "n_with_at_least_one_label": int(ch[TASKS].notna().any(axis=1).sum()),
        "n_all_labels_missing": int(ch[TASKS].isna().all(axis=1).sum()),
    }

    # ---- Challenge evaluation sets (structures only / partial labels) ----
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

    # ---- Cross-version agreement ----
    print("Cross-version agreement ...")
    agreement, joined = cross_version_agreement(mn_full, ch)
    agreement.to_csv(OUT / "cross_version_label_agreement.csv", index=False)
    summary["cross_version"] = {
        "n_csv_rows_matched_to_sdf_by_inchikey": int(agreement["n_matched"].iloc[0]),
        "n_csv_rows_unmatched": len(mn) - int(agreement["n_matched"].iloc[0]),
        "n_label_conflicts_total": int(agreement["n_conflict"].sum()),
        "n_sdf_only_labels_total": int(agreement["n_sdf_only_labeled"].sum()),
    }

    # ---- Scaffold split leakage audit ----
    print("Scaffold split audit ...")
    sizes, split_rates, leakage, nn_df = split_audit(mn_full)
    split_rates.to_csv(OUT / "split_task_active_rates.csv", index=False)
    nn_df.to_csv(OUT / "test_train_tanimoto.csv", index=False)
    summary["split"] = {"sizes": sizes, **leakage}

    with open(OUT / "audit_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str)[:4000])


if __name__ == "__main__":
    main()
