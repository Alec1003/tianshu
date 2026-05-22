import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  BrainCircuit,
  Cpu,
  Globe,
  Loader2,
  Plug,
  RefreshCw,
  Settings,
  Shield,
  Trash2,
  Wrench,
  X,
  Server,
  Activity,
  CheckCircle2,
  AlertCircle,
  KeyRound,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { CesiumBaseLayerKey } from "@/gui/map/CesiumToolbar";
import type { TacticalSettingsProps, ModelConfig } from "./AISidebar";

const SETTINGS_TABS = [
  {
    id: "model",
    label: "模型中枢",
    icon: BrainCircuit,
    desc: "配置战术推理模型与连通性",
  },
  {
    id: "mcp",
    label: "MCP 管理",
    icon: Plug,
    desc: "接入工具服务器与工作区能力",
  },
  {
    id: "skills",
    label: "技能阵列",
    icon: Wrench,
    desc: "管理后端技能与自定义提示词",
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

const MODEL_PROVIDER_OPTIONS = [
  "openai",
  "anthropic",
  "google",
  "ollama",
  "deepseek",
];

const INPUT_CLASS =
  "w-full rounded-md border border-cyan-400/20 bg-cyan-950/20 px-3 py-1.5 font-mono text-[11px] text-cyan-50 placeholder:text-cyan-600/30 focus:border-cyan-400/50 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all";
const SELECT_CLASS =
  "w-full rounded-md border border-cyan-400/20 bg-cyan-950/20 px-3 py-1.5 font-mono text-[11px] text-cyan-50 focus:border-cyan-400/50 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all";

const BASE_LAYER_OPTIONS: Array<{
  id: CesiumBaseLayerKey;
  label: string;
  desc: string;
}> = [
  { id: "darkMatter", label: "战术暗色", desc: "夜间态势与高对比目标显示" },
  { id: "lightVector", label: "标准矢量", desc: "中文道路、地名与行政标注" },
  { id: "satellite", label: "卫星影像", desc: "高德卫星遥感底图" },
  { id: "sentinel", label: "哨兵真彩", desc: "Sentinel-2 全球真彩影像" },
];

export default function TacticalSettingsModal(
  props: TacticalSettingsModalProps
) {
  const { open, onOpenChange } = props;
  const [activeTab, setActiveTab] = useState<SettingsTabId>("model");

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
            className="relative flex h-[80vh] w-[90vw] max-w-5xl overflow-hidden rounded-xl border border-cyan-400/30 bg-[#030914] shadow-[0_0_50px_rgba(8,145,178,0.15)] ring-1 ring-white/5"
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

              <div className="flex-1 overflow-y-auto p-8 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
                {activeTab === "model" && <ModelConfigSection {...props} />}
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

function ModelConfigSection({
  modelConfig,
  modelPresetOptions,
  selectedPreset,
  modelCheckResult,
  checkingModel,
  onModelConfigChange,
  onCheckModel,
}: TacticalSettingsProps) {
  const update = (patch: Partial<ModelConfig>) =>
    onModelConfigChange({ ...modelConfig, ...patch });

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div>
        <h2 className="font-mono text-lg text-cyan-50">AI 模型中枢</h2>
        <p className="mt-1 text-xs text-slate-400">
          配置驱动战术辅助、命令解释与推演建议的主力大模型。
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-4 rounded-xl border border-cyan-400/10 bg-cyan-950/5 p-5 shadow-inner">
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] uppercase text-cyan-500">
              服务商
            </label>
            <select
              className={SELECT_CLASS}
              onChange={(e) => update({ provider: e.target.value })}
              value={modelConfig.provider}
            >
              {MODEL_PROVIDER_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="font-mono text-[10px] uppercase text-cyan-500">
              预设模型
            </label>
            <select
              className={SELECT_CLASS}
              onChange={(e) => {
                if (e.target.value !== "__custom__") {
                  update({ model: e.target.value });
                }
              }}
              value={selectedPreset}
            >
              <option value="__custom__">自定义</option>
              {modelPresetOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="font-mono text-[10px] uppercase text-cyan-500">
              模型 ID
            </label>
            <input
              className={INPUT_CLASS}
              onChange={(e) => update({ model: e.target.value })}
              placeholder="例如 gpt-4o-mini"
              value={modelConfig.model}
            />
          </div>
        </div>

        <div className="space-y-4 rounded-xl border border-cyan-400/10 bg-cyan-950/5 p-5 shadow-inner">
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] uppercase text-cyan-500">
              Base URL 覆盖
            </label>
            <input
              className={INPUT_CLASS}
              onChange={(e) => update({ baseUrl: e.target.value })}
              placeholder="https://api.openai.com/v1"
              value={modelConfig.baseUrl}
            />
            <p className="text-[9px] text-slate-500">
              留空时使用后端或服务商默认地址
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="font-mono text-[10px] uppercase text-cyan-500">
              API 密钥
            </label>
            <div className="relative">
              <KeyRound className="absolute left-2.5 top-1/2 size-3 -translate-y-1/2 text-cyan-600" />
              <input
                className={cn(INPUT_CLASS, "pl-8")}
                onChange={(e) => update({ apiKey: e.target.value })}
                placeholder="sk-..."
                type="password"
                value={modelConfig.apiKey}
              />
            </div>
          </div>

          <div className="pt-2">
            <Button
              className="w-full gap-2 border border-cyan-400/30 bg-cyan-950/40 text-cyan-300 hover:bg-cyan-400/20"
              disabled={checkingModel}
              onClick={onCheckModel}
              variant="ghost"
            >
              {checkingModel ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Activity className="size-4" />
              )}
              {checkingModel ? "正在验证连接..." : "测试模型连接"}
            </Button>
          </div>
        </div>
      </div>

      {modelCheckResult && (
        <div
          className={cn(
            "rounded-lg border p-4 backdrop-blur-sm",
            modelCheckResult.status === "ok"
              ? "border-emerald-400/30 bg-emerald-950/20 text-emerald-100"
              : modelCheckResult.status === "partial"
                ? "border-amber-400/30 bg-amber-950/20 text-amber-100"
                : "border-red-400/30 bg-red-950/20 text-red-100"
          )}
        >
          <div className="flex items-center gap-2 font-mono text-sm font-bold">
            {modelCheckResult.status === "ok" ? (
              <CheckCircle2 className="size-4 text-emerald-400" />
            ) : modelCheckResult.status === "partial" ? (
              <AlertCircle className="size-4 text-amber-400" />
            ) : (
              <XCircle className="size-4 text-red-400" />
            )}
            {modelCheckResult.status === "ok"
              ? "连接已建立"
              : modelCheckResult.status === "partial"
                ? "连接部分可用"
                : "连接异常"}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-4 font-mono text-xs opacity-80">
            <div>
              <span className="block text-[9px] text-slate-400">端点</span>
              {modelCheckResult.endpoint || "未返回"}
            </div>
            <div>
              <span className="block text-[9px] text-slate-400">鉴权状态</span>
              {modelCheckResult.auth_ok ? "已验证" : "失败"}
            </div>
            <div>
              <span className="block text-[9px] text-slate-400">模型查询</span>
              {modelCheckResult.models_listed ? "已验证" : "失败"}
            </div>
          </div>
          {modelCheckResult.error && (
            <div className="mt-3 rounded border border-red-500/20 bg-red-950/30 p-2 font-mono text-[10px] text-red-300">
              {modelCheckResult.error}
            </div>
          )}
        </div>
      )}

      <div className="rounded-lg border border-cyan-400/10 bg-cyan-950/10 p-3 font-mono text-[10px] text-cyan-400/60 flex items-start gap-2">
        <Globe className="size-3.5 mt-0.5 shrink-0" />
        <p>
          模型配置会通过 X-AICC-Model-*
          请求头传入后端运行时；留空字段会回退到后端环境变量默认值。
        </p>
      </div>
    </div>
  );
}

function McpSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border-b border-cyan-400/10 pb-2">
        <h3 className="font-mono text-[11px] font-bold uppercase tracking-widest text-slate-300">
          {title}
        </h3>
        <Badge className="bg-cyan-950 border-cyan-400/20 text-[9px] text-cyan-300 font-mono">
          {count} 个启用
        </Badge>
      </div>
      {children}
    </div>
  );
}

