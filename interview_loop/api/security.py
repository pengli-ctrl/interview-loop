"""API 鉴权模块，负责 API Key、租户、用户和权限请求头的解析与校验。"""
from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    """身份。"""
    tenant_id: str
    user_id: str
    permissions: frozenset[str]


def get_principal(request: Request, configured_api_key: str = "") -> Principal:
    """获取身份。

    Args:
        request: `request` 输入参数，类型为 Request。
        configured_api_key: `configured_api_key` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 Principal。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出 HTTPException。

    """
    if configured_api_key:
        supplied_key = request.headers.get("X-API-Key", "")
        if not compare_digest(supplied_key, configured_api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

    permissions = frozenset(
        item.strip()
        for item in request.headers.get("X-Permissions", "").split(",")
        if item.strip()
    )
    return Principal(
        tenant_id=request.headers.get("X-Tenant-Id", "default"),
        user_id=request.headers.get("X-User-Id", "anonymous"),
        permissions=permissions,
    )
