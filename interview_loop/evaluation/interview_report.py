import re
from dataclasses import dataclass, field
from typing import Any

DIMENSION_LABELS = {
    "technical_depth": "技术深度",
    "problem_solving": "问题解决",
    "architecture": "架构设计",
    "communication": "沟通表达",
    "technical_decision": "技术决策",
    "leadership": "团队领导",
    "motivation": "求职动机",
    "collaboration": "协作能力",
    "self_awareness": "自我认知",
}

DIMENSION_KEYWORDS = {
    "technical_depth": ("原理", "实现", "源码", "缓存", "并发", "检索", "模型", "数据库"),
    "problem_solving": ("问题", "原因", "方案", "结果", "故障", "排查", "优化", "提升", "下降"),
    "architecture": ("架构", "模块", "扩展", "容灾", "解耦", "设计", "链路", "平台"),
    "communication": ("首先", "其次", "最后", "背景", "目标", "结果", "总结", "取舍"),
    "technical_decision": ("选型", "权衡", "对比", "取舍", "成本", "风险", "收益"),
    "leadership": ("团队", "负责", "推动", "决策", "协作", "管理", "培养"),
    "motivation": ("职业", "目标", "成长", "岗位", "机会", "规划"),
    "collaboration": ("团队", "协作", "冲突", "沟通", "推动", "配合"),
    "self_awareness": ("复盘", "反思", "不足", "改进", "学习", "成长"),
}

DIMENSION_ACTIONS = {
    "technical_depth": "补充核心原理、边界条件和故障案例，并解释关键实现。",
    "problem_solving": "用 STAR 结构回答，完整说明问题、行动、结果和量化收益。",
    "architecture": "练习模块关系、数据流、容量假设、容灾和扩展方案。",
    "communication": "使用结论-证据-取舍三段式，控制回答层次和长度。",
    "technical_decision": "准备备选方案对比，说明成本、风险、收益和决策依据。",
    "leadership": "补充团队目标、个人推动动作、冲突处理和最终组织结果。",
    "motivation": "把个人目标、岗位需求和长期规划连接起来。",
    "collaboration": "准备跨团队协作和冲突案例，说明具体动作与结果。",
    "self_awareness": "说明已发现的不足、改进动作和后续验证结果。",
}

STRUCTURE_MARKERS = ("首先", "其次", "最后", "背景", "目标", "行动", "结果", "总结", "取舍")
VAGUE_MARKERS = ("不知道", "没做过", "不了解", "不会", "大概", "可能吧")


@dataclass(frozen=True)
class EvidenceItem:
    dimension: str
    dimension_label: str
    question: str
    answer_excerpt: str
    score: float

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass(frozen=True)
class DimensionScore:
    name: str
    label: str
    score: float
    weight: float
    evidence: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ActionItem:
    priority: str
    action: str
    related_dimension: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass(frozen=True)
class InterviewReport:
    overall_score: float
    dimensions: tuple[DimensionScore, ...]
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    action_plan: tuple[ActionItem, ...]
    evidence: tuple[EvidenceItem, ...]
    summary: str
    source: str = "structure-heuristic-v1"

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "strengths": list(self.strengths),
            "risks": list(self.risks),
            "action_plan": [item.to_dict() for item in self.action_plan],
            "evidence": [item.to_dict() for item in self.evidence],
            "summary": self.summary,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewReport":
        return cls(
            overall_score=float(data.get("overall_score", 0)),
            dimensions=tuple(DimensionScore(**item) for item in data.get("dimensions", [])),
            strengths=tuple(data.get("strengths", [])),
            risks=tuple(data.get("risks", [])),
            action_plan=tuple(ActionItem(**item) for item in data.get("action_plan", [])),
            evidence=tuple(EvidenceItem(**item) for item in data.get("evidence", [])),
            summary=str(data.get("summary", "")),
            source=str(data.get("source", "structure-heuristic-v1")),
        )


@dataclass(frozen=True)
class ProgressRecord:
    time: str
    mode: str
    overall_score: float
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WeakAreaChange:
    new_areas: tuple[str, ...]
    resolved_areas: tuple[str, ...]
    persistent_areas: tuple[str, ...]


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def parse_turns(messages: list[dict]) -> list[tuple[str, str]]:
    turns = []
    pending = ""
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role == "interviewer":
            pending = content
        elif role == "candidate":
            turns.append((pending, content))
            pending = ""
    return turns


def _answer_quality(answer: str) -> float:
    text = answer.strip()
    if not text:
        return 1.0
    score = 3.2 + min(2.6, len(text) / 120)
    score += min(1.6, sum(marker in text for marker in STRUCTURE_MARKERS) * 0.4)
    if re.search(r"\d", text):
        score += 0.8
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}", text)
    score += min(1.4, len(set(tokens)) * 0.2)
    if any(marker in text for marker in VAGUE_MARKERS):
        score -= 1.8
    return round(_clamp(score), 1)


def _keyword_hits(text: str, dimension: str) -> int:
    return sum(text.count(keyword) for keyword in DIMENSION_KEYWORDS.get(dimension, ()))


