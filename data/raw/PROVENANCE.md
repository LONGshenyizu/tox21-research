# 数据来源记录（Data Provenance）

所有文件下载日期：**2026-08-14**。校验和为 SHA-256。

## 1. MoleculeNet Tox21 CSV（本研究主数据）

| 项目 | 内容 |
|---|---|
| 文件 | `data/raw/tox21_moleculenet.csv.gz`（解压后 7831 行） |
| URL | https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/tox21.csv.gz |
| SHA-256 | `45d09792492ce049039dd24aa27b07fc79ce20c573187d4d90bcd178c0c0d360` |
| 文件时间戳 | 2017-12-21（gzip 头内原始文件名 `tox21.csv`） |
| 版本说明 | DeepChem `load_tox21()` 的官方下载数据（`deepchem/molnet/load_function/tox21_datasets.py` 中 `TOX21_URL` 与本 URL 一致）。MoleculeNet 论文正文称 8014 化合物，但该托管 CSV 实为 7831 行；本仓库以该 CSV 文件本身（校验和固定）为准。 |
| 上游来源 | 2014 Tox21 Data Challenge 训练数据（见下），本仓库已做逐分子交叉验证（见 `reports/data_audit.md`） |

## 2. Tox21 Data Challenge 2014 原始文件

来源站点：https://tripod.nih.gov/tox21/challenge/data.jsp （NIH/NCATS 官方挑战赛站点，审计时仍在线）。
目录：`data/raw/challenge2014/`。其中 3 个 "SDF" 下载实为 ZIP 压缩包，已按真实格式重命名；SHA256SUMS.txt 覆盖下载当天原始字节（.bin 命名）；下方校验和对应重命名后的文件（字节未变）。

| 文件 | 内容 | 下载 URL（`&sec=` 后为空） | SHA-256 |
|---|---|---|---|
| `tox21_10k_data_all.zip` → 解压 `tox21_10k_data_all.sdf` | 完整训练库：11,764 个 NCGC 样本，含 DSSTox_CID 与 12 个测定标签（0/1，无标签=inconclusive/未测） | `download?id=tox21_10k_data_allsdf` | `024a3ae2690bcd4a593e6e0b10b455470b9bcb1d8f299dd36f220a250181517b` |
| `tox21_10k_challenge_test.zip` → `tox21_10k_challenge_test.sdf` | 排行榜测试集：296 化合物，带各测定标签 | `download?id=tox21_10k_challenge_testsdf` | `7ab05627b78db60f5a8426dc18d3bd50904ddab0e4ba1b2f33ad883f5087afd9` |
| `tox21_10k_challenge_test.smiles` | 同上（SMILES + Sample ID，TSV） | `download?id=tox21_10k_challenge_testsmiles` | `4832698e22ab993e392a4292f6001165c5020104d2156d6095cd687baaecf634` |
| `tox21_10k_challenge_score.zip` → `tox21_10k_challenge_score.sdf` | 最终评测集：647 化合物，**仅结构无标签**（当年评分在服务器端完成，标签从未公开） | `download?id=tox21_10k_challenge_scoresdf` | `786617d7a1921c904ee5294fd5a643148984dc5f423dbb3d4b0fbbf57975e4e1` |
| `tox21_10k_challenge_score.smiles` | 同上（SMILES + Sample ID，TSV） | `download?id=tox21_10k_challenge_scoresmiles` | `57e4fef6d42f7867486967fe6c1a9e98c42aaed43023745c460ff0d102ce5786` |
| `tox21-challenge.zip` | 各参赛队对最终评测集的预测文件（历史存档，本研究不使用） | `final-results/tox21-challenge.zip` | `edf17b749bf18af203220780d0c7f8fde06fe91a11cb073eda3c3cbe6d37f53b` |

完整 URL 形如：`https://tripod.nih.gov/tox21/challenge/download?id=<id>&sec=`。

## 3. 版本关系（审计结论，详见 reports/data_audit.md）

- 原始训练库 11,764 个样本（NCGC 批次级）→ 按 InChIKey 去重为 8,041 个唯一结构（与 Huang et al. 2016 报告的挑战赛训练集 "8043 samples" 对应）。
- MoleculeNet CSV（7,831 行）是原始数据经进一步去重/整理后的子集：7,823 行可按 InChIKey 匹配回原始 SDF，**12 个终点全部标签零冲突**；其余 8 行为 RDKit 无法解析的 SMILES（铝盐类）。
- 排行榜测试集（296）与训练库零重叠；最终评测集（647）与训练库仅 7 个重叠，且无公开标签。
