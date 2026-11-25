from dataclasses import dataclass, field

from interview_loop.evaluation.rubric import RubricDimension, weighted_score


@dataclass(frozen=True)
class QualityCaseResult:
    case_id: str
    human_weighted_score: float
    model_weighted_score: float
    weighted_error: float
    dimension_errors: dict[str, float]


@dataclass(frozen=True)
class QualityReport:
    case_count: int
    weighted_mae: float
    max_case_mae: float
    passed: bool
    human_review_metrics: dict = field(default_factory=dict)
    human_review_passed: bool = False
    thresholds: dict = field(default_factory=dict)
    cases: list[QualityCaseResult] = field(default_factory=list)


def evaluate_quality(dataset: dict) -> QualityReport:
    dimensions = [
        RubricDimension(item["name"], float(item["weight"]))
        for item in dataset.get("dimensions", [])
    ]
    cases = dataset.get("cases", [])
    thresholds = dataset.get("thresholds", {})
    results = []
    for case in cases:
        human_scores = case.get("human_scores", {})
        model_scores = case.get("model_scores", {})
        dimension_errors = {
            dimension.name: abs(
                float(human_scores.get(dimension.name, 0))
                - float(model_scores.get(dimension.name, 0))
            )
            for dimension in dimensions
        }
        human_weighted = weighted_score(human_scores, dimensions)
        model_weighted = weighted_score(model_scores, dimensions)
        results.append(
            QualityCaseResult(
                case_id=str(case["id"]),
                human_weighted_score=human_weighted,
                model_weighted_score=model_weighted,
                weighted_error=abs(human_weighted - model_weighted),
                dimension_errors=dimension_errors,
            )
        )

    if results:
        weighted_mae = sum(item.weighted_error for item in results) / len(results)
        max_case_mae = max(item.weighted_error for item in results)
    else:
        weighted_mae = 0.0
        max_case_mae = 0.0

    human_review_metrics = dataset.get("human_review_metrics", {})
    human_review_minimums = dataset.get("human_review_minimums", {})
    human_review_passed = all(
        float(human_review_metrics.get(name, 0)) >= float(minimum)
        for name, minimum in human_review_minimums.items()
    )
    passed = (
        weighted_mae <= float(thresholds.get("weighted_mae", 1.0))
        and max_case_mae <= float(thresholds.get("max_case_mae", 2.0))
        and human_review_passed
        and bool(cases)
    )
    return QualityReport(
        case_count=len(results),
        weighted_mae=weighted_mae,
        max_case_mae=max_case_mae,
        passed=passed,
        human_review_metrics=human_review_metrics,
        human_review_passed=human_review_passed,
        thresholds=thresholds,
        cases=results,
    )
