# 独立科研复现审查报告（Independent Scientific Audit）

- 审查对象：`<repo-root>`，冻结 commit `84ccf59`（Stage 3）；前置 `3e586e6`（Stage 2）、`53cc814`（Stage 1）。审查期间 HEAD 始终为 `84ccf59`，未 checkout、未修改任何被跟踪文件。
- 审查人：Independent Scientific Auditor（独立复现审查人，非协作者）。
- 审查日期：2026-08-14。
- 运行环境：仓库 venv `<repo-root>/.venv/Scripts/python.exe`（Python 3.11.9，rdkit 2026.03.5，scikit-learn 1.9.0，LightGBM 4.7.0，pandas 3.0.5，numpy 2.4.6，torch 2.13.0+cpu）。
- 方法：只读审查 + 内存重算。所有诊断脚本位于系统临时目录（`/tmp/audit/*.py`），未向 `data/`、`results/`、`src/`、`scripts/`、`configs/` 写入任何内容；未运行任何会写仓库目录的脚本（`audit_data.py`/`prepare_data.py`/`run_experiments.py`/`error_analysis.py`/`final_test.py`/`random_split_check.py`/`download_data.py`/`predict.py` 均未运行）。重算包括：从原始 CSV 重现两种 scaffold 分割并逐分子 ID 比较；用仓库 loader 重做跨版本标签比对（含正确 merge）；由保存的预测与 npz 标签重算全部冻结指标；重训 seed42 LightGBM 与三个 random split 复现。`pytest tests/ -q`：35 passed。

---

## 0. 执行摘要

**主结果数字本身全部可复现且正确**：冻结 test 宏 ROC-AUC 0.7003 / PR-AUC 0.3211 / BAcc 0.6024 与保存的逐终点预测+标签重算一致到机器精度（<1e-15）；重训 seed42 模型与保存预测 bit 级一致；random 分割三个种子精确重现；端到端确定性声称成立。

**但存在 1 项 P0**：阶段 1 的"跨版本标签零冲突"验证在代码层面从未发生（join 索引空间不同，匹配对数为 0），且正确的重算**推翻**了"逐分子一致、标签忠实"这一被三份报告、README 与 PROVENANCE 反复引用的基础性主张：按 DSSTox_CID 全部 7,831 行可匹配回挑战赛训练库，但重叠标签中存在 **624 对冲突（0.65%，408 个分子）**；按完整 InChIKey 仅 6,562 行（83.9%）可匹配，1,261 行（16.1%）结构不匹配（标准化差异）。数据选择结论（用社区标准 CSV）仍可由其余理由支撑，但"版本一致性已验证"这一关键审计结论必须撤销并改写。

另有 1 项 P1（审计分割与建模分割是两个不同分割、13 个分子分属不同子集、报告未披露）与若干 P2/P3。**无任何发现动摇 0.7003/0.3211/0.6024 或 scaffold-vs-random ≈0.10 差异的数字本身。**

---

## 1. Check 1 — 评价协议漂移

**结论：无实质性未声明协议漂移（PASS），但审计→建模的分割口径存在一次未记录的偏移（见 Check 2）。**

- 阶段 1 研究问题（`reports/research_plan.md` §1）："建立来源可溯、协议合理、结果可复现的多终点毒性预测流程"，明确"目标不是刷高单一指标"；§3 预登记主协议 = MoleculeNet 式内部 scaffold 80/10/10 + random 敏感性，指标以 ROC-AUC 为主。挑战赛式外部评测在阶段 1 即被排除（`data_audit.md` §1"评测集与训练库关系"、§5 异常 #5：最终评测集标签从未公开）。
- 我独立验证了排除外部评测的事实基础：排行榜测试集 296 个（带 3,130 个标签细胞）与训练库/CSV **零重叠**（重算 0/0）；最终评测集解析 645 个、**0 个标签**；647 文件与训练库/CSV 重叠 7/6。
- `6258/782/783` 的 test 就是预登记协议意义上的"最终测试集"（内部 scaffold test），不是 Tox21 Challenge official evaluation。报告**没有**把二者混为一谈：`final_report.md` §10.4 明确"与挑战赛名次不可直接比较"；`references/sources.md` §3 明确 Huang 获胜成绩与 MoleculeNet 基线"来自不同数据划分与不同测试集，不可直接比较"。
- 冻结纪律的时序证据：`results/final/` 全部文件首次出现于 Stage 3 commit；文件 mtime 显示 test 评测为 18:10:17–18:10:18 的单次突发，random 敏感性在 18:11:00–18:12:03（之后），Stage 3 commit 时间 18:16:25。与"test 冻结后只跑一次、random 在后且不回馈"的声明一致。
- 轻微保留：`final_report.md` §8 "与 MoleculeNet 论文 random 口径下强基线 ~0.82 的量级一致"是一次跨协议（不同数据版本与分割实现）的定性并置，与自身"不可直接比较"的纪律存在张力，但措辞为定性（"量级"），判 P3。

