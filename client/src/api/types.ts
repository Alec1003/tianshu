// Shared API DTOs mirroring the FastAPI response shapes in
// server/app/auth/schemas.py and server/app/scenarios/schemas.py.

export interface AuthUser {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  display_name: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: "bearer";
}

export type ScenarioStatus = "draft" | "running" | "completed";

export interface ScenarioListItem {
  id: string;
  name: string;
  description: string;
  is_template: boolean;
  owner_id: string | null;
  version: number;
  status: ScenarioStatus;
  mission_count: number;
  unit_count: number;
  side_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScenarioDetail extends ScenarioListItem {
  // Whole scenario JSON. Shape matches the existing client/src/scenarios/*.json
  // contract, so the in-memory Game can `loadScenario(JSON.stringify(data))`.
  data: Record<string, unknown>;
}

export interface RuntimeOutcome {
  ended: boolean;
  winner_side_id: string | null;
  reason: string;
  ended_at: number;
  objective_destroyed: Record<string, unknown> | null;
  time_up: boolean;
}

export type RuntimeVisibleObjectType =
  | "aircraft"
  | "ships"
  | "facilities"
  | "airbases"
  | "referencePoints"
  | "obstacles"
  | "weapons";

export interface RuntimeVisibilitySide {
  side_id: string;
  visible_object_ids: string[];
  operational_detail_object_ids: string[];
  detected_hostile_object_ids: string[];
  visible_counts: Record<RuntimeVisibleObjectType, number>;
  total_counts: Record<RuntimeVisibleObjectType, number>;
}

export interface RuntimeVisibility {
  current_side_id: string;
  by_side: Record<string, RuntimeVisibilitySide>;
}

export interface RuntimeSnapshot {
  ok: true;
  action: string;
  state: Record<string, unknown>;
  running: boolean;
  paused: boolean;
  current_time: number;
  elapsed: number;
  duration_left: number;
  outcome: RuntimeOutcome;
  scenario: Record<string, unknown>;
  visibility: RuntimeVisibility;
}

export interface RuntimeUnitChange {
  change_type: "added" | "removed" | "updated";
  unit_type: string;
  unit_id: string;
  name: string;
  side_id: string;
  fields: Record<string, { before: unknown; after: unknown }>;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

export interface RuntimeTimelineEvent {
  id: string;
  owner_id: string;
  scenario_id?: string | null;
  event_type: string;
  category: string;
  action: string;
  actor: string;
  summary: string;
  payload: Record<string, unknown>;
  unit_changes: RuntimeUnitChange[];
  current_time?: number | null;
  proposal_id?: string | null;
  aar_record_id?: string | null;
  created_at: string;
}

export interface RuntimeTimelineResponse {
  events: RuntimeTimelineEvent[];
}

export interface TrainingScoreDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  summary: string;
  evidence: string[];
}

export interface TrainingScoreResponse {
  scenario_id: string;
  runtime_scenario_id?: string | null;
  generated_at: string;
  overall_score: number;
  grade: string;
  confidence: "low" | "medium" | "high" | string;
  dimensions: TrainingScoreDimension[];
  metrics: Record<string, unknown>;
  strengths: string[];
  improvements: string[];
}

export interface TrainingScoreRecord {
  id: string;
  scenario_id: string | null;
  owner_id: string | null;
  runtime_scenario_id?: string | null;
  aar_record_id?: string | null;
  overall_score: number;
  grade: string;
  confidence: string;
  score: TrainingScoreResponse;
  metrics: Record<string, unknown>;
  created_at: string;
}

export interface SkillExecutionResult {
  skill: string;
  status: "ok" | "error";
  parameters: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string | null;
}

export interface RegisteredSkill {
  name: string;
  description: string;
  parameters?: Record<string, unknown>;
}

export interface SkillSchemaField {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export interface CustomSkill {
  id: string;
  name: string;
  description: string;
  prompt: string;
  source: "custom";
  version: string;
  enabled: boolean;
  readonly: boolean;
  inputSchema: SkillSchemaField[];
  outputSchema: SkillSchemaField[];
  usageCount: number;
  lastUsedAt: string | null;
  createdBy: string;
  updatedAt: string;
}

export interface CustomSkillCreatePayload {
  name: string;
  description?: string;
  prompt?: string;
  inputSchema?: SkillSchemaField[];
  outputSchema?: SkillSchemaField[];
  enabled?: boolean;
}

export interface CustomSkillUpdatePayload {
  name?: string;
  description?: string;
  prompt?: string;
  inputSchema?: SkillSchemaField[];
  outputSchema?: SkillSchemaField[];
  enabled?: boolean;
}

export interface CustomSkillListResponse {
  skills: CustomSkill[];
  skillsDir: string;
}

export type ExternalMcpTransport = "stdio" | "sse" | "http";

export interface ExternalMcpValidateRequest {
  name: string;
  transport: ExternalMcpTransport;
  endpoint?: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  headers?: Record<string, string>;
  allowedTools?: string[];
  enabled?: boolean;
  timeoutSeconds?: number;
}

export interface ExternalMcpTool {
  server: string;
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

export interface ExternalMcpTrace {
  action: string;
  target: string;
  status: "pending" | "ok" | "error";
  message: string;
}

export interface ExternalMcpValidateResponse {
  ok: boolean;
  server: string;
  transport: "stdio" | "streamable_http";
  message: string;
  tools: ExternalMcpTool[];
  trace: ExternalMcpTrace[];
}

export interface BuiltinMcpToolsResponse {
  ok: boolean;
  server: string;
  message: string;
  tools: ExternalMcpTool[];
}

export interface StructuredCommandStep {
  id: string;
  skill: string;
  parameters: Record<string, unknown>;
  source_text: string;
  summary: string;
  risk: "low" | "medium" | "high";
  writes_runtime: boolean;
}

export interface InternalSkillMissionDraft {
  type: "patrol" | "strike" | "move";
  name: string;
  assigned_unit_ids: string[];
  reference_point_ids?: string[];
  assigned_target_ids?: string[];
  route?: number[][];
  notes?: string;
}

export interface InternalSkillDraft {
  name: string;
  description?: string;
  side_id?: string;
  trigger_phrases?: string[];
  constraints?: string[];
  allowed_runtime_skills?: string[];
  missions: InternalSkillMissionDraft[];
  expires_at?: string | null;
  allow_duplicate_assignments?: boolean;
}

export interface InternalSkillProposalRequest {
  draft: InternalSkillDraft;
  command?: string;
}

export interface CommandAdjudicationIssue {
  severity: "info" | "warning" | "blocking";
  code: string;
  message: string;
  field?: string | null;
  step_id?: string | null;
}

export interface CommandAdjudicationResult {
  status: "needs_review" | "blocked";
  requires_human_approval: boolean;
  summary: string;
  issues: CommandAdjudicationIssue[];
}

export interface CommandProposal {
  id: string;
  command: string;
  source: "regex" | "llm_tool" | "api" | "mcp" | "internal_skill";
  status:
    | "pending"
    | "blocked"
    | "approved"
    | "rejected"
    | "executed"
    | "partial"
    | "failed";
  created_at: string;
  updated_at: string;
  steps: StructuredCommandStep[];
  adjudication: CommandAdjudicationResult;
  execution: SkillExecutionResult[];
  error?: string | null;
}

export interface CommandProposalListResponse {
  proposals: CommandProposal[];
}

export interface InternalSkillProposalResponse {
  draft: InternalSkillDraft;
  proposal: CommandProposal;
}

export interface CommandApprovalResponse {
  proposal: CommandProposal;
  snapshot?: RuntimeSnapshot | null;
}

export interface RuntimeAttackRequest {
  attacker_type: "aircraft" | "ship";
  attacker_id: string;
  target_id: string;
  weapon_id?: string;
  weapon_quantity?: number;
  auto?: boolean;
}

export type RuntimeUnitType =
  | "aircraft"
  | "ship"
  | "facility"
  | "airbase"
  | "reference_point"
  | "obstacle";

export interface RuntimeDeployUnitRequest {
  unit_type: RuntimeUnitType;
  class_name: string;
  latitude: number;
  longitude: number;
  side?: string | null;
  name?: string | null;
  altitude?: number | null;
  radius_nm?: number | null;
  obstacle_type?: string | null;
  movement_penalty?: number | null;
  detection_penalty?: number | null;
  communication_penalty?: number | null;
  affected_domains?: string[] | null;
}

export interface RuntimeMoveUnitRequest {
  unit_type: "aircraft" | "ship";
  unit_id: string;
  route: number[][];
}

export interface RuntimeSetUnitPositionRequest {
  unit_type: RuntimeUnitType;
  unit_id: string;
  latitude: number;
  longitude: number;
}

export interface RuntimeUpdateUnitRequest {
  unit_type: RuntimeUnitType;
  unit_id: string;
  patch: Record<string, unknown>;
}

export interface RuntimeCreateSideRequest {
  name: string;
  color: string;
  hostiles: string[];
  allies: string[];
  doctrine: Record<string, unknown>;
}

export interface RuntimeUpdateSideRequest extends RuntimeCreateSideRequest {}

export interface RuntimePatrolMissionRequest {
  name: string;
  assigned_unit_ids: string[];
  reference_point_ids: string[];
}

export interface RuntimeStrikeMissionRequest {
  name: string;
  assigned_unit_ids: string[];
  assigned_target_ids: string[];
}

export type RuntimeWeaponCarrierType = "aircraft" | "ship" | "facility";

export interface RuntimeAddWeaponRequest {
  unit_type: RuntimeWeaponCarrierType;
  unit_id: string;
  class_name: string;
  speed: number;
  max_fuel: number;
  fuel_rate: number;
  range: number;
  lethality: number;
  quantity?: number;
}

export interface RuntimeDeleteWeaponRequest {
  unit_type: RuntimeWeaponCarrierType;
  unit_id: string;
  weapon_id: string;
}

export interface RuntimeUpdateWeaponQuantityRequest
  extends RuntimeDeleteWeaponRequest {
  increment: number;
}

export interface ScenarioCreatePayload {
  name: string;
  description?: string;
  status?: ScenarioStatus;
  data: Record<string, unknown>;
}

export interface ScenarioUpdatePayload {
  name?: string;
  description?: string;
  status?: ScenarioStatus;
  data?: Record<string, unknown>;
}

export interface AarRecordCreatePayload {
  outcome_reason: string;
  winner_side_id: string;
  summary: Record<string, unknown>;
  ended_at: string;
}

export interface AarRecord extends AarRecordCreatePayload {
  id: string;
  scenario_id: string | null;
  owner_id: string | null;
  created_at: string;
}

export type UnitAssetType =
  | "aircraft"
  | "ship"
  | "facility"
  | "airbase"
  | "weapon";

export interface UnitAsset {
  id: string;
  type: UnitAssetType;
  name: string;
  data: Record<string, unknown>;
  is_system: boolean;
  owner_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface UnitAssetCreatePayload {
  type: UnitAssetType;
  data: Record<string, unknown>;
}

export interface UnitAssetGeneratePayload {
  type: UnitAssetType;
  query: string;
  context?: string;
}

export interface UnitAssetGenerateResult {
  type: UnitAssetType;
  data: Record<string, unknown>;
  source: "llm" | "estimate";
  confidence: number;
  warnings: string[];
}

export interface UnitAssetUpdatePayload {
  data: Record<string, unknown>;
}

export interface UnitAssetCatalogPayload {
  aircraftDb: Record<string, unknown>[];
  airbaseDb: Record<string, unknown>[];
  facilityDb: Record<string, unknown>[];
  shipDb: Record<string, unknown>[];
  weaponDb: Record<string, unknown>[];
}

export interface UnitAssetImportPayload extends UnitAssetCatalogPayload {
  replace_existing?: boolean;
}

export interface UnitAssetImportResult {
  created: number;
  updated: number;
  skipped: number;
  assets: UnitAsset[];
}
