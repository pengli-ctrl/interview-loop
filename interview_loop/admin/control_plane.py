"""只读平台控制面模块，负责场景、模型、工具、Run、配额和评估数据的查询与格式化。"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from interview_loop.evaluation.quality import evaluate_quality


def scenario_rows(registry) -> list[dict]:
    """把场景注册表转换为控制台表格行。

    Args:
        registry: `registry` 输入参数，类型为 未标注。

    Returns:
        函数处理结果，类型为 list[dict]。

    """
    return [
        {
            "ID": item.id,
            "轮次": item.interview_round,
            "岗位族": item.job_family,
            "岗位": item.role,
            "职级": item.seniority,
            "语言": item.language,
            "时长": item.duration_minutes,
            "阶段数": len(item.stages),
            "题目数": sum(len(stage.question_plan) for stage in item.stages),
            "默认风格": item.default_style,
        }
        for item in registry.list_scenarios()
    ]


def tool_rows(registry) -> list[dict]:
    """把工具注册表转换为控制台表格行。

    Args:
        registry: `registry` 输入参数，类型为 未标注。

    Returns:
        函数处理结果，类型为 list[dict]。

    """
    return [
        {
            "工具": item.name,
            "版本": item.version,
            "权限": item.required_permission or "-",
            "超时秒": item.timeout_seconds,
            "幂等": item.idempotent,
            "最大重试": item.max_retries,
            "输入Schema": bool(item.input_schema),
            "输出Schema": bool(item.output_schema),
        }
        for item in registry.list_tools()
    ]


def model_profile_rows(gateway) -> list[dict]:
    """把模型路由配置转换为表格行。

    Args:
        gateway: `gateway` 输入参数，类型为 未标注。

    Returns:
        函数处理结果，类型为 list[dict]。

    """
    rows = []
    for task in ("question", "tagging", "review"):
        for profile in gateway.profiles_for(task):
            rows.append(
                {
                    "任务": task,
                    "Provider": profile.provider,
                    "模型": profile.model,
                    "Prompt版本": profile.prompt_version,
                    "最大重试": profile.max_retries,
                    "输入单价/百万": profile.input_cost_per_million,
                    "输出单价/百万": profile.output_cost_per_million,
                }
            )
    return rows


def recent_runs(repository, limit: int = 20):
    """按更新时间倒序返回最近 AgentRun。

    Args:
        repository: `repository` 输入参数，类型为 未标注。
        limit: `limit` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 未标注。

    """
    runs = repository.list()
    return sorted(runs, key=lambda run: run.updated_at, reverse=True)[:limit]


def run_rows(runs) -> list[dict]:
    """把 AgentRun 转换为控制台表格行。

    Args:
        runs: `runs` 输入参数，类型为 未标注。

    Returns:
        函数处理结果，类型为 list[dict]。

    """
    return [
        {
            "Run": run.run_id,
            "租户": run.tenant_id,
            "用户": run.user_id,
            "状态": run.status.value,
            "当前节点": run.current_node,
            "事件数": len(run.events),
            "更新时间": format_local_time(run.updated_at),
        }
        for run in runs
    ]


def recent_run_rows(repository, limit: int = 20) -> list[dict]:
    """返回最近 AgentRun 的表格行。

    Args:
        repository: `repository` 输入参数，类型为 未标注。
        limit: `limit` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 list[dict]。

    """
    return run_rows(recent_runs(repository, limit))


def quality_metrics(path: str | Path) -> dict:
    """读取黄金集并计算质量校准指标。

    Args:
        path: `path` 输入参数，类型为 str | Path。

    Returns:
        函数处理结果，类型为 dict。

    """
    dataset = json.loads(Path(path).read_text(encoding="utf-8"))
    report = evaluate_quality(dataset)
    return {
        "case_count": report.case_count,
        "weighted_mae": report.weighted_mae,
        "max_case_mae": report.max_case_mae,
        "human_review_passed": report.human_review_passed,
        "passed": report.passed,
        "thresholds": report.thresholds,
    }


def format_rag_thresholds(thresholds: dict) -> str:
    """把 RAG 阈值格式化为可读文本。

    Args:
        thresholds: `thresholds` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 str。

    """
    return (
        f"Precision ≥ {float(thresholds.get('precision', 0)):.2f} · "
        f"Recall ≥ {float(thresholds.get('recall', 0)):.2f} · "
        f"MRR ≥ {float(thresholds.get('mrr', 0)):.2f} · "
        f"Hit Rate ≥ {float(thresholds.get('hit_rate', 0)):.2f}"
    )


def format_quality_thresholds(thresholds: dict) -> str:
    """把质量阈值格式化为可读文本。

    Args:
        thresholds: `thresholds` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 str。

    """
    return (
        f"加权 MAE ≤ {float(thresholds.get('weighted_mae', 0)):.2f} · "
        f"单条最大 MAE ≤ {float(thresholds.get('max_case_mae', 0)):.2f}"
    )


def format_quota_snapshot(snapshot: dict) -> str:
    """把租户用量快照格式化为可读文本。

    Args:
        snapshot: `snapshot` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 str。

    """
    return (
        f"{int(snapshot.get('used_tokens', 0)):,} / "
        f"{int(snapshot.get('max_tokens', 0)):,} Token · "
        f"¥{float(snapshot.get('used_cost', 0)):.4f} / "
        f"¥{float(snapshot.get('max_cost', 0)):.2f}"
    )


def format_local_time(value: str) -> str:
    """把 UTC 时间格式化为东八区时间。

    Args:
        value: `value` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
