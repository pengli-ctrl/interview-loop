import base64
import hashlib
import io
import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

import openai
import pandas as pd
import requests
import streamlit as st



st.set_page_config(page_title="全真大厂面试模拟器", layout="wide")

from interview_loop.config import (
    GLOBAL_STATS_PATH,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_RESUME_BYTES,
    MODE_CONFIG,
    MODE_LIST,
    RECORD_DIR,
    SAVE_DIR,
    STYLE_LIST,
    VOICE_TYPE,
    VOLC_APPID,
    VOLC_API_KEY,
    VOLC_ASR_RESOURCE_ID,
    VOLC_TOKEN,
    VOLC_TTS_RESOURCE_ID,
)


# ===================== 持久化与初始化 =====================
def new_session_id() -> str:
    return f"session_{int(time.time() * 1000)}"


def list_session_files() -> list[Path]:
    try:
        return sorted(SAVE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def _atomic_write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def load_global_weak_stats() -> dict:
    empty_stats = {mode: {} for mode in MODE_LIST}
    if not GLOBAL_STATS_PATH.exists():
        return empty_stats

    try:
        raw = json.loads(GLOBAL_STATS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        st.warning(f"薄弱统计文件损坏，已使用空统计：{exc}")
        return empty_stats

    if not isinstance(raw, dict):
        return empty_stats

    stats = {}
    for mode in MODE_LIST:
        mode_stats = raw.get(mode, {})
        if not isinstance(mode_stats, dict):
            mode_stats = {}
        cleaned = {}
        for tag, count in mode_stats.items():
            try:
                cleaned[str(tag)] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        stats[mode] = cleaned
    return stats


def save_global_weak_stats(stats: dict) -> None:
    _atomic_write_text(
        GLOBAL_STATS_PATH,
        json.dumps(stats, ensure_ascii=False, indent=2),
    )


def _safe_filename_part(value: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid or ord(char) < 32 else char for char in str(value))
    return cleaned.strip(" .") or "未命名"


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "未记录"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def build_markdown_record(data: dict) -> str:
    lines = [
        "# 面试记录",
        "",
        f"- 面试开始时间：{data.get('started_at', '未知')}",
        f"- 面试结束时间：{data.get('completed_at', '未知')}",
        f"- 面试轮次：{data.get('mode', '未知')}",
        f"- 面试模式：{data.get('interview_type', '未知')}",
        f"- 面试风格：{data.get('style', '未知')}",
        f"- 面试时长：{_format_duration(data.get('duration_seconds'))}",
        f"- 会话 ID：{data.get('session_id', '未知')}",
        "",
        "## 面试对话",
        "",
    ]

    turns = []
    pending_question = ""
    for message in data.get("messages", []):
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role == "interviewer":
            if pending_question:
                turns.append((pending_question, ""))
            pending_question = content
        elif role == "candidate":
            turns.append((pending_question, content))
            pending_question = ""
    if pending_question:
        turns.append((pending_question, ""))

    if not turns:
        lines.extend(["暂无对话记录。", ""])
    for index, (question, answer) in enumerate(turns, start=1):
        lines.extend(
            [
                f"### 第 {index} 题",
                "",
                "**面试官：**",
                "",
                question or "（未记录）",
                "",
                "**候选人：**",
                "",
                answer or "（未回答）",
                "",
            ]
        )

    lines.extend(
        [
            "## 面试复盘报告",
            "",
            str(data.get("feedback") or "暂无复盘报告").strip(),
            "",
            "## 薄弱标签",
            "",
        ]
    )
    tags = data.get("tags") or []
    if tags:
        lines.extend(f"- {tag}" for tag in tags)
    else:
        lines.append("暂无标签")
    lines.append("")
    return "\n".join(lines)


def save_session(mode: str, messages: list, feedback: str, tags: list[str]) -> Path:
    started_at = st.session_state.get("interview_started_at") or time.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )
    duration_seconds = None
    if st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))

    data = {
        "time": started_at.replace("_", " "),
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration_seconds,
        "session_id": st.session_state.session_id,
        "mode": mode,
        "interview_type": st.session_state.interview_type,
        "style": st.session_state.style,
        "messages": messages,
        "feedback": feedback,
        "tags": tags,
    }
    json_path = SAVE_DIR / f"{st.session_state.session_id}.json"
    _atomic_write_text(json_path, json.dumps(data, ensure_ascii=False, indent=2))

    filename = "_".join(
        [
            _safe_filename_part(started_at),
            _safe_filename_part(mode),
            _safe_filename_part(st.session_state.interview_type),
            _safe_filename_part(st.session_state.style),
        ]
    ) + ".md"
    markdown_path = RECORD_DIR / filename
    markdown = build_markdown_record(data)
    _atomic_write_text(markdown_path, markdown)
    st.session_state.last_record_path = str(markdown_path)
    st.session_state.last_record_markdown = markdown
    st.session_state.session_list = list_session_files()
    return json_path


