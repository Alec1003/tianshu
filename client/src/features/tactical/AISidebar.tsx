/**
 * AI Sidebar：右侧栏，支持「聊天 / 设置」两个 tab。
 *
 * 设计要点：
 * - 聊天：用 @ai-sdk/react `useChat` + ai-sdk v5 `DefaultChatTransport`
 *   接 POST /api/ai/chat 流式接口（SSE / UI message stream）。
 *   加密时用户填写的 model 配置通过 X-TianShu-Model-* header
 *   传到后端，后端 per-request 构造 pydantic-ai agent，让前端
 *   model 配置在流式路径上也真生效。流结束后拉
 *   /api/ai/runtime/scenario 刷新地图。
 * - 设置：MCP Servers（增删改 + enable toggle）/ Skills（后端已注册 + 用户
 *   自定义）/ 系统操作三段。模型配置已拆到独立 AI 模型配置中心。
 * - 持久化：modelConfig / mcpServers / projectMcpEnabled
 *   使用 tianshu.ai.* keys；customSkills 改由后端 skills folder 存储；chat 消息由于类型从
 *   ChatMessage 迁移到 UIMessage，另存为 tianshu.ai.messages.v2。
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
  ChevronDown,
  ChevronRight,
  CircleOff,
  Loader2,
  MessageSquare,
  Plus,
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
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  approveCommandProposal,
  createCustomSkill,
  deleteCustomSkill,
  getRuntimeScenario,
  listBuiltinMcpTools,
  listBackendSkills,
  listCommandProposals,
  listCustomSkills,
  rejectCommandProposal,
  updateCustomSkill,
  validateExternalMcpServer,
} from "@/api/ai";
import { Button } from "@/components/ui/button";
import type {
  CommandProposal,
  CustomSkill,
  CustomSkillCreatePayload,
  CustomSkillUpdatePayload,
  ExternalMcpTool,
  RegisteredSkill,
  SkillSchemaField,
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
import {
  readStorageItem,
  removeStorageItem,
  writeStorageItem,
} from "@/lib/legacyStorage";
import TacticalSettingsModal from "./TacticalSettingsModal";
import {
  buildChatRequestHeaders,
  formatChatError as formatChatTransportError,
} from "./chatTransport";

export type AISidebarTab = "chat" | "settings";
type ApprovalMode = "strict" | "smart" | "auto" | "off";
export type MCPServerTransport = "stdio" | "sse" | "http";
type MCPServerStatus = "unknown" | "validating" | "online" | "error";

interface MCPToolDefinition {
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

interface MCPServerConfig {
  id: string;
  name: string;
  endpoint: string;
  transport: MCPServerTransport;
  enabled: boolean;
  tools?: MCPToolDefinition[];
  status?: MCPServerStatus;
  statusMessage?: string;
  lastValidatedAt?: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  headers?: Record<string, string>;
  allowedTools?: string[];
  timeoutSeconds?: number;
}

export type MCPServerImportPayload = Omit<
  MCPServerConfig,
  "id" | "lastValidatedAt" | "status" | "statusMessage" | "tools"
>;

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

const PLAN_OPTIONS_TOOL_NAME = "propose_tactical_plan_options";

interface AISidebarProps {
  open: boolean;
  activeTab: AISidebarTab;
  onOpenChange: (open: boolean) => void;
  onTabChange: (tab: AISidebarTab) => void;
  layout?: "sidebar" | "workspace";
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
  docFolder?: string;
  panelClassName?: string;
  panelStyle?: CSSProperties;
  previewView?: "map" | "document";
  previewFile?: string | null;
  onOpenMapPreview?: () => void;
  onOpenDocumentPreview?: (filename?: string | null) => void;
  onDocumentGenerated?: () => void;
}

const STORAGE_KEY = {
  messagesV2: "tianshu.ai.messages.v2",
  mcpServers: "tianshu.ai.mcpServers",
  customSkills: "tianshu.ai.customSkills",
  model: MODEL_STORAGE_KEY.model,
  modelProfiles: MODEL_STORAGE_KEY.modelProfiles,
  activeModelProfileId: MODEL_STORAGE_KEY.activeModelProfileId,
  projectMcpEnabled: "tianshu.ai.projectMcpEnabled",
} as const;

const BUILTIN_MCP_SERVER_NAME = "TianShu MCP";
const BUILTIN_MCP_ENDPOINT = "stdio://local-tianshu-mcp";
const LEGACY_PLATFORM_PREFIX = "ai" + "cc";
const LEGACY_BUILTIN_MCP_ENDPOINT = `stdio://local-${LEGACY_PLATFORM_PREFIX}-mcp`;
const BUILTIN_MCP_STATUS_MESSAGE = "内置 MCP 由后端运行环境管理。";

const DOC_TOOLS_MCP_NAME = "doc-tools-mcp";
const DOC_TOOLS_MCP_ENDPOINT = "http://doc-tools-mcp:3010/";

const DEFAULT_MCP_SERVERS: MCPServerConfig[] = [
  {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `mcp-${Date.now()}`,
    name: BUILTIN_MCP_SERVER_NAME,
    endpoint: BUILTIN_MCP_ENDPOINT,
    transport: "stdio",
    enabled: true,
    status: "unknown",
    statusMessage: BUILTIN_MCP_STATUS_MESSAGE,
    tools: [],
  },
];

function stripLegacyModeGuard(text: string): string {
  return text
    .replace(
      /(?:Ask mode|ask mode)[^\n.]*\.?|如您希望减少审批往返[^\n。]*[。.]?/gi,
      ""
    )
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripDocumentApprovalNotice(text: string): string {
  return text.replace(
    /[，,]?\s*审批通过后(?:才)?可下载[。.]?/g,
    "，已自动同步至文档中心。"
  );
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
    const raw = readStorageItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function safeSave<T>(key: string, value: T): void {
  try {
    if (typeof window === "undefined") return;
    writeStorageItem(key, JSON.stringify(value));
  } catch {
    // ignore quota / privacy errors
  }
}

function safeRemove(key: string): void {
  try {
    if (typeof window === "undefined") return;
    removeStorageItem(key);
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

function transportFromValidated(
  transport: "stdio" | "streamable_http"
): MCPServerTransport {
  return transport === "stdio" ? "stdio" : "http";
}

function compactToolDescription(description?: string): string {
  return (
    description
      ?.split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean) || "该工具未提供描述。"
  );
}

function toolDefinitionsFromExternal(
  tools: ExternalMcpTool[]
): MCPToolDefinition[] {
  return tools.map((tool) => ({
    name: tool.name,
    description: chineseMcpToolDescription(tool.name, tool.description),
    inputSchema: tool.inputSchema,
    outputSchema: tool.outputSchema,
  }));
}

const MCP_TOOL_DESCRIPTIONS_ZH: Record<string, string> = {
  create_document: "创建文档。",
  open_document: "打开已有文档。",
  add_paragraph: "向文档添加段落。",
  add_table: "向文档添加表格。",
  create_docx: "创建保留 Word 结构与排版的文档。",
  save_file: "将 Markdown、文本或其他文件保存到当前项目文档中心。",
  list_documents: "列出当前项目已经生成的文档。",
  monte_carlo: "运行蒙特卡洛验证，评估当前兵力分配方案。",
  route_attack: "根据平台与目标组合的作战模式规划攻击路线。",
  route_model1: "规划直接攻击路线。",
  route_model2: "规划多角度攻击路线。",
  route_model3: "规划发射区域攻击路线。",
  route_model4: "通过航路点规划隐蔽渗透攻击路线。",
  route_return: "规划平台返回基地的路线。",
  route_refuel: "规划航迹上的空中加油点。",
  route_coverage: "规划多平台对多边形区域的曲线覆盖路线。",
};

function chineseMcpToolDescription(name: string, description?: string): string {
  const shortName = name.split("__").pop()?.split(".").pop() ?? name;
  return (
    MCP_TOOL_DESCRIPTIONS_ZH[shortName] ||
    (description && /[\u4e00-\u9fff]/.test(description)
      ? compactToolDescription(description)
      : `执行“${shortName}”工具操作。`)
  );
}

function validationTraceMessage(
  response: Awaited<ReturnType<typeof validateExternalMcpServer>>
): string {
  const traceText = response.trace
    .map((trace) => `${trace.action}:${trace.status} ${trace.message}`.trim())
    .join(" / ");
  return traceText || response.message;
}

function buildMcpValidationPayload(
  server: MCPServerImportPayload | MCPServerConfig
) {
  return {
    name: server.name,
    transport: server.transport,
    endpoint: server.endpoint,
    command: server.command,
    args: server.args,
    url: server.url,
    env: server.env,
    headers: server.headers,
    allowedTools: server.allowedTools,
    enabled: true,
    timeoutSeconds: server.timeoutSeconds,
  };
}

function isManagedRuntimeMcpPlaceholder(server: MCPServerConfig): boolean {
  const endpoint = (server.endpoint || "").trim().toLowerCase();
  return server.transport === "stdio" && isBuiltinMcpEndpoint(endpoint);
}

function isBuiltinMcpEndpoint(endpoint: string | undefined): boolean {
  const normalized = endpoint?.trim().toLowerCase();
  return (
    normalized === BUILTIN_MCP_ENDPOINT ||
    normalized === LEGACY_BUILTIN_MCP_ENDPOINT
  );
}

function includesLegacyPlatformText(text: string | undefined): boolean {
  return Boolean(text?.toLowerCase().includes(LEGACY_PLATFORM_PREFIX));
}

function normalizeMcpServerConfig(server: MCPServerConfig): MCPServerConfig {
  const endpoint = server.endpoint?.trim() || "";
  const looksLikeBrokenDocTools =
    (server.name || "").toLowerCase().includes("doc-tools") ||
    endpoint.toLowerCase().includes("doc-tools") ||
    (server.command || "").toLowerCase().includes("doc-tools") ||
    (server.args || []).some((arg) => arg.toLowerCase().includes("doc-tools"));
  if (looksLikeBrokenDocTools) {
    return {
      ...server,
      name: DOC_TOOLS_MCP_NAME,
      endpoint: DOC_TOOLS_MCP_ENDPOINT,
      transport: "http",
      command: "",
      args: [],
      url: DOC_TOOLS_MCP_ENDPOINT,
      status: "unknown",
      statusMessage: "文档工具服务已切换为内置 Streamable HTTP MCP。",
      tools: [],
    };
  }
  const legacyManagedName =
    (server.name || "").trim().toLowerCase() ===
      `${LEGACY_PLATFORM_PREFIX} mcp` &&
    !server.command &&
    (endpoint === "" || endpoint.toLowerCase().startsWith("stdio://local-"));
  if (!isBuiltinMcpEndpoint(endpoint) && !legacyManagedName) {
    return server;
  }
  return {
    ...server,
    name: BUILTIN_MCP_SERVER_NAME,
    endpoint: BUILTIN_MCP_ENDPOINT,
    transport: "stdio",
    command: "",
    args: [],
    url: "",
    statusMessage: includesLegacyPlatformText(server.statusMessage)
      ? BUILTIN_MCP_STATUS_MESSAGE
      : server.statusMessage || BUILTIN_MCP_STATUS_MESSAGE,
    tools: server.tools ?? [],
  };
}

function normalizeMcpServerConfigs(
  servers: MCPServerConfig[]
): MCPServerConfig[] {
  if (!Array.isArray(servers)) return DEFAULT_MCP_SERVERS;
  return servers.map(normalizeMcpServerConfig);
}

function mcpConfigWithoutId(
  server: MCPServerImportPayload | MCPServerConfig
): Omit<MCPServerConfig, "id"> {
  const { id: _id, ...rest } = server as MCPServerConfig;
  return rest;
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

/**
 * Extract a flat preview string from a UIMessage so empty assistant
 * messages can render a placeholder (“推理中…”) while the stream is
 * still warming up.
 */
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

