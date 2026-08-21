# Peer Review Simulation（模拟期刊审稿记录）

日期：2026-08-21 ｜ 审稿人角色：计算化学 / 化学信息学 ML 审稿人（全新只读代理，与项目既往工作无关联）
审查对象：`final-package` @ `868b7ff` ｜ 方式：只读审查 + 有限验证（84 tests 重跑、全部头条指标从工件重算、sha256 链核验、CLI 冒烟复放）
验证产物：`%TEMP%\journal_review\`（recompute.py 等）｜ 仓库零改动
说明：本文件为模拟审稿记录的归档，用于留存其 Major/Minor comments 作为后续修订依据；措辞中"独立"指独立于主实现的自动化代理复核，非人类外部第三方。

## 审稿摘要（原文摘录）

本文稿报告了一项基于公开 Tox21 数据的 12 终点毒性预测可复现研究（Murcko scaffold 80/10/10，LightGBM+ECFP4 冻结 test 宏 ROC-AUC 0.7003，random 对照 0.807±0.010），附数据双版本交叉审计、冻结评测纪律、FastAPI/Docker 推理服务及一轮安全审计与修复。审稿人独立重算全部头条数字（最大偏差 8.3e-17）、84 项测试全过、sha256 链匹配。科学新颖性有限（ECFP4+浅层模型为已知基线，scaffold/random 差异为领域已知现象的确认性结果，无 GNN/预训练对照，scaffold 单实现无方差）；软件发布规范缺失（无 LICENSE/DOI/CI）。**建议 MAJOR REVISION**：可信度工程顶级、科学增量边际、发布规范缺位——后两项可修，不拒稿。

## 四问回答（要点）

1. **最大优势**：证据链的可外部验证性——不重训、不联网即可从冻结工件复算全部头条数字（审稿人已做到，偏差 8.3e-17）；claim-evidence 矩阵、一次性 test 评测的 git/mtime 证据、对自身 P0 错误的完整披露构成同类投稿罕见的可审计标准；数据双版本冲突审计本身有独立参考价值。
2. **最大质疑**：科学新颖性不足叠加发布规范缺失（无 GNN 对照使"指纹不是瓶颈"叙事无法闭合；scaffold 单 realization 无不确定度；无 LICENSE 对软件型刊物为一票否决；"独立审计"实为内部代理审计需限定措辞）。
3. **需降语气的 claim**：DeepChem "等价"应限定为行为规格实现（未与库本体直接对照）；"两轮独立代理"应注明非外部第三方；README §4 的 0.107 vs 0.036 比较应注明口径不同（test vs valid）与 scaffold 单实现；"第三方独立重算"表述限定为代理复核。（注：以上措辞已在 2026-08-21 文档修正中落实。）
4. **case study publication quality**：未完全达到，倾向 **MAJOR REVISION**——J. Cheminform. 软件 track 当前不满足受理（LICENSE/存档缺失）；ACS Omega software/data 或 reproducibility/benchmark track 在补齐后可达发表水平。

## Major Comments（修订必须解决）

1. 添加 OSI 开源许可证（MIT/BSD-3/Apache-2.0）+ pyproject license 元数据 + Zenodo 存档 DOI。
2. 补 scaffold 分割方差（组自助或多种子变体），或把 0.107 vs 0.036 比较降为无不确定度的观察并同步 README。
3. 补至少一个现代基线（GCN/GraphConv/预训练表示，同协议多种子），或把定位收窄为"经典指纹管线的可复现性 case study + 数据审计"。
4. 全稿区分"内部代理审计"与"外部第三方验证"措辞。
5. 以 deepchem 库本体做一次直接分割对照（可选标记测试），做不到则维持降格措辞。

## Minor Comments

1. 更正 final_status §2 主张计数（16 SUPPORTED + 1 WITH LIMITATION）——已修正。
2. 更正 README §9 模块数（10 个 .py）——已修正。
3. PROVENANCE 为解压后三个 SDF 增加独立 sha256（当前只 pin zip 字节）。
4. "按化合物编号 100% 对应"处前置"两版本作为基准协议不等价（冲突 0.014%–0.29% 依聚约定）"。
5. scripts/ 层最小冒烟测试（关闭 E3）。
6. slow 回归测试静默跳过改为显式报告 skip 数。
7. 基础镜像 digest 固定 + `--require-hashes`（E1）。
8. CLI 逐项失效与 API 契约对齐（E5）或文档说明差异理由。
9. final_report §8 的 MoleculeNet ~0.82 并置加具体出处脚注（KernelSVM 0.822 / GraphConv 0.829）。
10. 增加 CITATION.cff 与版本标签 v1.0.0，配合 DOI。

## 审稿人的独立验证记录（要点）

- 指标重算：test 宏 0.700314 / PR 0.321138 / BAcc 0.602436（与冻结 CSV 最大偏差 8.3e-17）；valid 0.737576；random 均值 0.8073 / std 0.0101。
- 冻结纪律：`run_experiments.py` 不引用 test_idx（grep 证实）；results/final 首现于单 commit `84ccf59`；test 指标 mtime 单次突发、random 在其后。
- 数据与泄漏：冲突 228/11/102、both 77,889、Tanimoto 中位 0.4054/≥0.95 共 7——逐数吻合。
- 工件：`model_integrity.json` 两条 sha256 MATCH；`frozen_config.json ≡ configs/final_model.json`；预测 CSV 行序与 npz test_idx 逐项相等。
- 冒烟：阿司匹林全终点 <0.01；苯并噻唑砜 AhR 0.9998 / SR-ARE 0.9946（可按 reproducibility.md L2 第 5 步复算）。
- 发现文档错误 2 处（主张计数、模块数）——均已修正。

## 最终建议

**MAJOR REVISION** —— 证据链经独立重算完全成立、自我纠错记录堪称范本；科学新颖性需补现代基线或收窄定位支撑；发布要件（LICENSE/DOI/CI）缺位。全部问题可在不推翻任何冻结数字的前提下修复。
