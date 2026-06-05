import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getStoredToken } from "@/api/client";
import {
  createCustomSkill,
  deleteCustomSkill,
  listBackendSkills,
  listCustomSkills,
  updateCustomSkill,
} from "@/api/ai";
import type {
  CustomSkill,
  CustomSkillCreatePayload,
  RegisteredSkill,
} from "@/api/types";
import {
  MODEL_PRESETS,
  MODEL_PROVIDER_OPTIONS,
  MODEL_STORAGE_KEY,
  modelProfileLabel,
  profileToConfig,
  sameModelConfig,
  type ModelConfig,
  type ModelProfile,
} from "@/features/ai/modelProfiles";
import { useModelConfigStore } from "@/features/ai/modelStore";
import {
  readStorageItem,
  removeStorageItem,
  writeStorageItem,
} from "@/lib/legacyStorage";
import "@/styles/AIAssistantPanel.css";

type PanelTab = "chat" | "settings";
type MessageRole = "user" | "assistant";
type MessageState = "ok" | "error" | "pending";

interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  state: MessageState;
  detail?: string;
  createdAt: number;
}

interface MCPServerConfig {
  id: string;
  name: string;
  endpoint: string;
  transport: "stdio" | "sse" | "http";
  enabled: boolean;
}

type CustomSkillConfig = CustomSkill;
type OpenClawSkillDefinition = RegisteredSkill;

interface LegacyCustomSkillConfig {
  id?: string;
  name?: string;
  description?: string;
  prompt?: string;
  enabled?: boolean;
}

interface SkillExecution {
  skill: string;
  status: "ok" | "error";
  error?: string | null;
}

