# 最终研究报告：基于公开 Tox21 数据的可复现多终点毒性预测（v2 修订版）

日期：2026-08-14 ｜ 冻结配置：`configs/final_model.json` ｜ 结果目录：`results/final/`
阶段提交：阶段 1 `53cc814` → 阶段 2 `3e586e6` → 阶段 3 冻结 `84ccf59` → 阶段 4 独立审查（`reports/audit/`）→ **v2 科学修订冻结（本版）**
v2 说明：阶段 4 审查发现数据来源叙述与审计代码两类问题（详见 `reports/revision_log.md`），本版修订了相关叙述与审计代码；**模型、超参、分割与全部冻结数字未做任何改动**。

---

## 1. 本研究实际使用的 Tox21 数据是什么

**MoleculeNet/DeepChem 托管的 Tox21 基准 CSV**（`tox21.csv.gz`，7,831 行 × 12 终点，SHA-256 `45d09792492…`，全部来源记录见 `data/raw/PROVENANCE.md`）。

- 12 个终点：核受体 7 个（NR-AR、NR-AR-LBD、NR-AhR、NR-Aromatase、NR-ER、NR-ER-LBD、NR-PPAR-gamma）+ 应激反应 5 个（SR-ARE、SR-ATAD5、SR-HSE、SR-MMP、SR-p53），均源自 Tox21 qHTS 计量响应实验（各终点对应 PubChem AID 见 `references/sources.md` P1）。
- 建模前剔除 8 个 RDKit 无法解析的铝盐 SMILES（占 0.1%，携带 82 个标签），实际建模 **7,823 个分子**。
- 同时下载并审计了 **2014 Tox21 Data Challenge 原始文件**（tripod.nih.gov，11,764 样本训练库 + 296 化合物排行榜测试集 + 647 化合物最终评测集），仅用于来源交叉验证，不用于建模。

## 2. 为什么选择该数据与评价协议

**数据**：(a) 该 CSV 与挑战赛原始训练库**按化合物编号 100% 对应**（TOX#### ↔ DSSTox_CID，7,831/7,831），标签高度一致但**非零冲突**——原始库中同一化合物存在多批次复测样本且无权威批次，冲突数依赖批次聚合约定（首样本 228 对 / 任一批本活性 11 对 / 多数票 102 对，占 both-labeled 对的 0.014%–0.29%；按完整 InChIKey 结构匹配的行为 83.8%，其余为标准化拼写差异）——详见 `data_audit.md` §1（v2 修订）；(b) 它是社区标准基准口径（TDC 同为 7,831×12），结果可与文献定性对照；(c) 文件由校验和固定，版本漂移可控。原始 SDF 含 2,952 个多批次化合物，直接建模需要自定聚合规则，会把研究变成"另一个数据版本"，故仅作溯源。

**协议**：主协议为 **Murcko scaffold 分割 80/10/10**（逐行复刻 DeepChem `ScaffoldSplitter` 算法并有单元测试，确定性无需随机种子）。理由：与 DeepChem 对该数据文件的默认一致；衡量对**新颖骨架**的泛化能力，更接近毒理学虚拟筛选的实际需求；泄漏审计干净（跨分割同结构仅 1 例，test→train 最近邻 Tanimoto 中位 0.405）。辅以 **random 分割 ×3 种子的敏感性分析**，因为 MoleculeNet 论文对该数据用的是 random 口径。

**指标**：每终点 ROC-AUC 为主（Tox21 挑战赛与 MoleculeNet 共同的主指标），PR-AUC 与 balanced accuracy 为辅（活性率仅 2.9–16.2%，必须补充不平衡敏感指标）；整体为 12 终点宏平均。**边界纪律**：全部选型只看 valid；test 在冻结后由 `scripts/final_test.py` 一次性评测；random 敏感性在 test 之后运行且不回馈任何模型修改。

## 3. 数据中的重要特征与问题

详见 `reports/data_audit.md`。要点：类别不平衡（NR-PPAR-gamma 2.9%–SR-ARE 16.2%）；每终点 5,810–7,265 有标签（缺失=inconclusive/未测）；244 个混合物、546 个带电结构、140 个含非有机元素——真实筛选库面貌，全部保留；仅 2 组重复结构（4 行），其中二氯氰尿酸衍生物一对（TOX4994/TOX6178）在 NR-ER 上标签冲突（1 vs 0）且分处 valid/test 两侧——保留原样并写入误差分析；SR-ARE 等终点存在 valid/test 活性率漂移（15%→22–25%）。**终点噪声底板**：原始库同化合物批间标签不一致率 1.0%（NR-PPAR-gamma）至 11.5%（NR-ER），为各终点可达性能提供先验参照（NR-ER 恰为本研究表现最差的终点之一）。

