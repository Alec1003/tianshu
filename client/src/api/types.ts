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

export interface ScenarioListItem {
  id: string;
  name: string;
  description: string;
  is_template: boolean;
  owner_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ScenarioDetail extends ScenarioListItem {
  // Whole scenario JSON. Shape matches the existing client/src/scenarios/*.json
  // contract, so the in-memory Game can `loadScenario(JSON.stringify(data))`.
  data: Record<string, unknown>;
}

export interface ScenarioCreatePayload {
  name: string;
  description?: string;
  data: Record<string, unknown>;
}

export interface ScenarioUpdatePayload {
  name?: string;
  description?: string;
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
