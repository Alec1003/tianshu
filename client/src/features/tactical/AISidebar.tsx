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
 * - 设置：Model（provider + baseUrl + apiKey + model + 连接测试）/
 *   MCP Servers（增删改 + enable toggle）/ Skills（后端已注册 + 用户
 *   自定义）三段。
 * - 持久化：modelConfig / mcpServers / customSkills / projectMcpEnabled
 *   使用 aicc.ai.* keys；chat 消息由于类型从
 *   ChatMessage 迁移到 UIMessage，另存为 aicc.ai.messages.v2。
 * - 主题：cyan/slate tactical，复用 shadcn Card/Button，TailwindCSS。
 *
 * Props 由 AITacticalCommandPlatform 控制：open / activeTab /
 * onOpenChange / onTabChange / onApplyScenario(刷新 game)。
 */
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Cpu,
  KeyRound,
  Loader2,
  MessageSquare,
  Plug,
  Plus,
  RefreshCw,
  Send,
  Settings as SettingsIcon,
  Sparkles,
  Square,
  Trash2,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import { useChat } from "@ai-sdk/react";
import {
  DefaultChatTransport,
  isReasoningUIPart,
  isTextUIPart,
  isToolOrDynamicToolUIPart,
  type UIMessage,
} from "ai";

import { getRuntimeScenario } from "@/api/ai";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type AISidebarTab = "chat" | "settings";
type AIChatMode = "ask" | "command";

interface MCPServerConfig {
  id: string;
  name: string;
  endpoint: string;
  transport: "stdio" | "sse" | "http";
  enabled: boolean;
}

interface CustomSkillConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

interface ModelConfig {
  provider: string;
  baseUrl: string;
  apiKey: string;
  model: string;
}

interface RegisteredSkill {
  name: string;
  description: string;
  parameters?: Record<string, unknown>;
}

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

interface AISidebarProps {
  open: boolean;
  activeTab: AISidebarTab;
  onOpenChange: (open: boolean) => void;
  onTabChange: (tab: AISidebarTab) => void;
  /** AI command 返回的 scenario JSON 应用回 game。 */
  onApplyScenario?: (scenario: Record<string, unknown>) => void;
  /**
   * AI 调用 ``simulation_start`` 时触发的回调（等价于 UI 上的 Play 按钮）。
   * 后续仿真在客户端自动循环 step，直到 ``simulation_pause`` /
   * ``simulation_stop`` 或者用户手动暂停。``simulation_step(N)`` 不会触发
   * 此回调（视为单次推演 N 步即停）。
   */
  onResumePlay?: () => void | Promise<void>;
  /**
   * 当前 scenario id，用作 chat 历史的 localStorage 命名空间。
   * 切换/重置/导入新 scenario 时变化，自动切换该 scenario 的会话。
   * 可选：未提供时降级为单一全局会话。
   */
  scenarioId?: string;
}

const STORAGE_KEY = {
  messagesV2: "aicc.ai.messages.v2",
  mcpServers: "aicc.ai.mcpServers",
  customSkills: "aicc.ai.customSkills",
  model: "aicc.ai.model",
  projectMcpEnabled: "aicc.ai.projectMcpEnabled",
} as const;

const DEFAULT_MODEL: ModelConfig = {
  provider: "openai",
  baseUrl: "",
  apiKey: "",
  model: "gpt-4o-mini",
};

const MODEL_PROVIDER_OPTIONS = [
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "qwen",
  "ollama",
  "custom",
] as const;

const MODEL_PRESETS: Record<string, string[]> = {
  openai: ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"],
  anthropic: ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  qwen: ["qwen-max", "qwen-plus", "qwen-turbo"],
  ollama: ["llama3.1", "qwen2.5", "mistral"],
  custom: [],
};

