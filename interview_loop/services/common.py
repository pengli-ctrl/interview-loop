import requests


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
