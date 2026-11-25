"""测试模块，覆盖评估相关行为和回归场景。"""
import json
from pathlib import Path

from interview_loop.evaluation.retrieval import (
    RetrievalCase,
    evaluate_case,
    evaluate_retrieval,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from interview_loop.evaluation.rubric import RubricDimension, weighted_score


def test_precision_at_k():
    """验证 Precision@K 计算。"""
    assert precision_at_k(["a", "x", "b"], ["a", "b"], 3) == 2 / 3


def test_recall_at_k():
    """验证 Recall@K 计算。"""
    assert recall_at_k(["a", "x"], ["a", "b"], 2) == 0.5


def test_reciprocal_rank():
    """验证倒数排名计算。"""
    assert reciprocal_rank(["x", "a"], ["a"]) == 0.5


def test_evaluate_case_hit_rate():
    """验证单条评估用例的命中率。"""
    result = evaluate_case(lambda query, k: ["x", "a"], RetrievalCase("q", ["a"]), k=2)
    assert result.metrics.hit_rate == 1.0


def test_evaluate_retrieval_aggregate():
    """验证评估检索汇总。"""
    cases = [RetrievalCase("q1", ["a"]), RetrievalCase("q2", ["b"])]
    report = evaluate_retrieval(lambda query, k: ["a"] if query == "q1" else ["x"], cases, k=1)
    assert report.hit_rate == 0.5
    assert report.mrr == 0.5


def test_weighted_score():
    """验证加权评分。"""
    dimensions = [RubricDimension("depth", 0.5), RubricDimension("communication", 0.5)]
    assert weighted_score({"depth": 8, "communication": 6}, dimensions) == 7.0


def test_golden_dataset_is_consistent():
    """验证黄金数据集判断一致。"""
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "datasets" / "rag_golden.json").read_text(encoding="utf-8"))
    document_ids = {document["id"] for document in data["documents"]}
    case_ids = {item for case in data["cases"] for item in case["relevant_ids"]}
    assert data["cases"]
    assert case_ids <= document_ids