# 初始化 session state
defaults = {
    "mode": MODE_LIST[0],
    "interview_type": "闯关全真面试",
    "current_stage_idx": 0,
    "stage_main_index": 0,
    "stage_followup_count": 0,
    "messages": [],
    "current_question": "",
    "feedback": None,
    "session_id": new_session_id(),
    "resume_retriever": None,
    "resume_signature": None,
    "resume_name": None,
    "resume_chars": 0,
    "resume_error": None,
    "resume_rag_mode": None,
    "question_audio": None,
    "question_audio_error": None,
    "last_audio_digest": None,
    "global_weak_stats": load_global_weak_stats(),
    "start_time": None,
    "timer_alert": False,
    "interview_started_at": None,
    "last_record_path": None,
    "last_record_markdown": None,
    "session_list": list_session_files(),
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)
st.session_state.setdefault("style", MODE_CONFIG[st.session_state.mode]["default_style"])

# 60 分钟面试：每阶段按主问题计划执行，并根据回答动态追问。
if st.session_state.get("interview_flow_version") != 4:
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.current_question = ""
    st.session_state.start_time = None
    st.session_state.interview_started_at = None
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.session_id = new_session_id()
    st.session_state.interview_flow_version = 4


def reset_interview_state() -> None:
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.current_question = ""
    st.session_state.question_audio = None
    st.session_state.question_audio_error = None
    st.session_state.session_id = new_session_id()
    st.session_state.start_time = None
    st.session_state.timer_alert = False
    st.session_state.interview_started_at = None
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
# ===================== 简历解析与 RAG =====================
def _decode_resume_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请将简历另存为 UTF-8 后重试")


def extract_resume_text(upload) -> str:
    data = upload.getvalue()
    if len(data) > MAX_RESUME_BYTES:
        raise ValueError("简历文件超过 10 MB，请压缩或删除图片后重试")

    filename = upload.name.lower()
    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError as exc:
                raise RuntimeError("缺少 PDF 解析依赖，请安装 pypdf") from exc

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception as exc:
                    raise ValueError("PDF 已加密，无法读取") from exc
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{exc}") from exc
        return "\n".join(page for page in pages if page)

    return _decode_resume_text(data)


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_CACHE_NAME = "models--sentence-transformers--all-MiniLM-L6-v2"


def has_local_embedding_model() -> bool:
    try:
        hf_home = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
        model_dir = hf_home / "hub" / EMBEDDING_CACHE_NAME
        snapshots_dir = model_dir / "snapshots"
        if snapshots_dir.is_dir() and any(
            (snapshot / "modules.json").is_file()
            for snapshot in snapshots_dir.iterdir()
            if snapshot.is_dir()
        ):
            return True
        legacy_dir = Path.home() / ".cache" / "torch" / "sentence_transformers" / (
            "sentence-transformers_all-MiniLM-L6-v2"
        )
        return (legacy_dir / "modules.json").is_file()
    except OSError:
        return False


@st.cache_resource(show_spinner=False)
def get_embeddings():
    from langchain_community.embeddings import SentenceTransformerEmbeddings

    # 只加载本机已有模型，避免上传时因无法访问 HuggingFace 长时间卡住。
    return SentenceTransformerEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"local_files_only": True},
    )


