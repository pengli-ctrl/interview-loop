from dataclasses import dataclass


@dataclass(frozen=True)
class RubricDimension:
    name: str
    weight: float


def weighted_score(scores: dict[str, float], dimensions: list[RubricDimension]) -> float:
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
