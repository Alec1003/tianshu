import { apiCall } from "./client";
import type {
  BuiltinMcpToolsResponse,
  CommandApprovalResponse,
  CommandProposalListResponse,
  CustomSkill,
  CustomSkillCreatePayload,
  CustomSkillListResponse,
  CustomSkillUpdatePayload,
  ExternalMcpValidateRequest,
  ExternalMcpValidateResponse,
  InternalSkillProposalRequest,
  InternalSkillProposalResponse,
  RegisteredSkill,
  RuntimeAttackRequest,
  RuntimeAddWeaponRequest,
  RuntimeCreateSideRequest,
  RuntimeDeleteWeaponRequest,
  RuntimeDeployUnitRequest,
  RuntimeMoveUnitRequest,
  RuntimePatrolMissionRequest,
  RuntimeSetUnitPositionRequest,
  RuntimeSnapshot,
  RuntimeStrikeMissionRequest,
  RuntimeTimelineResponse,
  RuntimeUnitType,
  RuntimeUpdateSideRequest,
  RuntimeUpdateUnitRequest,
  RuntimeUpdateWeaponQuantityRequest,
} from "./types";

export async function getRuntimeScenario(): Promise<Record<string, unknown>> {
  return apiCall<Record<string, unknown>>("/api/ai/runtime/scenario");
}

export async function getRuntimeSnapshot(): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime");
}

export async function listRuntimeTimeline(params?: {
  scenarioId?: string;
  eventType?: string;
  category?: string;
  limit?: number;
  latest?: boolean;
}): Promise<RuntimeTimelineResponse> {
  const query = new URLSearchParams();
  if (params?.scenarioId) query.set("scenario_id", params.scenarioId);
  if (params?.eventType) query.set("event_type", params.eventType);
  if (params?.category) query.set("category", params.category);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.latest !== undefined) query.set("latest", String(params.latest));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiCall<RuntimeTimelineResponse>(`/api/ai/runtime/timeline${suffix}`);
}

export async function listCommandProposals(
  statusFilter?: string
): Promise<CommandProposalListResponse> {
  const query = statusFilter
    ? `?status_filter=${encodeURIComponent(statusFilter)}`
    : "";
  return apiCall<CommandProposalListResponse>(
    `/api/ai/command/proposals${query}`
  );
}

export async function approveCommandProposal(
  proposalId: string
): Promise<CommandApprovalResponse> {
  return apiCall<CommandApprovalResponse>(
    `/api/ai/command/proposals/${encodeURIComponent(proposalId)}/approve`,
    { method: "POST" }
  );
}

export async function rejectCommandProposal(
  proposalId: string
): Promise<CommandApprovalResponse> {
  return apiCall<CommandApprovalResponse>(
    `/api/ai/command/proposals/${encodeURIComponent(proposalId)}/reject`,
    { method: "POST" }
  );
}

export async function createInternalSkillProposal(
  payload: InternalSkillProposalRequest
): Promise<InternalSkillProposalResponse> {
  return apiCall<InternalSkillProposalResponse>(
    "/api/ai/internal-skills/proposals",
    { method: "POST", json: payload }
  );
}

export async function listBackendSkills(): Promise<RegisteredSkill[]> {
  const payload = await apiCall<{ skills?: RegisteredSkill[] }>(
    "/api/ai/skills"
  );
  return payload.skills ?? [];
}

export async function listCustomSkills(): Promise<CustomSkillListResponse> {
  return apiCall<CustomSkillListResponse>("/api/ai/custom-skills");
}

export async function createCustomSkill(
  payload: CustomSkillCreatePayload
): Promise<CustomSkill> {
  return apiCall<CustomSkill>("/api/ai/custom-skills", {
    method: "POST",
    json: payload,
  });
}

export async function updateCustomSkill(
  skillId: string,
  payload: CustomSkillUpdatePayload
): Promise<CustomSkill> {
  return apiCall<CustomSkill>(
    `/api/ai/custom-skills/${encodeURIComponent(skillId)}`,
    {
      method: "PATCH",
      json: payload,
    }
  );
}