## 2. Check 2 — scaffold 分割前后一致性

**结论：两组数字来自两个不同的分割；建模实际使用 `6258/782/783`；审计分析在另一个分割（`6264/783/776`）上完成；13 个分子被分到不同子集；报告从未披露（FAIL，P1）。幸运的是泄漏/相似度结论在建模分割上重算后不变。**

机制（代码级）：`src/tox21_research/splits.py::scaffold_split_indices` 以 `len(smiles_list)` 为基数计算 cutoff（`train_cutoff = frac_train * len(smiles_list)`）。

- `scripts/audit_data.py::split_audit`（L132）在**全部 7,831 行**（含 8 个无效 SMILES）上调用 → cutoff 基于 7831 → **6264/783/776**（skipped=8）。这是 `data_audit.md` §4 与 `audit_summary.json` 的数字。
- `scripts/prepare_data.py`（L25–35）先剔除 8 个无效行再分割 → cutoff 基于 7823 → **6258/782/783**，写入 npz 与 `manifest.json`。这是实验实际使用的分割。

我用 venv python 从原始 CSV 独立重现了两个分割（临时脚本 `/tmp/audit/check2_split.py`）：

- 重现的建模分割与 `tox21_modeling.npz` 的 `train_idx/valid_idx/test_idx` 映射到 mol_id 后**逐分子完全一致**；npz 的 `Y` 与 CSV 过滤后标签一致；`X_ecfp4`/`X_maccs` 与重算 bit 级一致。
- 两分割逐分子比较：**13 个分子分到不同子集**——7 个 audit-valid → 建模-test（TOX26168、TOX26164、TOX26166、TOX27568、TOX8008、TOX8001、TOX27781），6 个 audit-train → 建模-valid（TOX26137、TOX26640、TOX26138、TOX26648、TOX4204、TOX27341）。
- **对泄漏结论的影响评估**：我在实际建模分割上重算了泄漏与相似度统计——跨分割同 InChIKey 仍为 **1 例**（即 TOX4994/TOX6178 那对 NR-ER 冲突重复），test→train 最近邻 Tanimoto 中位数 **0.4054**、均值 0.4354、≥0.95 共 7 个、≥0.85 共 12 个——与审计分割上的数字（0.4048/0.4356/7/12）在报告引用精度（0.405）下完全一致；SR-ARE 活性率漂移（train 14.7% → valid 22.4% / test 24.5%）与"valid NR-PPAR-gamma 32、test NR-AR-LBD 19 个活性"在两个分割上数值相同。**因此 §4 的实质性结论（分割干净、骨架外推困难）可迁移，但证据链错位：`final_report.md` §2 引用的泄漏数字实际来源分割与被描述对象不同，且 `data_audit.md` §4 的规模数字（6264/783/776）不是实验所用分割。**
- "逐行复刻 DeepChem ScaffoldSplitter"与"与 DeepChem 对该文件的默认一致"：DeepChem 源码未随仓库快照，在本审查不联网约束下不可独立验证；仓库内仅能验证自洽与确定性（均成立）。值得注意的是，DeepChem 的行为对应"过滤前"还是"过滤后"分割口径，报告未论证。

## 3. Check 3 — 8041 vs 8043

**结论：2 个差异在报告写作时未被解释（FAIL，P2）；但用仓库自身数据可以解释，我已重算闭合。**