def build_rag(text: str):
    try:
        import jieba
        from langchain.retrievers import EnsembleRetriever
        from langchain_community.retrievers import BM25Retriever
        from langchain_community.vectorstores import FAISS
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise RuntimeError(f"缺少 RAG 依赖：{exc}") from exc

    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    chunks = [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
    if not chunks:
        raise ValueError("简历没有可用的文本内容")

    bm25 = BM25Retriever.from_texts(chunks, preprocess_func=jieba.lcut)
    bm25.k = 2
    if not has_local_embedding_model():
        return bm25, "BM25 本地关键词"

    try:
        embeddings = get_embeddings()
        faiss_store = FAISS.from_texts(chunks, embeddings)
        retriever = EnsembleRetriever(
            retrievers=[bm25, faiss_store.as_retriever()],
            weights=[0.5, 0.5],
        )
        return retriever, "BM25 + 本地向量"
    except Exception:
        # 向量模型未缓存或加载失败时退回纯关键词检索，保证离线也能使用。
        return bm25, "BM25 本地关键词"


def rag_query(query: str) -> str:
    retriever = st.session_state.get("resume_retriever")
    if retriever is None:
        return ""
    try:
        docs = retriever.invoke(query or "候选人的简历与项目经历")
        return "\n".join(doc.page_content for doc in docs)
    except Exception:
        return ""


# ===================== 模型与语音服务 =====================
def require_config(*values: str) -> None:
    if any(not value for value in values):
        raise RuntimeError("缺少必要配置，请检查 .streamlit/secrets.toml 或环境变量")


def parse_api_response(response: requests.Response, service: str) -> dict:
    try:
        result = response.json()
    except ValueError as exc:
        detail = response.text[:300].strip() or "响应不是 JSON"
        raise RuntimeError(f"{service} HTTP {response.status_code}：{detail}") from exc

    if not response.ok:
        header = result.get("header", {}) if isinstance(result, dict) else {}
        message = (
            result.get("message")
            or header.get("message")
            or result.get("error")
            or response.text[:300]
        )
        raise RuntimeError(f"{service} HTTP {response.status_code}：{message}")
    return result


def llm_call(system_prompt: str, user_msg: str) -> str:
    require_config(LLM_API_KEY)
    try:
        client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=90)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
    except Exception as exc:
        raise RuntimeError(f"大模型调用失败：{exc}") from exc

    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("大模型返回了空内容")
    return content


def volc_auth_headers(service: str) -> dict[str, str]:
    """同时兼容新版 API Key 单头和 AppID + AccessToken 双头。"""
    if VOLC_API_KEY:
        return {"X-Api-Key": VOLC_API_KEY}

    require_config(VOLC_APPID, VOLC_TOKEN)
    common = {"X-Api-Access-Key": VOLC_TOKEN}
    if service == "tts":
        return {**common, "X-Api-App-Id": VOLC_APPID}
    return {**common, "X-Api-App-Key": VOLC_APPID}


def audio2text(audio_bytes: bytes) -> str:
    if not audio_bytes:
        raise ValueError("录音内容为空")

    url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    headers = {
        **volc_auth_headers("asr"),
        "X-Api-Resource-Id": VOLC_ASR_RESOURCE_ID,
        "X-Api-Request-Id": uuid4().hex,
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    payload = {
        "user": {"uid": "interview_coach"},
        "audio": {"data": base64.b64encode(audio_bytes).decode()},
        "request": {
            "model_name": "bigmodel",
            "enable_punc": True,
            "enable_itn": True,
            "enable_ddc": False,
            "show_utterances": True,
        },
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        result = parse_api_response(response, "ASR")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"ASR 请求失败：{exc}") from exc

    body_header = result.get("header", {}) if isinstance(result, dict) else {}
    status_code = str(
        response.headers.get("X-Api-Status-Code")
        or body_header.get("code")
        or ""
    ).strip()
    status_message = str(
        response.headers.get("X-Api-Message")
        or body_header.get("message")
        or ""
    ).strip()
    if status_code == "20000003":
        return ""
    if status_code and status_code != "20000000":
        detail = status_message or str(result)[:300]
        raise RuntimeError(f"ASR 识别失败：code {status_code} {detail}")

    try:
        return str(result["result"]["text"]).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"ASR 返回格式异常：{str(result)[:300]}") from exc


def text2audio(text: str) -> bytes:
    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    headers = {
        **volc_auth_headers("tts"),
        "X-Api-Resource-Id": VOLC_TTS_RESOURCE_ID,
        "X-Api-Request-Id": uuid4().hex,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "X-Control-Require-Usage-Tokens-Return": "*",
    }
    payload = {
        "user": {"uid": "interview_coach"},
        "req_params": {
            "text": text,
            "speaker": VOICE_TYPE,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
            },
        },
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=(10, 120),
            stream=True,
        )
    except Exception as exc:
        raise RuntimeError(f"TTS 请求失败：{exc}") from exc

    if not response.ok:
        detail = response.text[:500].strip()
        try:
            error_data = response.json()
            detail = (
                error_data.get("message")
                or error_data.get("header", {}).get("message")
                or detail
            )
        except ValueError:
            pass
        raise RuntimeError(f"TTS HTTP {response.status_code}：{detail}")

    audio_chunks: list[bytes] = []
    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            header = event.get("header", {}) if isinstance(event, dict) else {}
            code = int(event.get("code", header.get("code", 0)) or 0)
            message = event.get("message") or header.get("message") or ""
            if code == 20000000:
                break
            if code != 0:
                raise RuntimeError(f"TTS 合成失败：code {code} {message}")

            audio_base64 = event.get("data")
            if audio_base64:
                audio_chunks.append(base64.b64decode(audio_base64))
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"TTS 响应解析失败：{exc}") from exc
    finally:
        response.close()

    if not audio_chunks:
        raise RuntimeError("TTS 合成失败：接口没有返回音频数据")
    return b"".join(audio_chunks)


