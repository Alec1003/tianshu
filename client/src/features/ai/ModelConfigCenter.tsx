import { useEffect, useMemo, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { useForm } from "react-hook-form";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Link2,
  Loader2,
  Plus,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
  XCircle,
  Zap,
} from "lucide-react";

import { apiCall } from "@/api/client";
import {
  listServerModelProviders,
  saveServerModelProvider,
} from "@/api/modelConfig";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  buildModelConfig,
  getModelProviderDefinition,
  listModelProviderDefinitions,
  providerConfigSchema,
  providerNeedsApiKey,
  type ProviderConfigFormInput,
  type ProviderConfigFormValues,
  type ProviderModel,
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

function formatCheckedAt(value: string | null | undefined): string {
  if (!value) return "未测试";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未测试";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function normalizeModelCheckStatus(
  status: ProviderModel["checkStatus"] | undefined
): NonNullable<ProviderModel["checkStatus"]> {
  return status ?? "untested";
}

function modelStatusIcon(status: ProviderModel["checkStatus"]) {
  const normalized = normalizeModelCheckStatus(status);
  if (normalized === "ok") return <Check className="size-4" />;
  if (normalized === "partial" || normalized === "error") {
    return <AlertCircle className="size-4" />;
  }
  if (normalized === "checking")
    return <Loader2 className="size-4 animate-spin" />;
  return <Zap className="size-4" />;
}

function modelStatusTone(status: ProviderModel["checkStatus"]): string {
  const normalized = normalizeModelCheckStatus(status);
  if (normalized === "ok") {
    return "bg-emerald-400/15 text-emerald-200";
  }
  if (normalized === "partial") {
    return "bg-amber-400/15 text-amber-200";
  }
  if (normalized === "error") {
    return "bg-rose-400/15 text-rose-200";
  }
  if (normalized === "checking") {
    return "bg-cyan-400/15 text-cyan-200";
  }
  return "bg-slate-800/80 text-slate-400";
}

function modelCheckMessage(
  result: ModelCheckResponse,
  modelId: string
): string {
  if (result.status === "ok") return "";
  return (
    result.error ||
    result.message ||
    `模型 ${modelId} 测试未通过，请检查模型名称或 Provider 配置。`
  );
}

interface ModelConfigCenterProps {
  onSaved?: () => void;
}