## 4. 分子表示

**ECFP4**（Morgan 循环指纹，半径 2，2048 bit，RDKit）。对照特征 MACCS（167 bit）：网格最优 C 下 0.737 vs 0.709。注意该对照未对 MACCS 做同等调参——同 C=1 时差距仅 0.0038（0.7125 vs 0.7087），故只支持"ECFP4 不劣于 MACCS"的弱结论。选择依据：该基准上文献最强经典基线特征、无外部服务依赖、完全可复现。

## 5. 比较了哪些模型

全部在相同 scaffold train/valid 上对比（`results/interim/model_comparison.csv`）：

| 模型 | 超参 | valid 宏 ROC-AUC | valid 宏 PR-AUC |
|---|---|---|---|
| **LightGBM ×12 单任务** | leaves=63, trees=800 | **0.7376** | **0.3665** |
| LightGBM ×12 单任务 | leaves=31, trees=400 | 0.7311 | 0.3491 |
| 逻辑回归 ×12 单任务 | C=0.1 | 0.7367 | 0.3384 |
| 逻辑回归 ×12 单任务 | C=1 / C=10 | 0.7125 / 0.6882 | 0.2950 / 0.2645 |
| 逻辑回归 ×12（MACCS 特征） | C=1 | 0.7087 | 0.2644 |
| 多任务 MLP（共享隐层 512-256） | 3 种子 | 0.7016 ± 0.0033 | 0.3197 |

所有模型统一 class-weight/scale-pos-weight 处理不平衡；MLP 用 valid 早停。多任务 MLP **未** 显示迁移增益（0.702 < 0.738），故未引入图模型——指纹表示下的线性/树模型已是该分割上的强基线，误差分析也未显示"指纹表示是瓶颈"的证据（见 §9）。

## 6. 最终模型如何确定

按预登记准则（valid 宏 ROC-AUC 最高）选择 **LightGBM（ECFP4，leaves=63，trees=800，lr=0.05，seed 42，确定性构建）**。与次优（LogReg C=0.1）的 ROC 差 0.0009 属噪声级，但 PR-AUC 高 0.028（不平衡数据上实质更优），且泛化理由充分。冻结配置与选型记录在 `configs/final_model.json`；模型文件在 `results/final/model/`；`test_summary.csv` 中 ensemble 行即最终评测结果（单确定性种子，集成=该模型本身）。

## 7. 各毒性终点表现（冻结 test，scaffold 分割）

| 终点 | ROC-AUC | PR-AUC | BAcc | | 终点 | ROC-AUC | PR-AUC | BAcc |
|---|---|---|---|---|---|---|---|---|
| NR-AhR | **0.795** | 0.446 | 0.660 | | NR-Aromatase | 0.692 | 0.318 | 0.593 |
| SR-MMP | 0.785 | **0.462** | 0.597 | | NR-ER-LBD | 0.681 | 0.232 | 0.636 |
| NR-AR-LBD | 0.775 | 0.396 | 0.680 | | NR-PPAR-gamma | 0.670 | 0.147 | 0.522 |
| SR-p53 | 0.734 | 0.376 | 0.578 | | NR-ER | 0.668 | 0.347 | 0.627 |
| NR-AR | 0.653 | 0.353 | 0.679 | | SR-ARE | 0.659 | 0.418 | 0.553 |
| SR-ATAD5 | 0.652 | 0.099 | 0.523 | | SR-HSE | 0.643 | 0.257 | 0.580 |

（完整表含样本数：`results/final/test_metrics_ensemble.csv`）

## 8. 整体表现

- **冻结 test（scaffold）：宏 ROC-AUC 0.7003 ｜ 宏 PR-AUC 0.3211 ｜ 宏 balanced accuracy 0.6024**。
- valid→test 差 -0.037：scaffold 测试集对模型更难（新骨架外推），符合预期方向。
- **random 分割敏感性**（冻结后运行）：3 个随机分割 test 宏 ROC-AUC = 0.7959 / 0.8055 / 0.8205（均值 0.807，种子间 ±0.010）。**在本研究的协议对比中观察到** scaffold 与 random 相差约 0.10，远大于本研究内部的模型间差异（≤0.04）。限定：这是观察性结论（scaffold 为单一确定性实现、random 为 3 个种子），不外推为一般因果规律；引用本研究数字时必须同时报告协议。与 MoleculeNet 论文 random 口径强基线 ~0.82 属不同数据版本与分割实现的定性并置，仅供参考。
- 推理冒烟示例（`scripts/predict.py`）：睾酮→AR 0.999、阿司匹林→全部 <0.01，方向化学上合理（v1 曾引更细的磺胺分子数字，因原始输出未留存，不再作为证据引用）。

## 9. 模型在哪些终点/样本上表现较差