def set_question_audio(question: str) -> None:
    try:
        st.session_state.question_audio = text2audio(question)
        st.session_state.question_audio_error = None
    except Exception as exc:
        st.session_state.question_audio = None
        st.session_state.question_audio_error = str(exc)
# ===================== 面试业务 =====================
def extract_tags(review_text: str, valid_tags: list[str]) -> list[str]:
    prompt = f"""从下面复盘文本提取标签，只输出 JSON 数组，例如 ["Temporal", "落地细节"]。
标签只能从列表选择：{",".join(valid_tags)}
文本：{review_text}"""
    try:
        raw = llm_call("", prompt).strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end < start:
            return []
        parsed = json.loads(raw[start : end + 1])
        return [tag for tag in parsed if tag in valid_tags]
    except Exception:
        return []


def update_global_stats(mode: str, tags: list[str]) -> None:
    mode_stats = st.session_state.global_weak_stats.setdefault(mode, {})
    for tag in tags:
        mode_stats[tag] = mode_stats.get(tag, 0) + 1
    save_global_weak_stats(st.session_state.global_weak_stats)


def _questions_too_similar(new_question: str, previous_question: str) -> bool:
    def normalize(value: str) -> str:
        return "".join(char.lower() for char in value if char.isalnum())

    left = normalize(new_question)
    right = normalize(previous_question)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def should_generate_followup(answer: str, stage: dict, followup_count: int) -> bool:
    max_followups = max(0, int(stage.get("max_followups", 0)))
    if followup_count >= max_followups:
        return False
    cleaned = answer.strip()
    if len(cleaned) < 40:
        return False
    return not any(keyword in cleaned for keyword in ("不知道", "没做过", "跳过", "不了解", "不会"))


def get_stage_question(
    mode: str,
    stage_idx: int,
    resume_ctx: str,
    weak_stats: dict,
    main_index: int,
    followup_index: int = 0,
    is_followup: bool = False,
    previous_question: str = "",
    last_answer: str = "",
) -> str:
    cfg = MODE_CONFIG[mode]
    stage = cfg["stage_list"][stage_idx]
    question_plan = stage.get("question_plan") or stage.get("pool") or [stage["desc"]]
    main_total = max(1, len(question_plan))
    main_index = min(max(0, main_index), main_total - 1)
    max_followups = max(0, int(stage.get("max_followups", 0)))
    current_topic = question_plan[main_index]
    weak_tags = [
        key for key, _ in sorted(weak_stats.items(), key=lambda item: item[1], reverse=True)
    ]
    question_type = "追问" if is_followup else "主问题"
    system_prompt = f"""你是【{mode}】面试官，风格：{st.session_state.style}。
当前面试阶段：{stage['name']}，考察方向：{stage['desc']}
本阶段主问题计划：{question_plan}
当前主问题：第 {main_index + 1}/{main_total} 个：{current_topic}
本题类型：{question_type}
追问进度：{followup_index}/{max_followups}
规则：
1. 主问题必须覆盖当前主问题目标，不要提前跳到后续主问题；
2. 如果是追问，必须基于候选人的上一轮回答继续深挖，不能重复上一题；
3. 薄弱标签参考：{weak_tags}
4. 简历上下文：{resume_ctx}
5. 输出只输出题目，不要多余解释；
6. 问题和追问必须严格停留在当前阶段【{stage['name']}】（{stage['desc']}），不得提前进入后续面试阶段；
7. 当前阶段是自我介绍时，只能围绕个人经历、职责范围、技术方向和职业动机，不得追问具体项目架构、技术方案、线上故障或系统设计细节。
上一题：{previous_question or "无"}
候选人回答：{last_answer or "无"}"""
    question = llm_call(system_prompt, "请给出当前这一题")
    if previous_question and last_answer and _questions_too_similar(question, previous_question):
        repair_prompt = system_prompt + """
你上一次生成的问题与上一题过于相似。请重新生成一个不同的题目；如果是追问，必须针对候选人回答中的具体内容。"""
        question = llm_call(repair_prompt, "请重新给出一个不同的问题")
    if previous_question and last_answer and _questions_too_similar(question, previous_question):
        answer_excerpt = last_answer.strip().replace("\n", " ")[:60]
        question = (
            f"你刚才提到“{answer_excerpt}”，请继续围绕当前主问题“{current_topic}”"
            f"说明具体经历、思路和结果，不要提前进入后续阶段。"
        )
    return question