def _best_evidence(turns: list[tuple[str, str]], dimension: str, label: str, score: float) -> EvidenceItem:
    if not turns:
        return EvidenceItem(dimension, label, "", "暂无回答证据", score)
    question, answer = max(turns, key=lambda item: _keyword_hits(item[1], dimension) * 100 + len(item[1]))
    return EvidenceItem(
        dimension,
        label,
        question,
        answer.replace("\n", " ").strip()[:180],
        score,
    )


def _job_value(job_match: Any, key: str, default: Any) -> Any:
    if job_match is None:
        return default
    if isinstance(job_match, dict):
        return job_match.get(key, default)
    return getattr(job_match, key, default)


def build_interview_report(
    messages: list[dict],
    rubric: list[Any] | tuple[Any, ...],
    tags: list[str] | None = None,
    job_match: Any = None,
) -> InterviewReport:
    tags = list(tags or [])
    turns = parse_turns(messages)
    answers = "\n".join(answer for _, answer in turns)
    quality = [_answer_quality(answer) for _, answer in turns]
    base = sum(quality) / len(quality) if quality else 0.0
    structure_hits = sum(sum(marker in answer for marker in STRUCTURE_MARKERS) for _, answer in turns)
    technical_tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}", answers))

    dimensions = []
    evidence = []
    for raw in rubric:
        name = str(getattr(raw, "name", ""))
        weight = float(getattr(raw, "weight", 0.0))
        label = DIMENSION_LABELS.get(name, name)
        adjustment = min(1.6, _keyword_hits(answers, name) * 0.2)
        if name == "communication":
            adjustment += min(1.0, structure_hits * 0.15)
        if name == "technical_depth":
            adjustment += min(1.0, len(technical_tokens) * 0.1)
        score = round(_clamp(base + adjustment), 1)
        best = _best_evidence(turns, name, label, score)
        dimensions.append(DimensionScore(name, label, score, weight, best.answer_excerpt))
        evidence.append(best)

    total_weight = sum(item.weight for item in dimensions) or 1.0
    overall = round(sum(item.score * item.weight for item in dimensions) / total_weight, 1)
    ranked = sorted(dimensions, key=lambda item: item.score, reverse=True)
    if ranked and ranked[0].score >= 6.5:
        strengths = tuple(
            f"{item.label}：{item.score}/10，该维度参考分相对较高。"
            for item in ranked[:2]
            if item.score >= 6.5
        )
    elif ranked:
        strengths = (
            f"本轮暂无明显优势；相对较好的是 {ranked[0].label}"
            f"（{ranked[0].score}/10）。",
        )
    else:
        strengths = ("本轮暂无明显优势。",)
    weak = sorted([item for item in dimensions if item.score < 6.5], key=lambda item: item.score)
    risks = tuple(
        f"{item.label}偏弱：{item.score}/10，需要补充事实、取舍和结果。"
        for item in weak[:2]
    )
    if tags:
        risks += (f"本轮重复出现薄弱标签：{'、'.join(tags[:5])}。",)
    missing = list(_job_value(job_match, "missing_skills", []))
    if missing:
        risks += (f"岗位匹配仍缺少证据：{'、'.join(missing[:5])}。",)

    actions = [
        ActionItem(
            f"P{index}",
            DIMENSION_ACTIONS.get(item.name, f"针对{item.label}补充案例并再次练习。"),
            item.name,
        )
        for index, item in enumerate(sorted(dimensions, key=lambda value: value.score)[:2], 1)
    ]
    for skill in missing[:2]:
        actions.append(ActionItem(f"P{len(actions) + 1}", f"准备 {skill} 的项目证据、取舍和量化结果。", "job_match"))
    if not actions:
        actions.append(ActionItem("P1", "选择最低分维度补充一个可量化案例后重新模拟。", "general"))

    strongest = ranked[0].label if ranked else "暂无"
    weakest = sorted(dimensions, key=lambda item: item.score)[0].label if dimensions else "暂无"
    if ranked and ranked[0].score >= 6.5:
        strength_summary = f"优势维度是{strongest}"
    else:
        strength_summary = f"本轮暂无明显优势，相对较好的是{strongest}"
    return InterviewReport(
        overall_score=overall,
        dimensions=tuple(dimensions),
        strengths=strengths,
        risks=risks,
        action_plan=tuple(actions),
        evidence=tuple(evidence),
        summary=f"表达结构参考分为 {overall}/10（基于回答长度、结构和关键词的启发式规则，仅用于训练反馈）。{strength_summary}，优先改进{weakest}。共记录 {len(turns)} 轮回答。",
    )


def build_progress_records(sessions: list[dict], mode: str | None = None) -> list[ProgressRecord]:
    records = []
    for item in sessions:
        if mode and item.get("mode") != mode:
            continue
        score = (item.get("structured_report") or {}).get("overall_score")
        if score is None:
            continue
        records.append(ProgressRecord(str(item.get("started_at") or item.get("time") or "未知"), str(item.get("mode", "")), float(score), tuple(item.get("tags", []))))
    return sorted(records, key=lambda item: item.time)


def compare_weak_areas(current_tags: list[str], previous_tags: list[str]) -> WeakAreaChange:
    current = set(current_tags)
    previous = set(previous_tags)
    return WeakAreaChange(tuple(sorted(current - previous)), tuple(sorted(previous - current)), tuple(sorted(current & previous)))