- **终点**：SR-HSE（0.643）、SR-ATAD5（0.652，PR-AUC 仅 0.099——33 个活性样本下精确度极差）、NR-AR（0.653）、SR-ARE（0.659）、NR-ER（0.668）。NR-AR 从 valid 0.788 掉到 test 0.653（-0.136，test 仅 27 个活性，小样本方差+骨架外推叠加）。
- **样本**（`results/interim/error_analysis/valid_confident_errors.csv`）：最自信的假阳性是**甾体骨架分子**（TOX28569、TOX28690，AR 预测 0.999 但标注 inactive）。**假设（非结论）**：甾体与雄激素受体的结合是公认化学事实，这类错误可能反映测定阈值/标注边界或标签噪声，而非模型分辨率不足；仅凭结构+概率+二值标签无法区分这几种解释，裁定需要原始 qHTS 响应曲线。PR-AUC 最低的 SR-ATAD5 的活性样本稀少且分散。终点难度与活性样本数无相关（valid r=-0.04），但与批间标签不一致率方向一致（NR-ER 批间不一致 11.5% 且为最差终点之一）。
- 已知数据瑕疵的影响：NR-ER 标签冲突的重复对分居 valid/test，两侧预测均为 0，未造成可观察的错误。

## 10. 当前研究最主要的局限

1. **表示与模型容量**：仅指纹 + 浅层模型；未测试图神经网络与预训练分子表征（它们在本基准 random 口径下可到 0.82–0.84，但 scaffold 口径的文献增益较小且方差大）。未做的理由是误差分析没有指向指纹瓶颈，但这仍是外推上限的未知项。
2. **单一数据版本、单一分割协议为主**：scaffold 分割确定但只是一种外推假设；不同分割结论差 0.10，任何引用本研究的数字都必须同时报告协议。
3. **标签噪声不可分离**：qHTS 的 inconclusive 被当作"缺失"，conflict 保留原样；终点级 AUC 的上限受测定重复性约束（原始库同化合物批间不一致率 1.0%–11.5%，NR-ER 最高且为最差终点之一；SR-HSE 批间 3.1%）。
4. **跨版本标签分歧的语义未裁定**：MoleculeNet 与挑战赛发布标签存在 11–228 对冲突（依赖批次聚约定），哪侧"更正确"需原始 qHTS 曲线才能判定，本研究不裁定。
5. **挑战赛外部评测不可复现**：最终评测集标签从未公开，本研究与挑战赛名次不可直接比较。
6. 未使用绝对效能/剂量响应信息（Tox21 原始 qHTS 曲线可提供 AC50 等），二值化损失了信息。

## 11. 后续研究最优先解决的问题

1. **图/预训练表示对照实验**（同协议、多种子）：直接回答"scaffold 口径下表示学习是否有真实增益"，这是本研究的自然延伸与最大未知。
2. **利用原始 qHTS 连续数据**（PubChem AID 级 AC50/hit-call 质量），把"inconclusive"细分为可信度而非统一缺失。
3. **终点间关系建模**：NR-ER/ER-LBD、AR/AR-LBD 的联合误差分析（相同受体系统），可能揭示系统性标注问题。
4. 扩展为**多版本协议矩阵**（数据版本 × 分割 × 指标）的系统性基准，量化每个选择的影响——本研究已给出其中一列（scaffold vs random 差 0.10）。

---

## 复现指南

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r environment/requirements.txt
                                                   # requirements.txt 首行含 torch CPU 源的 --extra-index-url
.venv/Scripts/python scripts/download_data.py     # 校验 SHA-256
.venv/Scripts/python -m pytest tests/ -q          # 45 个单元/回归测试（含真实数据慢测试）
.venv/Scripts/python scripts/audit_data.py        # 数据审计（建模分割上，含跨版本三约定比对）
.venv/Scripts/python scripts/prepare_data.py      # 特征与分割缓存
.venv/Scripts/python scripts/run_experiments.py   # 阶段 2 选型（valid）
.venv/Scripts/python scripts/error_analysis.py    # 验证集误差分析
.venv/Scripts/python scripts/final_test.py        # 阶段 3 冻结 test 评测（一次性）
.venv/Scripts/python scripts/random_split_check.py# random 分割敏感性
.venv/Scripts/python scripts/predict.py in.smiles out.csv   # 推理
```

环境：Windows / Python 3.11.9 / rdkit 2026.03.5 / scikit-learn 1.9.0 / LightGBM 4.7.0 / pandas 3.0.5 / numpy 2.4.6 / torch 2.13.0+cpu（完整冻结见 `environment/requirements.txt`，含 torch CPU 安装源）。除明确列出的种子外全部流程确定性（scaffold 分割无需种子；LogReg/LGBM 确定性构建）。