function getToolName(part: unknown): string {
  const p = part as {
    type?: string;
    toolName?: string;
  };
  return p.toolName
    ? p.toolName
    : typeof p.type === "string" && p.type.startsWith("tool-")
      ? p.type.slice("tool-".length)
      : "tool";
}

function completedPlanToolSignature(messages: UIMessage[]): string | null {
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    if (message.role !== "assistant") continue;
    for (
      let partIndex = message.parts.length - 1;
      partIndex >= 0;
      partIndex -= 1
    ) {
      const part = message.parts[partIndex];
      if (!isToolOrDynamicToolUIPart(part)) continue;
      const p = part as { state?: string; output?: unknown };
      if (p.state !== "output-available") continue;
      if (getToolName(part) !== PLAN_OPTIONS_TOOL_NAME) continue;
      let outputSignature = "";
      try {
        outputSignature = JSON.stringify(p.output ?? "").slice(0, 240);
      } catch {
        outputSignature = String(p.output ?? "");
      }
      return `${message.id}:${partIndex}:${p.state}:${outputSignature}`;
    }
  }
  return null;
}

function completedDocumentToolSignature(messages: UIMessage[]): string | null {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex];
    if (message.role !== "assistant") continue;
    for (let partIndex = message.parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const part = message.parts[partIndex];
      if (!isToolOrDynamicToolUIPart(part) || getToolName(part) !== "doc-tools") continue;
      const p = part as { state?: string; output?: unknown };
      if (p.state !== "output-available") continue;
      let outputSignature = "";
      try {
        outputSignature = JSON.stringify(p.output ?? "").slice(0, 240);
      } catch {
        outputSignature = String(p.output ?? "");
      }
      return `${message.id}:${partIndex}:${p.state}:${outputSignature}`;
    }
  }
  return null;
}

