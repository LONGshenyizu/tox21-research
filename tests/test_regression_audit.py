# ABOUTME: Real-data regression tests for the two error classes found in the stage-4 audit.
# ABOUTME: Guards: (1) identifier-space joins can never silently produce empty "zero-conflict" results;
# ABOUTME: (2) the audited/modeling split can never drift from the frozen split stored in the npz.
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rdkit import Chem, RDLogger

from tox21_research.compare import label_agreement, structure_match
from tox21_research.data import load_challenge_sdf, load_modeling_data, load_moleculenet_csv

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "tox21_moleculenet.csv.gz"
SDF = ROOT / "data" / "raw" / "challenge2014" / "tox21_10k_data_all.sdf"
NPZ = ROOT / "data" / "processed" / "tox21_modeling.npz"

requires_raw = pytest.mark.skipif(not CSV.exists() or not SDF.exists(), reason="raw data not downloaded")
slow = pytest.mark.slow


@slow
@requires_raw
def test_modeling_split_matches_frozen_npz():
    frame, train, valid, test, dropped = load_modeling_data(CSV)
    assert dropped == [
        "TOX31563", "TOX24724", "TOX24723", "TOX24552",
        "TOX24622", "TOX7518", "TOX28892", "TOX28623",
    ]
    assert len(frame) == 7823
    npz = np.load(NPZ)
    assert [str(m) for m in npz["mol_ids"]] == list(frame.index)
    for name, idx in [("train_idx", train), ("valid_idx", valid), ("test_idx", test)]:
        assert list(npz[name]) == list(idx), f"{name} differs from the frozen split"


@slow
@requires_raw
def test_label_agreement_matches_revised_audit_numbers():
    mn = load_moleculenet_csv(CSV)
    mn["inchikey"] = mn["smiles"].map(
        lambda s: Chem.MolToInchiKey(Chem.MolFromSmiles(s)) if Chem.MolFromSmiles(s) else None
    )
    ch = load_challenge_sdf(SDF)
    expected_conflicts = {"first": 228, "any_active": 11, "majority": 102}
    for agg, expected in expected_conflicts.items():
        table, totals = label_agreement(mn, ch, agg)
        assert totals["n_matched_rows"] == 7831
        conflicts = int(table["n_conflict"].sum())
        assert conflicts == expected, f"{agg}: {conflicts} != {expected}"
        assert int(table["n_sdf_only"].sum()) == 0
    # structure diagnostic: 6,562 of 7,831 rows share an InChIKey with the challenge library
    rates = structure_match(mn, ch)
    assert rates["matched"] == 6562
    assert rates["no_structure"] == 8
