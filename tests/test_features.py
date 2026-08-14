# ABOUTME: Tests for molecular fingerprint generation (ECFP/Morgan and MACCS).
# ABOUTME: Verifies shape, dtype, determinism, and invalid-SMILES handling on real molecules.
import numpy as np
import pytest

from tox21_research.features import ecfp_matrix, maccs_matrix


class TestEcfpMatrix:
    def test_shape_and_dtype(self):
        X = ecfp_matrix(["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"])
        assert X.shape == (3, 2048)
        assert X.dtype == np.uint8
        assert set(np.unique(X)) <= {0, 1}

    def test_deterministic(self):
        smiles = ["CCO", "c1ccccc1N"]
        assert np.array_equal(ecfp_matrix(smiles), ecfp_matrix(smiles))

    def test_distinct_molecules_differ(self):
        X = ecfp_matrix(["CCO", "CCC"])
        assert not np.array_equal(X[0], X[1])

    def test_invalid_smiles_raises(self):
        with pytest.raises(ValueError):
            ecfp_matrix(["CCO", "not_a_smiles"])

    def test_custom_params(self):
        X = ecfp_matrix(["CCOc1ccc2nc(S(N)(=O)=O)sc2c1"], n_bits=1024, radius=3)
        assert X.shape == (1, 1024)


class TestMaccsMatrix:
    def test_shape(self):
        X = maccs_matrix(["CCO", "c1ccccc1"])
        assert X.shape == (2, 167)
        assert X.dtype == np.uint8

    def test_benzene_has_ring_bits(self):
        X = maccs_matrix(["c1ccccc1"])
        assert X[0].sum() > 0
