/**
 * AI Sidebar：右侧栏，支持「聊天 / 设置」两个 tab。
 *
 * 设计要点：
 * - 聊天：用 @ai-sdk/react `useChat` + ai-sdk v5 `DefaultChatTransport`
 *   接 POST /api/ai/chat 流式接口（SSE / UI message stream）。
 *   加密时用户填写的 model 配置通过 X-AICC-Model-* header
 *   传到后端，后端 per-request 构造 pydantic-ai agent，让前端
 *   model 配置在流式路径上也真生效。流结束后拉
 *   /api/ai/runtime/scenario 刷新地图。
 * - 设置：MCP Servers（增删改 + enable toggle）/ Skills（后端已注册 + 用户
 *   自定义）/ 系统操作三段。模型配置已拆到独立 AI 模型配置中心。
 * - 持久化：modelConfig / mcpServers / projectMcpEnabled
 *   使用 aicc.ai.* keys；customSkills 改由后端 skills folder 存储；chat 消息由于类型从
 *   ChatMessage 迁移到 UIMessage，另存为 aicc.ai.messages.v2。
 * - 主题：cyan/slate tactical，复用 shadcn Card/Button，TailwindCSS。
 *
 * Props 由 AITacticalCommandPlatform 控制：open / activeTab /
 * onOpenChange / onTabChange / onApplyScenario(刷新 game)。
 */
import {
  type CSSProperties,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  MessageSquare,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Wrench,
  X,
} from "lucide-react";
import { useChat } from "@ai-sdk/react";
import {
  DefaultChatTransport,
  isReasoningUIPart,
  isTextUIPart,
  isToolOrDynamicToolUIPart,
  type UIMessage,
} from "ai";

import {
  approveCommandProposal,
  createCustomSkill,
  deleteCustomSkill,
  getRuntimeScenario,
  listBackendSkills,
  listCommandProposals,
  listCustomSkills,
  rejectCommandProposal,
  updateCustomSkill,
} from "@/api/ai";
import {
  getScenarioCompareSession,
  simulateScenarioCompareSession,
} from "@/api/scenarios";
import { Button } from "@/components/ui/button";
import type {
  CommandProposal,
  CustomSkill,
  CustomSkillCreatePayload,
  CustomSkillUpdatePayload,
  RegisteredSkill,
  SkillSchemaField,
  ScenarioBatchSimulationResponse,
  ScenarioCompareSession,
  ScenarioPlanOption,
} from "@/api/types";
import type { CesiumBaseLayerKey } from "@/gui/map/CesiumMapTypes";
import { cn } from "@/lib/utils";
import { apiCall, getStoredToken } from "@/api/client";
import {
  MODEL_PRESETS,
  MODEL_STORAGE_KEY,
  modelProfileLabel,
  profileToConfig,
  sameModelConfig,
  type ModelConfig,
  type ModelProfile,
} from "@/features/ai/modelProfiles";
import ModelSwitcher from "@/features/ai/ModelSwitcher";
import { useModelConfigStore } from "@/features/ai/modelStore";
import ScenarioCompareDialog from "@/features/scenarios/ScenarioCompareDialog";
import TacticalSettingsModal from "./TacticalSettingsModal";

export type AISidebarTab = "chat" | "settings";
type AIChatMode = "ask" | "command";

interface MCPServerConfig {
  id: string;
  name: string;
  endpoint: string;
  transport: "stdio" | "sse" | "http";
  enabled: boolean;
}

type CustomSkillConfig = CustomSkill;

export interface AddCustomSkillOptions {
  description?: string;
  prompt?: string;
  inputSchema?: SkillSchemaField[];
  outputSchema?: SkillSchemaField[];
  enabled?: boolean;
}

export interface UpdateCustomSkillOptions {
  name?: string;
  description?: string;
  prompt?: string;
  inputSchema?: SkillSchemaField[];
  outputSchema?: SkillSchemaField[];
  enabled?: boolean;
}