function parseToolOutput(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function collectProposalIdsFromOutput(value: unknown): string[] {
  const output = parseToolOutput(value);
  const ids = new Set<string>();

  if (isRecord(output) && typeof output.proposalId === "string") {
    ids.add(output.proposalId);
  }

  if (isRecord(output) && Array.isArray(output.proposals)) {
    for (const item of output.proposals) {
      if (isRecord(item) && typeof item.proposalId === "string") {
        ids.add(item.proposalId);
      } else if (isRecord(item) && typeof item.id === "string") {
        ids.add(item.id);
      }
    }
  }

  return [...ids];
}

function planProposalIdsForMessage(message: UIMessage): string[] {
  const ids = new Set<string>();
  for (const part of message.parts) {
    if (!isToolOrDynamicToolUIPart(part)) continue;
    if (getToolName(part) !== PLAN_OPTIONS_TOOL_NAME) continue;
    const p = part as { state?: string; output?: unknown };
    if (p.state !== "output-available") continue;
    for (const id of collectProposalIdsFromOutput(p.output)) {
      ids.add(id);
    }
  }
  return [...ids];
}

function proposalIdsForMessages(messages: UIMessage[]): string[] {
  const ids = new Set<string>();
  for (const message of messages) {
    for (const part of message.parts) {
      if (!isToolOrDynamicToolUIPart(part)) continue;
      const toolPart = part as { output?: unknown };
      for (const id of collectProposalIdsFromOutput(toolPart.output)) {
        ids.add(id);
      }
    }
  }
  return [...ids];
}

function messageHasVisibleContent(message: UIMessage): boolean {
  return message.parts.some((part) => {
    if (isTextUIPart(part)) return Boolean(part.text);
    return isReasoningUIPart(part);
  });
}

function formatChatError(error: Error): string {
  const message = error.message || "Unknown chat error";
  if (
    message.includes("503") ||
    message.toLowerCase().includes("service unavailable") ||
    message.includes("No LLM configured")
  ) {
    return "No LLM is configured. Fill API Key in AI 模型配置中心, or set TIANSHU_LLM_MODEL and TIANSHU_LLM_API_KEY in the server environment.";
  }
  return message;
}

export default function AISidebar({
  open,
  activeTab,
  onOpenChange,
  onTabChange,
  layout = "sidebar",
  settingsOpen = false,
  onSettingsOpenChange,
  onApplyScenario,
  onResumePlay,
  mapBaseLayer,
  onMapBaseLayerChange,
  scenarioId,
  docFolder,
  panelClassName,
  panelStyle,
  previewView = "map",
  previewFile,
  onOpenMapPreview,
  onOpenDocumentPreview,
  onDocumentGenerated,
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
  const builtinMcpToolsLoadAttemptedRef = useRef(false);

  // —— 持久化状态 ——
  const [mcpServers, setMcpServers] = useState<MCPServerConfig[]>(() =>
    normalizeMcpServerConfigs(
      safeLoad<MCPServerConfig[]>(STORAGE_KEY.mcpServers, DEFAULT_MCP_SERVERS)
    )
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
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("auto");
  const [commandProposals, setCommandProposals] = useState<CommandProposal[]>(
    []
  );
  const [proposalBusyId, setProposalBusyId] = useState<string | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [executingPlanLabel, setExecutingPlanLabel] = useState<string | null>(null);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const conversationProposalIdsRef = useRef<Set<string>>(new Set());
  const autoApprovedDocumentProposalIdsRef = useRef<Set<string>>(new Set());

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
  const docFolderRef = useRef<string | undefined>(docFolder);
  useEffect(() => {
    docFolderRef.current = docFolder;
  }, [docFolder]);
  const approvalModeRef = useRef<ApprovalMode>(approvalMode);
  useEffect(() => {
    approvalModeRef.current = approvalMode;
  }, [approvalMode]);

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/chat",
        headers: () => {
          const token = getStoredToken();
          return buildChatRequestHeaders({
            approvalMode: approvalModeRef.current,
            modelConfig: modelConfigRef.current,
            modelProviderId: modelProviderIdRef.current,
            // The backend uses this as the provider-config identity.  The
            // selected model itself is sent separately below; using the
            // provider id here keeps custom profiles resolvable.
            modelConfigId: modelProviderIdRef.current,
            docFolder: docFolderRef.current,
            scenarioId: scenarioIdRef.current,
            token,
          });
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
  const refreshCommandProposals = useCallback(async (): Promise<void> => {
    try {
      const payload = await listCommandProposals();
      setCommandProposals(
        payload.proposals.filter((proposal) =>
          conversationProposalIdsRef.current.has(proposal.id)
        )
      );
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

  // A gated agent turn stays open while the backend waits for approval. Poll
  // the persisted queue during that wait so the approval card appears before
  // the stream resumes; this does not change the backend execution flow.
  useEffect(() => {
    if (!open || !busy) return;
    const timer = window.setInterval(() => {
      void refreshCommandProposals();
    }, 500);
    return () => window.clearInterval(timer);
  }, [busy, open, refreshCommandProposals]);

  // ─── 按 scenario 隔离 chat 历史 ─────────────────────────────────────────
  // 设计：localStorage key = `tianshu.ai.messages.v2:<scenarioId>`。
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
    conversationProposalIdsRef.current.clear();
    autoApprovedDocumentProposalIdsRef.current.clear();
    setCommandProposals([]);
    setProposalError(null);
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

  useEffect(() => {
    const proposalIds = proposalIdsForMessages(messages);
    const newProposalIds = proposalIds.filter(
      (id) => !conversationProposalIdsRef.current.has(id)
    );
    if (newProposalIds.length === 0) return;
    for (const id of newProposalIds) {
      conversationProposalIdsRef.current.add(id);
    }
    void refreshCommandProposals();
  }, [messages, refreshCommandProposals]);

  // 流结束后：
  //   1) 拉一次 runtime scenario，应用到 game（让 AI 改的单位/任务可见）。
  //   2) 扫描最后一条 assistant 消息的工具调用：如果最终生命周期工具是
  //      ``simulation_start``，等价于用户按下 Play，自动启动客户端 step
  //      循环，让仿真持续推进；``simulation_step(N)`` 视为推演 N 步即停，
  //      不触发；``simulation_pause`` / ``simulation_stop`` 自然保持暂停。
  // 只在 “busy → ready” 转换时触发一次，避免初始化 / 错误后乱拉。
  const wasBusyRef = useRef(false);
  const lastPlanToolSignatureRef = useRef<string | null>(null);
  const lastDocumentToolSignatureRef = useRef<string | null>(null);
  useEffect(() => {
    if (busy) {
      wasBusyRef.current = true;
      return;
    }
    if (!wasBusyRef.current) return;
    wasBusyRef.current = false;
    const shouldRefreshRuntime = status === "ready";
    // 找最近一条 assistant 消息，扫它的 tool 调用决定推演意图。
    // ai-sdk v5 的 tool part 有两种形态：
    //   - 静态工具：``{ type: 'tool-<name>', ... }``（pydantic-ai @agent.tool 走这条）
    //   - 动态工具：``{ type: 'dynamic-tool', toolName, ... }``
    // 两种都要兼容，从 ``type`` / ``toolName`` 提取真实工具名。
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === "assistant");
    const lastLifecycleTool = (() => {
      if (!shouldRefreshRuntime) return null;
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
        const toolName = getToolName(part);
        if (lifecycleTools.has(toolName)) return toolName;
      }
      return null;
    })();
    void (async () => {
      if (shouldRefreshRuntime) {
        try {
          const data = await getRuntimeScenario();
          if (data && typeof data === "object") {
            onApplyScenario?.(data);
          }
        } catch (err) {
          console.error(
            "[TianShu] refresh runtime scenario after AI run failed",
            err
          );
        }
        // 等 onApplyScenario 完成（同步路径，loadScenarioFromObject 立刻生效）
        // 后再触发 play，避免在 reload 过程中开 loop 撞到 stale scenario。
        if (lastLifecycleTool === "simulation_start" && onResumePlay) {
          try {
            await onResumePlay();
          } catch (err) {
            console.error(
              "[TianShu] auto-resume play after AI start failed",
              err
            );
          }
        }
      }
      await refreshCommandProposals();
      // Proposal persistence is scheduled from the streaming request.  Do a
      // short follow-up refresh so the approval card is visible even when
      // the stream finishes just before the database write is committed.
      for (const delay of [250, 750]) {
        await new Promise((resolve) => window.setTimeout(resolve, delay));
        await refreshCommandProposals();
      }
    })();
  }, [
    busy,
    messages,
    onApplyScenario,
    onResumePlay,
    refreshCommandProposals,
    status,
  ]);

  useEffect(() => {
    if (!onDocumentGenerated || busy) return;
    const signature = completedDocumentToolSignature(messages);
    if (
      !signature ||
      signature === lastDocumentToolSignatureRef.current
    ) {
      return;
    }
    lastDocumentToolSignatureRef.current = signature;
    onDocumentGenerated();
  }, [busy, messages, onDocumentGenerated]);

  // —— 设置表单局部状态 ——
  useEffect(() => {
    if (!open) return;
    const signature = completedPlanToolSignature(messages);
    if (!signature || signature === lastPlanToolSignatureRef.current) return;
    lastPlanToolSignatureRef.current = signature;
    const timer = window.setTimeout(() => {
      void refreshCommandProposals();
    }, 250);
    return () => window.clearTimeout(timer);
  }, [messages, open, refreshCommandProposals]);

  const handleNewConversation = useCallback((): void => {
    if (busy) {
      try {
        stop();
      } catch {
        // ignore: stop() before any in-flight request is a no-op
      }
    }
    wasBusyRef.current = false;
    lastPlanToolSignatureRef.current = null;
    lastDocumentToolSignatureRef.current = null;
    conversationProposalIdsRef.current.clear();
    autoApprovedDocumentProposalIdsRef.current.clear();
    setCommandInput("");
    setProposalError(null);
    setCommandProposals([]);
    setMessages([]);
    removeStorageItem(messagesKeyFor(scenarioId));
  }, [busy, scenarioId, setMessages, stop]);

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
  }, [messages, commandProposals, status, open, activeTab]);

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
      const messageText = [buildCustomSkillPrompt(activeCustomSkills), trimmed]
        .filter(Boolean)
        .join("\n\n");
      sendMessage({ text: messageText });
    },
    [activeCustomSkills, busy, onTabChange, sendMessage]
  );

  const handleApprovalModeChange = useCallback((mode: ApprovalMode): void => {
    approvalModeRef.current = mode;
    setApprovalMode(mode);
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
      const selected = commandProposals.find((proposal) => proposal.id === proposalId);
      const selectedMetadata = selected ? planMetadata(selected) : null;
      if (selectedMetadata?.kind === "tactical_plan_option") {
        setExecutingPlanLabel(
          selectedMetadata.optionIndex
            ? `方案${String.fromCharCode(64 + selectedMetadata.optionIndex)}`
            : selectedMetadata.label || "方案"
        );
      }
      setProposalBusyId(proposalId);
      setProposalError(null);
      try {
        const response = await approveCommandProposal(proposalId);
        if (response.snapshot?.scenario) {
          onApplyScenario?.(response.snapshot.scenario);
        }
        if (
          response.proposal.steps.some(
            (step) => step.skill === "simulation_start"
          ) &&
          onResumePlay
        ) {
          await onResumePlay();
        }
        if (selected && isDocumentProposal(selected)) {
          // Document tools are non-interactive from the user's perspective:
          // once the backend has executed the tool, refresh Document Center
          // immediately instead of presenting a second download/approval step.
          onDocumentGenerated?.();
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
    [
      commandProposals,
      onApplyScenario,
      onDocumentGenerated,
      onResumePlay,
      refreshCommandProposals,
    ]
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

  useEffect(() => {
    const pendingDocuments = commandProposals.filter(
      (proposal) =>
        proposal.status === "pending" &&
        isDocumentProposal(proposal) &&
        !autoApprovedDocumentProposalIdsRef.current.has(proposal.id)
    );
    if (pendingDocuments.length === 0) return;
    for (const proposal of pendingDocuments) {
      autoApprovedDocumentProposalIdsRef.current.add(proposal.id);
      void handleApproveProposal(proposal.id);
    }
  }, [commandProposals, handleApproveProposal]);

  // activeMcpServers are still managed in settings; external MCP runtime
  // connections are configured server-side through TIANSHU_EXTERNAL_MCP_SERVERS.
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

  const validateMcpConfig = useCallback(
    async (
      server: MCPServerImportPayload | MCPServerConfig
    ): Promise<Omit<MCPServerConfig, "id">> => {
      const normalizedServer = normalizeMcpServerConfig({
        id: "pending",
        status: "unknown",
        ...server,
      });
      if (isManagedRuntimeMcpPlaceholder(normalizedServer)) {
        const response = await listBuiltinMcpTools();
        if (!response.ok) {
          throw new Error(`${BUILTIN_MCP_SERVER_NAME}: ${response.message}`);
        }
        return {
          ...mcpConfigWithoutId(normalizedServer),
          name: BUILTIN_MCP_SERVER_NAME,
          endpoint: BUILTIN_MCP_ENDPOINT,
          transport: "stdio",
          command: "",
          args: [],
          url: "",
          tools: toolDefinitionsFromExternal(response.tools),
          status: "online",
          statusMessage: response.message,
          lastValidatedAt: new Date().toISOString(),
        };
      }
      const response = await validateExternalMcpServer(
        buildMcpValidationPayload(server)
      );
      const statusMessage = validationTraceMessage(response);
      if (!response.ok) {
        throw new Error(`${server.name}: ${statusMessage}`);
      }
      return {
        ...mcpConfigWithoutId(server),
        transport: transportFromValidated(response.transport),
        endpoint: server.endpoint || server.url || "",
        tools: toolDefinitionsFromExternal(response.tools),
        status: "online",
        statusMessage,
        lastValidatedAt: new Date().toISOString(),
      };
    },
    []
  );

  const handleImportMcpServers = useCallback(
    async (servers: MCPServerImportPayload[]): Promise<void> => {
      const validatedServers: MCPServerConfig[] = [];
      for (const server of servers) {
        const validated = await validateMcpConfig(server);
        validatedServers.push({
          id: newId(),
          ...validated,
        });
      }
      setMcpServers((prev) => [...prev, ...validatedServers]);
    },
    [validateMcpConfig]
  );

  const handleUpdateMcpServer = useCallback(
    async (id: string, server: MCPServerImportPayload): Promise<void> => {
      setMcpServers((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                ...server,
                status: "validating",
                statusMessage: "正在验证 MCP 服务并读取工具列表。",
              }
            : item
        )
      );
      try {
        const validated = await validateMcpConfig(server);
        setMcpServers((prev) =>
          prev.map((item) => (item.id === id ? { id, ...validated } : item))
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "MCP 服务验证失败。";
        setMcpServers((prev) =>
          prev.map((item) =>
            item.id === id
              ? {
                  ...item,
                  ...server,
                  status: "error",
                  statusMessage: message,
                  lastValidatedAt: new Date().toISOString(),
                }
              : item
          )
        );
        throw error;
      }
    },
    [validateMcpConfig]
  );

  const handleValidateMcpServer = useCallback(
    async (id: string): Promise<void> => {
      const server = mcpServers.find((item) => item.id === id);
      if (!server) return;
      setMcpServers((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                status: "validating",
                statusMessage: "正在重新连接 MCP 服务并刷新工具列表。",
              }
            : item
        )
      );
      try {
        const validated = await validateMcpConfig(server);
        setMcpServers((prev) =>
          prev.map((item) => (item.id === id ? { id, ...validated } : item))
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "MCP 服务验证失败。";
        setMcpServers((prev) =>
          prev.map((item) =>
            item.id === id
              ? {
                  ...item,
                  status: "error",
                  statusMessage: message,
                  lastValidatedAt: new Date().toISOString(),
                }
              : item
          )
        );
      }
    },
    [mcpServers, validateMcpConfig]
  );

  useEffect(() => {
    if (builtinMcpToolsLoadAttemptedRef.current) return;
    const builtinServers = mcpServers.filter(
      (server) => isManagedRuntimeMcpPlaceholder(server)
    );
    if (builtinServers.length === 0) return;
    builtinMcpToolsLoadAttemptedRef.current = true;
    for (const server of builtinServers) {
      void handleValidateMcpServer(server.id);
    }
  }, [handleValidateMcpServer, mcpServers]);

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
        onClearMessages={handleNewConversation}
        onImportMcpServers={handleImportMcpServers}
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
        onUpdateMcpServer={handleUpdateMcpServer}
        onValidateMcpServer={(id) => void handleValidateMcpServer(id)}
        open={settingsOpen}
        projectMcpEnabled={projectMcpEnabled}
        registeredSkills={registeredSkills}
        selectedPreset={selectedPreset}
        skillsError={skillsError}
        skillsLoading={skillsLoading}
      />
      {(layout === "workspace" || open) && (
        <aside
          className={cn(
            "relative hidden h-full min-h-0 min-w-0 flex-col overflow-hidden lg:flex",
            layout === "workspace"
              ? "rounded-[28px] border border-white/[0.08] bg-[#08111a] shadow-[0_28px_90px_rgba(0,0,0,0.32)]"
              : "border-l border-tactical-line bg-tactical-panel/96 backdrop-blur-2xl",
            panelClassName
          )}
          style={panelStyle}
        >
          {/* 顶部：标题 + tabs + 关闭 */}
          <header
            className={cn(
              "flex items-center justify-between gap-2 px-4 py-3",
              layout === "workspace"
                ? "border-b border-white/[0.08] bg-[linear-gradient(180deg,rgba(13,24,36,0.96),rgba(8,17,26,0.9))]"
                : "border-b border-tactical-line"
            )}
          >
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "grid size-8 place-items-center rounded-xl text-tactical-accent",
                  layout === "workspace"
                    ? "border border-cyan-300/12 bg-cyan-300/[0.08]"
                    : "border border-tactical-line bg-white/[0.035]"
                )}
              >
                <Sparkles className="size-3.5" />
              </div>
              <div>
                {layout === "workspace" && (
                  <div className="mb-1.5">
                    <div className="text-[10px] uppercase tracking-[0.32em] text-slate-500">
                      Agent Workspace
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-100">
                      AI 作战智能体
                    </div>
                  </div>
                )}
                <div className="text-[10px] uppercase tracking-[0.32em] text-slate-500">
                  情报参谋席
                </div>
                <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-100 leading-tight">
                  工具链与指令审批
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
            <div className="flex items-center gap-1.5">
              <Button
                aria-label="新建对话"
                className="h-7 gap-1.5 px-2 text-[11px] text-slate-300 hover:text-slate-100"
                onClick={handleNewConversation}
                size="sm"
                type="button"
                variant="ghost"
                title="清空当前场景的聊天记录"
              >
                <Plus className="size-3.5" />
                <span>新建对话</span>
              </Button>
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
            </div>
          </header>

          <div
            className={cn(
              "flex items-center gap-1 px-3 py-1.5",
              layout === "workspace"
                ? "border-b border-white/[0.08] bg-white/[0.02]"
                : "border-b border-tactical-line"
            )}
          >
            <TabButton
              active={activeTab === "chat"}
              icon={<MessageSquare className="size-3.5" />}
              label="聊天"
              onClick={() => onTabChange("chat")}
            />
            <div className="ml-auto text-[11px] text-slate-500">
              {chatError ? (
                <span className="inline-flex items-center gap-1 text-red-300">
                  <AlertTriangle className="size-3" /> 异常
                </span>
              ) : (
                <span>待命</span>
              )}
            </div>
          </div>

          {/* Tab 内容 */}
          <div className="flex min-h-0 flex-1 flex-col">
            {activeTab === "chat" && (
              <ChatPanel
                chatLogRef={chatLogRef}
                chatError={chatError}
                approvalMode={approvalMode}
                commandInput={commandInput}
                commandProposals={commandProposals}
                proposalBusyId={proposalBusyId}
                proposalError={proposalError}
                executingPlanLabel={executingPlanLabel}
                messages={messages}
                onApproveProposal={(id) => void handleApproveProposal(id)}
                onApprovalModeChange={handleApprovalModeChange}
                onCommandInputChange={setCommandInput}
                onOpenModelSettings={() => navigate("/ai-models")}
                onRejectProposal={(id) => void handleRejectProposal(id)}
                onSubmit={onSubmitChat}
                layout={layout}
                onOpenDocumentPreview={onOpenDocumentPreview}
                onOpenMapPreview={onOpenMapPreview}
                previewFile={previewFile}
                previewView={previewView}
                busy={busy}
                stop={stop}
              />
            )}
          </div>
        </aside>
      )}
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
  layout: "sidebar" | "workspace";
  approvalMode: ApprovalMode;
  commandInput: string;
  commandProposals: CommandProposal[];
  proposalBusyId: string | null;
  proposalError: string | null;
  executingPlanLabel: string | null;
  busy: boolean;
  stop: () => void;
  onApproveProposal: (proposalId: string) => void;
  onApprovalModeChange: (mode: ApprovalMode) => void;
  onCommandInputChange: (next: string) => void;
  onOpenModelSettings: () => void;
  onRejectProposal: (proposalId: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  previewView: "map" | "document";
  previewFile?: string | null;
  onOpenMapPreview?: () => void;
  onOpenDocumentPreview?: (filename?: string | null) => void;
}

function ChatPanel({
  messages,
  chatLogRef,
  chatError,
  layout,
  approvalMode,
  commandInput,
  commandProposals,
  proposalBusyId,
  proposalError,
  executingPlanLabel,
  busy,
  stop,
  onApproveProposal,
  onApprovalModeChange,
  onCommandInputChange,
  onOpenModelSettings,
  onRejectProposal,
  onSubmit,
  previewView,
  previewFile,
  onOpenMapPreview,
  onOpenDocumentPreview,
}: ChatPanelProps) {
  const chatErrorMessage = chatError ? formatChatTransportError(chatError) : "";
  const latestUserMessageId = useMemo(
    () =>
      [...messages].reverse().find((message) => message.role === "user")?.id,
    [messages]
  );
  const hasDocumentPreview = Boolean(previewFile);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={chatLogRef}
        className={cn(
          "flex-1 overflow-y-auto",
          layout === "workspace" ? "space-y-3 px-5 py-5" : "space-y-1 px-3 py-3"
        )}
      >
        {layout === "workspace" && (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_16rem]">
            <div className="rounded-[24px] border border-white/[0.08] bg-[linear-gradient(180deg,rgba(18,30,45,0.92),rgba(10,18,27,0.9))] px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <div className="text-[11px] uppercase tracking-[0.28em] text-cyan-300/65">
                Mission Copilot
              </div>
              <div className="mt-3 max-w-xl text-3xl font-semibold tracking-tight text-slate-100">
                以对话驱动推演、方案生成和运行时操作。
              </div>
              <div className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                中央对话区负责主交互，右侧工作台负责地图、文档和结果预览。现有
                Runtime 与后端链路保持不变。
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs transition-colors",
                    previewView === "map"
                      ? "border-cyan-300/40 bg-cyan-300/12 text-cyan-100"
                      : "border-white/[0.08] bg-white/[0.03] text-slate-300 hover:border-cyan-300/25 hover:text-slate-100"
                  )}
                  onClick={() => onOpenMapPreview?.()}
                  type="button"
                >
                  打开地图预览
                </button>
                <button
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs transition-colors",
                    previewView === "document"
                      ? "border-cyan-300/40 bg-cyan-300/12 text-cyan-100"
                      : "border-white/[0.08] bg-white/[0.03] text-slate-300 hover:border-cyan-300/25 hover:text-slate-100",
                    !hasDocumentPreview && "opacity-70"
                  )}
                  onClick={() => onOpenDocumentPreview?.(previewFile ?? null)}
                  type="button"
                >
                  {hasDocumentPreview ? "打开当前文档" : "切到文档工作台"}
                </button>
              </div>
            </div>
            <div className="rounded-[24px] border border-white/[0.08] bg-[#0b121a] px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
                Workspace State
              </div>
              <div className="mt-3 space-y-2 text-xs text-slate-400">
                <div className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                  <span>预览栏</span>
                  <span className="text-slate-100">
                    {previewView === "map" ? "地图" : "文档"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                  <span>文档绑定</span>
                  <span className="max-w-[9rem] truncate text-slate-100">
                    {previewFile ?? "未打开"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
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
        {proposalError && (
          <div className="mb-3 rounded-lg border border-red-300/20 bg-red-300/[0.05] px-2.5 py-2 text-[11px] text-red-100">
            {proposalError}
          </div>
        )}
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-xs text-slate-500">
            <Sparkles className="size-5 text-slate-600" />
            <div className="text-slate-400">查询态势或提交推演指令</div>
            <div className="text-[11px] text-slate-600">
              示例：开始推演、部署单位、查看战况
            </div>
          </div>
        ) : (
          messages.map((m) => {
            if (!messageHasVisibleContent(m)) return null;
            return (
              <div className="space-y-1" key={m.id}>
                <MessageBlock message={m} />
                {busy && m.id === latestUserMessageId ? (
                  <ThinkingBubble />
                ) : null}
              </div>
            );
          })
        )}
      </div>

      {(proposalError ||
        commandProposals.some((proposal) =>
          !isDocumentProposal(proposal) &&
          ["pending", "failed"].includes(proposal.status)
        )) && (
        <div className="max-h-[38vh] shrink-0 overflow-y-auto border-t border-cyan-300/15 bg-[#08121b] px-3 py-2">
          {executingPlanLabel && proposalBusyId && (
            <div className="mb-2 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.05] px-2.5 py-2 text-[11px] text-cyan-100">
              正在执行{executingPlanLabel}
            </div>
          )}
          <ApprovalQueuePanel
            busyId={proposalBusyId}
            error={proposalError}
            onApprove={onApproveProposal}
            onReject={onRejectProposal}
            proposals={commandProposals}
          />
        </div>
      )}

      <div
        className={cn(
          "border-t px-3 py-2",
          layout === "workspace"
            ? "border-white/[0.08] bg-[#09111a] px-5 py-4"
            : "border-slate-700/50"
        )}
      >
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
            placeholder="输入将改变场景的推演指令..."
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
            </div>
            <div className="flex items-center gap-1.5">
              <ApprovalModeSwitcher
                disabled={busy}
                mode={approvalMode}
                onModeChange={onApprovalModeChange}
              />
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
          </div>
        </form>
      </div>
    </div>
  );
}

