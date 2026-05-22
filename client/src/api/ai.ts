import { apiCall } from "./client";
import type { RuntimeSnapshot } from "./types";

export async function getRuntimeScenario(): Promise<Record<string, unknown>> {
  return apiCall<Record<string, unknown>>("/api/ai/runtime/scenario");
}

export async function getRuntimeSnapshot(): Promise<RuntimeSnapshot> {
  return apiCall<RuntimeSnapshot>("/api/ai/runtime");
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
