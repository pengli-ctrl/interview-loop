"""代码注释门禁模块，负责校验和自动补齐中文 Google 风格 docstring。"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".capture"}
TOKEN_TRANSLATIONS = {
    "add": "添加",
    "apply": "应用",
    "build": "构建",
    "calculate": "计算",
    "check": "检查",
    "clean": "清理",
    "clear": "清空",
    "close": "关闭",
    "collect": "收集",
    "compare": "比较",
    "complete": "完成",
    "configure": "配置",
    "count": "统计",
    "create": "创建",
    "decode": "解码",
    "default": "默认",
    "delete": "删除",
    "detect": "检测",
    "discard": "丢弃",
    "emit": "发送",
    "encode": "编码",
    "ensure": "确保",
    "enter": "进入",
    "estimate": "估算",
    "evaluate": "评估",
    "execute": "执行",
    "export": "导出",
    "extract": "提取",
    "fail": "标记失败",
    "fetch": "获取",
    "find": "查找",
    "format": "格式化",
    "from": "从",
    "get": "获取",
    "handle": "处理",
    "has": "判断",
    "import": "导入",
    "is": "判断",
    "list": "列出",
    "load": "加载",
    "main": "主流程",
    "mark": "标记",
    "merge": "合并",
    "normalize": "规范化",
    "open": "打开",
    "parse": "解析",
    "persist": "持久化",
    "process": "处理",
    "query": "查询",
    "record": "记录",
    "refresh": "刷新",
    "register": "注册",
    "remove": "移除",
    "render": "渲染",
    "reset": "重置",
    "resolve": "解析",
    "restore": "恢复",
    "run": "运行",
    "save": "保存",
    "score": "评分",
    "select": "选择",
    "send": "发送",
    "set": "设置",
    "start": "启动",
    "stop": "停止",
    "submit": "提交",
    "summarize": "汇总",
    "supports": "支持",
    "test": "测试",
    "to": "转换为",
    "update": "更新",
    "validate": "校验",
    "action": "动作",
    "allows": "允许",
    "followup": "追问",
    "call": "调用",
    "control": "控制",
    "decide": "决定",
    "end": "结束",
    "evidence": "证据",
    "explicit": "显式",
    "generate": "生成",
    "next": "下一个",
    "phrase": "短语",
    "requires": "需要",
    "respected": "被遵守",
    "should": "应",
    "skips": "跳过",
    "answer": "回答",
    "agent": "Agent",
    "api": "API",
    "audio": "音频",
    "auth": "鉴权",
    "batch": "批量",
    "budget": "预算",
    "cache": "缓存",
    "candidate": "候选人",
    "catalog": "目录",
    "class": "类",
    "client": "客户端",
    "console": "控制台",
    "cost": "成本",
    "current": "当前",
    "data": "数据",
    "decision": "决策",
    "demo": "演示",
    "dict": "字典",
    "draft": "草稿",
    "event": "事件",
    "failure": "失败",
    "file": "文件",
    "flow": "流程",
    "id": "ID",
    "interview": "面试",
    "job": "岗位",
    "key": "键",
    "latency": "延迟",
    "long": "长",
    "message": "消息",
    "metric": "指标",
    "model": "模型",
    "name": "名称",
    "node": "节点",
    "output": "输出",
    "params": "参数",
    "path": "路径",
    "payload": "负载",
    "permission": "权限",
    "prompt": "提示词",
    "provider": "Provider",
    "question": "问题",
    "report": "报告",
    "request": "请求",
    "response": "响应",
    "result": "结果",
    "resume": "简历",
    "review": "复盘",
    "scenario": "场景",
    "session": "会话",
    "short": "短",
    "stage": "阶段",
    "stats": "统计",
    "status": "状态",
    "store": "存储",
    "tenant": "租户",
    "text": "文本",
    "time": "时间",
    "token": "Token",
    "tool": "工具",
    "trace": "Trace",
    "unknown": "未知",
    "user": "用户",
    "valid": "有效",
    "value": "值",
    "voice": "语音",
}

TOKEN_TRANSLATIONS.update(
    {
        "append": "追加",
        "breaker": "熔断器",
        "cached": "缓存",
        "calendar": "日历",
        "cap": "上限",
        "circuit": "熔断",
        "clears": "清理",
        "console": "控制台",
        "corrupt": "损坏",
        "dataset": "数据集",
        "dict": "字典",
        "dimension": "维度",
        "dimensions": "维度",
        "enter": "进入",
        "eval": "评估",
        "expired": "过期",
        "files": "文件",
        "formatting": "格式化",
        "gateway": "网关",
        "global": "全局",
        "golden": "黄金",
        "go": "前往",
        "good": "正常",
        "helpers": "辅助函数",
        "human": "人工",
        "id": "ID",
        "instead": "而不是",
        "into": "到",
        "latest": "最近",
        "legacy": "旧版",
        "limit": "上限",
        "local": "本地",
        "long": "长",
        "main": "主流程",
        "marked": "标记",
        "migrate": "迁移",
        "next": "下一步",
        "not": "不",
        "observability": "可观测性",
        "opens": "打开",
        "outside": "目录外",
        "owned": "所属",
        "partial": "部分",
        "passed": "通过",
        "pending": "待处理",
        "phrase": "短语",
        "policy": "策略",
        "poor": "较差",
        "principal": "身份",
        "privacy": "隐私",
        "product": "产品",
        "profile": "配置",
        "progress": "进度",
        "python": "Python",
        "quality": "质量",
        "quota": "配额",
        "record": "记录",
        "removed": "移除",
        "repo": "仓库",
        "repository": "仓库",
        "request": "请求",
        "requires": "需要",
        "respected": "被遵守",
        "restored": "恢复",
        "retention": "保留",
        "retry": "重试",
        "review": "复核",
        "risk": "风险",
        "risks": "风险",
        "roundtrip": "往返",
        "runs": "运行",
        "saved": "已保存",
        "scenarios": "场景",
        "score": "评分",
        "scores": "评分",
        "shell": "壳",
        "shows": "展示",
        "single": "单条",
        "skips": "跳过",
        "spec": "规格",
        "sqlite": "SQLite",
        "stale": "过期",
        "step": "步骤",
        "storage": "存储",
        "strength": "优势",
        "strengths": "优势",
        "structured": "结构化",
        "tenant": "租户",
        "threshold": "阈值",
        "thresholds": "阈值",
        "time": "时间",
        "ttl": "TTL",
        "unknown": "未知",
        "unscored": "未评分",
        "unfinished": "未完成",
        "usage": "用量",
        "uses": "使用",
        "view": "视图",
        "views": "视图",
        "visible": "可见",
        "weak": "薄弱",
        "zero": "零",
        "and": "和",
        "action": "行动",
        "actions": "行动",
        "annotation": "注解",
        "audit": "审计",
        "chinese": "中文",
        "contains": "包含",
        "conflict": "冲突",
        "docstring": "docstring",
        "failed": "失败",
        "fix": "修复",
        "function": "函数",
        "idempotency": "幂等",
        "iter": "遍历",
        "module": "模块",
        "raise": "抛出",
        "raised": "抛出",
        "registry": "注册表",
        "replace": "替换",
        "return": "返回",
        "route": "路由",
        "schema": "Schema",
        "sections": "章节",
        "select": "选择",
        "selection": "选择",
        "snapshot": "快照",
        "stream": "流式",
        "success": "成功",
        "summary": "摘要",
        "timeout": "超时",
        "translate": "翻译",
        "validation": "校验",
        "visit": "访问",
        "visitor": "访问器",
        "window": "窗口",
        "yield": "生成",
        "asr": "ASR",
        "be": "被",
        "bm25": "BM25",
        "by": "由",
        "cases": "用例",
        "css": "CSS",
        "context": "上下文",
        "db": "数据库",
        "events": "事件",
        "faiss": "FAISS",
        "generated": "生成",
        "health": "健康",
        "html": "HTML",
        "http": "HTTP",
        "inject": "注入",
        "json": "JSON",
        "llm": "LLM",
        "markdown": "Markdown",
        "match": "匹配",
        "me": "当前身份",
        "models": "模型",
        "overall": "综合",
        "pdf": "PDF",
        "pii": "PII",
        "plan": "计划",
        "precision": "精确率",
        "priority": "优先级",
        "rag": "RAG",
        "rate": "率",
        "recall": "召回率",
        "replay": "重放",
        "retrieval": "检索",
        "row": "行",
        "rows": "行",
        "serialize": "序列化",
        "sessions": "会话",
        "skill": "技能",
        "definition": "定义",
        "target": "目标",
        "sse": "SSE",
        "tags": "标签",
        "timer": "计时器",
        "tools": "工具",
        "transition": "切换",
        "tts": "TTS",
        "txt": "TXT",
        "ui": "UI",
        "url": "URL",
        "weight": "权重",
        "weighted": "加权",
        "without": "缺少",
        "with": "带",
        "can": "可以",
        "error": "错误",
        "dir": "目录",
        "state": "状态",
        "setup": "设置",
        "unavailable": "不可用",
        "exceeded": "超限",
        "remaining": "剩余",
        "tokens": "Token",
        "new": "新建",
        "dashboard": "工作台",
        "empty": "空",
        "chart": "图表",
        "growth": "成长",
        "streamlit": "Streamlit",
        "app": "应用",
        "metrics": "指标",
        "mark": "标记",
        "do": "",
        "does": "",
        "of": "",
        "the": "",
        "a": "",
        "an": "",
        "in": "",
        "on": "",
        "or": "或",
    }
)

TOKEN_TRANSLATIONS.update(
    {
        "accumulates": "累加",
        "actual": "实际",
        "after": "之后",
        "aggregate": "汇总",
        "alias": "别名",
        "aliases": "别名",
        "all": "所有",
        "answered": "已回答",
        "attempt": "尝试",
        "audio2text": "音频转文本",
        "authentication": "鉴权",
        "before": "之前",
        "between": "之间",
        "boundaries": "边界",
        "case": "用例",
        "change": "变化",
        "checks": "检查",
        "claims": "声明",
        "cleaning": "清洗",
        "clamp": "限制",
        "cooldown": "冷却",
        "common": "常见",
        "completed": "已完成",
        "config": "配置",
        "confirmed": "确认",
        "consistent": "一致",
        "contains": "包含",
        "context": "上下文",
        "corrupted": "损坏",
        "counts": "计数",
        "decode": "解码",
        "deletes": "删除",
        "description": "描述",
        "details": "详情",
        "different": "不同",
        "directory": "目录",
        "duration": "时长",
        "empty": "空",
        "enforced": "强制执行",
        "evaluation": "评估",
        "execution": "执行",
        "expires": "到期",
        "expiry": "到期",
        "filename": "文件名",
        "finish": "结束",
        "found": "找到",
        "filters": "过滤",
        "failing": "失败",
        "failures": "失败",
        "flaky": "不稳定",
        "half": "半",
        "handler": "处理器",
        "handles": "处理",
        "hits": "命中",
        "higher": "更高",
        "idempotent": "幂等",
        "identical": "相同",
        "ignored": "被忽略",
        "include": "包含",
        "includes": "包含",
        "input": "输入",
        "interpolates": "插值",
        "invalid": "无效",
        "isolated": "隔离",
        "isolation": "隔离",
        "item": "项",
        "lifecycle": "生命周期",
        "loads": "加载",
        "matches": "匹配",
        "mode": "模式",
        "moves": "移动",
        "must": "必须",
        "names": "名称",
        "nested": "嵌套",
        "not": "不",
        "old": "旧",
        "output": "输出",
        "overrun": "超限",
        "pack": "包",
        "pairs": "配对",
        "part": "部分",
        "paths": "路径",
        "persists": "持久化",
        "policy": "策略",
        "post": "之后",
        "prompts": "提示词",
        "punctuation": "标点",
        "purge": "清理",
        "raises": "抛出",
        "reconstructs": "重建",
        "records": "记录",
        "redact": "脱敏",
        "redacted": "已脱敏",
        "rejected": "被拒绝",
        "rejects": "拒绝",
        "removes": "移除",
        "rendered": "渲染",
        "repair": "修复",
        "reports": "报告",
        "required": "必需",
        "resets": "重置",
        "respects": "遵守",
        "retries": "重试",
        "returns": "返回",
        "reuses": "复用",
        "round": "轮次",
        "rounds": "轮次",
        "routes": "路由",
        "safe": "安全",
        "sanitized": "清洗",
        "search": "搜索",
        "secret": "密钥",
        "sequence": "顺序",
        "serialization": "序列化",
        "sidebar": "侧边栏",
        "similar": "相似",
        "similarity": "相似度",
        "skills": "技能",
        "skip": "跳过",
        "sort": "排序",
        "stages": "阶段",
        "strip": "移除",
        "styles": "风格",
        "successful": "成功",
        "tag": "标签",
        "tasks": "任务",
        "tenants": "租户",
        "text2audio": "文本转音频",
        "than": "比",
        "threshold": "阈值",
        "timestamp": "时间戳",
        "too": "太",
        "topic": "主题",
        "transient": "瞬时",
        "turns": "轮次",
        "unanswered": "未回答",
        "unknown": "未知",
        "utcnow": "当前 UTC 时间",
        "vague": "含糊",
        "values": "值",
        "weights": "权重",
        "window": "窗口",
        "word": "词",
        "wrapped": "包装",
        "administrator": "管理员",
        "admin": "管理",
        "restart": "重启",
        "complete": "完成",
        "completes": "完成",
        "adds": "添加",
        "builds": "构建",
        "creates": "创建",
        "extracts": "提取",
        "generates": "生成",
        "opens": "打开",
        "parses": "解析",
        "renders": "渲染",
        "saves": "保存",
        "selects": "选择",
        "starts": "启动",
        "validates": "校验",
        "migrates": "迁移",
        "assesses": "评估",
        "accepts": "接受",
        "enforces": "强制",
        "recovers": "恢复",
        "excludes": "排除",
        "limits": "限制",
        "skips": "跳过",
        "keeps": "保持",
        "kept": "保持",
        "makes": "生成",
        "works": "工作",
        "provides": "提供",
        "avoids": "避免",
    }
)


MODULE_DESCRIPTIONS = {
    "app": "InterviewLoop 应用入口与业务编排模块，负责 Streamlit 会话状态、页面回调、持久化和外部服务装配。",
    "control_plane": "只读平台控制面模块，负责场景、模型、工具、Run、配额和评估数据的查询与格式化。",
    "security": "API 鉴权模块，负责 API Key、租户、用户和权限请求头的解析与校验。",
    "main": "FastAPI 应用入口模块，负责 API 路由、鉴权、AgentRun、工具执行、指标和 SSE 接口。",
    "config": "项目配置模块，负责读取模型、语音、存储、Demo 和 Admin 等运行配置。",
    "flow": "确定性面试流程模块，负责追问、主问题、阶段推进和结束决策。",
    "job_match": "岗位匹配模块，负责 JD/简历技能提取、匹配评分、风险分析和模型上下文构建。",
    "question_engine": "问题生成模块，负责阶段提示词、相似问题修复和兜底追问。",
    "review": "面试复盘模块，负责复盘提示词、标签解析和数字分数清洗。",
    "agent_metrics": "Agent 指标模块，负责汇总运行失败率、延迟、成本、重试、重复问题和阶段遵守率。",
    "interview_report": "面试报告模块，负责表达结构参考分、维度评分、证据、风险和行动计划生成。",
    "quality": "评分质量模块，负责人工评分与模型评分的误差校准和门禁判断。",
    "rag_benchmark": "RAG 基准模块，负责运行默认检索黄金集并返回评估结果。",
    "replay": "Trace Replay 模块，负责从 AgentRun 事件重建面试阶段和完成状态。",
    "retrieval": "检索评估模块，负责 Precision、Recall、MRR 和 Hit Rate 计算。",
    "rubric": "Rubric 模块，负责评分维度与权重加权计算。",
    "markdown": "Markdown 导出模块，负责完整面试记录、评分和复盘报告生成。",
    "agent_run": "AgentRun 模块，负责运行状态、事件、Trace、保留策略和导出结构。",
    "builtin_tools": "内置工具模块，负责注册项目提供的 Agent 工具及权限。",
    "model_gateway": "模型网关模块，负责路由、重试、熔断、预算、租户额度、成本和调用遥测。",
    "privacy": "隐私模块，负责 PII 脱敏、保留到期和数据处理辅助逻辑。",
    "run_repository": "AgentRun 持久化模块，负责 SQLite 中的运行、事件、幂等和保留清理。",
    "tool_registry": "工具注册表模块，负责工具注册、权限、Schema、超时、幂等和审计。",
    "resume": "简历模块，负责 TXT、Markdown 和 PDF 简历文本提取。",
    "retriever": "检索器模块，负责本地向量模型检测、BM25/FAISS 混合检索和降级。",
    "text": "文本处理模块，负责简历文本编码识别和解码。",
    "models": "场景模型模块，负责场景包、阶段、Rubric 的数据模型和配置校验。",
    "registry": "场景注册表模块，负责加载场景包、按轮次查询和兼容旧配置。",
    "asr": "语音识别模块，负责火山引擎 ASR 适配和 Demo 占位识别。",
    "common": "服务公共模块，负责外部服务配置校验与公共辅助逻辑。",
    "demo": "Demo 服务模块，负责固定题目、演示复盘和标签响应生成。",
    "llm": "大模型服务模块，负责 OpenAI 兼容接口调用和 Demo 响应分发。",
    "speech_common": "语音公共模块，负责语音服务请求构造和响应处理辅助逻辑。",
    "tts": "语音合成模块，负责火山引擎 TTS 适配和 Demo 占位音频。",
    "draft_store": "草稿存储模块，负责未完成面试草稿的保存、TTL、清理和删除。",
    "session_store": "会话存储模块，负责会话 ID、JSON 数据和文件列表管理。",
    "stats_store": "统计存储模块，负责薄弱标签统计的读写和容错。",
    "tenant_paths": "租户路径模块，负责租户标识清洗和存储目录隔离。",
    "components": "Streamlit 通用组件模块，负责 CSS、chips、指标网格和评分卡片。",
    "dashboard_view": "Streamlit 工作台页面模块，负责开始训练、恢复草稿、最近报告和成长入口。",
    "setup_view": "Streamlit 面试设置页面模块，负责三步向导、JD/简历上下文、授权和开始面试。",
    "interview_view": "Streamlit 面试室页面模块，负责阶段进度、计时、问题、语音/文字回答和结束操作。",
    "report_view": "Streamlit 复盘报告页面模块，负责参考分、维度图、行动计划和下载入口。",
    "growth_view": "Streamlit 成长记录页面模块，负责弱项统计、趋势、历史下载和删除确认。",
    "admin_view": "Streamlit 管理控制台页面模块，负责展示场景、模型、工具、AgentRun 和评估指标。",
    "capture_demo": "演示捕获脚本模块，负责启动隔离 Demo、执行 Playwright 流程、截图断言和 GIF 生成。",
    "check_docstrings": "代码注释门禁模块，负责校验和自动补齐中文 Google 风格 docstring。",
    "evaluate_quality": "质量评估脚本模块，负责运行评分质量校准门禁。",
    "evaluate_rag": "RAG 评估脚本模块，负责运行检索黄金集门禁。",
    "purge_expired_runs": "AgentRun 清理脚本模块，负责按保留策略清理过期运行记录。",
}

@dataclass(frozen=True)
class FunctionSpec:
    """函数 docstring 生成规格。"""

    summary: str
    params: tuple[tuple[str, str], ...]
    returns: str | None
    raises: tuple[tuple[str, str], ...]


def _contains_chinese(text: str | None) -> bool:
    """判断文本是否包含中文。

    Args:
        text: `text` 输入参数，类型为 str | None。

    Returns:
        函数处理结果，类型为 bool。

    """
    return bool(text and CHINESE_RE.search(text))


def _iter_python_files(root: Path) -> list[Path]:
    """遍历需要检查的 Python 文件。

    Args:
        root: `root` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 list[Path]。

    """
    files = []
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _translate_name(name: str) -> str:
    """把标识符按词元翻译为中文短语。

    Args:
        name: `name` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    tokens = [token for token in re.split(r"[_\W]+", expanded) if token]
    translated = [TOKEN_TRANSLATIONS.get(token.lower(), token) for token in tokens]
    if not translated:
        return "对应"
    return "".join(translated)