interface PlanCardMetadata {
  kind?: string;
  title?: string;
  label?: string;
  description?: string;
  advantages?: string[];
  risks?: string[];
  optionIndex?: number;
  reasoningSummary?: string;
  planGroupKey?: string;
  optionKey?: string;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && !!item)
    : [];
}

function planMetadata(proposal: CommandProposal): PlanCardMetadata {
  const raw = proposal.plan_metadata ?? {};
  return {
    kind: typeof raw.kind === "string" ? raw.kind : undefined,
    title: typeof raw.title === "string" ? raw.title : undefined,
    label: typeof raw.label === "string" ? raw.label : undefined,
    description:
      typeof raw.description === "string" ? raw.description : undefined,
    advantages: stringList(raw.advantages),
    risks: stringList(raw.risks),
    optionIndex:
      typeof raw.optionIndex === "number" ? raw.optionIndex : undefined,
    reasoningSummary:
      typeof raw.reasoning_summary === "string"
        ? raw.reasoning_summary
        : undefined,
    planGroupKey:
      typeof raw.planGroupKey === "string" ? raw.planGroupKey : undefined,
    optionKey: typeof raw.optionKey === "string" ? raw.optionKey : undefined,
  };
}

function isDocumentProposal(proposal: CommandProposal): boolean {
  return proposal.steps.some((step) => {
    const skill = step.skill.toLowerCase();
    return (
      skill.includes("doc-tools") ||
      skill.includes("create_docx") ||
      skill.includes("create_document") ||
      skill.includes("save_file")
    );
  });
}

