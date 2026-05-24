import { z } from "zod";

export type ProviderProtocol =
  | "openai-compatible"
  | "openai-responses"
  | "anthropic";

export interface ProviderModel {
  id: string;
  label?: string;
  group?: string;
  contextWindow?: number;
  recommended?: boolean;
}

export interface ModelProviderDefinition {
  id: string;
  name: string;
  shortName: string;
  description: string;
  protocol: ProviderProtocol;
  defaultBaseUrl: string;
  requiresApiKey: boolean;
  supportsModelList: boolean;
  enabledByDefault: boolean;
  sortOrder: number;
  models: ProviderModel[];
}

export interface ProviderConfig {
  providerId: string;
  displayName: string;
  apiKey: string;
  baseUrl: string;
  enabled: boolean;
  verified: boolean;
  lastCheckedAt: string | null;
  customModels: ProviderModel[];
}

export interface ModelConfig {
  provider: string;
  baseUrl: string;
  apiKey: string;
  model: string;
}

export interface ModelProfile extends ModelConfig {
  id: string;
  providerId: string;
  name: string;
  updatedAt: string;
  isDefault?: boolean;
}

export interface ModelProfileState {
  modelConfig: ModelConfig;
  modelProfiles: ModelProfile[];
  activeModelProfileId: string;
  defaultModelProfileId: string;
}

export const MODEL_STORAGE_KEY = {
  model: "aicc.ai.model",
  modelProfiles: "aicc.ai.modelProfiles",
  activeModelProfileId: "aicc.ai.activeModelProfileId",
  configCenter: "aicc.ai.configCenter.v1",
} as const;

export const modelConfigSchema = z.object({
  provider: z.string().trim().min(1).default("openai"),
  baseUrl: z.string().default(""),
  apiKey: z.string().default(""),
  model: z.string().trim().min(1).default("gpt-4o-mini"),
});

export const providerConfigSchema = z.object({
  providerId: z.string().trim().min(1),
  displayName: z.string().trim().min(1),
  apiKey: z.string().default(""),
  baseUrl: z.string().default(""),
  enabled: z.boolean().default(false),
  verified: z.boolean().default(false),
  lastCheckedAt: z.string().nullable().default(null),
  customModels: z
    .array(
      z.object({
        id: z.string().trim().min(1),
        label: z.string().optional(),
        group: z.string().optional(),
        contextWindow: z.number().optional(),
        recommended: z.boolean().optional(),
      })
    )
    .default([]),
});

export const modelProfileSchema = modelConfigSchema.extend({
  id: z.string().trim().min(1),
  providerId: z.string().trim().min(1).optional(),
  name: z.string().trim().min(1),
  updatedAt: z.string().default(""),
  isDefault: z.boolean().optional(),
});

export type ProviderConfigFormInput = z.input<typeof providerConfigSchema>;
export type ProviderConfigFormValues = z.output<typeof providerConfigSchema>;

export const DEFAULT_MODEL: ModelConfig = {
  provider: "openai",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  model: "gpt-4o-mini",
};

const providerDefinitions = new Map<string, ModelProviderDefinition>();

export function registerModelProvider(
  definition: ModelProviderDefinition
): void {
  providerDefinitions.set(definition.id, definition);
}

export function getModelProviderDefinition(
  providerId: string
): ModelProviderDefinition | undefined {
  return providerDefinitions.get(providerId);
}

export function listModelProviderDefinitions(): ModelProviderDefinition[] {
  return [...providerDefinitions.values()].sort(
    (a, b) => a.sortOrder - b.sortOrder
  );
}

function addProvider(definition: ModelProviderDefinition): void {
  registerModelProvider(definition);
}

addProvider({
  id: "openai",
  name: "OpenAI",
  shortName: "OpenAI",
  description:
    "Chat Completions 兼容模型，适合通用对话、工具调用和结构化输出。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://api.openai.com/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: true,
  sortOrder: 10,
  models: [
    { id: "gpt-5", group: "GPT-5", recommended: true },
    { id: "gpt-5-mini", group: "GPT-5", recommended: true },
    { id: "gpt-4.1", group: "GPT-4.1" },
    { id: "gpt-4o", group: "GPT-4o" },
    { id: "gpt-4o-mini", group: "GPT-4o", recommended: true },
  ],
});

addProvider({
  id: "openai-responses",
  name: "OpenAI Responses",
  shortName: "Responses",
  description: "OpenAI Responses API 格式，适合 GPT-5 与原生结构化输出。",
  protocol: "openai-responses",
  defaultBaseUrl: "https://api.openai.com/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 11,
  models: [
    { id: "gpt-5", group: "GPT-5", recommended: true },
    { id: "gpt-5-mini", group: "GPT-5", recommended: true },
    { id: "gpt-5-nano", group: "GPT-5" },
    { id: "gpt-4.1", group: "GPT-4.1" },
  ],
});

