import { useEffect, useMemo, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  KeyRound,
  Link2,
  Loader2,
  Plus,
  Search,
  Server,
  Settings2,
  Sparkles,
  Star,
  Tag,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

import { apiCall } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  buildModelConfig,
  getModelProviderDefinition,
  getProviderModels,
  listModelProviderDefinitions,
  modelProfileEndpointLabel,
  providerConfigSchema,
  providerNeedsApiKey,
  type ProviderConfigFormInput,
  type ProviderConfigFormValues,
} from "./modelProfiles";
import { useModelConfigStore } from "./modelStore";

interface ModelCheckResponse {
  status: "ok" | "partial" | "error";
  message: string;
  provider: string;
  endpoint: string;
  auth_ok: boolean;
  models_listed: boolean;
  checked_model?: string | null;
  checked_model_exists?: boolean | null;
  http_status?: number | null;
  sample_models?: string[];
  error?: string | null;
}

const ADDABLE_PROVIDER_IDS = [
  "openai",
  "openai-responses",
  "anthropic",
  "deepseek",
  "glm",
  "qwen",
  "minimax",
  "openrouter",
  "ollama",
  "custom",
] as const;

const INPUT_CLASS =
  "h-10 w-full rounded-md border border-cyan-300/15 bg-slate-950/65 px-3 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-600 focus:border-cyan-300/45 focus:ring-4 focus:ring-cyan-300/10";
const SMALL_INPUT_CLASS =
  "h-9 w-full rounded-md border border-cyan-300/15 bg-slate-950/65 px-3 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-600 focus:border-cyan-300/45 focus:ring-4 focus:ring-cyan-300/10";
const LABEL_CLASS =
  "flex items-center gap-2 text-sm font-medium text-slate-200";

function providerGlyph(providerId: string): string {
  const glyphs: Record<string, string> = {
    openai: "O",
    "openai-responses": "R",
    anthropic: "A",
    deepseek: "D",
    glm: "G",
    qwen: "Q",
    minimax: "M",
    openrouter: "OR",
    ollama: "OL",
    custom: "C",
  };
  return glyphs[providerId] ?? providerId.slice(0, 2).toUpperCase();
}

function checkTone(result: ModelCheckResponse | null): string {
  if (!result) return "";
  if (result.status === "ok") {
    return "border-emerald-400/25 bg-emerald-500/10 text-emerald-100";
  }
  if (result.status === "partial") {
    return "border-amber-400/25 bg-amber-500/10 text-amber-100";
  }
  return "border-red-400/25 bg-red-500/10 text-red-100";
}

function checkIcon(result: ModelCheckResponse) {
  if (result.status === "ok") return <CheckCircle2 className="size-4" />;
  if (result.status === "partial") return <AlertCircle className="size-4" />;
  return <XCircle className="size-4" />;
}

function checkTitle(result: ModelCheckResponse): string {
  if (result.status === "ok") return "连接已验证";
  if (result.status === "partial") return "端点可访问";
  return "连接异常";
}

