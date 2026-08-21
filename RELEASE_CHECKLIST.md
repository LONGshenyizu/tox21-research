# Release Checklist（发布清单）— v1.0.0 Release Candidate

状态：**RC 就绪（APPROVED WITH NOTES），等待人工确认发布。本文件生成过程未上传任何公网、未修改任何 git 历史。**
基线：分支 `final-package`（RC 终审 `d96d1d4` + 本清单提交）；annotated tag `v1.0.0` 指向本清单提交。
冻结约束已复核：`git diff 84ccf59 --stat -- data/processed results/final` 为空。

## 0. 发布前人工决策项（阻塞发布，需陈先生明示）

| # | 决策 | 选项与默认建议 |
|---|---|---|
| D1 | **提交作者邮箱公开**：14 个提交 + tag 元数据含 `2608900633@qq.com`；不改写历史则推任意含本分支的历史都会公开 | (a) 接受（默认建议：与署名身份一致；代价=爬虫收割风险）；(b) 改用 GitHub noreply 并改写历史（本阶段被禁止，需另行授权）；(c) 放弃公开 |
| D2 | **推送范围**：全部 4 个分支（main/revision-v2/security-audit/security-hardening/final-package）还是仅 final-package | 默认建议全量（security-audit 分支是审计证据链一部分）；仅推 final-package 可缩小历史路径暴露面，但需同步修改 README §3 分支地图（前向提交，允许） |
| D3 | 历史中的本地路径（16 提交 + security-audit 分支 1 份 uvicorn 日志堆栈，用户名 "admin" 通用、无凭据） | 默认接受（低危）；清除需历史改写（禁止） |

## 1. 发布要素（当前状态）

- [x] LICENSE：MIT（Copyright 2026 龙神一族）
- [x] CHANGELOG.md（v1.0.0 段完整）
- [x] README.md（第三方入口，八板块）
- [x] pyproject.toml（name/version 1.0.0/license MIT/authors）
- [x] CITATION.cff（cff 1.2.0；两处占位符见 §3）
- [x] CI（.github/workflows/ci.yml：install→tests→verify；首次 push 后自动运行）
- [x] scripts/verify_artifacts.py（本地 PASSED：模型哈希/配置一致性/分割清单/原始数据 7 文件哈希）
- [x] 测试：本地 84 passed（fresh clone/CI 上为 82 passed + 2 skipped——慢测试需原始数据，语义已声明）
- [x] tag：v1.0.0（annotated，指向本提交）
- [x] repository URL：`https://github.com/LONGshenyizu/tox21-research`（CITATION.cff 已更新）
- [ ] DOI：**待填**（占位 `10.0000/zenodo.placeholder`，位于 CITATION.cff；Zenodo 元数据已备好于 `.zenodo.json`）

## 2. Release notes 草稿（可直接用于 GitHub Release）

```markdown
Tox21 多终点毒性预测：可复现研究与推理工件 v1.0.0

首个公开发布。包含：完整可复现科研流程（数据审计→选型→冻结评测→独立审计→修订）、
冻结模型（LightGBM+ECFP4，scaffold test 宏 ROC-AUC 0.7003 / PR-AUC 0.3211，
random 对照 0.807±0.010）、FastAPI 推理服务（经安全审计与修复）、
Docker 镜像（非 root）、84 项测试与工件完整性校验器。

验证入口：README §8（pytest / verify_artifacts / reports/final/claim_evidence_matrix.csv，
17 项主张：16 SUPPORTED + 1 SUPPORTED WITH LIMITATION）。
许可证：MIT。引用：见 CITATION.cff（引用时必须同报分割协议）。
```

## 3. 发布操作序列（人工执行）

1. 确认 §0 三项决策。
2. 创建公开仓库，替换 `CITATION.cff` L12 为真实 URL（新提交）。
3. 推送：`git push --all && git push --tags`（或按 D2 范围推送）；确认 CI 首跑绿（预期 82 passed, 2 skipped + verifier PASSED）。
4. Zenodo 存档：
   - [ ] `git archive --format=zip -o tox21-research-v1.0.0.zip v1.0.0`（仅跟踪文件）
   - [ ] Zenodo 新 upload：类型 software；标题/作者/版本/许可证/关键词照抄 CITATION.cff；上传 zip
   - [ ] 取得 DOI 后回填 CITATION.cff L15（若 v1.0.0 已发布，回填作为 v1.0.1 或在 release notes 附注 DOI，避免改动已发布 tag 内容）
5. GitHub Release：tag `v1.0.0` + §2 草稿 + DOI 链接。
6. 发布后抽验：fresh clone → pytest（82+2 skipped）→ verify_artifacts → 按 `reports/final/reproducibility.md` L2 重算 0.700314/0.321138。

## 4. 已知接受项（随发布公开，均有记录）

- 提交历史含作者 QQ 邮箱与 16+1 个历史块的本地路径（当前树已脱敏；清理需历史改写，未执行）。
- `results/final/model/model_seed42.joblib` 66.2MB（>50MB 警告线，<100MB 硬限，无需 LFS）。
- CI 首跑前 `ci.yml` 未在真实 runner 上执行过（本地等价命令全绿）。
- 慢测试在无数据环境自动跳过（语义见 README §7 / reproducibility.md L1）。
