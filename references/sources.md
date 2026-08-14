# 外部资料清单（所有访问日期：2026-08-14）

仅列入对本研究决策产生实质影响的资料。优先级：官方来源 > 原始论文 > 同行评议文献/预印本 > 软件官方文档。

## 1. 数据集与项目官方来源

| # | 资料 | URL | 支持的研究判断 |
|---|---|---|---|
| S1 | Tox21 Data Challenge 2014 官方数据页（NIH/NCATS，tripod.nih.gov，存档快照 `data/raw/challenge2014/_data_page.html`） | https://tripod.nih.gov/tox21/challenge/data.jsp | 原始训练/测试/评测数据文件清单与下载；12 个测定对应的 PubChem AID；官方 baseline 为 LyChI 结构标准化 + PubChem 指纹 + 朴素贝叶斯 |
| S2 | DeepChem MoleculeNet Tox21 加载器源码 `deepchem/molnet/load_function/tox21_datasets.py`（master） | https://github.com/deepchem/deepchem/blob/master/deepchem/molnet/load_function/tox21_datasets.py | 本研究主数据 CSV 的权威下载 URL；12 任务名清单；DeepChem 默认协议（ECFP 指纹 / scaffold 分割 / 类平衡加权）；其 docstring 同时注明该库“建议 random split”，说明两种协议并存 |
| S3 | DeepChem `deepchem/splits/splitters.py`（master）中 `ScaffoldSplitter` | https://github.com/deepchem/deepchem/blob/master/deepchem/splits/splitters.py | 本研究 scaffold 分割的精确算法（按组规模与首索引降序贪心填充；无效 SMILES 跳过；确定性），据此逐行复刻并单元测试 |
| S4 | Therapeutics Data Commons（TDC）Tox21 页面 | https://tdcommons.ai/single_pred_tasks/tox/ | 独立佐证 7,831×12 版本即社区流通的 "Tox21" 基准数据；TDC 提供 random/scaffold 两种分割 |

## 2. 原始研究论文

| # | 资料 | URL / DOI | 支持的研究判断 |
|---|---|---|---|
| P1 | Huang R. et al. "Tox21Challenge to Build Predictive Models of Nuclear Receptor and Stress Response Pathways As Mediated by Exposure to Environmental Chemicals and Drugs." *Front. Environ. Sci.* 3:85 (2016). | https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2015.00085/full ; DOI: 10.3389/fenvs.2016.00085 | 12 个终点的官方定义与 PubChem AID；训练集 8043、最终评测集构成（LOPAC 留出 296 + EPA 345）；挑战赛评分协议（主指标 AUC-ROC，平分用 balanced accuracy）；各终点难度与活性率的关系（AR/AR-LBD 活性率 <5% 时最难） |
| P2 | Wu Z. et al. "MoleculeNet: a benchmark for molecular machine learning." *Chem. Sci.* 9:513–530 (2018). | https://pmc.ncbi.nlm.nih.gov/articles/PMC5868307/ ; DOI: 10.1039/C7SC02664A ; arXiv:1703.00564 | MoleculeNet 版数据的来源描述与推荐协议（80/10/10，分类用 ROC-AUC，Tox21 推荐 random split）；可比基线数字（random split 测试集 ROC-AUC：KernelSVM 0.822，GraphConv 0.829）；论文正文样本数 8014 与托管 CSV 7831 的出入（以校验和固定的 CSV 文件为准） |

## 3. 说明与限制

- moleculenet.org 数据集页在审计时返回 404（站点迁移），未作为依据。
- `web.archive.org` 在本网络环境不可达（超时），原始站点 tripod 仍在线，故未使用存档副本。
- `ncats/tox21baseline`（官方 baseline 代码库）由 S1 页面链接，本研究仅引用 S1 对其的描述，未复用其代码。
- Huang et al. 报告的挑战赛获胜成绩（各终点 AUC-ROC 0.81–0.95）与 MoleculeNet 论文基线（random split 0.75–0.83 量级）来自**不同数据划分与不同测试集**，不可直接比较；本研究结论只与本研究协议内部可比。此判断同样基于 P1（评测集为独立 641 化合物）与 P2（MoleculeNet 为内部 10% 划分）。