function McpConfigSection({
  mcpServers,
  activeMcpServersCount,
  projectMcpEnabled,
  newServerName,
  newServerEndpoint,
  newServerTransport,
  onProjectMcpEnabledChange,
  onAddServer,
  onRemoveServer,
  onToggleServer,
  onNewServerNameChange,
  onNewServerEndpointChange,
  onNewServerTransportChange,
}: TacticalSettingsProps) {
  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div>
        <h2 className="font-mono text-lg text-cyan-50">MCP 工具节点阵列</h2>
        <p className="mt-1 text-xs text-slate-400">
          管理 MCP 工具桥接，让 AI 能调用工作区、外部服务与战术工具能力。
        </p>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-cyan-400/10 bg-cyan-950/5 p-4 shadow-inner">
        <div>
          <div className="font-mono text-xs font-bold text-slate-200">
            项目内置 MCP
          </div>
          <div className="mt-1 text-[10px] text-slate-500">
            启用本地工作区读取、检索与项目辅助能力
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "font-mono text-[10px] uppercase",
              projectMcpEnabled ? "text-emerald-400" : "text-slate-500"
            )}
          >
            {projectMcpEnabled ? "在线" : "离线"}
          </span>
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              className="peer sr-only"
              checked={projectMcpEnabled}
              onChange={(e) => onProjectMcpEnabledChange(e.target.checked)}
            />
            <div className="peer h-5 w-9 rounded-full bg-slate-800 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-slate-300 after:transition-all after:content-[''] peer-checked:bg-cyan-500 peer-checked:after:translate-x-full peer-checked:after:bg-white peer-focus:outline-none"></div>
          </label>
        </div>
      </div>

      <McpSection title="外部 MCP 节点" count={activeMcpServersCount}>
        <div className="space-y-3">
          {mcpServers.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-cyan-400/20 bg-cyan-950/5 font-mono text-[10px] text-cyan-600/50">
              尚未接入外部节点
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {mcpServers.map((server) => (
                <div
                  className={cn(
                    "group relative overflow-hidden rounded-lg border p-3 transition-colors",
                    server.enabled
                      ? "border-cyan-400/30 bg-cyan-950/20"
                      : "border-white/5 bg-white/[0.02]"
                  )}
                  key={server.id}
                >
                  {server.enabled && (
                    <div className="absolute inset-0 bg-gradient-to-r from-cyan-400/0 via-cyan-400/5 to-cyan-400/0 opacity-0 transition-opacity duration-1000 group-hover:opacity-100 group-hover:animate-pulse" />
                  )}
                  <div className="relative flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "font-mono text-xs font-bold",
                            server.enabled ? "text-cyan-100" : "text-slate-400"
                          )}
                        >
                          {server.name}
                        </span>
                        <span className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[9px] uppercase text-cyan-300">
                          {server.transport}
                        </span>
                      </div>
                      <div className="mt-1 truncate font-mono text-[10px] text-slate-500">
                        {server.endpoint}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="relative inline-flex cursor-pointer items-center">
                        <input
                          type="checkbox"
                          className="peer sr-only"
                          checked={server.enabled}
                          onChange={(e) =>
                            onToggleServer(server.id, e.target.checked)
                          }
                        />
                        <div className="peer h-4 w-7 rounded-full bg-slate-800 after:absolute after:left-[2px] after:top-[2px] after:h-3 after:w-3 after:rounded-full after:bg-slate-300 after:transition-all after:content-[''] peer-checked:bg-cyan-500 peer-checked:after:translate-x-full peer-checked:after:bg-white peer-focus:outline-none"></div>
                      </label>
                      <button
                        className="rounded p-1 text-slate-500 hover:bg-red-500/20 hover:text-red-400 transition-colors"
                        onClick={() => onRemoveServer(server.id)}
                        title="移除 MCP 节点"
                        type="button"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </McpSection>

      <div className="rounded-xl border border-cyan-400/10 bg-cyan-950/5 p-5 shadow-inner">
        <h3 className="mb-4 font-mono text-[11px] font-bold uppercase tracking-widest text-slate-300">
          添加 MCP 节点
        </h3>
        <div className="grid gap-4 md:grid-cols-[1fr_2fr_100px_auto]">
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewServerNameChange(e.target.value)}
            placeholder="节点名称，例如 weather"
            value={newServerName}
          />
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewServerEndpointChange(e.target.value)}
            placeholder="端点地址或启动命令"
            value={newServerEndpoint}
          />
          <select
            className={SELECT_CLASS}
            onChange={(e) =>
              onNewServerTransportChange(
                e.target.value as "stdio" | "sse" | "http"
              )
            }
            value={newServerTransport}
          >
            <option value="stdio">STDIO</option>
            <option value="sse">SSE</option>
            <option value="http">HTTP</option>
          </select>
          <Button
            className="w-full font-mono font-bold tracking-wider"
            onClick={onAddServer}
            disabled={!newServerName || !newServerEndpoint}
            variant="tactical"
          >
            接入
          </Button>
        </div>
      </div>
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
  onNewSkillNameChange,
  onNewSkillDescriptionChange,
}: TacticalSettingsProps) {
  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-mono text-lg text-cyan-50">技能阵列管理</h2>
          <p className="mt-1 text-xs text-slate-400">
            同步后端注册技能，并管理本地自定义提示词与战术行为。
          </p>
        </div>
        <Button
          onClick={onRefreshSkills}
          disabled={skillsLoading}
          variant="ghost"
          className="gap-2 border border-cyan-400/30 text-cyan-300 font-mono text-xs"
        >
          <RefreshCw
            className={cn("size-3.5", skillsLoading && "animate-spin")}
          />
          同步后端
        </Button>
      </div>

      {skillsError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 font-mono text-xs text-red-200">
          <AlertCircle className="inline size-4 mr-2 -mt-0.5" />
          同步失败：{skillsError}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Backend Skills */}
        <div className="space-y-4">
          <McpSection title="后端注册技能" count={registeredSkills.length}>
            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
              {registeredSkills.length === 0 ? (
                <div className="flex h-20 items-center justify-center rounded-lg border border-dashed border-cyan-400/20 bg-cyan-950/5 font-mono text-[10px] text-cyan-600/50">
                  {skillsLoading ? "正在同步..." : "未发现后端技能"}
                </div>
              ) : (
                registeredSkills.map((skill) => (
                  <div
                    key={skill.name}
                    className="rounded-lg border border-white/5 bg-white/[0.02] p-3 transition-colors hover:border-cyan-400/20 hover:bg-cyan-950/20"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-slate-200">
                        {skill.name}
                      </span>
                      <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[9px] text-emerald-400">
                        只读
                      </span>
                    </div>
                    <p className="mt-1.5 text-[10px] text-slate-400 leading-relaxed line-clamp-2">
                      {skill.description}
                    </p>
                  </div>
                ))
              )}
            </div>
          </McpSection>
        </div>

        {/* Custom Skills */}
        <div className="space-y-4">
          <McpSection title="自定义技能注入" count={activeCustomSkillsCount}>
            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
              {customSkills.length === 0 ? (
                <div className="flex h-20 items-center justify-center rounded-lg border border-dashed border-cyan-400/20 bg-cyan-950/5 font-mono text-[10px] text-cyan-600/50">
                  暂无自定义技能
                </div>
              ) : (
                customSkills.map((skill) => (
                  <div
                    key={skill.id}
                    className={cn(
                      "rounded-lg border p-3 transition-colors",
                      skill.enabled
                        ? "border-cyan-400/30 bg-cyan-950/20 shadow-[0_0_15px_rgba(34,211,238,0.05)]"
                        : "border-white/5 bg-white/[0.02]"
                    )}
                  >
                    <div className="flex flex-col gap-2">
                      <div className="flex items-start justify-between gap-2">
                        <span
                          className={cn(
                            "font-mono text-xs font-bold break-all",
                            skill.enabled ? "text-cyan-100" : "text-slate-400"
                          )}
                        >
                          {skill.name}
                        </span>
                        <div className="flex shrink-0 items-center gap-2">
                          <label className="relative inline-flex cursor-pointer items-center">
                            <input
                              type="checkbox"
                              className="peer sr-only"
                              checked={skill.enabled}
                              onChange={(e) =>
                                onToggleCustomSkill(skill.id, e.target.checked)
                              }
                            />
                            <div className="peer h-4 w-7 rounded-full bg-slate-800 after:absolute after:left-[2px] after:top-[2px] after:h-3 after:w-3 after:rounded-full after:bg-slate-300 after:transition-all after:content-[''] peer-checked:bg-cyan-500 peer-checked:after:translate-x-full peer-checked:after:bg-white peer-focus:outline-none"></div>
                          </label>
                          <button
                            className="rounded p-1 text-slate-500 hover:bg-red-500/20 hover:text-red-400 transition-colors"
                            onClick={() => onRemoveCustomSkill(skill.id)}
                            title="移除自定义技能"
                            type="button"
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-relaxed whitespace-pre-wrap font-mono bg-black/20 p-2 rounded">
                        {skill.description}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </McpSection>
        </div>
      </div>

      <div className="rounded-xl border border-cyan-400/10 bg-cyan-950/5 p-5 shadow-inner">
        <h3 className="mb-4 font-mono text-[11px] font-bold uppercase tracking-widest text-slate-300">
          注入自定义技能提示词
        </h3>
        <div className="space-y-4">
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewSkillNameChange(e.target.value)}
            placeholder="技能触发 ID，例如 format_response"
            value={newSkillName}
          />
          <textarea
            className={cn(INPUT_CLASS, "min-h-[80px] resize-y")}
            onChange={(e) => onNewSkillDescriptionChange(e.target.value)}
            placeholder="描述系统提示词或需要注入的 AI 行为..."
            value={newSkillDescription}
          />
          <div className="flex justify-end">
            <Button
              className="font-mono font-bold tracking-wider w-32"
              onClick={onAddSkill}
              disabled={!newSkillName || !newSkillDescription}
              variant="tactical"
            >
              注入
            </Button>
          </div>
        </div>
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
