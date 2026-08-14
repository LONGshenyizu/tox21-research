# ABOUTME: Cross-version comparison between the MoleculeNet CSV and the 2014 challenge SDF.
# ABOUTME: Joins by explicit compound id (mol_id TOX#### -> DSSTox_CID); InChIKey matching is a
# ABOUTME: separate structural diagnostic. No single batch-aggregation is treated as ground truth:
# ABOUTME: three conventions are reported as a sensitivity analysis.
import numpy as np
import pandas as pd
from rdkit import Chem

from tox21_research.data import TASKS

AGGREGATIONS = ("first", "any_active", "majority")


def csv_compound_id(mol_id):
    """Numeric compound id behind a MoleculeNet mol_id (TOX#### -> ####)."""
    return int(str(mol_id)[3:])


def challenge_labels_by_cid(ch, aggregation="first"):
    """Collapse challenge sample-level labels to one row per DSSTox_CID.

    first: labels of the first sample record; any_active: 1 if any sample is
    active; majority: 1 if at least half the labeled samples are active
    (ties count as active). Untested endpoints stay NaN under every rule.
    """
    grouped = ch.groupby("dsstox_cid")[list(TASKS)]
    if aggregation == "first":
        return grouped.first()
    if aggregation == "any_active":
        return grouped.max()
    if aggregation == "majority":
        return (grouped.mean() >= 0.5).astype(float).mask(grouped.max().isna())
    raise ValueError(f"unknown aggregation: {aggregation!r}")


def label_agreement(mn, ch, aggregation="first"):
    """Per-task label agreement between the CSV and the challenge SDF.

    Returns (per_task_table, totals). Raises ValueError when no row matches,
    so a broken identifier mapping can never be reported as "zero conflicts".
    """
    sdf = challenge_labels_by_cid(ch, aggregation)
    left = mn[list(TASKS)].copy()
    left.index = pd.Index([csv_compound_id(m) for m in mn.index], name="dsstox_cid")
    joined = left.join(sdf, rsuffix="_ch", how="left")

    matched = np.zeros(len(joined), dtype=bool)
    for task in TASKS:
        matched |= joined[f"{task}_ch"].notna().to_numpy()
    if not matched.any():
        raise ValueError(
            "no rows matched between versions -- identifier mapping is broken"
        )

    rows = {}
    for task in TASKS:
        a = joined[task].to_numpy()
        b = joined[f"{task}_ch"].to_numpy()
        both = matched & ~np.isnan(a) & ~np.isnan(b)
        rows[task] = {
            "n_both": int(both.sum()),
            "n_agree": int((both & (a == b)).sum()),
            "n_conflict": int((both & (a != b)).sum()),
            "n_csv_only": int((matched & ~np.isnan(a) & np.isnan(b)).sum()),
            "n_sdf_only": int((matched & np.isnan(a) & ~np.isnan(b)).sum()),
        }
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "task"
    totals = {
        "aggregation": aggregation,
        "n_matched_rows": int(matched.sum()),
        "n_unmatched_rows": int((~matched).sum()),
        "n_conflict_total": int(table["n_conflict"].sum()),
    }
    return table, totals


def structure_match(mn, ch):
    """How many CSV rows share an InChIKey with any challenge sample (diagnostic)."""
    if "inchikey" not in mn.columns:
        raise ValueError("mn must carry an 'inchikey' column")
    mn_keys = mn["inchikey"]
    ch_keys = set(ch["inchikey"].dropna())
    matched = mn_keys.notna() & mn_keys.isin(ch_keys)
    return {
        "matched": int(matched.sum()),
        "unmatched": int((mn_keys.notna() & ~matched).sum()),
        "no_structure": int(mn_keys.isna().sum()),
    }


def intra_compound_disagreement(ch):
    """Per-task disagreement between same-compound samples in the challenge SDF."""
    rows = {}
    for task in TASKS:
        grouped = ch.groupby("dsstox_cid")[task]
        counts = grouped.count()
        multi = counts[counts > 1]
        if len(multi) == 0:
            rows[task] = {
                "n_multi_sample_compounds": 0,
                "n_disagreeing_compounds": 0,
                "disagreement_rate": float("nan"),
            }
            continue
        ranges = grouped.max() - grouped.min()
        disagree = int((ranges.loc[multi.index] > 0).sum())
        rows[task] = {
            "n_multi_sample_compounds": int(len(multi)),
            "n_disagreeing_compounds": disagree,
            "disagreement_rate": round(disagree / len(multi), 4),
        }
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "task"
    return table
