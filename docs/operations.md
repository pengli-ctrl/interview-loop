# 运维手册

## 1. 环境要求

- Python 3.10+
- Windows、macOS 或 Linux
- 可选：Docker / Docker Compose
- 真实模式需要 DeepSeek 兼容模型和火山引擎语音凭证
- 演示捕获需要 Chrome/Edge，或安装 Playwright Chromium

## 2. 本地启动

推荐使用独立虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app.py
```

浏览器访问 `http://localhost:8501`。

在 PowerShell 中请使用新行的命令，不要把 `& "python.exe" ...` 和行尾反斜杠拼成同一条命令。`&` 是 PowerShell 的调用运算符，不是命令分隔符。

## 3. 配置

复制模板：

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

也可以使用 `.env.example` 中的环境变量。

| 配置 | 必填 | 用途 |
|---|---|---|
| `deepseek_api_key` | 真实模式 | 大模型出题与复盘 |
| `deepseek_base_url` | 否 | OpenAI 兼容接口地址 |
| `deepseek_model` | 否 | 模型名称 |
| `volc_api_key` | 语音模式 | 火山引擎新版语音 API Key 单头模式 |
| `volc_appid` / `volc_token` | 语音模式 | AppID + AccessToken 双头模式 |
| `volc_tts_resource_id` | 否 | TTS 资源版本 |
| `volc_asr_resource_id` | 否 | ASR 资源版本 |
| `volc_voice_type` | 否 | 发音人与音色 ID |
| `demo_mode` | 否 | 使用固定题目和复盘，不调用真实 Provider |
| `admin_mode` | 否 | 显示本地只读平台控制台 |
| `INTERVIEWLOOP_API_KEY` | 公网 API | `/v1/*` 请求鉴权 |
| `INTERVIEWLOOP_DB_PATH` | 否 | AgentRun SQLite 文件路径 |

模型预算和租户额度配置见 `.env.example`。真实 Key 只放在本地 secrets 或部署环境变量中，不提交仓库。

## 4. Demo 模式

无需 API Key：

```powershell
$env:demo_mode="true"
python -m streamlit run app.py
```

Demo 模式使用固定题目、固定复盘和语音占位数据，适合 UI 展示、自动测试和回归验证。

## 5. 平台控制台

```powershell
$env:admin_mode="true"
python -m streamlit run app.py
```

控制台只读展示：

- 场景目录；
- 模型路由、熔断和预算；
- 工具权限与 Schema；
- 租户额度；
- 最近 AgentRun 与 Trace；
- RAG 检索指标；
- 模型评分质量校准。

未启用 `admin_mode` 时，候选导航不会显示管理入口。

## 6. 演示素材重新生成

安装开发依赖和浏览器：

```powershell
pip install -r requirements-dev.txt
python -m playwright install chromium
```

生成截图和 GIF：

```powershell
python scripts/capture_demo.py
```

脚本会：

- 使用 `scripts/demo_app.py` 启动隔离的 Demo 服务；
- 把数据库和会话写入 `demo/.capture/`；
- 在 8502 捕获候选人全流程；
- 在 8503 捕获管理控制台；
- 输出 `demo/screenshots/*.png` 和 `demo/interview-loop.gif`；
- 结束后停止服务，不修改真实训练数据。

如果本机已安装 Chrome 或 Edge，脚本会优先使用本机浏览器；`playwright install chromium` 仍是最可复现的选择。

## 7. Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

服务：

- 候选人界面：`http://localhost:8501`
- Agent API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`

Compose 使用 volume 持久化：

- `./interview_sessions` → 容器内会话；
- `./面试记录` → Markdown 记录；
- `./data` → API SQLite 数据。

Docker 镜像不会打包真实 secrets、面试记录或本地会话。

## 8. Agent API

启动：

```bash
uvicorn interview_loop.api.main:app --reload
```

主要接口：

| 类别 | 接口 |
|---|---|
| 健康检查 | `GET /health` |
| 场景 | `GET /v1/scenarios`、`GET /v1/scenarios/{scenario_id}` |
| 岗位匹配 | `POST /v1/job-match` |
| AgentRun | `POST /v1/agent-runs`、查询、启动、完成、失败、导出、删除 |
| 工具 | `GET /v1/tools`、`POST /v1/agent-runs/{run_id}/tools/{tool_name}` |
| 指标 | `GET /v1/metrics` |
| 事件流 | `GET /v1/agent-runs/{run_id}/events/stream`（SSE） |

启用 API Key 后，请求需要：

```text
X-API-Key: your-secret-key
X-Tenant-Id: tenant-a
X-User-Id: user-a
X-Permissions: record:write,audio:read
```

工具权限只从请求身份中读取，不能由请求体覆盖。不同租户不能访问对方的 AgentRun。

## 9. 数据目录与保留

| 路径 | 内容 | 是否入库 |
|---|---|---|
| `interview_sessions/` | 本地会话 JSON | 否 |
| `面试记录/` | Markdown 面试记录 | 否 |
| `weak_stats_mode.json` | 弱项统计 | 否 |
| `interview_loop.db` | 本地 AgentRun SQLite | 否 |
| `demo/.capture/` | 捕获脚本临时数据 | 否 |
| `datasets/` | 黄金测试数据 | 是 |

候选人开始面试前必须显式同意数据保存。支持 `ephemeral`、`standard`、`extended` 保留策略、PII 脱敏、导出和删除。

清理过期 AgentRun：

```bash
python scripts/purge_expired_runs.py
```

## 10. 健康检查与验证

```bash
ruff check .
pytest -q
python scripts/evaluate_rag.py
python scripts/evaluate_quality.py
```

Streamlit 健康检查：

```text
http://localhost:8501/_stcore/health
```

API 健康检查：

```bash
curl http://localhost:8000/health
```

## 11. 常见故障

### 端口被占用

```powershell
python -m streamlit run app.py --server.port 8502
```

或查找监听该端口的进程后关闭。

### PowerShell 报“此时不应有 &”

请单独执行 Python 命令，不要使用 Unix 风格的 `&` 或命令末尾反斜杠。推荐：

```powershell
python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats=false
```

### 向量模型不可用

系统会回退 BM25，不影响面试继续。若需要使用本地 FAISS 检索，预先准备 `all-MiniLM-L6-v2` 缓存。

### 语音服务失败

切换到“文字输入”即可继续。文字与语音共用同一套状态机和复盘逻辑。

### 控制台 404 或不可见

确认当前进程设置了 `admin_mode=true`，并重启 Streamlit。控制台默认关闭。

### 截图脚本找不到浏览器

执行：

```powershell
python -m playwright install chromium
```

然后重新运行 `python scripts/capture_demo.py`。

## 12. 公测前必须补齐

当前仓库适合本地使用、作品展示和受控演示，不应直接暴露为无保护的公共生产服务。上线前至少完成：

- 账号、租户和管理员权限；
- PostgreSQL 与对象存储；
- 公网域名、HTTPS 和备案；
- 限流、配额、监控、告警和备份；
- 隐私政策、数据删除和内容安全；
- Provider Key 托管与成本上限；
- 真实用户压测和故障演练。

具体范围与验收门槛见 [产品路线图](product/roadmap.md)。