def _annotation_text(annotation: ast.AST | None) -> str:
    """把类型注解转换为可读文本。

    Args:
        annotation: `annotation` 输入参数，类型为 ast.AST | None。

    Returns:
        函数处理结果，类型为 str。

    """
    if annotation is None:
        return ""
    try:
        return ast.unparse(annotation)
    except Exception:
        return "任意类型"


def _function_summary(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """根据函数名和类型生成中文职责摘要。

    Args:
        node: `node` 输入参数，类型为 ast.FunctionDef | ast.AsyncFunctionDef。

    Returns:
        函数处理结果，类型为 str。

    """
    name = node.name
    if name == "__init__":
        return "初始化实例。"
    if name.startswith("__") and name.endswith("__"):
        return f"实现 Python 特殊方法 `{name}`。"
    is_test = name.startswith("test_")
    translated = _translate_name(name.removeprefix("test_") if is_test else name)
    translated = translated.removesuffix("逻辑").strip() or f"处理 `{name}`"
    if is_test:
        return f"验证{translated}。"
    if name.startswith("_"):
        return f"内部辅助：{translated}。"
    return f"{translated}。"


def _return_visitor(node: ast.AST) -> tuple[bool, bool]:
    """判断函数体是否包含带值 return 或 yield。

    Args:
        node: `node` 输入参数，类型为 ast.AST。

    Returns:
        函数处理结果，类型为 tuple[bool, bool]。

    """

    class Visitor(ast.NodeVisitor):
        """收集 return/yield 标记的 AST 访问器。"""

        def __init__(self) -> None:
            """初始化访问标记。"""
            self.has_return_value = False
            self.has_yield = False

        def visit_Return(self, child: ast.Return) -> None:
            """记录是否存在带值 return。

            Args:
                child: `child` 输入参数，类型为 ast.Return。

            """
            if child.value is not None:
                self.has_return_value = True

        def visit_Yield(self, child: ast.Yield) -> None:
            """记录是否存在 yield。

            Args:
                child: `child` 输入参数，类型为 ast.Yield。

            """
            self.has_yield = True

        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            """只遍历目标普通函数体。

            Args:
                child: `child` 输入参数，类型为 ast.FunctionDef。

            """
            if child is node:
                self.generic_visit(child)

        def visit_AsyncFunctionDef(self, child: ast.AsyncFunctionDef) -> None:
            """只遍历目标异步函数体。

            Args:
                child: `child` 输入参数，类型为 ast.AsyncFunctionDef。

            """
            if child is node:
                self.generic_visit(child)

    visitor = Visitor()
    for statement in node.body:
        visitor.visit(statement)
    return visitor.has_return_value, visitor.has_yield


def _raised_exceptions(node: ast.AST) -> tuple[str, ...]:
    """收集函数体显式抛出的异常类型。

    Args:
        node: `node` 输入参数，类型为 ast.AST。

    Returns:
        函数处理结果，类型为 tuple[str, ...]。

    """
    result: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Raise) or child.exc is None:
            continue
        try:
            name = ast.unparse(child.exc)
        except Exception:
            name = "Exception"
        name = name.split("(", 1)[0].strip() or "Exception"
        if name not in result:
            result.append(name)
    return tuple(result)


