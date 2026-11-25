"""租户路径模块，负责租户标识清洗和存储目录隔离。"""
import re
from pathlib import Path

_SAFE_TENANT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_tenant_segment(tenant_id: str) -> str:
    """生成安全的租户目录名。

    Args:
        tenant_id: `tenant_id` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    cleaned = _SAFE_TENANT_RE.sub("_", str(tenant_id)).strip("._")
    return cleaned or "tenant"


def tenant_scoped_dir(base: Path, tenant_id: str, *, local_tenant: str = "local") -> Path:
    """返回租户作用域目录。

    Args:
        base: `base` 输入参数，类型为 Path。
        tenant_id: `tenant_id` 输入参数，类型为 str。
        local_tenant: `local_tenant` 关键字参数，类型为 str。

    Returns:
        函数处理结果，类型为 Path。

    """
    if tenant_id == local_tenant:
        return base
    return base / "tenants" / safe_tenant_segment(tenant_id)