def get_weak_question(mode: str) -> str:
    stats = st.session_state.global_weak_stats[mode]
    if not stats:
        return MODE_CONFIG[mode]["stage_list"][0]["pool"][0]
    top_tag = max(stats.items(), key=lambda item: item[1])[0]
    prompt = f"【{mode}】薄弱点：{top_tag}，生成一道面试题，只输出题目。"
    return llm_call("你是面试出题专家", prompt)


def generate_review(mode_cfg: dict) -> bool:
    if not st.session_state.messages:
        st.warning("还没有对话记录，至少回答一道题后再生成复盘")
        return False

    tag_list = mode_cfg["tags"]
    reviewer_prompt = f"""你是面试评审，轮次：{st.session_state.mode}，风格：{st.session_state.style}。
输出固定结构：
1. 📊 打分（架构深度、落地细节、表达流畅度，0-10）
2. ✅ 优点
3. ❌ 不足（附带标签，标签只能从{tag_list}）
4. 📝 口述优化版本
5. 📚 知识点补充
6. 💡 练习建议
对话记录：{json.dumps(st.session_state.messages, ensure_ascii=False)}"""
    try:
        feedback = llm_call(reviewer_prompt, "")
    except Exception as exc:
        st.error(str(exc))
        return False

    st.session_state.feedback = feedback
    tags = extract_tags(feedback, tag_list)
    try:
        update_global_stats(st.session_state.mode, tags)
    except Exception as exc:
        st.warning(f"薄弱统计更新失败：{exc}")
    try:
        save_session(st.session_state.mode, st.session_state.messages, feedback, tags)
    except Exception as exc:
        st.warning(f"复盘已生成，但保存失败：{exc}")
    return True


def process_answer(ans_text: str, mode_cfg: dict) -> bool:
    st.session_state.messages.append(
        {"role": "interviewer", "content": st.session_state.current_question}
    )
    st.session_state.messages.append({"role": "candidate", "content": ans_text})

    if "结束面试" in ans_text:
        return generate_review(mode_cfg)

    ctx = rag_query(f"{st.session_state.current_question}\n{ans_text}")
    if st.session_state.interview_type == "闯关全真面试":
        current_stage = mode_cfg["stage_list"][st.session_state.current_stage_idx]
        question_plan = current_stage.get("question_plan") or current_stage["pool"]
        main_total = max(1, len(question_plan))
        main_index = st.session_state.stage_main_index
        followup_count = st.session_state.stage_followup_count

        if should_generate_followup(ans_text, current_stage, followup_count):
            next_followup = followup_count + 1
            try:
                question = get_stage_question(
                    st.session_state.mode,
                    st.session_state.current_stage_idx,
                    ctx,
                    st.session_state.global_weak_stats[st.session_state.mode],
                    main_index,
                    next_followup,
                    True,
                    previous_question=st.session_state.current_question,
                    last_answer=ans_text,
                )
            except Exception as exc:
                st.error(str(exc))
                return False
            st.session_state.stage_followup_count = next_followup
        else:
            next_main_index = main_index + 1
            if next_main_index < main_total:
                try:
                    question = get_stage_question(
                        st.session_state.mode,
                        st.session_state.current_stage_idx,
                        ctx,
                        st.session_state.global_weak_stats[st.session_state.mode],
                        next_main_index,
                        0,
                        False,
                        previous_question=st.session_state.current_question,
                        last_answer=ans_text,
                    )
                except Exception as exc:
                    st.error(str(exc))
                    return False
                st.session_state.stage_main_index = next_main_index
                st.session_state.stage_followup_count = 0
            else:
                next_stage_idx = st.session_state.current_stage_idx + 1
                if next_stage_idx >= len(mode_cfg["stage_list"]):
                    question = "本次面试所有阶段完成，你可以说【结束面试】或点击 Finish 生成复盘。"
                else:
                    try:
                        question = get_stage_question(
                            st.session_state.mode,
                            next_stage_idx,
                            ctx,
                            st.session_state.global_weak_stats[st.session_state.mode],
                            0,
                            0,
                            False,
                            previous_question=st.session_state.current_question,
                            last_answer=ans_text,
                        )
                    except Exception as exc:
                        st.error(str(exc))
                        return False
                st.session_state.current_stage_idx = next_stage_idx
                st.session_state.stage_main_index = 0
                st.session_state.stage_followup_count = 0
    else:
        try:
            question = get_weak_question(st.session_state.mode)
        except Exception as exc:
            st.error(str(exc))
            return False

    st.session_state.current_question = question
    set_question_audio(question)
    return True


