# Reproducibility Guide（第三方复现指南）

日期：2026-08-21 ｜ 分支：`final-package` ｜ 前置：Python 3.11.x、约 4GB 磁盘、可选 Docker

本指南分四档：**L1 环境与测试**（分钟级）→ **L2 工件重算**（无需重训，分钟级）→ **L3 全流程重跑**（含重训，小时级）→ **L4 容器验证**。全部命令在仓库根目录执行；Windows 示例（Linux/Mac 将 `.venv/Scripts/` 换为 `.venv/bin/`）。

## L1 环境与测试

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r environment/requirements.txt
.venv/Scripts/python -m pytest tests/ -q
```

期望：`84 passed`（2 个 warning 为已知的 httpx 弃用提示，来自 fastapi testclient 自身）。
注：`tests/test_regression_audit.py` 的 2 项真实数据回归测试需要 `data/raw/` 已下载（见 L3 第 1 步），未下载时静默跳过。

## L2 工件重算（推荐：不重训验证全部头条数字）

前提：`data/processed/tox21_modeling.npz` 与 `results/final/*.csv` 均在 git 内（无需下载数据）。

1. **数据规模与分割**：读 npz 的 `train_idx/valid_idx/test_idx` 长度 → 6,258/782/783；`data/processed/manifest.json` 的 `dropped_mol_ids` → 8 条。
2. **头条指标**（约 10 行 sklearn）：将 `results/final/test_predictions_ensemble.csv`（行序 = npz `test_idx` 的 mol_id 顺序）与 npz `Y[test_idx]` 对齐，逐任务算 ROC-AUC/PR-AUC 再宏平均。期望：宏 ROC-AUC **0.700314**、PR-AUC **0.321138**、BAcc **0.602436**（与 `test_metrics_ensemble.csv`、`test_summary.csv` 及 README §4 一致）。
3. **选型数字**：`results/interim/model_comparison.csv` 首行宏 ROC-AUC **0.7376**。
4. **random 对照**：`results/final/random_split_sensitivity.csv` 三行均值 **0.8073**、std **0.0101**。
5. **推理一致性**：任取若干 SMILES，分别跑 CLI 与 API，比较 12×n 个概率：

```bash
printf 'CCOc1ccc2nc(S(N)(=O)=O)sc2c1\nCC(=O)Oc1ccccc1C(=O)O\nnot_a_smiles\n' > sample.smiles
PYTHONPATH=src .venv/Scripts/python scripts/predict.py sample.smiles sample_out.csv
.venv/Scripts/python - <<'PY'
import json, pandas as pd
from fastapi.testclient import TestClient
from tox21_research.api import create_app
smiles = open("sample.smiles").read().splitlines()
cli = pd.read_csv("sample_out.csv", index_col=0)
with TestClient(create_app()) as c:
    preds = c.post("/predict", json={"smiles": smiles}).json()["predictions"]
diffs = [abs(p - float(cli.iloc[i][t]))
         for i, item in enumerate(preds) if item["valid"]
         for t, p in item["probabilities"].items()]
print(f"n={len(diffs)} max|diff|={max(diffs):.3e}")   # 期望 0.0（同机同进程）
PY
```

注：CLI 对无效 SMILES 会抛错（研究 CLI 已知行为，见 limitations.md）；上例若要含无效项请只用有效 SMILES。跨平台（Windows↔Linux 容器）存在已量化的 1-ULP（1.11e-16）求和顺序差异，以 1e-12 容差判等。

6. **模型完整性**：`src/tox21_research/model_integrity.json` 内的 sha256 应与 `results/final/frozen_config.json`、`results/final/model/model_seed42.joblib` 实际哈希一致（`sha256sum`）；篡改任一文件后 `load_frozen_predictor()` 应拒绝启动。

## L3 全流程重跑（重训，约数小时 CPU）

```bash
.venv/Scripts/python scripts/download_data.py     # 下载并校验（结束应打印 all files present and verified）
.venv/Scripts/python scripts/audit_data.py        # 数据审计 → results/interim/audit/
.venv/Scripts/python scripts/prepare_data.py      # 特征与分割缓存 → data/processed/
.venv/Scripts/python scripts/run_experiments.py   # 选型（期望榜首 lgbm 0.7376）
.venv/Scripts/python scripts/error_analysis.py    # 验证集误差分析
.venv/Scripts/python scripts/final_test.py        # 冻结 test 评测（期望 0.7003/0.3211）
.venv/Scripts/python scripts/random_split_check.py# random 敏感性（期望 0.807±0.010）
```

- 确定性：所有随机性由显式 seed 控制（LGBM seed 42；MLP 0/1/2）；审计期重训一致到 1.1e-16。
- `final_test.py` 会重写 `results/final/`（这是它的设计：一次性冻结评测）。若只想验证而不覆盖冻结产物，请先在副本仓库执行，或仅做 L2。
- 网络不可达时：download_data 逐文件报 FAIL 并以非零码退出；此时 L2/L1 仍完全可做（不依赖网络）。

## L4 容器验证

```bash
docker build -t tox21-api:v1 .
docker run -d -p 8000:8000 --name tox21-api tox21-api:v1
curl http://127.0.0.1:8000/health                                   # {"status":"ok",...}
docker exec tox21-api id -u                                          # 10001（非 root）
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d '{"smiles":["CCO"]}'
```

期望：/health 200；predict 概率与本地 CLI 一致（≤1e-12）；`GET /docs` 404。基础镜像 `python:3.11-slim`；本机无法直连 docker.io 时可经镜像源拉取（见 `reports/engineering_freeze.md` §3）。本仓库验证环境的构建实测记录见 `final_status.md`。
