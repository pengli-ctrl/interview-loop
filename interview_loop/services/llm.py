import openai

from interview_loop.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from interview_loop.services.common import require_config


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