export async function deleteCustomSkill(skillId: string): Promise<void> {
  await apiCall<void>(`/api/ai/custom-skills/${encodeURIComponent(skillId)}`, {
    method: "DELETE",
  });
}

export async function validateExternalMcpServer(
  payload: ExternalMcpValidateRequest
): Promise<ExternalMcpValidateResponse> {
  return apiCall<ExternalMcpValidateResponse>("/api/ai/mcp/validate", {
    method: "POST",
    json: payload,
  });
}

export async function listBuiltinMcpTools(): Promise<BuiltinMcpToolsResponse> {
  return apiCall<BuiltinMcpToolsResponse>("/api/ai/mcp/builtin/tools");
}

export async function loadRuntimeScenario(
  scenario: Record<string, unknown>
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/scenario", {
    method: "PUT",
    json: { scenario },
  });
}

export async function startRuntime(): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/start", {
    method: "POST",
  });
}

export async function pauseRuntime(): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/pause", {
    method: "POST",
  });
}

export async function resetRuntime(): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/reset", {
    method: "POST",
  });
}

export async function stepRuntime(steps: number = 1): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/step", {
    method: "POST",
    json: { steps },
  });
}

export async function attackRuntime(
  attack: RuntimeAttackRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/attack", {
    method: "POST",
    json: attack,
  });
}

export async function deployRuntimeUnit(
  unit: RuntimeDeployUnitRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/units", {
    method: "POST",
    json: unit,
  });
}

export async function deleteRuntimeUnit(
  unitType: RuntimeUnitType,
  unitId: string
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/units/${encodeURIComponent(unitType)}/${encodeURIComponent(
      unitId
    )}`,
    { method: "DELETE" }
  );
}

export async function moveRuntimeUnit(
  move: RuntimeMoveUnitRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/units/route", {
    method: "PATCH",
    json: move,
  });
}

export async function setRuntimeUnitPosition(
  position: RuntimeSetUnitPositionRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/units/position", {
    method: "PATCH",
    json: position,
  });
}

export async function updateRuntimeUnit(
  update: RuntimeUpdateUnitRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/units", {
    method: "PATCH",
    json: update,
  });
}

export async function setRuntimeCurrentSide(
  side: string
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/side/current", {
    method: "PATCH",
    json: { side },
  });
}

export async function createRuntimeSide(
  side: RuntimeCreateSideRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/sides", {
    method: "POST",
    json: side,
  });
}

export async function updateRuntimeSide(
  sideId: string,
  side: RuntimeUpdateSideRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/sides/${encodeURIComponent(sideId)}`,
    {
      method: "PATCH",
      json: side,
    }
  );
}

export async function deleteRuntimeSide(
  sideId: string
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/sides/${encodeURIComponent(sideId)}`,
    { method: "DELETE" }
  );
}

export async function deleteRuntimeMission(
  missionId: string
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/missions/${encodeURIComponent(missionId)}`,
    { method: "DELETE" }
  );
}

export async function createRuntimePatrolMission(
  mission: RuntimePatrolMissionRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/missions/patrol", {
    method: "POST",
    json: mission,
  });
}

export async function updateRuntimePatrolMission(
  missionId: string,
  mission: RuntimePatrolMissionRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/missions/patrol/${encodeURIComponent(missionId)}`,
    { method: "PATCH", json: mission }
  );
}

export async function createRuntimeStrikeMission(
  mission: RuntimeStrikeMissionRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/missions/strike", {
    method: "POST",
    json: mission,
  });
}

export async function updateRuntimeStrikeMission(
  missionId: string,
  mission: RuntimeStrikeMissionRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>(
    `/api/ai/runtime/missions/strike/${encodeURIComponent(missionId)}`,
    { method: "PATCH", json: mission }
  );
}

export async function addRuntimeWeapon(
  weapon: RuntimeAddWeaponRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/weapons", {
    method: "POST",
    json: weapon,
  });
}

export async function deleteRuntimeWeapon(
  weapon: RuntimeDeleteWeaponRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/weapons", {
    method: "DELETE",
    json: weapon,
  });
}

export async function updateRuntimeWeaponQuantity(
  weapon: RuntimeUpdateWeaponQuantityRequest
): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime/weapons/quantity", {
    method: "PATCH",
    json: weapon,
  });
}
