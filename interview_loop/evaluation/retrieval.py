"""检索评估模块，负责 Precision、Recall、MRR 和 Hit Rate 计算。"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class RetrievalCase:
    """单条检索评估用例。"""
    query: str
    relevant_ids: list[str]


@dataclass(frozen=True)
class RetrievalMetrics:
    """检索评估指标。"""
    precision: float
    recall: float
    mrr: float
    hit_rate: float


@dataclass(frozen=True)
class CaseResult:
    """单条检索用例结果。"""
    query: str
    retrieved_ids: list[str]
    metrics: RetrievalMetrics


@dataclass(frozen=True)
class EvaluationReport:
    """检索评估汇总报告。"""
    k: int
    precision: float
    recall: float
    mrr: float
    hit_rate: float
    cases: list[CaseResult] = field(default_factory=list)


SearchFn = Callable[[str, int], list[str]]


def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """计算 Precision@K。

    Args:
        retrieved_ids: `retrieved_ids` 输入参数，类型为 list[str]。
        relevant_ids: `relevant_ids` 输入参数，类型为 list[str]。
        k: `k` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 float。

    """
    if k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    relevant = set(relevant_ids)
    return sum(item in relevant for item in top_k) / len(top_k)


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """计算 Recall@K。

    Args:
        retrieved_ids: `retrieved_ids` 输入参数，类型为 list[str]。
        relevant_ids: `relevant_ids` 输入参数，类型为 list[str]。
        k: `k` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 float。

    """
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """计算倒数排名。

    Args:
        retrieved_ids: `retrieved_ids` 输入参数，类型为 list[str]。
        relevant_ids: `relevant_ids` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 float。

    """
    relevant = set(relevant_ids)
    for index, item in enumerate(retrieved_ids, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def evaluate_case(search_fn: SearchFn, case: RetrievalCase, k: int = 3) -> CaseResult:
    """评估单条检索用例。

    Args:
        search_fn: `search_fn` 输入参数，类型为 SearchFn。
        case: `case` 输入参数，类型为 RetrievalCase。
        k: `k` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 CaseResult。

    """
    retrieved_ids = search_fn(case.query, k)
    return CaseResult(
        query=case.query,
        retrieved_ids=retrieved_ids,
        metrics=RetrievalMetrics(
            precision=precision_at_k(retrieved_ids, case.relevant_ids, k),
            recall=recall_at_k(retrieved_ids, case.relevant_ids, k),
            mrr=reciprocal_rank(retrieved_ids, case.relevant_ids),
            hit_rate=1.0 if set(retrieved_ids[:k]) & set(case.relevant_ids) else 0.0,
        ),
    )


def evaluate_retrieval(
    search_fn: SearchFn,
    cases: list[RetrievalCase],
    k: int = 3,
) -> EvaluationReport:
    """汇总检索评估指标。

    Args:
        search_fn: `search_fn` 输入参数，类型为 SearchFn。
        cases: `cases` 输入参数，类型为 list[RetrievalCase]。
        k: `k` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 EvaluationReport。

    """
    results = [evaluate_case(search_fn, case, k) for case in cases]
    if not results:
        return EvaluationReport(k=k, precision=0, recall=0, mrr=0, hit_rate=0)
    count = len(results)
    return EvaluationReport(
        k=k,
        precision=sum(result.metrics.precision for result in results) / count,
        recall=sum(result.metrics.recall for result in results) / count,
        mrr=sum(result.metrics.mrr for result in results) / count,
        hit_rate=sum(result.metrics.hit_rate for result in results) / count,
        cases=results,
    )
