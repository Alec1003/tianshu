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
}

export interface RuntimeAttackRequest {
  attacker_type: "aircraft" | "ship";
  attacker_id: string;
  target_id: string;
  weapon_id?: string;
  weapon_quantity?: number;
  auto?: boolean;
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