addProvider({
  id: "anthropic",
  name: "Anthropic",
  shortName: "Claude",
  description: "Claude 系列模型，适合长上下文分析、代码和复杂规划。",
  protocol: "anthropic",
  defaultBaseUrl: "https://api.anthropic.com",
  requiresApiKey: true,
  supportsModelList: false,
  enabledByDefault: false,
  sortOrder: 20,
  models: [
    { id: "claude-3-7-sonnet", group: "Claude 3.7", recommended: true },
    { id: "claude-3-5-sonnet", group: "Claude 3.5", recommended: true },
    { id: "claude-3-5-haiku", group: "Claude 3.5" },
  ],
});

addProvider({
  id: "deepseek",
  name: "DeepSeek",
  shortName: "DeepSeek",
  description: "OpenAI-compatible DeepSeek API，适合代码、推理和低成本任务。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://api.deepseek.com/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 30,
  models: [
    { id: "deepseek-chat", group: "DeepSeek", recommended: true },
    { id: "deepseek-reasoner", group: "DeepSeek", recommended: true },
    { id: "deepseek-ai/deepseek-v3.2", group: "OpenRouter/NVIDIA" },
  ],
});

addProvider({
  id: "glm",
  name: "GLM (Zhipu)",
  shortName: "GLM",
  description: "智谱 GLM / BigModel OpenAI-compatible API。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 40,
  models: [
    { id: "glm-4.7", group: "GLM", recommended: true },
    { id: "glm-4.5", group: "GLM" },
    { id: "glm-4-flash", group: "GLM" },
    { id: "z-ai/glm4.7", group: "OpenRouter/NVIDIA" },
  ],
});

addProvider({
  id: "qwen",
  name: "Qwen (Alibaba)",
  shortName: "Qwen",
  description: "通义千问 DashScope OpenAI 兼容模式。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 50,
  models: [
    { id: "qwen-max", group: "Qwen", recommended: true },
    { id: "qwen-plus", group: "Qwen", recommended: true },
    { id: "qwen-turbo", group: "Qwen" },
    { id: "qwen3-max", group: "Qwen" },
  ],
});

addProvider({
  id: "minimax",
  name: "MiniMax",
  shortName: "MiniMax",
  description: "MiniMax OpenAI-compatible API，适合长文本与多模态生态。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://api.minimax.chat/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 60,
  models: [
    { id: "minimax-m2.1", group: "MiniMax", recommended: true },
    { id: "minimax-m1", group: "MiniMax" },
    { id: "minimax-text-01", group: "MiniMax" },
    { id: "minimaxai/minimax-m2.1", group: "OpenRouter/NVIDIA" },
  ],
});

addProvider({
  id: "openrouter",
  name: "OpenRouter",
  shortName: "OpenRouter",
  description: "统一路由多家模型，适合快速横评和备用模型池。",
  protocol: "openai-compatible",
  defaultBaseUrl: "https://openrouter.ai/api/v1",
  requiresApiKey: true,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 70,
  models: [
    { id: "openai/gpt-4o", group: "OpenAI", recommended: true },
    { id: "anthropic/claude-3.7-sonnet", group: "Anthropic" },
    { id: "deepseek/deepseek-chat", group: "DeepSeek", recommended: true },
    { id: "minimaxai/minimax-m2.1", group: "MiniMax", recommended: true },
    { id: "z-ai/glm-4.5", group: "GLM" },
  ],
});

addProvider({
  id: "ollama",
  name: "Ollama",
  shortName: "Ollama",
  description: "本地模型服务，默认连接本机 Ollama OpenAI 兼容接口。",
  protocol: "openai-compatible",
  defaultBaseUrl: "http://localhost:11434/v1",
  requiresApiKey: false,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 80,
  models: [
    { id: "llama3.1", group: "Local", recommended: true },
    { id: "qwen2.5", group: "Local", recommended: true },
    { id: "mistral", group: "Local" },
  ],
});

addProvider({
  id: "custom",
  name: "Custom OpenAI Compatible",
  shortName: "Custom",
  description: "自定义 OpenAI-compatible 服务，需要填写 Base URL。",
  protocol: "openai-compatible",
  defaultBaseUrl: "",
  requiresApiKey: false,
  supportsModelList: true,
  enabledByDefault: false,
  sortOrder: 100,
  models: [],
});

export const MODEL_PROVIDER_OPTIONS = listModelProviderDefinitions().map(
  (definition) => definition.id
);

