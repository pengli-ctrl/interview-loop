# InterviewLoop

面向技术岗位的多轮自适应 AI 面试训练平台。它将简历、面试轮次、阶段状态机、动态追问、语音/文字作答、结构化复盘和完整记录导出连接成一个可重复训练、可回顾的闭环。

![InterviewLoop demo](demo/interview-loop.gif)

> 当前状态：MVP。核心面试流程、模块化结构、pytest 测试、GitHub Actions、Docker 运行方式、Mock Demo 和演示素材已经具备。

## 项目解决什么问题

传统面试准备通常依赖题库、面经或真人陪练：

- 题库缺少针对个人简历的上下文。
- 通用 AI 聊天缺少稳定的面试流程和阶段控制。
- 真人模拟面试成本高、难预约。
- 面试结束后缺少完整问答记录和可执行的复盘。

InterviewLoop 将一次技术面试拆成轮次、阶段、主问题、追问和时间预算，并在面试完成后自动生成复盘和 Markdown 记录。

## 核心功能

- 4 个面试轮次：技术一面、技术二面、技术三面、HR 面。
- 每轮独立 6 阶段流程，支持主问题、动态追问和时间预算。
- 默认 60 分钟面试，倒计时自动刷新。
- 支持 TXT、Markdown、PDF 简历解析。
- 简历 RAG：本地向量模型可用时使用 FAISS + BM25，否则自动回退 BM25。
- 支持语音回答和文字回答二选一。
- ASR/TTS 接入火山引擎新版豆包语音。
- 大模型接入 DeepSeek OpenAI 兼容接口。
- 重复问题检测和阶段约束。
- 面试结束生成复盘、薄弱标签和完整 Markdown 记录。
- 支持历史记录、弱项统计、跳过阶段和开启新一轮。

## 面试流程

```text
选择轮次和风格
  → 上传简历（可选）
  → 开始 60 分钟面试
  → 当前阶段生成主问题
  → 语音或文字作答
  → 根据回答决定是否追问
  → 主问题完成
  → 阶段完成
  → 生成复盘
  → 保存 JSON + Markdown
```

详细流程见 [docs/interview-flow.md](docs/interview-flow.md)。

## 技术架构

```text
Streamlit UI
  ├── Interview State Machine
  ├── Resume Parser + RAG
  ├── DeepSeek Question / Review Service
  ├── Volcengine ASR / TTS
  ├── Session & Weakness Storage
  └── Markdown Record Export
```

详细说明见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置凭证

复制配置模板：

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

然后填写：

- `deepseek_api_key`
- `volc_api_key` 或 `volc_appid` + `volc_token`
- `volc_tts_resource_id`
- `volc_asr_resource_id`
- `volc_voice_type`

也可以使用 `.env.example` 中的同名环境变量。

### 4. 启动应用

```bash
streamlit run app.py
```

浏览器访问：

```text
http://localhost:8501
```

## 配置说明

| 配置 | 用途 |
|---|---|
| `deepseek_api_key` | 大模型出题与复盘 |
| `deepseek_base_url` | OpenAI 兼容接口地址 |
| `deepseek_model` | 模型名称 |
| `volc_api_key` | 新版豆包语音 API Key 单头模式 |
| `volc_appid` / `volc_token` | AppID + AccessToken 双头模式 |
| `volc_tts_resource_id` | TTS 资源版本 |
| `volc_asr_resource_id` | ASR 资源版本 |
| `volc_voice_type` | 发音人 / 音色 ID |

## 本地数据

运行时会生成：

- `interview_sessions/`：JSON 会话数据。
- `面试记录/`：Markdown 完整面试记录。
- `weak_stats_mode.json`：分轮次弱项统计。

这些文件已默认加入 `.gitignore`，不应提交到公开仓库。

## Architecture Decisions

- [ADR-001: Deterministic workflow](docs/adr/0001-deterministic-workflow-vs-autonomous-agent.md)
- [ADR-002: Hybrid RAG with BM25 fallback](docs/adr/0002-hybrid-rag-with-bm25-fallback.md)
- [ADR-003: Model Gateway](docs/adr/0003-model-gateway.md)
- [ADR-004: Modular monolith first](docs/adr/0004-modular-monolith-first.md)
- [ADR-005: Tenant isolation and tool permissions](docs/adr/0005-tenancy-pii-and-tool-permissions.md)
- [ADR-006: Trace, evaluation and regression](docs/adr/0006-trace-evaluation-and-regression.md)
- [ADR-007: FastAPI vertical slice](docs/adr/0007-fastapi-vertical-slice.md)

## 当前局限

- 当前是单机 MVP，没有账号和多租户数据隔离。
- 使用本地文件存储，不适合直接公开 SaaS 部署。
- 评估质量依赖大模型，尚缺少标准化评分基准。
- 没有支付、订阅、配额和滥用防护。
- 公开在线 Demo 会产生第三方 API 成本，因此仓库优先提供本地运行和录屏演示。

## Roadmap

- [x] 拆分 `core`、`services`、`rag`、`storage` 和 `export` 模块。
- [x] 增加 pytest 纯逻辑测试和 GitHub Actions。
- [x] 增加 Dockerfile 和环境变量模板。
- [x] 增加 Mock Demo 模式。
- [x] 增加演示截图和流程 GIF。
- [ ] 建立标准评分 Rubric 和评估基准集。
- [ ] 增加账号、数据库、对象存储和用户数据隔离。
- [ ] 增加公测所需的配额、限流、监控和隐私合规能力。

## 免责声明

本项目用于技术面试训练和模拟，不构成真实招聘决策、职业建议或录用承诺。请勿提交真实简历、录音或面试记录到公开仓库。

## 测试

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q
```

当前测试覆盖状态机、追问判定、问题相似度、复盘标签、Markdown 导出、会话存储、弱项统计和简历编码解析。

## Demo 模式

无需任何 API Key 即可运行完整面试流程：

```bash
demo_mode=true streamlit run app.py
```

Windows PowerShell:

```powershell
$env:demo_mode="true"
streamlit run app.py
```

演示模式会使用固定题目、固定复盘和语音占位数据，不会调用真实模型或语音接口。

## Agent API

启动 API：

```bash
uvicorn interview_loop.api.main:app --reload
```

接口：

- `GET /health`
- `GET /v1/tools`
- `POST /v1/agent-runs`
- `GET /v1/agent-runs/{run_id}`
- `POST /v1/agent-runs/{run_id}/start`
- `POST /v1/agent-runs/{run_id}/events`

OpenAPI 文档：`http://localhost:8000/docs`。

当前 Repository 为进程内实现，适合架构演示和本地开发；公测需要替换为 PostgreSQL。

## Docker 运行

先准备环境变量：

```bash
cp .env.example .env
```

填写 `.env` 后启动：

```bash
docker compose up --build
```

浏览器访问 `http://localhost:8501`。

Docker 不会打包 `.streamlit/secrets.toml`、真实面试记录或本地会话数据。运行时记录通过 volume 保存在宿主机。
