import base64
import hashlib
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from jsonschema import Draft202012Validator

from interview_loop.platform.privacy import redact_pii


class ToolNotFoundError(LookupError):
    pass


class ToolExecutionError(RuntimeError):
    pass


class ToolTimeoutError(ToolExecutionError):
    pass


class ToolPermissionError(PermissionError):
    pass


class ToolIdempotencyConflictError(RuntimeError):
    pass


class ToolSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    version: str = "v1"
    timeout_seconds: float = 30.0
    required_permission: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    max_retries: int = 0
    idempotent: bool = False
    idempotency_ttl_seconds: int = 300


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    output: Any
    duration_ms: int
    attempts: int = 1
    cached: bool = False
    tool_version: str = "v1"


@dataclass(frozen=True)
class ToolAuditEvent:
    tool_name: str
    event_type: str
    status: str
    tool_version: str
    tenant_id: str
    user_id: str
    run_id: str | None
    attempts: int
    duration_ms: int
    input_digest: str
    idempotency_key: str | None = None
    error: str | None = None

    def to_payload(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "status": self.status,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "input_digest": self.input_digest,
            "idempotency_key": self.idempotency_key,
            "error": redact_pii(self.error) if self.error else None,
        }


def _argument_digest(kwargs: dict[str, Any]) -> str:
    raw = repr(sorted(kwargs.items(), key=lambda item: item[0])).encode(
        "utf-8", errors="replace"
    )
    return hashlib.sha256(raw).hexdigest()[:16]