export const MODEL_PRESETS: Record<string, string[]> =
  listModelProviderDefinitions().reduce<Record<string, string[]>>(
    (acc, definition) => {
      acc[definition.id] = definition.models.map((model) => model.id);
      return acc;
    },
    {}
  );

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readLocalJson(key: string): unknown {
  try {
    if (typeof window === "undefined") return undefined;
    const raw = window.localStorage.getItem(key);
    if (!raw) return undefined;
    return JSON.parse(raw) as unknown;
  } catch {
    return undefined;
  }
}

function writeLocalJson(key: string, value: unknown): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore quota / privacy mode errors
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function boolValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

export function normalizeModelConfig(value: unknown): ModelConfig {
  const parsed = modelConfigSchema.safeParse(value);
  if (parsed.success) return parsed.data;
  return DEFAULT_MODEL;
}

export function createProviderConfig(
  definition: ModelProviderDefinition,
  overrides: Partial<ProviderConfig> = {}
): ProviderConfig {
  return providerConfigSchema.parse({
    providerId: definition.id,
    displayName: definition.name,
    apiKey: "",
    baseUrl: definition.defaultBaseUrl,
    enabled: definition.enabledByDefault,
    verified: false,
    lastCheckedAt: null,
    customModels: [],
    ...overrides,
  });
}

export function normalizeProviderConfig(
  providerId: string,
  value: unknown
): ProviderConfig {
  const definition = getModelProviderDefinition(providerId);
  const fallback = definition
    ? createProviderConfig(definition)
    : createProviderConfig(getModelProviderDefinition("custom")!, {
        providerId,
        displayName: providerId,
      });
  if (!isRecord(value)) return fallback;
  const parsed = providerConfigSchema.safeParse({
    ...fallback,
    ...value,
    providerId,
  });
  return parsed.success ? parsed.data : fallback;
}

export function createDefaultProviderConfigs(): Record<string, ProviderConfig> {
  return listModelProviderDefinitions().reduce<Record<string, ProviderConfig>>(
    (acc, definition) => {
      acc[definition.id] = createProviderConfig(definition);
      return acc;
    },
    {}
  );
}

export function getProviderModels(
  providerId: string,
  config?: ProviderConfig
): ProviderModel[] {
  const definition = getModelProviderDefinition(providerId);
  const baseModels = definition?.models ?? [];
  const customModels = config?.customModels ?? [];
  const seen = new Set<string>();
  return [...baseModels, ...customModels].filter((model) => {
    if (seen.has(model.id)) return false;
    seen.add(model.id);
    return true;
  });
}

export function providerRuntimeId(providerId: string): string {
  return providerId.startsWith("custom-") ? "custom" : providerId;
}

export function buildModelConfig(
  providerId: string,
  modelId: string,
  providerConfig?: ProviderConfig
): ModelConfig {
  const definition = getModelProviderDefinition(providerId);
  return {
    provider: providerRuntimeId(providerId),
    baseUrl: providerConfig?.baseUrl ?? definition?.defaultBaseUrl ?? "",
    apiKey: providerConfig?.apiKey ?? "",
    model: modelId,
  };
}

export function profileToConfig(profile: ModelProfile): ModelConfig {
  return {
    provider: profile.provider,
    baseUrl: profile.baseUrl,
    apiKey: profile.apiKey,
    model: profile.model,
  };
}

export function sameModelConfig(a: ModelConfig, b: ModelConfig): boolean {
  return (
    a.provider === b.provider &&
    a.baseUrl === b.baseUrl &&
    a.apiKey === b.apiKey &&
    a.model === b.model
  );
}