interface AICommandResponse {
  status: "ok" | "partial" | "error";
  message: string;
  execution?: {
    decomposition?: string[];
    skill_calls?: SkillExecution[];
  };
  scenario?: Record<string, unknown> | null;
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

interface OpenClawAssistantPanelProps {
  mobileView: boolean;
  onApplyScenario?: (scenario: Record<string, unknown>) => void;
}

const STORAGE_KEY = {
  messages: "tianshu.ai.messages",
  mcpServers: "tianshu.ai.mcpServers",
  customSkills: "tianshu.ai.customSkills",
  model: MODEL_STORAGE_KEY.model,
  modelProfiles: MODEL_STORAGE_KEY.modelProfiles,
  activeModelProfileId: MODEL_STORAGE_KEY.activeModelProfileId,
  projectMcpEnabled: "tianshu.ai.projectMcpEnabled",
};

const BUILTIN_MCP_SERVER_NAME = "TianShu MCP";
const BUILTIN_MCP_ENDPOINT = "stdio://local-tianshu-mcp";
const LEGACY_PLATFORM_PREFIX = "ai" + "cc";
const LEGACY_BUILTIN_MCP_ENDPOINT = `stdio://local-${LEGACY_PLATFORM_PREFIX}-mcp`;

const DEFAULT_MCP_SERVERS: MCPServerConfig[] = [
  {
    id: crypto.randomUUID(),
    name: BUILTIN_MCP_SERVER_NAME,
    endpoint: BUILTIN_MCP_ENDPOINT,
    transport: "stdio",
    enabled: true,
  },
];

const QUICK_COMMANDS = [
  "Start simulation and run 3 steps",
  "Deploy one BLUE F-16 at 22.1 121.5",
  "Pause simulation and trigger a tactical event",
];

function safeLoad<T>(key: string, fallback: T): T {
  try {
    const raw = readStorageItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch (_error) {
    return fallback;
  }
}

function safeSave<T>(key: string, value: T): void {
  try {
    writeStorageItem(key, JSON.stringify(value));
  } catch (_error) {
    // Ignore local persistence failures.
  }
}

function safeRemove(key: string): void {
  try {
    removeStorageItem(key);
  } catch (_error) {
    // Ignore local persistence failures.
  }
}

function isBuiltinMcpEndpoint(endpoint: string | undefined): boolean {
  const normalized = endpoint?.trim().toLowerCase();
  return (
    normalized === BUILTIN_MCP_ENDPOINT ||
    normalized === LEGACY_BUILTIN_MCP_ENDPOINT
  );
}

function normalizeMcpServerConfig(server: MCPServerConfig): MCPServerConfig {
  const endpoint = server.endpoint?.trim() || "";
  const legacyManagedName =
    (server.name || "").trim().toLowerCase() ===
      `${LEGACY_PLATFORM_PREFIX} mcp` &&
    (endpoint === "" || endpoint.toLowerCase().startsWith("stdio://local-"));
  if (!isBuiltinMcpEndpoint(endpoint) && !legacyManagedName) {
    return server;
  }
  return {
    ...server,
    name: BUILTIN_MCP_SERVER_NAME,
    endpoint: BUILTIN_MCP_ENDPOINT,
    transport: "stdio",
  };
}

function normalizeMcpServerConfigs(
  servers: MCPServerConfig[]
): MCPServerConfig[] {
  if (!Array.isArray(servers)) return DEFAULT_MCP_SERVERS;
  return servers.map(normalizeMcpServerConfig);
}

function authHeaders(
  extra: Record<string, string> = {}
): Record<string, string> {
  const token = getStoredToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function OpenClawAssistantPanel({
  mobileView,
  onApplyScenario,
}: Readonly<OpenClawAssistantPanelProps>) {
  const aiBaseUrl = (
    (import.meta.env.VITE_AI_SERVER_URL ?? "http://127.0.0.1:8000") as string
  )
    .trim()
    .replace(/\/+$/, "");
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
  const [panelOpen, setPanelOpen] = useState(!mobileView);
  const [activeTab, setActiveTab] = useState<PanelTab>("chat");
  const [commandInput, setCommandInput] = useState("");
  const [sending, setSending] = useState(false);
  const [projectMcpEnabled, setProjectMcpEnabled] = useState(() =>
    safeLoad<boolean>(STORAGE_KEY.projectMcpEnabled, true)
  );
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    safeLoad<ChatMessage[]>(STORAGE_KEY.messages, [])
  );
  const [mcpServers, setMcpServers] = useState<MCPServerConfig[]>(() =>
    normalizeMcpServerConfigs(
      safeLoad<MCPServerConfig[]>(STORAGE_KEY.mcpServers, DEFAULT_MCP_SERVERS)
    )
  );
  const legacyCustomSkillsRef = useRef<LegacyCustomSkillConfig[]>(
    safeLoad<LegacyCustomSkillConfig[]>(STORAGE_KEY.customSkills, [])
  );
  const customSkillMigrationAttemptedRef = useRef(false);
  const [customSkills, setCustomSkills] = useState<CustomSkillConfig[]>([]);
  const [registeredSkills, setRegisteredSkills] = useState<
    OpenClawSkillDefinition[]
  >([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
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
  const [modelProfileNameDraft, setModelProfileNameDraft] = useState(
    activeModelProfile?.name ?? ""
  );

  useEffect(() => {
    setModelProfileNameDraft(activeModelProfile?.name ?? "");
  }, [activeModelProfile?.id, activeModelProfile?.name]);

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

  useEffect(() => {
    setPanelOpen(!mobileView);
  }, [mobileView]);

  useEffect(() => {
    safeSave(STORAGE_KEY.messages, messages);
  }, [messages]);

  useEffect(() => {
    safeSave(STORAGE_KEY.mcpServers, mcpServers);
  }, [mcpServers]);

  useEffect(() => {
    safeSave(STORAGE_KEY.projectMcpEnabled, projectMcpEnabled);
  }, [projectMcpEnabled]);

  useEffect(() => {
    if (!chatLogRef.current) {
      return;
    }
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [messages, panelOpen, activeTab]);

  useEffect(() => {
    void refreshSkills();
  }, [refreshSkills]);

  function appendMessage(role: MessageRole, text: string, state: MessageState) {
    const nextMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role,
      text,
      state,
      createdAt: Date.now(),
    };
    setMessages((prev) => [...prev, nextMessage]);
    return nextMessage.id;
  }

  function updateMessage(
    messageId: string,
    updates: Partial<Pick<ChatMessage, "text" | "state" | "detail">>
  ): void {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId ? { ...message, ...updates } : message
      )
    );
  }

  async function sendCommand(command: string): Promise<void> {
    const trimmed = command.trim();
    if (!trimmed || sending) {
      return;
    }

    setCommandInput("");
    setActiveTab("chat");
    setSending(true);

    appendMessage("user", trimmed, "ok");
    const assistantMessageId = appendMessage(
      "assistant",
      "Running...",
      "pending"
    );

    try {
      const response = await fetch(`${aiBaseUrl}/api/ai/command`, {
        method: "POST",
        headers: authHeaders({
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          command: trimmed,
          context: {
            project_mcp_enabled: projectMcpEnabled,
            mcp_servers: activeMcpServers,
            custom_skills: activeCustomSkills,
            model: modelConfig,
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = (await response.json()) as AICommandResponse;
      const skillSummary =
        payload.execution?.skill_calls
          ?.map(
            (call) =>
              `${call.status === "ok" ? "OK" : "ERR"} - ${call.skill}${
                call.error ? `: ${call.error}` : ""
              }`
          )
          .join("\n") ?? "";

      updateMessage(assistantMessageId, {
        text: payload.message || "Command submitted.",
        state: payload.status === "error" ? "error" : "ok",
        detail: skillSummary,
      });

      if (
        payload.scenario &&
        typeof payload.scenario === "object" &&
        !Array.isArray(payload.scenario)
      ) {
        onApplyScenario?.(payload.scenario);
      }
    } catch (error) {
      updateMessage(assistantMessageId, {
        text: "Command failed. Check AI server and configuration.",
        state: "error",
        detail: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setSending(false);
    }
  }

  function onSendSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void sendCommand(commandInput);
  }

  function handleModelProfileSelect(profileId: string): void {
    selectModelProfile(profileId);
    setModelCheckResult(null);
  }

  function handleModelProfileSave(name: string): void {
    saveActiveProfile(name.trim() || modelProfileLabel(modelConfig));
    setModelCheckResult(null);
  }

  function handleModelProfileCreate(name: string): void {
    createProfileFromActive(name.trim() || modelProfileLabel(modelConfig));
    setModelCheckResult(null);
  }

  function handleModelProfileDelete(profileId: string): void {
    deleteModelProfile(profileId);
    setModelCheckResult(null);
  }

  function handleAddServer(): void {
    const name = newServerName.trim();
    const endpoint = newServerEndpoint.trim();
    if (!name || !endpoint) {
      return;
    }
    setMcpServers((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        name,
        endpoint,
        transport: newServerTransport,
        enabled: true,
      },
    ]);
    setNewServerName("");
    setNewServerEndpoint("");
    setNewServerTransport("stdio");
  }

  async function handleAddSkill(): Promise<void> {
    const name = newSkillName.trim();
    const description = newSkillDescription.trim();
    if (!name || !description) {
      return;
    }
    try {
      const skill = await createCustomSkill({
        name,
        description,
        prompt: description,
        enabled: true,
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
  }

  async function handleToggleCustomSkill(
    id: string,
    enabled: boolean
  ): Promise<void> {
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
  }

  async function handleRemoveCustomSkill(id: string): Promise<void> {
    try {
      await deleteCustomSkill(id);
      setCustomSkills((prev) => prev.filter((item) => item.id !== id));
      setSkillsError(null);
    } catch (error) {
      setSkillsError(
        error instanceof Error ? error.message : "Custom skill delete failed"
      );
    }
  }

  async function checkModelConnection(): Promise<void> {
    if (!modelConfig.baseUrl.trim()) {
      setModelCheckResult({
        status: "error",
        message: "Base URL is required before testing connection.",
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
      const response = await fetch(`${aiBaseUrl}/api/ai/model/check`, {
        method: "POST",
        headers: authHeaders({
          "Content-Type": "application/json",
        }),
        body: JSON.stringify(modelConfig),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = (await response.json()) as ModelCheckResponse;
      setModelCheckResult(payload);
      const activeProviderId =
        modelProfiles.find((profile) => profile.id === activeModelProfileId)
          ?.providerId ?? modelConfig.provider;
      markProviderChecked(activeProviderId, payload.status !== "error");
    } catch (error) {
      setModelCheckResult({
        status: "error",
        message: "Connection test failed.",
        provider: modelConfig.provider,
        endpoint: modelConfig.baseUrl,
        auth_ok: false,
        models_listed: false,
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setCheckingModel(false);
    }
  }

  function renderChat(): JSX.Element {
    return (
      <div className="openclaw-panel-body">
        <section className="openclaw-hero">
          <h4>天枢指挥助手</h4>
          <p>
            Use natural language to invoke OpenClaw skills for simulation, unit,
            script and situation control.
          </p>
        </section>

        <div className="openclaw-chat-log" ref={chatLogRef}>
          {messages.length === 0 && (
            <div className="openclaw-empty-chat">
              <span>No conversation yet. Enter a command to start.</span>
            </div>
          )}
          {messages.map((message) => (
            <article
              key={message.id}
              className={`openclaw-message openclaw-message-${message.role}`}
            >
              <header>
                <span>{message.role === "user" ? "You" : "OpenClaw"}</span>
                <time>{formatTime(message.createdAt)}</time>
              </header>
              <p>{message.text}</p>
              {message.detail && (
                <pre
                  className={`openclaw-detail ${
                    message.state === "error" ? "is-error" : ""
                  }`}
                >
                  {message.detail}
                </pre>
              )}
            </article>
          ))}
        </div>

        <div className="openclaw-quick-commands">
          {QUICK_COMMANDS.map((command) => (
            <button
              key={command}
              type="button"
              onClick={() => void sendCommand(command)}
            >
              {command}
            </button>
          ))}
        </div>

        <form className="openclaw-composer" onSubmit={onSendSubmit}>
          <textarea
            value={commandInput}
            onChange={(event) => setCommandInput(event.target.value)}
            placeholder="Example: start simulation and deploy one BLUE F-16 to 23.5 121.0"
            rows={3}
          />
          <div className="openclaw-composer-footer">
            <span>{sending ? "Running..." : "Enter to send"}</span>
            <button type="submit" disabled={sending || !commandInput.trim()}>
              Send
            </button>
          </div>
        </form>
      </div>
    );
  }

  function renderSettings(): JSX.Element {
    return (
      <div className="openclaw-panel-body openclaw-settings">
        <section className="openclaw-section-card">
          <header>
            <h4>Project MCP</h4>
          </header>
          <label className="openclaw-switch-row">
            <span>Enable project-level MCP</span>
            <input
              type="checkbox"
              checked={projectMcpEnabled}
              onChange={(event) => setProjectMcpEnabled(event.target.checked)}
            />
          </label>
          <small>{activeMcpServers.length} MCP server(s) enabled.</small>
        </section>

        <section className="openclaw-section-card">
          <header>
            <h4>MCP Servers</h4>
          </header>
          <div className="openclaw-list">
            {mcpServers.map((server) => (
              <div key={server.id} className="openclaw-list-item">
                <div className="openclaw-list-item-head">
                  <strong>{server.name}</strong>
                  <span>{server.transport.toUpperCase()}</span>
                </div>
                <p>{server.endpoint}</p>
                <div className="openclaw-list-item-actions">
                  <label>
                    <input
                      type="checkbox"
                      checked={server.enabled}
                      onChange={(event) => {
                        const enabled = event.target.checked;
                        setMcpServers((prev) =>
                          prev.map((item) =>
                            item.id === server.id ? { ...item, enabled } : item
                          )
                        );
                      }}
                    />
                    Enabled
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setMcpServers((prev) =>
                        prev.filter((item) => item.id !== server.id)
                      )
                    }
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="openclaw-form-grid">
            <input
              value={newServerName}
              onChange={(event) => setNewServerName(event.target.value)}
              placeholder="Server name"
            />
            <select
              value={newServerTransport}
              onChange={(event) =>
                setNewServerTransport(
                  event.target.value as "stdio" | "sse" | "http"
                )
              }
            >
              <option value="stdio">stdio</option>
              <option value="sse">sse</option>
              <option value="http">http</option>
            </select>
            <input
              className="span-2"
              value={newServerEndpoint}
              onChange={(event) => setNewServerEndpoint(event.target.value)}
              placeholder="Endpoint, e.g. stdio://local-mcp"
            />
            <button type="button" className="span-2" onClick={handleAddServer}>
              Add MCP Server
            </button>
          </div>
        </section>

        <section className="openclaw-section-card">
          <header>
            <h4>Skills</h4>
            <button
              type="button"
              onClick={() => void refreshSkills()}
              disabled={skillsLoading}
            >
              Refresh
            </button>
          </header>

          {skillsError && <p className="openclaw-error">{skillsError}</p>}
          <div className="openclaw-list">
            {registeredSkills.map((skill) => (
              <div key={skill.name} className="openclaw-list-item readonly">
                <div className="openclaw-list-item-head">
                  <strong>{skill.name}</strong>
                  <span>Registered</span>
                </div>
                <p>{skill.description}</p>
              </div>
            ))}
            {registeredSkills.length === 0 && !skillsLoading && (
              <div className="openclaw-list-item readonly">
                <p>No backend-registered skills found.</p>
              </div>
            )}
          </div>

          <div className="openclaw-list">
            {customSkills.map((skill) => (
              <div key={skill.id} className="openclaw-list-item">
                <div className="openclaw-list-item-head">
                  <strong>{skill.name}</strong>
                  <span>Custom</span>
                </div>
                <p>{skill.description}</p>
                <div className="openclaw-list-item-actions">
                  <label>
                    <input
                      type="checkbox"
                      checked={skill.enabled}
                      onChange={(event) => {
                        const enabled = event.target.checked;
                        void handleToggleCustomSkill(skill.id, enabled);
                      }}
                    />
                    Enabled
                  </label>
                  <button
                    type="button"
                    onClick={() => void handleRemoveCustomSkill(skill.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="openclaw-form-grid">
            <input
              value={newSkillName}
              onChange={(event) => setNewSkillName(event.target.value)}
              placeholder="Skill name"
            />
            <input
              value={newSkillDescription}
              onChange={(event) => setNewSkillDescription(event.target.value)}
              placeholder="Skill description"
            />
            <button
              type="button"
              className="span-2"
              onClick={() => void handleAddSkill()}
            >
              Add Custom Skill
            </button>
          </div>
        </section>

        <section className="openclaw-section-card">
          <header>
            <h4>Model Config</h4>
            <button
              type="button"
              onClick={() => void checkModelConnection()}
              disabled={checkingModel}
            >
              {checkingModel ? "Testing..." : "Test Connection"}
            </button>
          </header>
          <div className="openclaw-form-grid">
            <select
              className="span-2"
              value={activeModelProfileId}
              onChange={(event) => handleModelProfileSelect(event.target.value)}
            >
              {modelProfiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} · {profile.provider}/{profile.model}
                </option>
              ))}
            </select>
            <input
              className="span-2"
              value={modelProfileNameDraft}
              onChange={(event) => setModelProfileNameDraft(event.target.value)}
              placeholder="Profile name"
            />
            <button
              type="button"
              onClick={() => handleModelProfileSave(modelProfileNameDraft)}
            >
              {activeModelProfileDirty ? "Save Profile" : "Saved"}
            </button>
            <button
              type="button"
              onClick={() => handleModelProfileCreate(modelProfileNameDraft)}
            >
              Save As New
            </button>
            <button
              type="button"
              disabled={!activeModelProfile || modelProfiles.length <= 1}
              onClick={() =>
                activeModelProfile &&
                handleModelProfileDelete(activeModelProfile.id)
              }
            >
              Delete Profile
            </button>
          </div>
          <div className="openclaw-form-grid">
            <select
              value={modelConfig.provider}
              onChange={(event) =>
                updateActiveModelConfig({
                  ...modelConfig,
                  provider: event.target.value,
                })
              }
            >
              {MODEL_PROVIDER_OPTIONS.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
            <select
              value={selectedPreset}
              onChange={(event) => {
                if (event.target.value === "__custom__") {
                  return;
                }
                updateActiveModelConfig({
                  ...modelConfig,
                  model: event.target.value,
                });
              }}
            >
              <option value="__custom__">Custom model name</option>
              {modelPresetOptions.map((modelName) => (
                <option key={modelName} value={modelName}>
                  {modelName}
                </option>
              ))}
            </select>
            <input
              className="span-2"
              value={modelConfig.model}
              onChange={(event) =>
                updateActiveModelConfig({
                  ...modelConfig,
                  model: event.target.value,
                })
              }
              placeholder="Model Name (editable)"
              autoComplete="off"
              list="openclaw-model-presets"
            />
            <datalist id="openclaw-model-presets">
              {modelPresetOptions.map((modelName) => (
                <option key={modelName} value={modelName} />
              ))}
            </datalist>
            <input
              className="span-2"
              value={modelConfig.baseUrl}
              onChange={(event) =>
                updateActiveModelConfig({
                  ...modelConfig,
                  baseUrl: event.target.value,
                })
              }
              placeholder="Base URL"
            />
            <input
              className="span-2"
              value={modelConfig.apiKey}
              onChange={(event) =>
                updateActiveModelConfig({
                  ...modelConfig,
                  apiKey: event.target.value,
                })
              }
              placeholder="API Key"
              type="password"
            />
          </div>
          {modelCheckResult && (
            <div className={`openclaw-check-result ${modelCheckResult.status}`}>
              <strong>{modelCheckResult.message}</strong>
              <p>
                endpoint: {modelCheckResult.endpoint || "N/A"} | auth:{" "}
                {modelCheckResult.auth_ok ? "ok" : "fail"} | models:{" "}
                {modelCheckResult.models_listed ? "ok" : "fail"}
              </p>
              {modelCheckResult.checked_model && (
                <p>
                  model: {modelCheckResult.checked_model} | exists:{" "}
                  {modelCheckResult.checked_model_exists ? "yes" : "no"}
                </p>
              )}
              {modelCheckResult.sample_models &&
                modelCheckResult.sample_models.length > 0 && (
                  <p>
                    sample models:{" "}
                    {modelCheckResult.sample_models.slice(0, 5).join(", ")}
                  </p>
                )}
              {modelCheckResult.error && <p>error: {modelCheckResult.error}</p>}
            </div>
          )}
        </section>
      </div>
    );
  }

  return (
    <>
      {!panelOpen && (
        <button
          type="button"
          className="openclaw-panel-fab"
          onClick={() => setPanelOpen(true)}
        >
          AI
        </button>
      )}

      {panelOpen && (
        <aside
          className={`openclaw-panel-shell ${mobileView ? "mobile" : "desktop"}`}
        >
          <header className="openclaw-panel-header">
            <div className="openclaw-panel-title">
              <h3>OpenClaw</h3>
              <span>天枢指挥界面</span>
            </div>
            <div className="openclaw-panel-actions">
              <button type="button" onClick={() => setActiveTab("chat")}>
                Chat
              </button>
              <button type="button" onClick={() => setActiveTab("settings")}>
                Settings
              </button>
              <button type="button" onClick={() => setPanelOpen(false)}>
                Close
              </button>
            </div>
          </header>

          <div className="openclaw-panel-tabs">
            <button
              type="button"
              className={activeTab === "chat" ? "active" : ""}
              onClick={() => setActiveTab("chat")}
            >
              Chat
            </button>
            <button
              type="button"
              className={activeTab === "settings" ? "active" : ""}
              onClick={() => setActiveTab("settings")}
            >
              Settings
            </button>
          </div>

          {activeTab === "chat" ? renderChat() : renderSettings()}
        </aside>
      )}
    </>
  );
}
