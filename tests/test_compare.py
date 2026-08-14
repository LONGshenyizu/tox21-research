# ABOUTME: Tests for cross-version label agreement by explicit compound-id mapping (no implicit index joins).
# ABOUTME: Verifies the empty-match guard, all three batch-aggregation conventions, and structural diagnostics.
import numpy as np
import pandas as pd
import pytest

from tox21_research.compare import (
    AGGREGATIONS,
    challenge_labels_by_cid,
    csv_compound_id,
    intra_compound_disagreement,
    label_agreement,
    structure_match,
)
from tox21_research.data import TASKS


def _mn_frame(rows):
    """rows: {mol_id: {task: label or None}}"""
    data = {t: [] for t in TASKS}
    index = []
    for mol_id, labels in rows.items():
        index.append(mol_id)
        for t in TASKS:
            v = labels.get(t)
            data[t].append(np.nan if v is None else float(v))
    return pd.DataFrame(data, index=pd.Index(index, name="mol_id"))


def _ch_frame(samples):
    """samples: {sample_id: (dsstox_cid, {task: label or None})}"""
    rows = {}
    for sample_id, (cid, labels) in samples.items():
        row = {"dsstox_cid": cid, "smiles": "CCO", "inchikey": f"IK{cid:014d}"}
        for t in TASKS:
            v = labels.get(t)
            row[t] = np.nan if v is None else float(v)
        rows[sample_id] = row
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("sample_id")


class TestCsvCompoundId:
    def test_strips_tox_prefix(self):
        assert csv_compound_id("TOX3021") == 3021
        assert csv_compound_id("TOX17577") == 17577


class TestChallengeLabelsByCid:
    def test_first_any_majority(self):
        # cid 1: first sample active, others inactive -> first=1, any=1, majority=0
        ch = _ch_frame({
            "NCGC1-01": (1, {"NR-AR": 1}),
            "NCGC1-02": (1, {"NR-AR": 0}),
            "NCGC1-03": (1, {"NR-AR": 0}),
            "NCGC2-01": (2, {"NR-AR": 0}),
        })
        assert challenge_labels_by_cid(ch, "first").loc[1, "NR-AR"] == 1.0
        assert challenge_labels_by_cid(ch, "any_active").loc[1, "NR-AR"] == 1.0
        # tie (mean 0.5) counts as active under majority
        ch_tie = _ch_frame({
            "N1": (1, {"NR-AR": 1}), "N2": (1, {"NR-AR": 0}),
        })
        assert challenge_labels_by_cid(ch_tie, "majority").loc[1, "NR-AR"] == 1.0
        assert challenge_labels_by_cid(ch, "majority").loc[1, "NR-AR"] == 0.0

    def test_never_tested_stays_nan(self):
        ch = _ch_frame({"N1": (1, {})})
        for agg in AGGREGATIONS:
            assert np.isnan(challenge_labels_by_cid(ch, agg).loc[1, "SR-p53"])


class TestLabelAgreement:
    def test_hand_computed_counts(self):
        ch = _ch_frame({
            # cid 1: NR-AR first=1/any=1/majority=0 vs CSV 0
            "s1": (1, {"NR-AR": 1, "SR-p53": 0}),
            "s2": (1, {"NR-AR": 0}),
            "s3": (1, {"NR-AR": 0}),
            # cid 2: SR-p53 only in SDF
            "s4": (2, {"NR-AR": 0, "SR-p53": 1}),
        })
        mn = _mn_frame({
            "TOX1": {"NR-AR": 0, "SR-p53": 0},   # NR-AR: conf(first/any), agree(majority)
            "TOX2": {"NR-AR": 1},                 # NR-AR: conf(all); SR-p53: csv missing, sdf 1 -> sdf_only
            "TOX9": {"NR-AR": 1},                 # no cid-9 counterpart: unmatched row
        })
        table, totals = label_agreement(mn, ch, "first")
        row_ar = table.loc["NR-AR"]
        assert row_ar["n_both"] == 2
        assert row_ar["n_conflict"] == 2  # TOX1 (0 vs 1) and TOX2 (1 vs 0)
        assert row_ar["n_sdf_only"] == 0
        row_p53 = table.loc["SR-p53"]
        assert row_p53["n_both"] == 1 and row_p53["n_conflict"] == 0
        assert row_p53["n_sdf_only"] == 1
        assert totals["n_matched_rows"] == 2
        assert totals["n_unmatched_rows"] == 1

        table_maj, _ = label_agreement(mn, ch, "majority")
        # cid1 majority=0 -> TOX1 agrees; TOX2 still conflicts with cid2's 0
        assert table_maj.loc["NR-AR", "n_conflict"] == 1

    def test_zero_match_raises(self):
        ch = _ch_frame({"s1": (100, {"NR-AR": 0})})
        mn = _mn_frame({"TOX1": {"NR-AR": 1}})
        with pytest.raises(ValueError, match="no rows matched"):
            label_agreement(mn, ch, "first")

    def test_all_aggregations_accepted(self):
        ch = _ch_frame({"s1": (1, {"NR-AR": 0})})
        mn = _mn_frame({"TOX1": {"NR-AR": 0}})
        for agg in AGGREGATIONS:
            _, totals = label_agreement(mn, ch, agg)
            assert totals["n_matched_rows"] == 1


class TestStructureMatch:
    def test_counts_by_inchikey(self):
        ch = _ch_frame({"s1": (1, {}), "s2": (2, {})})
        mn = _mn_frame({
            "TOX1": {},   # shares structure with cid 1
            "TOX2": {},   # structure only in CSV
            "TOX3": {},   # shares with cid 2
        })
        mn["inchikey"] = ["IK00000000000001", "IK99999999999999", "IK00000000000002"]
        rates = structure_match(mn, ch)
        assert rates["matched"] == 2
        assert rates["unmatched"] == 1


class TestIntraCompoundDisagreement:
    def test_counts_disagreeing_compounds(self):
        ch = _ch_frame({
            "s1": (1, {"NR-AR": 1}), "s2": (1, {"NR-AR": 0}),  # disagrees
            "s3": (2, {"NR-AR": 0}), "s4": (2, {"NR-AR": 0}),  # agrees
            "s5": (3, {"NR-AR": 1}),                            # single sample
        })
        table = intra_compound_disagreement(ch)
        row = table.loc["NR-AR"]
        assert row["n_multi_sample_compounds"] == 2
        assert row["n_disagreeing_compounds"] == 1
        assert row["disagreement_rate"] == 0.5