export interface ModelCheckResponse {
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

interface ToolRunSnapshot {
  toolName: string;
  state: string;
}

interface ChatRunSummary {
  label: string;
  detail: string;
  tone: "idle" | "running" | "done" | "error";
  tools: ToolRunSnapshot[];
}

interface PlanSetToolOutput {
  ok: boolean;
  kind: "plan_set";
  compareSession: ScenarioCompareSession;
  sourceScenarioId: string;
  sourceScenarioName: string;
  branchCount: number;
  plans: ScenarioPlanOption[];
}

interface PlanSimulationToolOutput {
  ok: boolean;
  kind: "plan_simulation_batch";
  compareSession: ScenarioCompareSession;
  steps: number;
  includeBaseline: boolean;
  simulatedAt: string;
  results: ScenarioBatchSimulationResponse["results"];
  recommendedScenarioId: string | null;
  recommendedReason: string;
}

interface AISidebarProps {
  open: boolean;
  activeTab: AISidebarTab;
  onOpenChange: (open: boolean) => void;
  onTabChange: (tab: AISidebarTab) => void;
  settingsOpen?: boolean;
  onSettingsOpenChange?: (open: boolean) => void;
  /** AI command 返回的 scenario JSON 应用回 game。 */
  onApplyScenario?: (scenario: Record<string, unknown>) => void;
  /**
   * AI 调用 ``simulation_start`` 时触发的回调（等价于 UI 上的 Play 按钮）。
   * 后续仿真在客户端自动循环 step，直到 ``simulation_pause`` /
   * ``simulation_stop`` 或者用户手动暂停。``simulation_step(N)`` 不会触发
   * 此回调（视为单次推演 N 步即停）。
   */
  onResumePlay?: () => void | Promise<void>;
  mapBaseLayer: CesiumBaseLayerKey;
  onMapBaseLayerChange: (key: CesiumBaseLayerKey) => void;
  /**
   * 当前 scenario id，用作 chat 历史的 localStorage 命名空间。
   * 切换/重置/导入新 scenario 时变化，自动切换该 scenario 的会话。
   * 可选：未提供时降级为单一全局会话。
   */
  scenarioId?: string;
  panelClassName?: string;
  panelStyle?: CSSProperties;
}

const STORAGE_KEY = {
  messagesV2: "aicc.ai.messages.v2",
  mcpServers: "aicc.ai.mcpServers",
  customSkills: "aicc.ai.customSkills",
  model: MODEL_STORAGE_KEY.model,
  modelProfiles: MODEL_STORAGE_KEY.modelProfiles,
  activeModelProfileId: MODEL_STORAGE_KEY.activeModelProfileId,
  projectMcpEnabled: "aicc.ai.projectMcpEnabled",
} as const;

const DEFAULT_MCP_SERVERS: MCPServerConfig[] = [
  {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `mcp-${Date.now()}`,
    name: "天枢 MCP",
    endpoint: "stdio://local-aicc-mcp",
    transport: "stdio",
    enabled: true,
  },
];

const QUICK_COMMANDS: string[] = [
  "开始推演并运行 3 步",
  "在 22.1, 121.5 部署一架蓝方 F-16",
  "暂停推演并查看战况",
];
const LEGACY_ASK_MODE_GUARD =
  "Ask mode: answer, analyze, or plan only. Do not execute scenario-changing tools.";

function stripLegacyModeGuard(text: string): string {
  return text
    .split(LEGACY_ASK_MODE_GUARD)
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function sanitizeLegacyModeGuards(messages: UIMessage[]): UIMessage[] {
  let changed = false;
  const sanitized = messages.map((message) => {
    const parts = message.parts.map((part) => {
      if (!isTextUIPart(part)) return part;
      const nextText = stripLegacyModeGuard(part.text);
      if (nextText === part.text) return part;
      changed = true;
      return { ...part, text: nextText };
    });
    return changed ? { ...message, parts } : message;
  });
  return changed ? sanitized : messages;
}

function safeLoad<T>(key: string, fallback: T): T {
  try {
    if (typeof window === "undefined") return fallback;
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function safeSave<T>(key: string, value: T): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore quota / privacy errors
  }
}

function safeRemove(key: string): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(key);
  } catch {
    // ignore privacy errors
  }
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface LegacyCustomSkillConfig {
  id?: string;
  name?: string;
  description?: string;
  prompt?: string;
  enabled?: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isScenarioCompareSession(
  value: unknown
): value is ScenarioCompareSession {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    Array.isArray(value.scenario_ids) &&
    isRecord(value.state)
  );
}

function isPlanSetToolOutput(value: unknown): value is PlanSetToolOutput {
  return (
    isRecord(value) &&
    value.kind === "plan_set" &&
    isScenarioCompareSession(value.compareSession) &&
    Array.isArray(value.plans)
  );
}

function isPlanSimulationToolOutput(
  value: unknown
): value is PlanSimulationToolOutput {
  return (
    isRecord(value) &&
    value.kind === "plan_simulation_batch" &&
    isScenarioCompareSession(value.compareSession) &&
    Array.isArray(value.results)
  );
}

/**
 * Extract a flat preview string from a UIMessage so empty assistant
 * messages can render a placeholder (“推理中…”) while the stream is
 * still warming up.
 */
function previewText(message: UIMessage): string {
  for (const part of message.parts) {
    if (isTextUIPart(part) && part.text) return part.text;
  }
  return "";
}

/**
 * Build the localStorage key for the chat history of a given scenario.
 * Falls back to a stable "__none__" namespace when no scenario is bound,
 * so an embedding without scenarioId still works (single global thread).
 */
function messagesKeyFor(scenarioId: string | undefined): string {
  return `${STORAGE_KEY.messagesV2}:${scenarioId || "__none__"}`;
}

function buildCustomSkillPrompt(skills: CustomSkillConfig[]): string {
  if (skills.length === 0) return "";
  const skillLines = skills.map((skill, index) => {
    const prompt = (skill.prompt || skill.description).trim();
    return [
      `${index + 1}. ${skill.name}`,
      skill.description ? `Description: ${skill.description}` : "",
      prompt ? `Prompt: ${prompt}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  });
  return [
    "User-enabled custom skill guidance:",
    ...skillLines,
    "Treat these as user-defined guidance, not executable backend tools. Platform safety rules and human approval still apply.",
  ].join("\n");
}

function getToolRunSnapshot(part: unknown): ToolRunSnapshot {
  const p = part as {
    type?: string;
    toolName?: string;
    state?: string;
  };
  const toolName = p.toolName
    ? p.toolName
    : typeof p.type === "string" && p.type.startsWith("tool-")
      ? p.type.slice("tool-".length)
      : "tool";
  return {
    toolName,
    state: p.state ?? "unknown",
  };
}

function formatChatError(error: Error): string {
  const message = error.message || "Unknown chat error";
  if (
    message.includes("503") ||
    message.toLowerCase().includes("service unavailable") ||
    message.includes("No LLM configured")
  ) {
    return "No LLM is configured. Fill API Key in AI 模型配置中心, or set AICC_LLM_MODEL and AICC_LLM_API_KEY in the server environment.";
  }
  return message;
}

function summarizeChatRun(
  messages: UIMessage[],
  busy: boolean,
  hasError: boolean
): ChatRunSummary {
  if (hasError) {
    return {
      label: "Run failed",
      detail: "Check the latest assistant response or model settings",
      tone: "error",
      tools: [],
    };
  }

  const lastAssistant = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");
  const tools =
    lastAssistant?.parts
      .filter((part) => isToolOrDynamicToolUIPart(part))
      .map(getToolRunSnapshot) ?? [];
  const completed = tools.filter(
    (tool) => tool.state === "output-available"
  ).length;
  const failed = tools.some((tool) => tool.state === "output-error");
  const runningTool = tools.find(
    (tool) => tool.state !== "output-available" && tool.state !== "output-error"
  );

  if (busy && tools.length > 0) {
    return {
      label: "Running tools",
      detail: `${completed}/${tools.length} tasks done${
        runningTool ? ` · ${runningTool.toolName}` : ""
      }`,
      tone: "running",
      tools,
    };
  }

  if (busy) {
    return {
      label: "Thinking",
      detail: "Waiting for assistant response",
      tone: "running",
      tools,
    };
  }

  if (tools.length > 0) {
    return {
      label: failed ? "Tasks finished with errors" : "Tasks complete",
      detail: `${completed}/${tools.length} tasks done`,
      tone: failed ? "error" : "done",
      tools,
    };
  }

  return {
    label: messages.length > 0 ? "Ready for follow-up" : "No active run",
    detail:
      messages.length > 0
        ? "Ask another question or issue a command"
        : "Start by asking about the current scenario",
    tone: "idle",
    tools,
  };
}

export default function AISidebar({
  open,
  activeTab,
  onOpenChange,
  onTabChange,
  settingsOpen = false,
  onSettingsOpenChange,
  onApplyScenario,
  onResumePlay,
  mapBaseLayer,
  onMapBaseLayerChange,
  scenarioId,
  panelClassName,
  panelStyle,
}: AISidebarProps) {
  const navigate = useNavigate();
  const modelConfig = useModelConfigStore((state) => state.activeModelConfig);
  const modelProfiles = useModelConfigStore((state) => state.modelProfiles);
  const activeModelProfileId = useModelConfigStore(
    (state) => state.activeModelProfileId
  );
  const updateActiveModelConfig = useModelConfigStore(
    (state) => state.updateActiveModelConfig
  );
  const selectModelProfile = useModelConfigStore(
    (state) => state.selectModelProfile
  );
  const saveActiveProfile = useModelConfigStore(
    (state) => state.saveActiveProfile
  );
  const createProfileFromActive = useModelConfigStore(
    (state) => state.createProfileFromActive
  );
  const deleteModelProfile = useModelConfigStore(
    (state) => state.deleteModelProfile
  );
  const markProviderChecked = useModelConfigStore(
    (state) => state.markProviderChecked
  );
  const legacyCustomSkillsRef = useRef<LegacyCustomSkillConfig[]>(
    safeLoad<LegacyCustomSkillConfig[]>(STORAGE_KEY.customSkills, [])
  );
  const customSkillMigrationAttemptedRef = useRef(false);

  // —— 持久化状态 ——
  const [mcpServers, setMcpServers] = useState<MCPServerConfig[]>(() =>
    safeLoad<MCPServerConfig[]>(STORAGE_KEY.mcpServers, DEFAULT_MCP_SERVERS)
  );
  const [customSkills, setCustomSkills] = useState<CustomSkillConfig[]>([]);
  const [projectMcpEnabled, setProjectMcpEnabled] = useState<boolean>(() =>
    safeLoad<boolean>(STORAGE_KEY.projectMcpEnabled, true)
  );

  // —— 后端注册技能 ——
  const [registeredSkills, setRegisteredSkills] = useState<RegisteredSkill[]>(
    []
  );
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);

  // —— 聊天 / 流式状态 ——
  const [commandInput, setCommandInput] = useState("");
  const [chatMode, setChatMode] = useState<AIChatMode>("command");
  const [commandProposals, setCommandProposals] = useState<CommandProposal[]>(
    []
  );
  const [proposalBusyId, setProposalBusyId] = useState<string | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [activeCompareSession, setActiveCompareSession] =
    useState<ScenarioCompareSession | null>(null);
  const [planSimulationBusyId, setPlanSimulationBusyId] = useState<
    string | null
  >(null);
  const [planSimulationResults, setPlanSimulationResults] = useState<
    Record<string, ScenarioBatchSimulationResponse>
  >({});
  const chatLogRef = useRef<HTMLDivElement | null>(null);

  // headers 函数需要读最新 modelConfig，但 transport 有状态不能重建；
  // 用 ref 告诉 headers（）去拿最新值，避免重建 transport 丢失消息。
  const modelConfigRef = useRef(modelConfig);
  useEffect(() => {
    modelConfigRef.current = modelConfig;
  }, [modelConfig]);
  const modelProviderIdRef = useRef(modelConfig.provider);
  useEffect(() => {
    const activeProfile = modelProfiles.find(
      (profile) => profile.id === activeModelProfileId
    );
    modelProviderIdRef.current =
      activeProfile?.providerId ?? modelConfig.provider;
  }, [activeModelProfileId, modelConfig.provider, modelProfiles]);
  const scenarioIdRef = useRef<string | undefined>(scenarioId);
  useEffect(() => {
    scenarioIdRef.current = scenarioId;
  }, [scenarioId]);
  const chatModeRef = useRef<AIChatMode>(chatMode);
  useEffect(() => {
    chatModeRef.current = chatMode;
  }, [chatMode]);
  const lastSubmittedModeRef = useRef<AIChatMode>("command");

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/chat",
        headers: () => {
          const m = modelConfigRef.current;
          const h: Record<string, string> = {};
          const token = getStoredToken();
          if (token) h.Authorization = `Bearer ${token}`;
          if (modelProviderIdRef.current) {
            h["X-AICC-Model-Provider-Id"] = modelProviderIdRef.current;
          }
          if (m.provider) h["X-AICC-Model-Provider"] = m.provider;
          if (m.model) h["X-AICC-Model-Name"] = m.model;
          if (m.baseUrl) h["X-AICC-Model-Base-Url"] = m.baseUrl;
          if (scenarioIdRef.current) {
            h["X-AICC-Scenario-Id"] = scenarioIdRef.current;
          }
          h["X-AICC-Chat-Mode"] = chatModeRef.current;
          return h;
        },
      }),
    []
  );

  const {
    messages,
    sendMessage,
    status,
    stop,
    error: chatError,
    setMessages,
  } = useChat({ transport });

  const busy = status === "submitted" || status === "streaming";
  const chatRunSummary = useMemo(
    () => summarizeChatRun(messages, busy, Boolean(chatError)),
    [messages, busy, chatError]
  );

  const refreshCommandProposals = useCallback(async (): Promise<void> => {
    try {
      const payload = await listCommandProposals();
      setCommandProposals(payload.proposals);
      setProposalError(null);
    } catch (error) {
      setProposalError(
        error instanceof Error ? error.message : "命令审批队列刷新失败"
      );
    }
  }, []);

  useEffect(() => {
    if (open) {
      void refreshCommandProposals();
    }
  }, [open, refreshCommandProposals]);

  // ─── 按 scenario 隔离 chat 历史 ─────────────────────────────────────────
  // 设计：localStorage key = `aicc.ai.messages.v2:<scenarioId>`。
  // 首次挂载：直接读当前 scenario 的历史 → setMessages。
  // 之后切换 scenario（id 变化）时：
  //   1) 把当前 messages 落盘到 *旧* scenario 的 key（保留它的会话）
  //   2) 从 *新* scenario 的 key 读历史 → setMessages 替换
  // 由于 useChat 的 messages 是组件内 state，setMessages 之后流式就接到
  // 新的会话上；如果当前正在流式，需要先 stop 防止把新会话污染。
  const initializedRef = useRef(false);
  const prevScenarioIdRef = useRef<string | undefined>(scenarioId);
  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      const initial = sanitizeLegacyModeGuards(
        safeLoad<UIMessage[]>(messagesKeyFor(scenarioId), [])
      );
      if (initial.length) setMessages(initial);
      prevScenarioIdRef.current = scenarioId;
      return;
    }
    const prev = prevScenarioIdRef.current;
    if (prev === scenarioId) return;
    // 切换前：把当前内存中的 messages 落盘到上一个 scenario
    safeSave(messagesKeyFor(prev), messages);
    // 流式正在进行就切，会拿到“别人家的回答”，先停掉
    if (busy) {
      try {
        stop();
      } catch {
        // ignore: stop() before any in-flight request is a no-op
      }
    }
    // 切换后：读新 scenario 的历史
    const next = sanitizeLegacyModeGuards(
      safeLoad<UIMessage[]>(messagesKeyFor(scenarioId), [])
    );
    setMessages(next);
    prevScenarioIdRef.current = scenarioId;
    // 注意：不依赖 messages，否则会无限循环；切换那一瞬间用闭包里的旧值
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId]);

  // 消息变动即贴盘到当前 scenario 的 key。流式增量频繁，未来若是
  // localStorage 性能热点再考虑 throttle。
  useEffect(() => {
    safeSave(messagesKeyFor(scenarioId), messages);
  }, [messages, scenarioId]);

  // 流结束后：
  //   1) 拉一次 runtime scenario，应用到 game（让 AI 改的单位/任务可见）。
  //   2) 扫描最后一条 assistant 消息的工具调用：如果最终生命周期工具是
  //      ``simulation_start``，等价于用户按下 Play，自动启动客户端 step
  //      循环，让仿真持续推进；``simulation_step(N)`` 视为推演 N 步即停，
  //      不触发；``simulation_pause`` / ``simulation_stop`` 自然保持暂停。
  // 只在 “busy → ready” 转换时触发一次，避免初始化 / 错误后乱拉。
  const wasBusyRef = useRef(false);
  useEffect(() => {
    if (busy) {
      wasBusyRef.current = true;
      return;
    }
    if (!wasBusyRef.current) return;
    wasBusyRef.current = false;
    if (status !== "ready") return;
    if (lastSubmittedModeRef.current !== "command") return;
    // 找最近一条 assistant 消息，扫它的 tool 调用决定推演意图。
    // ai-sdk v5 的 tool part 有两种形态：
    //   - 静态工具：``{ type: 'tool-<name>', ... }``（pydantic-ai @agent.tool 走这条）
    //   - 动态工具：``{ type: 'dynamic-tool', toolName, ... }``
    // 两种都要兼容，从 ``type`` / ``toolName`` 提取真实工具名。
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === "assistant");
    const lastLifecycleTool = (() => {
      if (!lastAssistant) return null;
      const lifecycleTools = new Set([
        "simulation_start",
        "simulation_pause",
        "simulation_stop",
        "simulation_step",
        "simulation_reset",
      ]);
      for (let i = lastAssistant.parts.length - 1; i >= 0; i -= 1) {
        const part = lastAssistant.parts[i];
        if (!isToolOrDynamicToolUIPart(part)) continue;
        const p = part as { type?: string; toolName?: string };
        const toolName = p.toolName
          ? p.toolName
          : typeof p.type === "string" && p.type.startsWith("tool-")
            ? p.type.slice("tool-".length)
            : "";
        if (lifecycleTools.has(toolName)) return toolName;
      }
      return null;
    })();
    void (async () => {
      try {
        const data = await getRuntimeScenario();
        if (data && typeof data === "object") {
          onApplyScenario?.(data);
        }
      } catch (err) {
        console.error(
          "[AICC] refresh runtime scenario after AI run failed",
          err
        );
      }
      // 等 onApplyScenario 完成（同步路径，loadScenarioFromObject 立刻生效）
      // 后再触发 play，避免在 reload 过程中开 loop 撞到 stale scenario。
      if (lastLifecycleTool === "simulation_start" && onResumePlay) {
        try {
          await onResumePlay();
        } catch (err) {
          console.error("[AICC] auto-resume play after AI start failed", err);
        }
      }
      await refreshCommandProposals();
    })();
  }, [
    busy,
    messages,
    onApplyScenario,
    onResumePlay,
    refreshCommandProposals,
    status,
  ]);

  // —— 设置表单局部状态 ——
  const [newServerName, setNewServerName] = useState("");
  const [newServerEndpoint, setNewServerEndpoint] = useState("");
  const [newServerTransport, setNewServerTransport] = useState<
    "stdio" | "sse" | "http"
  >("stdio");
  const [newSkillName, setNewSkillName] = useState("");
  const [newSkillDescription, setNewSkillDescription] = useState("");
  const [checkingModel, setCheckingModel] = useState(false);
  const [modelCheckResult, setModelCheckResult] =
    useState<ModelCheckResponse | null>(null);

  // 持久化副作用
  useEffect(() => safeSave(STORAGE_KEY.mcpServers, mcpServers), [mcpServers]);
  useEffect(
    () => safeSave(STORAGE_KEY.projectMcpEnabled, projectMcpEnabled),
    [projectMcpEnabled]
  );

  // 自动滚到底。messages 增量会频繁变化（流式），每个 tick 都
  // 刷一下即可。
  useEffect(() => {
    if (!chatLogRef.current) return;
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [messages, status, open, activeTab]);

  const activeMcpServers = useMemo(
    () => mcpServers.filter((server) => server.enabled),
    [mcpServers]
  );
  const activeCustomSkills = useMemo(
    () => customSkills.filter((skill) => skill.enabled),
    [customSkills]
  );
  const modelPresetOptions = useMemo(
    () => MODEL_PRESETS[modelConfig.provider] ?? [],
    [modelConfig.provider]
  );
  const selectedPreset = modelPresetOptions.includes(modelConfig.model)
    ? modelConfig.model
    : "__custom__";

  const activeModelProfile = useMemo(
    () => modelProfiles.find((profile) => profile.id === activeModelProfileId),
    [activeModelProfileId, modelProfiles]
  );
  const activeModelProfileDirty = activeModelProfile
    ? !sameModelConfig(profileToConfig(activeModelProfile), modelConfig)
    : true;

  const handleModelConfigChange = useCallback(
    (next: ModelConfig): void => {
      updateActiveModelConfig(next);
      setModelCheckResult(null);
    },
    [updateActiveModelConfig]
  );

  const handleModelProfileSelect = useCallback(
    (profileId: string): void => {
      selectModelProfile(profileId);
      setModelCheckResult(null);
    },
    [selectModelProfile]
  );

  const handleModelProfileSave = useCallback(
    (name: string): void => {
      saveActiveProfile(name.trim() || modelProfileLabel(modelConfig));
      setModelCheckResult(null);
    },
    [modelConfig, saveActiveProfile]
  );

  const handleModelProfileCreate = useCallback(
    (name: string): void => {
      createProfileFromActive(name.trim() || modelProfileLabel(modelConfig));
      setModelCheckResult(null);
    },
    [createProfileFromActive, modelConfig]
  );

  const handleModelProfileDelete = useCallback(
    (profileId: string): void => {
      deleteModelProfile(profileId);
      setModelCheckResult(null);
    },
    [deleteModelProfile]
  );

  const migrateLegacyCustomSkills = useCallback(async (): Promise<
    CustomSkillConfig[]
  > => {
    if (customSkillMigrationAttemptedRef.current) return [];
    customSkillMigrationAttemptedRef.current = true;
    const legacySkills = legacyCustomSkillsRef.current.filter(
      (skill) => skill.name?.trim() && skill.description?.trim()
    );
    if (legacySkills.length === 0) return [];

    const migrated: CustomSkillConfig[] = [];
    for (const legacySkill of legacySkills) {
      const payload: CustomSkillCreatePayload = {
        name: legacySkill.name!.trim(),
        description: legacySkill.description!.trim(),
        prompt: (legacySkill.prompt || legacySkill.description || "").trim(),
        enabled: legacySkill.enabled ?? true,
      };
      migrated.push(await createCustomSkill(payload));
    }
    legacyCustomSkillsRef.current = [];
    safeRemove(STORAGE_KEY.customSkills);
    return migrated;
  }, []);

  // ─── 后端技能拉取 ──────────────────────────────────────────────────────────
  const refreshSkills = useCallback(async (): Promise<void> => {
    setSkillsLoading(true);
    setSkillsError(null);
    try {
      const [backendSkills, customPayload] = await Promise.all([
        listBackendSkills(),
        listCustomSkills(),
      ]);
      let nextCustomSkills = customPayload.skills;
      if (nextCustomSkills.length === 0) {
        const migratedSkills = await migrateLegacyCustomSkills();
        if (migratedSkills.length > 0) {
          nextCustomSkills = migratedSkills;
        }
      }
      setRegisteredSkills(backendSkills);
      setCustomSkills(nextCustomSkills);
    } catch (error) {
      setSkillsError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setSkillsLoading(false);
    }
  }, [migrateLegacyCustomSkills]);

  // 首次挂载就拉一次；后续切到 settings tab 时也刷新一次。
  useEffect(() => {
    void refreshSkills();
  }, [refreshSkills]);
  useEffect(() => {
    if (settingsOpen) {
      void refreshSkills();
    }
  }, [settingsOpen, refreshSkills]);

  // ─── 聊天提交 ──────────────────────────────────────────────────────────────
  // sendMessage / status / stop / setMessages 都由 useChat 提供，
  // 上面已 destructure。这里只需包一层"trim + 切到 chat tab"。
  const sendChat = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      onTabChange("chat");
      const submittedMode = chatModeRef.current;
      lastSubmittedModeRef.current = submittedMode;
      const messageText = [buildCustomSkillPrompt(activeCustomSkills), trimmed]
        .filter(Boolean)
        .join("\n\n");
      sendMessage({ text: messageText });
    },
    [activeCustomSkills, busy, onTabChange, sendMessage]
  );

  const handleChatModeChange = useCallback((mode: AIChatMode): void => {
    chatModeRef.current = mode;
    setChatMode(mode);
  }, []);

  const onSubmitChat = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const text = commandInput;
    if (!text.trim() || busy) return;
    setCommandInput("");
    sendChat(text);
  };

  const handleApproveProposal = useCallback(
    async (proposalId: string): Promise<void> => {
      setProposalBusyId(proposalId);
      setProposalError(null);
      try {
        const response = await approveCommandProposal(proposalId);
        if (response.snapshot?.scenario) {
          onApplyScenario?.(response.snapshot.scenario);
        }
        await refreshCommandProposals();
      } catch (error) {
        setProposalError(
          error instanceof Error ? error.message : "命令审批执行失败"
        );
      } finally {
        setProposalBusyId(null);
      }
    },
    [onApplyScenario, refreshCommandProposals]
  );

  const handleRejectProposal = useCallback(
    async (proposalId: string): Promise<void> => {
      setProposalBusyId(proposalId);
      setProposalError(null);
      try {
        await rejectCommandProposal(proposalId);
        await refreshCommandProposals();
      } catch (error) {
        setProposalError(
          error instanceof Error ? error.message : "命令提案驳回失败"
        );
      } finally {
        setProposalBusyId(null);
      }
    },
    [refreshCommandProposals]
  );

  const handleOpenCompareSession = useCallback(
    async (compareSession: ScenarioCompareSession): Promise<void> => {
      try {
        const fresh = await getScenarioCompareSession(compareSession.id);
        setActiveCompareSession(fresh);
      } catch {
        setActiveCompareSession(compareSession);
      }
      setCompareDialogOpen(true);
    },
    []
  );

  const handleRunPlanSimulation = useCallback(
    async (compareSession: ScenarioCompareSession): Promise<void> => {
      setPlanSimulationBusyId(compareSession.id);
      try {
        const result = await simulateScenarioCompareSession(compareSession.id, {
          steps: 600,
          include_baseline: true,
        });
        setPlanSimulationResults((current) => ({
          ...current,
          [compareSession.id]: result,
        }));
        setActiveCompareSession(result.compare_session);
        setCompareDialogOpen(true);
      } finally {
        setPlanSimulationBusyId(null);
      }
    },
    []
  );

  const handleOpenScenario = useCallback(
    (nextScenarioId: string): void => {
      if (!nextScenarioId) return;
      navigate(`/play/${nextScenarioId}`);
    },
    [navigate]
  );

  // activeMcpServers are still managed in settings; external MCP runtime
  // connections are configured server-side through AICC_EXTERNAL_MCP_SERVERS.
  void activeMcpServers;

  // ─── MCP / Skill 增删 ─────────────────────────────────────────────────────
  const handleAddServer = useCallback(() => {
    const name = newServerName.trim();
    const endpoint = newServerEndpoint.trim();
    if (!name || !endpoint) return;
    setMcpServers((prev) => [
      ...prev,
      {
        id: newId(),
        name,
        endpoint,
        transport: newServerTransport,
        enabled: true,
      },
    ]);
    setNewServerName("");
    setNewServerEndpoint("");
    setNewServerTransport("stdio");
  }, [newServerName, newServerEndpoint, newServerTransport]);

  const handleAddSkill = useCallback(
    async (options?: AddCustomSkillOptions): Promise<void> => {
      const name = newSkillName.trim();
      const description = (options?.description ?? newSkillDescription).trim();
      const prompt = (options?.prompt ?? description).trim();
      const enabled = options?.enabled ?? true;
      if (!name || !description || !prompt) return;
      try {
        const skill = await createCustomSkill({
          name,
          description,
          prompt,
          inputSchema: options?.inputSchema,
          outputSchema: options?.outputSchema,
          enabled,
        });
        setCustomSkills((prev) => [...prev, skill]);
        setSkillsError(null);
        setNewSkillName("");
        setNewSkillDescription("");
      } catch (error) {
        setSkillsError(
          error instanceof Error ? error.message : "Custom skill save failed"
        );
      }
    },
    [newSkillName, newSkillDescription]
  );

  const handleRemoveCustomSkill = useCallback(async (id: string) => {
    try {
      await deleteCustomSkill(id);
      setCustomSkills((prev) => prev.filter((skill) => skill.id !== id));
      setSkillsError(null);
    } catch (error) {
      setSkillsError(
        error instanceof Error ? error.message : "Custom skill delete failed"
      );
    }
  }, []);

  const handleToggleCustomSkill = useCallback(
    async (id: string, enabled: boolean) => {
      try {
        const skill = await updateCustomSkill(id, { enabled });
        setCustomSkills((prev) =>
          prev.map((item) => (item.id === id ? skill : item))
        );
        setSkillsError(null);
      } catch (error) {
        setSkillsError(
          error instanceof Error ? error.message : "Custom skill update failed"
        );
      }
    },
    []
  );

  const handleUpdateCustomSkill = useCallback(
    async (id: string, next: UpdateCustomSkillOptions) => {
      try {
        const payload: CustomSkillUpdatePayload = next;
        const skill = await updateCustomSkill(id, payload);
        setCustomSkills((prev) =>
          prev.map((item) => (item.id === id ? skill : item))
        );
        setSkillsError(null);
      } catch (error) {
        setSkillsError(
          error instanceof Error ? error.message : "Custom skill update failed"
        );
      }
    },
    []
  );

  // ─── 模型连接测试 ────────────────────────────────────────────────────────
  const checkModelConnection = useCallback(async (): Promise<void> => {
    if (!modelConfig.baseUrl.trim()) {
      setModelCheckResult({
        status: "error",
        message: "请先填写 Base URL。",
        provider: modelConfig.provider,
        endpoint: "",
        auth_ok: false,
        models_listed: false,
      });
      return;
    }
    setCheckingModel(true);
    setModelCheckResult(null);
    try {
      const payload = await apiCall<ModelCheckResponse>("/api/ai/model/check", {
        method: "POST",
        json: modelConfig,
      });
      setModelCheckResult(payload);
      const activeProviderId =
        modelProfiles.find((profile) => profile.id === activeModelProfileId)
          ?.providerId ?? modelConfig.provider;
      markProviderChecked(activeProviderId, payload.status !== "error");
    } catch (error) {
      setModelCheckResult({
        status: "error",
        message: "连接测试失败。",
        provider: modelConfig.provider,
        endpoint: modelConfig.baseUrl,
        auth_ok: false,
        models_listed: false,
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setCheckingModel(false);
    }
  }, [activeModelProfileId, markProviderChecked, modelConfig, modelProfiles]);

  return (
    <>
      <TacticalSettingsModal
        activeCustomSkillsCount={activeCustomSkills.length}
        activeMcpServersCount={activeMcpServers.length}
        checkingModel={checkingModel}
        customSkills={customSkills}
        mcpServers={mcpServers}
        modelCheckResult={modelCheckResult}
        modelConfig={modelConfig}
        modelProfiles={modelProfiles}
        modelPresetOptions={modelPresetOptions}
        activeModelProfileDirty={activeModelProfileDirty}
        activeModelProfileId={activeModelProfileId}
        mapBaseLayer={mapBaseLayer}
        newServerEndpoint={newServerEndpoint}
        newServerName={newServerName}
        newServerTransport={newServerTransport}
        newSkillDescription={newSkillDescription}
        newSkillName={newSkillName}
        onAddServer={handleAddServer}
        onAddSkill={handleAddSkill}
        onCheckModel={() => void checkModelConnection()}
        onClearMessages={() => setMessages([])}
        onMapBaseLayerChange={onMapBaseLayerChange}
        onModelConfigChange={handleModelConfigChange}
        onModelProfileCreate={handleModelProfileCreate}
        onModelProfileDelete={handleModelProfileDelete}
        onModelProfileSave={handleModelProfileSave}
        onModelProfileSelect={handleModelProfileSelect}
        onNewServerEndpointChange={setNewServerEndpoint}
        onNewServerNameChange={setNewServerName}
        onNewServerTransportChange={setNewServerTransport}
        onNewSkillDescriptionChange={setNewSkillDescription}
        onNewSkillNameChange={setNewSkillName}
        onOpenChange={onSettingsOpenChange ?? (() => undefined)}
        onProjectMcpEnabledChange={setProjectMcpEnabled}
        onRefreshSkills={() => void refreshSkills()}
        onRemoveCustomSkill={(id) => void handleRemoveCustomSkill(id)}
        onRemoveServer={(id) =>
          setMcpServers((prev) => prev.filter((s) => s.id !== id))
        }
        onToggleCustomSkill={(id, enabled) =>
          void handleToggleCustomSkill(id, enabled)
        }
        onUpdateCustomSkill={(id, next) =>
          void handleUpdateCustomSkill(id, next)
        }
        onToggleServer={(id, enabled) =>
          setMcpServers((prev) =>
            prev.map((s) => (s.id === id ? { ...s, enabled } : s))
          )
        }
        open={settingsOpen}
        projectMcpEnabled={projectMcpEnabled}
        registeredSkills={registeredSkills}
        selectedPreset={selectedPreset}
        skillsError={skillsError}
        skillsLoading={skillsLoading}
      />
      {open && (
        <aside
          className={cn(
            "relative hidden h-full min-h-0 min-w-0 flex-col border-l",
            "border-slate-700/50 bg-[#0a0f18]/95 backdrop-blur-2xl lg:flex",
            panelClassName
          )}
          style={panelStyle}
        >
          {/* 顶部：标题 + tabs + 关闭 */}
          <header className="flex items-center justify-between gap-2 border-b border-slate-700/50 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <div className="grid size-7 place-items-center rounded-lg border border-slate-700/50 bg-slate-800/50 text-slate-300">
                <Sparkles className="size-3.5" />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.32em] text-slate-500">
                  AI Copilot
                </div>
                <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-100 leading-tight">
                  天枢助手
                  {scenarioId && (
                    <span
                      className="rounded bg-slate-800/50 px-1.5 py-0.5 font-mono text-[9px] font-normal tracking-wider text-slate-400"
                      title={`会话已绑定到 scenario ${scenarioId}`}
                    >
                      #{scenarioId.slice(0, 6)}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <Button
              aria-label="关闭 AI 侧栏"
              className="size-8 text-slate-400 hover:text-slate-100"
              onClick={() => onOpenChange(false)}
              size="icon"
              variant="ghost"
              title="收起 AI 侧栏"
            >
              <X className="size-4" />
            </Button>
          </header>

          <div className="flex items-center gap-1 border-b border-slate-700/50 px-3 py-1.5">
            <TabButton
              active={activeTab === "chat"}
              icon={<MessageSquare className="size-3.5" />}
              label="聊天"
              onClick={() => onTabChange("chat")}
            />
            <div className="ml-auto text-[11px] text-slate-500">
              {busy ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="size-3 animate-spin" /> Thinking
                </span>
              ) : chatError ? (
                <span className="inline-flex items-center gap-1 text-red-300">
                  <AlertTriangle className="size-3" /> Error
                </span>
              ) : (
                <span>Ready</span>
              )}
            </div>
          </div>

          {/* Tab 内容 */}
          <div className="flex min-h-0 flex-1 flex-col">
            {activeTab === "chat" && (
              <ChatPanel
                chatLogRef={chatLogRef}
                chatError={chatError}
                chatRunSummary={chatRunSummary}
                chatMode={chatMode}
                commandInput={commandInput}
                commandProposals={commandProposals}
                proposalBusyId={proposalBusyId}
                proposalError={proposalError}
                messages={messages}
                onApproveProposal={(id) => void handleApproveProposal(id)}
                onChatModeChange={handleChatModeChange}
                onCommandInputChange={setCommandInput}
                onOpenCompareSession={(session) =>
                  void handleOpenCompareSession(session)
                }
                onOpenModelSettings={() => navigate("/ai-models")}
                onOpenScenario={handleOpenScenario}
                onQuickCommand={sendChat}
                onRejectProposal={(id) => void handleRejectProposal(id)}
                onRunPlanSimulation={(session) =>
                  void handleRunPlanSimulation(session)
                }
                onSubmit={onSubmitChat}
                busy={busy}
                planSimulationBusyId={planSimulationBusyId}
                planSimulationResults={planSimulationResults}
                stop={stop}
              />
            )}
          </div>
        </aside>
      )}
      <ScenarioCompareDialog
        scenarioIds={activeCompareSession?.scenario_ids ?? []}
        open={compareDialogOpen}
        onClose={() => setCompareDialogOpen(false)}
        onOpenScenario={handleOpenScenario}
        initialSession={activeCompareSession}
      />
    </>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Tab 按钮 + 通用小组件
// ────────────────────────────────────────────────────────────────────────────

interface TabButtonProps {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}

function TabButton({ active, icon, label, onClick }: TabButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors",
        active
          ? "bg-slate-700/50 text-slate-100"
          : "text-slate-400 hover:bg-slate-800/30 hover:text-slate-200"
      )}
      onClick={onClick}
      type="button"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

const TEXTAREA_CLASS =
  "min-h-[64px] w-full resize-none rounded-lg border border-slate-700/50 bg-slate-900/50 p-2 text-xs text-slate-100 placeholder:text-slate-600 focus:border-slate-600/50 focus:outline-none focus:ring-1 focus:ring-slate-600/30";

// ────────────────────────────────────────────────────────────────────────────
// Chat Panel
// ────────────────────────────────────────────────────────────────────────────

interface ChatPanelProps {
  messages: UIMessage[];
  chatLogRef: React.MutableRefObject<HTMLDivElement | null>;
  chatError?: Error;
  chatRunSummary: ChatRunSummary;
  chatMode: AIChatMode;
  commandInput: string;
  commandProposals: CommandProposal[];
  proposalBusyId: string | null;
  proposalError: string | null;
  planSimulationBusyId: string | null;
  planSimulationResults: Record<string, ScenarioBatchSimulationResponse>;
  busy: boolean;
  stop: () => void;
  onApproveProposal: (proposalId: string) => void;
  onChatModeChange: (mode: AIChatMode) => void;
  onCommandInputChange: (next: string) => void;
  onOpenCompareSession: (compareSession: ScenarioCompareSession) => void;
  onOpenModelSettings: () => void;
  onOpenScenario: (scenarioId: string) => void;
  onQuickCommand: (cmd: string) => void;
  onRejectProposal: (proposalId: string) => void;
  onRunPlanSimulation: (compareSession: ScenarioCompareSession) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function ChatPanel({
  messages,
  chatLogRef,
  chatError,
  chatRunSummary,
  chatMode,
  commandInput,
  commandProposals,
  proposalBusyId,
  proposalError,
  planSimulationBusyId,
  planSimulationResults,
  busy,
  stop,
  onApproveProposal,
  onChatModeChange,
  onCommandInputChange,
  onOpenCompareSession,
  onOpenModelSettings,
  onOpenScenario,
  onQuickCommand,
  onRejectProposal,
  onRunPlanSimulation,
  onSubmit,
}: ChatPanelProps) {
  const chatErrorMessage = chatError ? formatChatError(chatError) : "";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={chatLogRef}
        className="flex-1 space-y-1 overflow-y-auto px-3 py-3"
      >
        <RunStatusCard summary={chatRunSummary} />
        {chatErrorMessage && (
          <div className="mb-3 rounded-lg border border-red-300/25 bg-red-300/[0.05] px-2.5 py-2 text-[11px] text-red-100">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-3" />
              <div>
                <div className="font-medium">AI chat unavailable</div>
                <div className="mt-0.5 text-[10px] opacity-80">
                  {chatErrorMessage}
                </div>
              </div>
            </div>
          </div>
        )}
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-xs text-slate-500">
            <Sparkles className="size-5 text-slate-600" />
            <div className="text-slate-400">
              Ask anything about this scenario
            </div>
            <div className="text-[11px] text-slate-600">
              示例：开始推演、部署单位、查看战况……
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <MessageBlock
              key={m.id}
              message={m}
              onOpenCompareSession={onOpenCompareSession}
              onOpenScenario={onOpenScenario}
              onRunPlanSimulation={onRunPlanSimulation}
              planSimulationBusyId={planSimulationBusyId}
              planSimulationResults={planSimulationResults}
            />
          ))
        )}
      </div>

      <div className="border-t border-slate-700/50 px-3 py-2">
        <ApprovalQueuePanel
          busyId={proposalBusyId}
          error={proposalError}
          onApprove={onApproveProposal}
          onReject={onRejectProposal}
          proposals={commandProposals}
        />
        <ModeSwitcher
          disabled={busy}
          mode={chatMode}
          onModeChange={onChatModeChange}
        />
        <div className="mb-2 flex flex-wrap gap-1">
          {chatMode === "command" &&
            QUICK_COMMANDS.map((cmd) => (
              <button
                className="rounded-md border border-slate-700/50 bg-slate-800/50 px-2 py-0.5 text-[10px] text-slate-400 transition-colors hover:border-slate-600/50 hover:bg-slate-700/50 hover:text-slate-200"
                key={cmd}
                onClick={() => onQuickCommand(cmd)}
                type="button"
              >
                {cmd}
              </button>
            ))}
        </div>
        <form className="flex flex-col gap-2" onSubmit={onSubmit}>
          <textarea
            className={TEXTAREA_CLASS}
            onChange={(event) => onCommandInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={
              chatMode === "ask"
                ? "Ask about this scenario without changing it..."
                : "Command this scenario..."
            }
            value={commandInput}
            rows={2}
          />
          <div className="flex min-w-0 items-center justify-between gap-2 text-[10px] text-slate-500">
            <div className="flex min-w-0 items-center gap-2">
              <ModelSwitcher
                className="min-w-0"
                disabled={busy}
                onOpenSettings={onOpenModelSettings}
              />
              <span className="hidden truncate sm:inline">
                {busy
                  ? "Thinking..."
                  : chatMode === "ask"
                    ? "Ask mode"
                    : "Command mode"}
              </span>
            </div>
            {busy ? (
              <Button
                className="h-6 gap-1 px-2 text-[10px]"
                onClick={() => stop()}
                size="sm"
                type="button"
                variant="danger"
              >
                <Square className="size-2.5" />
                Stop
              </Button>
            ) : (
              <Button
                className="h-6 gap-1 px-2 text-[10px]"
                disabled={!commandInput.trim()}
                size="sm"
                type="submit"
              >
                <Send className="size-3" />
                Send
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

function ApprovalQueuePanel({
  proposals,
  busyId,
  error,
  onApprove,
  onReject,
}: {
  proposals: CommandProposal[];
  busyId: string | null;
  error: string | null;
  onApprove: (proposalId: string) => void;
  onReject: (proposalId: string) => void;
}) {
  const visible = proposals
    .filter((proposal) =>
      ["pending", "blocked", "failed"].includes(proposal.status)
    )
    .slice(0, 3);

  if (visible.length === 0 && !error) return null;

  return (
    <div className="mb-2 space-y-1.5">
      {error && (
        <div className="rounded-lg border border-red-300/20 bg-red-300/[0.05] px-2.5 py-2 text-[11px] text-red-100">
          {error}
        </div>
      )}
      {visible.map((proposal) => {
        const blocked = proposal.status === "blocked";
        const busy = busyId === proposal.id;
        const issueCount = proposal.adjudication.issues.length;
        return (
          <div
            className={cn(
              "rounded-lg border px-2.5 py-2 text-[11px]",
              blocked
                ? "border-red-300/20 bg-red-300/[0.04] text-red-100"
                : "border-cyan-300/20 bg-cyan-300/[0.04] text-cyan-50"
            )}
            key={proposal.id}
          >
            <div className="flex items-start gap-2">
              {blocked ? (
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              ) : (
                <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">
                    {blocked ? "规则未通过" : "待人工审批"}
                  </span>
                  <span className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[9px] uppercase opacity-70">
                    {proposal.source}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-[10px] opacity-75">
                  {proposal.steps
                    .map((step) => step.summary || step.skill)
                    .join(" / ")}
                </div>
                {issueCount > 0 && (
                  <div className="mt-1 space-y-0.5 text-[10px] opacity-80">
                    {proposal.adjudication.issues.slice(0, 2).map((issue) => (
                      <div key={`${issue.code}-${issue.step_id ?? ""}`}>
                        {issue.severity === "blocking" ? "阻断" : "提示"}：
                        {issue.message}
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-2 flex items-center justify-end gap-1.5">
                  <Button
                    className="h-6 px-2 text-[10px]"
                    disabled={busy}
                    onClick={() => onReject(proposal.id)}
                    size="sm"
                    type="button"
                    variant="ghost"
                  >
                    驳回
                  </Button>
                  <Button
                    className="h-6 px-2 text-[10px]"
                    disabled={blocked || busy}
                    onClick={() => onApprove(proposal.id)}
                    size="sm"
                    type="button"
                  >
                    {busy ? "执行中" : "审批执行"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ModeSwitcher({
  disabled,
  mode,
  onModeChange,
}: {
  disabled: boolean;
  mode: AIChatMode;
  onModeChange: (mode: AIChatMode) => void;
}) {
  const modes: Array<{ label: string; value: AIChatMode }> = [
    { label: "Ask", value: "ask" },
    { label: "Command", value: "command" },
  ];

  return (
    <div className="mb-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
      <div className="inline-flex rounded-md border border-slate-700/50 bg-slate-900/50 p-0.5">
        {modes.map((item) => (
          <button
            className={cn(
              "rounded px-2 py-0.5 transition-colors",
              mode === item.value
                ? "bg-slate-700/70 text-slate-100"
                : "text-slate-500 hover:text-slate-300",
              disabled && "cursor-not-allowed opacity-50"
            )}
            disabled={disabled}
            key={item.value}
            onClick={() => onModeChange(item.value)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <span className="truncate">
        {mode === "ask" ? "Explain and plan" : "Commands require approval"}
      </span>
    </div>
  );
}

function RunStatusCard({ summary }: { summary: ChatRunSummary }) {
  const icon =
    summary.tone === "running" ? (
      <Loader2 className="mt-0.5 size-3 animate-spin" />
    ) : summary.tone === "done" ? (
      <CheckCircle2 className="mt-0.5 size-3" />
    ) : summary.tone === "error" ? (
      <AlertTriangle className="mt-0.5 size-3" />
    ) : (
      <Sparkles className="mt-0.5 size-3" />
    );

  return (
    <div
      className={cn(
        "mb-3 rounded-lg border px-2.5 py-2 text-[11px]",
        summary.tone === "running" &&
          "border-blue-300/20 bg-blue-300/[0.04] text-blue-100",
        summary.tone === "done" &&
          "border-emerald-300/20 bg-emerald-300/[0.04] text-emerald-100",
        summary.tone === "error" &&
          "border-red-300/25 bg-red-300/[0.05] text-red-100",
        summary.tone === "idle" &&
          "border-slate-700/50 bg-slate-900/40 text-slate-300"
      )}
    >
      <div className="flex items-start gap-2">
        {icon}
        <div className="min-w-0 flex-1">
          <div className="font-medium">{summary.label}</div>
          <div className="mt-0.5 truncate text-[10px] opacity-70">
            {summary.detail}
          </div>
        </div>
      </div>
      {summary.tools.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[10px] opacity-70">
            {summary.tools.length} tool call
            {summary.tools.length > 1 ? "s" : ""}
          </summary>
          <div className="mt-1 space-y-1">
            {summary.tools.map((tool, idx) => (
              <div
                className="flex items-center justify-between gap-2 rounded bg-black/20 px-2 py-1 font-mono text-[10px] text-slate-300"
                key={`${tool.toolName}-${idx}`}
              >
                <span className="truncate">{tool.toolName}</span>
                <span className="shrink-0 uppercase text-slate-500">
                  {tool.state}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function MessageBlock({
  message,
  onOpenCompareSession,
  onOpenScenario,
  onRunPlanSimulation,
  planSimulationBusyId,
  planSimulationResults,
}: {
  message: UIMessage;
  onOpenCompareSession: (compareSession: ScenarioCompareSession) => void;
  onOpenScenario: (scenarioId: string) => void;
  onRunPlanSimulation: (compareSession: ScenarioCompareSession) => void;
  planSimulationBusyId: string | null;
  planSimulationResults: Record<string, ScenarioBatchSimulationResponse>;
}) {
  const isUser = message.role === "user";
  const text = previewText(message);
  const hasContent = text || message.parts.length > 0;

  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        isUser ? "items-end" : "items-start"
      )}
    >
      <div
        className={cn("text-[10px] text-slate-500", isUser ? "pr-1" : "pl-1")}
      >
        {isUser ? "你" : "助手"}
      </div>
      <div
        className={cn(
          "max-w-[92%] rounded-lg px-3 py-2 text-xs",
          isUser
            ? "bg-slate-800/80 text-slate-100"
            : "bg-transparent text-slate-100"
        )}
      >
        {!hasContent && !isUser && (
          <span className="inline-flex items-center gap-1 text-slate-500">
            <Loader2 className="size-3 animate-spin" /> 思考中…
          </span>
        )}
        {message.parts.map((part, idx) => {
          if (isTextUIPart(part)) {
            return (
              <div key={idx} className="whitespace-pre-wrap leading-relaxed">
                {part.text}
              </div>
            );
          }
          if (isReasoningUIPart(part)) {
            return (
              <details
                key={idx}
                className="mt-2 rounded-md border border-slate-700/50 bg-slate-900/50 px-2 py-1"
              >
                <summary className="cursor-pointer text-[10px] text-slate-400">
                  推理过程
                </summary>
                <div className="mt-1 whitespace-pre-wrap text-[11px] text-slate-500">
                  {part.text}
                </div>
              </details>
            );
          }
          if (isToolOrDynamicToolUIPart(part)) {
            const p = part as {
              type?: string;
              toolName?: string;
              state: string;
              input?: unknown;
              output?: unknown;
              errorText?: string;
            };
            // 静态工具的 toolName 编码在 type='tool-<name>' 里；动态工具有
            // 单独的 toolName 字段。两者都要兼容。
            const toolName = p.toolName
              ? p.toolName
              : typeof p.type === "string" && p.type.startsWith("tool-")
                ? p.type.slice("tool-".length)
                : "tool";
            if (
              p.state === "output-available" &&
              isPlanSetToolOutput(p.output)
            ) {
              return (
                <PlanSetCard
                  key={idx}
                  output={p.output}
                  onOpenCompareSession={onOpenCompareSession}
                  onRunPlanSimulation={onRunPlanSimulation}
                  planSimulationBusyId={planSimulationBusyId}
                  planSimulationResult={
                    planSimulationResults[p.output.compareSession.id]
                  }
                />
              );
            }
            if (
              p.state === "output-available" &&
              isPlanSimulationToolOutput(p.output)
            ) {
              return (
                <PlanSimulationCard
                  key={idx}
                  output={p.output}
                  onOpenCompareSession={onOpenCompareSession}
                  onOpenScenario={onOpenScenario}
                />
              );
            }
            return (
              <details
                key={idx}
                className="mt-2 rounded-md border border-slate-700/50 bg-slate-900/50 p-2"
              >
                <summary className="cursor-pointer flex items-center gap-1.5 text-[10px] font-medium text-slate-300">
                  <Wrench className="size-3" />
                  {toolName}
                  <span className="rounded bg-slate-700/50 px-1.5 py-0.5 text-[9px] uppercase text-slate-400">
                    {p.state}
                  </span>
                </summary>
                {p.input != null && (
                  <pre className="mt-2 max-h-24 overflow-auto rounded bg-black/30 p-1.5 font-mono text-[10px] text-slate-300">
                    {typeof p.input === "string"
                      ? p.input
                      : JSON.stringify(p.input, null, 2)}
                  </pre>
                )}
                {p.state === "output-available" && p.output != null && (
                  <pre className="mt-2 max-h-24 overflow-auto rounded bg-black/30 p-1.5 font-mono text-[10px] text-emerald-300/80">
                    {typeof p.output === "string"
                      ? p.output
                      : JSON.stringify(p.output, null, 2)}
                  </pre>
                )}
                {p.state === "output-error" && p.errorText && (
                  <div className="mt-2 text-[10px] text-red-300">
                    {p.errorText}
                  </div>
                )}
              </details>
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}

function PlanSetCard({
  output,
  onOpenCompareSession,
  onRunPlanSimulation,
  planSimulationBusyId,
  planSimulationResult,
}: {
  output: PlanSetToolOutput;
  onOpenCompareSession: (compareSession: ScenarioCompareSession) => void;
  onRunPlanSimulation: (compareSession: ScenarioCompareSession) => void;
  planSimulationBusyId: string | null;
  planSimulationResult?: ScenarioBatchSimulationResponse;
}) {
  const compareSession = output.compareSession;
  const simBusy = planSimulationBusyId === compareSession.id;

  return (
    <div className="mt-2 rounded-xl border border-cyan-300/15 bg-cyan-300/[0.04] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-cyan-100">
            已生成 {output.branchCount} 个候选方案
          </div>
          <div className="mt-1 text-[10px] text-slate-400">
            来源场景：{output.sourceScenarioName}
          </div>
        </div>
        <span className="rounded border border-cyan-300/20 px-1.5 py-0.5 text-[9px] uppercase text-cyan-200/80">
          Plan Set
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {output.plans.map((plan, index) => (
          <div
            className="rounded-lg border border-slate-700/50 bg-slate-950/40 px-2.5 py-2"
            key={`${plan.title}-${index}`}
          >
            <div className="text-[11px] font-medium text-slate-100">
              方案 {index + 1} · {plan.title}
            </div>
            {plan.concept && (
              <div className="mt-1 text-[10px] leading-relaxed text-slate-400">
                {plan.concept}
              </div>
            )}
            {plan.key_actions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {plan.key_actions.slice(0, 4).map((item) => (
                  <span
                    className="rounded border border-slate-700/50 bg-slate-900/60 px-1.5 py-0.5 text-[9px] text-slate-300"
                    key={item}
                  >
                    {item}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {planSimulationResult && (
        <div className="mt-3 rounded-lg border border-emerald-300/15 bg-emerald-300/[0.04] px-2.5 py-2 text-[10px] text-emerald-100">
          最近一次批量推演已完成，共 {planSimulationResult.results.length}{" "}
          个结果。
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          className="h-7 px-2 text-[10px]"
          size="sm"
          type="button"
          onClick={() => onOpenCompareSession(compareSession)}
        >
          打开对比台
        </Button>
        <Button
          className="h-7 px-2 text-[10px]"
          size="sm"
          type="button"
          variant="ghost"
          disabled={simBusy}
          onClick={() => onRunPlanSimulation(compareSession)}
        >
          {simBusy ? "推演中..." : "一键并行推演"}
        </Button>
      </div>
    </div>
  );
}

function PlanSimulationCard({
  output,
  onOpenCompareSession,
  onOpenScenario,
}: {
  output: PlanSimulationToolOutput;
  onOpenCompareSession: (compareSession: ScenarioCompareSession) => void;
  onOpenScenario: (scenarioId: string) => void;
}) {
  const topResults = output.results.slice(0, 3);
  return (
    <div className="mt-2 rounded-xl border border-emerald-300/15 bg-emerald-300/[0.04] p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium text-emerald-100">
            批量推演完成
          </div>
          <div className="mt-1 text-[10px] text-slate-400">
            推演步数：{output.steps}
          </div>
        </div>
        <span className="rounded border border-emerald-300/20 px-1.5 py-0.5 text-[9px] uppercase text-emerald-200/80">
          Results
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {topResults.map((result, index) => (
          <div
            className="flex items-center justify-between gap-3 rounded-lg border border-slate-700/50 bg-slate-950/40 px-2.5 py-2"
            key={result.scenario_id}
          >
            <div className="min-w-0">
              <div className="truncate text-[11px] font-medium text-slate-100">
                #{index + 1} {result.scenario_name}
              </div>
              <div className="mt-1 text-[10px] text-slate-400">
                {result.grade} · {result.confidence}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold text-emerald-200">
                {result.overall_score}
              </div>
              <div className="text-[10px] text-slate-500">score</div>
            </div>
          </div>
        ))}
      </div>
      {output.recommendedReason && (
        <div className="mt-3 text-[10px] leading-relaxed text-emerald-100">
          {output.recommendedReason}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          className="h-7 px-2 text-[10px]"
          size="sm"
          type="button"
          onClick={() => onOpenCompareSession(output.compareSession)}
        >
          打开对比台
        </Button>
        {output.recommendedScenarioId && (
          <Button
            className="h-7 px-2 text-[10px]"
            size="sm"
            type="button"
            variant="ghost"
            onClick={() => onOpenScenario(output.recommendedScenarioId!)}
          >
            载入最优方案
          </Button>
        )}
      </div>
    </div>
  );
}

export type { MCPServerConfig, CustomSkillConfig, ModelConfig, ModelProfile };

// ──────────────────────────────────────────────────────────────────────────────
// Settings Panel Props
// ──────────────────────────────────────────────────────────────────────────────

export interface TacticalSettingsProps {
  modelConfig: ModelConfig;
  modelProfiles: ModelProfile[];
  activeModelProfileId: string;
  activeModelProfileDirty: boolean;
  modelPresetOptions: string[];
  selectedPreset: string;
  modelCheckResult: ModelCheckResponse | null;
  checkingModel: boolean;
  mcpServers: MCPServerConfig[];
  activeMcpServersCount: number;
  projectMcpEnabled: boolean;
  newServerName: string;
  newServerEndpoint: string;
  newServerTransport: "stdio" | "sse" | "http";
  customSkills: CustomSkillConfig[];
  activeCustomSkillsCount: number;
  registeredSkills: RegisteredSkill[];
  skillsLoading: boolean;
  skillsError: string | null;
  newSkillName: string;
  newSkillDescription: string;
  onModelConfigChange: (next: ModelConfig) => void;
  onModelProfileSelect: (id: string) => void;
  onModelProfileSave: (name: string) => void;
  onModelProfileCreate: (name: string) => void;
  onModelProfileDelete: (id: string) => void;
  onCheckModel: () => void;
  mapBaseLayer: CesiumBaseLayerKey;
  onMapBaseLayerChange: (key: CesiumBaseLayerKey) => void;
  onProjectMcpEnabledChange: (enabled: boolean) => void;
  onAddServer: () => void;
  onRemoveServer: (id: string) => void;
  onToggleServer: (id: string, enabled: boolean) => void;
  onNewServerNameChange: (v: string) => void;
  onNewServerEndpointChange: (v: string) => void;
  onNewServerTransportChange: (t: "stdio" | "sse" | "http") => void;
  onAddSkill: (options?: AddCustomSkillOptions) => void | Promise<void>;
  onRemoveCustomSkill: (id: string) => void | Promise<void>;
  onToggleCustomSkill: (id: string, enabled: boolean) => void | Promise<void>;
  onUpdateCustomSkill: (
    id: string,
    next: UpdateCustomSkillOptions
  ) => void | Promise<void>;
  onNewSkillNameChange: (v: string) => void;
  onNewSkillDescriptionChange: (v: string) => void;
  onRefreshSkills: () => void;
  onClearMessages: () => void;
}
