# Tox21 多终点毒性预测：可复现研究与推理服务（最终版）

本项目是面向**第三方研究者、审稿人与工程使用者**的完整科研软件工程产物：基于公开 Tox21 数据完成 12 终点毒性预测的可复现研究（数据审计 → 选型 → 冻结评测 → 独立审计 → 修订冻结），并将其工程化为经过安全审计与修复的 FastAPI 推理服务。**全部科学结论均可从 git 工件只读重算**——对照表见 `reports/final/claim_evidence_matrix.csv`，重算方法见 `reports/final/reproducibility.md`。

## 1. 项目目标

不是刷榜，而是回答：在严格协议下，(a) 经典指纹+浅层模型在 Tox21 上的真实泛化能力是多少；(b) scaffold 与 random 分割的差异有多大；(c) 公共数据两个版本（MoleculeNet CSV 与 2014 挑战赛 SDF）的标签一致性如何。目标是**来源可溯、协议合理、结果可复现、结论克制**。

## 2. 数据来源

- **MoleculeNet/DeepChem Tox21 CSV**（7,831 分子 × 12 终点，建模 7,823）：`https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/tox21.csv.gz`，SHA-256 固定于 `data/raw/PROVENANCE.md` 并内嵌于 `scripts/download_data.py`（下载后校验，不匹配即失败）。
- **2014 Tox21 挑战赛 SDF**（data_all / challenge_test / challenge_score）：NIH tripod 下载，同上校验和固定。
- 数据审计：跨版本按化合物编号 100% 对应；标签高度一致但存在少量批次聚约定依赖的冲突（228/11/102 对，占 both-labeled 的 0.014%–0.29%，三种聚约定口径），详见 `reports/data_audit.md` §1 与 `results/interim/audit/cross_version_label_agreement.csv`。

## 3. 科研流程（九环节闭环）

```
数据固定(SHA-256) → 数据审计 → 预登记协议 → valid 选型 → 一次性冻结 test 评测
→ 独立科学审计(P0×1/P1×2) → 科学修订冻结 v2 → 工程冻结(API/CLI/Docker)
→ 安全审计 → 安全修复+回归验证 → 最终独立评审
```

- 分割：Murcko scaffold 80/10/10（按 DeepChem ScaffoldSplitter 的公开行为规格实现并以测试锁定确定性与自洽；与 deepchem 库本体的直接对照未在仓库内执行），6,258/782/783；8 条不可解析 SMILES 显式丢弃并记录 mol_id。
- 选型只在 valid 上进行（LogReg / LightGBM / 多任务 MLP）；test 只在冻结配置下评测一次（git 历史与文件时间戳可证）。
- 泄漏检查：test↔train Tanimoto 中位 0.405、≥0.95 共 7 分子（骨架外推困难但分割干净），见 `results/interim/audit/test_train_tanimoto.csv`。

**分支地图**（各阶段的历史记录分支，`git log/show` 只读可查）：

| 分支 | 提交 | 内容 |
|---|---|---|
| `main` | `84ccf59` | Stage 3 冻结评测（历史基线） |
| `revision-v2` | `43b4513` | 科学修订冻结 v2 + Engineering/API Freeze v1 |
| `security-audit` | `f21fcde` | 安全审计记录（findings.csv 等） |
| `security-hardening` | `c05145a` | 安全修复（7 commits）+ 修复报告 |
| `final-package` | 本分支 | 最终发布包（README、证据包、Docker 验证、审稿模拟） |

## 4. 模型结果（冻结，v1=v2）

| 指标 | 数值 | 出处 |
|---|---|---|
| valid 选型宏 ROC-AUC | 0.7376 | `results/interim/model_comparison.csv` |
| **scaffold test 宏 ROC-AUC** | **0.7003** | `results/final/test_metrics_ensemble.csv` |
| scaffold test PR-AUC / BAcc | 0.3211 / 0.6024 | 同上 |
| random 分割对照（3 seeds） | 0.807 ± 0.010 | `results/final/random_split_sensitivity.csv` |

模型：LightGBM（leaves 63, trees 800, lr 0.05）× 12 单任务 + ECFP4（Morgan r=2, 2048bit）；冻结配置 `results/final/frozen_config.json`，模型 `results/final/model/model_seed42.joblib`（SHA-256 由 `src/tox21_research/model_integrity.json` 固定并在加载时校验）。

**主结论（观察性）**：在本研究协议对比中观察到分割协议差异（scaffold→random，test 口径 0.107）大于模型族间差异（valid 选型口径极差 0.036）。两者口径不同，且 scaffold 为单一实现（无分割方差）、random 为 3 种子；不外推因果与一般规律；引用本仓库数字必须同时报告分割协议。

## 5. 工程部署

