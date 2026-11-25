# Admin Console

Enable with:

```bash
admin_mode=true streamlit run app.py
```

The console is read-only and includes:

- scenario catalog;
- model profiles, retry and pricing metadata;
- provider circuit-breaker policy;
- tenant quota configuration and usage snapshot;
- tool permissions and schema availability;
- recent AgentRuns and event traces;
- RAG retrieval and quality-calibration metrics.

When `admin_mode` is false, the admin option is omitted and direct access redirects to the candidate dashboard.
