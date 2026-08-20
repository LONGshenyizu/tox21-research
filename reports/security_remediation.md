# Security Remediation and Regression Validation（Stage 9）

日期：2026-08-20 ｜ 分支：`security-hardening`（基线 `43b4513` = Engineering / API Freeze v1）
输入：白盒安全审计 findings（F1-F5 confirmed、P1 potential、H1 hardening；审计见 `security-audit` 分支 `f21fcde`）
性质：只修复安全问题；**未重训模型，未触碰 `data/processed`、`results/final`、冻结模型与预测逻辑**

## 1. 约束遵守情况

- `git diff 43b4513 --stat -- data/processed results/final` 为空（冻结产物零改动，子代理复核确认）。
- 改动面仅 5 个文件：`src/tox21_research/api.py`、`src/tox21_research/inference.py`、`src/tox21_research/model_integrity.json`（新增）、`tests/test_security.py`（新增）、`Dockerfile`。
- 科学连续性证明：CLI 对 105 分子固定样本输出 sha256 与修复前基线**逐字节一致**（`613bea2d…`）；API 与冻结 CLI 逐值比对 max |diff| = **1.11e-16**（1 ULP，与冻结期容器对比同级）。

## 2. 修复对照表（finding → commit → 行为差异）

| Finding | 严重性 | Commit | 修复 | 修复前 → 修复后 |
|---|---|---|---|---|
| F1 CPU 耗尽 | Medium（T2 下 High） | `e8042be` | SMILES 复杂度上限：长度 10000→**512** 字符（数据集 max 342），新增环闭合数字 ≤**64**（数据集 max 28），解析前廉价检查；`/health` 改 async（不再占线程池 token） | 审计 PoC 批量（8×9998 字符病理串）：**26,560ms → 34ms**，全部 valid=false；16 并发：分钟级 → **519ms**；负载下 /health：4200-5500ms → **2-25ms**（Docker healthcheck 5s 阈值不再可达） |
| F2 请求体无上限 | Medium（T2 下 High） | `8460328` | ASGI `BodySizeLimitMiddleware`：Content-Length 预检（不读 body 即拒）+ 无长度/欺骗时的流式字节计数兜底，上限 2MB；schema 描述文档化上限 | 2.6MB body：完整解析后 413/200 回显 40MB → **0.02s 内 413**；40MB 请求体与 ~5× 解析期内存放大路径消除（回显被 body+长度上限共同约束） |
| F3 单条异常击穿整批 | Low | `64e1d80` | `is_valid_smiles` 全捕获解析异常（逐项失效契约成立）；响应回显 UTF-8 可编码化（stdlib encode-replace） | `["CCO","\ud800","CCN"]`：**500 → 200**，valid=[true,false,true]；修复中发现的第二层崩溃（回显序列化 PydanticSerializationError）一并关闭 |
| F4 日志注入 | Low | `b805561` | 服务启动 `RDLogger.DisableLog("rdApp.*")`（与科研脚本既有做法一致） | 含换行载荷在服务日志伪造独立行 → **原始输入零回显**（子代理日志 grep 0 命中） |
| F5 文档端点暴露 | Low | `95cd2ca` | `docs_url/redoc_url/openapi_url=None` | /docs /redoc /openapi.json：**200 → 404** |
| P1 模型反序列化信任边界 | Potential | `3fb7700` | 加载前对每个冻结工件做 **SHA-256 固定校验**（清单 `src/tox21_research/model_integrity.json` 随镜像分发、git 固化）+ **路径包含检查**（必须在 `results/final` 内）；缺清单项/不匹配/越界 → 启动即失败（fail-secure） | joblib.load 无校验加载任意字节 → 篡改 1 字节即拒绝启动（子代理实测末字节翻转被拦截，错误含完整性信息） |
| H1 容器 root | Low（hardening） | `452762e` | Dockerfile：`useradd --system --uid 10001 tox21` + `COPY --chown` + `USER tox21` | root 运行 → 非 root（uid 10001）运行；**静态审查通过，本地未构建镜像（网络限制）** |

## 3. 新增回归测试

`tests/test_security.py`（22 项，全部真实行为、无 mock）：
`TestBodySizeLimit`（4：>2MB 413、<上限 200、Content-Length 预检不触达 app、chunked 流式跨限中止）
`TestSmilesComplexityLimit`（6：审计 PoC 无效化、批量 <5s、上限内正常分子仍 valid、化学合法但超限输入按策略判 invalid）
`TestModelIntegrity`（5：合法副本加载、篡改模型/配置拒绝、无清单项拒绝、路径逃逸拒绝）
`TestPerItemExceptionIsolation`（3：代理对批次 200、回显可编码、`is_valid_smiles` 吞异常）
`TestLogSecurity`（1：输入不进日志）
`TestDocsDisabled`（3：三端点 404）

