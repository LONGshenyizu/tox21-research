# 复现核验记录（Reproduction Check）

日期：2026-08-14 ｜ 核验人：主代理（第二层复核）｜ 冻结对象：`84ccf59`
约束：全程只读；诊断经临时脚本在内存中完成；未运行任何会写 `data/`、`results/` 的仓库脚本；冻结文件零改动。

## 1. 状态核验

- `git log`：HEAD = `84ccf59`（Stage 3）← `3e586e6` ← `53cc814`；工作区除新增 `reports/audit/` 外干净。
- `pytest tests/ -q`：**35 passed**。

## 2. 确定性链路（same input → same split → same features → same predictions/metrics）

| 环节 | 方法 | 结果 |
|---|---|---|
| 数据→分割 | 从 `tox21_moleculenet.csv.gz` 重新解析、过滤无效 SMILES、重跑 `scaffold_split_indices`，与 `data/processed/tox21_modeling.npz` 的 train/valid/test **逐分子 ID** 比较 | **一致**（train 6,258 / valid 782 / test 783；三个集合 ID 全等） |
| 数据→特征 | 从原始 CSV 重算 ECFP4（r=2, 2048bit）与 npz `X_ecfp4` 比较 | **bit 级一致**（`np.array_equal` = True） |
| 保存预测→指标 | 用 `results/final/test_predictions_ensemble.csv` + npz 标签重算全部 12×3 指标，与 `test_metrics_ensemble.csv` 比较 | 最大偏差 **8.3e-17**；宏 ROC 0.7003 / PR 0.3211 / BAcc 0.6024 重现 |
| 重新训练→预测 | 按冻结配置 `configs/final_model.json` 重训 LightGBM（seed 42，21s），预测 test，与保存的 ensemble 预测比较 | 最大绝对差 **1.1e-16**（浮点求和顺序级；"逐行 bit 相同"为 0/783 属预期——差异在双精度末位，远低于任何报告阈值） |

结论：**冻结管线宣称的确定性在"输入→分割→特征→模型→指标"全链路成立**（机器精度内）。审查人（子代理）独立报告了同样的结论（其重训 diff 1.1e-16、指标重算 diff 8.3e-17，与我的数字一致）。

## 3. 跨版本比对复核（对 P0 定量细节的修正性重算）

为裁决 C-01 的具体数字，用仓库 loader 以**明确约定**重做 CSV ↔ 挑战赛 SDF 比对（化合物层面对 `dsstox_cid` 聚合）：

| 口径/约定 | 匹配 | 标签冲突对 | ≥1 冲突分子 |
|---|---|---|---|
| 结构（InChIKey，SDF 侧 groupby-first） | 6,562 / 7,831（83.8%） | 212 | 181 |
| 化合物编号（TOX#### ↔ DSSTox_CID），SDF=任一样本活性 | **7,831 / 7,831（100%）** | **11** | 10 |
| 同上，SDF=首样本 | 7,831 / 7,831 | 228 | 197 |
| 同上，SDF=多数票 | 7,831 / 7,831 | 499 | 401 |

- 匹配化合物上：both-labeled 标签对 77,889；CSV 独有标签仅 **57**；SDF 独有 **0**。
- 8 个无效 SMILES 行按化合物编号**全部可匹配**（8/8）。
- 分割差异（C-02）：重算两个分割并逐 ID 比较，**13 个分子**子集归属不同（7 个 valid→test、6 个 train→valid，名单与子代理完全一致）；建模分割与 npz 逐分子一致。
- 8043 闭合（C-06）：解析样本唯一 CID 8,041 + 未解析记录 CID {28914, 29072} → 并集 **8,043**，与 Huang et al. 数字恰好闭合。

## 4. 结论

- 冻结结果（0.7003/0.3211/0.6024 及全部每终点指标）**可由当前 commit 的数据与代码机器精度复现**。
- 复现核验**不能**为"跨版本零冲突"主张背书：该主张出自一次空集上的无效验证（见 audit_summary §2 P0），正确重算显示冲突非零但数量依赖批次聚合约定（11–499 对 / 0.014%–0.64% 的 both-labeled 对），且 CSV 标签几乎完全被挑战赛化合物层标签覆盖（非子代理所称"CSV 多 1.7–2k 标签"）。
- 环境复现存在一处缺口：`environment/requirements.txt` 中 `torch==2.13.0+cpu` 需 `--extra-index-url https://download.pytorch.org/whl/cpu`，README 复现指南未注明（裸 `pip install -r` 会失败）。
