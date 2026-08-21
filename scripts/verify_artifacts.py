# ABOUTME: Release artifact verifier: frozen-model integrity, config parity, split/manifest consistency, raw-data checksums.
# ABOUTME: Read-only; prints one line per check and exits non-zero on any failure. Absent optional files are skipped and counted.
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import download_data  # noqa: E402 - reuse its pinned (path, url, sha256) list


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_model_integrity(root, failures):
    manifest_path = root / "src" / "tox21_research" / "model_integrity.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in sorted(manifest.items()):
        path = root / "results" / "final" / relative
        if not path.exists():
            failures.append(f"missing frozen artifact: {relative}")
            continue
        actual = sha256(path)
        status = "OK" if actual == expected else "FAIL"
        if status == "FAIL":
            failures.append(f"integrity mismatch: {relative}")
        print(f"[{status}] model integrity {relative} {actual[:16]}...")


def check_config_parity(root, failures):
    frozen = (root / "results" / "final" / "frozen_config.json").read_text(encoding="utf-8")
    source = (root / "configs" / "final_model.json").read_text(encoding="utf-8")
    if json.loads(frozen) == json.loads(source):
        print("[OK] config parity results/final/frozen_config.json == configs/final_model.json")
    else:
        failures.append("frozen config differs from configs/final_model.json")
        print("[FAIL] config parity results/final/frozen_config.json != configs/final_model.json")


def check_split_consistency(root, failures):
    import numpy as np

    npz = np.load(root / "data" / "processed" / "tox21_modeling.npz", allow_pickle=False)
    manifest = json.loads((root / "data" / "processed" / "manifest.json").read_text(encoding="utf-8"))
    actual = {k: int(len(npz[f"{k}_idx"])) for k in ("train", "valid", "test")}
    claimed = manifest["split_sizes"]
    n_rows = npz["Y"].shape[0]
    checks = [
        (actual == claimed, f"split sizes npz {actual} == manifest {claimed}"),
        (manifest["n_modeling"] == n_rows, "manifest n_modeling == npz rows"),
        (
            manifest["n_total_rows"] == n_rows + manifest["n_dropped_invalid_smiles"],
            "total rows == modeling + dropped",
        ),
        (
            len(manifest["dropped_mol_ids"]) == manifest["n_dropped_invalid_smiles"],
            "dropped id count consistent",
        ),
    ]
    for ok, label in checks:
        if not ok:
            failures.append(f"split/manifest inconsistency: {label}")
        print(f"[{'OK' if ok else 'FAIL'}] {label}")


def check_raw_checksums(root, failures):
    skipped = 0
    for path, _url, expected in download_data.FILES:
        relative = path.relative_to(download_data.RAW)
        target = root / "data" / "raw" / relative
        if not target.exists():
            skipped += 1
            continue
        actual = sha256(target)
        if actual != expected:
            failures.append(f"raw checksum mismatch: {relative}")
            print(f"[FAIL] raw checksum {relative}")
        else:
            print(f"[OK] raw checksum {relative} {actual[:16]}...")
    print(f"[SKIP] raw checksums: {skipped} file(s) not present "
          f"(regenerate with scripts/download_data.py)")


def main():
    parser = argparse.ArgumentParser(description="Verify release artifact integrity.")
    parser.add_argument("--root", default=str(ROOT), help="repository root to verify")
    args = parser.parse_args()
    root = Path(args.root)

    failures = []
    check_model_integrity(root, failures)
    check_config_parity(root, failures)
    check_split_consistency(root, failures)
    check_raw_checksums(root, failures)

    if failures:
        print(f"\nARTIFACT VERIFICATION FAILED ({len(failures)} problem(s))")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nARTIFACT VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
