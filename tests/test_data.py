# ABOUTME: Tests for Tox21 dataset loading: MoleculeNet CSV parsing and challenge SDF parsing.
# ABOUTME: Verifies label parsing rules, canonicalization, and row-level invariants on synthetic data.
import math

import pandas as pd
import pytest

from tox21_research.data import (
    TASKS,
    load_challenge_sdf,
    load_moleculenet_csv,
    parse_label,
)


def _write_csv(tmp_path, rows, header=None):
    header = header or ["mol_id", "smiles"] + TASKS
    path = tmp_path / "mini.csv"
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestParseLabel:
    def test_binary_values(self):
        assert parse_label("0") == 0.0
        assert parse_label("1") == 1.0
        assert parse_label(0) == 0.0
        assert parse_label(1) == 1.0

    def test_missing_variants(self):
        assert parse_label("") is None
        assert parse_label(None) is None
        assert math.isnan(parse_label(float("nan")))

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError):
            parse_label("2")
        with pytest.raises(ValueError):
            parse_label("-1")


class TestLoadMoleculenetCsv:
    def test_rows_and_columns(self, tmp_path):
        path = _write_csv(
            tmp_path,
            [
                ["TOX1", "CCO"] + ["1"] + ["0"] * 11,
                ["TOX2", "c1ccccc1"] + [""] * 12,
            ],
        )
        df = load_moleculenet_csv(path)
        assert list(df.columns) == ["smiles"] + TASKS
        assert len(df) == 2
        assert df.loc["TOX1", "NR-AR"] == 1.0
        assert df.loc["TOX1", "SR-p53"] == 0.0
        # TOX2 has all labels missing
        assert df.loc["TOX2"].drop("smiles").isna().all()

    def test_duplicate_mol_id_raises(self, tmp_path):
        path = _write_csv(
            tmp_path,
            [
                ["TOX1", "CCO"] + ["0"] * 12,
                ["TOX1", "CCO"] + ["0"] * 12,
            ],
        )
        with pytest.raises(ValueError, match="duplicate mol_id"):
            load_moleculenet_csv(path)


def _write_sdf(tmp_path, molblocks_with_props):
    path = tmp_path / "mini.sdf"
    records = []
    for name, props in molblocks_with_props:
        rec = f"{name}\n  test\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0\nM  END\n"
        for k, v in props.items():
            rec += f">  <{k}>\n{v}\n\n"
        records.append(rec)
    path.write_text("$$$$\n".join(records) + "$$$$\n", encoding="utf-8")
    return path


class TestLoadChallengeSdf:
    def test_props_and_missing_labels(self, tmp_path):
        path = _write_sdf(
            tmp_path,
            [
                ("NCGC1-01", {"DSSTox_CID": "11", "NR-AR": "1", "SR-p53": "0"}),
                ("NCGC2-01", {"DSSTox_CID": "12", "NR-AR": "0"}),
            ],
        )
        df = load_challenge_sdf(path)
        assert len(df) == 2
        assert df.loc["NCGC1-01", "dsstox_cid"] == 11
        assert df.loc["NCGC1-01", "NR-AR"] == 1.0
        assert df.loc["NCGC1-01", "SR-p53"] == 0.0
        # NCGC2-01 was not tested in SR-p53 -> NaN
        assert pd.isna(df.loc["NCGC2-01", "SR-p53"])
        # structure-derived columns exist
        assert df.loc["NCGC1-01", "smiles"] == "C"
        assert len(df.loc["NCGC1-01", "inchikey"]) > 0
