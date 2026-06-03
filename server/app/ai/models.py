from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class SkillSchemaField(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(default="string", max_length=80)
    required: bool = False
    description: str = Field(default="", max_length=1000)


class CustomSkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    prompt: str = Field(default="", max_length=12000)
    inputSchema: list[SkillSchemaField] = Field(default_factory=list, max_length=32)
    outputSchema: list[SkillSchemaField] = Field(default_factory=list, max_length=32)
    enabled: bool = True


class CustomSkillUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    prompt: str | None = Field(default=None, max_length=12000)
    inputSchema: list[SkillSchemaField] | None = Field(default=None, max_length=32)
    outputSchema: list[SkillSchemaField] | None = Field(default=None, max_length=32)
    enabled: bool | None = None


class CustomSkillRead(BaseModel):
    id: str
    name: str
    description: str = ""
    prompt: str = ""
    source: Literal["custom"] = "custom"
    version: str = "custom-1"
    enabled: bool = True
    readonly: bool = False
    inputSchema: list[SkillSchemaField] = Field(default_factory=list)
    outputSchema: list[SkillSchemaField] = Field(default_factory=list)
    usageCount: int = 0
    lastUsedAt: str | None = None
    createdBy: str = ""
    updatedAt: str


class CustomSkillListResponse(BaseModel):
    skills: list[CustomSkillRead] = Field(default_factory=list)
    skillsDir: str


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


class ExternalMcpValidateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transport: str = Field(default="stdio", max_length=40)
    endpoint: str = Field(default="", max_length=4096)
    command: str = Field(default="", max_length=1024)
    args: list[str] = Field(default_factory=list, max_length=64)
    url: str = Field(default="", max_length=4096)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    allowedTools: list[str] = Field(default_factory=list, max_length=128)
    enabled: bool = True
    timeoutSeconds: float = Field(default=10.0, ge=1.0)


class ExternalMcpToolRead(BaseModel):
    server: str
    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    outputSchema: dict[str, Any] = Field(default_factory=dict)


class ExternalMcpValidateResponse(BaseModel):
    ok: bool
    server: str
    transport: Literal["stdio", "streamable_http"]
    message: str
    tools: list[ExternalMcpToolRead] = Field(default_factory=list)
    trace: list[MCPCallTrace] = Field(default_factory=list)


class BuiltinMcpToolsResponse(BaseModel):
    ok: bool
    server: str
    message: str
    tools: list[ExternalMcpToolRead] = Field(default_factory=list)


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


class TacticalPlanStepDraft(BaseModel):
    skill: str = Field(
        min_length=1,
        max_length=80,
        description="Backend runtime skill to execute after human approval.",
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=300)
    rationale: str = Field(default="", max_length=1200)
    risk: Literal["low", "medium", "high"] = "medium"


class TacticalPlanOptionDraft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=2000)
    advantages: list[str] = Field(default_factory=list, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=8)
    steps: list[TacticalPlanStepDraft] = Field(
        default_factory=list,
        min_length=1,
        max_length=16,
    )


class InternalSkillMissionDraft(BaseModel):
    """One constrained mission/task inside a project-native tactical skill."""

    type: Literal["patrol", "strike", "move"]
    name: str = Field(min_length=1, max_length=120)
    assigned_unit_ids: list[str] = Field(default_factory=list, max_length=32)
    reference_point_ids: list[str] = Field(default_factory=list, max_length=16)
    assigned_target_ids: list[str] = Field(default_factory=list, max_length=32)
    route: list[list[float]] = Field(default_factory=list, max_length=32)
    notes: str = Field(default="", max_length=1000)


class InternalSkillDraft(BaseModel):
    """A temporary in-app doctrine pack generated by an LLM or operator.

    This is app data, not an executable Codex/Anthropic skill file.
    """

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    side_id: str = Field(default="", max_length=120)
    trigger_phrases: list[str] = Field(default_factory=list, max_length=16)
    constraints: list[str] = Field(default_factory=list, max_length=24)
    allowed_runtime_skills: list[str] = Field(default_factory=list, max_length=16)
    missions: list[InternalSkillMissionDraft] = Field(default_factory=list, min_length=1, max_length=12)
    expires_at: str | None = None
    allow_duplicate_assignments: bool = False


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
    source: Literal[
        "regex",
        "llm_tool",
        "llm_plan",
        "api",
        "mcp",
        "internal_skill",
    ] = "api"
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
    plan_metadata: dict[str, Any] = Field(default_factory=dict)
    execution: list[SkillExecutionResult] = Field(default_factory=list)
    error: str | None = None


class CommandProposalListResponse(BaseModel):
    proposals: list[CommandProposal] = Field(default_factory=list)


class InternalSkillProposalRequest(BaseModel):
    draft: InternalSkillDraft
    command: str = Field(
        default="",
        max_length=1000,
        description="Operator-visible reason for creating this internal skill proposal.",
    )


class InternalSkillProposalResponse(BaseModel):
    draft: InternalSkillDraft
    proposal: CommandProposal


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
    "obstacle",
]


class RuntimeDeployUnitRequest(BaseModel):
    unit_type: RuntimeUnitType
    class_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    side: str | None = None
    name: str | None = None
    altitude: float | None = None
    radius_nm: float | None = Field(default=None, ge=0)
    obstacle_type: str | None = None
    movement_penalty: float | None = Field(default=None, ge=0, le=1)
    detection_penalty: float | None = Field(default=None, ge=0, le=1)
    communication_penalty: float | None = Field(default=None, ge=0, le=1)
    affected_domains: list[str] | None = None


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
    providerId: str = ""
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
