"""测试模块，覆盖岗位匹配相关行为和回归场景。"""
import pytest

from interview_loop.core.job_match import (
    JobDescriptionError,
    JobMatchReport,
    assess_job_match,
    build_job_context,
    extract_skills,
    load_default_skill_catalog,
    validate_job_description,
)


@pytest.fixture(scope="module")
def catalog():
    """加载默认技能目录测试夹具。

    Returns:
        函数处理结果，类型为 未标注。

    """
    return load_default_skill_catalog()


def test_skill_catalog_loads(catalog):
    """验证技能目录加载。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    assert catalog.version == "1.0"
    assert len(catalog.skills) >= 40


def test_extract_skills_respects_aliases_and_word_boundaries(catalog):
    """验证提取技能遵守别名和词边界。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    skills = extract_skills("使用 Python、FastAPI、K8s 和检索增强构建服务", catalog)
    assert {"Python", "FastAPI", "Kubernetes", "RAG"} <= set(skills)
    assert "Go" not in extract_skills("Google Cloud platform", catalog)


def test_good_match(catalog):
    """验证正常匹配。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    jd = "负责 Python FastAPI Redis RAG 服务开发，要求具备可观测性和分布式系统经验。"
    resume = "使用 Python FastAPI 构建 RAG 服务，接入 Redis 和 OpenTelemetry，具备可观测性和分布式系统经验，请求延迟下降 30%。"
    report = assess_job_match(jd, resume, catalog)
    assert report.match_level == "good"
    assert report.match_score >= 70
    assert {"Python", "FastAPI", "Redis", "RAG"} <= set(report.matched_skills)
    assert report.suggested_focus


def test_partial_match(catalog):
    """验证部分匹配。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    jd = "岗位要求 Python FastAPI Redis Kubernetes RAG 和可观测性经验。"
    resume = "使用 Python FastAPI Redis 开发业务服务，并完成性能优化。"
    report = assess_job_match(jd, resume, catalog)
    assert report.match_level == "partial"
    assert 40 <= report.match_score < 70
    assert "Kubernetes" in report.missing_skills
    assert "RAG" in report.missing_skills
    assert any("缺少岗位技能证据" in risk for risk in report.risk_areas)


def test_poor_match_without_resume(catalog):
    """验证较差匹配缺少简历。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    jd = "岗位要求 Java Spring Boot MySQL Kafka Kubernetes 和系统设计经验。"
    report = assess_job_match(jd, "", catalog)
    assert report.match_level == "poor"
    assert report.match_score == 0
    assert report.missing_skills
    assert any("尚未提供简历" in risk for risk in report.risk_areas)


def test_short_job_description_is_rejected(catalog):
    """验证短岗位描述判断被拒绝。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    with pytest.raises(JobDescriptionError, match="过短"):
        validate_job_description("招 Python 工程师", catalog)


def test_job_description_outside_catalog_is_marked_unscored(catalog):
    """验证岗位描述目录外目录判断标记未评分。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    jd = "负责团队日常沟通、项目协调和业务运营工作，需要良好的表达能力、跨部门协作意识和长期规划能力。"
    assert validate_job_description(jd, catalog) == jd
    report = assess_job_match(jd, "", catalog)
    assert report.match_level == "unscored"
    assert report.jd_skills == ()
    assert any("技能目录未覆盖" in risk for risk in report.risk_areas)
    context = build_job_context(report)
    assert "未评分" in context
    assert "0/100" not in context


def test_report_roundtrip_and_context(catalog):
    """验证报告往返和上下文。

    Args:
        catalog: `catalog` 输入参数，类型为 未标注。

    """
    jd = "岗位要求 Python FastAPI Redis 和可观测性经验，能够独立负责服务稳定性。"
    resume = "Python FastAPI Redis OpenTelemetry，错误率下降 20%。"
    report = assess_job_match(jd, resume, catalog)
    restored = JobMatchReport.from_dict(report.to_dict())
    assert restored == report
    context = build_job_context(report)
    assert "岗位匹配分数" in context
    assert "缺失技能" in context
