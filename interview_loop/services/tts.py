import base64
import json
from uuid import uuid4

import requests

from interview_loop.config import VOICE_TYPE, VOLC_TTS_RESOURCE_ID
from interview_loop.services.speech_common import volc_auth_headers


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