export default function ModelConfigCenter({ onSaved }: ModelConfigCenterProps) {
  const definitions = useMemo(listModelProviderDefinitions, []);
  const providerConfigs = useModelConfigStore((state) => state.providerConfigs);
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
  const hydrateProviderConfigs = useModelConfigStore(
    (state) => state.hydrateProviderConfigs
  );
  const addCustomModel = useModelConfigStore((state) => state.addCustomModel);
  const removeCustomModel = useModelConfigStore(
    (state) => state.removeCustomModel
  );
  const setShowUnverifiedModels = useModelConfigStore(
    (state) => state.setShowUnverifiedModels
  );

  const enabledProviderIds = useMemo(
    () =>
      definitions
        .filter((definition) => providerConfigs[definition.id]?.enabled)
        .map((definition) => definition.id),
    [definitions, providerConfigs]
  );
  const firstEnabledProviderId = enabledProviderIds[0] ?? "openai";

  const [selectedProviderId, setSelectedProviderId] = useState(
    firstEnabledProviderId
  );
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [modelQuery, setModelQuery] = useState("");
  const [customModelDraft, setCustomModelDraft] = useState("");
  const [checkingProvider, setCheckingProvider] = useState(false);
  const [savingProvider, setSavingProvider] = useState(false);
  const [loadingSavedConfigs, setLoadingSavedConfigs] = useState(false);
  const [checkResult, setCheckResult] = useState<ModelCheckResponse | null>(
    null
  );
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingSavedConfigs(true);
    listServerModelProviders()
      .then((providers) => {
        if (cancelled) return;
        hydrateProviderConfigs(
          providers.map((provider) => ({
            providerId: provider.providerId,
            displayName: provider.displayName,
            baseUrl: provider.baseUrl,
            enabled: provider.enabled,
            verified: provider.verified,
            lastCheckedAt: provider.lastCheckedAt,
            customModels: provider.customModels as unknown as ProviderModel[],
            apiKey: "",
            apiKeySet: provider.apiKeySet,
          }))
        );
      })
      .catch((error) => {
        if (cancelled) return;
        setCheckResult({
          status: "error",
          message:
            error instanceof Error ? error.message : "模型配置加载失败。",
          provider: "",
          endpoint: "",
          auth_ok: false,
          models_listed: false,
        });
      })
      .finally(() => {
        if (!cancelled) setLoadingSavedConfigs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hydrateProviderConfigs]);

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
    () =>
      (selectedConfig?.customModels ?? []).map((model) => ({
        ...model,
        checkStatus: normalizeModelCheckStatus(model.checkStatus),
      })),
    [selectedConfig]
  );
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
    estimateSize: (index) =>
      normalizeModelCheckStatus(filteredModels[index]?.checkStatus) === "error"
        ? 74
        : 56,
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
    setProviderEnabled(fallbackId, true);
    setSelectedProviderId(fallbackId);
  };

  const saveProvider = async (values: ProviderConfigFormValues) => {
    setSavingProvider(true);
    let closeAfterSave = false;
    try {
      const saved = await saveServerModelProvider(selectedProviderId, {
        displayName: values.displayName,
        baseUrl: values.baseUrl,
        apiKey: values.apiKey.trim() ? values.apiKey : undefined,
        enabled: values.enabled,
        verified: values.verified,
        lastCheckedAt: values.lastCheckedAt,
        customModels: values.customModels.map((model) => ({ ...model })),
      });
      const localValues = {
        ...values,
        apiKey: "",
        apiKeySet: saved.apiKeySet,
        verified: saved.verified,
        lastCheckedAt: saved.lastCheckedAt,
      };
      updateProviderConfig(selectedProviderId, {
        ...localValues,
        providerId: selectedProviderId,
      });
      reset(localValues);
      closeAfterSave = true;
    } finally {
      setSavingProvider(false);
    }
    if (closeAfterSave) onSaved?.();
  };

  const testProvider = async () => {
    const values = providerConfigSchema.parse({
      ...selectedConfig,
      ...getValues(),
      customModels: providerModels,
      providerId: selectedProviderId,
    });
    const modelsToCheck = providerModels;

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
    if (modelsToCheck.length === 0) {
      setCheckResult({
        status: "error",
        message: "请先添加模型。",
        provider: selectedProviderId,
        endpoint: values.baseUrl,
        auth_ok: false,
        models_listed: false,
      });
      return;
    }

    updateProviderConfig(selectedProviderId, {
      ...values,
      customModels: modelsToCheck.map((model) => ({
        ...model,
        checkStatus: "checking",
        checkMessage: "",
      })),
    });
    setCheckingProvider(true);
    setCheckResult(null);
    try {
      const checkedAt = new Date().toISOString();
      const testedModels = await Promise.all(
        modelsToCheck.map(async (model) => {
          try {
            const payload = await apiCall<ModelCheckResponse>(
              "/api/ai/model/check",
              {
                method: "POST",
                json: {
                  ...buildModelConfig(selectedProviderId, model.id, values),
                  providerId: selectedProviderId,
                },
              }
            );
            return {
              ...model,
              checkStatus: payload.status,
              checkMessage: modelCheckMessage(payload, model.id),
              checkedAt,
            } satisfies ProviderModel;
          } catch (error) {
            return {
              ...model,
              checkStatus: "error",
              checkMessage:
                error instanceof Error ? error.message : "连接测试失败。",
              checkedAt,
            } satisfies ProviderModel;
          }
        })
      );
      const okCount = testedModels.filter(
        (model) => model.checkStatus === "ok" || model.checkStatus === "partial"
      ).length;
      const errorCount = testedModels.length - okCount;
      const overallStatus =
        errorCount === 0 ? "ok" : okCount > 0 ? "partial" : "error";
      updateProviderConfig(selectedProviderId, {
        ...values,
        verified: okCount > 0,
        lastCheckedAt: checkedAt,
        customModels: testedModels,
      });
      setCheckResult({
        status: overallStatus,
        message:
          errorCount === 0
            ? `已测试 ${testedModels.length} 个模型，全部可用。`
            : `已测试 ${testedModels.length} 个模型，${okCount} 个可用，${errorCount} 个异常。`,
        provider: selectedProviderId,
        endpoint: values.baseUrl,
        auth_ok: okCount > 0,
        models_listed: okCount > 0,
      });
      markProviderChecked(selectedProviderId, okCount > 0);
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
    setCustomModelDraft("");
  };

  const selectedProviderVerified = Boolean(
    selectedConfig?.verified || !selectedDefinition.requiresApiKey
  );
  const providerStatusLabel = selectedProviderVerified ? "已验证" : "未验证";

  return (
    <div className="tianshu-model-config-window flex h-[min(670px,calc(100vh-7rem))] w-full flex-col overflow-hidden rounded-xl border border-cyan-300/15 bg-[#050914]/95 shadow-[0_24px_90px_rgba(0,0,0,0.48),0_0_60px_rgba(34,211,238,0.08)] backdrop-blur-2xl md:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-cyan-300/10 bg-slate-950/45 md:w-[224px] md:border-b-0 md:border-r">
        <div className="relative border-b border-cyan-300/10 p-4">
          <div className="flex items-center gap-3">
            <div className="grid size-8 place-items-center rounded-md border border-cyan-300/20 bg-cyan-300/10 text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,0.10)]">
              <Server className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-base font-semibold tracking-normal text-slate-50">
                AI 模型
              </h1>
              <p className="mt-0.5 truncate text-xs text-slate-500">
                {enabledProviderIds.length} 个 Provider
              </p>
            </div>
            <button
              aria-expanded={addProviderOpen}
              className="grid size-8 place-items-center rounded-md border border-cyan-300/15 bg-slate-950/65 text-slate-300 transition-colors hover:border-cyan-300/30 hover:bg-slate-900/80 hover:text-cyan-50"
              onClick={() => setAddProviderOpen((value) => !value)}
              title="添加提供商"
              type="button"
            >
              <Plus className="size-4" />
            </button>
          </div>

          {addProviderOpen && (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="absolute left-3 right-3 top-[62px] z-20 overflow-hidden rounded-lg border border-cyan-300/15 bg-[#07111f]/95 py-1 shadow-2xl shadow-black/40 backdrop-blur-xl"
              initial={{ opacity: 0, y: -6 }}
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
                    <span className="min-w-0 flex-1 truncate">
                      {definition.name}
                    </span>
                  </button>
                ))
              )}
            </motion.div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-2.5 py-3">
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
                      "flex w-full items-center gap-2.5 rounded-md border px-2.5 py-2.5 text-left transition-all",
                      selected
                        ? "border-cyan-300/30 bg-cyan-300/[0.10] text-cyan-50 shadow-[0_0_28px_rgba(34,211,238,0.10)]"
                        : "border-transparent text-slate-400 hover:bg-slate-900/70 hover:text-slate-100"
                    )}
                    key={definition.id}
                    onClick={() => setSelectedProviderId(definition.id)}
                    type="button"
                  >
                    <span className="grid size-7 shrink-0 place-items-center rounded-md border border-cyan-300/10 bg-slate-900/80 text-[11px] font-semibold text-cyan-100">
                      {providerGlyph(definition.id)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {definition.shortName}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-slate-600">
                        {verified ? "ready" : "setup"}
                      </span>
                    </span>
                    {verified ? (
                      <Check className="size-4 shrink-0 text-emerald-300" />
                    ) : (
                      <span className="size-2 rounded-full bg-slate-700" />
                    )}
                  </button>
                );
              })}
          </div>
        </div>

        <div className="border-t border-cyan-300/10 p-3">
          <div className="rounded-md border border-cyan-300/10 bg-slate-950/55 p-3">
            <div className="text-xs text-slate-500">模型清单</div>
            <div className="mt-1 truncate text-sm font-medium text-slate-100">
              {providerModels.length > 0
                ? `${providerModels.length} 个待维护模型`
                : "空白"}
            </div>
          </div>
          <label className="mt-3 flex items-center gap-2 text-xs text-slate-400">
            <input
              checked={showUnverifiedModels}
              className="size-4 rounded border-cyan-300/20 bg-slate-950 accent-cyan-300"
              onChange={(event) =>
                setShowUnverifiedModels(event.target.checked)
              }
              type="checkbox"
            />
            显示未验证模型
          </label>
        </div>
      </aside>

      <form
        className="min-w-0 flex-1 overflow-hidden bg-slate-950/20"
        onSubmit={handleSubmit(saveProvider)}
      >
        <div className="flex h-full min-h-0 flex-col">
          <header className="flex flex-col gap-4 border-b border-cyan-300/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-cyan-300/15 bg-cyan-300/[0.08] text-sm font-semibold text-cyan-50 shadow-[0_0_30px_rgba(34,211,238,0.10)]">
                {providerGlyph(selectedProviderId)}
              </div>
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <h2 className="truncate text-lg font-semibold tracking-normal text-slate-50">
                    {selectedDefinition.name}
                  </h2>
                  <span
                    className={cn(
                      "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
                      selectedProviderVerified
                        ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200"
                        : "border-amber-400/20 bg-amber-500/10 text-amber-200"
                    )}
                  >
                    <ShieldCheck className="size-3" />
                    {providerStatusLabel}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm text-slate-500">
                  {loadingSavedConfigs
                    ? "正在加载模型配置..."
                    : selectedDefinition.description}
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <button
                className="grid size-9 place-items-center rounded-md text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-35"
                disabled={enabledProviderIds.length <= 1}
                onClick={removeProvider}
                title="停用提供商"
                type="button"
              >
                <Trash2 className="size-4" />
              </button>
              <Button
                className="h-9 rounded-md border border-cyan-300/20 bg-cyan-400/12 px-3 text-sm text-cyan-50 hover:border-cyan-300/40 hover:bg-cyan-400/22"
                disabled={checkingProvider || providerModels.length === 0}
                onClick={() => void testProvider()}
                type="button"
              >
                {checkingProvider ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  "测试模型"
                )}
              </Button>
              <Button
                className="h-9 rounded-md border border-cyan-300/20 bg-gradient-to-r from-cyan-500 to-blue-500 px-4 text-white shadow-[0_0_28px_rgba(34,211,238,0.18)] hover:from-cyan-400 hover:to-blue-400"
                disabled={savingProvider}
                type="submit"
              >
                {savingProvider ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : isDirty ? (
                  "保存更改"
                ) : (
                  "保存"
                )}
              </Button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            {checkResult && (
              <div
                className={cn(
                  "mb-5 rounded-md border px-4 py-3 text-sm",
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

            <section className="border-b border-cyan-300/10 pb-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-medium text-slate-200">
                    连接参数
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    上次测试：{formatCheckedAt(selectedConfig?.lastCheckedAt)}
                  </p>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <label className="space-y-2">
                  <span className={LABEL_CLASS}>
                    <Server className="size-4 text-slate-400" />
                    显示名称
                  </span>
                  <input
                    className={INPUT_CLASS}
                    placeholder={selectedDefinition.name}
                    {...register("displayName")}
                  />
                </label>

                <label className="space-y-2">
                  <span className={LABEL_CLASS}>
                    <Link2 className="size-4 text-slate-400" />
                    Base URL
                  </span>
                  <input
                    className={cn(INPUT_CLASS, "font-mono")}
                    placeholder={selectedDefinition.defaultBaseUrl}
                    {...register("baseUrl")}
                  />
                </label>

                <label className="space-y-2 lg:col-span-2">
                  <span className={LABEL_CLASS}>
                    <KeyRound className="size-4 text-slate-400" />
                    API Key
                  </span>
                  <div className="relative">
                    <input
                      className={cn(INPUT_CLASS, "pr-10 font-mono")}
                      placeholder={
                        providerNeedsApiKey(selectedProviderId)
                          ? selectedConfig?.apiKeySet
                            ? "输入新的 API Key（留空保持原配置）"
                            : "输入 API Key"
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
                </label>
              </div>
            </section>

            <section className="pt-5">
              <div className="mb-3 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-medium text-slate-200">
                    <Sparkles className="size-4 text-cyan-200/80" />
                    模型
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {providerModels.length} 个模型 · {filteredModels.length}{" "}
                    个可见
                  </p>
                </div>

                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="relative sm:w-56">
                    <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                    <input
                      className={cn(SMALL_INPUT_CLASS, "pl-9")}
                      onChange={(event) => setModelQuery(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                        }
                      }}
                      placeholder="搜索模型"
                      value={modelQuery}
                    />
                  </div>
                  <div className="flex min-w-0 gap-2">
                    <input
                      className={cn(SMALL_INPUT_CLASS, "min-w-0 sm:w-56")}
                      onChange={(event) =>
                        setCustomModelDraft(event.target.value)
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          addCustomModelAndSelect();
                        }
                      }}
                      placeholder="自定义模型 ID"
                      value={customModelDraft}
                    />
                    <button
                      aria-label="添加自定义模型"
                      className="grid size-9 shrink-0 place-items-center rounded-md border border-cyan-300/15 bg-slate-950/65 text-slate-200 shadow-[0_10px_28px_rgba(0,0,0,0.16)] transition-colors hover:border-cyan-300/30 hover:bg-slate-900/80 disabled:opacity-40"
                      disabled={!customModelDraft.trim()}
                      onClick={addCustomModelAndSelect}
                      title="添加自定义模型"
                      type="button"
                    >
                      <Plus className="size-4" />
                    </button>
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-lg border border-cyan-300/12 bg-slate-950/45 shadow-[0_18px_50px_rgba(0,0,0,0.20)]">
                <div className="flex items-center justify-between border-b border-cyan-300/10 px-3 py-2 text-xs text-slate-500">
                  <span>{selectedDefinition.shortName}</span>
                  <span>{providerModels.length} 个模型</span>
                </div>
                <div ref={listRef} className="h-[318px] overflow-y-auto">
                  {providerModels.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-500">
                      <Sparkles className="size-7" />
                      暂无模型，输入模型 ID 后添加
                    </div>
                  ) : filteredModels.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-500">
                      <Search className="size-7" />
                      未找到匹配模型
                    </div>
                  ) : (
                    <div
                      className="relative"
                      style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                    >
                      {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                        const model = filteredModels[virtualItem.index];
                        if (!model) return null;
                        const status = normalizeModelCheckStatus(
                          model.checkStatus
                        );
                        return (
                          <div
                            className="absolute left-0 top-0 flex w-full items-center gap-2 px-3 py-1.5"
                            key={`${selectedProviderId}:${model.id}`}
                            style={{
                              height: `${virtualItem.size}px`,
                              transform: `translateY(${virtualItem.start}px)`,
                            }}
                          >
                            <div
                              className={cn(
                                "flex min-h-full min-w-0 flex-1 items-center gap-3 rounded-md border px-3 text-left transition-colors",
                                status === "error"
                                  ? "border-rose-400/20 bg-rose-500/[0.05]"
                                  : "border-transparent bg-slate-950/30 hover:border-cyan-300/10 hover:bg-slate-900/70"
                              )}
                            >
                              <span
                                className={cn(
                                  "grid size-8 shrink-0 place-items-center rounded-full",
                                  modelStatusTone(status)
                                )}
                              >
                                {modelStatusIcon(status)}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate font-mono text-sm font-medium text-slate-100">
                                  {model.label ?? model.id}
                                </span>
                                {model.checkMessage && status !== "ok" && (
                                  <span
                                    className={cn(
                                      "mt-1 block truncate text-xs",
                                      status === "error"
                                        ? "text-rose-300"
                                        : "text-amber-300"
                                    )}
                                  >
                                    {model.checkMessage}
                                  </span>
                                )}
                              </span>
                              <button
                                className="grid size-8 shrink-0 place-items-center rounded-md text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-300"
                                onClick={() =>
                                  removeCustomModel(
                                    selectedProviderId,
                                    model.id
                                  )
                                }
                                title="移除模型"
                                type="button"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </section>
          </div>
        </div>
      </form>
    </div>
  );
}
