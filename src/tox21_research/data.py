# ABOUTME: Loaders for the two public Tox21 data versions: the MoleculeNet CSV and the 2014 challenge SDFs.
# ABOUTME: Labels are parsed strictly (0/1/missing) so any unexpected value fails loudly instead of being silently dropped.
import math

import pandas as pd
from rdkit import Chem

from tox21_research.splits import scaffold_split_indices

# Canonical task order, identical to the MoleculeNet Tox21 CSV column order.
TASKS = [
    "NR-AR",
    "NR-AR-LBD",
    "NR-AhR",
    "NR-Aromatase",
    "NR-ER",
    "NR-ER-LBD",
    "NR-PPAR-gamma",
    "SR-ARE",
    "SR-ATAD5",
    "SR-HSE",
    "SR-MMP",
    "SR-p53",
]


def parse_label(value):
    """Return 0.0, 1.0, or None (missing). Any other value raises ValueError."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return float("nan")
        if value in (0.0, 1.0):
            return value
        raise ValueError(f"unexpected label value: {value!r}")
    if isinstance(value, int):
        if value in (0, 1):
            return float(value)
        raise ValueError(f"unexpected label value: {value!r}")
    text = str(value).strip()
    if text == "":
        return None
    if text == "0":
        return 0.0
    if text == "1":
        return 1.0
    raise ValueError(f"unexpected label value: {text!r}")


def load_moleculenet_csv(path):
    """Load the MoleculeNet Tox21 CSV into a DataFrame indexed by mol_id.

    Columns: smiles + the 12 task labels (float, NaN = not tested/inconclusive).
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"mol_id", "smiles"} | set(TASKS)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if df["mol_id"].duplicated().any():
        raise ValueError("duplicate mol_id in MoleculeNet CSV")
    labels = df[TASKS].map(parse_label)
    labels = labels.map(lambda v: float("nan") if v is None else v)
    out = pd.concat([df[["smiles"]], labels], axis=1)
    out.index = pd.Index(df["mol_id"], name="mol_id")
    return out


def load_challenge_sdf(path):
    """Load a 2014 challenge SDF into a DataFrame indexed by sample/record title.

    Columns: smiles (RDKit canonical), inchikey, dsstox_cid (when present),
    plus the 12 task labels (NaN = tag absent).
    Records that RDKit fails to parse are skipped; callers compare row counts
    against the raw record count to detect this.
    """
    supplier = Chem.SDMolSupplier(str(path), sanitize=True, removeHs=False)
    rows = []
    for mol in supplier:
        if mol is None:
            continue
        props = mol.GetPropsAsDict()
        row = {
            "smiles": Chem.MolToSmiles(mol),
            "inchikey": Chem.MolToInchiKey(mol),
            "dsstox_cid": props.get("DSSTox_CID", float("nan")),
        }
        for task in TASKS:
            parsed = parse_label(props[task]) if task in props else None
            row[task] = float("nan") if parsed is None else parsed
        rows.append((mol.GetProp("_Name").strip(), row))
    if not rows:
        raise ValueError(f"no parsable molecules in {path}")
    df = pd.DataFrame.from_dict(dict(rows), orient="index")
    df.index.name = "sample_id"
    return df


def load_modeling_data(csv_path):
    """Modeling frame and deterministic scaffold split shared by preparation and audit.

    Rows whose SMILES RDKit cannot parse are dropped (their ids are returned).
    Returns (frame, train_idx, valid_idx, test_idx, dropped_ids). prepare_data
    and audit_data both call this, so the audited split can never silently
    diverge from the modeling split.
    """
    df = load_moleculenet_csv(csv_path)
    parseable = [Chem.MolFromSmiles(s) is not None for s in df["smiles"]]
    dropped = [str(m) for m, ok in zip(df.index, parseable) if not ok]
    frame = df.loc[parseable]
    train, valid, test, skipped = scaffold_split_indices(frame["smiles"].tolist())
    if skipped:
        raise ValueError("unparseable SMILES remained after filtering")
    return frame, train, valid, test, dropped