const DEFAULT_MCP_SERVERS: MCPServerConfig[] = [
  {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `mcp-${Date.now()}`,
    name: "AICC MCP",
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

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
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
    return "No LLM is configured. Fill API Key in Settings > 模型配置, or set AICC_LLM_MODEL and AICC_LLM_API_KEY in the server environment.";
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
  onApplyScenario,
  onResumePlay,
  scenarioId,
}: AISidebarProps) {
  // —— 持久化状态 ——
  const [mcpServers, setMcpServers] = useState<MCPServerConfig[]>(() =>
    safeLoad<MCPServerConfig[]>(STORAGE_KEY.mcpServers, DEFAULT_MCP_SERVERS)
  );
  const [customSkills, setCustomSkills] = useState<CustomSkillConfig[]>(() =>
    safeLoad<CustomSkillConfig[]>(STORAGE_KEY.customSkills, [])
  );
  const [modelConfig, setModelConfig] = useState<ModelConfig>(() => {
    const loaded = safeLoad<Partial<ModelConfig>>(
      STORAGE_KEY.model,
      DEFAULT_MODEL
    );
    return {
      provider: loaded.provider ?? DEFAULT_MODEL.provider,
      baseUrl: loaded.baseUrl ?? DEFAULT_MODEL.baseUrl,
      apiKey: loaded.apiKey ?? DEFAULT_MODEL.apiKey,
      model: loaded.model ?? DEFAULT_MODEL.model,
    };
  });
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
  const chatLogRef = useRef<HTMLDivElement | null>(null);

  // headers 函数需要读最新 modelConfig，但 transport 有状态不能重建；
  // 用 ref 告诉 headers（）去拿最新值，避免重建 transport 丢失消息。
  const modelConfigRef = useRef(modelConfig);
  useEffect(() => {
    modelConfigRef.current = modelConfig;
  }, [modelConfig]);
  const chatModeRef = useRef<AIChatMode>(chatMode);
  useEffect(() => {
    chatModeRef.current = chatMode;
  }, [chatMode]);

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/chat",
        headers: () => {
          const m = modelConfigRef.current;
          const h: Record<string, string> = {};
          if (m.provider) h["X-AICC-Model-Provider"] = m.provider;
          if (m.model) h["X-AICC-Model-Name"] = m.model;
          if (m.apiKey) h["X-AICC-Model-Api-Key"] = m.apiKey;
          if (m.baseUrl) h["X-AICC-Model-Base-Url"] = m.baseUrl;
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
      const initial = safeLoad<UIMessage[]>(messagesKeyFor(scenarioId), []);
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
    const next = safeLoad<UIMessage[]>(messagesKeyFor(scenarioId), []);
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
    if (chatMode === "ask") return;
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
    })();
  }, [busy, status, chatMode, messages, onApplyScenario, onResumePlay]);

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
    () => safeSave(STORAGE_KEY.customSkills, customSkills),
    [customSkills]
  );
  useEffect(() => safeSave(STORAGE_KEY.model, modelConfig), [modelConfig]);
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

  // ─── 后端技能拉取 ──────────────────────────────────────────────────────────
  const refreshRegisteredSkills = useCallback(async (): Promise<void> => {
    setSkillsLoading(true);
    setSkillsError(null);
    try {
      const response = await fetch(`/api/ai/skills`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as {
        skills?: RegisteredSkill[];
      };
      setRegisteredSkills(payload.skills ?? []);
    } catch (error) {
      setSkillsError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setSkillsLoading(false);
    }
  }, []);

  // 首次挂载就拉一次；后续切到 settings tab 时也刷新一次。
  useEffect(() => {
    void refreshRegisteredSkills();
  }, [refreshRegisteredSkills]);
  useEffect(() => {
    if (open && activeTab === "settings") {
      void refreshRegisteredSkills();
    }
  }, [open, activeTab, refreshRegisteredSkills]);

  // ─── 聊天提交 ──────────────────────────────────────────────────────────────
  // sendMessage / status / stop / setMessages 都由 useChat 提供，
  // 上面已 destructure。这里只需包一层"trim + 切到 chat tab"。
  const sendChat = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      onTabChange("chat");
      const messageText =
        chatMode === "ask"
          ? `Ask mode: answer, analyze, or plan only. Do not execute scenario-changing tools.\n\n${trimmed}`
          : trimmed;
      sendMessage({ text: messageText });
    },
    [busy, chatMode, onTabChange, sendMessage]
  );

  const onSubmitChat = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const text = commandInput;
    if (!text.trim() || busy) return;
    setCommandInput("");
    sendChat(text);
  };

  // activeMcpServers / activeCustomSkills 仍供 settings section 计数；
  // 流式 chat 的 request body 现在不再带 context，留给后续 advisor /
  // takeover 切片再恢复。
  void activeMcpServers;
  void activeCustomSkills;

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

  const handleAddSkill = useCallback(() => {
    const name = newSkillName.trim();
    const description = newSkillDescription.trim();
    if (!name || !description) return;
    setCustomSkills((prev) => [
      ...prev,
      { id: newId(), name, description, enabled: true },
    ]);
    setNewSkillName("");
    setNewSkillDescription("");
  }, [newSkillName, newSkillDescription]);

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
      const response = await fetch(`/api/ai/model/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(modelConfig),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as ModelCheckResponse;
      setModelCheckResult(payload);
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
  }, [modelConfig]);

  if (!open) return null;

  return (
    <aside
      className={cn(
        "relative hidden h-full min-h-0 min-w-0 flex-col border-l",
        "border-slate-700/50 bg-[#0a0f18]/95 backdrop-blur-2xl lg:flex"
      )}
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
              AICC 助手
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
        <TabButton
          active={activeTab === "settings"}
          icon={<SettingsIcon className="size-3.5" />}
          label="设置"
          onClick={() => onTabChange("settings")}
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
        {activeTab === "chat" ? (
          <ChatPanel
            chatLogRef={chatLogRef}
            chatError={chatError}
            chatRunSummary={chatRunSummary}
            chatMode={chatMode}
            commandInput={commandInput}
            messages={messages}
            onChatModeChange={setChatMode}
            onCommandInputChange={setCommandInput}
            onQuickCommand={sendChat}
            onSubmit={onSubmitChat}
            busy={busy}
            stop={stop}
          />
        ) : (
          <SettingsPanel
            activeCustomSkillsCount={activeCustomSkills.length}
            activeMcpServersCount={activeMcpServers.length}
            checkingModel={checkingModel}
            customSkills={customSkills}
            mcpServers={mcpServers}
            modelCheckResult={modelCheckResult}
            modelConfig={modelConfig}
            modelPresetOptions={modelPresetOptions}
            newServerEndpoint={newServerEndpoint}
            newServerName={newServerName}
            newServerTransport={newServerTransport}
            newSkillDescription={newSkillDescription}
            newSkillName={newSkillName}
            onAddServer={handleAddServer}
            onAddSkill={handleAddSkill}
            onCheckModel={() => void checkModelConnection()}
            onClearMessages={() => setMessages([])}
            onModelConfigChange={setModelConfig}
            onNewServerEndpointChange={setNewServerEndpoint}
            onNewServerNameChange={setNewServerName}
            onNewServerTransportChange={setNewServerTransport}
            onNewSkillDescriptionChange={setNewSkillDescription}
            onNewSkillNameChange={setNewSkillName}
            onProjectMcpEnabledChange={setProjectMcpEnabled}
            onRefreshSkills={() => void refreshRegisteredSkills()}
            onRemoveCustomSkill={(id) =>
              setCustomSkills((prev) => prev.filter((s) => s.id !== id))
            }
            onRemoveServer={(id) =>
              setMcpServers((prev) => prev.filter((s) => s.id !== id))
            }
            onToggleCustomSkill={(id, enabled) =>
              setCustomSkills((prev) =>
                prev.map((s) => (s.id === id ? { ...s, enabled } : s))
              )
            }
            onToggleServer={(id, enabled) =>
              setMcpServers((prev) =>
                prev.map((s) => (s.id === id ? { ...s, enabled } : s))
              )
            }
            projectMcpEnabled={projectMcpEnabled}
            registeredSkills={registeredSkills}
            selectedPreset={selectedPreset}
            skillsError={skillsError}
            skillsLoading={skillsLoading}
          />
        )}
      </div>
    </aside>
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

interface InputRowProps {
  label?: string;
  hint?: string;
  children: React.ReactNode;
}

function InputRow({ label, hint, children }: InputRowProps) {
  return (
    <label className="flex flex-col gap-1.5">
      {label && (
        <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
          {label}
        </span>
      )}
      {children}
      {hint && <span className="text-[10px] text-slate-600">{hint}</span>}
    </label>
  );
}

const INPUT_CLASS =
  "h-8 w-full rounded-md border border-cyan-300/12 bg-slate-950/40 px-2 text-xs text-slate-100 placeholder:text-slate-600 focus:border-cyan-300/40 focus:outline-none focus:ring-1 focus:ring-cyan-300/30";

const SELECT_CLASS =
  "h-8 w-full rounded-md border border-cyan-300/12 bg-slate-950/40 px-2 text-xs text-slate-100 focus:border-cyan-300/40 focus:outline-none focus:ring-1 focus:ring-cyan-300/30";

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
  busy: boolean;
  stop: () => void;
  onChatModeChange: (mode: AIChatMode) => void;
  onCommandInputChange: (next: string) => void;
  onQuickCommand: (cmd: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function ChatPanel({
  messages,
  chatLogRef,
  chatError,
  chatRunSummary,
  chatMode,
  commandInput,
  busy,
  stop,
  onChatModeChange,
  onCommandInputChange,
  onQuickCommand,
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
          messages.map((m) => <MessageBlock key={m.id} message={m} />)
        )}
      </div>

      <div className="border-t border-slate-700/50 px-3 py-2">
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
          <div className="flex items-center justify-between text-[10px] text-slate-500">
            <span>
              {busy
                ? "Thinking…"
                : chatMode === "ask"
                  ? "Ask mode: answer-only guidance"
                  : "Command mode: scenario changes allowed"}
            </span>
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
        {mode === "ask" ? "Explain and plan" : "Tools can change scenario"}
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

function MessageBlock({ message }: { message: UIMessage }) {
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

export type { MCPServerConfig, CustomSkillConfig, ModelConfig };

// ────────────────────────────────────────────────────────────────────────────
// Settings Panel
// ────────────────────────────────────────────────────────────────────────────

interface SettingsPanelProps {
  modelConfig: ModelConfig;
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
  onCheckModel: () => void;
  onProjectMcpEnabledChange: (enabled: boolean) => void;
  onAddServer: () => void;
  onRemoveServer: (id: string) => void;
  onToggleServer: (id: string, enabled: boolean) => void;
  onNewServerNameChange: (v: string) => void;
  onNewServerEndpointChange: (v: string) => void;
  onNewServerTransportChange: (t: "stdio" | "sse" | "http") => void;
  onAddSkill: () => void;
  onRemoveCustomSkill: (id: string) => void;
  onToggleCustomSkill: (id: string, enabled: boolean) => void;
  onNewSkillNameChange: (v: string) => void;
  onNewSkillDescriptionChange: (v: string) => void;
  onRefreshSkills: () => void;
  onClearMessages: () => void;
}

function SettingsPanel(props: SettingsPanelProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
      <ModelSection {...props} />
      <McpSection {...props} />
      <SkillsSection {...props} />
      <DangerZone onClearMessages={props.onClearMessages} />
    </div>
  );
}

function ModelSection({
  modelConfig,
  modelPresetOptions,
  selectedPreset,
  modelCheckResult,
  checkingModel,
  onModelConfigChange,
  onCheckModel,
}: SettingsPanelProps) {
  const update = (patch: Partial<ModelConfig>) =>
    onModelConfigChange({ ...modelConfig, ...patch });

  return (
    <Card className="border-cyan-300/12 bg-[#07111d]/82">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span className="inline-flex items-center gap-2 text-slate-100">
            <Cpu className="size-4 text-cyan-200" />
            模型配置
          </span>
          <Button
            className="h-7 gap-1.5 px-2.5 text-[11px]"
            disabled={checkingModel}
            onClick={onCheckModel}
            size="sm"
            variant="tactical"
          >
            {checkingModel ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <Plug className="size-3" />
            )}
            连接测试
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        <div className="grid grid-cols-2 gap-2">
          <InputRow label="Provider">
            <select
              className={SELECT_CLASS}
              onChange={(e) => update({ provider: e.target.value })}
              value={modelConfig.provider}
            >
              {MODEL_PROVIDER_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </InputRow>
          <InputRow label="预设模型">
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
          </InputRow>
        </div>

        <InputRow label="模型名" hint="自定义模型可以直接输入名称">
          <input
            className={INPUT_CLASS}
            onChange={(e) => update({ model: e.target.value })}
            placeholder="例如 gpt-4o-mini"
            value={modelConfig.model}
          />
        </InputRow>

        <InputRow
          label="Base URL"
          hint="留空则使用 provider 默认；自建/反代必填"
        >
          <input
            className={INPUT_CLASS}
            onChange={(e) => update({ baseUrl: e.target.value })}
            placeholder="https://api.openai.com/v1"
            value={modelConfig.baseUrl}
          />
        </InputRow>

        <InputRow label="API Key">
          <div className="relative">
            <KeyRound className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-slate-500" />
            <input
              className={cn(INPUT_CLASS, "pl-7")}
              onChange={(e) => update({ apiKey: e.target.value })}
              placeholder="sk-..."
              type="password"
              value={modelConfig.apiKey}
            />
          </div>
        </InputRow>

        {modelCheckResult && (
          <div
            className={cn(
              "rounded-md border px-2.5 py-2 text-[11px]",
              modelCheckResult.status === "ok"
                ? "border-emerald-300/30 bg-emerald-300/8 text-emerald-100"
                : modelCheckResult.status === "partial"
                  ? "border-amber-300/30 bg-amber-300/8 text-amber-100"
                  : "border-red-300/30 bg-red-300/8 text-red-100"
            )}
          >
            <div className="flex items-center gap-1.5 font-medium">
              {modelCheckResult.status === "ok" ? (
                <CheckCircle2 className="size-3.5" />
              ) : (
                <XCircle className="size-3.5" />
              )}
              {modelCheckResult.message}
            </div>
            <div className="mt-1 text-[10px] opacity-80">
              endpoint: {modelCheckResult.endpoint || "N/A"} · auth:{" "}
              {modelCheckResult.auth_ok ? "ok" : "fail"} · models:{" "}
              {modelCheckResult.models_listed ? "ok" : "fail"}
            </div>
            {modelCheckResult.checked_model && (
              <div className="mt-0.5 text-[10px] opacity-80">
                model: {modelCheckResult.checked_model} ·{" "}
                {modelCheckResult.checked_model_exists ? "exists" : "missing"}
              </div>
            )}
            {modelCheckResult.sample_models &&
              modelCheckResult.sample_models.length > 0 && (
                <div className="mt-0.5 text-[10px] opacity-80">
                  sample:{" "}
                  {modelCheckResult.sample_models.slice(0, 5).join(", ")}
                </div>
              )}
            {modelCheckResult.error && (
              <div className="mt-0.5 text-[10px] opacity-80">
                err: {modelCheckResult.error}
              </div>
            )}
          </div>
        )}

        <div className="rounded-md border border-emerald-300/15 bg-emerald-300/[0.04] px-2.5 py-1.5 text-[10px] text-emerald-200/80">
          模型配置通过 X-AICC-Model-* header 在每次请求时下发后端，实时生效。
          若留空则使用后端环境变量默认配置。
        </div>
      </CardContent>
    </Card>
  );
}

function McpSection({
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
}: SettingsPanelProps) {
  return (
    <Card className="border-cyan-300/12 bg-[#07111d]/82">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span className="inline-flex items-center gap-2 text-slate-100">
            <Plug className="size-4 text-cyan-200" />
            MCP Servers
          </span>
          <Badge
            className="bg-cyan-300/10 text-[10px] text-cyan-100"
            variant="muted"
          >
            {activeMcpServersCount} 启用
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        <label className="flex items-center justify-between rounded-md border border-cyan-300/10 bg-slate-950/35 px-2.5 py-1.5 text-[11px] text-slate-200">
          <span>项目内置 MCP</span>
          <input
            checked={projectMcpEnabled}
            className="size-3.5 accent-cyan-400"
            onChange={(e) => onProjectMcpEnabledChange(e.target.checked)}
            type="checkbox"
          />
        </label>

        <div className="space-y-2">
          {mcpServers.length === 0 ? (
            <div className="rounded-md border border-dashed border-cyan-300/12 px-2.5 py-2 text-center text-[11px] text-slate-500">
              暂无 MCP server
            </div>
          ) : (
            mcpServers.map((server) => (
              <div
                className="rounded-md border border-cyan-300/10 bg-slate-950/30 p-2 text-xs"
                key={server.id}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium text-slate-100">
                        {server.name}
                      </span>
                      <span className="rounded bg-cyan-300/10 px-1.5 py-0.5 text-[9px] uppercase text-cyan-200">
                        {server.transport}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-[10px] text-slate-500">
                      {server.endpoint}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <input
                      checked={server.enabled}
                      className="size-3.5 accent-cyan-400"
                      onChange={(e) =>
                        onToggleServer(server.id, e.target.checked)
                      }
                      type="checkbox"
                    />
                    <Button
                      aria-label="移除该 MCP server"
                      className="size-6 text-slate-500 hover:text-red-300"
                      onClick={() => onRemoveServer(server.id)}
                      size="icon"
                      variant="ghost"
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2 rounded-md border border-cyan-300/10 bg-slate-950/20 p-2.5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            添加新 MCP server
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <input
              className={cn(INPUT_CLASS, "col-span-2")}
              onChange={(e) => onNewServerNameChange(e.target.value)}
              placeholder="名称"
              value={newServerName}
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
              <option value="stdio">stdio</option>
              <option value="sse">sse</option>
              <option value="http">http</option>
            </select>
          </div>
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewServerEndpointChange(e.target.value)}
            placeholder="endpoint（如 stdio://... 或 https://...）"
            value={newServerEndpoint}
          />
          <Button
            className="w-full gap-1.5"
            disabled={!newServerName.trim() || !newServerEndpoint.trim()}
            onClick={onAddServer}
            size="sm"
            variant="tactical"
          >
            <Plus className="size-3.5" /> 添加 MCP server
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SkillsSection({
  registeredSkills,
  skillsLoading,
  skillsError,
  customSkills,
  activeCustomSkillsCount,
  newSkillName,
  newSkillDescription,
  onRefreshSkills,
  onAddSkill,
  onRemoveCustomSkill,
  onToggleCustomSkill,
  onNewSkillNameChange,
  onNewSkillDescriptionChange,
}: SettingsPanelProps) {
  return (
    <Card className="border-cyan-300/12 bg-[#07111d]/82">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span className="inline-flex items-center gap-2 text-slate-100">
            <Wrench className="size-4 text-cyan-200" />
            技能
          </span>
          <div className="flex items-center gap-1.5">
            <Badge
              className="bg-cyan-300/10 text-[10px] text-cyan-100"
              variant="muted"
            >
              后端 {registeredSkills.length} · 自定义 {activeCustomSkillsCount}
            </Badge>
            <Button
              aria-label="刷新后端技能列表"
              className="size-6 text-slate-400 hover:text-cyan-100"
              disabled={skillsLoading}
              onClick={onRefreshSkills}
              size="icon"
              variant="ghost"
            >
              <RefreshCw
                className={cn("size-3", skillsLoading && "animate-spin")}
              />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {skillsError && (
          <div className="rounded-md border border-red-300/30 bg-red-300/8 px-2.5 py-1.5 text-[11px] text-red-100">
            刷新失败：{skillsError}
          </div>
        )}

        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            后端已注册（只读）
          </div>
          {registeredSkills.length === 0 ? (
            <div className="rounded-md border border-dashed border-cyan-300/12 px-2.5 py-2 text-center text-[11px] text-slate-500">
              {skillsLoading ? "加载中…" : "暂无"}
            </div>
          ) : (
            registeredSkills.map((skill) => (
              <div
                className="rounded-md border border-cyan-300/10 bg-slate-950/30 px-2 py-1.5 text-xs"
                key={skill.name}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-slate-100">
                    {skill.name}
                  </span>
                  <ChevronRight className="size-3 text-slate-600" />
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500">
                  {skill.description}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            自定义技能
          </div>
          {customSkills.length === 0 ? (
            <div className="rounded-md border border-dashed border-cyan-300/12 px-2.5 py-2 text-center text-[11px] text-slate-500">
              暂无自定义
            </div>
          ) : (
            customSkills.map((skill) => (
              <div
                className="rounded-md border border-cyan-300/10 bg-slate-950/30 px-2 py-1.5 text-xs"
                key={skill.id}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-slate-100">
                    {skill.name}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <input
                      checked={skill.enabled}
                      className="size-3.5 accent-cyan-400"
                      onChange={(e) =>
                        onToggleCustomSkill(skill.id, e.target.checked)
                      }
                      type="checkbox"
                    />
                    <Button
                      aria-label="删除自定义技能"
                      className="size-6 text-slate-500 hover:text-red-300"
                      onClick={() => onRemoveCustomSkill(skill.id)}
                      size="icon"
                      variant="ghost"
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500">
                  {skill.description}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2 rounded-md border border-cyan-300/10 bg-slate-950/20 p-2.5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            添加自定义技能
          </div>
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewSkillNameChange(e.target.value)}
            placeholder="技能名"
            value={newSkillName}
          />
          <input
            className={INPUT_CLASS}
            onChange={(e) => onNewSkillDescriptionChange(e.target.value)}
            placeholder="描述（给 AI 看的提示）"
            value={newSkillDescription}
          />
          <Button
            className="w-full gap-1.5"
            disabled={!newSkillName.trim() || !newSkillDescription.trim()}
            onClick={onAddSkill}
            size="sm"
            variant="tactical"
          >
            <Plus className="size-3.5" /> 添加技能
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DangerZone({ onClearMessages }: { onClearMessages: () => void }) {
  return (
    <Card className="border-red-400/15 bg-red-500/[0.03]">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-red-100">
          <Activity className="size-4" /> 数据
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button
          className="w-full gap-1.5"
          onClick={onClearMessages}
          size="sm"
          variant="danger"
        >
          <Trash2 className="size-3.5" /> 清空聊天记录
        </Button>
      </CardContent>
    </Card>
  );
}