本地（仓库根目录，Windows 示例；Linux/Mac 为 `.venv/bin/`）：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r environment/requirements.txt   # 首行含 torch CPU 源
# 推理 CLI（输入文件每行一个 SMILES）：
PYTHONPATH=src .venv/Scripts/python scripts/predict.py in.smiles out.csv
# API 服务：
PYTHONPATH=src .venv/Scripts/uvicorn tox21_research.api:app --host 0.0.0.0 --port 8000
# 测试（84 项，无需手动 PYTHONPATH）：
.venv/Scripts/python -m pytest tests/ -q
```

API 契约：`GET /health` → 冻结模型元信息；`POST /predict` `{"smiles": [...]}` → 逐项 `{"index","smiles","valid","probabilities"}`。**安全修复引入的契约差异**（详见 `reports/security_remediation.md`）：请求体上限 2MB（超限 413，不读 body）；单项 SMILES 上限 512 字符 + 64 个环闭合数字（超限按项 `valid=false`，不进入解析）；`/docs` `/redoc` `/openapi.json` 已关闭（404）。

Docker：

```bash
docker build -t tox21-api:v1 .
docker run -d -p 8000:8000 --name tox21-api tox21-api:v1
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d '{"smiles":["CCO"]}'
```

镜像离线推理（不下载训练数据、不训练）；以非 root 用户（uid 10001 `tox21`）运行；仅包含 `src/` 与 `results/final/`（`.dockerignore` 排除数据/报告/git）。以上已于 2026-08-21 实测通过（构建、health、非 root、容器↔本地 CLI 预测 1.11e-16，见 `reports/final/final_status.md` §3）。跨平台已知 1-ULP（1.11e-16）浮点差异，对比以 1e-12 容差判等（`reports/engineering_freeze.md` §4）。

## 6. 安全审计与修复状态

审计（`security-audit` 分支）确认 5 项 confirmed + 1 项 potential + 1 项 hardening；修复（`security-hardening` 分支）逐项对应 commit、回归测试与前后行为数字，并经两轮由独立于主实现的代理执行的回归验证（REGRESSION PASS；代理复核，非外部第三方）：

| Finding | 问题（一句话） | 修复 commit | 状态 |
|---|---|---|---|
| F1 | 无认证病理 SMILES CPU 耗尽 + healthcheck 饿死（26.6s/请求 → 34ms） | `e8042be` | CLOSED |
| F2 | 请求体无上限、解析期内存放大 + 回显放大（→ 2MB 预检 413） | `8460328` | CLOSED |
| F3 | 孤立 UTF-16 代理对使整批 500（→ 200 逐项失效） | `64e1d80` | CLOSED |
| F4 | RDKit 回显输入可伪造日志行（→ 服务禁用 rdApp 日志） | `b805561` | CLOSED |
| F5 | /docs 等端点未授权暴露（→ 404） | `95cd2ca` | CLOSED |
| P1 | joblib 反序列化信任边界（→ SHA-256 固定校验 + 路径包含，篡改即拒启） | `3fb7700` | CLOSED |
| H1 | 容器以 root 运行（→ 非 root uid 10001） | `452762e` | CLOSED |

修复未改变任何被接受输入的预测：CLI 对 105 分子固定样本输出与修复前**逐字节一致**（sha256 `613bea2d…`）；API↔CLI 105×12 概率最大差 1.11e-16；`data/processed`、`results/final` 相对基线零改动。

## 7. 已知限制

摘要（完整清单见 `reports/final/limitations.md`）：

- **科学**：仅指纹+浅层模型（无 GNN/预训练表示对照，项目自列为首要后续）；单一数据版本；scaffold 单一确定性实现、无分割方差量化；跨版本标签冲突未裁定哪侧正确；挑战赛官方评测不可复现（分数集标签未公开）。
- **工程**：基础镜像浮动 tag、依赖未按 hash 固定（供应链，需网络时处理）；模型加载存在校验→加载 TOCTOU 残余窗口（利用需本地文件写权限）；`scripts/` 无直接测试；真实数据回归测试在未下载数据时静默跳过；研究 CLI 对无效 SMILES 整体抛错（与 API 逐项失效不对称）。
- **部署**：单 worker、无认证/限流——为 T1（隔离内网）刻意决策；对外暴露前需代理层认证/限流（T2 conditional）。

## 8. 验证入口（第三方如何信任本仓库）

1. `python -m pytest tests/ -q` → 84 passed。
2. 按 `reports/final/reproducibility.md` 重算头条指标（无需重训：从 `results/final/*.csv` + `data/processed/*.npz` 直接重算 0.7003/0.3211）。
3. 按 `reports/final/claim_evidence_matrix.csv` 逐条对照 Claim/Evidence/Status。
4. 安全回归：`pytest tests/test_security.py -q`（22 项）。

## 9. 目录结构与文档地图

```text
data/raw/            原始数据 + PROVENANCE.md（SHA-256 固定）
data/processed/      建模缓存（npz + manifest）
src/tox21_research/  核心库（10 个 Python 模块，另含模型完整性清单 JSON）
scripts/             数据下载/审计/训练/评测/推理入口脚本
tests/               84 项测试（含 22 项安全回归、真实数据回归标记 slow）
configs/             实验配置与冻结配置
results/interim/     阶段性输出（审计表、模型对比）
results/final/       冻结结果（指标/预测/模型/配置）
reports/             全部阶段报告：
  research_plan.md        预登记协议（阶段 1）
  data_audit.md           数据审计（阶段 1，v2 修订）
  final_report.md         最终科研报告（阶段 3）
  audit/                  独立科学审计记录（阶段 4）
  revision_log.md         科学修订记录（阶段 5）
  engineering_freeze.md   工程冻结（阶段 6/8）
  security_remediation.md 安全修复报告（阶段 9）
  final/                  最终证据包（阶段 11，本分支新增）
environment/         requirements.txt（56 包精确锁定）+ python 版本
```

注：`reports/` 内各阶段文档为**时间戳记录**（写作时点的测试数等以当时为准，如 final_report 的 45 项测试）；当前状态一律以本 README 与 `reports/final/` 为准。
