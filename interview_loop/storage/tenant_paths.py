import re
from pathlib import Path

_SAFE_TENANT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_tenant_segment(tenant_id: str) -> str:
    cleaned = _SAFE_TENANT_RE.sub("_", str(tenant_id)).strip("._")
    return cleaned or "tenant"


def tenant_scoped_dir(base: Path, tenant_id: str, *, local_tenant: str = "local") -> Path:
    if tenant_id == local_tenant:
        return base
    return base / "tenants" / safe_tenant_segment(tenant_id)
