import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Globe,
  Plug,
  RefreshCw,
  Settings,
  Shield,
  Trash2,
  Wrench,
  X,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Activity,
  CalendarClock,
  Clock,
  Code2,
  Database,
  FileText,
  History,
  Lock,
  MoreHorizontal,
  Pencil,
  PlayCircle,
  Plus,
  Power,
  ScrollText,
  Search,
  SlidersHorizontal,
  Terminal,
  User,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { CesiumBaseLayerKey } from "@/gui/map/CesiumMapTypes";
import type {
  MCPServerImportPayload,
  TacticalSettingsProps,
} from "./AISidebar";

const SETTINGS_TABS = [
  {
    id: "mcp",
    label: "MCP 管理",
    icon: Plug,
    desc: "接入工具服务器与工作区能力",
  },
  {
    id: "skills",
    label: "AI 工具",
    icon: Wrench,
    desc: "查看后端工具与自定义提示词",
  },
  {
    id: "system",
    label: "系统操作",
    icon: Settings,
    desc: "会话、危险操作与运行偏好",
  },
] as const;

type SettingsTabId = (typeof SETTINGS_TABS)[number]["id"];

export interface TacticalSettingsModalProps extends TacticalSettingsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const INPUT_CLASS =
  "w-full rounded-md border border-cyan-400/20 bg-cyan-950/20 px-3 py-1.5 font-mono text-[11px] text-cyan-50 placeholder:text-cyan-600/30 focus:border-cyan-400/50 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all";

const BASE_LAYER_OPTIONS: Array<{
  id: CesiumBaseLayerKey;
  label: string;
  desc: string;
}> = [
  { id: "darkMatter", label: "战术暗色", desc: "夜间态势与高对比目标显示" },
  { id: "lightVector", label: "标准矢量", desc: "中文道路、地名与行政标注" },
  { id: "satellite", label: "卫星影像", desc: "高德卫星遥感底图（z16）" },
  { id: "sentinel", label: "哨兵真彩", desc: "Sentinel-2 全球真彩影像" },
];

export default function TacticalSettingsModal(
  props: TacticalSettingsModalProps
) {
  const { open, onOpenChange } = props;
  const [activeTab, setActiveTab] = useState<SettingsTabId>("mcp");

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onOpenChange]);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => onOpenChange(false)}
            className="absolute inset-0 bg-[#01040a]/80 backdrop-blur-md"
          />

          {/* Modal Container */}
          <motion.div
            aria-label="AI 战术配置中心"
            aria-modal="true"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            role="dialog"
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="relative flex h-[86vh] w-[94vw] max-w-7xl overflow-hidden rounded-xl border border-cyan-400/30 bg-[#030914] shadow-[0_0_50px_rgba(8,145,178,0.15)] ring-1 ring-white/5"
          >
            {/* Header / Sidebar (Left) */}
            <div className="flex w-64 shrink-0 flex-col border-r border-cyan-400/20 bg-[#02050c]">
              <div className="flex h-14 items-center gap-3 border-b border-cyan-400/20 px-5">
                <div className="grid size-7 place-items-center rounded bg-cyan-950/50 text-cyan-400 border border-cyan-400/20">
                  <Shield className="size-4" />
                </div>
                <div className="flex flex-col">
                  <span className="font-mono text-xs font-bold tracking-wider text-slate-100">
                    AI 战术配置中心
                  </span>
                  <span className="text-[9px] uppercase tracking-widest text-cyan-500/70">
                    战术参数中枢
                  </span>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-1">
                {SETTINGS_TABS.map((tab) => {
                  const isActive = activeTab === tab.id;
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      type="button"
                      className={cn(
                        "flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-all",
                        isActive
                          ? "bg-cyan-400/10 border border-cyan-400/20 shadow-[inset_0_0_12px_rgba(34,211,238,0.05)]"
                          : "border border-transparent hover:bg-white/5"
                      )}
                    >
                      <Icon
                        className={cn(
                          "mt-0.5 size-4 shrink-0 transition-colors",
                          isActive ? "text-cyan-400" : "text-slate-500"
                        )}
                      />
                      <div className="flex flex-col">
                        <span
                          className={cn(
                            "font-mono text-[11px] uppercase tracking-wider",
                            isActive
                              ? "text-cyan-100 font-bold"
                              : "text-slate-300"
                          )}
                        >
                          {tab.label}
                        </span>
                        <span className="text-[10px] text-slate-500 line-clamp-1">
                          {tab.desc}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="border-t border-cyan-400/20 p-4">
                <div className="flex items-center gap-2">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-500"></span>
                  </span>
                  <span className="font-mono text-[10px] uppercase text-emerald-400/80">
                    系统在线
                  </span>
                </div>
              </div>
            </div>

            {/* Content Area (Right) */}
            <div className="flex flex-1 flex-col relative bg-gradient-to-b from-[#050914] to-[#02050c]">
              <button
                aria-label="关闭战术配置中心"
                onClick={() => onOpenChange(false)}
                className="absolute right-4 top-4 z-10 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-white/10 hover:text-slate-200"
                title="关闭"
                type="button"
              >
                <X className="size-4" />
              </button>

              <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
                {activeTab === "mcp" && <McpConfigSection {...props} />}
                {activeTab === "skills" && <SkillsConfigSection {...props} />}
                {activeTab === "system" && <SystemConfigSection {...props} />}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Sub-sections
// ──────────────────────────────────────────────────────────────────────────────

const MCP_CONFIG_PLACEHOLDER = `{
  "mcpServers": {
    "example-server": {
      "command": "npx",
      "args": ["-y", "mcp-server-example"]
    }
  }
}`;

function getMcpInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "M";
  return trimmed.slice(0, 1).toUpperCase();
}

function getStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item).trim())
      .filter((item) => item.length > 0);
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  return [];
}

function getStringRecord(value: unknown): Record<string, string> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => [key.trim(), String(item)] as const)
    .filter(([key]) => key.length > 0);
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function getNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const next = Number(value);
    if (Number.isFinite(next)) return next;
  }
  return undefined;
}

function normalizeImportedTransport(
  config: Record<string, unknown>
): MCPServerImportPayload["transport"] {
  const raw = String(config.transport ?? config.type ?? "").toLowerCase();
  if (raw.includes("sse")) return "sse";
  if (raw.includes("http") || config.url || config.baseUrl) return "http";
  return "stdio";
}

function getImportedEndpoint(
  config: Record<string, unknown>,
  transport: MCPServerImportPayload["transport"]
): string {
  const url = config.url ?? config.baseUrl ?? config.endpoint;
  if (typeof url === "string" && url.trim()) return url.trim();

  const command =
    typeof config.command === "string" ? config.command.trim() : "";
  const args = Array.isArray(config.args)
    ? config.args.filter((arg): arg is string => typeof arg === "string")
    : [];
  const commandLine = [command, ...args].filter(Boolean).join(" ");
  if (commandLine) return commandLine;

  return transport === "stdio" ? "" : "http://localhost:3000/mcp";
}

