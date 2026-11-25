"""工具注册表模块，负责工具注册、权限、Schema、超时、幂等和审计。"""
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
    """表示工具不存在的异常。"""
    pass


class ToolExecutionError(RuntimeError):
    """表示工具执行失败的异常。"""
    pass


class ToolTimeoutError(ToolExecutionError):
    """表示工具超时的异常。"""
    pass


class ToolPermissionError(PermissionError):
    """表示工具权限不足的异常。"""
    pass


class ToolIdempotencyConflictError(RuntimeError):
    """表示工具幂等冲突的异常。"""
    pass


class ToolSchemaError(ValueError):
    """表示工具 Schema 校验失败的异常。"""
    pass


@dataclass(frozen=True)
class ToolSpec:
    """工具规格。"""
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
    """工具执行结果。"""
    tool_name: str
    output: Any
    duration_ms: int
    attempts: int = 1
    cached: bool = False
    tool_version: str = "v1"


@dataclass(frozen=True)
class ToolAuditEvent:
    """工具审计事件。"""
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
        """转换为可序列化负载。

        Returns:
            函数处理结果，类型为 dict。

        """
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
    """计算参数摘要用于幂等键。

    Args:
        kwargs: `kwargs` 输入参数，类型为 dict[str, Any]。

    Returns:
        函数处理结果，类型为 str。

    """
    raw = repr(sorted(kwargs.items(), key=lambda item: item[0])).encode(
        "utf-8", errors="replace"
    )
    return hashlib.sha256(raw).hexdigest()[:16]