export function modelProfileEndpointLabel(baseUrl: string): string {
  const trimmed = baseUrl.trim();
  if (!trimmed) return "default endpoint";
  try {
    return new URL(trimmed).host || trimmed;
  } catch {
    return trimmed.replace(/^https?:\/\//i, "").split("/")[0] || trimmed;
  }
}

export function modelProfileLabel(
  config: ModelConfig,
  providerName?: string
): string {
  const endpoint = modelProfileEndpointLabel(config.baseUrl);
  const suffix = endpoint === "default endpoint" ? "" : ` / ${endpoint}`;
  return `${providerName ?? config.provider} / ${config.model}${suffix}`;
}

export function createModelProfileId(): string {
  const webCrypto = globalThis.crypto;
  if (webCrypto && "randomUUID" in webCrypto) {
    return `model-${webCrypto.randomUUID()}`;
  }
  return `model-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createModelProfile(
  config: ModelConfig,
  name?: string,
  id = createModelProfileId(),
  providerId = config.provider,
  isDefault = false
): ModelProfile {
  const normalized = normalizeModelConfig(config);
  const definition = getModelProviderDefinition(providerId);
  return {
    ...normalized,
    id,
    providerId,
    name:
      name?.trim() ||
      modelProfileLabel(normalized, definition?.shortName ?? definition?.name),
    updatedAt: new Date().toISOString(),
    isDefault,
  };
}

export function normalizeModelProfile(value: unknown): ModelProfile | null {
  const parsed = modelProfileSchema.safeParse(value);
  if (!parsed.success) return null;
  const providerId = parsed.data.providerId ?? parsed.data.provider;
  return {
    ...parsed.data,
    providerId,
  };
}

function uniqueProfiles(values: unknown): ModelProfile[] {
  if (!Array.isArray(values)) return [];
  const seen = new Set<string>();
  const profiles: ModelProfile[] = [];
  for (const value of values) {
    const profile = normalizeModelProfile(value);
    if (!profile || seen.has(profile.id)) continue;
    seen.add(profile.id);
    profiles.push(profile);
  }
  return profiles;
}

export function readModelProfileState(): ModelProfileState {
  const modelConfig = normalizeModelConfig(
    readLocalJson(MODEL_STORAGE_KEY.model)
  );
  const profiles = uniqueProfiles(
    readLocalJson(MODEL_STORAGE_KEY.modelProfiles)
  );
  const storedActiveId =
    stringValue(readLocalJson(MODEL_STORAGE_KEY.activeModelProfileId)) ?? "";
  const storedActiveExists = profiles.some((p) => p.id === storedActiveId);
  const matchingProfile = profiles.find((p) =>
    sameModelConfig(profileToConfig(p), modelConfig)
  );
  let activeModelProfileId = storedActiveExists
    ? storedActiveId
    : (matchingProfile?.id ?? "");
  let modelProfiles = profiles;

  if (!activeModelProfileId) {
    const migratedProfile = createModelProfile(
      modelConfig,
      modelProfileLabel(modelConfig),
      undefined,
      modelConfig.provider,
      true
    );
    modelProfiles = [migratedProfile, ...profiles];
    activeModelProfileId = migratedProfile.id;
  }

  const defaultModelProfileId =
    modelProfiles.find((profile) => profile.isDefault)?.id ??
    activeModelProfileId;

  return {
    modelConfig,
    modelProfiles: modelProfiles.map((profile) => ({
      ...profile,
      isDefault: profile.id === defaultModelProfileId,
    })),
    activeModelProfileId,
    defaultModelProfileId,
  };
}

export function readPersistedProviderConfigs(): Record<string, ProviderConfig> {
  const raw = readLocalJson(MODEL_STORAGE_KEY.configCenter);
  const persisted = isRecord(raw) && isRecord(raw.state) ? raw.state : {};
  const rawProviders = isRecord(persisted.providerConfigs)
    ? persisted.providerConfigs
    : {};
  const configs = createDefaultProviderConfigs();
  for (const providerId of Object.keys(rawProviders)) {
    configs[providerId] = normalizeProviderConfig(
      providerId,
      rawProviders[providerId]
    );
  }
  return configs;
}

export function writeLegacyModelState(
  modelConfig: ModelConfig,
  modelProfiles: ModelProfile[],
  activeModelProfileId: string
): void {
  writeLocalJson(MODEL_STORAGE_KEY.model, modelConfig);
  writeLocalJson(MODEL_STORAGE_KEY.modelProfiles, modelProfiles);
  writeLocalJson(MODEL_STORAGE_KEY.activeModelProfileId, activeModelProfileId);
}

export function providerConfigFromLegacyModel(
  config: ModelConfig
): Partial<ProviderConfig> {
  const providerId = config.provider;
  return {
    providerId,
    baseUrl: config.baseUrl,
    apiKey: config.apiKey,
    enabled: true,
  };
}

export function modelConfigFromMaybeProfile(value: unknown): ModelConfig {
  if (isRecord(value) && "model" in value) {
    return normalizeModelConfig(value);
  }
  return DEFAULT_MODEL;
}

export function isProviderVerified(config: ProviderConfig): boolean {
  if (config.verified) return true;
  const definition = getModelProviderDefinition(config.providerId);
  return Boolean(definition && !definition.requiresApiKey && config.enabled);
}

export function providerNeedsApiKey(providerId: string): boolean {
  return getModelProviderDefinition(providerId)?.requiresApiKey ?? true;
}

export function providerSupportsModelList(providerId: string): boolean {
  return getModelProviderDefinition(providerId)?.supportsModelList ?? true;
}

export function isEnabledRaw(value: unknown): boolean | undefined {
  return boolValue(value);
}
