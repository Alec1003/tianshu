import { apiCall } from "./client";
import type {
  UnitAsset,
  UnitAssetCatalogPayload,
  UnitAssetCreatePayload,
  UnitAssetGeneratePayload,
  UnitAssetGenerateResult,
  UnitAssetImportPayload,
  UnitAssetImportResult,
  UnitAssetType,
  UnitAssetUpdatePayload,
} from "./types";

interface StoredModelConfig {
  provider?: string;
  baseUrl?: string;
  model?: string;
}

interface StoredModelProfile {
  id?: string;
  providerId?: string;
}

function readActiveModelProviderId(fallbackProvider?: string): string {
  try {
    const activeId = window.localStorage.getItem(
      "aicc.ai.activeModelProfileId"
    );
    const rawProfiles = window.localStorage.getItem("aicc.ai.modelProfiles");
    const profiles = rawProfiles
      ? (JSON.parse(rawProfiles) as StoredModelProfile[])
      : [];
    const activeProfile = Array.isArray(profiles)
      ? profiles.find((profile) => profile.id === activeId)
      : undefined;
    return activeProfile?.providerId || fallbackProvider || "";
  } catch {
    return fallbackProvider || "";
  }
}

function readModelHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem("aicc.ai.model");
    if (!raw) return {};
    const config = JSON.parse(raw) as StoredModelConfig;
    const headers: Record<string, string> = {};
    const providerId = readActiveModelProviderId(config.provider);
    if (providerId) headers["X-AICC-Model-Provider-Id"] = providerId;
    if (config.provider) headers["X-AICC-Model-Provider"] = config.provider;
    if (config.model) headers["X-AICC-Model-Name"] = config.model;
    if (config.baseUrl) headers["X-AICC-Model-Base-Url"] = config.baseUrl;
    return headers;
  } catch {
    return {};
  }
}

export async function listUnitAssets(
  type?: UnitAssetType
): Promise<UnitAsset[]> {
  const query = type ? `?type=${encodeURIComponent(type)}` : "";
  return apiCall<UnitAsset[]>(`/api/unit-assets${query}`);
}

export async function getUnitAssetCatalog(): Promise<UnitAssetCatalogPayload> {
  return apiCall<UnitAssetCatalogPayload>("/api/unit-assets/catalog");
}

export async function createUnitAsset(
  payload: UnitAssetCreatePayload
): Promise<UnitAsset> {
  return apiCall<UnitAsset>("/api/unit-assets", {
    method: "POST",
    json: payload,
  });
}

export async function generateUnitAsset(
  payload: UnitAssetGeneratePayload
): Promise<UnitAssetGenerateResult> {
  return apiCall<UnitAssetGenerateResult>("/api/unit-assets/generate", {
    method: "POST",
    headers: readModelHeaders(),
    json: payload,
  });
}

export async function updateUnitAsset(
  id: string,
  payload: UnitAssetUpdatePayload
): Promise<UnitAsset> {
  return apiCall<UnitAsset>(`/api/unit-assets/${encodeURIComponent(id)}`, {
    method: "PATCH",
    json: payload,
  });
}

export async function deleteUnitAsset(id: string): Promise<void> {
  await apiCall<void>(`/api/unit-assets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function importUnitAssets(
  payload: UnitAssetImportPayload
): Promise<UnitAssetImportResult> {
  return apiCall<UnitAssetImportResult>("/api/unit-assets/import", {
    method: "POST",
    json: payload,
  });
}

export async function resetUnitAssets(): Promise<UnitAsset[]> {
  return apiCall<UnitAsset[]>("/api/unit-assets/reset", {
    method: "POST",
  });
}