- 仓库主张：`data_audit.md` §1 "A 按结构去重为 8,041 个唯一 InChIKey（≈ Huang 的 8043 'samples'，为挑战赛训练集口径）"；`PROVENANCE.md` §3 "与 Huang et al. 2016 报告的挑战赛训练集 '8043 samples' 对应"。两处均未分析 identity 定义（InChIKey vs DSSTox_CID vs canonical SMILES）与 RDKit 解析失败（11,764 原始 → 11,761 解析）的影响，属于"接近但未解析差异"，不构成完成的一致性验证。
- 我的重算：解析成功样本上，唯一完整 InChIKey = 唯一 DSSTox_CID = 唯一 canonical SMILES = **8,041**（三种身份定义同数，排除了 identity 选择导致 ±2 的可能）。从 SDF 原文提取 **3 条 RDKit 不可解析记录**（CID 28914×2 条样本、29072），计入后唯一 DSSTox_CID = **8,043**。即 Huang 的 8,043 对应**全文件**（含不可解析记录）的唯一化合物数，8,041 是"解析成功子集"口径。该解释完全来自仓库自带数据，但报告未做。建议改写为明确口径的表述。

## 4. Check 4 — 标签一致性是否被过度解释

**结论：比"过度解释"更严重——验证本身是空集，且正确重算直接反驳报告主张（FAIL，P0）。**

### 4.1 保存结果与代码的证据

`results/interim/audit/cross_version_label_agreement.csv` 中 12 个终点的 **`n_both_labeled` 全部为 0**（`n_agree=0`、`n_conflict=0`、`n_sdf_only_labeled=0`）。原因在 `scripts/audit_data.py::cross_version_agreement`（L109–127）：

```python
joined = mn.join(ch, rsuffix="_ch", how="left")   # 按 index join
matched = joined["inchikey"].notna()               # 实为"CSV 自身 InChIKey 非空"
```

`mn.index` 是 `TOX####`，`ch.index` 是 `NCGC########-##`，**索引交集为 0**（我实测）。因此 left join 后所有 `*_ch` 列全 NaN；`matched`（7,823）只是"CSV 行自身可解析出 InChIKey"，被误读为"匹配到 SDF"。`n_conflict=0` 是在**零个可比标签对**上的空集结论。该缺陷自 Stage 1 即存在于已提交文件中（`n_both_labeled=0` 在 CSV 中可见），三份报告在其上写出了"7,823 行匹配成功……12 个终点全部标签零冲突""逐分子一致""标签忠实"。

### 4.2 正确的重算（仓库 loader，临时脚本）

按**完整 InChIKey** merge（报告声称的口径）：

- 仅 **6,562/7,823 行（83.9%）** 能匹配到训练库；**1,261 行（16.1%）不匹配**，其中 1,120 行在完整 InChIKey、首段 InChIKey、canonical SMILES 三种定义下均不匹配（携带 10,545 个标签）。
- 匹配上的 9,635 个 (CSV 行 × SDF 批次样本) 对中，双方均有标签的 82,565 对里 **570 对冲突（0.69%）**，涉及 369 个唯一 CSV 分子；NR-ER 最差（163 对，模式为 CSV=1 / SDF=0），12 个终点全部非零冲突。

按 **DSSTox_CID（挑战赛自身的化合物编号，CSV 的 TOX#### 去前缀即为其数值）** merge：

- **全部 7,831/7,831 行可匹配**（含 8 个无效 SMILES 行）——"B 是 A 的子集"在 CID 口径下成立，但因 CSV 与 SDF 的结构标准化差异（质子化/互变异构/盐形式），数值匹配的样本对中仅 83% 同时具有相同完整 InChIKey，这解释了 InChIKey 口径的 16% 缺口。
- 11,508 个匹配对中，双方均有标签的 96,166 对里 **624 对冲突（0.65%）**，涉及 **408 个唯一分子**；且在匹配化合物上 SDF 有标签而 CSV 缺失的情形为 **0**、CSV 多出约 1.7–2.0k 个标签/终点——即 CSV 标签并非挑战赛 SDF 标签的忠实拷贝，而是更大/更晚的 curation（更宽松的 hit-call + 少量改判）。

### 4.3 对各文档主张的裁定