def _invoke_with_timeout(
    spec: ToolSpec,
    kwargs: dict[str, Any],
) -> Any:
    """在线程中带超时调用工具。

    Args:
        spec: `spec` 输入参数，类型为 ToolSpec。
        kwargs: `kwargs` 输入参数，类型为 dict[str, Any]。

    Returns:
        函数处理结果，类型为 Any。

    Raises:
        ToolTimeoutError: 当输入、状态或外部依赖不满足要求时抛出 ToolTimeoutError。
        outcome['error']: 当工具执行失败时重新抛出工具异常。

    """
    outcome: dict[str, Any] = {}

    def target() -> None:
        """在线程中执行工具并把结果写入 outcome。"""
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
    """工具注册表。"""
    def __init__(self) -> None:
        """初始化工具注册表。"""
        self._tools: dict[str, ToolSpec] = {}
        self._cache_lock = threading.Lock()
        self._idempotency_locks: dict[tuple[str, str, str], threading.Lock] = {}
        self._cache_entries: dict[
            tuple[str, str, str], tuple[float, str, ToolResult]
        ] = {}
        self._cache_max_entries = 1000

    def register(self, spec: ToolSpec) -> None:
        """注册工具。

        Args:
            spec: `spec` 输入参数，类型为 ToolSpec。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

        """
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
        """列出已注册工具。

        Returns:
            函数处理结果，类型为 list[ToolSpec]。

        """
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        """按名称获取工具。

        Args:
            name: `name` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 ToolSpec。

        Raises:
            ToolNotFoundError: 当输入、状态或外部依赖不满足要求时抛出 ToolNotFoundError。

        """
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
        """执行工具并处理权限、重试和审计。

        Args:
            name: `name` 输入参数，类型为 str。
            permissions: `permissions` 关键字参数，类型为 set[str] | frozenset[str] | None。
            idempotency_key: `idempotency_key` 关键字参数，类型为 str | None。
            tenant_id: `tenant_id` 关键字参数，类型为 str。
            user_id: `user_id` 关键字参数，类型为 str。
            run_id: `run_id` 关键字参数，类型为 str | None。
            audit_sink: `audit_sink` 关键字参数，类型为 Callable[[ToolAuditEvent], None] | None。
            **kwargs: 可变关键字参数，类型为 Any。

        Returns:
            函数处理结果，类型为 ToolResult。

        Raises:
            ToolPermissionError: 当输入、状态或外部依赖不满足要求时抛出 ToolPermissionError。

        """
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
        """按重试策略执行工具调用。

        Args:
            spec: `spec` 关键字参数，类型为 ToolSpec。
            kwargs: `kwargs` 关键字参数，类型为 dict[str, Any]。
            audit_sink: `audit_sink` 关键字参数，类型为 Callable[[ToolAuditEvent], None] | None。
            tenant_id: `tenant_id` 关键字参数，类型为 str。
            user_id: `user_id` 关键字参数，类型为 str。
            run_id: `run_id` 关键字参数，类型为 str | None。
            input_digest: `input_digest` 关键字参数，类型为 str。
            idempotency_key: `idempotency_key` 关键字参数，类型为 str | None。

        Returns:
            函数处理结果，类型为 ToolResult。

        Raises:
            ToolExecutionError: 当输入、状态或外部依赖不满足要求时抛出 ToolExecutionError。

        """
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
        """内部辅助：校验输入或输出 Schema。

        Args:
            schema: `schema` 输入参数，类型为 dict | None。
            value: `value` 输入参数，类型为 Any。
            direction: `direction` 输入参数，类型为 str。

        Raises:
            ToolSchemaError: 当输入、状态或外部依赖不满足要求时抛出 ToolSchemaError。

        """
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
        """内部辅助：读取 Schema 字段值。

        Args:
            value: `value` 输入参数，类型为 Any。

        Returns:
            函数处理结果，类型为 Any。

        """
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
        """内部辅助：按幂等键获取锁。

        Args:
            key: `key` 输入参数，类型为 tuple[str, str, str]。

        Returns:
            函数处理结果，类型为 threading.Lock。

        """
        with self._cache_lock:
            return self._idempotency_locks.setdefault(key, threading.Lock())

    def _get_cached(
        self,
        key: tuple[str, str, str],
        input_digest: str,
    ) -> ToolResult | None:
        """内部辅助：读取幂等缓存。

        Args:
            key: `key` 输入参数，类型为 tuple[str, str, str]。
            input_digest: `input_digest` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 ToolResult | None。

        Raises:
            ToolIdempotencyConflictError: 当输入、状态或外部依赖不满足要求时抛出 ToolIdempotencyConflictError。

        """
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
        """内部辅助：写入幂等缓存。

        Args:
            key: `key` 输入参数，类型为 tuple[str, str, str]。
            result: `result` 输入参数，类型为 ToolResult。
            ttl_seconds: `ttl_seconds` 输入参数，类型为 int。
            input_digest: `input_digest` 输入参数，类型为 str。

        """
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
        """内部辅助：记录重试审计事件。

        Args:
            audit_sink: `audit_sink` 输入参数，类型为 Callable[[ToolAuditEvent], None] | None。
            spec: `spec` 输入参数，类型为 ToolSpec。
            tenant_id: `tenant_id` 输入参数，类型为 str。
            user_id: `user_id` 输入参数，类型为 str。
            run_id: `run_id` 输入参数，类型为 str | None。
            input_digest: `input_digest` 输入参数，类型为 str。
            idempotency_key: `idempotency_key` 输入参数，类型为 str | None。
            attempt: `attempt` 输入参数，类型为 int。
            error: `error` 输入参数，类型为 Exception。

        """
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
        """内部辅助：记录失败审计事件。

        Args:
            audit_sink: `audit_sink` 输入参数，类型为 Callable[[ToolAuditEvent], None] | None。
            spec: `spec` 输入参数，类型为 ToolSpec。
            status: `status` 输入参数，类型为 str。
            tenant_id: `tenant_id` 输入参数，类型为 str。
            user_id: `user_id` 输入参数，类型为 str。
            run_id: `run_id` 输入参数，类型为 str | None。
            input_digest: `input_digest` 输入参数，类型为 str。
            idempotency_key: `idempotency_key` 输入参数，类型为 str | None。
            attempts: `attempts` 输入参数，类型为 int。
            duration_ms: `duration_ms` 输入参数，类型为 int。
            error: `error` 输入参数，类型为 Exception。

        """
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
        """内部辅助：写入审计事件。

        Args:
            audit_sink: `audit_sink` 输入参数，类型为 Callable[[ToolAuditEvent], None] | None。
            event: `event` 输入参数，类型为 ToolAuditEvent。

        """
        if audit_sink is None:
            return
        try:
            audit_sink(event)
        except Exception:
            return