function skillLabel(skill: string): string {
  const labels: Record<string, string> = {
    move_unit: "路径规划",
    create_patrol_mission: "巡逻任务",
    create_strike_mission: "打击任务",
    attack_unit: "武器打击",
    update_weapon_quantity: "武器分配",
    simulation_start: "开始推演",
    simulation_step: "推进推演",
    update_unit_state: "状态调整",
    deploy_reference_point: "航路点",
  };
  return labels[skill] ?? skill.replace(/_/g, " ");
}

function parameterPreview(parameters: Record<string, unknown>): string {
  const picked = [
    parameters.unit_id,
    parameters.attacker_id,
    parameters.target_id,
    parameters.weapon_id,
    parameters.name,
  ]
    .filter((value): value is string => typeof value === "string" && !!value)
    .slice(0, 2);
  if (picked.length > 0) return picked.join(" -> ");
  const keys = Object.keys(parameters).slice(0, 3);
  return keys.length > 0 ? keys.join(", ") : "no parameters";
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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [dialogProposal, setDialogProposal] = useState<CommandProposal | null>(
    null
  );
  const active = proposals.filter(
    (proposal) =>
      !isDocumentProposal(proposal) &&
      ["pending", "failed"].includes(proposal.status)
  );
  const planGroups = active
    .slice()
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .map(planMetadata)
    .filter((metadata) => metadata.kind === "tactical_plan_option");
  const latestPlanGroup = planGroups
    .map((metadata) => metadata.planGroupKey)
    .filter((value): value is string => Boolean(value))[0];
  const seenPlanKeys = new Set<string>();
  const visible = active
    .filter((proposal) => {
      const metadata = planMetadata(proposal);
      if (metadata.kind !== "tactical_plan_option") return true;
      if (latestPlanGroup && metadata.planGroupKey !== latestPlanGroup) {
        return false;
      }
      const key = `${metadata.planGroupKey ?? ""}:${metadata.optionKey ?? metadata.optionIndex ?? metadata.title ?? proposal.id}`;
      if (seenPlanKeys.has(key)) return false;
      seenPlanKeys.add(key);
      return true;
    })
    .sort((left, right) => {
      const leftIndex = planMetadata(left).optionIndex ?? 999;
      const rightIndex = planMetadata(right).optionIndex ?? 999;
      return leftIndex - rightIndex;
    })
    .slice(0, 8);

  if (visible.length === 0 && !error) return null;

  return (
    <div className="mb-2 space-y-2">
      {error && (
        <div className="rounded-lg border border-red-300/20 bg-red-300/[0.05] px-2.5 py-2 text-[11px] text-red-100">
          {error}
        </div>
      )}
      {visible.map((proposal) => {
        const metadata = planMetadata(proposal);
        const isPlan = metadata.kind === "tactical_plan_option";
        const blocked = proposal.status === "blocked";
        const busy = busyId === proposal.id;
        const expanded = expandedId === proposal.id;
        const issueCount = proposal.adjudication.issues.length;
        const title =
          metadata.title ||
          proposal.command ||
          proposal.steps[0]?.summary ||
          "待审批命令";
        const description =
          metadata.description ||
          proposal.command ||
          proposal.steps[0]?.source_text ||
          proposal.steps[0]?.summary ||
          "待审批操作";
        const planBadge =
          isPlan && metadata.optionIndex
            ? `方案 ${String.fromCharCode(64 + metadata.optionIndex)}`
            : undefined;
        const badge = planBadge || metadata.label || "审批任务";
        return (
          <div
            className={cn(
              "cursor-pointer rounded-lg border px-2.5 py-2 text-[11px] transition-colors",
              blocked
                ? "border-red-300/25 bg-red-300/[0.045] text-red-100 hover:bg-red-300/[0.07]"
                : isPlan
                  ? "border-cyan-300/25 bg-cyan-300/[0.055] text-cyan-50 hover:bg-cyan-300/[0.08]"
                  : "border-slate-700/60 bg-slate-900/45 text-slate-200 hover:bg-slate-800/55"
            )}
            key={proposal.id}
            onClick={() => setExpandedId(expanded ? null : proposal.id)}
            aria-expanded={expanded}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setExpandedId(expanded ? null : proposal.id);
              }
            }}
          >
            <div className="flex items-start gap-2">
              {blocked ? (
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              ) : (
                <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-center gap-1.5">
                      {expanded ? (
                        <ChevronDown className="size-3 shrink-0 text-cyan-200/70" />
                      ) : (
                        <ChevronRight className="size-3 shrink-0 text-cyan-200/70" />
                      )}
                      <span className="truncate font-semibold text-slate-50">
                        {title}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <span className="rounded border border-white/10 bg-black/15 px-1.5 py-0.5 text-[9px] text-slate-300">
                        {badge}
                      </span>
                      <span className="rounded border border-white/10 bg-black/15 px-1.5 py-0.5 text-[9px] text-slate-400">
                        {proposal.steps.length} 个动作
                      </span>
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-[9px]",
                          blocked
                            ? "border-red-300/25 text-red-200"
                            : "border-emerald-300/25 text-emerald-200"
                        )}
                      >
                        {blocked ? "规则未通过" : "待人工审批"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-2 line-clamp-2 text-[10px] leading-relaxed text-slate-300/85">
                  {description || proposal.adjudication.summary}
                </div>

                {false && (
                  <div className="mt-2 rounded-md border border-cyan-300/15 bg-cyan-300/[0.035] px-2 py-1.5 text-[10px] leading-relaxed text-cyan-100/85">
                    <div className="mb-0.5 text-[9px] font-medium uppercase tracking-[0.14em] text-cyan-200/70">
                    </div>
                    {metadata.reasoningSummary || description || proposal.adjudication.summary}
                  </div>
                )}

                {expanded && (
                  <div className="mt-3 space-y-2 border-t border-white/10 pt-2">
                    {description && (
                      <p className="text-[10px] leading-relaxed text-slate-200/90">
                        {description}
                      </p>
                    )}
                    {Boolean(
                      metadata.advantages?.length || metadata.risks?.length
                    ) && (
                      <div className="grid grid-cols-2 gap-2 text-[10px]">
                        <div className="rounded-md border border-emerald-300/15 bg-emerald-300/[0.035] px-2 py-1.5">
                          <div className="mb-1 text-[9px] font-medium text-emerald-200">
                            优势
                          </div>
                          <div className="space-y-0.5 text-slate-300">
                            {(metadata.advantages ?? ["未说明"]).map((item) => (
                              <div key={item}>{item}</div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-md border border-amber-300/15 bg-amber-300/[0.035] px-2 py-1.5">
                          <div className="mb-1 text-[9px] font-medium text-amber-200">
                            风险
                          </div>
                          <div className="space-y-0.5 text-slate-300">
                            {(metadata.risks ?? ["未说明"]).map((item) => (
                              <div key={item}>{item}</div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                    {false && <div className="space-y-1">
                      {proposal.steps.map((step, index) => (
                        <div
                          className="rounded-md border border-white/10 bg-black/18 px-2 py-1.5"
                          key={step.id}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium text-slate-100">
                              {index + 1}.{" "}
                              {step.summary || skillLabel(step.skill)}
                            </span>
                            <span
                              className={cn(
                                "rounded border px-1.5 py-0.5 text-[9px]",
                                step.risk === "high"
                                  ? "border-red-300/25 text-red-200"
                                  : step.risk === "low"
                                    ? "border-emerald-300/25 text-emerald-200"
                                    : "border-amber-300/25 text-amber-200"
                              )}
                            >
                              {step.risk}
                            </span>
                          </div>
                          <div className="mt-1 text-[10px] text-slate-400">
                            {skillLabel(step.skill)} ·{" "}
                            {parameterPreview(step.parameters)}
                          </div>
                          {step.source_text && (
                            <div className="mt-1 text-[10px] leading-relaxed text-slate-300/80">
                              {step.source_text}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>}
                  </div>
                )}

                {issueCount > 0 && (
                  <div className="mt-2 space-y-0.5 text-[10px] opacity-85">
                    {proposal.adjudication.issues.slice(0, 2).map((issue) => (
                      <div key={`${issue.code}-${issue.step_id ?? ""}`}>
                        {issue.severity === "blocking" ? "阻断" : "提示"}：
                        {issue.message}
                      </div>
                    ))}
                  </div>
                )}
                <div
                  className="mt-2 flex items-center justify-end gap-1.5"
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    className="h-6 px-2 text-[10px]"
                    disabled={["executed", "partial", "rejected"].includes(
                      proposal.status
                    )}
                    onClick={() => {
                      onReject(proposal.id);
                      setDialogProposal(null);
                    }}
                    size="sm"
                    type="button"
                    variant="ghost"
                  >
                    驳回
                  </Button>
                  <Button
                    className="h-6 px-2 text-[10px]"
                    disabled={blocked}
                    onClick={() => {
                      onApprove(proposal.id);
                      setDialogProposal(null);
                    }}
                    size="sm"
                    type="button"
                  >
                    {busy ? "执行中" : "通过"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        );
      })}
      {dialogProposal && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/65 p-4"
          role="presentation"
          onClick={() => setDialogProposal(null)}
        >
          <div
            className="w-full max-w-md rounded-xl border border-cyan-200/20 bg-[#11151d] p-4 text-xs text-slate-200 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approval-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-2">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-300" />
              <div className="min-w-0 flex-1">
                <div
                  id="approval-dialog-title"
                  className="font-semibold text-slate-50"
                >
                  审批确认
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  {dialogProposal.command ||
                    String(
                      dialogProposal.plan_metadata?.title || "待处理命令提案"
                    )}
                </div>
              </div>
              <button
                aria-label="关闭审批对话框"
                className="rounded p-1 text-slate-500 hover:bg-white/10 hover:text-slate-200"
                onClick={() => setDialogProposal(null)}
                type="button"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="mt-3 max-h-48 space-y-1.5 overflow-y-auto rounded-lg border border-white/10 bg-black/20 p-2 text-[10px]">
              {dialogProposal.steps.map((step, index) => (
                <div key={step.id}>
                  {index + 1}. {step.summary || skillLabel(step.skill)} ·{" "}
                  {parameterPreview(step.parameters)}
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button
                className="h-7 px-3 text-[10px]"
                disabled={busyId === dialogProposal.id}
                onClick={() => {
                  const id = dialogProposal.id;
                  setDialogProposal(null);
                  onReject(id);
                }}
                size="sm"
                type="button"
                variant="danger"
              >
                驳回
              </Button>
              <Button
                className="h-7 px-3 text-[10px]"
                disabled={
                  busyId === dialogProposal.id ||
                  dialogProposal.status === "blocked"
                }
                onClick={() => {
                  const id = dialogProposal.id;
                  setDialogProposal(null);
                  onApprove(id);
                }}
                size="sm"
                type="button"
                variant="default"
              >
                通过
              </Button>
              <Button
                className="h-7 px-3 text-[10px]"
                onClick={() => setDialogProposal(null)}
                size="sm"
                type="button"
                variant="ghost"
              >
                取消
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function approvalModeLabel(mode: ApprovalMode): string {
  return {
    strict: "严格模式",
    smart: "智能模式",
    auto: "自动模式",
    off: "关闭模式",
  }[mode];
}

function approvalModeDescription(mode: ApprovalMode): string {
  return {
    strict: "所有变更工具调用均需审批，安全级别最高",
    smart: "低风险工具自动批准，中高风险工具需要审批",
    auto: "变更工具默认进入审批流程（默认）",
    off: "关闭人工审批，由 Agent 自动执行；规则校验仍然生效",
  }[mode];
}

function approvalModeIcon(mode: ApprovalMode) {
  return {
    strict: ShieldAlert,
    smart: Sparkles,
    auto: ShieldCheck,
    off: CircleOff,
  }[mode];
}

function approvalModeTone(mode: ApprovalMode): string {
  return {
    strict: "text-amber-300",
    smart: "text-yellow-300",
    auto: "text-sky-300",
    off: "text-emerald-400",
  }[mode];
}

function ApprovalModeSwitcher({
  disabled,
  mode,
  onModeChange,
}: {
  disabled: boolean;
  mode: ApprovalMode;
  onModeChange: (mode: ApprovalMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const modes: ApprovalMode[] = ["strict", "smart", "auto", "off"];
  const currentIcon = approvalModeIcon(mode);
  const CurrentIcon = currentIcon;

  useEffect(() => {
    if (!open) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`审批模式：${approvalModeLabel(mode)}`}
        className={cn(
          "inline-flex h-6 max-w-[8.5rem] items-center gap-1 rounded border px-1.5 text-[10px] transition-colors",
          "border-slate-700/70 bg-slate-900/90 text-slate-200 hover:border-slate-500",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-400/70",
          disabled && "cursor-not-allowed opacity-50"
        )}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <CurrentIcon className={cn("size-3", approvalModeTone(mode))} />
        <span className="truncate">{approvalModeLabel(mode)}</span>
        <ChevronDown
          className={cn(
            "size-3 shrink-0 transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div
          aria-label="审批模式选项"
          className="absolute bottom-full right-0 z-50 mb-2 w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-slate-700/80 bg-[#111923] p-1 shadow-[0_12px_32px_rgba(0,0,0,0.45)]"
          role="listbox"
        >
          {modes.map((item) => {
            const Icon = approvalModeIcon(item);
            const selected = item === mode;
            return (
              <button
                aria-selected={selected}
                className={cn(
                  "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                  selected ? "bg-slate-800/90" : "hover:bg-slate-800/60",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-400/70"
                )}
                key={item}
                onClick={() => {
                  onModeChange(item);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <Icon
                  className={cn(
                    "mt-0.5 size-3.5 shrink-0",
                    approvalModeTone(item)
                  )}
                />
                <span className="min-w-0">
                  <span className="block text-[10px] font-medium leading-4 text-slate-100">
                    {approvalModeLabel(item)}
                  </span>
                  <span className="block text-[9px] leading-3.5 text-slate-400">
                    {approvalModeDescription(item)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex items-start justify-start pl-1">
      <div className="inline-flex max-w-[92%] items-center gap-2 rounded-lg border border-cyan-300/15 bg-cyan-300/[0.045] px-3 py-2 text-[11px] text-cyan-100">
        <Loader2 className="size-3 animate-spin" />
        <span>助手正在思考…</span>
      </div>
    </div>
  );
}

function MessageBlock({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";
  // Tool calls remain available to the chat transport and approval flow, but
  // their raw input/output JSON is intentionally hidden from the conversation UI.
  const showInlineToolDetails = false;
  const hasVisibleContent = messageHasVisibleContent(message);

  if (!hasVisibleContent) return null;

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
        {message.parts.map((part, idx) => {
          if (isTextUIPart(part)) {
            const displayText = isUser
              ? part.text
              : stripDocumentApprovalNotice(part.text);
            return isUser ? (
              <div key={idx} className="whitespace-pre-wrap leading-relaxed">
                {displayText}
              </div>
            ) : (
              <div className="ai-chat-markdown" key={idx}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {displayText}
                </ReactMarkdown>
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
          if (showInlineToolDetails && isToolOrDynamicToolUIPart(part)) {
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
  newServerTransport: MCPServerTransport;
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
  onImportMcpServers: (
    servers: MCPServerImportPayload[]
  ) => void | Promise<void>;
  onRemoveServer: (id: string) => void;
  onToggleServer: (id: string, enabled: boolean) => void;
  onUpdateMcpServer: (
    id: string,
    server: MCPServerImportPayload
  ) => void | Promise<void>;
  onValidateMcpServer: (id: string) => void | Promise<void>;
  onNewServerNameChange: (v: string) => void;
  onNewServerEndpointChange: (v: string) => void;
  onNewServerTransportChange: (t: MCPServerTransport) => void;
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
