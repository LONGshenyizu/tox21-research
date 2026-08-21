# Limitations（已知限制清单）

日期：2026-08-21 ｜ 汇总自：final_report §8、revision_log、engineering_freeze §6、security_remediation §7、最终独立评审（阶段 10）

## 1. 科学层

| # | 限制 | 影响 | 状态/出处 |
|---|---|---|---|
| S1 | 仅指纹（ECFP4/MACCS）+ 浅层模型（LogReg/LGBM/浅 MLP），无 GNN/预训练表示对照 | 绝对性能不代表 Tox21 上限；结论限定在"经典管线"范围内 | 项目自列为首要后续工作（final_report §10） |
| S2 | 单一数据版本（MoleculeNet CSV 一份、挑战赛 SDF 一份，均校验和固定） | 无法评估数据版本漂移的长期影响 | PROVENANCE.md 固定即为此妥协 |
| S3 | scaffold 分割单一确定性实现（无随机 scaffold 变体、无分割方差量化） | 分割难度贡献未带不确定度；random 对照有 3 seeds 但 scaffold 侧只有 1 次 | 确定性已由独立逐元素复现锁定（可复现性优先于方差分析） |
| S4 | qHTS 标签噪声/inconclusive 语义在两个公共版本中不可分离 | 跨版本冲突（228/11/102 对）无法裁定哪侧正确；需原始剂量-响应曲线 | data_audit §1 明示为观察性结论 |
| S5 | 挑战赛官方评测不可复现（score 集标签从未公开） | 无法与 2014 参赛队伍官方排名直接对比 | data_audit/audit 记录 |
| S6 | 类别失衡下 BAcc 等阈值指标依赖 0.5 阈值 | BAcc 0.6024 仅为参考指标 | 主指标为 ROC-AUC（阈值无关） |

## 2. 工程层

| # | 限制 | 影响 | 状态/出处 |
|---|---|---|---|
| E1 | 供应链未完全闭合：基础镜像浮动 tag（python:3.11-slim 未按 digest 固定）、requirements 未加 `--require-hashes` | 构建不可逐位重现（版本已锁定，但 wheel 字节未固定） | 需网络可用时处理（security_remediation §7） |
| E2 | 模型加载存在校验→加载 TOCTOU 残余窗口 | 拥有本地文件写权限+精确时机的攻击者理论上可绕过 sha256 校验 | 利用前提已超出 T1 威胁模型；可选改进为内存内校验后加载 |
| E3 | `scripts/` 入口脚本无直接单元测试 | 管线级回归靠库层测试与 slow 数据回归测试守护 | 阶段 4 审计已知（历史 P0 即从 scripts 层逃逸后被库层修复） |
| E4 | 真实数据回归测试（test_regression_audit.py）在未下载原始数据时静默跳过 | fresh clone 在 L3 第 1 步之前跑测试，三个防复发锚点不被执行 | reproducibility.md L1 已注明显式条件 |
| E5 | 研究 CLI（scripts/predict.py）对无效 SMILES 整体抛错 | 与 API 的逐项失效契约不对称 | API 侧已修复（F3）；CLI 属本地研究工具，未改 |
| E6 | 跨平台 1-ULP（1.11e-16）浮点差异 | Windows 与 Linux 求和顺序不同 | 已量化并声明 1e-12 判等容差（engineering_freeze §4/§6） |
| E7 | API 契约在安全修复后有三处变化（body 2MB 上限、SMILES 512 字符/64 环数字、docs 关闭） | 依赖旧行为的客户端需适配；化学合法但超限的输入会被判 invalid | 全部文档化于 security_remediation §2/§6，并有回归测试 |
| E8 | 单 worker、无认证/限流/可观测性 | 仅适用于 T1（隔离内网） | 冻结文档 §6 声明的刻意决策；对外暴露（T2）前需代理层认证限流 |

## 3. 安全层（残余项）

| # | 限制 | 状态 |
|---|---|---|
| SEC1 | Docker 镜像构建与非 root 运行的**物理实测**依赖网络（见 final_status.md 的最新记录） | H1 修复为静态验证 + 构建实测（若完成） |
| SEC2 | P1 的 manifest（model_integrity.json）自身不自校验，且在容器内与代码同属主 | 攻击者到该权限已可直接改代码，无实际增量暴露；可选 `:ro` 挂载收紧 |
| SEC3 | 预检 413 时"先写完 body 再读响应"的简单客户端可能收到连接中断而非 413 | HTTP 语义允许；标准客户端实测稳定收到 413 |

## 4. 文档层

| # | 限制 | 状态 |
|---|---|---|
| D1 | 各阶段报告为时间戳记录（如 final_report 写"45 项测试"为当时数字，现为 84） | 本文件所在 `reports/final/` 与 README 为当前状态权威入口；历史报告不改写 |

## 5. 明确不做的事

- 不追新模型/SOTA；不扩充数据；不发布挑战赛 score 集的"伪标签"评测；不在本仓库引入认证体系（属部署环境职责）。
