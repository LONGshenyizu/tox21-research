# ABOUTME: Tests for the Murcko scaffold split (same algorithm as DeepChem's ScaffoldSplitter).
# ABOUTME: Verifies deterministic ordering, group integrity, greedy fill behaviour, and skipping of invalid SMILES.
import pytest

from tox21_research.splits import murcko_scaffold, scaffold_split_indices


class TestMurckoScaffold:
    def test_benzene_derivatives_share_scaffold(self):
        s1 = murcko_scaffold("c1ccc(cc1)O")
        s2 = murcko_scaffold("c1ccc(cc1)N")
        assert s1 == s2 == "c1ccccc1"

    def test_acyclic_has_empty_scaffold(self):
        assert murcko_scaffold("CCCCO") == ""

    def test_invalid_smiles_returns_none(self):
        assert murcko_scaffold("not_a_smiles") is None


class TestScaffoldSplitIndices:
    def test_partition_and_sizes(self):
        # 3 benzene derivatives share one scaffold (24 members); the 3 acyclic
        # molecules share the empty scaffold (24 members). Greedy fill puts the
        # chain group (first index 3) in train and the ring group in test.
        smiles = ["c1ccccc1O", "c1ccccc1N", "c1ccccc1Cl", "CCCCO", "CCCCN", "CCCCCCO"] * 8
        train, valid, test, skipped = scaffold_split_indices(
            smiles, frac_train=0.8, frac_valid=0.1, frac_test=0.1
        )
        all_idx = sorted(train + valid + test)
        assert all_idx == list(range(len(smiles)))
        assert skipped == []
        assert len(train) == 24
        assert len(valid) == 0
        assert len(test) == 24
        assert set(train).isdisjoint(valid)
        assert set(train).isdisjoint(test)
        assert set(valid).isdisjoint(test)

    def test_same_scaffold_stays_together(self):
        # 10 benzene + 10 alkane molecules: groups are never split across train/test
        smiles = ["c1ccccc1O", "c1ccccc1N"] * 10 + ["CCCCO", "CCCCN"] * 10
        train, valid, test, skipped = scaffold_split_indices(smiles)
        groups = {i: ("ring" if "c1" in s else "chain") for i, s in enumerate(smiles)}
        for split in (train, valid, test):
            kinds = {groups[i] for i in split}
            # a split may contain one group kind only if the other group went elsewhere
            assert len(kinds) <= 2
        ring_splits = [
            [groups[i] for i in split].count("ring") for split in (train, valid, test)
        ]
        # ring group (20 members) must sit fully inside exactly one split
        assert sorted(ring_splits) == [0, 0, 20]

    def test_deterministic(self):
        smiles = ["c1ccccc1O", "CCCCO", "c1ccccc1N", "CCCCCCO", "CCCCCO", "CCCCCCCO"] * 5
        r1 = scaffold_split_indices(smiles)
        r2 = scaffold_split_indices(smiles)
        assert r1 == r2

    def test_invalid_smiles_skipped(self):
        smiles = ["CCO", "bad_smiles", "c1ccccc1"]
        train, valid, test, skipped = scaffold_split_indices(smiles)
        assert skipped == [1]
        assert sorted(train + valid + test) == [0, 2]
