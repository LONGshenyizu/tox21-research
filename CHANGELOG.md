# Changelog

本项目的阶段化演进记录。科学冻结产物（`data/processed`、`results/final`）自 Stage 3 起内容不变；后续阶段仅追加工程、安全与发布工件。提交哈希与分支可用只读 git 命令核验。

## [1.0.0] - 2026-08-21（final-package 分支）

### 发布工件（Stage 12）
- 添加 MIT 许可证（选择理由：研究工件以学术复用与引用为首要目标，MIT 为研究软件最通行、摩擦最低的宽松许可证；无专利条款诉求。发布前如需 Apache-2.0 专利授权可整体替换）。
- 添加 `CITATION.cff`（DOI 与仓库 URL 为占位符，存档时替换）。
- 添加本 CHANGELOG。
- 添加最小 CI（install → tests → artifact 校验；不含训练）与 `scripts/verify_artifacts.py` 完整性校验工具。

### 最终评审与发布包（Stage 11，2026-08-21）
- README 重写为第三方入口（目标/数据/流程/结果/部署/安全/限制/验证入口）。
- `reports/final/` 证据包：claim_evidence_matrix.csv（17 项主张：16 SUPPORTED、1 SUPPORTED WITH LIMITATION）、reproducibility.md（L1-L4 复现指南）、limitations.md、final_status.md。
- Docker 最终验证实测：构建成功、非 root（uid 10001）、/health 200、/docs 404、容器↔CLI 预测 1.11e-16、容器内病理批量 3ms（`868b7ff`）。
- 模拟期刊审稿（全新只读代理）：独立重算全部头条指标（偏差 8.3e-17）后给出 MAJOR REVISION 倾向；其意见归档于 `reports/final/peer_review_simulation.md`，其中两处文档事实错误与"独立审计"措辞已修正（`583a3ef`）。

### 安全修复（Stage 9，2026-08-20，security-hardening 分支，基于 `43b4513`）
审计 findings 全部关闭，科学输出逐字节不变（CLI 105 分子 sha256 一致；冻结目录零 diff）：
- F1 CPU 耗尽：SMILES 复杂度上限（512 字符/64 环数字）+ `/health` 异步化（`e8042be`；病理批量 26.6s→34ms）。
- F2 请求体无上限：2MB body 上限中间件，预检 413（`8460328`）。
- F3 整批 500：逐项异常隔离 + 回显可编码化（`64e1d80`）。
- F4 日志注入：服务禁用 RDKit rdApp 日志（`b805561`）。
- F5 文档端点暴露：docs/redoc/openapi 关闭（`95cd2ca`）。
- P1 反序列化信任边界：冻结工件 SHA-256 固定校验 + 路径包含（`3fb7700`）。
- H1 root 容器：非 root uid 10001（`452762e`；后经 Stage 11 构建实测确认）。
- 修复报告与回归记录：`reports/security_remediation.md`（`c05145a`）；两轮独立于主实现的代理回归验证 REGRESSION PASS。

### 安全审计（Stage 7，2026-08-20 复审；security-audit 分支 `f21fcde`）
- 白盒审计：F1-F5 confirmed（PoC 验证）、P1 potential（RCE 原语证明）、H1 hardening；依赖 OSV 全量 56 包 0 已知漏洞。

### 工程冻结（Stage 6/8，2026-08-14，`43b4513`，revision-v2 分支）
- FastAPI 推理服务（POST /predict、GET /health）复用唯一推理实现；科研 CLI 重接为同一模块薄封装（重接前后输出 SHA-256 一致）。
- Docker 镜像（离线推理、无数据）；API↔CLI↔容器三方一致（≤1.11e-16）；重启确定性验证。
- 62 项测试（45 科研 + 17 API）。

### 科学修订冻结 v2（Stage 5，2026-08-14，`b50229f`）
- 独立审计（Stage 4，`ca12336`：P0×1、P1×2）驱动的修订：撤销 v1"零冲突"错误结论并量化（228/11/102 对，依三种批次聚约定）；模型结果与 v1 完全一致。

### 科学结果冻结（Stage 3，2026-08-14，`84ccf59`）
- 冻结配置：LightGBM+ECFP4（leaves 63/trees 800，seed 42）；scaffold test 宏 ROC-AUC 0.7003 / PR-AUC 0.3211 / BAcc 0.6024；random 对照 0.807±0.010。

### 选型与数据（Stage 1-2，2026-08-14，`53cc814`、`3e586e6`）
- 数据：MoleculeNet Tox21 CSV（7,831×12，SHA-256 固定）+ 2014 挑战赛 SDF；跨版本审计与泄漏检查。
- 选型（valid 口径）：LGBM 0.7376 居首；预登记协议与数据审计报告。

## 约定
- 日期为各阶段冻结/提交日；分支 `main` 停留在 Stage 3（`84ccf59`），完整历史见 `revision-v2` → `security-audit` → `security-hardening` → `final-package`。
- 科学数字的当前权威入口：`README.md` §4 与 `reports/final/claim_evidence_matrix.csv`。
