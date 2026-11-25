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

## 当前代码边界

当前为单文件 MVP，主要逻辑包括：

- 面试配置和阶段计划。
- 状态机与追问决策。
- 简历解析和检索。
- LLM、ASR、TTS 调用。
- Streamlit 页面。
- 本地存储和 Markdown 导出。

## 目标模块边界

```text
app.py
interview_loop/
  config.py
  core/
    flow.py
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
  ui/
    pages.py
```

重构原则：

1. 纯业务逻辑不依赖 Streamlit。
2. 第三方服务不直接操作页面。
3. 存储层可替换为数据库或对象存储。
4. Markdown 导出保持纯函数，便于测试。