- "7,823 行匹配成功、12 终点零标签冲突"（`data_audit.md` §1）：**FAIL**（匹配从未发生；正确比对有数百对冲突）。
- "8 行未匹配 = 8 个无效 SMILES，并非版本分歧"（`data_audit.md` §1）：**FAIL**（正确分析下 InChIKey 未匹配为 1,261 行且以标准化差异为主；8 个无效 SMILES 行按 CID 反而全部可匹配）。
- "B 是 A 的去重整理子集，标签忠实"（`data_audit.md` §1）：子集关系在 CID 口径成立、InChIKey 口径不成立；"标签忠实"在任何口径下都不成立（0.6–0.7% 冲突 + CSV 标签集显著更大）。
- "审计已证明其与 2014 挑战赛原始训练库逐分子一致（零标签冲突）"（`research_plan.md` §2 理由(a)、`final_report.md` §2 理由(a)、README"已验证与 2014 挑战赛原始数据零标签冲突"）：**FAIL**。
- 匹配方法漏洞（原问题所列）：InChIKey join 确会掩盖一对多映射（SDF 批次重复）——我的重算按对处理并单独统计了多映射；"8 个未匹配行是否真是无效 SMILES"——在失效代码的语义下是（tautologically），在正确语义下不是。

**影响范围**：数据选择（校验和固定的 CSV）仍可由理由 (b) 社区标准口径、(c) 文件稳定支撑，且建模数字不受影响；但作为"本研究的关键审计结果"的版本一致性叙事必须改写为量化的部分一致（CID 全匹配 + 0.6–0.7% 标签冲突 + 16% 结构表示分歧）。

## 5. Check 5 — 0.7003 的定义与可比性

**结论：数字定义清晰、重算完全一致、冻结后单次运行成立（PASS）；跨协议比较措辞有一处轻微张力（P3）。**

- 样本与脚本：test = scaffold 分割 783 个分子（npz `test_idx`），逐终点只在有标签行上评估（每终点 481–715），`scripts/final_test.py` → `evaluate_matrix`（`src/tox21_research/metrics.py`）：NaN 正确 mask；单类终点返回 NaN（实际 12 终点在所有 split 均两类俱全，`n_tasks_scored=12`）；宏平均 = 12 终点**等权**算术平均（与文档"宏平均"一致）；BAcc 用阈值 0.5（文档已声明为辅指标）。
- 重算（`/tmp/audit/check5_recompute.py`）：用 `test_predictions_ensemble.csv` + npz `Y` 重算全部 12×3 指标与 `test_metrics_ensemble.csv` 的最大偏差 **8.3e-17**（容差 1e-4 远超满足）；宏 ROC 0.700314 / PR 0.321138 / BAcc 0.602436；valid 宏 0.737576（= 选型数字 0.7376）；valid→test 差 -0.03726（报告 "-0.037" ✓）；预测文件行序与 npz `test_idx` 一致；ensemble ≡ seed42（单种子，`test_predictions_per_seed.csv` 与 ensemble 全等）。
- 端到端复现（`/tmp/audit/check5b_retrain.py`）：按 `configs/final_model.json` 重训 seed42 LGBM（18.6 s），与保存 test 预测 max diff **1.1e-16**；`model_seed42.joblib` 加载后预测同样 bit 级一致；`frozen_config.json` 与 `configs/final_model.json` 内容相等。
- 单次运行：见 Check 1 时序证据（PASS）。
- 跨协议比较审查：未发现与挑战赛名次的任何不当比较；`final_report.md` §8 与 MoleculeNet random 基线"量级一致"为定性并置（P3，见 Check 1）。

## 6. Check 6 — random vs scaffold 结论强度

**结论：实验同质性成立、复现成立；"协议影响 > 模型间差异"在本研究语境下有内部证据支撑（PASS，附单 realization 保留）；报告措辞总体保持在观察性层面。**

