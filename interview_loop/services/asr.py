"""语音识别模块，负责火山引擎 ASR 适配和 Demo 占位识别。"""
import base64
from uuid import uuid4

import requests

from interview_loop.config import DEMO_MODE, VOLC_ASR_RESOURCE_ID
from interview_loop.services.common import parse_api_response
from interview_loop.services.demo import DEMO_ANSWER
from interview_loop.services.speech_common import volc_auth_headers


def audio2text(audio_bytes: bytes) -> str:
    """把音频转写为文本。

    Args:
        audio_bytes: `audio_bytes` 输入参数，类型为 bytes。

    Returns:
        函数处理结果，类型为 str。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    if DEMO_MODE:
        return DEMO_ANSWER
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
