# Tox21 多终点毒性预测：可复现研究

基于公开 Tox21 数据（12 个核受体/应激反应测定终点）的多终点毒性预测研究，目标是**来源可溯、协议合理、结果可复现**的完整流程与研究代码库，而非单一模型刷榜。

## 目录结构

```text
data/raw/            原始数据（PROVENANCE.md 记录 URL/校验和/日期；由 scripts/download_data.py 重建）
src/tox21_research/  核心库：数据加载、scaffold 分割、特征、模型、评价
configs/             实验配置（yaml）
scripts/             数据下载、审计、训练、评测入口脚本
tests/               pytest 单元测试
results/interim/     阶段性实验输出（审计表、模型对比等）
results/final/       冻结后的最终结果
reports/             研究计划、数据审计、最终研究报告
references/          外部资料清单（标题/URL/访问日期/支持的判断）
environment/         requirements.txt（pip freeze）与 Python 版本
```

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r environment/requirements.txt   # 首行含 torch CPU 源 --extra-index-url；Linux/Mac 为 .venv/bin/python
.venv/Scripts/python scripts/download_data.py     # 下载并校验原始数据（SHA-256 固定）
.venv/Scripts/python -m pytest tests/ -q          # 单元测试
.venv/Scripts/python scripts/audit_data.py        # 数据审计 → results/interim/audit/
.venv/Scripts/python scripts/prepare_data.py      # 特征与分割缓存
.venv/Scripts/python scripts/run_experiments.py   # 阶段 2 模型选型（valid）
.venv/Scripts/python scripts/error_analysis.py    # 验证集误差分析
.venv/Scripts/python scripts/final_test.py        # 阶段 3 冻结 test 评测（一次性）
.venv/Scripts/python scripts/random_split_check.py# random 分割敏感性
.venv/Scripts/python scripts/predict.py in.smiles out.csv   # 对 SMILES 列表推理
```

## 当前状态（研究已完成，v2 修订版冻结）

- [x] 阶段 1：来源确认、数据审计、研究计划（`reports/data_audit.md`、`reports/research_plan.md`）
- [x] 阶段 2：基线与选型（LogReg/LGBM/多任务 MLP；valid 宏 ROC-AUC 0.7376）
- [x] 阶段 3：结果冻结与最终报告（`84ccf59`，`reports/final_report.md`）
- [x] 阶段 4：独立科研审查与复现核验（`reports/audit/`，发现 1 项 P0、2 项 P1）
- [x] 阶段 5：科学修订与 **Scientific Result Freeze v2**（本分支；修订记录见 `reports/revision_log.md`，模型结果与 v1 完全一致）

**冻结结果（v1=v2）**：LightGBM + ECFP4，scaffold test 宏 ROC-AUC **0.7003**（PR-AUC 0.3211）；random 分割对照 0.807±0.010——在本研究协议对比中，分割协议造成的差异远大于模型间差异（观察性结论）。

## 数据与协议（一句话版）

MoleculeNet/DeepChem 托管的 Tox21 CSV（7,831×12，SHA-256 固定；与 2014 挑战赛原始数据按化合物编号 100% 对应、标签高度一致但存在少量批次聚约定依赖的冲突，见 `reports/data_audit.md` §1）；建模 7,823 分子，scaffold 80/10/10 分割（6,258/782/783，审计与建模共用同一分割实现并有 npz 一致性断言）；主指标 ROC-AUC（每终点+宏平均），辅以 PR-AUC 与 balanced accuracy。详见 `reports/research_plan.md`。