- 同质性（代码级 + 重算验证）：两种协议共用同一 npz（同数据、同 ECFP4 特征、同 7823 分子池）、同 LGBM 超参（leaves=63/trees=800/lr=0.05）、同训练预算；`random_split_check.py` 传入的模型种子=分割种子（0/1/2），但我实测 LGBM 在 `force_row_wise=True`、无 subsampling 配置下**种子完全无关**（同数据 seed42 vs seed7 预测 max diff = 0.0），故不构成混淆。
- 复现：三个 random 种子重训重算 = 0.7959 / 0.8055 / 0.8205，与保存文件逐位一致；均值 0.8073（报告"0.807"）；与 scaffold 0.7003 差 0.1070（"约 0.10"）。
- 证据强度：split 效应 0.107 vs 模型间极差（选型表 0.7376 − 0.7016 = 0.036，scaffold-valid 口径）。README"协议选择的影响大于模型选择"在所测范围内成立，但两点保留：(a) scaffold 是单一确定性 realization（无分割方差量化），random 是 3 种子；(b) 两个量分别取自 valid（选型语境）与 test（协议语境），非严格同语境对比。报告正文（`final_report.md` §8/§10.2）将其表述为本研究内的观察性结论并要求引用时同报协议，措辞基本恰当；README 的短句因果味略强（P3）。
- "±0.010"：为总体标准差（ddof=0 = 0.0101；样本标准差 0.0124），口径未注明（P3）。
- 模型选择未针对 random 调整：`run_experiments.py` 只在 scaffold train/valid 上评估（`model_comparison.csv` 全部为 scaffold-valid），`random_split_check.py` 复用冻结 spec，无回溯（git 时序亦支持）。

## 7. Check 7 — 生物学解释的证据等级

**结论：结构性观察 SUPPORTED；"更可能反映测定阈值/标注边界而非特征错误"的比较性归因 UNSUPPORTED（P2）。**

- 事实核对（重算）：TOX28569（valid，AR 预测 0.9999，NR-AR 及其余 7 个有标签终点全为 0）与 TOX28690（valid，AR 预测 0.9990，NR-AR=0，但 NR-ER-LBD/SR-ATAD5/SR-MMP=1）确为甾体骨架（Murcko scaffold 为典型甾体四环），是 valid 集最自信的 NR-AR 假阳性——与 `final_report.md` §9 一致。另 TOX3322（AR-LBD 0.99999 FP，标注 NR-AR=1/AR-LBD=0）同样为甾体。
- 可区分性分析：仓库仅保留二值标签（qHTS 连续曲线未保留，`final_report.md` §10.5 自认）；无每样本测定质量/重复次数/AC50 信息。在此证据面上，model error（ECFP4 无法区分 AR 活性与非活性甾体，即指纹分辨率极限）、label noise、assay threshold、biological ambiguity 四种解释**不可分辨**。且"甾体与 AR 结合是公认事实"对胆酸型甾体（TOX28569 属此类，缺乏典型 AR 药效团）并不直接适用。
- 逐条分级（`final_report.md` §9）：
  - "最自信假阳性是甾体骨架分子（TOX28569/TOX28690，AR 0.999 但标注 inactive）"：SUPPORTED。
  - "甾体与雄激素受体的结合是公认化学事实"：PLAUSIBLE HYPOTHESIS（外部领域知识，仓库内无证据；对具体分子不必然成立）。
  - "这类错误更可能反映测定阈值/标注边界而非特征错误"：UNSUPPORTED（比较性概率主张，无比较性证据；特征错误即模型分辨率解释至少同等相容）。
  - "SR-ATAD5 PR-AUC 最低因活性样本稀少分散"：SUPPORTED（test 33 活性、PR 0.099，描述性）。
  - "终点难度与活性样本数无相关（valid r=-0.04）"：SUPPORTED（重算 r=-0.04）。
  - "NR-ER 冲突重复对分居 valid/test，两侧预测均为 0"：SUPPORTED-近似（实测 0.0251 / 0.00056，均远低于 0.5，"均为 0"为约略表述，P3）。

## 8. 分层发现（Check 1–7 之外）

### 数据层
- SHA-256：`tox21_moleculenet.csv.gz` 实测 `45d0979249…d360` 与 PROVENANCE 一致（PASS）。
- 8 个无效 SMILES：全部含 `[AlH3]` 伪原子记法（铝盐/铝配合物），携带 82 个标签——与 `data_audit.md` §3.1 一致（PASS）。
- 重复与冲突：2 组重复结构 4 行，`CEJLBZWIKQJOAT-…-M`（TOX4994/TOX6178）NR-ER 1 vs 0——重算一致（PASS）。该对正是跨分割"泄漏 1 例"，即同一化合物以两种书写分居 test/valid 且标签互斥——比"泄漏"更准确的性质是"重复+冲突跨分割"，报告在 §3/§9 已作交代。
- 缺失标签：每行至少 1 个标签（n_all_labels_missing=0，重算一致）；建模按任务 mask（PASS）。
- 任务活性率范围 2.9%–16.2%、每终点 5,810–7,265 有标签：重算一致（PASS）。
- `data_audit.md` §2 "每测定有标签样本 7,167–9,362" 与 `challenge_task_summary.csv` 实际 **7,166–9,360** 不符（FAIL，P3）。

