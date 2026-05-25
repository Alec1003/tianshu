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


class StructuredCommandStep(BaseModel):
    id: str
    skill: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_text: str = ""
    summary: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    writes_runtime: bool = True


class CommandAdjudicationIssue(BaseModel):
    severity: Literal["info", "warning", "blocking"]
    code: str
    message: str
    field: str | None = None
    step_id: str | None = None


class CommandAdjudicationResult(BaseModel):
    status: Literal["needs_review", "blocked"] = "needs_review"
    requires_human_approval: bool = True
    summary: str = ""
    issues: list[CommandAdjudicationIssue] = Field(default_factory=list)


class CommandProposal(BaseModel):
    id: str
    command: str
    source: Literal["regex", "llm_tool", "api"] = "api"
    status: Literal[
        "pending",
        "blocked",
        "approved",
        "rejected",
        "executed",
        "partial",
        "failed",
    ] = "pending"
    created_at: str
    updated_at: str
    steps: list[StructuredCommandStep] = Field(default_factory=list)
    adjudication: CommandAdjudicationResult
    execution: list[SkillExecutionResult] = Field(default_factory=list)
    error: str | None = None


class CommandProposalListResponse(BaseModel):
    proposals: list[CommandProposal] = Field(default_factory=list)


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
    proposals: list[CommandProposal] = Field(default_factory=list)


class RuntimeStepRequest(BaseModel):
    steps: int = Field(
        default=1,
        ge=1,
        le=7200,
        description="Number of authoritative backend simulation seconds to advance.",
    )


class RuntimeAttackRequest(BaseModel):
    attacker_type: Literal["aircraft", "ship"] = Field(
        description="Type of unit launching the weapon.",
    )
    attacker_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    weapon_id: str = ""
    weapon_quantity: int = Field(default=1, ge=0, le=512)
    auto: bool = False


RuntimeUnitType = Literal[
    "aircraft",
    "ship",
    "facility",
    "airbase",
    "reference_point",
]


class RuntimeDeployUnitRequest(BaseModel):
    unit_type: RuntimeUnitType
    class_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    side: str | None = None
    name: str | None = None
    altitude: float | None = None


class RuntimeMoveUnitRequest(BaseModel):
    unit_type: Literal["aircraft", "ship"]
    unit_id: str = Field(min_length=1)
    route: list[list[float]] = Field(default_factory=list)


class RuntimeSetUnitPositionRequest(BaseModel):
    unit_type: RuntimeUnitType
    unit_id: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RuntimeUpdateUnitRequest(BaseModel):
    unit_type: RuntimeUnitType
    unit_id: str = Field(min_length=1)
    patch: dict[str, Any] = Field(default_factory=dict)


class RuntimeSetCurrentSideRequest(BaseModel):
    side: str = Field(min_length=1)


class RuntimeCreateSideRequest(BaseModel):
    name: str = Field(min_length=1)
    color: str = "blue"
    hostiles: list[str] = Field(default_factory=list)
    allies: list[str] = Field(default_factory=list)
    doctrine: dict[str, Any] = Field(default_factory=dict)


class RuntimeUpdateSideRequest(BaseModel):
    name: str = Field(min_length=1)
    color: str = "blue"
    hostiles: list[str] = Field(default_factory=list)
    allies: list[str] = Field(default_factory=list)
    doctrine: dict[str, Any] = Field(default_factory=dict)


class RuntimePatrolMissionRequest(BaseModel):
    name: str = Field(min_length=1)
    assigned_unit_ids: list[str] = Field(default_factory=list)
    reference_point_ids: list[str] = Field(default_factory=list)


class RuntimeStrikeMissionRequest(BaseModel):
    name: str = Field(min_length=1)
    assigned_unit_ids: list[str] = Field(default_factory=list)
    assigned_target_ids: list[str] = Field(default_factory=list)


RuntimeWeaponCarrierType = Literal["aircraft", "ship", "facility"]


class RuntimeAddWeaponRequest(BaseModel):
    unit_type: RuntimeWeaponCarrierType
    unit_id: str = Field(min_length=1)
    class_name: str = Field(min_length=1)
    speed: float = 0.0
    max_fuel: float = 0.0
    fuel_rate: float = 1.0
    range: float = 0.0
    lethality: float = 0.0
    quantity: int = Field(default=1, ge=1, le=512)


class RuntimeDeleteWeaponRequest(BaseModel):
    unit_type: RuntimeWeaponCarrierType
    unit_id: str = Field(min_length=1)
    weapon_id: str = Field(min_length=1)


class RuntimeUpdateWeaponQuantityRequest(RuntimeDeleteWeaponRequest):
    increment: int = Field(ge=-512, le=512)


class RuntimeLoadScenarioRequest(BaseModel):
    scenario: dict[str, Any] = Field(
        description="Frontend-shaped scenario JSON to load into the backend runtime.",
    )


class RuntimeVisibilitySide(BaseModel):
    side_id: str
    visible_object_ids: list[str] = Field(default_factory=list)
    operational_detail_object_ids: list[str] = Field(default_factory=list)
    detected_hostile_object_ids: list[str] = Field(default_factory=list)
    visible_counts: dict[str, int] = Field(default_factory=dict)
    total_counts: dict[str, int] = Field(default_factory=dict)


class RuntimeVisibilityResponse(BaseModel):
    current_side_id: str = ""
    by_side: dict[str, RuntimeVisibilitySide] = Field(default_factory=dict)


class RuntimeSnapshotResponse(BaseModel):
    ok: Literal[True] = True
    action: str = ""
    state: dict[str, Any] = Field(default_factory=dict)
    running: bool
    paused: bool
    current_time: int
    elapsed: int
    duration_left: int
    outcome: dict[str, Any]
    scenario: dict[str, Any]
    visibility: RuntimeVisibilityResponse = Field(
        default_factory=RuntimeVisibilityResponse
    )


class CommandApprovalResponse(BaseModel):
    proposal: CommandProposal
    snapshot: RuntimeSnapshotResponse | None = None


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
