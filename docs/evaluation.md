# 评估体系

## 1. 为什么要评估

AI 面试系统同时包含检索、模型生成、流程控制、工具调用和评分。仅靠“看起来像面试”无法判断质量，因此项目把评估拆成四层：

1. 检索质量；
2. 面试报告与 Rubric；
3. 模型评分校准；
4. Agent 运行质量与 Trace 回归。

所有评估都优先使用确定性输入，CI 中不需要真实模型或语音 Key。

## 2. 检索评估

实现：`interview_loop/evaluation/retrieval.py`
脚本：`scripts/evaluate_rag.py`
黄金数据：`datasets/rag_golden.json`

指标：

- **Precision@K**：Top-K 中相关文档占比。
- **Recall@K**：相关文档被 Top-K 覆盖的比例。
- **MRR**：第一个相关结果排名的倒数。
- **Hit Rate**：Top-K 是否至少命中一个相关结果。

当前黄金集 `K=3`，回归阈值为：

| 指标 | 最低值 |
|---|---:|
| Precision | 0.30 |
| Recall | 0.90 |
| MRR | 0.90 |
| Hit Rate | 0.90 |

运行：

```bash
python scripts/evaluate_rag.py
```

该脚本使用 BM25 作为稳定基线，验证降级链路和指标工具，不代表生产向量模型在所有真实简历上的表现。

## 3. 结构化报告与 Rubric

实现：

- `interview_loop/evaluation/rubric.py`
- `interview_loop/evaluation/interview_report.py`

报告由确定性逻辑和评分维度共同生成，包含：

- 综合得分；
- 各维度得分与权重；
- 基于回答的证据摘录；
- 优势；
- 风险与不足；
- 按优先级排序的行动计划；
- 与 JD 匹配结果关联的补强重点。

示例维度包括：

| 维度 | 示例权重 |
|---|---:|
| 架构深度 | 30% |
| 实现细节 | 25% |
| 权衡推理 | 25% |
| 沟通表达 | 20% |

不同面试轮次使用不同 Rubric，具体以场景配置为准。旧版记录缺少结构化报告时可以正常读取，但不会参与新趋势计算。

## 4. 质量校准

实现：`interview_loop/evaluation/quality.py`
脚本：`scripts/evaluate_quality.py`
黄金数据：`datasets/quality_golden.json`

质量校准比较人工评分与模型评分：

- 加权平均绝对误差 `weighted_mae`；
- 单条最大误差 `max_case_mae`；
- 追问相关性和报告可执行性的人工评审最低值。

当前门禁：

| 项目 | 阈值 |
|---|---:|
| 加权 MAE | ≤ 0.75 |
| 单条最大 MAE | ≤ 1.00 |
| 追问相关性 | ≥ 0.80 |
| 报告可执行性 | ≥ 0.75 |

运行：

```bash
python scripts/evaluate_quality.py
```

黄金集目前用于锁定评分计算和回归行为，不应被理解为已完成大规模真实用户校准。公测阶段需要持续补充匿名化、人工双评的样本。

## 5. AgentRun 指标

实现：`interview_loop/evaluation/agent_metrics.py`

指标包括：

- 运行数、完成数、失败数和失败率；
- 模型调用数与工具调用数；
- 延迟 P50 / P95；
- 输入/输出 Token 与估算成本；
- 模型和工具重试率；
- 问题生成数；
- 重复问题率；
- 阶段约束遵守率。

候选人 UI 不直接展示这些内部指标；本地只读控制台和 `GET /v1/metrics` 可查看当前租户汇总。

## 6. Trace Replay

实现：`interview_loop/evaluation/replay.py`

Trace Replay 从 AgentRun 导出数据重建阶段顺序、问题和完成事件，不调用模型或工具 Provider。它适合：

- 定位问题在哪个阶段重复；
- 检查是否提前跨阶段；
- 复盘模型或工具失败链路；
- 在 CI 或本地重放回归样本。

## 7. 测试门禁

当前完整测试包含 126+ 个 pytest 用例，覆盖：

- 场景配置；
- 状态机与追问；
- 问题相似度；
- JD/简历匹配；
- 结构化报告与成长趋势；
- Markdown 导出；
- 会话和统计存储；
- 模型路由、熔断与额度；
- 工具超时、幂等、Schema、权限与审计；
- PII、保留和删除；
- API 鉴权与 SSE；
- 控制台访问控制；
- Streamlit 全流程。

CI 依次执行：

```bash
ruff check .
pytest -q
python scripts/evaluate_rag.py
python scripts/evaluate_quality.py
```

## 8. 当前局限

- 黄金集规模仍然较小，主要用于回归而非统计显著性评估。
- 评分仍需要更多真实面试样本和人工双评校准。
- 当前没有线上 A/B 实验平台和多模型自动评测队列。
- Demo 模式和真实 Provider 模式的质量结果应分开统计。
