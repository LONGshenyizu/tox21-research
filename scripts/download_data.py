# ABOUTME: Downloads and verifies all raw Tox21 data files used in this study, then extracts the challenge SDFs.
# ABOUTME: Checksums are pinned to the versions recorded in data/raw/PROVENANCE.md (downloaded 2026-08-14).
import gzip
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CH = RAW / "challenge2014"

FILES = [
    # (path, url, sha256)
    (
        RAW / "tox21_moleculenet.csv.gz",
        "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/tox21.csv.gz",
        "45d09792492ce049039dd24aa27b07fc79ce20c573187d4d90bcd178c0c0d360",
    ),
    (
        CH / "tox21_10k_data_all.zip",
        "https://tripod.nih.gov/tox21/challenge/download?id=tox21_10k_data_allsdf&sec=",
        "024a3ae2690bcd4a593e6e0b10b455470b9bcb1d8f299dd36f220a250181517b",
    ),
    (
        CH / "tox21_10k_challenge_test.zip",
        "https://tripod.nih.gov/tox21/challenge/download?id=tox21_10k_challenge_testsdf&sec=",
        "7ab05627b78db60f5a8426dc18d3bd50904ddab0e4ba1b2f33ad883f5087afd9",
    ),
    (
        CH / "tox21_10k_challenge_test.smiles",
        "https://tripod.nih.gov/tox21/challenge/download?id=tox21_10k_challenge_testsmiles&sec=",
        "4832698e22ab993e392a4292f6001165c5020104d2156d6095cd687baaecf634",
    ),
    (
        CH / "tox21_10k_challenge_score.zip",
        "https://tripod.nih.gov/tox21/challenge/download?id=tox21_10k_challenge_scoresdf&sec=",
        "786617d7a1921c904ee5294fd5a643148984dc5f423dbb3d4b0fbbf57975e4e1",
    ),
    (
        CH / "tox21_10k_challenge_score.smiles",
        "https://tripod.nih.gov/tox21/challenge/download?id=tox21_10k_challenge_scoresmiles&sec=",
        "57e4fef6d42f7867486967fe6c1a9e98c42aaed43023745c460ff0d102ce5786",
    ),
    (
        CH / "tox21-challenge.zip",
        "https://tripod.nih.gov/tox21/challenge/final-results/tox21-challenge.zip",
        "edf17b749bf18af203220780d0c7f8fde06fe91a11cb073eda3c3cbe6d37f53b",
    ),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    CH.mkdir(parents=True, exist_ok=True)
    failures = []
    for path, url, expected in FILES:
        if path.exists() and sha256(path) == expected:
            print(f"OK (cached)  {path.name}")
            continue
        print(f"downloading  {path.name} ...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tox21-research/0.1"})
            with urllib.request.urlopen(req, timeout=300) as resp, open(path, "wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as exc:  # noqa: BLE001 - report every file, fail at the end
            print(f"FAIL         {path.name}: {exc}")
            failures.append(path.name)
            continue
        actual = sha256(path)
        if actual != expected:
            print(f"FAIL         {path.name}: sha256 {actual} != {expected}")
            failures.append(path.name)
        else:
            print(f"OK           {path.name}")
    # extract the SDFs used by the audit
    for z in ["tox21_10k_data_all.zip", "tox21_10k_challenge_test.zip", "tox21_10k_challenge_score.zip"]:
        archive = CH / z
        if archive.exists():
            with zipfile.ZipFile(archive) as f:
                f.extractall(CH)
    # decompress the MoleculeNet CSV copy for convenience
    gz = RAW / "tox21_moleculenet.csv.gz"
    if gz.exists() and not (RAW / "tox21_moleculenet.csv").exists():
        with gzip.open(gz, "rb") as src, open(RAW / "tox21_moleculenet.csv", "wb") as dst:
            shutil.copyfileobj(src, dst)
    if failures:
        sys.exit(f"checksum/download failures: {failures}")
    print("all files present and verified")


if __name__ == "__main__":
    main()
