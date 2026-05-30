// Scenario CRUD + AAR record endpoints.

import { apiCall } from "./client";
import type {
  AarRecord,
  AarRecordCreatePayload,
  ScenarioBranchCreatePayload,
  ScenarioCompareForkCreatePayload,
  ScenarioCompareResponse,
  ScenarioCompareReport,
  ScenarioCompareReportCreatePayload,
  ScenarioCompareSession,
  ScenarioCompareSessionCreatePayload,
  ScenarioCompareSessionUpdatePayload,
  ScenarioCreatePayload,
  ScenarioDetail,
  ScenarioListItem,
  RuntimeTimelineResponse,
  ScenarioUpdatePayload,
  TrainingScoreRecord,
  TrainingScoreResponse,
} from "./types";

export async function listScenarios(
  includeTemplates = true
): Promise<ScenarioListItem[]> {
  const q = includeTemplates
    ? "?include_templates=true"
    : "?include_templates=false";
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

export async function createScenarioBranch(
  id: string,
  payload: ScenarioBranchCreatePayload
): Promise<ScenarioDetail> {
  return apiCall<ScenarioDetail>(
    `/api/scenarios/${encodeURIComponent(id)}/branch`,
    {
      method: "POST",
      json: payload,
    }
  );
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

export async function compareScenarios(
  scenarioIds: string[],
  baselineId?: string
): Promise<ScenarioCompareResponse> {
  const query = new URLSearchParams();
  scenarioIds.forEach((id) => query.append("scenario_id", id));
  if (baselineId) query.set("baseline_id", baselineId);
  return apiCall<ScenarioCompareResponse>(`/api/scenarios/compare?${query}`);
}

export async function listScenarioCompareReports(params?: {
  limit?: number;
}): Promise<ScenarioCompareReport[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiCall<ScenarioCompareReport[]>(
    `/api/scenarios/compare/reports${suffix}`
  );
}

export async function createScenarioCompareReport(
  payload: ScenarioCompareReportCreatePayload
): Promise<ScenarioCompareReport> {
  return apiCall<ScenarioCompareReport>("/api/scenarios/compare/reports", {
    method: "POST",
    json: payload,
  });
}

export async function deleteScenarioCompareReport(
  reportId: string
): Promise<void> {
  await apiCall<void>(
    `/api/scenarios/compare/reports/${encodeURIComponent(reportId)}`,
    { method: "DELETE" }
  );
}

export async function listScenarioCompareSessions(params?: {
  limit?: number;
}): Promise<ScenarioCompareSession[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiCall<ScenarioCompareSession[]>(
    `/api/scenarios/compare/sessions${suffix}`
  );
}

export async function createScenarioCompareSession(
  payload: ScenarioCompareSessionCreatePayload
): Promise<ScenarioCompareSession> {
  return apiCall<ScenarioCompareSession>("/api/scenarios/compare/sessions", {
    method: "POST",
    json: payload,
  });
}

export async function getScenarioCompareSession(
  compareSessionId: string
): Promise<ScenarioCompareSession> {
  return apiCall<ScenarioCompareSession>(
    `/api/scenarios/compare/sessions/${encodeURIComponent(compareSessionId)}`
  );
}

export async function updateScenarioCompareSession(
  compareSessionId: string,
  payload: ScenarioCompareSessionUpdatePayload
): Promise<ScenarioCompareSession> {
  return apiCall<ScenarioCompareSession>(
    `/api/scenarios/compare/sessions/${encodeURIComponent(compareSessionId)}`,
    {
      method: "PATCH",
      json: payload,
    }
  );
}

export async function deleteScenarioCompareSession(
  compareSessionId: string
): Promise<void> {
  await apiCall<void>(
    `/api/scenarios/compare/sessions/${encodeURIComponent(compareSessionId)}`,
    { method: "DELETE" }
  );
}

export async function forkScenarioCompareSession(
  scenarioId: string,
  payload: ScenarioCompareForkCreatePayload = {}
): Promise<ScenarioCompareSession> {
  return apiCall<ScenarioCompareSession>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/compare-session/fork`,
    {
      method: "POST",
      json: payload,
    }
  );
}

export async function listAarRecords(scenarioId: string): Promise<AarRecord[]> {
  return apiCall<AarRecord[]>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/aar`
  );
}

export async function listScenarioTimeline(
  scenarioId: string,
  params?: {
    eventType?: string;
    category?: string;
    limit?: number;
  }
): Promise<RuntimeTimelineResponse> {
  const query = new URLSearchParams();
  if (params?.eventType) query.set("event_type", params.eventType);
  if (params?.category) query.set("category", params.category);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiCall<RuntimeTimelineResponse>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/timeline${suffix}`
  );
}

export async function getScenarioTrainingScore(
  scenarioId: string
): Promise<TrainingScoreResponse> {
  return apiCall<TrainingScoreResponse>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/training-score`
  );
}

export async function listScenarioTrainingScoreRecords(
  scenarioId: string,
  params?: { limit?: number }
): Promise<TrainingScoreRecord[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiCall<TrainingScoreRecord[]>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/training-score/records${suffix}`
  );
}

export async function createScenarioTrainingScoreRecord(
  scenarioId: string
): Promise<TrainingScoreRecord> {
  return apiCall<TrainingScoreRecord>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/training-score/records`,
    { method: "POST" }
  );
}

export async function activateScenario(id: string): Promise<void> {
  await apiCall<unknown>(`/api/scenarios/${encodeURIComponent(id)}/activate`, {
    method: "POST",
  });
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
