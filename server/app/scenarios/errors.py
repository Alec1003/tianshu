"""Scenario service domain errors.

为什么独立成文件：service 层不依赖 FastAPI（不导入 HTTPException），让
MCP tools / 未来的 CLI / 任何其他 transport 都能复用同一套业务函数，由各自
的上层把这些异常映射到对应协议的错误码。

约束（来自 api 技能）：错误模型必须稳定 -> 业务 code 全局唯一不复用，
有 retryable 提示，不让客户端解析 message 文案做分支。
"""

from __future__ import annotations


class ScenarioServiceError(Exception):
    """Service 层基类。子类必须覆盖 ``code``。

    Attributes:
        code: 全局唯一业务码，客户端可解析做分支判断。
        retryable: 是否值得客户端重试（瞬时故障）。Service 层默认 False。
        details: 结构化补充信息，可被序列化进 MCP/HTTP 响应。
    """

    code: str = "scenario_error"
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ScenarioNotFoundError(ScenarioServiceError):
    code = "scenario_not_found"

    def __init__(self, scenario_id: str):
        super().__init__(
            f"scenario not found: {scenario_id}",
            details={"scenario_id": scenario_id},
        )


class ScenarioForbiddenError(ScenarioServiceError):
    code = "scenario_forbidden"

    def __init__(self, scenario_id: str, reason: str):
        super().__init__(
            f"forbidden: {reason}",
            details={"scenario_id": scenario_id, "reason": reason},
        )


class ScenarioInvalidError(ScenarioServiceError):
    code = "scenario_invalid"

    def __init__(self, field: str, reason: str):
        super().__init__(
            f"invalid {field}: {reason}",
            details={"field": field, "reason": reason},
        )


class ScenarioTemplateReadOnlyError(ScenarioServiceError):
    """Templates are read-only for non-superusers; clients should "save as"."""

    code = "scenario_template_read_only"

    def __init__(self, scenario_id: str):
        super().__init__(
            "templates are read-only; use 'save as' to fork into your own copy",
            details={"scenario_id": scenario_id},
        )
