# Final Status（最终状态判定）

日期：2026-08-21 ｜ 分支：`final-package`（= security-hardening `c05145a` + 发布包文档）

## 1. 阶段完成度

| 阶段 | 内容 | 分支/提交 | 状态 |
|---|---|---|---|
| 1 | 数据来源确认、审计、研究计划 | `revision-v2`（53cc814…） | 完成 |
| 2 | 基线与选型（valid 宏 ROC-AUC 0.7376） | `3e586e6` | 完成 |
| 3 | 冻结 test 评测 + 最终报告（0.7003/0.3211） | `84ccf59` | 完成 |
| 4 | 独立科学审计（P0×1、P1×2 裁决） | `ca12336` | 完成 |
| 5 | 科学修订 → Scientific Result Freeze v2 | `b50229f` | 完成（v1=v2 数字不变） |
| 6/8 | Engineering / API Freeze v1 | `43b4513` | 完成（62 tests） |
| 7 | 安全审计（F1-F5/P1/H1，全部 PoC 验证） | `security-audit` `f21fcde` | 完成 |
| 9 | 安全修复 + 回归验证（7 commits，84 tests，REGRESSION PASS） | `security-hardening` `c05145a` | 完成 |
| 10 | 最终独立评审（头条数字全部独立重算吻合） | 评审报告（对话存档；复核结论已并入本目录证据矩阵） | 完成 |
| 11 | 发布包 + Docker 验证 + 审稿模拟 | `final-package`（本分支）+ `peer_review_simulation.md` | 完成 |

## 2. 一句话判定

**科学结论**：全部主要数字（0.7376 / 0.7003+0.3211 / 0.807±0.010 / 分割 6258-782-783 / 冲突 228-11-102）经独立于主实现的复核（阶段 10 终审代理、阶段 11 模拟审稿代理；均为自动化代理复核，非人类外部第三方）从 git 工件重算并吻合——`claim_evidence_matrix.csv` 17 项主张中 16 项 SUPPORTED、1 项 SUPPORTED WITH LIMITATION、0 项 NEEDS REVISION / NOT SUPPORTED。

**工程与安全**：84 项测试全通过；安全 findings 全部关闭且未改变任何被接受输入的预测（CLI 逐字节一致、API↔CLI 1.11e-16、冻结目录零改动）。

**部署就绪**：T1（隔离内网）DEPLOYMENT READY；T2（对外暴露）CONDITIONAL（需代理层认证/限流）。

## 3. Docker 验证记录（2026-08-21，final-package 分支实测）

环境：Docker Desktop 29.2.1（Linux engine，Windows 宿主）；`docker build -t tox21-api:final .` 成功（3.8s，requirements 层命中缓存；镜像 sha256:92b46908…）。

| 检查项 | 结果 |
|---|---|
| docker run -d -p 8000:8000 | 容器正常启动 |
| GET /health | 200，`{"status":"ok","model_loaded":true,"family":"lgbm_ecfp4","feature_set":"ecfp4","n_endpoints":12}` |
| **非 root 运行（H1 物理实测）** | `docker exec id` → `uid=10001(tox21) gid=999(tox21)` |
| GET /docs（F5 容器内） | 404 |
| POST /predict（3 分子，含 1 无效项） | 200，逐项 valid/invalid 与 probabilities 正常 |
| **prediction 一致性（容器 ↔ 本地 CLI）** | 3 分子 × 12 终点 = 36 概率，max \|diff\| = **1.11e-16**（已知跨平台 1-ULP，≤1e-12 容差通过） |
| F1 病理批量（容器内抽验） | 8×9998 字符病理串 → **3ms**，全部 valid=false |

结论：H1 由"静态验证"升级为**构建+运行实测 CLOSED**；镜像构建/运行/API/预测一致性全部物理验证通过。验证容器已删除（镜像 `tox21-api:final` 保留在本地）。遗留供应链限制 E1（基础镜像浮动 tag、无 hash 固定）不变——见 limitations.md。

## 4. 残余限制（摘要）

完整清单见 `limitations.md`（科学 6 项 / 工程 8 项 / 安全 3 项 / 文档 1 项）。最需跟进的三件：
1. 网络可用后按 digest 固定基础镜像 + `--require-hashes`（E1，同时关闭 SEC1 脚注）；
2. `scripts/` 层最小测试 + predict.py 逐项失效（E3/E5，历史 P0 的逃逸面）；
3. README→各阶段文档的交叉引用维护（新增报告时同步）。

## 5. 第三方验证入口

`README.md` §8 → `reproducibility.md`（L1-L4 四档）→ `claim_evidence_matrix.csv`（逐条对照）。
