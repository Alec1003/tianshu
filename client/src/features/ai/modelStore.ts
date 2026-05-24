import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  DEFAULT_MODEL,
  MODEL_STORAGE_KEY,
  buildModelConfig,
  createDefaultProviderConfigs,
  createModelProfile,
  createModelProfileId,
  getModelProviderDefinition,
  getProviderModels,
  listModelProviderDefinitions,
  modelProfileLabel,
  normalizeProviderConfig,
  providerConfigFromLegacyModel,
  providerRuntimeId,
  profileToConfig,
  readModelProfileState,
  readPersistedProviderConfigs,
  sameModelConfig,
  writeLegacyModelState,
  type ModelConfig,
  type ModelProfile,
  type ProviderConfig,
  type ProviderModel,
} from "./modelProfiles";

export interface ModelOption extends ProviderModel {
  providerId: string;
  providerName: string;
  providerShortName: string;
  profileId?: string;
  enabled: boolean;
  verified: boolean;
  isActive: boolean;
  isDefault: boolean;
}

interface ModelConfigStoreState {
  providerConfigs: Record<string, ProviderConfig>;
  modelProfiles: ModelProfile[];
  activeModelProfileId: string;
  defaultModelProfileId: string;
  activeModelConfig: ModelConfig;
  showUnverifiedModels: boolean;
  updateProviderConfig: (
    providerId: string,
    patch: Partial<ProviderConfig>
  ) => void;
  setProviderEnabled: (providerId: string, enabled: boolean) => void;
  markProviderChecked: (providerId: string, verified: boolean) => void;
  addCustomModel: (providerId: string, modelId: string) => void;
  removeCustomModel: (providerId: string, modelId: string) => void;
  selectModel: (providerId: string, modelId: string) => void;
  selectModelProfile: (profileId: string) => void;
  saveActiveProfile: (name?: string) => void;
  createProfileFromActive: (name?: string) => void;
  deleteModelProfile: (profileId: string) => void;
  setDefaultModelProfile: (profileId: string) => void;
  updateActiveModelConfig: (next: ModelConfig) => void;
  setShowUnverifiedModels: (show: boolean) => void;
  getModelOptions: () => ModelOption[];
}

function createProviderConfigsFromLegacyModel(
  activeConfig: ModelConfig
): Record<string, ProviderConfig> {
  const configs = {
    ...createDefaultProviderConfigs(),
    ...readPersistedProviderConfigs(),
  };
  const legacyProviderId = activeConfig.provider || DEFAULT_MODEL.provider;
  configs[legacyProviderId] = normalizeProviderConfig(legacyProviderId, {
    ...(configs[legacyProviderId] ?? {}),
    ...providerConfigFromLegacyModel(activeConfig),
  });
  return configs;
}

function profileFromSelection(
  providerConfigs: Record<string, ProviderConfig>,
  providerId: string,
  modelId: string,
  name?: string,
  isDefault = false,
  id = createModelProfileId()
): ModelProfile {
  const providerConfig = providerConfigs[providerId];
  const definition = getModelProviderDefinition(providerId);
  const config = buildModelConfig(providerId, modelId, providerConfig);
  return createModelProfile(
    config,
    name ||
      modelProfileLabel(config, definition?.shortName ?? definition?.name),
    id,
    providerId,
    isDefault
  );
}

function withDefaultFlags(
  profiles: ModelProfile[],
  defaultModelProfileId: string
): ModelProfile[] {
  return profiles.map((profile) => ({
    ...profile,
    isDefault: profile.id === defaultModelProfileId,
  }));
}

function activeConfigFromProfile(
  profile: ModelProfile | undefined,
  providerConfigs: Record<string, ProviderConfig>
): ModelConfig {
  if (!profile) return DEFAULT_MODEL;
  const providerConfig = providerConfigs[profile.providerId];
  return {
    ...profileToConfig(profile),
    apiKey: providerConfig?.apiKey ?? profile.apiKey,
    baseUrl: providerConfig?.baseUrl ?? profile.baseUrl,
  };
}

function syncLegacy(
  state: Pick<
    ModelConfigStoreState,
    "activeModelConfig" | "modelProfiles" | "activeModelProfileId"
  >
): void {
  writeLegacyModelState(
    state.activeModelConfig,
    state.modelProfiles,
    state.activeModelProfileId
  );
}

function createInitialState(): Pick<
  ModelConfigStoreState,
  | "providerConfigs"
  | "modelProfiles"
  | "activeModelProfileId"
  | "defaultModelProfileId"
  | "activeModelConfig"
  | "showUnverifiedModels"
