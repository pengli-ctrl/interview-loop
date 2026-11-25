"""服务公共模块，负责外部服务配置校验与请求辅助。"""
import requests


def require_config(*values: str) -> None:
    """校验必要配置已提供。

    Args:
        *values: 可变位置参数，类型为 str。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    if any(not value for value in values):
        raise RuntimeError("缺少必要配置，请检查 .streamlit/secrets.toml 或环境变量")


def parse_api_response(response: requests.Response, service: str) -> dict:
    """解析外部服务响应并检查错误。

    Args:
        response: `response` 输入参数，类型为 requests.Response。
        service: `service` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 dict。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
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
