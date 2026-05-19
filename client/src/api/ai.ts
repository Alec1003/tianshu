import { apiCall } from "./client";

export async function getRuntimeScenario(): Promise<Record<string, unknown>> {
  return apiCall<Record<string, unknown>>("/api/ai/runtime/scenario");
}