function parseMcpServerConfigJson(raw: string): MCPServerImportPayload[] {
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object") {
    throw new Error("配置必须是 JSON 对象。");
  }

  const root = parsed as Record<string, unknown>;
  const source = root.mcpServers ?? root.servers ?? root;
  const entries = Array.isArray(source)
    ? source.map((value, index) => [`server-${index + 1}`, value] as const)
    : Object.entries(source as Record<string, unknown>);

  const servers = entries.map(([fallbackName, value]) => {
    const config =
      value && typeof value === "object"
        ? (value as Record<string, unknown>)
        : {};
    const name =
      typeof config.name === "string" && config.name.trim()
        ? config.name.trim()
        : fallbackName;
    const transport = normalizeImportedTransport(config);
    const endpoint = getImportedEndpoint(config, transport);
    if (!endpoint) {
      throw new Error(`MCP Server "${name}" 缺少 command、url 或 endpoint。`);
    }
    return {
      name,
      endpoint,
      transport,
      enabled: config.enabled !== false,
      command:
        typeof config.command === "string" && config.command.trim()
          ? config.command.trim()
          : undefined,
      args: getStringArray(config.args),
      url:
        typeof (config.url ?? config.baseUrl) === "string"
          ? String(config.url ?? config.baseUrl).trim()
          : undefined,
      env: getStringRecord(config.env),
      headers: getStringRecord(config.headers),
      allowedTools: getStringArray(config.allowedTools ?? config.allowed_tools),
      timeoutSeconds: getNumber(
        config.timeoutSeconds ?? config.timeout_seconds
      ),
    };
  });

  if (servers.length === 0) {
    throw new Error("没有识别到可导入的 MCP Server。");
  }

  return servers;
}

function buildMcpServerConfigJson(
  server: TacticalSettingsProps["mcpServers"][number]
): string {
  const config: Record<string, unknown> = {
    transport: server.transport,
    enabled: server.enabled,
  };
  if (server.transport === "stdio") {
    if (server.command) config.command = server.command;
    if (server.args?.length) config.args = server.args;
    if (!server.command && server.endpoint) config.endpoint = server.endpoint;
  } else {
    config.url = server.url || server.endpoint;
  }
  if (server.env && Object.keys(server.env).length > 0) config.env = server.env;
  if (server.headers && Object.keys(server.headers).length > 0) {
    config.headers = server.headers;
  }
  if (server.allowedTools?.length) config.allowedTools = server.allowedTools;
  if (server.timeoutSeconds) config.timeoutSeconds = server.timeoutSeconds;

  return JSON.stringify(
    {
      mcpServers: {
        [server.name]: config,
      },
    },
    null,
    2
  );
}

function McpStatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium",
        enabled
          ? "border-emerald-400/24 bg-emerald-400/10 text-emerald-200"
          : "border-slate-600/50 bg-slate-800/50 text-slate-400"
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          enabled ? "bg-emerald-300" : "bg-slate-500"
        )}
      />
      {enabled ? "已启用" : "已停用"}
    </span>
  );
}

function McpConnectionBadge({
  status,
}: {
  status?: TacticalSettingsProps["mcpServers"][number]["status"];
}) {
  const current = status ?? "unknown";
  const label =
    current === "online"
      ? "在线"
      : current === "validating"
        ? "验证中"
        : current === "error"
          ? "错误"
          : "未验证";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px]",
        current === "online" &&
          "border-emerald-400/24 bg-emerald-400/10 text-emerald-200",
        current === "validating" &&
          "border-cyan-400/24 bg-cyan-400/10 text-cyan-100",
        current === "error" && "border-red-400/30 bg-red-500/10 text-red-200",
        current === "unknown" &&
          "border-slate-600/50 bg-slate-800/50 text-slate-400"
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          current === "online" && "bg-emerald-300",
          current === "validating" && "bg-cyan-300",
          current === "error" && "bg-red-300",
          current === "unknown" && "bg-slate-500"
        )}
      />
      {label}
    </span>
  );
}

function McpToggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="relative inline-flex cursor-pointer items-center">
      <input
        aria-label={label}
        checked={checked}
        className="peer sr-only"
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <span className="h-7 w-12 rounded-full bg-slate-700/80 transition-colors peer-checked:bg-emerald-400" />
      <span className="absolute left-1 size-5 rounded-full bg-slate-300 transition-transform peer-checked:translate-x-5 peer-checked:bg-white" />
    </label>
  );
}

