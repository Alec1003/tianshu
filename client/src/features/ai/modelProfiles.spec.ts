import { beforeEach, describe, expect, it } from "vitest";
import {
  MODEL_STORAGE_KEY,
  createModelProfile,
  getModelProviderDefinition,
  listModelProviderDefinitions,
  profileToConfig,
  readModelProfileState,
  readPersistedProviderConfigs,
  type ModelConfig,
} from "./modelProfiles";

const customModel: ModelConfig = {
  provider: "openai-responses",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "test-key",
  model: "gpt-5-mini",
};

const customModelWithoutSecret: ModelConfig = {
  ...customModel,
  apiKey: "",
};

describe("modelProfiles", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("migrates the legacy active model into a saved profile", () => {
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.model,
      JSON.stringify(customModel)
    );

    const state = readModelProfileState();

    expect(state.modelConfig).toEqual(customModelWithoutSecret);
    expect(state.modelProfiles).toHaveLength(1);
    expect(state.modelProfiles[0]).toMatchObject(customModelWithoutSecret);
    expect(state.activeModelProfileId).toBe(state.modelProfiles[0].id);
  });

  it("keeps the legacy active model authoritative when profiles already exist", () => {
    const savedProfile = createModelProfile(
      {
        provider: "anthropic",
        baseUrl: "https://api.anthropic.com/v1",
        apiKey: "anthropic-key",
        model: "claude-3-5-sonnet",
      },
      "Claude"
    );

    window.localStorage.setItem(
      MODEL_STORAGE_KEY.model,
      JSON.stringify(customModel)
    );
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.modelProfiles,
      JSON.stringify([savedProfile])
    );
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.activeModelProfileId,
      JSON.stringify(savedProfile.id)
    );

    const state = readModelProfileState();

    expect(state.modelConfig).toEqual(customModelWithoutSecret);
    expect(state.activeModelProfileId).toBe(savedProfile.id);
    expect(profileToConfig(state.modelProfiles[0])).toEqual({
      ...profileToConfig(savedProfile),
      apiKey: "",
    });
  });

  it("selects an existing matching profile when no active profile is stored", () => {
    const matchingProfile = createModelProfile(customModel, "OpenAI Responses");
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.model,
      JSON.stringify(customModel)
    );
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.modelProfiles,
      JSON.stringify([matchingProfile])
    );

    const state = readModelProfileState();

    expect(state.modelProfiles).toHaveLength(1);
    expect(state.activeModelProfileId).toBe(matchingProfile.id);
  });

  it("registers the multi-provider model catalog", () => {
    const providerIds = listModelProviderDefinitions().map(
      (definition) => definition.id
    );

    expect(providerIds).toEqual(
      expect.arrayContaining([
        "openai",
        "openai-responses",
        "anthropic",
        "deepseek",
        "glm",
        "qwen",
        "minimax",
        "openrouter",
        "ollama",
      ])
    );
    expect(getModelProviderDefinition("openrouter")?.defaultBaseUrl).toBe(
      "https://openrouter.ai/api/v1"
    );
  });

  it("reads persisted provider configs with defaults", () => {
    window.localStorage.setItem(
      MODEL_STORAGE_KEY.configCenter,
      JSON.stringify({
        state: {
          providerConfigs: {
            glm: {
              providerId: "glm",
              displayName: "GLM",
              apiKey: "glm-key",
              baseUrl: "https://open.bigmodel.cn/api/paas/v4",
              enabled: true,
              verified: true,
              lastCheckedAt: "2026-05-24T00:00:00.000Z",
              customModels: [{ id: "glm-custom" }],
            },
          },
        },
      })
    );

    const configs = readPersistedProviderConfigs();

    expect(configs.glm).toMatchObject({
      apiKey: "",
      enabled: true,
      verified: true,
    });
    expect(configs.openai.baseUrl).toBe("https://api.openai.com/v1");
  });
});
