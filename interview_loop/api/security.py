from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    permissions: frozenset[str]


def get_principal(request: Request, configured_api_key: str = "") -> Principal:
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