def _invoke_with_timeout(
    spec: ToolSpec,
    kwargs: dict[str, Any],
) -> Any:
    outcome: dict[str, Any] = {}

    def target() -> None:
        try:
            outcome["output"] = spec.handler(**kwargs)
        except BaseException as exc:
            if isinstance(exc, Exception):
                outcome["error"] = exc
            else:
                outcome["error"] = RuntimeError(
                    f"Tool aborted with {type(exc).__name__}"
                )

    thread = threading.Thread(
        target=target,
        name=f"tool:{spec.name}",
        daemon=True,
    )
    thread.start()
    thread.join(max(0.001, float(spec.timeout_seconds)))
    if thread.is_alive():
        raise ToolTimeoutError(
            f"{spec.name} timed out after {spec.timeout_seconds:g}s"
        )
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("output")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._cache_lock = threading.Lock()
        self._idempotency_locks: dict[tuple[str, str, str], threading.Lock] = {}
        self._cache_entries: dict[
            tuple[str, str, str], tuple[float, str, ToolResult]
        ] = {}
        self._cache_max_entries = 1000

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        if spec.timeout_seconds <= 0:
            raise ValueError("Tool timeout_seconds must be positive")
        if spec.max_retries < 0:
            raise ValueError("Tool max_retries must be non-negative")
        if spec.max_retries > 0 and not spec.idempotent:
            raise ValueError("Retries require an idempotent tool")
        if spec.idempotency_ttl_seconds <= 0:
            raise ValueError("Tool idempotency TTL must be positive")
        self._tools[spec.name] = spec

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(name) from exc

    def execute(
        self,
        name: str,
        /,
        *,
        permissions: set[str] | frozenset[str] | None = None,
        idempotency_key: str | None = None,
        tenant_id: str = "default",
        user_id: str = "anonymous",
        run_id: str | None = None,
        audit_sink: Callable[[ToolAuditEvent], None] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        spec = self.get(name)
        input_digest = _argument_digest(kwargs)
        if spec.required_permission and spec.required_permission not in (
            permissions or set()
        ):
            self._audit(
                audit_sink,
                ToolAuditEvent(
                    tool_name=name,
                    event_type="tool.denied",
                    status="denied",
                    tool_version=spec.version,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    run_id=run_id,
                    attempts=0,
                    duration_ms=0,
                    input_digest=input_digest,
                    idempotency_key=idempotency_key,
                    error=f"Missing permission: {spec.required_permission}",
                ),
            )
            raise ToolPermissionError(
                f"Missing permission: {spec.required_permission}"
            )

        try:
            self._validate_schema(spec.input_schema, kwargs, "input")
        except ToolSchemaError as exc:
            self._audit(
                audit_sink,
                ToolAuditEvent(
                    tool_name=name,
                    event_type="tool.schema_rejected",
                    status="schema_rejected",
                    tool_version=spec.version,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    run_id=run_id,
                    attempts=0,
                    duration_ms=0,
                    input_digest=input_digest,
                    idempotency_key=idempotency_key,
                    error=str(exc),
                ),
            )
            raise

        self._audit(
            audit_sink,
            ToolAuditEvent(
                tool_name=name,
                event_type="tool.started",
                status="started",
                tool_version=spec.version,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                attempts=0,
                duration_ms=0,
                input_digest=input_digest,
                idempotency_key=idempotency_key,
            ),
        )

        cache_key = (
            (tenant_id, name, idempotency_key)
            if idempotency_key
            else None
        )
        if cache_key is None:
            return self._execute_with_retries(
                spec=spec,
                kwargs=kwargs,
                audit_sink=audit_sink,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                input_digest=input_digest,
                idempotency_key=idempotency_key,
            )

        with self._lock_for(cache_key):
            try:
                cached = self._get_cached(cache_key, input_digest)
            except ToolIdempotencyConflictError as exc:
                self._audit(
                    audit_sink,
                    ToolAuditEvent(
                        tool_name=name,
                        event_type="tool.idempotency_conflict",
                        status="conflict",
                        tool_version=spec.version,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        run_id=run_id,
                        attempts=0,
                        duration_ms=0,
                        input_digest=input_digest,
                        idempotency_key=idempotency_key,
                        error=str(exc),
                    ),
                )
                raise
            if cached is not None:
                result = replace(cached, cached=True)
                self._audit(
                    audit_sink,
                    ToolAuditEvent(
                        tool_name=name,
                        event_type="tool.cache_hit",
                        status="cached",
                        tool_version=spec.version,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        run_id=run_id,
                        attempts=0,
                        duration_ms=0,
                        input_digest=input_digest,
                        idempotency_key=idempotency_key,
                    ),
                )
                return result

            result = self._execute_with_retries(
                spec=spec,
                kwargs=kwargs,
                audit_sink=audit_sink,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                input_digest=input_digest,
                idempotency_key=idempotency_key,
            )
            self._put_cached(
                cache_key,
                result,
                spec.idempotency_ttl_seconds,
                input_digest,
            )
            return result

    def _execute_with_retries(
        self,
        *,
        spec: ToolSpec,
        kwargs: dict[str, Any],
        audit_sink: Callable[[ToolAuditEvent], None] | None,
        tenant_id: str,
        user_id: str,
        run_id: str | None,
        input_digest: str,
        idempotency_key: str | None,
    ) -> ToolResult:
        attempts_allowed = 1 + (spec.max_retries if spec.idempotent else 0)
        started = perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, attempts_allowed + 1):
            try:
                output = _invoke_with_timeout(spec, kwargs)
            except ToolTimeoutError as exc:
                last_error = exc
                if attempt < attempts_allowed:
                    self._audit_retry(
                        audit_sink,
                        spec,
                        tenant_id,
                        user_id,
                        run_id,
                        input_digest,
                        idempotency_key,
                        attempt,
                        exc,
                    )
                    continue
                duration_ms = int((perf_counter() - started) * 1000)
                self._audit_failure(
                    audit_sink,
                    spec,
                    "timeout",
                    tenant_id,
                    user_id,
                    run_id,
                    input_digest,
                    idempotency_key,
                    attempt,
                    duration_ms,
                    exc,
                )
                raise
            except Exception as exc:
                last_error = exc
                if attempt < attempts_allowed:
                    self._audit_retry(
                        audit_sink,
                        spec,
                        tenant_id,
                        user_id,
                        run_id,
                        input_digest,
                        idempotency_key,
                        attempt,
                        exc,
                    )
                    continue
                duration_ms = int((perf_counter() - started) * 1000)
                self._audit_failure(
                    audit_sink,
                    spec,
                    "failed",
                    tenant_id,
                    user_id,
                    run_id,
                    input_digest,
                    idempotency_key,
                    attempt,
                    duration_ms,
                    exc,
                )
                raise ToolExecutionError(
                    f"{spec.name} failed after {attempt} attempt(s): {exc}"
                ) from exc

            try:
                self._validate_schema(spec.output_schema, output, "output")
            except ToolSchemaError as exc:
                duration_ms = int((perf_counter() - started) * 1000)
                self._audit_failure(
                    audit_sink,
                    spec,
                    "schema_failed",
                    tenant_id,
                    user_id,
                    run_id,
                    input_digest,
                    idempotency_key,
                    attempt,
                    duration_ms,
                    exc,
                )
                raise

            duration_ms = int((perf_counter() - started) * 1000)
            self._audit(
                audit_sink,
                ToolAuditEvent(
                    tool_name=spec.name,
                    event_type="tool.completed",
                    status="completed",
                    tool_version=spec.version,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    run_id=run_id,
                    attempts=attempt,
                    duration_ms=duration_ms,
                    input_digest=input_digest,
                    idempotency_key=idempotency_key,
                ),
            )
            return ToolResult(
                tool_name=spec.name,
                output=output,
                duration_ms=duration_ms,
                attempts=attempt,
                tool_version=spec.version,
            )

        raise ToolExecutionError(
            f"{spec.name} failed: {last_error or 'unknown error'}"
        )

    @staticmethod
    def _validate_schema(
        schema: dict | None,
        value: Any,
        direction: str,
    ) -> None:
        if schema is None:
            return
        normalized = ToolRegistry._schema_value(value)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(normalized),
            key=lambda error: list(error.path),
        )
        if not errors:
            return
        error = errors[0]
        path = ".".join(str(item) for item in error.path) or "$"
        raise ToolSchemaError(
            f"{direction} schema validation failed at {path}: {error.message}"
        )

    @staticmethod
    def _schema_value(value: Any) -> Any:
        if isinstance(value, bytes):
            return {
                "type": "bytes",
                "encoding": "base64",
                "data": base64.b64encode(value).decode("ascii"),
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {
                key: ToolRegistry._schema_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [ToolRegistry._schema_value(item) for item in value]
        return value

    def _lock_for(self, key: tuple[str, str, str]) -> threading.Lock:
        with self._cache_lock:
            return self._idempotency_locks.setdefault(key, threading.Lock())

    def _get_cached(
        self,
        key: tuple[str, str, str],
        input_digest: str,
    ) -> ToolResult | None:
        with self._cache_lock:
            entry = self._cache_entries.get(key)
            if entry is None:
                return None
            expires_at, cached_digest, result = entry
            if expires_at <= perf_counter():
                self._cache_entries.pop(key, None)
                return None
            if cached_digest != input_digest:
                raise ToolIdempotencyConflictError(
                    "Idempotency key was already used with different arguments"
                )
            return result

    def _put_cached(
        self,
        key: tuple[str, str, str],
        result: ToolResult,
        ttl_seconds: int,
        input_digest: str,
    ) -> None:
        now = perf_counter()
        with self._cache_lock:
            expired = [
                cache_key
                for cache_key, (expires_at, _, _) in self._cache_entries.items()
                if expires_at <= now
            ]
            for cache_key in expired:
                self._cache_entries.pop(cache_key, None)
            if len(self._cache_entries) >= self._cache_max_entries:
                oldest_key = next(iter(self._cache_entries))
                self._cache_entries.pop(oldest_key, None)
            self._cache_entries[key] = (now + ttl_seconds, input_digest, result)

    def _audit_retry(
        self,
        audit_sink: Callable[[ToolAuditEvent], None] | None,
        spec: ToolSpec,
        tenant_id: str,
        user_id: str,
        run_id: str | None,
        input_digest: str,
        idempotency_key: str | None,
        attempt: int,
        error: Exception,
    ) -> None:
        self._audit(
            audit_sink,
            ToolAuditEvent(
                tool_name=spec.name,
                event_type="tool.retry",
                status="retrying",
                tool_version=spec.version,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                attempts=attempt,
                duration_ms=0,
                input_digest=input_digest,
                idempotency_key=idempotency_key,
                error=redact_pii(str(error))[:500],
            ),
        )

    def _audit_failure(
        self,
        audit_sink: Callable[[ToolAuditEvent], None] | None,
        spec: ToolSpec,
        status: str,
        tenant_id: str,
        user_id: str,
        run_id: str | None,
        input_digest: str,
        idempotency_key: str | None,
        attempts: int,
        duration_ms: int,
        error: Exception,
    ) -> None:
        self._audit(
            audit_sink,
            ToolAuditEvent(
                tool_name=spec.name,
                event_type="tool.failed",
                status=status,
                tool_version=spec.version,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                attempts=attempts,
                duration_ms=duration_ms,
                input_digest=input_digest,
                idempotency_key=idempotency_key,
                error=redact_pii(str(error))[:500],
            ),
        )

    @staticmethod
    def _audit(
        audit_sink: Callable[[ToolAuditEvent], None] | None,
        event: ToolAuditEvent,
    ) -> None:
        if audit_sink is None:
            return
        try:
            audit_sink(event)
        except Exception:
            return