每项修复均按 TDD 执行：先写失败测试（失败方式=修复前缺陷本身），再最小实现，再转绿。

## 4. Before/After 安全矩阵

| 攻击向量 | 修复前（实测） | 修复后（主代理实测 / 子代理独立复测） | 状态 |
|---|---|---|---|
| 80KB 病理批量 → CPU 饱和 + healthcheck 重启循环 | 26.56s CPU；/health 4.2-5.5s；>5s healthcheck 超时 | 34ms / 8.8ms；/health 负载下 2-25ms | **CLOSED** |
| 16 并发病理批量（饱和向量） | 分钟级 CPU 饱和 | 总计 519ms / 0.02s（16/16 成功） | **CLOSED** |
| 数十 MB body → 解析期 ~5× 内存尖峰 + 40MB 回显 | 40MB body→200 回显 40MB，堆峰值 200MB | >2MB 即 0.02s/1.3ms 413（不读 body） | **CLOSED** |
| 孤立代理对 → 整批 500 | HTTP 500（解析层与回显层两次） | HTTP 200，逐项 valid=false | **CLOSED** |
| 换行载荷 → 伪造日志行 | stderr 出现伪造独立 INFO 行 | 日志 0 命中原始输入 | **CLOSED** |
| /docs /redoc /openapi.json 未授权 | 全 200 | 全 404 | **CLOSED** |
| 模型文件篡改 → pickle RCE 原语（需文件写权限） | joblib.load 无校验 | sha256 不符即拒绝启动 + 路径包含 | **CLOSED**（原语利用前提本就超出 T1） |
| 容器 root | root 运行 | 非 root uid 10001 | **CLOSED**（静态） |

## 5. 验证汇总

- **全量测试**：`pytest tests/ -q` → **84 passed, 0 failed**（基线 62 + 新增 22；主代理与子代理各自独立运行）。
- **冻结零改动**：`git diff 43b4513 -- data/processed results/final` 为空。
- **CLI 逐字节复现**：105 分子输出 sha256 `613bea2d…` 不变。
- **API ↔ 冻结模型**：105×12 概率全量比对 max |diff| = 1.11e-16（现有 test_api.py 的一致性测试亦全部通过）。
- **数据集上限安全余量**：7,831 分子 max 长度 342（上限 512，余量 33%+）、max 环数字 28（上限 64，2.3×）；**0 分子因新上限失效**（子代理独立实测）。
- **修复自身审查**：中间件无绕过（欺骗/无长度/chunked/非数字 Content-Length 各路径均兜住并有单测）；无新引入漏洞。

## 6. 独立只读回归验证（子代理，2026-08-20）

7/7 项通过，findings F1-F5/P1/H1 全部 **CLOSED**，总判定 **REGRESSION PASS**。证据存于 `%TEMP%\regress_verify\`。三项非阻塞观察（如实记录）：
1. 预检 413 时先写完 body 再读响应的简单客户端可能收到连接中断而非 413（HTTP 语义允许，pre-parse 拒绝通病；标准客户端稳定收到 413）。
2. P1 存在校验→加载 TOCTOU 残余窗口与 manifest 自身属主问题（利用需本地文件写权限+时机，已远超基线；后续可改为内存内校验加载）。
3. 行为变化均属文档化的输入策略边界（超限化学合法输入判 invalid、代理对回显替换字符）。

## 7. 残余风险与后续建议（非阻塞）

- P2 供应链：requirements 未 hash 固定、基础镜像浮动 tag 未按 digest 固定（需网络，本轮未做）。
- 容器内 tox21 对自身目录可写：可加 `:ro` 挂载进一步收紧 P1。
- 对外暴露（T2）前仍建议反向代理层认证/限流——认证属工程决策，冻结文档 §6 已声明不在本轮范围。
- Docker 镜像构建实测待网络可用后补做（H1 目前为静态验证）。

## 8. Deployment Ready 判定

**T1（隔离单机/内网，冻结文档声明的部署假设）：DEPLOYMENT READY**——全部 findings 关闭、无新引入问题、科学结果逐字节不变、全量测试通过。
**T2（对外暴露）：CONDITIONAL**——本分支已消除已知的无认证 DoS/信息暴露面，但仍需代理层认证与限流、以及镜像构建实测后再放行。
