# ABOUTME: Molecular fingerprint features: ECFP/Morgan bit vectors and MACCS keys.
# ABOUTME: Invalid SMILES raise immediately so callers never train on silently dropped rows.
import numpy as np
from rdkit import Chem
from rdkit.Chem.MACCSkeys import GenMACCSKeys
from rdkit.Chem.AllChem import GetMorganFingerprintAsBitVect


def _parse(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    return mol


def ecfp_matrix(smiles_list, radius=2, n_bits=2048):
    """Binary ECFP (Morgan) fingerprint matrix, shape (n, n_bits), uint8."""
    rows = []
    for smiles in smiles_list:
        fp = GetMorganFingerprintAsBitVect(_parse(smiles), radius, nBits=n_bits)
        arr = np.zeros(n_bits, dtype=np.uint8)
        Chem.DataStructs.ConvertToNumpyArray(fp, arr)
        rows.append(arr)
    return np.vstack(rows)


def maccs_matrix(smiles_list):
    """Binary MACCS keys (167 bits) fingerprint matrix, uint8."""
    rows = []
    for smiles in smiles_list:
        fp = GenMACCSKeys(_parse(smiles))
        arr = np.zeros(fp.GetNumBits(), dtype=np.uint8)
        Chem.DataStructs.ConvertToNumpyArray(fp, arr)
        rows.append(arr)
    return np.vstack(rows)
