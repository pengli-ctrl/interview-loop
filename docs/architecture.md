# 架构说明

## 1. 定位

InterviewLoop 是一个面向技术岗位的 AI 面试训练系统。架构目标不是构建完全自主 Agent，而是把大模型能力放进可控、可观测、可评估的确定性面试工作流中。

当前采用**模块化单体 + 独立 API 切片**：

- Streamlit 提供候选人产品界面和本地只读控制台。
- FastAPI 提供场景、岗位匹配、AgentRun、工具执行、指标和 SSE 事件接口。
- 核心业务逻辑与模型、语音、存储、导出实现解耦。
- 本地优先使用 SQLite 和文件存储，避免在需求尚未验证时引入分布式基础设施。

## 2. 系统上下文

```text
候选人
  │
  ▼
Streamlit UI ───────────────┐
  │                         │
  ├── 面试状态机            ├── FastAPI /v1/*
  ├── 简历解析与检索        │     ├── 场景查询
  ├── JD/简历匹配           │     ├── 岗位匹配
  ├── 文本/语音作答         │     ├── AgentRun
  └── 报告与成长记录        │     └── 指标 / SSE
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
       DeepSeek 兼容模型             火山引擎 ASR/TTS
              │                           │
              └─────────────┬─────────────┘
                            ▼
             会话文件 / Markdown / SQLite
```

外部 Provider 只通过 `interview_loop/services/` 和 `interview_loop/platform/` 访问。核心流程在 Demo 模式下不依赖真实网络调用。

## 3. 模块边界

| 目录 | 职责 | 关键约束 |
|---|---|---|
| `app.py` | Streamlit 五视图产品壳、会话状态和用例编排 | 不承载可复用领域算法 |
| `interview_loop/core/` | 状态机、追问判定、问题生成、复盘、岗位匹配 | 纯逻辑优先，可 pytest |
| `interview_loop/scenarios/` | 场景模型、JSON 配置包、校验和注册表 | UI 与 API 共用同一配置 |
| `interview_loop/services/` | LLM、ASR、TTS Provider 适配 | 不直接操作页面或数据库 |
| `interview_loop/rag/` | 简历文本抽取、切分、BM25/向量检索 | 向量不可用时自动降级 |
| `interview_loop/storage/` | 会话、统计和租户路径持久化 | 可替换为数据库实现 |
| `interview_loop/export/` | Markdown 面试记录生成 | 纯函数、可测试 |
| `interview_loop/evaluation/` | 检索指标、Rubric、质量校准、Trace Replay、Agent 指标 | 不调用真实模型即可回归 |
| `interview_loop/platform/` | AgentRun、Model Gateway、工具注册与执行、配额和审计 | 受权限、预算和超时约束 |
| `interview_loop/api/` | FastAPI 路由、鉴权和请求模型 | 垂直切片，不复制核心逻辑 |
| `interview_loop/admin/` | 控制台只读数据聚合 | 不修改生产数据 |

详细模块清单可查看仓库中的 `interview_loop/` 目录。关键决策见 [ADR 索引](README.md#adr-索引)。

## 4. 一次面试的运行链路

```text
选择轮次/模式/风格
  → 读取版本化场景配置
  → 可选：解析 JD 与简历，计算技能匹配
  → 创建 AgentRun
  → 状态机生成当前阶段主问题
  → 候选人使用语音或文字回答
  → 追问判定 / 下一个主问题 / 下一阶段
  → 全部阶段完成或手动结束
  → 确定性结构化报告 + 模型复盘
  → 保存 JSON 会话与 Markdown 记录
  → 更新弱项统计和成长趋势
```

状态机的输入输出、题目计划数量和追问规则详见 [面试引擎](interview-engine.md)。

## 5. 数据与存储

| 数据 | 默认位置 | 说明 |
|---|---|---|
| 会话 JSON | `interview_sessions/` | 每次面试的轮次、阶段、问答和报告 |
| Markdown 记录 | `面试记录/` | 可下载的完整训练记录 |
| 弱项统计 | `weak_stats_mode.json` | 按面试轮次聚合薄弱标签 |
| AgentRun | `interview_loop.db` 或 `INTERVIEWLOOP_DB_PATH` | SQLite 中的 Run、事件、幂等和审计数据 |
| 演示隔离数据 | `demo/.capture/` | 捕获脚本专用，不进入版本控制 |

运行时目录默认被 `.gitignore` 排除。演示捕获会重定向会话、记录和弱项统计路径，并使用独立 SQLite 数据库，不会污染真实训练数据。

## 6. 部署形态

### 本地开发

- Streamlit：`python -m streamlit run app.py`
- API：`uvicorn interview_loop.api.main:app --reload`
- Demo：设置 `demo_mode=true`，无需真实 API Key。

### Docker Compose

- `interview-loop`：8501，候选人界面。
- `interview-loop-api`：8000，Agent API。
- 会话、面试记录和 SQLite 通过 volume 持久化。

### 公测阶段

当前实现仍属于本地优先的模块化单体。公测前至少需要补齐：

- 正式账号体系与租户权限；
- PostgreSQL、对象存储、迁移和备份；
- 限流、配额、审计、监控和告警；
- 数据保留、删除、导出与隐私合规；
- 内容安全和场景质量治理。

这里只定义必要演进方向，不提前拆微服务。具体门槛见 [产品路线图](product/roadmap.md)。

## 7. 质量属性

- **可控性**：阶段和题目预算由配置决定，模型不能任意跳阶段。
- **可降级**：向量模型不可用时回退 BM25；Demo 模式不依赖外部 Provider。
- **可测试**：状态机、评分、导出、权限、工具运行时和 API 均有 pytest 覆盖。
- **可观测**：AgentRun 记录模型、工具、阶段、错误和耗时事件。
- **成本可控**：模型网关支持路由、重试、熔断、单轮预算和租户额度。
- **隐私优先**：显式同意、PII 脱敏、保留策略、导出和删除均有实现边界。

## 8. 非目标

当前架构不追求：

- 完全自主、无阶段约束的面试 Agent；
- 一开始拆分微服务或引入消息队列；
- 在未验证需求前建设复杂计费系统；
- 使用单一模型评分替代全部确定性规则；
- 把公开演示实例当作生产级招聘决策系统。

相关取舍记录在 [架构决策记录](adr/) 中。