@st.fragment(run_every="1s", key="interview_timer_fragment")
def render_interview_timer() -> None:
    elapsed = time.time() - st.session_state.start_time
    remain = max(0, 60 * 60 - elapsed)
    minutes, seconds = int(remain // 60), int(remain % 60)
    st.metric("⏱️ 剩余面试时间", f"{minutes}分{seconds}秒")
    if remain <= 0 and not st.session_state.timer_alert:
        st.warning("⚠️ 60 分钟面试时长到，建议结束面试生成复盘")
        st.session_state.timer_alert = True


# ===================== UI =====================
st.title("🎙️ 全真大厂面试模拟器｜闯关 + 专项双模式")

col0_1, col0_2, col0_3 = st.columns([1, 1, 1])
with col0_1:
    new_mode = st.selectbox(
        "👉 面试轮次",
        MODE_LIST,
        index=MODE_LIST.index(st.session_state.mode),
    )
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode
        st.session_state.style = MODE_CONFIG[new_mode]["default_style"]
        reset_interview_state()
        st.rerun()

with col0_2:
    new_it = st.radio(
        "面试模式",
        ["闯关全真面试", "薄弱专项练习"],
        horizontal=True,
        index=0 if st.session_state.interview_type == "闯关全真面试" else 1,
    )
    if new_it != st.session_state.interview_type:
        st.session_state.interview_type = new_it
        reset_interview_state()
        st.rerun()

with col0_3:
    st.session_state.style = st.selectbox(
        "面试官风格",
        STYLE_LIST,
        index=STYLE_LIST.index(st.session_state.style),
    )

mode_cfg = MODE_CONFIG[st.session_state.mode]
st.markdown(f"✅ 当前轮次：**{st.session_state.mode}**｜风格：**{st.session_state.style}**")

if st.session_state.interview_type == "闯关全真面试":
    stages = mode_cfg["stage_list"]
    total_stage = len(stages)
    cur_idx = st.session_state.current_stage_idx
    if cur_idx < total_stage:
        cur_stage = stages[cur_idx]
        question_plan = cur_stage.get("question_plan") or cur_stage["pool"]
        main_total = max(1, len(question_plan))
        main_current = min(st.session_state.stage_main_index + 1, main_total)
        max_followups = max(0, int(cur_stage.get("max_followups", 0)))
        followup_text = (
            f"｜追问 {st.session_state.stage_followup_count}/{max_followups}"
            if max_followups
            else ""
        )
        st.progress(
            (cur_idx + 1) / total_stage,
            text=(
                f"进度：阶段 {cur_idx + 1}/{total_stage}｜【{cur_stage['name']}】"
                f"｜主问题 {main_current}/{main_total}{followup_text}"
            ),
        )
        if st.button("⏭️ 跳过当前阶段", help="直接跳到下一阶段"):
            next_stage_idx = st.session_state.current_stage_idx + 1
            st.session_state.current_stage_idx = next_stage_idx
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            st.session_state.current_question = ""
            st.session_state.question_audio = None
            st.session_state.question_audio_error = None

            if st.session_state.start_time is not None:
                if next_stage_idx >= total_stage:
                    st.session_state.current_question = (
                        "本次面试所有阶段完成，你可以点击 Finish 生成复盘。"
                    )
                    st.rerun()
                else:
                    try:
                        with st.spinner("正在生成下一阶段题目..."):
                            next_question = get_stage_question(
                                st.session_state.mode,
                                next_stage_idx,
                                rag_query(""),
                                st.session_state.global_weak_stats[st.session_state.mode],
                                0,
                                0,
                                False,
                            )
                    except Exception as exc:
                        st.error(str(exc))
                        st.session_state.start_time = None
                    else:
                        st.session_state.current_question = next_question
                        set_question_audio(next_question)
                        st.rerun()
            else:
                st.rerun()
    else:
        st.success("🎉 所有面试阶段全部走完！")

col_main, col_side = st.columns([2, 1])
with col_main:
    upload = st.file_uploader(
        "📄 上传简历（txt/md/pdf），RAG 个性化出题",
        type=["txt", "md", "pdf"],
        key="resume_upload",
    )

    if upload is None:
        if st.session_state.resume_signature is not None:
            st.session_state.resume_signature = None
            st.session_state.resume_retriever = None
            st.session_state.resume_name = None
            st.session_state.resume_chars = 0
            st.session_state.resume_error = None
            st.session_state.resume_rag_mode = None
    else:
        file_bytes = upload.getvalue()
        signature = hashlib.sha256(file_bytes).hexdigest()
        if signature != st.session_state.resume_signature:
            st.session_state.resume_signature = signature
            st.session_state.resume_retriever = None
            st.session_state.resume_error = None
            st.session_state.resume_rag_mode = None
            st.session_state.resume_name = upload.name
            st.session_state.resume_chars = 0
            try:
                with st.spinner("正在解析简历并构建 RAG 索引，只需执行一次..."):
                    resume_text = extract_resume_text(upload)
                    if not resume_text.strip():
                        raise ValueError("简历没有可提取的文本；扫描版 PDF 请先做 OCR")
                    retriever, rag_mode = build_rag(resume_text)
                    st.session_state.resume_retriever = retriever
                    st.session_state.resume_rag_mode = rag_mode
                    st.session_state.resume_chars = len(resume_text)
            except Exception as exc:
                st.session_state.resume_error = str(exc)

        if st.session_state.resume_error:
            st.error(f"简历加载失败：{st.session_state.resume_error}")
        elif st.session_state.resume_retriever is not None:
            st.caption(
                f"已加载简历：{st.session_state.resume_name}｜"
                f"{st.session_state.resume_chars} 字符｜"
                f"检索模式：{st.session_state.resume_rag_mode}｜后续重跑不会重复解析"
            )
    if st.session_state.start_time is None:
        if st.button("▶️ 开始面试计时", key="start_interview"):
            if (
                st.session_state.interview_type == "闯关全真面试"
                and st.session_state.current_stage_idx >= len(mode_cfg["stage_list"])
            ):
                st.warning("所有阶段已完成，可以点击 Finish 生成复盘或开启新一轮")
            else:
                try:
                    with st.spinner("正在生成第一道题..."):
                        ctx = rag_query("")
                        if st.session_state.interview_type == "闯关全真面试":
                            question = get_stage_question(
                                st.session_state.mode,
                                st.session_state.current_stage_idx,
                                ctx,
                                st.session_state.global_weak_stats[st.session_state.mode],
                                st.session_state.stage_main_index,
                                st.session_state.stage_followup_count,
                                st.session_state.stage_followup_count > 0,
                            )
                        else:
                            question = get_weak_question(st.session_state.mode)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.session_state.start_time = time.time()
                    st.session_state.interview_started_at = time.strftime(
                        "%Y-%m-%d_%H-%M-%S"
                    )
                    st.session_state.current_question = question
                    set_question_audio(question)
                    st.rerun()
    else:
        render_interview_timer()

    if st.session_state.current_question:
        st.subheader("👨‍💼 面试官问题")
        st.markdown(f"**{st.session_state.current_question}**")
        if st.session_state.question_audio:
            st.audio(st.session_state.question_audio, format="audio/mpeg")
        elif st.session_state.question_audio_error:
            st.caption(f"语音播放不可用：{st.session_state.question_audio_error}")

        answer_mode = st.radio(
            "选择回答方式",
            ["🎤 语音输入", "⌨️ 文字输入"],
            index=0,
            horizontal=True,
            key="answer_input_mode",
        )

        if answer_mode == "🎤 语音输入":
            audio_in = st.audio_input("🎤 点击录制回答", key="answer_audio")
            if audio_in is not None:
                audio_bytes = audio_in.getvalue()
                st.audio(audio_bytes, format="audio/wav")
                audio_digest = hashlib.sha256(audio_bytes).hexdigest()
                if audio_digest == st.session_state.last_audio_digest:
                    st.caption("这段录音已经处理过；请重新录制下一段回答")
                else:
                    # 先标记已处理，避免 Streamlit 重跑时重复识别同一段录音。
                    st.session_state.last_audio_digest = audio_digest
                    try:
                        with st.spinner("正在识别回答..."):
                            ans_text = audio2text(audio_bytes)
                    except Exception as exc:
                        st.error(str(exc))
                    else:
                        if not ans_text:
                            st.warning("没有识别到有效内容，请重新录制")
                        else:
                            st.success(f"✅ 识别回答：{ans_text}")
                            if process_answer(ans_text, mode_cfg):
                                st.rerun()
        else:
            with st.form("text_answer_form", clear_on_submit=True, border=True):
                text_answer = st.text_area(
                    "⌨️ 输入文字回答",
                    height=140,
                    placeholder="在这里输入你的回答，提交后与语音回答流程完全一致。",
                    key="text_answer",
                )
                text_submitted = st.form_submit_button(
                    "提交文字回答",
                    type="primary",
                    key="submit_text_answer",
                )
            if text_submitted:
                cleaned_answer = text_answer.strip()
                if not cleaned_answer:
                    st.warning("请输入文字回答后再提交")
                elif process_answer(cleaned_answer, mode_cfg):
                    st.rerun()

        if st.button("✅ Finish 结束面试，生成复盘", type="primary", key="finish_interview"):
            if generate_review(mode_cfg):
                st.rerun()

    if st.session_state.feedback:
        st.markdown("---")
        st.subheader("📝 面试复盘报告")
        st.markdown(st.session_state.feedback)

    if st.session_state.get("last_record_path"):
        st.success(f"完整面试记录已保存：{st.session_state.last_record_path}")
        if st.session_state.get("last_record_markdown"):
            st.download_button(
                "⬇️ 下载本次面试记录",
                data=st.session_state.last_record_markdown.encode("utf-8"),
                file_name=Path(st.session_state.last_record_path).name,
                mime="text/markdown",
                key="download_interview_record",
            )

    if st.button("🔄 开启新一轮【当前轮次】面试", key="new_round"):
        reset_interview_state()
        st.rerun()
with col_side:
    st.subheader("📊 分轮次薄弱统计")
    tabs = st.tabs(MODE_LIST)
    for idx, mode in enumerate(MODE_LIST):
        with tabs[idx]:
            mode_stats = st.session_state.global_weak_stats[mode]
            if mode_stats:
                df = pd.DataFrame(
                    list(mode_stats.items()),
                    columns=["标签", "次数"],
                ).sort_values("次数", ascending=False)
                st.dataframe(df, hide_index=True)
                if st.button(f"🗑️ 清空【{mode}】统计", key=f"clear_{mode}"):
                    st.session_state.global_weak_stats[mode] = {}
                    try:
                        save_global_weak_stats(st.session_state.global_weak_stats)
                    except Exception as exc:
                        st.error(f"保存薄弱统计失败：{exc}")
                    else:
                        st.rerun()
            else:
                st.write("暂无薄弱记录")

    st.subheader("📚 历史面试记录")
    st.session_state.session_list = list_session_files()
    for session_file in st.session_state.session_list:
        try:
            saved = json.loads(session_file.read_text(encoding="utf-8"))
            saved_mode = saved["mode"]
            if saved_mode not in MODE_CONFIG:
                raise ValueError("未知面试轮次")
        except Exception:
            st.caption(f"跳过损坏记录：{session_file.name}")
            continue

        label = (
            f"{saved.get('time', '未知时间')}｜{saved_mode}｜"
            f"{saved.get('interview_type', '未知模式')}"
        )
        if st.button(label, key=f"history_{session_file.stem}"):
            st.session_state.messages = saved.get("messages", [])
            st.session_state.feedback = saved.get("feedback")
            st.session_state.mode = saved_mode
            st.session_state.interview_type = saved.get(
                "interview_type", "闯关全真面试"
            )
            st.session_state.style = saved.get(
                "style", MODE_CONFIG[saved_mode]["default_style"]
            )
            st.session_state.current_stage_idx = 0
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            st.session_state.current_question = ""
            st.session_state.question_audio = None
            st.session_state.question_audio_error = None
            st.session_state.start_time = None
            st.session_state.timer_alert = False
            st.session_state.interview_started_at = saved.get("started_at")
            st.session_state.last_record_path = None
            st.session_state.last_record_markdown = None
            st.session_state.session_id = new_session_id()
            st.rerun()

st.caption(
    "全真面试模拟器｜60 分钟闯关流程、主问题与动态追问、文字/语音作答；"
    "专项模式专攻短板"
)