import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class JobDescriptionError(ValueError):
    pass


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    category: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class SkillCatalog:
    version: str
    skills: tuple[SkillDefinition, ...]


@dataclass(frozen=True)
class JobMatchReport:
    match_score: int
    match_level: str
    jd_skills: tuple[str, ...]
    resume_skills: tuple[str, ...]
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    bonus_skills: tuple[str, ...]
    risk_areas: tuple[str, ...]
    suggested_focus: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "JobMatchReport":
        return cls(
            match_score=int(data.get("match_score", 0)),
            match_level=str(data.get("match_level", "poor")),
            jd_skills=tuple(data.get("jd_skills", [])),
            resume_skills=tuple(data.get("resume_skills", [])),
            matched_skills=tuple(data.get("matched_skills", [])),
            missing_skills=tuple(data.get("missing_skills", [])),
            bonus_skills=tuple(data.get("bonus_skills", [])),
            risk_areas=tuple(data.get("risk_areas", [])),
            suggested_focus=tuple(data.get("suggested_focus", [])),
        )

    def to_dict(self) -> dict:
        return {
            "match_score": self.match_score,
            "match_level": self.match_level,
            "jd_skills": list(self.jd_skills),
            "resume_skills": list(self.resume_skills),
            "matched_skills": list(self.matched_skills),
            "missing_skills": list(self.missing_skills),
            "bonus_skills": list(self.bonus_skills),
            "risk_areas": list(self.risk_areas),
            "suggested_focus": list(self.suggested_focus),
        }


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _matches_alias(text: str, alias: str) -> bool:
    normalized_alias = normalize_text(alias)
    if not normalized_alias:
        return False
    if re.fullmatch(r"[\x00-\x7f]+", normalized_alias):
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(normalized_alias)
            + r"(?![a-z0-9])"
        )
        return re.search(pattern, text) is not None
    return normalized_alias in text


def extract_skills(text: str, catalog: SkillCatalog) -> list[str]:
    normalized = normalize_text(text)
    result = []
    for skill in catalog.skills:
        if any(_matches_alias(normalized, alias) for alias in skill.aliases):
            result.append(skill.name)
    return result


def validate_job_description(text: str, catalog: SkillCatalog) -> str:
    value = str(text or "").strip()
    if len(value) < 40:
        raise JobDescriptionError("岗位 JD 过短，请至少提供职责、技能或任职要求")
    return value


def assess_job_match(
    job_description: str,
    resume_text: str,
    catalog: SkillCatalog,
) -> JobMatchReport:
    validate_job_description(job_description, catalog)
    jd_skills = tuple(extract_skills(job_description, catalog))
    resume_skills = tuple(extract_skills(resume_text, catalog))
    jd_set = set(jd_skills)
    resume_set = set(resume_skills)
    matched = tuple(skill for skill in jd_skills if skill in resume_set)
    missing = tuple(skill for skill in jd_skills if skill not in resume_set)
    bonus = tuple(skill for skill in resume_skills if skill not in jd_set)
    score = round(len(matched) / len(jd_skills) * 100) if jd_skills else 0
    if not jd_skills:
        level = "unscored"
    elif score >= 70:
        level = "good"
    elif score >= 40:
        level = "partial"
    else:
        level = "poor"

    risks = []
    if not jd_skills:
        risks.append(
            "当前技能目录未覆盖该 JD 的技术关键词，岗位匹配本次不评分，但不阻断面试。"
        )
    if not str(resume_text or "").strip():
        risks.append("尚未提供简历，无法验证岗位要求")
    elif missing:
        risks.append(f"缺少岗位技能证据：{', '.join(missing[:5])}")
    if str(resume_text or "").strip() and len(str(resume_text).strip()) < 300:
        risks.append("简历内容偏少，项目背景和个人贡献证据不足")
    if str(resume_text or "").strip() and not re.search(r"\d", str(resume_text)):
        risks.append("简历缺少量化结果，如性能提升、成本下降或业务指标")

    if not jd_skills:
        focus = ("补充岗位中的技术栈、工具和职责描述，以便下次生成可评分的匹配结果",)
    elif missing:
        focus = tuple(f"准备 {skill} 的实践案例和取舍说明" for skill in missing[:3])
    else:
        focus = tuple(
            f"围绕 {skill} 准备更深入的架构和故障排查案例"
            for skill in jd_skills[:3]
        )
    return JobMatchReport(
        match_score=score,
        match_level=level,
        jd_skills=jd_skills,
        resume_skills=resume_skills,
        matched_skills=matched,
        missing_skills=missing,
        bonus_skills=bonus,
        risk_areas=tuple(risks),
        suggested_focus=focus,
    )


def build_job_context(report: JobMatchReport | None) -> str:
    if report is None:
        return ""
    return (
        f"岗位匹配分数：{report.match_score}/100；"
        f"已匹配技能：{', '.join(report.matched_skills) or '无'}；"
        f"缺失技能：{', '.join(report.missing_skills) or '无'}；"
        f"风险：{'；'.join(report.risk_areas) or '无'}。"
    )


@lru_cache(maxsize=1)
def load_default_skill_catalog() -> SkillCatalog:
    path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "skills"
        / "technical.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    skills = []
    seen = set()
    for item in data.get("skills", []):
        name = str(item.get("name", "")).strip()
        if not name or name in seen:
            continue
        aliases = tuple(
            str(alias).strip()
            for alias in item.get("aliases", [])
            if str(alias).strip()
        )
        if not aliases:
            aliases = (name,)
        skills.append(
            SkillDefinition(
                name=name,
                category=str(item.get("category", "general")),
                aliases=aliases,
            )
        )
    if not skills:
        raise JobDescriptionError("技能目录为空")
    return SkillCatalog(
        version=str(data.get("version", "unknown")),
        skills=tuple(skills),
    )
