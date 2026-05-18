from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class SkillExecutionResult(BaseModel):
    skill: str
    status: Literal["ok", "error"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MCPCallTrace(BaseModel):
    action: str
    target: str
    status: Literal["pending", "ok", "error"] = "pending"
    message: str = ""


class AgentExecutionSummary(BaseModel):
    command: str
    decomposition: list[str] = Field(default_factory=list)
    skill_calls: list[SkillExecutionResult] = Field(default_factory=list)
    mcp_traces: list[MCPCallTrace] = Field(default_factory=list)
    status: Literal["ok", "error", "partial"] = "ok"
    error: str | None = None


class AICommandRequest(BaseModel):
    command: str = Field(min_length=1, description="Natural language command")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved extension field for future multi-turn context",
    )


class AICommandResponse(BaseModel):
    status: Literal["ok", "error", "partial"]
    message: str
    execution: AgentExecutionSummary
    scenario: dict[str, Any] | None = None


class ModelCheckRequest(BaseModel):
    provider: str = "openai"
    baseUrl: str = Field(min_length=1)
    apiKey: str = ""
    model: str = ""


class ModelCheckResponse(BaseModel):
    status: Literal["ok", "error", "partial"]
    message: str
    provider: str
    endpoint: str
    auth_ok: bool
    models_listed: bool
    checked_model: str | None = None
    checked_model_exists: bool | None = None
    http_status: int | None = None
    sample_models: list[str] = Field(default_factory=list)
    error: str | None = None
