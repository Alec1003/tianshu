import { apiCall } from "./client";

export interface ServerModelProviderConfig {
  providerId: string;
  displayName: string;
  baseUrl: string;
  enabled: boolean;
  verified: boolean;
  lastCheckedAt: string | null;
  customModels: Array<Record<string, unknown>>;
  apiKeySet: boolean;
}

export interface ServerModelProviderConfigUpdate {
  displayName: string;
  baseUrl: string;
  apiKey?: string;
  clearApiKey?: boolean;
  enabled: boolean;
  verified: boolean;
  lastCheckedAt: string | null;
  customModels: Array<Record<string, unknown>>;
}

export async function listServerModelProviders(): Promise<
  ServerModelProviderConfig[]
> {
  const payload = await apiCall<{ providers: ServerModelProviderConfig[] }>(
    "/api/ai/model/providers"
  );
  return payload.providers;
}

export async function saveServerModelProvider(
  providerId: string,
  payload: ServerModelProviderConfigUpdate
): Promise<ServerModelProviderConfig> {
  return apiCall<ServerModelProviderConfig>(
    `/api/ai/model/providers/${encodeURIComponent(providerId)}`,
    {
      method: "PUT",
      json: payload,
    }
  );
}
