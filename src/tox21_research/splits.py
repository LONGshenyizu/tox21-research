# ABOUTME: Murcko scaffold train/validation/test split, mirroring DeepChem's ScaffoldSplitter algorithm.
# ABOUTME: Deterministic (no seed needed); molecules with unparsable SMILES are reported, not silently dropped.
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


def murcko_scaffold(smiles):
    """Return the Bemis-Murcko scaffold SMILES, or None if the SMILES is invalid."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)


def scaffold_split_indices(
    smiles_list, frac_train=0.8, frac_valid=0.1, frac_test=0.1
):
    """Split row indices by Murcko scaffold, largest scaffold group first.

    Returns (train, valid, test, skipped): index lists plus indices whose SMILES
    produced no scaffold. Groups are never split across subsets; the greedy fill
    reproduces deepchem.splits.ScaffoldSplitter exactly.
    """
    if abs(frac_train + frac_valid + frac_test - 1.0) > 1e-9:
        raise ValueError("split fractions must sum to 1")

    scaffolds = {}
    skipped = []
    for idx, smiles in enumerate(smiles_list):
        scaffold = murcko_scaffold(smiles)
        if scaffold is None:
            skipped.append(idx)
        else:
            scaffolds.setdefault(scaffold, []).append(idx)

    groups = sorted(scaffolds.values())
    groups = sorted(groups, key=lambda g: (len(g), g[0]), reverse=True)

    train_cutoff = frac_train * len(smiles_list)
    valid_cutoff = (frac_train + frac_valid) * len(smiles_list)
    train, valid, test = [], [], []
    for group in groups:
        if len(train) + len(group) > train_cutoff:
            if len(train) + len(valid) + len(group) > valid_cutoff:
                test.extend(group)
            else:
                valid.extend(group)
        else:
            train.extend(group)
    return train, valid, test, skipped
