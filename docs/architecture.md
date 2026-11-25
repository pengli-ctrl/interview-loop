# Architecture

## 当前架构

```text
                    ┌─────────────────────┐
                    │     Streamlit UI    │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼─────────┐ ┌────────▼────────┐ ┌─────────▼─────────┐
│ Interview Flow    │ │ Resume / RAG    │ │ Answer Input       │
│ State Machine     │ │ Parser          │ │ Voice / Text       │
└─────────┬─────────┘ └────────┬────────┘ └─────────┬─────────┘
          │                    │                    │
          └──────────────┬─────┴──────────┬─────────┘
                         │                │
                ┌────────▼───────┐ ┌──────▼─────────┐
                │ LLM Service    │ │ ASR / TTS      │
                │ DeepSeek       │ │ Volcengine     │
                └────────┬───────┘ └──────┬─────────┘
                         │                │
                ┌────────▼────────────────▼────────┐
                │ Review / Tags / Weak Stats        │
                └────────────────┬─────────────────┘
                                 │
                ┌────────────────▼─────────────────┐
                │ JSON Session + Markdown Export   │
                └──────────────────────────────────┘
```

## 当前模块结构

```text
app.py
interview_loop/
  config.py
  scenarios/
    models.py
    registry.py
    packs/
  core/
    flow.py
    job_match.py
    question_engine.py
    review.py
  services/
    common.py
    llm.py
    asr.py
    tts.py
    speech_common.py
  rag/
    resume.py
    retriever.py
    text.py
  storage/
    common.py
    session_store.py
    stats_store.py
  export/
    markdown.py
  evaluation/
    interview_report.py
    retrieval.py
    quality.py
    replay.py
    agent_metrics.py
  platform/
    agent_run.py
    builtin_tools.py
    model_gateway.py
    run_repository.py
    tool_registry.py
  api/
    main.py
  admin/
    control_plane.py
```

模块边界原则：

1. `core` 负责可测试的纯业务逻辑。
2. `services` 负责第三方 API 适配。
3. `rag` 负责简历解析和检索。
4. `storage` 负责会话和统计持久化。
5. `export` 负责 Markdown 生成。
6. `scenarios` 负责版本化场景模型、配置包、校验和注册表。
7. `platform` 负责 AgentRun、ModelGateway 和 ToolRegistry；模型网关支持重试、Provider 回退、预算控制与调用事件，工具运行层负责超时、幂等、权限与审计。
8. `app.py` 负责 Streamlit UI 和 session state 编排。
9. 纯逻辑模块不依赖真实网络调用，便于 pytest 和 CI。

## 后续演进方向

```text
app.py
interview_loop/
  config.py
  core/
    flow.py
    job_match.py
    question_engine.py
    review.py
  services/
    llm.py
    asr.py
    tts.py
  rag/
    resume.py
    retriever.py
  storage/
    session_store.py
    stats_store.py
  export/
    markdown.py
  evaluation/
    interview_report.py
    retrieval.py
    quality.py
    replay.py
    agent_metrics.py
  ui/
    pages.py
```

重构原则：

1. 纯业务逻辑不依赖 Streamlit。
2. 第三方服务不直接操作页面。
3. 存储层可替换为数据库或对象存储。
4. Markdown 导出保持纯函数，便于测试。