function ManualMcpConfigDialog({
  busy,
  error,
  onClose,
  onConfirm,
  onRawChange,
  open,
  raw,
  title = "手动配置",
}: {
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  onRawChange: (value: string) => void;
  open: boolean;
  raw: string;
  title?: string;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 px-5 backdrop-blur-sm">
      <motion.div
        aria-label="手动配置 MCP Servers"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-slate-700/80 bg-[#1a1d22] text-slate-100 shadow-2xl"
        initial={{ opacity: 0, y: 18, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 18, scale: 0.98 }}
        role="dialog"
        transition={{ duration: 0.18 }}
      >
        <header className="flex items-center justify-between gap-4 border-b border-slate-700/70 px-5 py-4">
          <h3 className="text-xl font-semibold text-slate-100">{title}</h3>
          <div className="flex items-center gap-3">
            <button
              className="rounded-md bg-slate-700/55 px-4 py-2 text-sm font-semibold text-slate-200 transition-colors hover:bg-slate-700"
              type="button"
            >
              原始配置（JSON）
            </button>
            <button
              aria-label="关闭手动配置"
              className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white/8 hover:text-slate-100"
              disabled={busy}
              onClick={onClose}
              type="button"
            >
              <X className="size-5" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          <p className="mb-4 text-sm leading-relaxed text-slate-400">
            请从 MCP Servers 的介绍页面复制配置 JSON（优先使用 NPX 或 UVX
            配置），并粘贴到输入框中。
          </p>
          <div className="relative overflow-hidden rounded-lg border border-slate-600/80 bg-[#24282d]">
            <div className="pointer-events-none absolute inset-y-0 left-0 w-12 border-r border-slate-700/70 bg-[#24282d] py-3 text-right font-mono text-sm leading-6 text-slate-500">
              {Array.from({ length: 13 }, (_, index) => (
                <div className="pr-3" key={index}>
                  {index + 1}
                </div>
              ))}
            </div>
            <textarea
              aria-label="MCP Servers 原始配置 JSON"
              className="min-h-[350px] w-full resize-y bg-transparent py-3 pl-16 pr-4 font-mono text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-500"
              onChange={(event) => onRawChange(event.target.value)}
              placeholder={MCP_CONFIG_PLACEHOLDER}
              spellCheck={false}
              value={raw}
            />
          </div>
          {error && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-4 border-t border-slate-700/70 px-5 py-4">
          <div className="flex items-center gap-2 text-sm text-amber-200">
            <AlertCircle className="size-4" />
            配置前请确认来源，甄别风险
          </div>
          <div className="flex items-center gap-3">
            <Button
              className="bg-slate-700/70 text-slate-200 hover:bg-slate-700"
              disabled={busy}
              onClick={onClose}
              type="button"
              variant="ghost"
            >
              取消
            </Button>
            <Button
              className="bg-slate-200 text-slate-950 hover:bg-white"
              disabled={!raw.trim() || busy}
              onClick={onConfirm}
              type="button"
              variant="ghost"
            >
              {busy ? "验证中" : "确认"}
            </Button>
          </div>
        </footer>
      </motion.div>
    </div>
  );
}

function McpConfigSection({
  mcpServers,
  activeMcpServersCount,
  projectMcpEnabled,
  onProjectMcpEnabledChange,
  onImportMcpServers,
  onRemoveServer,
  onToggleServer,
  onUpdateMcpServer,
  onValidateMcpServer,
}: TacticalSettingsProps) {
  const [expandedServerIds, setExpandedServerIds] = useState<string[]>(() =>
    mcpServers.length > 0 ? [mcpServers[0].id] : []
  );
  const [manualConfigOpen, setManualConfigOpen] = useState(false);
  const [manualConfigRaw, setManualConfigRaw] = useState("");
  const [manualConfigError, setManualConfigError] = useState<string | null>(
    null
  );
  const [manualConfigBusy, setManualConfigBusy] = useState(false);
  const [editingServerId, setEditingServerId] = useState<string | null>(null);
  const [serverMenu, setServerMenu] = useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);
  const [lastRefreshLabel, setLastRefreshLabel] = useState("刚刚");

  useEffect(() => {
    setExpandedServerIds((prev) => {
      const existing = new Set(mcpServers.map((server) => server.id));
      const next = prev.filter((id) => existing.has(id));
      if (next.length === 0 && mcpServers[0]) return [mcpServers[0].id];
      return next;
    });
  }, [mcpServers]);

  const totalTools = useMemo(
    () =>
      mcpServers.reduce(
        (total, server) => total + (server.tools?.length ?? 0),
        0
      ),
    [mcpServers]
  );

  const toggleExpanded = (id: string) => {
    setExpandedServerIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleManualConfigConfirm = async () => {
    setManualConfigBusy(true);
    try {
      const imported = parseMcpServerConfigJson(manualConfigRaw);
      if (editingServerId) {
        if (imported.length !== 1) {
          throw new Error("编辑模式一次只能保存一个 MCP Server。");
        }
        await onUpdateMcpServer(editingServerId, imported[0]);
      } else {
        await onImportMcpServers(imported);
      }
      setManualConfigOpen(false);
      setManualConfigRaw("");
      setManualConfigError(null);
      setEditingServerId(null);
    } catch (error) {
      setManualConfigError(
        error instanceof Error ? error.message : "配置解析失败。"
      );
    } finally {
      setManualConfigBusy(false);
    }
  };

  const openServerMenu = (
    event: { currentTarget: HTMLButtonElement },
    id: string
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setServerMenu({
      id,
      x: Math.max(12, rect.right - 168),
      y: rect.bottom + 8,
    });
  };

  const openEditConfig = (
    server: TacticalSettingsProps["mcpServers"][number]
  ) => {
    setEditingServerId(server.id);
    setManualConfigRaw(buildMcpServerConfigJson(server));
    setManualConfigError(null);
    setManualConfigOpen(true);
    setServerMenu(null);
  };

  const menuServer = serverMenu
    ? mcpServers.find((server) => server.id === serverMenu.id)
    : null;

  return (
    <div className="flex min-h-full flex-col gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              已配置的 MCP Servers
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              管理已添加的 MCP 服务器，可启用、配置或添加新的工具能力。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              aria-label="刷新 MCP Servers 列表"
              className="grid size-10 place-items-center rounded-md border border-slate-700/70 bg-slate-800/70 text-slate-300 transition-colors hover:border-slate-600 hover:bg-slate-700/80 hover:text-white"
              onClick={() => {
                setLastRefreshLabel("刷新中");
                void Promise.all(
                  mcpServers.map((server) => onValidateMcpServer(server.id))
                ).finally(() => setLastRefreshLabel("刚刚"));
              }}
              title="同步后端工具列表"
              type="button"
            >
              <RefreshCw className="size-4" />
            </button>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-100 px-4 text-sm font-semibold text-slate-950 transition-colors hover:bg-white"
              onClick={() => {
                setEditingServerId(null);
                setManualConfigRaw("");
                setManualConfigError(null);
                setManualConfigOpen(true);
              }}
              type="button"
            >
              <Plus className="size-4" />
              添加
              <MoreHorizontal className="size-4" />
            </button>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/55 px-4 py-3">
            <div className="text-[11px] text-slate-500">Servers</div>
            <div className="mt-1 text-xl font-semibold text-slate-100">
              {mcpServers.length}
            </div>
          </div>
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/55 px-4 py-3">
            <div className="text-[11px] text-slate-500">已启用</div>
            <div className="mt-1 text-xl font-semibold text-emerald-200">
              {activeMcpServersCount}
            </div>
          </div>
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/55 px-4 py-3">
            <div className="text-[11px] text-slate-500">工具预览</div>
            <div className="mt-1 text-xl font-semibold text-cyan-100">
              {totalTools}
            </div>
          </div>
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/55 px-4 py-3">
            <div className="text-[11px] text-slate-500">刷新状态</div>
            <div className="mt-1 text-sm font-medium text-slate-200">
              {lastRefreshLabel}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700/80 bg-[#171b20] shadow-[0_16px_42px_rgba(0,0,0,0.22)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/70 px-5 py-4">
          <div>
            <div className="text-base font-semibold text-slate-100">
              MCP Servers 管理
            </div>
            <div className="mt-1 text-sm text-slate-400">
              服务器启用状态保存在本地项目配置，后端真实连接由运行环境读取。
            </div>
          </div>
          <div className="flex items-center gap-3">
            <McpStatusBadge enabled={projectMcpEnabled} />
            <McpToggle
              checked={projectMcpEnabled}
              label="启用项目内置 MCP"
              onChange={onProjectMcpEnabledChange}
            />
          </div>
        </div>

        <div className="divide-y divide-slate-700/70">
          {mcpServers.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center gap-3 px-5 text-center">
              <Plug className="size-7 text-slate-500" />
              <div>
                <div className="text-sm font-semibold text-slate-200">
                  尚未配置外部 MCP Server
                </div>
                <div className="mt-1 text-sm text-slate-500">
                  点击添加，粘贴 MCP Servers JSON 配置。
                </div>
              </div>
            </div>
          ) : (
            mcpServers.map((server) => {
              const expanded = expandedServerIds.includes(server.id);
              const tools = server.tools ?? [];
              return (
                <div key={server.id}>
                  <div className="flex items-center gap-4 px-5 py-4">
                    <button
                      aria-label={`${expanded ? "收起" : "展开"} ${
                        server.name
                      }`}
                      className="grid size-7 shrink-0 place-items-center rounded-md text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
                      onClick={() => toggleExpanded(server.id)}
                      type="button"
                    >
                      <span
                        className={cn(
                          "text-lg leading-none transition-transform",
                          expanded && "rotate-90"
                        )}
                      >
                        ›
                      </span>
                    </button>
                    <div className="grid size-12 shrink-0 place-items-center rounded-lg bg-slate-300 text-xl font-semibold text-slate-950">
                      {getMcpInitial(server.name)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-base font-semibold text-slate-100">
                          {server.name}
                        </span>
                        {server.enabled && (
                          <CheckCircle2 className="size-4 text-emerald-300" />
                        )}
                        <Badge
                          className="font-mono text-[10px]"
                          variant="muted"
                        >
                          {server.transport.toUpperCase()}
                        </Badge>
                        <McpConnectionBadge status={server.status} />
                      </div>
                      <div className="mt-1 truncate font-mono text-xs text-slate-500">
                        {server.endpoint}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <McpToggle
                        checked={server.enabled}
                        label={`${server.enabled ? "停用" : "启用"} ${
                          server.name
                        }`}
                        onChange={(checked) =>
                          onToggleServer(server.id, checked)
                        }
                      />
                      <button
                        aria-label={`打开 ${server.name} 设置菜单`}
                        className="grid size-9 place-items-center rounded-md border border-slate-700/70 bg-slate-900/70 text-slate-400 transition-colors hover:border-cyan-400/30 hover:bg-cyan-400/10 hover:text-cyan-100"
                        onClick={(event) => openServerMenu(event, server.id)}
                        title="MCP Server 设置"
                        type="button"
                      >
                        <Settings className="size-4" />
                      </button>
                    </div>
                  </div>

                  {expanded && (
                    <div className="px-5 pb-4">
                      <div className="mb-3 grid gap-2 text-[11px] text-slate-400 md:grid-cols-2">
                        <div className="rounded-md border border-slate-700/70 bg-slate-950/35 px-3 py-2">
                          <div className="font-mono text-slate-500">
                            最近校验
                          </div>
                          <div className="mt-1 text-slate-200">
                            {server.lastValidatedAt
                              ? new Date(
                                  server.lastValidatedAt
                                ).toLocaleString()
                              : "尚未校验"}
                          </div>
                        </div>
                        <div className="rounded-md border border-slate-700/70 bg-slate-950/35 px-3 py-2">
                          <div className="font-mono text-slate-500">
                            连接日志
                          </div>
                          <div className="mt-1 line-clamp-2 text-slate-200">
                            {server.statusMessage || "暂无连接日志。"}
                          </div>
                        </div>
                      </div>
                      <div className="overflow-hidden rounded-md border border-slate-700/80 bg-[#24272b]">
                        {tools.length === 0 ? (
                          <div className="flex min-h-24 items-center justify-center px-5 py-6 text-center text-sm text-slate-500">
                            {server.status === "error"
                              ? "验证失败，无法读取工具列表。"
                              : server.status === "online"
                                ? "该 MCP 已验证，但没有声明可用工具。"
                                : "验证后会在这里显示该 MCP 暴露的 tools。"}
                          </div>
                        ) : (
                          tools.map((tool, index) => (
                            <div
                              className={cn(
                                "grid gap-3 px-5 py-3 text-sm md:grid-cols-[minmax(180px,260px)_1fr_auto]",
                                index > 0 && "border-t border-slate-700/70"
                              )}
                              key={tool.name}
                            >
                              <div className="truncate font-mono font-semibold text-slate-100">
                                {tool.name}
                              </div>
                              <div className="line-clamp-2 text-slate-300">
                                {tool.description}
                              </div>
                              <Badge
                                className="justify-self-start font-mono text-[9px] md:justify-self-end"
                                variant="muted"
                              >
                                schema
                              </Badge>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {serverMenu &&
        menuServer &&
        createPortal(
          <div
            className="fixed inset-0 z-[130]"
            onClick={() => setServerMenu(null)}
          >
            <div
              className="fixed w-40 overflow-hidden rounded-md border border-slate-700/80 bg-[#111821] py-1 shadow-2xl ring-1 ring-cyan-400/10"
              onClick={(event) => event.stopPropagation()}
              style={{ left: serverMenu.x, top: serverMenu.y }}
            >
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 transition-colors hover:bg-slate-800"
                onClick={() => openEditConfig(menuServer)}
                type="button"
              >
                <Pencil className="size-4 text-slate-400" />
                编辑
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 transition-colors hover:bg-slate-800"
                onClick={() => {
                  setServerMenu(null);
                  void onValidateMcpServer(menuServer.id);
                }}
                type="button"
              >
                <RefreshCw className="size-4 text-cyan-300" />
                刷新工具
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 transition-colors hover:bg-slate-800"
                onClick={() => {
                  setExpandedServerIds((prev) =>
                    prev.includes(menuServer.id)
                      ? prev
                      : [...prev, menuServer.id]
                  );
                  setServerMenu(null);
                }}
                type="button"
              >
                <ScrollText className="size-4 text-slate-400" />
                日志
              </button>
              <button
                className="flex w-full items-center gap-2 border-t border-slate-700/70 px-3 py-2 text-left text-sm text-red-200 transition-colors hover:bg-red-500/10"
                onClick={() => {
                  setServerMenu(null);
                  onRemoveServer(menuServer.id);
                }}
                type="button"
              >
                <Trash2 className="size-4" />
                删除
              </button>
            </div>
          </div>,
          document.body
        )}

      <ManualMcpConfigDialog
        busy={manualConfigBusy}
        error={manualConfigError}
        onClose={() => {
          setManualConfigOpen(false);
          setManualConfigError(null);
          setEditingServerId(null);
        }}
        onConfirm={handleManualConfigConfirm}
        onRawChange={(value) => {
          setManualConfigRaw(value);
          setManualConfigError(null);
        }}
        open={manualConfigOpen}
        raw={manualConfigRaw}
        title={editingServerId ? "编辑 MCP Server" : "手动配置"}
      />
    </div>
  );
}

type SkillLibraryView = "all" | "backend" | "custom" | "disabled";
type SkillSource = "backend" | "custom";
type SkillDetailPanel = "schema" | "output" | "activity";

const SKILL_LIBRARY_VIEWS: Array<{
  id: SkillLibraryView;
  label: string;
}> = [
  { id: "all", label: "全部" },
  { id: "backend", label: "后端注册" },
  { id: "custom", label: "自定义" },
  { id: "disabled", label: "已停用" },
];

interface SkillSchemaField {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface SkillCallRecord {
  id: string;
  at: string;
  status: "success" | "warning";
  latencyMs: number;
  input: string;
}

interface SkillCatalogItem {
  id: string;
  name: string;
  description: string;
  source: SkillSource;
  version: string;
  enabled: boolean;
  readonly: boolean;
  inputSchema: SkillSchemaField[];
  outputSchema: SkillSchemaField[];
  usageCount: number;
  lastUsedAt: string;
  createdBy: string;
  updatedAt: string;
  responseTimeMs: number;
  rawCustomId?: string;
  callRecords: SkillCallRecord[];
}

function getParameterRows(parameters?: Record<string, unknown>) {
  if (!parameters) return [];
  return Object.entries(parameters).map(([name, value]) => {
    const meta =
      typeof value === "object" && value !== null
        ? (value as Record<string, unknown>)
        : {};
    const type = typeof meta.type === "string" ? meta.type : "unknown";
    const required = meta.required !== false;
    const description =
      typeof meta.description === "string" ? meta.description : "";
    return { name, type, required, description };
  });
}

function hashSkillText(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function toMockDate(seed: number, offset = 0): string {
  const hoursAgo = (seed % 180) + offset + 2;
  return new Date(Date.now() - hoursAgo * 60 * 60 * 1000).toISOString();
}

function formatRelativeDate(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "未知";
  const diffMs = Date.now() - timestamp;
  const minutes = Math.max(1, Math.floor(diffMs / 60000));
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

function formatExactDate(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function getMockOutputSchema(source: SkillSource): SkillSchemaField[] {
  if (source === "custom") {
    return [
      {
        name: "guidance",
        type: "string",
        required: true,
        description: "注入到 AI 会话的用户自定义行为说明",
      },
      {
        name: "applied",
        type: "boolean",
        required: true,
        description: "是否参与当前 AI 请求上下文",
      },
    ];
  }
  return [
    {
      name: "ok",
      type: "boolean",
      required: true,
      description: "技能执行是否成功",
    },
    {
      name: "summary",
      type: "string",
      required: false,
      description: "后端运行态返回的执行摘要",
    },
    {
      name: "scenario",
      type: "object",
      required: false,
      description: "可能变更后的 runtime scenario snapshot",
    },
  ];
}

function schemaFromSpec(spec: string, name: string): SkillSchemaField[] {
  const description = spec.trim();
  if (!description) return [];
  return [
    {
      name,
      type: "string",
      required: false,
      description,
    },
  ];
}

function schemaToSpec(fields: SkillSchemaField[] | undefined): string {
  if (!fields || fields.length === 0) return "";
  return fields
    .map((field) => {
      const required = field.required ? "required" : "optional";
      return `${field.name} (${field.type}, ${required}): ${field.description}`;
    })
    .join("\n");
}

function getMockCallRecords(
  id: string,
  name: string,
  seed: number,
  usageCount: number,
  responseTimeMs: number
): SkillCallRecord[] {
  if (usageCount === 0) return [];
  return Array.from({ length: Math.min(3, usageCount) }).map((_, index) => ({
    id: `${id}:call:${index}`,
    at: toMockDate(seed + index * 17, index * 8),
    status: index === 2 && seed % 5 === 0 ? "warning" : "success",
    latencyMs: responseTimeMs + index * 13,
    input:
      index === 0 ? `${name} latest invocation` : `sample payload ${index}`,
  }));
}

function createSkillCatalog(
  registeredSkills: TacticalSettingsProps["registeredSkills"],
  customSkills: TacticalSettingsProps["customSkills"]
): SkillCatalogItem[] {
  return [
    ...registeredSkills.map((skill, index) => {
      const seed = hashSkillText(skill.name);
      const usageCount = 24 + (seed % 180);
      const responseTimeMs = 120 + (seed % 420);
      const id = `backend:${skill.name}`;
      const inputSchema = getParameterRows(skill.parameters);
      return {
        id,
        name: skill.name,
        description: skill.description,
        source: "backend" as const,
        version: `v${1 + (seed % 3)}.${(seed >> 3) % 10}.${index}`,
        enabled: true,
        readonly: true,
        inputSchema,
        outputSchema: getMockOutputSchema("backend"),
        usageCount,
        lastUsedAt: toMockDate(seed, index),
        createdBy: "TianShu Runtime",
        updatedAt: toMockDate(seed, index + 18),
        responseTimeMs,
        callRecords: getMockCallRecords(
          id,
          skill.name,
          seed,
          usageCount,
          responseTimeMs
        ),
      };
    }),
    ...customSkills.map((skill, index) => {
      const seed = hashSkillText(skill.id + skill.name);
      const usageCount =
        typeof skill.usageCount === "number"
          ? skill.usageCount
          : skill.enabled
            ? seed % 38
            : seed % 5;
      const responseTimeMs = 90 + (seed % 260);
      const id = `custom:${skill.id}`;
      return {
        id,
        name: skill.name,
        description: skill.description,
        source: "custom" as const,
        version: skill.version || "custom-1",
        enabled: skill.enabled,
        readonly: false,
        inputSchema:
          skill.inputSchema && skill.inputSchema.length > 0
            ? skill.inputSchema
            : [
                {
                  name: "context",
                  type: "string",
                  required: true,
                  description: "当前对话与战术场景上下文",
                },
                {
                  name: "operator_intent",
                  type: "string",
                  required: false,
                  description: "操作者输入的自然语言目标",
                },
              ],
        outputSchema:
          skill.outputSchema && skill.outputSchema.length > 0
            ? skill.outputSchema
            : getMockOutputSchema("custom"),
        usageCount,
        lastUsedAt:
          skill.lastUsedAt ??
          (usageCount > 0 ? toMockDate(seed, index + 4) : "never"),
        createdBy: skill.createdBy || "Operator",
        updatedAt: skill.updatedAt || toMockDate(seed, index + 12),
        responseTimeMs,
        rawCustomId: skill.id,
        callRecords: getMockCallRecords(
          id,
          skill.name,
          seed,
          usageCount,
          responseTimeMs
        ),
      };
    }),
  ];
}

function SkillMetricCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "cyan",
}: {
  icon: typeof Wrench;
  label: string;
  value: string | number;
  hint: string;
  tone?: "cyan" | "emerald" | "amber";
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#07111d] px-3.5 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] text-slate-400">{label}</div>
        <div
          className={cn(
            "grid size-7 place-items-center rounded-md border",
            tone === "emerald"
              ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-200"
              : tone === "amber"
                ? "border-amber-300/20 bg-amber-300/10 text-amber-200"
                : "border-cyan-300/20 bg-cyan-300/10 text-cyan-200"
          )}
        >
          <Icon className="size-3.5" />
        </div>
      </div>
      <div className="mt-2 font-mono text-xl font-semibold text-slate-50">
        {value}
      </div>
      <div className="mt-1 text-[10px] text-slate-500">{hint}</div>
    </div>
  );
}

function SkillSchemaList({
  fields,
  emptyText,
}: {
  fields: SkillSchemaField[];
  emptyText: string;
}) {
  if (fields.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-slate-700/70 bg-black/20 text-[11px] text-slate-500">
        {emptyText}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {fields.map((field) => (
        <div
          className="rounded-md border border-slate-700/60 bg-slate-950/40 px-3 py-2"
          key={field.name}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="break-all font-mono text-[11px] text-slate-100">
                {field.name}
              </div>
              <div className="mt-1 text-[10px] leading-relaxed text-slate-500">
                {field.description || "暂无说明"}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Badge className="font-mono text-[9px]" variant="muted">
                {field.type}
              </Badge>
              <Badge
                className="font-mono text-[9px]"
                variant={field.required ? "warning" : "muted"}
              >
                {field.required ? "必填" : "可选"}
              </Badge>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SkillsConfigSection({
  customSkills,
  activeCustomSkillsCount,
  registeredSkills,
  skillsLoading,
  skillsError,
  newSkillName,
  newSkillDescription,
  onRefreshSkills,
  onAddSkill,
  onRemoveCustomSkill,
  onToggleCustomSkill,
  onUpdateCustomSkill,
  onNewSkillNameChange,
  onNewSkillDescriptionChange,
}: TacticalSettingsProps) {
  const [skillQuery, setSkillQuery] = useState("");
  const [skillView, setSkillView] = useState<SkillLibraryView>("all");
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [detailPanel, setDetailPanel] = useState<SkillDetailPanel>("schema");
  const [createPanelOpen, setCreatePanelOpen] = useState(false);
  const [newSkillSummary, setNewSkillSummary] = useState("");
  const [newSkillPrompt, setNewSkillPrompt] = useState("");
  const [newSkillInputSpec, setNewSkillInputSpec] = useState("");
  const [newSkillOutputSpec, setNewSkillOutputSpec] = useState("");
  const [newSkillEnabled, setNewSkillEnabled] = useState(true);
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null);

  const skillCatalog = useMemo(
    () => createSkillCatalog(registeredSkills, customSkills),
    [customSkills, registeredSkills]
  );

  const filteredSkillCatalog = useMemo(() => {
    const normalizedQuery = skillQuery.trim().toLowerCase();
    return skillCatalog.filter((item) => {
      const matchesView =
        skillView === "all" ||
        (skillView === "backend" && item.source === "backend") ||
        (skillView === "custom" && item.source === "custom") ||
        (skillView === "disabled" && !item.enabled);
      if (!matchesView) return false;
      if (!normalizedQuery) return true;
      return (
        item.name.toLowerCase().includes(normalizedQuery) ||
        item.description.toLowerCase().includes(normalizedQuery) ||
        item.version.toLowerCase().includes(normalizedQuery) ||
        item.createdBy.toLowerCase().includes(normalizedQuery)
      );
    });
  }, [skillCatalog, skillQuery, skillView]);

  useEffect(() => {
    if (filteredSkillCatalog.length === 0) {
      setSelectedSkillId(null);
      return;
    }
    if (!filteredSkillCatalog.some((item) => item.id === selectedSkillId)) {
      setSelectedSkillId(filteredSkillCatalog[0].id);
    }
  }, [filteredSkillCatalog, selectedSkillId]);

  useEffect(() => {
    if (!newSkillName && !newSkillDescription) {
      setNewSkillSummary("");
      setNewSkillPrompt("");
      setNewSkillInputSpec("");
      setNewSkillOutputSpec("");
      setNewSkillEnabled(true);
    }
  }, [newSkillDescription, newSkillName]);

  const selectedSkill =
    filteredSkillCatalog.find((item) => item.id === selectedSkillId) ??
    filteredSkillCatalog[0] ??
    null;
  const backendCount = skillCatalog.filter(
    (skill) => skill.source === "backend"
  ).length;
  const customCount = skillCatalog.filter(
    (skill) => skill.source === "custom"
  ).length;
  const totalUsageCount = skillCatalog.reduce(
    (total, skill) => total + skill.usageCount,
    0
  );
  const averageResponseMs =
    skillCatalog.length === 0
      ? 0
      : Math.round(
          skillCatalog.reduce(
            (total, skill) => total + skill.responseTimeMs,
            0
          ) / skillCatalog.length
        );
  const disabledCount = skillCatalog.filter((skill) => !skill.enabled).length;

  const resetSkillForm = () => {
    onNewSkillNameChange("");
    onNewSkillDescriptionChange("");
    setNewSkillSummary("");
    setNewSkillPrompt("");
    setNewSkillInputSpec("");
    setNewSkillOutputSpec("");
    setNewSkillEnabled(true);
    setEditingSkillId(null);
  };

  const handleOpenCreateSkill = () => {
    resetSkillForm();
    setCreatePanelOpen(true);
  };

  const handleEditSelectedSkill = () => {
    if (!selectedSkill?.rawCustomId) return;
    const rawSkill = customSkills.find(
      (skill) => skill.id === selectedSkill.rawCustomId
    );
    setEditingSkillId(selectedSkill.rawCustomId);
    setCreatePanelOpen(true);
    onNewSkillNameChange(rawSkill?.name ?? selectedSkill.name);
    setNewSkillSummary(rawSkill?.description ?? selectedSkill.description);
    setNewSkillPrompt(
      rawSkill?.prompt || rawSkill?.description || selectedSkill.description
    );
    setNewSkillInputSpec(schemaToSpec(rawSkill?.inputSchema));
    setNewSkillOutputSpec(schemaToSpec(rawSkill?.outputSchema));
    setNewSkillEnabled(rawSkill?.enabled ?? selectedSkill.enabled);
  };

  const handleCreateCustomSkill = async () => {
    const name = newSkillName.trim();
    const summary = newSkillSummary.trim();
    const prompt = newSkillPrompt.trim();
    if (!name || !summary || !prompt) return;

    if (editingSkillId) {
      await onUpdateCustomSkill(editingSkillId, {
        name,
        description: summary,
        prompt,
        inputSchema: schemaFromSpec(newSkillInputSpec, "input"),
        outputSchema: schemaFromSpec(newSkillOutputSpec, "output"),
        enabled: newSkillEnabled,
      });
    } else {
      await onAddSkill({
        description: summary,
        prompt,
        inputSchema: schemaFromSpec(newSkillInputSpec, "input"),
        outputSchema: schemaFromSpec(newSkillOutputSpec, "output"),
        enabled: newSkillEnabled,
      });
    }
    resetSkillForm();
    setCreatePanelOpen(false);
  };

  return (
    <div className="flex min-h-full flex-col gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex flex-col gap-4 rounded-xl border border-slate-700/60 bg-[#07111d] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-lg font-semibold text-cyan-50">
              技能库管理
            </h2>
            <Badge className="font-mono text-[9px]" variant="muted">
              Agent Skills
            </Badge>
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-400">
            统一管理后端注册技能和文件夹自定义提示词，展示
            schema、版本、调用记录和启用状态。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={onRefreshSkills}
            disabled={skillsLoading}
            variant="ghost"
            size="sm"
            className="gap-2 border border-cyan-400/30 font-mono text-xs text-cyan-200"
          >
            <RefreshCw
              className={cn("size-3.5", skillsLoading && "animate-spin")}
            />
            同步后端
          </Button>
          <Button
            onClick={() =>
              createPanelOpen
                ? setCreatePanelOpen(false)
                : handleOpenCreateSkill()
            }
            size="sm"
            variant="tactical"
            className="font-mono text-xs"
          >
            <Plus className="size-3.5" />
            新建自定义技能
          </Button>
        </div>
      </div>

      {skillsError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 font-mono text-xs text-red-200">
          <AlertCircle className="inline size-4 mr-2 -mt-0.5" />
          同步失败：{skillsError}
        </div>
      )}

      {createPanelOpen && (
        <div className="rounded-xl border border-cyan-400/15 bg-[#07111d] p-4 shadow-[inset_0_1px_0_rgba(103,232,249,0.06)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="font-mono text-xs font-semibold text-cyan-50">
                {editingSkillId ? "编辑自定义技能" : "注入新技能提示词"}
              </h3>
              <p className="mt-1 text-[10px] text-slate-500">
                字段会保存到后端 skills
                文件夹，并在对话提交时作为用户定义提示词注入。
              </p>
            </div>
            <label className="flex shrink-0 items-center gap-2 text-[10px] text-slate-400">
              <input
                checked={newSkillEnabled}
                className="size-3.5 accent-cyan-400"
                onChange={(event) => setNewSkillEnabled(event.target.checked)}
                type="checkbox"
              />
              创建后启用
            </label>
          </div>
          <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)_minmax(0,1fr)]">
            <input
              className={INPUT_CLASS}
              onChange={(event) => onNewSkillNameChange(event.target.value)}
              placeholder="技能名称，例如 refine_brief"
              value={newSkillName}
            />
            <input
              className={INPUT_CLASS}
              onChange={(event) => setNewSkillSummary(event.target.value)}
              placeholder="描述，例如 将口语需求整理成执行 brief"
              value={newSkillSummary}
            />
            <textarea
              className={cn(INPUT_CLASS, "min-h-[72px] resize-y lg:row-span-2")}
              onChange={(event) => setNewSkillPrompt(event.target.value)}
              placeholder="提示词内容"
              value={newSkillPrompt}
            />
            <input
              className={INPUT_CLASS}
              onChange={(event) => setNewSkillInputSpec(event.target.value)}
              placeholder="输入参数说明，例如 user_goal/context"
              value={newSkillInputSpec}
            />
            <input
              className={INPUT_CLASS}
              onChange={(event) => setNewSkillOutputSpec(event.target.value)}
              placeholder="输出格式，例如 JSON 或 Markdown checklist"
              value={newSkillOutputSpec}
            />
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button
              className="font-mono text-xs"
              onClick={() => {
                resetSkillForm();
                setCreatePanelOpen(false);
              }}
              size="sm"
              variant="ghost"
            >
              取消
            </Button>
            <Button
              className="font-mono text-xs"
              disabled={
                !newSkillName.trim() ||
                !newSkillSummary.trim() ||
                !newSkillPrompt.trim()
              }
              onClick={handleCreateCustomSkill}
              size="sm"
              variant="tactical"
            >
              <Plus className="size-3.5" />
              {editingSkillId ? "保存技能" : "注入技能"}
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-4">
        <SkillMetricCard
          hint="服务端 registry 只读同步"
          icon={Database}
          label="后端注册技能总数"
          value={backendCount}
        />
        <SkillMetricCard
          hint={`${activeCustomSkillsCount} 个当前启用，后端文件夹持久化`}
          icon={SlidersHorizontal}
          label="自定义技能"
          tone="emerald"
          value={customCount}
        />
        <SkillMetricCard
          hint="后端统计接入前使用 mock telemetry"
          icon={Activity}
          label="技能调用次数"
          value={totalUsageCount}
        />
        <SkillMetricCard
          hint={`${disabledCount} 个停用项`}
          icon={Clock}
          label="平均响应时间"
          tone="amber"
          value={`${averageResponseMs}ms`}
        />
      </div>

      <div className="grid min-h-[510px] flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_410px]">
        <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-700/70 bg-[#07111d]">
          <div className="border-b border-slate-700/60 p-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
                <input
                  className={cn(INPUT_CLASS, "h-8 pl-9")}
                  onChange={(event) => setSkillQuery(event.target.value)}
                  placeholder="搜索技能名称、描述、版本或创建者"
                  value={skillQuery}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {SKILL_LIBRARY_VIEWS.map((view) => {
                  const active = skillView === view.id;
                  return (
                    <button
                      className={cn(
                        "rounded-md border px-2.5 py-1.5 font-mono text-[10px] transition-colors",
                        active
                          ? "border-cyan-400/45 bg-cyan-400/12 text-cyan-100"
                          : "border-slate-700 bg-slate-950/40 text-slate-400 hover:border-cyan-400/25 hover:text-slate-200"
                      )}
                      key={view.id}
                      onClick={() => setSkillView(view.id)}
                      type="button"
                    >
                      {view.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="mt-3 hidden grid-cols-[minmax(240px,1.45fr)_110px_80px_92px_120px_44px] gap-3 border-t border-slate-800 pt-2 px-2 font-mono text-[9px] text-slate-500 lg:grid">
              <span>技能</span>
              <span>来源</span>
              <span>版本</span>
              <span>状态</span>
              <span>调用</span>
              <span>操作</span>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
            {skillsLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <div
                  className="m-3 h-16 animate-pulse rounded-lg border border-white/5 bg-white/[0.03]"
                  key={index}
                />
              ))
            ) : filteredSkillCatalog.length === 0 ? (
              <div className="m-3 flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-cyan-400/20 bg-cyan-950/5 text-center">
                <Wrench className="mb-2 size-5 text-cyan-600/50" />
                <div className="font-mono text-[11px] text-cyan-500/70">
                  未匹配到技能
                </div>
                <div className="mt-1 text-[10px] text-slate-500">
                  调整搜索词或筛选范围
                </div>
              </div>
            ) : (
              filteredSkillCatalog.map((skill) => {
                const selected = selectedSkill?.id === skill.id;
                return (
                  <div
                    className={cn(
                      "grid cursor-pointer gap-3 border-b border-slate-800/80 px-3 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 lg:grid-cols-[minmax(240px,1.45fr)_110px_80px_92px_120px_44px]",
                      selected ? "bg-cyan-400/10" : "hover:bg-slate-950/45"
                    )}
                    key={skill.id}
                    onClick={() => setSelectedSkillId(skill.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setSelectedSkillId(skill.id);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-mono text-xs font-semibold text-slate-100">
                          {skill.name}
                        </span>
                        {skill.readonly && (
                          <Lock className="size-3 text-slate-500" />
                        )}
                      </div>
                      <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-slate-400">
                        {skill.description}
                      </p>
                    </div>
                    <div className="flex items-center lg:block">
                      <Badge
                        className="font-mono text-[9px]"
                        variant={
                          skill.source === "backend" ? "muted" : "default"
                        }
                      >
                        {skill.source === "backend" ? "后端注册" : "自定义"}
                      </Badge>
                    </div>
                    <div className="flex items-center font-mono text-[10px] text-slate-400">
                      {skill.version}
                    </div>
                    <div className="flex items-center">
                      <Badge
                        className="font-mono text-[9px]"
                        variant={skill.enabled ? "success" : "muted"}
                      >
                        {skill.enabled ? "启用" : "停用"}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-slate-500">
                      <Activity className="size-3.5 text-cyan-300/75" />
                      <div>
                        <div className="font-mono text-slate-300">
                          {skill.usageCount} 次
                        </div>
                        <div>{formatRelativeDate(skill.lastUsedAt)}</div>
                      </div>
                    </div>
                    <button
                      className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-800 hover:text-cyan-200"
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedSkillId(skill.id);
                        setDetailPanel("activity");
                      }}
                      title="打开操作菜单"
                      type="button"
                    >
                      <MoreHorizontal className="size-4" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-700/70 bg-[#07111d]">
          <div className="flex min-h-0 flex-1 flex-col p-4">
            {selectedSkill ? (
              <>
                <div className="border-b border-slate-700/70 pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="break-all font-mono text-sm font-semibold text-cyan-50">
                          {selectedSkill.name}
                        </h3>
                        <Badge
                          className="font-mono text-[9px]"
                          variant={selectedSkill.enabled ? "success" : "muted"}
                        >
                          {selectedSkill.enabled ? "已启用" : "已停用"}
                        </Badge>
                        {selectedSkill.readonly && (
                          <Badge
                            className="font-mono text-[9px]"
                            variant="muted"
                          >
                            只读
                          </Badge>
                        )}
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-slate-400">
                        {selectedSkill.description}
                      </p>
                    </div>
                    <label
                      className={cn(
                        "relative inline-flex shrink-0 items-center",
                        selectedSkill.readonly
                          ? "cursor-not-allowed opacity-45"
                          : "cursor-pointer"
                      )}
                      title={
                        selectedSkill.readonly
                          ? "后端注册技能只读，不能在前端停用"
                          : "切换自定义技能启用状态"
                      }
                    >
                      <input
                        checked={selectedSkill.enabled}
                        className="peer sr-only"
                        disabled={selectedSkill.readonly}
                        onChange={(event) => {
                          if (selectedSkill.rawCustomId) {
                            onToggleCustomSkill(
                              selectedSkill.rawCustomId,
                              event.target.checked
                            );
                          }
                        }}
                        type="checkbox"
                      />
                      <div className="peer h-5 w-9 rounded-full bg-slate-800 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-slate-300 after:transition-all after:content-[''] peer-checked:bg-cyan-500 peer-checked:after:translate-x-full peer-checked:after:bg-white peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-400/60" />
                    </label>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                    <div className="rounded-md border border-slate-700/60 bg-slate-950/40 p-2">
                      <div className="flex items-center gap-1.5 text-slate-500">
                        <Database className="size-3.5" />
                        来源
                      </div>
                      <div className="mt-1 font-mono text-slate-200">
                        {selectedSkill.source === "backend"
                          ? "后端注册"
                          : "文件夹自定义"}
                      </div>
                    </div>
                    <div className="rounded-md border border-slate-700/60 bg-slate-950/40 p-2">
                      <div className="flex items-center gap-1.5 text-slate-500">
                        <Zap className="size-3.5" />
                        版本
                      </div>
                      <div className="mt-1 font-mono text-slate-200">
                        {selectedSkill.version}
                      </div>
                    </div>
                    <div className="rounded-md border border-slate-700/60 bg-slate-950/40 p-2">
                      <div className="flex items-center gap-1.5 text-slate-500">
                        <User className="size-3.5" />
                        创建者
                      </div>
                      <div className="mt-1 font-mono text-slate-200">
                        {selectedSkill.createdBy}
                      </div>
                    </div>
                    <div className="rounded-md border border-slate-700/60 bg-slate-950/40 p-2">
                      <div className="flex items-center gap-1.5 text-slate-500">
                        <CalendarClock className="size-3.5" />
                        更新时间
                      </div>
                      <div className="mt-1 font-mono text-slate-200">
                        {formatExactDate(selectedSkill.updatedAt)}
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <Button
                      className="justify-start font-mono text-[11px]"
                      onClick={() => setDetailPanel("activity")}
                      size="sm"
                      variant="tactical"
                    >
                      <PlayCircle className="size-3.5" />
                      测试技能
                    </Button>
                    <Button
                      className="justify-start font-mono text-[11px]"
                      onClick={() => setDetailPanel("activity")}
                      size="sm"
                      variant="ghost"
                    >
                      <ScrollText className="size-3.5" />
                      查看日志
                    </Button>
                    <Button
                      className="justify-start font-mono text-[11px]"
                      disabled={selectedSkill.readonly}
                      onClick={handleEditSelectedSkill}
                      size="sm"
                      variant="ghost"
                    >
                      <Pencil className="size-3.5" />
                      编辑
                    </Button>
                    <Button
                      className="justify-start font-mono text-[11px]"
                      disabled={
                        selectedSkill.readonly || !selectedSkill.rawCustomId
                      }
                      onClick={() => {
                        if (selectedSkill.rawCustomId) {
                          onToggleCustomSkill(
                            selectedSkill.rawCustomId,
                            !selectedSkill.enabled
                          );
                        }
                      }}
                      size="sm"
                      variant={selectedSkill.enabled ? "ghost" : "tactical"}
                    >
                      <Power className="size-3.5" />
                      {selectedSkill.enabled ? "停用" : "启用"}
                    </Button>
                    <Button
                      className="justify-start font-mono text-[11px] text-red-200 hover:text-red-100"
                      disabled={
                        selectedSkill.readonly || !selectedSkill.rawCustomId
                      }
                      onClick={() => {
                        if (selectedSkill.rawCustomId) {
                          onRemoveCustomSkill(selectedSkill.rawCustomId);
                        }
                      }}
                      size="sm"
                      variant="ghost"
                    >
                      <Trash2 className="size-3.5" />
                      删除
                    </Button>
                  </div>
                </div>

                <div className="mt-3 flex gap-1 rounded-md border border-slate-700/60 bg-slate-950/40 p-1">
                  {[
                    { id: "schema", label: "输入 Schema", icon: Code2 },
                    { id: "output", label: "输出 Schema", icon: FileText },
                    { id: "activity", label: "调用记录", icon: History },
                  ].map((tab) => {
                    const Icon = tab.icon;
                    const active = detailPanel === tab.id;
                    return (
                      <button
                        className={cn(
                          "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 font-mono text-[10px] transition-colors",
                          active
                            ? "bg-cyan-400/12 text-cyan-100"
                            : "text-slate-500 hover:bg-slate-800/80 hover:text-slate-200"
                        )}
                        key={tab.id}
                        onClick={() =>
                          setDetailPanel(tab.id as SkillDetailPanel)
                        }
                        type="button"
                      >
                        <Icon className="size-3.5" />
                        {tab.label}
                      </button>
                    );
                  })}
                </div>

                <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-700/60 bg-black/20 p-3 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
                  {detailPanel === "schema" && (
                    <SkillSchemaList
                      emptyText="该技能未声明输入参数 Schema"
                      fields={selectedSkill.inputSchema}
                    />
                  )}
                  {detailPanel === "output" && (
                    <SkillSchemaList
                      emptyText="该技能未声明输出结果 Schema"
                      fields={selectedSkill.outputSchema}
                    />
                  )}
                  {detailPanel === "activity" && (
                    <div className="space-y-2">
                      {selectedSkill.callRecords.length === 0 ? (
                        <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-slate-700/70 bg-black/20 text-[11px] text-slate-500">
                          暂无调用记录
                        </div>
                      ) : (
                        selectedSkill.callRecords.map((record) => (
                          <div
                            className="rounded-md border border-slate-700/60 bg-slate-950/40 px-3 py-2"
                            key={record.id}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex min-w-0 items-center gap-2">
                                <Terminal className="size-3.5 shrink-0 text-cyan-300/80" />
                                <span className="truncate font-mono text-[10px] text-slate-200">
                                  {record.input}
                                </span>
                              </div>
                              <Badge
                                className="shrink-0 font-mono text-[9px]"
                                variant={
                                  record.status === "success"
                                    ? "success"
                                    : "warning"
                                }
                              >
                                {record.status === "success" ? "成功" : "告警"}
                              </Badge>
                            </div>
                            <div className="mt-1 flex items-center justify-between font-mono text-[9px] text-slate-500">
                              <span>{formatExactDate(record.at)}</span>
                              <span>{record.latencyMs}ms</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <Search className="mb-3 size-6 text-cyan-600/50" />
                <div className="font-mono text-xs text-cyan-500/70">
                  选择一个技能查看详情
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function SystemConfigSection({
  mapBaseLayer,
  onClearMessages,
  onMapBaseLayerChange,
}: TacticalSettingsProps) {
  const activeBaseLayer =
    BASE_LAYER_OPTIONS.find((option) => option.id === mapBaseLayer) ??
    BASE_LAYER_OPTIONS[0];

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div>
        <h2 className="font-mono text-lg text-cyan-50">战术系统操作</h2>
        <p className="mt-1 text-xs text-slate-400">
          管理当前战术会话的运行偏好、记忆清理与高风险操作。
        </p>
      </div>

      <div className="rounded-xl border border-cyan-400/15 bg-cyan-950/10 p-6">
        <h3 className="flex items-center gap-2 font-mono text-sm font-bold text-cyan-100">
          <Globe className="size-4 text-cyan-300" /> 战术底图
        </h3>
        <p className="mt-2 text-xs text-slate-400">
          当前底图：{activeBaseLayer.label}
          。可根据任务阶段切换暗色、矢量或卫星影像。
        </p>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {BASE_LAYER_OPTIONS.map((option) => {
            const selected = option.id === mapBaseLayer;
            return (
              <button
                aria-label={`切换底图为${option.label}`}
                aria-pressed={selected}
                className={cn(
                  "rounded-lg border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                  selected
                    ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-100 shadow-[0_0_16px_rgba(34,211,238,0.12)]"
                    : "border-white/10 bg-black/20 text-slate-300 hover:border-cyan-400/30 hover:bg-cyan-400/5"
                )}
                key={option.id}
                onClick={() => onMapBaseLayerChange(option.id)}
                title={`切换底图为${option.label}`}
                type="button"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs font-bold">
                    {option.label}
                  </span>
                  {selected && (
                    <CheckCircle2 className="size-4 text-cyan-300" />
                  )}
                </div>
                <div className="mt-1 text-[10px] leading-relaxed text-slate-500">
                  {option.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="rounded-xl border border-red-500/20 bg-red-950/10 p-6">
        <h3 className="flex items-center gap-2 font-mono text-sm font-bold text-red-400">
          <AlertTriangle className="size-4" /> 危险操作区
        </h3>
        <p className="mt-2 text-xs text-slate-400">
          以下操作会影响当前战术会话，执行前请确认影响范围。
        </p>

        <div className="mt-6 flex items-center justify-between rounded-lg border border-red-500/10 bg-black/20 p-4">
          <div>
            <div className="font-mono text-xs font-bold text-slate-200">
              清空 AI 会话记忆
            </div>
            <div className="mt-1 text-[10px] text-slate-500">
              清空当前想定的聊天历史与本地 AI 上下文；此操作不可恢复。
            </div>
          </div>
          <Button
            onClick={() => {
              if (
                window.confirm(
                  "确认清空当前想定的 AI 聊天历史和本地上下文？此操作不可恢复。"
                )
              ) {
                onClearMessages();
              }
            }}
            variant="ghost"
            className="border border-red-500/30 text-red-400 hover:bg-red-500/20 hover:text-red-200"
          >
            <Trash2 className="size-4 mr-2" /> 清空
          </Button>
        </div>
      </div>
    </div>
  );
}