### 特征层
- ECFP4 = Morgan r=2 / 2048 bit、MACCS = 167 bit：与文档一致，npz 特征全量重算 bit 级一致（PASS）。
- 无效分子：`features._parse` 抛错、`prepare_data` 先过滤（PASS）。
- MACCS 对照公平性：ECFP4 侧用了网格调参后的最优 C=0.1（0.7367），MACCS 侧固定 C=1.0（0.7087）（`configs/experiments.yaml` `feature_check.C: 1.0`）。`final_report.md` §4 "0.737 vs 0.709 验证了特征选择"夸大了差距：同 C=1 时 ECFP4 0.7125 vs MACCS 0.7087，差仅 0.0038。方向成立、幅度不可靠，且未给 MACCS 同等调参（UNSUPPORTED，P2）。

### 模型层
- 选型只看 valid：`run_experiments.py` 全部评估在 scaffold-valid 上；`final_model.json` 记录 criterion 与 runner-up（PASS）。
- MLP valid 早停（best-restore）+ valid 选型：早停使 MLP 的 valid 数字相对 LGBM 略乐观，但这只会低估而非高估 MLP 差距，不影响选型方向（P3 信息项）。
- 类别不平衡：三类模型均按文档加权（class_weight / scale_pos_weight / BCE pos_weight）（PASS）。
- "多任务共享表示"实现与描述相符（共享隐层 512-256、逐任务 mask 损失）（PASS）。
- 种子与确定性：LGBM 种子无关性实测成立；重训 bit 级复现；"集成=单确定性种子本身"如实声明（PASS）。

### 指标层
- 等权宏平均、NaN mask、单类 NaN、BAcc@0.5：实现正确且与文档一致（PASS，见 Check 5）。
- train 集宏 ROC 0.99994（重算）：800 棵树在 6258 样本上的深度记忆，报告未引用 train 数字，无误导（信息项）。

### 工程层
- 环境冻结不自足：`requirements.txt` 含 `torch==2.13.0+cpu`，本地版本号无法从默认 PyPI 解析；README/复现指南未提供 `--extra-index-url https://download.pytorch.org/whl/cpu` 或等价配置，裸 `pip install -r` 会失败（FAIL，P2）。venv 实测版本与其余条目全部吻合。
- 测试覆盖缺口：35 个用例全部通过，覆盖 `src/` 六个模块，但 `scripts/`（含 `cross_version_agreement` 所在的 `audit_data.py`）零覆盖——P0 缺陷恰从该缝隙逃逸（FAIL，P2）。
- 模型序列化与推理一致性：joblib 加载预测与被评测 ensemble bit 级一致；`predict.py` 逻辑（读 frozen_config → 加载各 seed 模型 → 平均 → 相同 featurizer）与被评测对象一致（读代码推演 + 等价内存重放验证）（PASS）。
- 路径：脚本一律仓库相对路径，无硬编码绝对路径（PASS）。
- 冒烟测试产物缺失：`final_report.md` §8 引用的 predict 冒烟结果无输入/输出文件留存；我的独立重放部分支持（阿司匹林全部 <0.01 ✓、睾酮 AR=1.0 ✓；结构相近的苯并噻唑砜 AhR=0.73，与所引"1.00/0.99"不可比）（UNCERTAIN，P3）。
- Git 卫生：`__pycache__`/`.pytest_cache` 均被忽略且未跟踪（PASS）；Stage 2/3 对 `data_audit.md`、`valid_task_metrics.csv` 的修改均为良性且在 commit message 中记录（NR-AR→NR-ER 笔误修正；索引格式化，数值不变——我逐值 diff 核对）。

