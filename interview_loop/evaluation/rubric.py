"""Rubric 模块，负责评分维度与权重加权计算。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RubricDimension:
    """评分维度及权重。"""
    name: str
    weight: float


def weighted_score(scores: dict[str, float], dimensions: list[RubricDimension]) -> float:
    """按权重计算综合得分。

    Args:
        scores: `scores` 输入参数，类型为 dict[str, float]。
        dimensions: `dimensions` 输入参数，类型为 list[RubricDimension]。

    Returns:
        函数处理结果，类型为 float。

    """
    if not dimensions:
        return 0.0
    total_weight = sum(max(0.0, dimension.weight) for dimension in dimensions)
    if total_weight <= 0:
        return 0.0
    total = sum(
        max(0.0, min(10.0, float(scores.get(dimension.name, 0))))
        * max(0.0, dimension.weight)
        for dimension in dimensions
    )
    return total / total_weight