> {
  const legacy = readModelProfileState();
  const providerConfigs = createProviderConfigsFromLegacyModel(
    legacy.modelConfig
  );
  const activeProfile =
    legacy.modelProfiles.find(
      (profile) => profile.id === legacy.activeModelProfileId
    ) ?? legacy.modelProfiles[0];
  const activeModelConfig = activeConfigFromProfile(
    activeProfile,
    providerConfigs
  );

  return {
    providerConfigs,
    modelProfiles: withDefaultFlags(
      legacy.modelProfiles,
      legacy.defaultModelProfileId
    ),
    activeModelProfileId: legacy.activeModelProfileId,
    defaultModelProfileId: legacy.defaultModelProfileId,
    activeModelConfig,
    showUnverifiedModels: true,
  };
}

export const useModelConfigStore = create<ModelConfigStoreState>()(
  persist(
    (set, get) => ({
      ...createInitialState(),

      updateProviderConfig: (providerId, patch) => {
        set((state) => {
          const current =
            state.providerConfigs[providerId] ??
            normalizeProviderConfig(providerId, {});
          const providerConfigs = {
            ...state.providerConfigs,
            [providerId]: normalizeProviderConfig(providerId, {
              ...current,
              ...patch,
              verified:
                patch.apiKey !== undefined || patch.baseUrl !== undefined
                  ? false
                  : (patch.verified ?? current.verified),
            }),
          };
          const activeProfile = state.modelProfiles.find(
            (profile) => profile.id === state.activeModelProfileId
          );
          const activeModelConfig = activeConfigFromProfile(
            activeProfile,
            providerConfigs
          );
          const next = { providerConfigs, activeModelConfig };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      setProviderEnabled: (providerId, enabled) => {
        get().updateProviderConfig(providerId, { enabled });
      },

      markProviderChecked: (providerId, verified) => {
        get().updateProviderConfig(providerId, {
          verified,
          lastCheckedAt: new Date().toISOString(),
        });
      },

      addCustomModel: (providerId, modelId) => {
        const trimmed = modelId.trim();
        if (!trimmed) return;
        set((state) => {
          const current =
            state.providerConfigs[providerId] ??
            normalizeProviderConfig(providerId, {});
          if (
            getProviderModels(providerId, current).some((m) => m.id === trimmed)
          ) {
            return {};
          }
          return {
            providerConfigs: {
              ...state.providerConfigs,
              [providerId]: {
                ...current,
                customModels: [
                  ...current.customModels,
                  { id: trimmed, group: "Custom", recommended: true },
                ],
              },
            },
          };
        });
      },

      removeCustomModel: (providerId, modelId) => {
        set((state) => {
          const current = state.providerConfigs[providerId];
          if (!current) return {};
          return {
            providerConfigs: {
              ...state.providerConfigs,
              [providerId]: {
                ...current,
                customModels: current.customModels.filter(
                  (model) => model.id !== modelId
                ),
              },
            },
          };
        });
      },

      selectModel: (providerId, modelId) => {
        set((state) => {
          const existing = state.modelProfiles.find(
            (profile) =>
              profile.providerId === providerId && profile.model === modelId
          );
          const profile =
            existing ??
            profileFromSelection(state.providerConfigs, providerId, modelId);
          const modelProfiles = existing
            ? state.modelProfiles
            : [profile, ...state.modelProfiles];
          const defaultModelProfileId = profile.id;
          const nextProfiles = withDefaultFlags(
            modelProfiles,
            defaultModelProfileId
          );
          const activeModelConfig = activeConfigFromProfile(
            profile,
            state.providerConfigs
          );
          const next = {
            modelProfiles: nextProfiles,
            activeModelProfileId: profile.id,
            defaultModelProfileId,
            activeModelConfig,
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      selectModelProfile: (profileId) => {
        set((state) => {
          const profile = state.modelProfiles.find(
            (item) => item.id === profileId
          );
          if (!profile) return {};
          const activeModelConfig = activeConfigFromProfile(
            profile,
            state.providerConfigs
          );
          const next = {
            activeModelProfileId: profile.id,
            activeModelConfig,
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      saveActiveProfile: (name) => {
        set((state) => {
          const activeExists = state.modelProfiles.some(
            (profile) => profile.id === state.activeModelProfileId
          );
          const activeProviderId =
            state.modelProfiles.find(
              (profile) => profile.id === state.activeModelProfileId
            )?.providerId ?? state.activeModelConfig.provider;
          const profile = createModelProfile(
            state.activeModelConfig,
            name,
            activeExists ? state.activeModelProfileId : undefined,
            activeProviderId,
            state.defaultModelProfileId === state.activeModelProfileId
          );
          const modelProfiles = activeExists
            ? state.modelProfiles.map((item) =>
                item.id === profile.id ? profile : item
              )
            : [profile, ...state.modelProfiles];
          const next = {
            modelProfiles: withDefaultFlags(
              modelProfiles,
              state.defaultModelProfileId || profile.id
            ),
            activeModelProfileId: profile.id,
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      createProfileFromActive: (name) => {
        set((state) => {
          const activeProviderId =
            state.modelProfiles.find(
              (profile) => profile.id === state.activeModelProfileId
            )?.providerId ?? state.activeModelConfig.provider;
          const profile = createModelProfile(
            state.activeModelConfig,
            name,
            undefined,
            activeProviderId
          );
          const next = {
            modelProfiles: [profile, ...state.modelProfiles],
            activeModelProfileId: profile.id,
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      deleteModelProfile: (profileId) => {
        set((state) => {
          const remaining = state.modelProfiles.filter(
            (profile) => profile.id !== profileId
          );
          if (remaining.length === state.modelProfiles.length) return {};
          const modelProfiles =
            remaining.length > 0
              ? remaining
              : [
                  profileFromSelection(
                    state.providerConfigs,
                    DEFAULT_MODEL.provider,
                    DEFAULT_MODEL.model,
                    "OpenAI / gpt-4o-mini",
                    true
                  ),
                ];
          const activeProfile =
            state.activeModelProfileId === profileId
              ? modelProfiles[0]
              : (modelProfiles.find(
                  (profile) => profile.id === state.activeModelProfileId
                ) ?? modelProfiles[0]);
          const defaultModelProfileId =
            state.defaultModelProfileId === profileId
              ? activeProfile.id
              : state.defaultModelProfileId;
          const next = {
            modelProfiles: withDefaultFlags(
              modelProfiles,
              defaultModelProfileId
            ),
            activeModelProfileId: activeProfile.id,
            defaultModelProfileId,
            activeModelConfig: activeConfigFromProfile(
              activeProfile,
              state.providerConfigs
            ),
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      setDefaultModelProfile: (profileId) => {
        set((state) => {
          const profile = state.modelProfiles.find(
            (item) => item.id === profileId
          );
          if (!profile) return {};
          const next = {
            modelProfiles: withDefaultFlags(state.modelProfiles, profileId),
            defaultModelProfileId: profileId,
            activeModelProfileId: profileId,
            activeModelConfig: activeConfigFromProfile(
              profile,
              state.providerConfigs
            ),
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      updateActiveModelConfig: (nextConfig) => {
        set((state) => {
          const activeProfile = state.modelProfiles.find(
            (profile) => profile.id === state.activeModelProfileId
          );
          const providerId = activeProfile?.providerId ?? nextConfig.provider;
          const modelProfiles = state.modelProfiles.map((profile) =>
            profile.id === state.activeModelProfileId
              ? {
                  ...profile,
                  ...nextConfig,
                  providerId,
                  updatedAt: new Date().toISOString(),
                }
              : profile
          );
          const providerConfig = state.providerConfigs[providerId];
          const providerConfigs = providerConfig
            ? {
                ...state.providerConfigs,
                [providerId]: {
                  ...providerConfig,
                  apiKey: nextConfig.apiKey,
                  baseUrl: nextConfig.baseUrl,
                  verified: sameModelConfig(state.activeModelConfig, nextConfig)
                    ? providerConfig.verified
                    : false,
                },
              }
            : state.providerConfigs;
          const next = {
            providerConfigs,
            modelProfiles,
            activeModelConfig: nextConfig,
          };
          syncLegacy({ ...state, ...next });
          return next;
        });
      },

      setShowUnverifiedModels: (show) => {
        set({ showUnverifiedModels: show });
      },

      getModelOptions: () => {
        const state = get();
        const activeProfile = state.modelProfiles.find(
          (profile) => profile.id === state.activeModelProfileId
        );
        return listModelProviderDefinitions().flatMap((definition) => {
          const config = state.providerConfigs[definition.id];
          const enabled = Boolean(config?.enabled);
          const verified = Boolean(
            config?.verified || !definition.requiresApiKey
          );
          if (!enabled) return [];
          if (!state.showUnverifiedModels && !verified) return [];
          return getProviderModels(definition.id, config).map((model) => {
            const profile = state.modelProfiles.find(
              (item) =>
                item.providerId === definition.id && item.model === model.id
            );
            return {
              ...model,
              providerId: definition.id,
              providerName: definition.name,
              providerShortName: definition.shortName,
              profileId: profile?.id,
              enabled,
              verified,
              isActive:
                activeProfile?.providerId === definition.id &&
                state.activeModelConfig.provider ===
                  providerRuntimeId(definition.id) &&
                state.activeModelConfig.model === model.id,
              isDefault: profile?.id === state.defaultModelProfileId,
            };
          });
        });
      },
    }),
    {
      name: MODEL_STORAGE_KEY.configCenter,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        providerConfigs: state.providerConfigs,
        modelProfiles: state.modelProfiles,
        activeModelProfileId: state.activeModelProfileId,
        defaultModelProfileId: state.defaultModelProfileId,
        activeModelConfig: state.activeModelConfig,
        showUnverifiedModels: state.showUnverifiedModels,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) syncLegacy(state);
      },
    }
  )
);
