import type { ModelConfig } from "@/features/ai/modelProfiles";

interface BuildChatRequestHeadersOptions {
  chatMode: "ask" | "command";
  modelConfig: ModelConfig;
  modelProviderId?: string;
  scenarioId?: string;
  token?: string | null;
}

const ERROR_MESSAGE_KEYS = [
  "message",
  "error",
  "error_description",
  "detail",
] as const;
const ERROR_CONTAINER_KEYS = ["cause", "response", "data", "body"] as const;

export function buildChatRequestHeaders({
  chatMode,
  modelConfig,
  modelProviderId,
  scenarioId,
  token,
}: BuildChatRequestHeadersOptions): Record<string, string> {
  const headers: Record<string, string> = {
    "X-TianShu-Chat-Mode": chatMode,
  };

  if (token) headers.Authorization = `Bearer ${token}`;
  if (modelProviderId) {
    headers["X-TianShu-Model-Provider-Id"] = modelProviderId;
  }
  if (modelConfig.provider) {
    headers["X-TianShu-Model-Provider"] = modelConfig.provider;
  }
  if (modelConfig.model) {
    headers["X-TianShu-Model-Name"] = modelConfig.model;
  }
  if (modelConfig.apiKey) {
    headers["X-TianShu-Model-Api-Key"] = modelConfig.apiKey;
  }
  if (modelConfig.baseUrl) {
    headers["X-TianShu-Model-Base-Url"] = modelConfig.baseUrl;
  }
  if (scenarioId) {
    headers["X-TianShu-Scenario-Id"] = scenarioId;
  }

  return headers;
}

export function extractChatErrorMessage(error: unknown): string | null {
  return extractChatErrorMessageInternal(error, new Set());
}

export function formatChatError(error: unknown): string {
  const message = extractChatErrorMessage(error) ?? "Unknown chat error";
  const normalized = message.toLowerCase();

  if (
    message.includes("503") ||
    normalized.includes("service unavailable") ||
    normalized.includes("no llm configured")
  ) {
    return "No LLM is configured. Fill the API key in AI model settings, or set TIANSHU_LLM_MODEL and TIANSHU_LLM_API_KEY in the server environment.";
  }

  return message;
}

function extractChatErrorMessageInternal(
  value: unknown,
  seen: Set<unknown>
): string | null {
  if (typeof value === "string") {
    const message = value.trim();
    return message ? message : null;
  }

  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value !== "object") {
    return null;
  }

  if (seen.has(value)) {
    return null;
  }
  seen.add(value);

  if (Array.isArray(value)) {
    for (const item of value) {
      const message = extractChatErrorMessageInternal(item, seen);
      if (message) return message;
    }
    return null;
  }

  const record = value as Record<string, unknown>;
  const directMessage = findMessage(record, ERROR_MESSAGE_KEYS, seen);
  const nestedMessage = findMessage(record, ERROR_CONTAINER_KEYS, seen);

  if (nestedMessage && shouldPreferNestedMessage(directMessage)) {
    return nestedMessage;
  }

  return directMessage ?? nestedMessage;
}

function findMessage(
  record: Record<string, unknown>,
  keys: readonly string[],
  seen: Set<unknown>
): string | null {
  for (const key of keys) {
    const message = extractChatErrorMessageInternal(record[key], seen);
    if (message) return message;
  }
  return null;
}

function shouldPreferNestedMessage(message: string | null): boolean {
  if (!message) return true;

  const normalized = message.trim().toLowerCase();
  return (
    normalized === "unknown chat error" ||
    normalized === "failed to fetch" ||
    normalized.includes("service unavailable") ||
    normalized.includes("request failed") ||
    normalized.startsWith("http 5") ||
    normalized.startsWith("http 4")
  );
}