export default function ModelConfigCenter() {
  const definitions = useMemo(listModelProviderDefinitions, []);
  const providerConfigs = useModelConfigStore((state) => state.providerConfigs);
  const modelProfiles = useModelConfigStore((state) => state.modelProfiles);
  const activeModelConfig = useModelConfigStore(
    (state) => state.activeModelConfig
  );
  const activeProfileId = useModelConfigStore(
    (state) => state.activeModelProfileId
  );
  const defaultProfileId = useModelConfigStore(
    (state) => state.defaultModelProfileId
  );
  const showUnverifiedModels = useModelConfigStore(
    (state) => state.showUnverifiedModels
  );
  const updateProviderConfig = useModelConfigStore(
    (state) => state.updateProviderConfig
  );
  const setProviderEnabled = useModelConfigStore(
    (state) => state.setProviderEnabled
  );
  const markProviderChecked = useModelConfigStore(
    (state) => state.markProviderChecked
  );
  const addCustomModel = useModelConfigStore((state) => state.addCustomModel);
  const removeCustomModel = useModelConfigStore(
    (state) => state.removeCustomModel
  );
  const selectModel = useModelConfigStore((state) => state.selectModel);
  const selectModelProfile = useModelConfigStore(
    (state) => state.selectModelProfile
  );
  const deleteModelProfile = useModelConfigStore(
    (state) => state.deleteModelProfile
  );
  const setDefaultModelProfile = useModelConfigStore(
    (state) => state.setDefaultModelProfile
  );
  const setShowUnverifiedModels = useModelConfigStore(
    (state) => state.setShowUnverifiedModels
  );

  const activeProfile = modelProfiles.find(
    (profile) => profile.id === activeProfileId
  );
  const activeProviderId =
    activeProfile?.providerId ?? activeModelConfig.provider;
  const enabledProviderIds = useMemo(
    () =>
      definitions
        .filter((definition) => providerConfigs[definition.id]?.enabled)
        .map((definition) => definition.id),
    [definitions, providerConfigs]
  );
  const firstEnabledProviderId = enabledProviderIds[0] ?? "openai";

  const [selectedProviderId, setSelectedProviderId] = useState(
    enabledProviderIds.includes(activeProviderId)
      ? activeProviderId
      : firstEnabledProviderId
  );
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [modelQuery, setModelQuery] = useState("");
  const [customModelDraft, setCustomModelDraft] = useState("");
  const [checkingProvider, setCheckingProvider] = useState(false);
  const [checkResult, setCheckResult] = useState<ModelCheckResponse | null>(
    null
  );
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (enabledProviderIds.length === 0) {
      setProviderEnabled("openai", true);
      setSelectedProviderId("openai");
      return;
    }
    if (!enabledProviderIds.includes(selectedProviderId)) {
      setSelectedProviderId(enabledProviderIds[0]);
    }
  }, [enabledProviderIds, selectedProviderId, setProviderEnabled]);

  const selectedDefinition =
    getModelProviderDefinition(selectedProviderId) ??
    getModelProviderDefinition("openai")!;
  const selectedConfig = providerConfigs[selectedProviderId];
  const providerModels = useMemo(
    () => getProviderModels(selectedProviderId, selectedConfig),
    [selectedConfig, selectedProviderId]
  );
  const providerProfiles = useMemo(
    () =>
      modelProfiles.filter(
        (profile) => profile.providerId === selectedProviderId
      ),
    [modelProfiles, selectedProviderId]
  );
  const activeProviderSelected = activeProviderId === selectedProviderId;
  const activeProviderModelId = activeProviderSelected
    ? activeModelConfig.model
    : "";
  const addableProviders = useMemo(
    () =>
      ADDABLE_PROVIDER_IDS.map((id) => getModelProviderDefinition(id))
        .filter((definition): definition is NonNullable<typeof definition> =>
          Boolean(definition)
        )
        .filter((definition) => !providerConfigs[definition.id]?.enabled),
    [providerConfigs]
  );

  const filteredModels = useMemo(() => {
    const needle = modelQuery.trim().toLowerCase();
    if (!needle) return providerModels;
    return providerModels.filter((model) =>
      [model.id, model.label, model.group]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [modelQuery, providerModels]);

  const rowVirtualizer = useVirtualizer({
    count: filteredModels.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 56,
    overscan: 8,
  });

  const {
    formState: { isDirty },
    getValues,
    handleSubmit,
    register,
    reset,
  } = useForm<ProviderConfigFormInput, unknown, ProviderConfigFormValues>({
    resolver: zodResolver(providerConfigSchema),
    defaultValues: selectedConfig,
  });

  useEffect(() => {
    if (selectedConfig) {
      reset(selectedConfig);
    }
  }, [reset, selectedConfig, selectedProviderId]);

  useEffect(() => {
    setCheckResult(null);
    setModelQuery("");
    setCustomModelDraft("");
    setApiKeyVisible(false);
  }, [selectedProviderId]);

  const addProvider = (providerId: string) => {
    setProviderEnabled(providerId, true);
    setSelectedProviderId(providerId);
    setAddProviderOpen(false);
  };

  const removeProvider = () => {
    const remaining = enabledProviderIds.filter(
      (id) => id !== selectedProviderId
    );
    const fallbackId = remaining[0] ?? "openai";
    setProviderEnabled(selectedProviderId, false);
    if (activeProviderId === selectedProviderId) {
      const fallbackModels = getProviderModels(
        fallbackId,
        providerConfigs[fallbackId]
      );
      if (fallbackModels[0]) {
        setProviderEnabled(fallbackId, true);
        selectModel(fallbackId, fallbackModels[0].id);
      }
    }
    setSelectedProviderId(fallbackId);
  };

  const saveProvider = (values: ProviderConfigFormValues) => {
    updateProviderConfig(selectedProviderId, {
      ...values,
      providerId: selectedProviderId,
    });
  };

  const testProvider = async () => {
    const values = providerConfigSchema.parse({
      ...selectedConfig,
      ...getValues(),
      providerId: selectedProviderId,
    });
    const modelId =
      activeProviderModelId || providerModels[0]?.id || customModelDraft.trim();

    if (!values.baseUrl.trim()) {
      setCheckResult({
        status: "error",
        message: "请先填写 Base URL。",
        provider: selectedProviderId,
        endpoint: "",
        auth_ok: false,
        models_listed: false,
      });
      return;
    }
    if (!modelId) {
      setCheckResult({
        status: "error",
        message: "请先添加或选择一个模型。",
        provider: selectedProviderId,
        endpoint: values.baseUrl,
        auth_ok: false,
        models_listed: false,
      });
      return;
    }

    updateProviderConfig(selectedProviderId, values);
    setCheckingProvider(true);
    setCheckResult(null);
    try {
      const payload = await apiCall<ModelCheckResponse>("/api/ai/model/check", {
        method: "POST",
        json: buildModelConfig(selectedProviderId, modelId, values),
      });
      setCheckResult(payload);
      markProviderChecked(selectedProviderId, payload.status !== "error");
      for (const sample of payload.sample_models ?? []) {
        addCustomModel(selectedProviderId, sample);
      }
    } catch (error) {
      setCheckResult({
        status: "error",
        message: "连接测试失败。",
        provider: selectedProviderId,
        endpoint: values.baseUrl,
        auth_ok: false,
        models_listed: false,
        error: error instanceof Error ? error.message : "Unknown error",
      });
      markProviderChecked(selectedProviderId, false);
    } finally {
      setCheckingProvider(false);
    }
  };

  const addCustomModelAndSelect = () => {
    const modelId = customModelDraft.trim();
    if (!modelId) return;
    addCustomModel(selectedProviderId, modelId);
    setProviderEnabled(selectedProviderId, true);
    selectModel(selectedProviderId, modelId);
    setCustomModelDraft("");
  };

  return (
    <div className="aicc-model-config-window flex h-[min(620px,calc(100vh-8rem))] w-full overflow-hidden rounded-xl border border-cyan-300/15 bg-[#050914]/95 shadow-[0_24px_90px_rgba(0,0,0,0.48),0_0_60px_rgba(34,211,238,0.08)] backdrop-blur-2xl">
      <aside className="flex w-[248px] shrink-0 flex-col border-r border-cyan-300/10 bg-slate-950/45">
        <div className="border-b border-cyan-300/10 px-5 py-5">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-md border border-cyan-300/20 bg-cyan-300/10 text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,0.10)]">
              <Server className="size-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-normal text-slate-50">
                AI 模型配置
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                配置多个 AI 提供商和模型
              </p>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          <div className="mb-3 px-2 text-xs font-medium text-slate-500">
            提供商
          </div>
          <div className="space-y-1">
            {definitions
              .filter((definition) => providerConfigs[definition.id]?.enabled)
              .map((definition) => {
                const config = providerConfigs[definition.id];
                const selected = selectedProviderId === definition.id;
                const verified = Boolean(
                  config?.verified || !definition.requiresApiKey
                );
                return (
                  <button
                    className={cn(
                      "flex w-full items-center gap-3 rounded-md border px-3 py-3 text-left text-sm transition-all",
                      selected
                        ? "border-cyan-300/30 bg-cyan-300/[0.10] text-cyan-50 shadow-[0_0_28px_rgba(34,211,238,0.10)]"
                        : "border-transparent text-slate-400 hover:bg-slate-900/70 hover:text-slate-100"
                    )}
                    key={definition.id}
                    onClick={() => setSelectedProviderId(definition.id)}
                    type="button"
                  >
                    <span className="grid size-8 place-items-center rounded-md border border-cyan-300/10 bg-slate-900/80 text-xs font-semibold text-cyan-100">
                      {providerGlyph(definition.id)}
                    </span>
                    <span className="min-w-0 flex-1 truncate">
                      {definition.name}
                    </span>
                    {verified && (
                      <Check className="size-4 shrink-0 text-emerald-300" />
                    )}
                    {selected && (
                      <ChevronDown className="-rotate-90 size-4 shrink-0 text-slate-500" />
                    )}
                  </button>
                );
              })}
          </div>
        </div>

        <div className="relative border-t border-cyan-300/10 p-3">
          {addProviderOpen && (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="absolute bottom-[58px] left-3 right-3 z-20 overflow-hidden rounded-lg border border-cyan-300/15 bg-[#07111f]/95 py-1 shadow-2xl shadow-black/40 backdrop-blur-xl"
              initial={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.14 }}
            >
              {addableProviders.length === 0 ? (
                <div className="px-3 py-3 text-sm text-slate-400">
                  可添加的提供商均已启用
                </div>
              ) : (
                addableProviders.map((definition) => (
                  <button
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm text-slate-300 transition-colors hover:bg-cyan-300/[0.08] hover:text-cyan-50"
                    key={definition.id}
                    onClick={() => addProvider(definition.id)}
                    type="button"
                  >
                    <span className="grid size-6 place-items-center rounded border border-cyan-300/10 bg-slate-900/80 text-[10px] font-semibold text-cyan-100">
                      {providerGlyph(definition.id)}
                    </span>
                    {definition.name}
                  </button>
                ))
              )}
            </motion.div>
          )}
          <button
            className="flex h-11 w-full items-center justify-between rounded-md border border-cyan-300/15 bg-slate-950/65 px-3 text-sm text-slate-200 shadow-[0_10px_28px_rgba(0,0,0,0.16)] transition-colors hover:border-cyan-300/30 hover:bg-slate-900/80"
            onClick={() => setAddProviderOpen((value) => !value)}
            type="button"
          >
            <span className="inline-flex items-center gap-2">
              <Plus className="size-4" />
              添加提供商
            </span>
            <ChevronDown
              className={cn(
                "size-4 text-slate-500 transition-transform",
                addProviderOpen && "rotate-180"
              )}
            />
          </button>

          <label className="mt-4 flex items-center gap-3 text-sm text-slate-400">
            <input
              checked={showUnverifiedModels}
              className="size-4 rounded border-cyan-300/20 text-cyan-300"
              onChange={(event) =>
                setShowUnverifiedModels(event.target.checked)
              }
              type="checkbox"
            />
            显示未验证的模型
          </label>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto bg-slate-950/25">
        <div className="flex min-h-full flex-col px-6 py-5">
          <div className="mb-5 flex items-start justify-between gap-6">
            <div className="flex min-w-0 items-start gap-4">
              <div className="grid size-14 shrink-0 place-items-center rounded-xl border border-cyan-300/15 bg-cyan-300/[0.08] text-lg font-semibold text-cyan-50 shadow-[0_0_30px_rgba(34,211,238,0.10)]">
                {providerGlyph(selectedProviderId)}
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-xl font-semibold tracking-normal text-slate-50">
                  {selectedDefinition.name}
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  {providerProfiles.length > 0
                    ? `已配置 ${providerProfiles.length} 个模型`
                    : "尚未配置模型"}
                </p>
              </div>
            </div>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm text-red-300 transition-colors hover:bg-red-500/10 hover:text-red-200 disabled:opacity-40"
              disabled={enabledProviderIds.length <= 1}
              onClick={removeProvider}
              type="button"
            >
              <Trash2 className="size-4" />
              删除提供商
            </button>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit(saveProvider)}>
            <section>
              <div className="mb-4 flex items-center gap-2 text-sm font-medium text-slate-300">
                <Settings2 className="size-4" />
                配置
              </div>
              <div className="rounded-lg border border-cyan-300/12 bg-slate-950/45 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.20)]">
                <div className="space-y-5">
                  <div className="space-y-2">
                    <label className={LABEL_CLASS}>
                      <Tag className="size-4 text-slate-400" />
                      显示名称
                    </label>
                    <input
                      className={INPUT_CLASS}
                      placeholder={selectedDefinition.name}
                      {...register("displayName")}
                    />
                  </div>

                  <div className="space-y-2">
                    <label className={LABEL_CLASS}>
                      <KeyRound className="size-4 text-slate-400" />
                      API 密钥
                    </label>
                    <div className="flex gap-2">
                      <div className="relative min-w-0 flex-1">
                        <input
                          className={cn(INPUT_CLASS, "pr-10")}
                          placeholder={
                            providerNeedsApiKey(selectedProviderId)
                              ? "输入您的 API 密钥"
                              : "可选"
                          }
                          type={apiKeyVisible ? "text" : "password"}
                          {...register("apiKey")}
                        />
                        <button
                          className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded text-slate-500 hover:bg-slate-800/80 hover:text-slate-100"
                          onClick={() => setApiKeyVisible((value) => !value)}
                          title={apiKeyVisible ? "隐藏密钥" : "显示密钥"}
                          type="button"
                        >
                          {apiKeyVisible ? (
                            <EyeOff className="size-4" />
                          ) : (
                            <Eye className="size-4" />
                          )}
                        </button>
                      </div>
                      <Button
                        className="h-10 min-w-20 rounded-md border border-cyan-300/20 bg-cyan-400/15 text-sm text-cyan-50 hover:border-cyan-300/40 hover:bg-cyan-400/25"
                        disabled={checkingProvider}
                        onClick={() => void testProvider()}
                        type="button"
                      >
                        {checkingProvider ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          "测试"
                        )}
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className={LABEL_CLASS}>
                      <Link2 className="size-4 text-slate-400" />
                      基础 URL
                      <span className="font-normal text-slate-500">
                        （可选，例如 https://api.openai.com/v1）
                      </span>
                    </label>
                    <input
                      className={cn(INPUT_CLASS, "font-mono")}
                      placeholder={selectedDefinition.defaultBaseUrl}
                      {...register("baseUrl")}
                    />
                  </div>
                </div>
              </div>

              {checkResult && (
                <div
                  className={cn(
                    "mt-3 rounded-md border px-4 py-3 text-sm",
                    checkTone(checkResult)
                  )}
                >
                  <div className="flex items-center gap-2 font-medium">
                    {checkIcon(checkResult)}
                    {checkTitle(checkResult)}
                  </div>
                  <div className="mt-1 truncate text-xs opacity-75">
                    {checkResult.endpoint || checkResult.message}
                  </div>
                  {checkResult.error && (
                    <div className="mt-2 rounded border border-red-400/20 bg-red-950/35 p-2 font-mono text-xs text-red-200">
                      {checkResult.error}
                    </div>
                  )}
                </div>
              )}
            </section>

            <section className="min-h-0">
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
                  <Sparkles className="size-4" />
                  模型
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative w-52">
                    <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                    <input
                      className={cn(SMALL_INPUT_CLASS, "pl-9")}
                      onChange={(event) => setModelQuery(event.target.value)}
                      placeholder="搜索模型"
                      value={modelQuery}
                    />
                  </div>
                  <input
                    className={cn(SMALL_INPUT_CLASS, "w-48")}
                    onChange={(event) =>
                      setCustomModelDraft(event.target.value)
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addCustomModelAndSelect();
                      }
                    }}
                    placeholder="自定义模型 ID..."
                    value={customModelDraft}
                  />
                  <button
                    className="grid size-9 place-items-center rounded-md border border-cyan-300/15 bg-slate-950/65 text-slate-200 shadow-[0_10px_28px_rgba(0,0,0,0.16)] transition-colors hover:border-cyan-300/30 hover:bg-slate-900/80 disabled:opacity-40"
                    disabled={!customModelDraft.trim()}
                    onClick={addCustomModelAndSelect}
                    type="button"
                  >
                    <Plus className="size-4" />
                  </button>
                  <button
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-cyan-300/15 bg-slate-950/65 px-3 text-sm text-slate-300 shadow-[0_10px_28px_rgba(0,0,0,0.16)] transition-colors hover:border-cyan-300/30 hover:bg-slate-900/80 hover:text-slate-100"
                    type="button"
                  >
                    推荐
                    <ChevronDown className="size-4 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="overflow-hidden rounded-lg border border-cyan-300/12 bg-slate-950/45 shadow-[0_18px_50px_rgba(0,0,0,0.20)]">
                <div ref={listRef} className="h-60 overflow-y-auto">
                  {filteredModels.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-500">
                      <Sparkles className="size-7" />
                      尚未配置模型
                    </div>
                  ) : (
                    <div
                      className="relative"
                      style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                    >
                      {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                        const model = filteredModels[virtualItem.index];
                        if (!model) return null;
                        const selected = activeProviderModelId === model.id;
                        const isCustom = selectedConfig?.customModels.some(
                          (item) => item.id === model.id
                        );
                        return (
                          <div
                            className="absolute left-0 top-0 flex w-full items-center gap-2 px-3 py-2"
                            key={`${selectedProviderId}:${model.id}`}
                            style={{
                              height: `${virtualItem.size}px`,
                              transform: `translateY(${virtualItem.start}px)`,
                            }}
                          >
                            <button
                              className={cn(
                                "flex min-w-0 flex-1 items-center gap-3 rounded-md px-3 py-2 text-left transition-colors",
                                selected
                                  ? "bg-cyan-300/[0.10] text-cyan-50"
                                  : "text-slate-300 hover:bg-slate-900/70 hover:text-slate-50"
                              )}
                              onClick={() =>
                                selectModel(selectedProviderId, model.id)
                              }
                              type="button"
                            >
                              <span className="grid size-7 shrink-0 place-items-center rounded border border-cyan-300/10 bg-slate-900/80 text-xs font-semibold text-cyan-100">
                                {providerGlyph(selectedProviderId)}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">
                                  {model.label ?? model.id}
                                </span>
                                <span className="mt-0.5 block truncate text-xs text-slate-500">
                                  {model.group ?? "Model"}
                                </span>
                              </span>
                              {model.recommended && (
                                <Star className="size-4 shrink-0 fill-amber-300 text-amber-400" />
                              )}
                              {selected && (
                                <Check className="size-4 shrink-0 text-cyan-100" />
                              )}
                            </button>
                            {isCustom && (
                              <button
                                className="grid size-8 shrink-0 place-items-center rounded-md text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-300"
                                onClick={() =>
                                  removeCustomModel(
                                    selectedProviderId,
                                    model.id
                                  )
                                }
                                title="删除自定义模型"
                                type="button"
                              >
                                <X className="size-4" />
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section>
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-medium text-slate-300">
                  已保存模型
                </div>
                <div className="text-xs text-slate-500">
                  {modelProfiles.length} 个本地配置
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {modelProfiles.map((profile) => {
                  const definition = getModelProviderDefinition(
                    profile.providerId
                  );
                  const active = profile.id === activeProfileId;
                  const isDefault = profile.id === defaultProfileId;
                  return (
                    <div
                      className={cn(
                        "flex items-center gap-2 rounded-md border px-3 py-2",
                        active
                          ? "border-cyan-300/25 bg-cyan-300/[0.08]"
                          : "border-cyan-300/10 bg-slate-950/45"
                      )}
                      key={profile.id}
                    >
                      <button
                        className="min-w-0 flex-1 text-left"
                        onClick={() => selectModelProfile(profile.id)}
                        type="button"
                      >
                        <div className="truncate text-sm font-medium text-slate-100">
                          {profile.name}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-slate-500">
                          {definition?.shortName ?? profile.provider} /{" "}
                          {profile.model} /{" "}
                          {modelProfileEndpointLabel(profile.baseUrl)}
                        </div>
                      </button>
                      <button
                        className={cn(
                          "grid size-8 place-items-center rounded-md transition-colors",
                          isDefault
                            ? "text-amber-500"
                            : "text-slate-500 hover:bg-amber-500/10 hover:text-amber-400"
                        )}
                        onClick={() => setDefaultModelProfile(profile.id)}
                        title="设为默认"
                        type="button"
                      >
                        <Star
                          className={cn(
                            "size-4",
                            isDefault && "fill-amber-300"
                          )}
                        />
                      </button>
                      <button
                        className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-300"
                        disabled={modelProfiles.length <= 1}
                        onClick={() => deleteModelProfile(profile.id)}
                        title="删除模型配置"
                        type="button"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>

            <div className="mt-auto flex items-center justify-between border-t border-cyan-300/10 pt-5">
              <div className="inline-flex items-center gap-2 text-xs text-slate-500">
                <KeyRound className="size-4" />
                API 密钥存储在您的浏览器本地
              </div>
              <Button
                className="h-10 rounded-md border border-cyan-300/20 bg-gradient-to-r from-cyan-500 to-blue-500 px-5 text-white shadow-[0_0_28px_rgba(34,211,238,0.18)] hover:from-cyan-400 hover:to-blue-400"
                type="submit"
              >
                {isDirty ? "保存更改" : "保存配置"}
              </Button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