### 文档层（逐数核对）
- `final_report.md` §5 选型表（10 行）、§6（0.0009 / 0.028）、§7（36 个终点数字）、§8（0.7003/0.3211/0.6024/-0.037/0.7959/0.8055/0.8205/0.807/约0.10）、§9（-0.136、27 活性、0.099、33 活性、r=-0.04）与 commit 内结果文件**全部一致**（PASS）。
- `README.md` 冻结数字（0.7376 / 0.7003 / 0.3211 / 0.807±0.010）一致（PASS）；"已验证与 2014 挑战赛原始数据零标签冲突"（FAIL，见 Check 4）。
- 环境版本行：`final_report.md` L109 "numpy 2.4.1" 错误（实际 2.4.6）；"rdkit 2026.03.5" 与 requirements 的 `2026.3.5` 为同一版本的规范化写法差异（前者与 venv 实测一致）；其余（Python 3.11.9 / sklearn 1.9.0 / LightGBM 4.7.0 / pandas 3.0.5 / torch 2.13.0+cpu）全部正确（FAIL，P2，仅 numpy 一处）。
- "35 个单元测试"：实测 35 passed（PASS；tests/ 为 6 个文件）。
- 外部引用主张（Huang 数字、MoleculeNet 正文 8014、TDC 7,831、DeepChem docstring 等）：受不联网约束未验证，仅核内部一致性（UNCERTAIN，整体 P3）。

---

## 9. 结论

1. **可复现性**：冻结主结果（0.7003/0.3211/0.6024）、选型表、random 敏感性、端到端确定性——全部独立复现成功，精度达机器精度。这是本仓库最强的部分。
2. **科学主张**：数据层的一项基础性主张（跨版本逐分子一致/零标签冲突）不成立——验证代码失效且正确重算显示数百对标签冲突与 16% 的结构表示分歧；分割审计与建模使用的分割存在未披露的口径偏移（13 个分子）。二者都需要在报告层面修正，但不改变任何已冻结的建模数字。
3. **解释层**：MACCS 对照幅度、甾体假阳性归因、8043 口径三处措辞超出证据，需降格或补证。
4. **修正建议（按优先级）**：(a) 重写跨版本一致性章节，以量化结果（CID 全匹配 / InChIKey 83.9% / 标签冲突 624 对或 570 对、NR-ER 最差）替代"零冲突"叙事，并修复或移除 `cross_version_agreement` 的 index join；(b) 在 `data_audit.md` §4 与 `final_report.md` §2 中显式区分审计分割与建模分割（或统一在 7,823 行上重跑审计）；(c) 修正 numpy 版本、challenge SDF 有标签样本范围两处文档数字；(d) requirements 补 torch CPU 源说明；(e) 为 `cross_version_agreement` 类管线函数补测试（空匹配应触发告警而非静默通过）。

**No confirmed P0 findings 不适用——本审查确认 1 项 P0（C-01）。** 全部主张的逐条裁决见同目录 `claim_evidence_matrix.csv`。

---

## 附：审查执行的复现命令清单（全部只读）

- `git log --stat`（三阶段时序与文件首次出现）；`git show <stage> -- <file>`（跨阶段 diff）。
- `.venv/Scripts/python.exe -m pytest tests/ -q` → 35 passed。
- `/tmp/audit/check2_split.py`：两种分割重现 + npz 一致性 + 13 分子差集 + 建模分割泄漏/Tanimoto/活性率重算。
- `/tmp/audit/check4_crossversion.py`、`check4b_correct_merge.py`、`check4c_dsstox.py`：失效 join 复现；InChIKey/CID/SMILES 三种口径正确 merge 与冲突统计；3 条不可解析 SDF 记录的 CID 提取（8043 闭合）。
- `/tmp/audit/check5_recompute.py`：冻结指标重算（最大偏差 8.3e-17）。
- `/tmp/audit/check5b_retrain.py`：seed42 重训（1.1e-16）+ joblib 一致性 + 冒烟重放。
- `/tmp/audit/check6_random_and_misc.py`：random×3 重现；LGBM 种子无关性；无效 SMILES/特征/重复/重叠/活性率核查。
- `/tmp/audit/check7_steroids.py` + npz 直查：甾体 FP 分子标签与分割归属。
