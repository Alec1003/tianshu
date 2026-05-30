import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Bot,
  Check,
  ChevronDown,
  Cpu,
  Monitor,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  getModelProviderDefinition,
  listModelProviderDefinitions,
  providerRuntimeId,
  type ProviderModel,
} from "./modelProfiles";
import { listServerModelProviders } from "@/api/modelConfig";
import { useModelConfigStore, type ModelOption } from "./modelStore";

interface ModelSwitcherProps {
  className?: string;
  disabled?: boolean;
  onOpenSettings?: () => void;
}

type SwitcherRow =
  | {
      type: "provider";
      id: string;
      name: string;
      count: number;
    }
  | {
      type: "model";
      option: ModelOption;
    };

function optionSearchText(option: ModelOption): string {
  return [
    option.id,
    option.label,
    option.group,
    option.providerName,
    option.providerShortName,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

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

function buildRows(options: ModelOption[], query: string): SwitcherRow[] {
  const needle = query.trim().toLowerCase();
  const groups = new Map<string, ModelOption[]>();

  for (const option of options) {
    if (needle && !optionSearchText(option).includes(needle)) continue;
    const current = groups.get(option.providerId) ?? [];
    current.push(option);
    groups.set(option.providerId, current);
  }

  return [...groups.entries()].flatMap(([providerId, providerOptions]) => [
    {
      type: "provider" as const,
      id: providerId,
      name: providerOptions[0]?.providerName ?? providerId,
      count: providerOptions.length,
    },
    ...providerOptions.map((option) => ({
      type: "model" as const,
      option,
    })),
  ]);
}

function preferredModelRowIndex(rows: SwitcherRow[]): number {
  const activeIndex = rows.findIndex(
    (row) => row.type === "model" && row.option.isActive
  );
  if (activeIndex >= 0) return activeIndex;
  return Math.max(
    0,
    rows.findIndex((row) => row.type === "model")
  );
}

export default function ModelSwitcher({
  className,
  disabled,
  onOpenSettings,
}: ModelSwitcherProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedRowIndex, setHighlightedRowIndex] = useState(0);

  const activeModelConfig = useModelConfigStore(
    (state) => state.activeModelConfig
  );
  const activeProfileId = useModelConfigStore(
    (state) => state.activeModelProfileId
  );
  const defaultProfileId = useModelConfigStore(
    (state) => state.defaultModelProfileId
  );
  const providerConfigs = useModelConfigStore((state) => state.providerConfigs);
  const hydrateProviderConfigs = useModelConfigStore(
    (state) => state.hydrateProviderConfigs
  );
  const showUnverifiedModels = useModelConfigStore(
    (state) => state.showUnverifiedModels
  );
  const modelProfiles = useModelConfigStore((state) => state.modelProfiles);
  const selectModel = useModelConfigStore((state) => state.selectModel);

  const activeProfile = modelProfiles.find(
    (profile) => profile.id === activeProfileId
  );

  useEffect(() => {
    let cancelled = false;
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
      .catch(() => {
        // The switcher can still use the local persisted snapshot if the
        // backend is temporarily unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, [hydrateProviderConfigs]);

  const modelOptions = useMemo<ModelOption[]>(() => {
    return listModelProviderDefinitions().flatMap((definition) => {
      const config = providerConfigs[definition.id];
      const enabled = Boolean(config?.enabled);
      const verified = Boolean(config?.verified || !definition.requiresApiKey);
      if (!enabled) return [];
      if (!showUnverifiedModels && !verified) return [];

      return (config?.customModels ?? []).map((model) => {
        const profile = modelProfiles.find(
          (item) => item.providerId === definition.id && item.model === model.id
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
            activeModelConfig.provider === providerRuntimeId(definition.id) &&
            activeModelConfig.model === model.id,
          isDefault: profile?.id === defaultProfileId,
        };
      });
    });
  }, [
    activeModelConfig.model,
    activeModelConfig.provider,
    activeProfile?.providerId,
    defaultProfileId,
    modelProfiles,
    providerConfigs,
    showUnverifiedModels,
  ]);

  useEffect(() => {
    if (modelOptions.length === 0) return;
    if (modelOptions.some((option) => option.isActive)) return;
    const next = modelOptions[0];
    if (next) selectModel(next.providerId, next.id);
  }, [modelOptions, selectModel]);
  const activeDefinition = getModelProviderDefinition(
    activeProfile?.providerId ?? activeModelConfig.provider
  );
  const activeProviderLabel =
    activeDefinition?.shortName ??
    activeDefinition?.name ??
    activeModelConfig.provider;
  const activeLabel = `${activeProviderLabel}/${activeModelConfig.model}`;

  const rows = useMemo(
    () => buildRows(modelOptions, query),
    [modelOptions, query]
  );
  const selectableRowIndexes = useMemo(
    () =>
      rows
        .map((row, index) => (row.type === "model" ? index : -1))
        .filter((index) => index >= 0),
    [rows]
  );

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => listRef.current,
    estimateSize: (index) => (rows[index]?.type === "provider" ? 38 : 58),
    overscan: 8,
  });

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    const index = preferredModelRowIndex(rows);
    setHighlightedRowIndex(index);
    listRef.current?.scrollTo({ top: 0 });
  }, [query, open, rows]);

  useEffect(() => {
    if (!open || rows.length === 0) return;
    rowVirtualizer.scrollToIndex(highlightedRowIndex, { align: "auto" });
  }, [highlightedRowIndex, open, rowVirtualizer, rows.length]);

  const selectOption = (option: ModelOption | undefined) => {
    if (!option) return;
    selectModel(option.providerId, option.id);
    setOpen(false);
    setQuery("");
  };

  const moveHighlight = (direction: 1 | -1) => {
    if (selectableRowIndexes.length === 0) return;
    setHighlightedRowIndex((index) => {
      const currentPosition = selectableRowIndexes.indexOf(index);
      const fallbackPosition = direction > 0 ? -1 : selectableRowIndexes.length;
      const nextPosition = Math.min(
        Math.max(
          (currentPosition >= 0 ? currentPosition : fallbackPosition) +
            direction,
          0
        ),
        selectableRowIndexes.length - 1
      );
      return selectableRowIndexes[nextPosition] ?? index;
    });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveHighlight(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveHighlight(-1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const row = rows[highlightedRowIndex];
      selectOption(row?.type === "model" ? row.option : undefined);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cn(
          "flex h-8 max-w-full items-center gap-2 rounded-md border border-cyan-300/15 bg-slate-950/55 px-2.5 text-left text-xs text-slate-200 shadow-sm shadow-black/20 transition-all",
          "hover:border-cyan-300/35 hover:bg-slate-900/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40",
          disabled && "cursor-not-allowed opacity-50"
        )}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        title={`${activeLabel} (点击更改)`}
        type="button"
      >
        <Bot className="size-3.5 shrink-0 text-cyan-200/80" />
        <span className="min-w-0 truncate font-medium">{activeLabel}</span>
        <ChevronDown className="size-3.5 shrink-0 text-slate-500" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className="absolute bottom-10 left-0 z-50 w-[min(340px,calc(100vw-2rem))] overflow-hidden rounded-xl border border-cyan-300/15 bg-slate-950/95 text-slate-100 shadow-[0_24px_70px_rgba(0,0,0,0.45),0_0_36px_rgba(34,211,238,0.08)] backdrop-blur-2xl"
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.16 }}
          >
            <div className="flex h-12 items-center gap-3 border-b border-cyan-300/10 px-3">
              <Search className="size-4 shrink-0 text-cyan-200/70" />
              <input
                autoFocus
                className="h-full min-w-0 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="搜索模型..."
                value={query}
              />
              <button
                aria-label="关闭模型选择"
                className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200"
                onClick={() => setOpen(false)}
                type="button"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-slate-300">
              <Monitor className="size-4 text-cyan-200/70" />
              已配置模型
            </div>

            <div
              ref={listRef}
              className="max-h-72 overflow-y-auto border-t border-cyan-300/10"
              role="listbox"
            >
              {rows.length === 0 ? (
                <div className="flex h-32 flex-col items-center justify-center gap-2 px-4 text-center text-sm text-slate-500">
                  <Cpu className="size-5 text-slate-600" />
                  未找到已配置模型
                </div>
              ) : (
                <div
                  className="relative"
                  style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                >
                  {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                    const row = rows[virtualItem.index];
                    if (!row) return null;

                    if (row.type === "provider") {
                      return (
                        <div
                          className="absolute left-0 top-0 flex w-full items-center justify-between px-5 text-xs font-medium uppercase tracking-[0.18em] text-slate-500"
                          key={`provider:${row.id}`}
                          style={{
                            height: `${virtualItem.size}px`,
                            transform: `translateY(${virtualItem.start}px)`,
                          }}
                        >
                          <span>{row.name}</span>
                          <span className="text-xs text-slate-600">
                            {row.count}
                          </span>
                        </div>
                      );
                    }

                    const option = row.option;
                    const highlighted =
                      virtualItem.index === highlightedRowIndex;
                    const isDefault = option.profileId === defaultProfileId;

                    return (
                      <button
                        aria-selected={option.isActive}
                        className={cn(
                          "absolute left-0 top-0 flex w-full items-center gap-3 px-4 text-left transition-colors",
                          option.isActive && "bg-cyan-300/10",
                          highlighted && !option.isActive && "bg-slate-900/75",
                          !highlighted &&
                            !option.isActive &&
                            "hover:bg-slate-900/75"
                        )}
                        key={`${option.providerId}:${option.id}`}
                        onClick={() => selectOption(option)}
                        onMouseEnter={() =>
                          setHighlightedRowIndex(virtualItem.index)
                        }
                        role="option"
                        style={{
                          height: `${virtualItem.size}px`,
                          transform: `translateY(${virtualItem.start}px)`,
                        }}
                        type="button"
                      >
                        <div className="grid size-7 shrink-0 place-items-center text-slate-500">
                          {option.isActive ? (
                            <Check className="size-5 text-cyan-200" />
                          ) : (
                            <span />
                          )}
                        </div>
                        <div className="grid size-8 shrink-0 place-items-center rounded-md border border-cyan-300/10 bg-cyan-300/[0.06] text-[11px] font-semibold text-cyan-100">
                          {providerGlyph(option.providerId)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="truncate text-sm font-medium text-slate-100">
                              {option.label ?? option.id}
                            </span>
                            {option.recommended && (
                              <Star className="size-3.5 shrink-0 fill-amber-300 text-amber-400" />
                            )}
                          </div>
                          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-slate-500">
                            <span className="truncate">
                              {option.providerShortName}
                            </span>
                            {option.group && (
                              <>
                                <span>/</span>
                                <span className="truncate">{option.group}</span>
                              </>
                            )}
                            {option.verified && (
                              <>
                                <span>/</span>
                                <ShieldCheck className="size-3" />
                              </>
                            )}
                          </div>
                        </div>
                        {isDefault && (
                          <span className="shrink-0 text-xs text-slate-500">
                            默认
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="border-t border-cyan-300/10 px-3 py-3">
              <button
                className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm text-slate-300 transition-colors hover:bg-slate-900 hover:text-slate-100"
                onClick={() => {
                  setOpen(false);
                  onOpenSettings?.();
                }}
                type="button"
              >
                <SlidersHorizontal className="size-4 text-cyan-200/70" />
                配置模型...
                <Settings2 className="ml-auto size-4 text-slate-500" />
              </button>
              <div className="mt-2 flex items-center gap-2 px-2 text-xs text-slate-500">
                <Sparkles className="size-3.5" />
                仅显示配置中心添加的模型
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
