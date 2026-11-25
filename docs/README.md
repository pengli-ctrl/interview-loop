# InterviewLoop 文档

这里是 InterviewLoop 的正式文档入口。根目录 [README](../README.md) 负责项目概览与快速开始，本目录负责架构、面试引擎、评估、运维和产品说明。

## 推荐阅读顺序

1. [产品概览](product/overview.md)：项目定位、用户价值、边界与适用场景。
2. [使用指南](product/user-guide.md)：从创建面试到复盘、成长记录和导出记录。
3. [架构说明](architecture.md)：模块边界、运行链路、数据与部署方式。
4. [面试引擎](interview-engine.md)：场景配置、状态机、追问、JD/简历匹配和记录输出。
5. [评估体系](evaluation.md)：检索评估、Rubric、质量校准、Trace 与回归测试。
6. [运维手册](operations.md)：配置、启动、Docker、API、数据目录和故障排查。
7. [代码注释规范](code-style.md)：模块、类、函数的中文 Google docstring 与推送门禁。
8. [产品路线图](product/roadmap.md)：已完成范围、公测前门槛和后续演进。
9. [架构决策记录](adr/)：关键取舍及其上下文。

## 文档地图

| 文档 | 回答的问题 |
|---|---|
| [architecture.md](architecture.md) | 系统由哪些模块组成？请求如何流转？为什么保持模块化单体？ |
| [interview-engine.md](interview-engine.md) | 面试如何配置、出题、追问、切换阶段和生成记录？ |
| [evaluation.md](evaluation.md) | 如何验证检索质量、评分稳定性和 Agent 运行质量？ |
| [operations.md](operations.md) | 本地、Docker 和 API 如何配置与启动？数据保存在哪里？ |
| [code-style.md](code-style.md) | 中文 Google docstring 和代码推送门禁如何执行？ |
| [product/overview.md](product/overview.md) | 产品面向谁、解决什么问题、当前不做什么？ |
| [product/user-guide.md](product/user-guide.md) | 候选人如何完成一次完整训练闭环？ |
| [product/roadmap.md](product/roadmap.md) | 已交付什么？距离公测还缺什么？ |
| [demo/README](../demo/README.md) | 演示素材如何组织、如何重新生成？ |

## ADR 索引

ADR 记录已经发生的架构取舍，不代替当前实现文档。

| 编号 | 主题 |
|---|---|
| [ADR-001](adr/0001-deterministic-workflow-vs-autonomous-agent.md) | 确定性工作流优先于完全自主 Agent |
| [ADR-002](adr/0002-hybrid-rag-with-bm25-fallback.md) | RAG + BM25 降级 |
| [ADR-003](adr/0003-model-gateway.md) | Model Gateway 与路由、成本控制 |
| [ADR-004](adr/0004-modular-monolith-first.md) | 先做模块化单体 |
| [ADR-005](adr/0005-tenancy-pii-and-tool-permissions.md) | 多租户、PII 与工具权限 |
| [ADR-006](adr/0006-trace-evaluation-and-regression.md) | Trace、评估与回归 |
| [ADR-007](adr/0007-fastapi-vertical-slice.md) | FastAPI 垂直切片 |
| [ADR-008](adr/0008-sqlite-first-persistence.md) | SQLite 优先持久化 |
| [ADR-009](adr/0009-api-auth-and-tool-permissions.md) | API 鉴权与工具权限 |
| [ADR-010](adr/0010-sse-event-streaming.md) | SSE 事件流 |
| [ADR-011](adr/0011-golden-dataset-and-retrieval-metrics.md) | 黄金数据集与检索指标 |
| [ADR-012](adr/0012-model-routing-budgets-and-telemetry.md) | 模型路由、预算与遥测 |
| [ADR-013](adr/0013-tool-execution-runtime.md) | 工具执行运行时 |
| [ADR-014](adr/0014-versioned-scenario-registry.md) | 版本化场景注册表 |
| [ADR-015](adr/0015-job-description-resume-matching.md) | JD 与简历匹配 |
| [ADR-016](adr/0016-structured-report-and-growth-loop.md) | 结构化报告与成长闭环 |
| [ADR-017](adr/0017-minimal-read-only-control-plane.md) | 最小只读控制面 |

## 维护约定

- 当前实现以 `architecture.md`、`interview-engine.md`、`evaluation.md` 和 `operations.md` 为准。
- 历史背景和取舍写入 ADR；ADR 不随功能迭代反复改写，需要变更时新增后续 ADR。
- 面向用户的行为变化同步更新 `product/user-guide.md`。
- 截图、GIF 和示例数据从 `demo/` 维护，不把真实简历、录音或面试记录提交到仓库。
- 删除或合并文档时同步更新本索引、根 README 和代码内链接。