def _function_spec(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionSpec:
    """提取函数的参数、返回值和异常规格。

    Args:
        node: `node` 输入参数，类型为 ast.FunctionDef | ast.AsyncFunctionDef。

    Returns:
        函数处理结果，类型为 FunctionSpec。

    """
    positional = [*node.args.posonlyargs, *node.args.args]
    params = [
        (
            argument.arg,
            f"`{argument.arg}` 输入参数，类型为 {_annotation_text(argument.annotation) or '未标注'}。",
        )
        for argument in positional
        if argument.arg not in {"self", "cls"}
    ]
    if node.args.vararg is not None:
        params.append(
            (
                f"*{node.args.vararg.arg}",
                f"可变位置参数，类型为 {_annotation_text(node.args.vararg.annotation) or '未标注'}。",
            )
        )
    for argument in node.args.kwonlyargs:
        params.append(
            (
                argument.arg,
                f"`{argument.arg}` 关键字参数，类型为 {_annotation_text(argument.annotation) or '未标注'}。",
            )
        )
    if node.args.kwarg is not None:
        params.append(
            (
                f"**{node.args.kwarg.arg}",
                f"可变关键字参数，类型为 {_annotation_text(node.args.kwarg.annotation) or '未标注'}。",
            )
        )
    has_return, has_yield = _return_visitor(node)
    returns = None
    if has_yield:
        returns = "生成迭代结果。"
    elif has_return and node.name != "__init__":
        returns = f"函数处理结果，类型为 {_annotation_text(node.returns) or '未标注'}。"
    raises = tuple(
        (
            exception,
            f"当输入、状态或外部依赖不满足要求时抛出 {exception}。",
        )
        for exception in _raised_exceptions(node)
    )
    return FunctionSpec(
        summary=_function_summary(node),
        params=tuple(params),
        returns=returns,
        raises=raises,
    )


def _format_docstring(indent: str, spec: FunctionSpec) -> list[str]:
    """按 Google 风格格式化 docstring 文本。

    Args:
        indent: `indent` 输入参数，类型为 str。
        spec: `spec` 输入参数，类型为 FunctionSpec。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    if not spec.params and spec.returns is None and not spec.raises:
        return [f'{indent}"""{spec.summary}"""']
    lines = [f'{indent}"""{spec.summary}', ""]
    if spec.params:
        lines.append(f"{indent}Args:")
        lines.extend(f"{indent}    {name}: {description}" for name, description in spec.params)
        lines.append("")
    if spec.returns is not None:
        lines.append(f"{indent}Returns:")
        lines.append(f"{indent}    {spec.returns}")
        lines.append("")
    if spec.raises:
        lines.append(f"{indent}Raises:")
        lines.extend(f"{indent}    {name}: {description}" for name, description in spec.raises)
        lines.append("")
    lines.append(f'{indent}"""')
    return lines


def _docstring_node(node: ast.AST) -> ast.Expr | None:
    """返回节点首条语句中的 docstring 表达式。

    Args:
        node: `node` 输入参数，类型为 ast.AST。

    Returns:
        函数处理结果，类型为 ast.Expr | None。

    """
    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return body[0]
    return None


PATH_MODULE_DESCRIPTIONS = {
    "storage/common.py": "存储公共模块，负责原子写入等文件持久化辅助。",
    "services/common.py": "服务公共模块，负责外部服务配置校验与请求辅助。",
    "scripts/demo_app.py": "Demo 启动包装模块，负责使用隔离目录运行 app.py。",
}


def _module_summary(path: Path) -> str:
    """根据模块路径生成模块职责说明。

    Args:
        path: `path` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 str。

    """
    stem = path.stem
    if stem == "__init__":
        return f"{path.parent.name} 包的初始化模块，用于声明 Python 包。"
    posix = path.as_posix()
    for suffix, description in PATH_MODULE_DESCRIPTIONS.items():
        if posix.endswith(suffix):
            return description
    if stem in MODULE_DESCRIPTIONS:
        return MODULE_DESCRIPTIONS[stem]
    if path.parent.name == "tests":
        translated = _translate_name(stem.removeprefix("test_"))
        return f"测试模块，覆盖{translated}相关行为和回归场景。"
    translated = _translate_name(stem)
    return f"{path.stem} 模块，提供{translated}相关功能。"


def _class_summary(node: ast.ClassDef) -> str:
    """根据类名、装饰器和基类生成类职责说明。

    Args:
        node: `node` 输入参数，类型为 ast.ClassDef。

    Returns:
        函数处理结果，类型为 str。

    """
    name = node.name
    if name.endswith("NotFoundError"):
        base = _translate_name(name.removesuffix("NotFoundError"))
        return f"表示{base}不存在的异常。"
    if name.endswith("PermissionError"):
        base = _translate_name(name.removesuffix("PermissionError"))
        return f"表示{base}权限不足的异常。"
    if name.endswith("TimeoutError"):
        base = _translate_name(name.removesuffix("TimeoutError"))
        return f"表示{base}超时的异常。"
    if name.endswith("ExecutionError"):
        base = _translate_name(name.removesuffix("ExecutionError"))
        return f"表示{base}执行失败的异常。"
    if name.endswith("ValidationError"):
        base = _translate_name(name.removesuffix("ValidationError"))
        return f"表示{base}校验失败的异常。"
    if name.endswith("ConflictError"):
        base = _translate_name(name.removesuffix("ConflictError"))
        return f"表示{base}冲突的异常。"
    if name.endswith("SchemaError"):
        base = _translate_name(name.removesuffix("SchemaError"))
        return f"表示{base} Schema 校验失败的异常。"
    if name.endswith("UnavailableError"):
        base = _translate_name(name.removesuffix("UnavailableError"))
        return f"表示{base}不可用的异常。"
    if name.endswith("ExceededError"):
        base = _translate_name(name.removesuffix("ExceededError"))
        return f"表示{base}超限的异常。"
    if name == "CircuitBreakerPolicy":
        return "熔断器策略。"
    translated = _translate_name(name) or name
    base_names = {ast.unparse(base) for base in node.bases}
    decorator_names = {ast.unparse(item) for item in node.decorator_list}
    is_exception = node.name.endswith("Error") or any(
        name.endswith("Error") or name.endswith("Exception") for name in base_names
    )
    is_enum = any(name.endswith("Enum") for name in base_names)
    is_request_model = node.name.endswith("Request") or any(
        name.endswith("BaseModel") for name in base_names
    )
    is_dataclass = any(name.endswith("dataclass") for name in decorator_names)
    if is_exception:
        return f"表示{translated}的异常。"
    if is_enum:
        return f"{translated}枚举。"
    if is_request_model:
        return f"{translated}模型。"
    if is_dataclass:
        return f"{translated}数据模型。"
    return f"{translated}。"


def _apply_edit(lines: list[str], start: int, end: int, replacement: list[str]) -> None:
    """用给定内容替换文件行区间。

    Args:
        lines: `lines` 输入参数，类型为 list[str]。
        start: `start` 输入参数，类型为 int。
        end: `end` 输入参数，类型为 int。
        replacement: `replacement` 输入参数，类型为 list[str]。

    """
    lines[start:end] = replacement


def _replace_docstring(
    lines: list[str],
    node: ast.AST,
    doc_lines: list[str],
) -> None:
    """替换已有 docstring 或在节点开头插入。

    Args:
        lines: `lines` 输入参数，类型为 list[str]。
        node: `node` 输入参数，类型为 ast.AST。
        doc_lines: `doc_lines` 输入参数，类型为 list[str]。

    """
    existing = _docstring_node(node)
    if existing is not None:
        _apply_edit(lines, existing.lineno - 1, existing.end_lineno, doc_lines)
        return
    if isinstance(node, ast.Module):
        lines[0:0] = doc_lines
        return
    first_body = node.body[0]
    indent = " " * (getattr(node, "col_offset", 0) + 4)
    if first_body.lineno == node.lineno:
        original = lines[node.lineno - 1]
        split_at = first_body.col_offset
        header = original[:split_at].rstrip()
        body = original[split_at:]
        lines[node.lineno - 1 : node.lineno] = [header, *doc_lines, f"{indent}{body}"]
        return
    insert_at = first_body.lineno - 1
    lines[insert_at:insert_at] = doc_lines


def _fix_file(path: Path, rewrite: bool = False) -> bool:
    """补齐单个文件缺失或不合格的 docstring。

    Args:
        path: `path` 输入参数，类型为 Path。
        rewrite: `rewrite` 输入参数，类型为 bool。

    Returns:
        函数处理结果，类型为 bool。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    lines = source.splitlines()
    edits: list[tuple[int, ast.AST, list[str]]] = []
    module_edit: tuple[ast.AST, list[str]] | None = None
    module_doc = ast.get_docstring(tree, clean=False)
    if rewrite or not _contains_chinese(module_doc) or "模块" not in (module_doc or ""):
        module_edit = (tree, [f'"""{_module_summary(path)}"""'])
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            existing = ast.get_docstring(node, clean=False)
            if rewrite or not _contains_chinese(existing):
                indent = " " * (node.col_offset + 4)
                edits.append((node.lineno, node, _format_docstring(indent, FunctionSpec(_class_summary(node), (), None, ()))))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            existing = ast.get_docstring(node, clean=False)
            spec = _function_spec(node)
            needs_fix = rewrite or not _contains_chinese(existing)
            doc = existing or ""
            if spec.params and "Args:" not in doc:
                needs_fix = True
            if spec.returns is not None and "Returns:" not in doc and "Yields:" not in doc:
                needs_fix = True
            if spec.raises and "Raises:" not in doc:
                needs_fix = True
            if needs_fix:
                indent = " " * (node.col_offset + 4)
                edits.append((node.lineno, node, _format_docstring(indent, spec)))
    if not edits and module_edit is None:
        return False
    for _line, node, doc_lines in sorted(edits, key=lambda item: item[0], reverse=True):
        _replace_docstring(lines, node, doc_lines)
    if module_edit is not None:
        _replace_docstring(lines, *module_edit)
    updated = "\n".join(lines) + "\n"
    try:
        ast.parse(updated)
    except SyntaxError as exc:
        raise RuntimeError(f"自动补齐后语法错误：{path}: {exc}") from exc
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def _docstring_sections(doc: str) -> dict[str, list[str]]:
    """解析 docstring 的 Google 风格章节。

    Args:
        doc: `doc` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 dict[str, list[str]]。

    """
    sections: dict[str, list[str]] = {}
    current = ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped in {"Args:", "Returns:", "Yields:", "Raises:"}:
            current = stripped[:-1]
            sections[current] = []
        elif current and stripped:
            sections[current].append(stripped)
    return sections


def _validate_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """校验单个函数的 docstring 完整性。

    Args:
        node: `node` 输入参数，类型为 ast.FunctionDef | ast.AsyncFunctionDef。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    errors = []
    doc = ast.get_docstring(node, clean=False)
    prefix = f"{node.name}:{node.lineno}"
    if not _contains_chinese(doc):
        errors.append(f"{prefix} 缺少中文 docstring")
        return errors
    sections = _docstring_sections(doc or "")
    spec = _function_spec(node)
    if spec.params and "Args" not in sections:
        errors.append(f"{prefix} 缺少 Args 章节")
    for name, _description in spec.params:
        if not any(line.startswith(f"{name}:") for line in sections.get("Args", [])):
            errors.append(f"{prefix} Args 缺少参数 {name}")
    if spec.returns is not None and "Returns" not in sections and "Yields" not in sections:
        errors.append(f"{prefix} 缺少 Returns/Yields 章节")
    if spec.raises and "Raises" not in sections:
        errors.append(f"{prefix} 缺少 Raises 章节")
    for name, _description in spec.raises:
        if not any(line.startswith(f"{name}:") for line in sections.get("Raises", [])):
            errors.append(f"{prefix} Raises 缺少异常 {name}")
    return errors


def _validate_file(path: Path) -> list[str]:
    """校验单个文件及其节点是否符合注释门禁。

    Args:
        path: `path` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    errors = []
    module_doc = ast.get_docstring(tree, clean=False)
    if not _contains_chinese(module_doc) or "模块" not in (module_doc or ""):
        errors.append("模块缺少中文作用说明")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and not _contains_chinese(ast.get_docstring(node, clean=False)):
            errors.append(f"{node.name}:{node.lineno} 缺少中文类说明")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors.extend(_validate_function(node))
    return errors


def main() -> int:
    """命令行入口：检查或补齐 Python docstring。

    Returns:
        函数处理结果，类型为 int。

    """
    parser = argparse.ArgumentParser(description="检查或补齐中文 Google 风格 docstring")
    parser.add_argument("--fix", action="store_true", help="自动补齐缺失注释")
    parser.add_argument("--rewrite", action="store_true", help="统一重写所有自动生成的注释")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    files = _iter_python_files(args.root)
    if args.fix:
        changed = [path for path in files if _fix_file(path, rewrite=args.rewrite)]
        print(f"已更新 {len(changed)} 个文件的 docstring")
    failures = []
    for path in _iter_python_files(args.root):
        try:
            errors = _validate_file(path)
        except SyntaxError as exc:
            errors = [f"语法错误：{exc}"]
        if errors:
            failures.append((path, errors))
    if failures:
        for path, errors in failures:
            print(f"{path}:")
            for error in errors[:20]:
                print(f"  - {error}")
        print(f"注释门禁失败：{len(failures)} 个文件")
        return 1
    print(f"注释门禁通过：{len(files)} 个 Python 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
