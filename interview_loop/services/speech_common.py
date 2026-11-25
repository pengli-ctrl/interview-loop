"""语音公共模块，负责语音服务请求构造和响应处理辅助逻辑。"""
from interview_loop.config import VOLC_API_KEY, VOLC_APPID, VOLC_TOKEN
from interview_loop.services.common import require_config


def volc_auth_headers(service: str) -> dict[str, str]:
    """构造火山引擎鉴权请求头。

    Args:
        service: `service` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 dict[str, str]。

    """
    if VOLC_API_KEY:
        return {"X-Api-Key": VOLC_API_KEY}

    require_config(VOLC_APPID, VOLC_TOKEN)
    common = {"X-Api-Access-Key": VOLC_TOKEN}
    if service == "tts":
        return {**common, "X-Api-App-Id": VOLC_APPID}
    return {**common, "X-Api-App-Key": VOLC_APPID}
