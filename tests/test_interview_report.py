from interview_loop.evaluation.interview_report import (
    InterviewReport,
    build_interview_report,
    build_progress_records,
    compare_weak_areas,
)
from interview_loop.scenarios import RubricDimensionSpec


def _rubric():
    return [
        RubricDimensionSpec("technical_depth", 0.35),
        RubricDimensionSpec("problem_solving", 0.25),
        RubricDimensionSpec("architecture", 0.25),
        RubricDimensionSpec("communication", 0.15),
    ]


def _strong_messages():
    answer = (
        "首先说明背景和目标，然后分析问题原因。我们设计了分层架构和缓存模块，"
        "通过限流与容灾应对高并发，最后延迟下降 30%，错误率下降 20%。"
    )
    return [
        {"role": "interviewer", "content": "请介绍项目架构"},
        {"role": "candidate", "content": answer},
    ]


def test_structured_report_contains_scores_evidence_and_actions():
    report = build_interview_report(
        _strong_messages(),
        _rubric(),
        tags=["架构设计"],
        job_match={"missing_skills": ["Kubernetes"]},
    )
    assert 0 <= report.overall_score <= 10
    assert report.source == "structure-heuristic-v1"
    assert "表达结构参考分" in report.summary
    assert "启发式" in report.summary
    assert len(report.dimensions) == 4
    assert sum(item.weight for item in report.dimensions) == 1.0
    assert report.strengths
    assert report.risks
    assert len(report.action_plan) >= 2
    assert report.evidence[0].answer_excerpt


def test_strong_answer_scores_higher_than_vague_answer():
    strong = build_interview_report(_strong_messages(), _rubric())
    vague_messages = [
        {"role": "interviewer", "content": "请介绍项目架构"},
        {"role": "candidate", "content": "不知道，没做过。"},
    ]
    vague = build_interview_report(vague_messages, _rubric())
    assert strong.overall_score > vague.overall_score
    assert "暂无明显优势" in vague.strengths[0]
    assert not any("可复用的方法" in item for item in vague.strengths)


def test_report_roundtrip():
    report = build_interview_report(_strong_messages(), _rubric())
    restored = InterviewReport.from_dict(report.to_dict())
    assert restored == report


def test_progress_records_sort_and_skip_old_sessions():
    sessions = [
        {"started_at": "2026-02-01", "mode": "技术一面", "structured_report": {"overall_score": 6.0}, "tags": []},
        {"started_at": "2026-01-01", "mode": "技术一面", "structured_report": {"overall_score": 5.0}, "tags": []},
        {"started_at": "2026-03-01", "mode": "技术一面", "feedback": "old", "tags": []},
        {"started_at": "2026-01-15", "mode": "HR面", "structured_report": {"overall_score": 7.0}, "tags": []},
    ]
    records = build_progress_records(sessions, mode="技术一面")
    assert [item.overall_score for item in records] == [5.0, 6.0]


def test_compare_weak_areas():
    change = compare_weak_areas(["RAG", "系统设计"], ["RAG", "Temporal"])
    assert change.new_areas == ("系统设计",)
    assert change.resolved_areas == ("Temporal",)
    assert change.persistent_areas == ("RAG",)
