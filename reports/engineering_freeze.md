# Engineering / API Freeze v1：FastAPI 推理服务

日期：2026-08-14 ｜ 科学基线：`b50229f`（Scientific Result Freeze v2，分支 `revision-v2`）｜ 本 commit 即 Engineering / API Freeze v1
服务代码：`src/tox21_research/inference.py`（共享推理实现）+ `src/tox21_research/api.py`（FastAPI）｜ 测试：`tests/test_api.py`

## 1. 冻结原则

服务**直接复用**冻结的预处理与预测链路，全仓库只有一份推理实现：

- 预处理/特征：`tox21_research.features.ecfp_matrix`（ECFP4，r=2，2048 bit）
- 模型文件：`results/final/model/model_seed42.joblib`（LightGBM ×12 单任务）
- 终点顺序：`tox21_research.data.TASKS`（12 个，与 CSV/报告一致）
- 预测逻辑：`tox21_research.models.predict_per_task`（经 `inference.load_frozen_predictor` 加载）

科研 CLI `scripts/predict.py` 重接为同一 `inference` 模块的薄封装；重接前后对固定样本集输出 **SHA-256 逐字节一致**（`586ce608…`）。

## 2. API schema

`GET /health` → `{"status":"ok","model_loaded":true,"family":"lgbm_ecfp4","feature_set":"ecfp4","n_endpoints":12}`

`POST /predict`（`application/json`）：

```json
请求:  {"smiles": ["CCOc1ccc2nc(S(N)(=O)=O)sc2c1", "not_a_smiles", ""]}
响应:  {
  "endpoints": ["NR-AR", "NR-AR-LBD", "NR-AhR", "NR-Aromatase", "NR-ER", "NR-ER-LBD",
                "NR-PPAR-gamma", "SR-ARE", "SR-ATAD5", "SR-HSE", "SR-MMP", "SR-p53"],
  "model": {"family": "lgbm_ecfp4", "feature_set": "ecfp4", "seeds": [42]},
  "predictions": [
    {"index": 0, "smiles": "CCOc1...", "valid": true,
     "probabilities": {"NR-AR": 1.2e-05, "...": "12 个终点活性概率, [0,1]"}},
    {"index": 1, "smiles": "not_a_smiles", "valid": false, "probabilities": null}
  ]
}
```

行为约定：批量语义，无效 SMILES（含空串、超长 >10,000 字符）按项标记 `valid=false`，不使整批失败；空列表 → `predictions: []`；批量 >512 → HTTP 413；非 JSON/非列表 → 422；重复 SMILES 返回重复且相同的概率。与已记录的评价契约一致：按 Huang et al.（P1）挑战赛评分为**各终点活性概率**（AUC-ROC 消费的概率口径），终点名与顺序为项目 TASKS。

## 3. 运行与容器

本地（仓库根目录）：

```bash
PYTHONPATH=src .venv/Scripts/uvicorn tox21_research.api:app --host 0.0.0.0 --port 8000
```

Docker（干净环境 → build → run → health → predict）：

```bash
docker build -t tox21-api:v1 .
docker run -d -p 8000:8000 --name tox21-api tox21-api:v1
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" \
     -d '{"smiles":["CCO"]}'
```

镜像离线推理（构建/运行期不下载训练数据、不训练、不访问外部模型服务）；基础镜像 `python:3.11-slim`，依赖=科研环境全量 `environment/requirements.txt`（含 torch CPU 源首行）。本网络环境 docker.io 不可达，实测经镜像源拉取基础镜像后按上述命令构建：`docker pull docker.m.daocloud.io/library/python:3.11-slim && docker tag docker.m.daocloud.io/library/python:3.11-slim python:3.11-slim`。

## 4. 测试与一致性结果（2026-08-14 实测）

- **单元/回归测试**：`pytest tests/ -q` → **62 passed**（45 科研 + 17 API；2 个 warning 来自 fastapi testclient 自身的 httpx 弃用提示，非本项目代码）。
- **API ↔ 共享推理模块**：逐分子**精确相等**（abs=0.0）。
- **API ↔ 科研 CLI**：rel 1e-12 内一致（test_api.py::test_api_matches_research_cli）。
- **CLI 重接前后**：固定样本输出 SHA-256 相同。
- **重启确定性**：进程内二次建 app 输出相同；**容器重启前后** /predict 响应 SHA-256 相同（`f1c6f60c…`）。
- **容器 vs 冻结 CLI**（Linux 容器 vs Windows 宿主）：60 项概率比较最大绝对差 **1.11e-16**（float64 末位；跨平台浮点求和顺序差异，在任务允许的"合理浮点误差"内）。
- **容器边界**：空列表 200、畸形体 422、批量 513 → 413、无效/超长 SMILES 按项标记，服务不崩溃。
- **科学产物零改动**：`git diff b50229f -- results/final data/processed` 为空。

## 5. 子代理工程验收结论

> 工程验收（只读复核，2026-08-14）：API/CLI/保存预测三路一致（0–1.11e-16），TASKS 列序与语义锚点核验通过；科学产物对 b50229f 零改动，CLI 重接 SHA-256 重放一致；62 项测试及 12 项对抗输入通过；Docker 干净启动、容器↔本地 1e-12 内一致、重启响应哈希相同。结论：**ACCEPT WITH NOTES**（唯一实质备注为根目录遗留的 CLI 基线 CSV 待归档/删除，已于冻结提交前删除，其 SHA-256 已记录于 §4 且可由 CLI 随时复现）。

## 6. 已知工程限制

1. 镜像 2.32GB：为保证环境与科研完全一致安装了全量 requirements（含 torch，LGBM 推理路径实际不需要）；未做裁剪。
2. 跨平台 1-ULP（1.11e-16）预测差异：同一模型在 Windows 宿主与 Linux 容器的浮点求和顺序不同；任何部署对比都应以 1e-12 级容差判等。
3. 单 worker uvicorn、无鉴权/限流/可观测性——这些属于下一阶段（独立安全审计）之后的工程决策，本阶段刻意不做。
4. 批量上限 512、单 SMILES 长度上限 10,000 字符为工程防护，非科学约束。
5. 本网络环境需镜像源拉取 docker.io 基础镜像（见 §3）。
