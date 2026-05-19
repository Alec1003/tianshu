// Scenario CRUD + AAR record endpoints.

import { apiCall } from "./client";
import type {
  AarRecord,
  AarRecordCreatePayload,
  ScenarioCreatePayload,
  ScenarioDetail,
  ScenarioListItem,
  ScenarioUpdatePayload,
} from "./types";

export async function listScenarios(
  includeTemplates = true
): Promise<ScenarioListItem[]> {
  const q = includeTemplates ? "?include_templates=true" : "?include_templates=false";
  return apiCall<ScenarioListItem[]>(`/api/scenarios${q}`);
}

export async function getScenario(id: string): Promise<ScenarioDetail> {
  return apiCall<ScenarioDetail>(`/api/scenarios/${encodeURIComponent(id)}`);
}

export async function createScenario(
  payload: ScenarioCreatePayload
): Promise<ScenarioDetail> {
  return apiCall<ScenarioDetail>("/api/scenarios", {
    method: "POST",
    json: payload,
  });
}

export async function updateScenario(
  id: string,
  patch: ScenarioUpdatePayload
): Promise<ScenarioDetail> {
  return apiCall<ScenarioDetail>(`/api/scenarios/${encodeURIComponent(id)}`, {
    method: "PATCH",
    json: patch,
  });
}

export async function deleteScenario(id: string): Promise<void> {
  await apiCall<void>(`/api/scenarios/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function listAarRecords(scenarioId: string): Promise<AarRecord[]> {
  return apiCall<AarRecord[]>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/aar`
  );
}

export async function activateScenario(id: string): Promise<void> {
  await apiCall<unknown>(
    `/api/scenarios/${encodeURIComponent(id)}/activate`,
    { method: "POST" }
  );
}

export async function createAarRecord(
  scenarioId: string,
  payload: AarRecordCreatePayload
): Promise<AarRecord> {
  return apiCall<AarRecord>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/aar`,
    { method: "POST", json: payload }
  );
}
