import {
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Command,
  Copy,
  Crosshair,
  Layers3,
  Map,
  Save,
  Settings,
  Shield,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Game from "@/game/Game";
import Scenario from "@/game/Scenario";
import { getRuntimeScenario } from "@/api/ai";
import { SetScenarioTimeContext } from "@/gui/contextProviders/contexts/ScenarioTimeContext";
import CesiumScenarioMap from "@/gui/map/CesiumScenarioMap";
import type { CesiumPlacement } from "@/gui/map/CesiumToolbar";
import SCSScenarioJson from "@/scenarios/SCS.json";
import blankScenarioJson from "@/scenarios/blank_scenario.json";
import defaultScenarioJson from "@/scenarios/default_scenario.json";
import { isScenarioObjectVisible } from "@/game/scenarioVisibility";
import { cn } from "@/lib/utils";
import { randomUUID } from "@/utils/generateUUID";
import AISidebar, { type AISidebarTab } from "./AISidebar";
import SimulationInspectorPanel from "./SimulationInspectorPanel";
import SimulationSidebar, {
  type SimulationPanelId,
  type SimulationRunState,
  type SimulationSideStats,
  type SimulationSnapshot,
} from "./SimulationSidebar";
import AARDialog, { type AARSideEntry } from "./AARDialog";
import { SIDE_COLOR } from "@/utils/colors";

const railItems: Array<{
  id: SimulationPanelId;
  label: string;
  icon: typeof Command;
}> = [
  { id: "command", label: "指挥", icon: Command },
  { id: "simulation", label: "仿真", icon: Crosshair },
  { id: "layers", label: "图层", icon: Layers3 },
  { id: "assets", label: "单位", icon: Boxes },
];

// 从任意 scenario JSON 创建一个全新的 Game 实例。传 null/undefined 则走默认 SCS。
// 独立出来是为了让 PlayScenarioPage 能传入远端拉取的 JSON。
function createAiccGameFromJson(
  scenarioJson: object | null | undefined
): Game {
  const currentScenario = new Scenario({
    id: randomUUID(),
    name: "AICC Tactical Simulation",
    startTime: 1699073110,
    duration: 14400,
  });
  const game = new Game(currentScenario);
  const source = scenarioJson ?? SCSScenarioJson;
  try {
    game.loadScenario(JSON.stringify(source));
  } catch (err) {
    console.error("[AICC] createAiccGameFromJson: loadScenario failed, falling back to SCS", err);
    game.loadScenario(JSON.stringify(SCSScenarioJson));
    // Defer the alert so it doesn't block the synchronous useState initializer.
    window.setTimeout(() => {
      window.alert("场景数据格式无效，已加载默认 SCS 场景。请重新保存或联系管理员。");
    }, 0);
  }
  game.scenarioPaused = true;
  return game;
}

function buildSideStats(game: Game): SimulationSideStats[] {
  const scenario = game.currentScenario;
  return scenario.sides.map((side) => ({
    id: side.id,
    name: side.name,
    colorHex: side.color || SIDE_COLOR.BLACK,
    score: side.totalScore ?? 0,
    aircraft: scenario.aircraft.filter((u) => u.sideId === side.id).length,
    ships: scenario.ships.filter((u) => u.sideId === side.id).length,
    facilities: scenario.facilities.filter((u) => u.sideId === side.id).length,
    airbases: scenario.airbases.filter((u) => u.sideId === side.id).length,
  }));
}

function buildSimulationSnapshot(
  game: Game,
  runState: SimulationRunState
): SimulationSnapshot {
  const scenario = game.currentScenario;
  const elapsedSeconds = Math.max(0, scenario.currentTime - scenario.startTime);
  const visibility = {
    godMode: game.godMode,
    currentSideId: game.currentSideId,
  };

  return {
    runState,
    scenarioName: scenario.name,
    timeCompression: scenario.timeCompression || 1,
    currentTime: scenario.currentTime,
    elapsedSeconds,
    duration: scenario.duration,
    aircraft: scenario.aircraft.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    ships: scenario.ships.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    facilities: scenario.facilities.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    airbases: scenario.airbases.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    referencePoints: scenario.referencePoints.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    weapons: scenario.weapons.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    ).length,
    missions: game.godMode
      ? scenario.missions.length
      : scenario.missions.filter(
          (mission) => !scenario.isHostile(game.currentSideId, mission.sideId)
        ).length,
    sides: scenario.sides.length,
    currentSideId: game.currentSideId,
    godMode: game.godMode,
    eraserMode: game.eraserMode,
    outcome: { ...game.gameOutcome },
    sideStats: buildSideStats(game),
  };
}

// 路由层（PlayScenarioPage）传入的必要上下文。全部 optional，
// 缺省时退化为原有 standalone 行为（SCS 默认内嵌、无保存按钮）。
export interface ScenarioMeta {
  id: string;
  name: string;
  isTemplate: boolean;
  version: number;
}

export interface SaveAarPayload {
  outcomeReason: string;
  winnerSideId: string;
  endedAt: string;
  summary: Record<string, unknown>;
}

export interface AITacticalCommandPlatformProps {
  scenarioMeta?: ScenarioMeta;
  /** 远端 scenario JSON；路由实例变化时会重新 reload。 */
  initialScenarioData?: Record<string, unknown> | null;
  /** 保存到当前 scenario（仅非模板）。模板上下文会在上层弹出 another-as 对话框。 */
  onSave?: (data: Record<string, unknown>) => Promise<void> | void;
  /** 另存为新 scenario；平台仅负责报上当前 JSON，名称/跳转由上层处理。 */
  onRequestSaveAs?: (data: Record<string, unknown>) => void;
  /** 返回想定列表。 */
  onExit?: () => void;
  /** 推演结束时异步归档 AAR。可选；失败不阻断 UI。 */
  onPostAar?: (payload: SaveAarPayload) => Promise<void> | void;
}

export default function AITacticalCommandPlatform({
  scenarioMeta,
  initialScenarioData,
  onSave,
  onRequestSaveAs,
  onExit,
  onPostAar,
}: AITacticalCommandPlatformProps = {}) {
  // game 是引用型，useState 仅初始化一次；实际切换想定走下面 useEffect
  // 调 loadScenario，避免重建 Cesium。
  const [game] = useState<Game>(() =>
    createAiccGameFromJson(initialScenarioData ?? null)
  );
  const setScenarioTime = useContext(SetScenarioTimeContext);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeRailItem, setActiveRailItem] =
    useState<SimulationPanelId>("simulation");
  const [missionCreatorOpen, setMissionCreatorOpen] = useState(false);
  const [missionEditorMissionId, setMissionEditorMissionId] = useState<
    string | null
  >(null);
  // AI 侧栏：默认 collapsed；sidebar 顶部 Sparkles 动作与底部 Settings
  // 动作分别打开 chat / settings tab。
  const [aiSidebarOpen, setAiSidebarOpen] = useState(false);
  const [aiSidebarTab, setAiSidebarTab] = useState<AISidebarTab>("chat");
  const [showRoutes, setShowRoutes] = useState(false);
  const [showRanges, setShowRanges] = useState(false);
  const [placement, setPlacement] = useState<CesiumPlacement | null>(null);
  const runStateRef = useRef<SimulationRunState>("idle");
  const playLoopRunning = useRef(false);
  const [aarOpen, setAarOpen] = useState(false);
  // 仅在「未关闭过此局 AAR」时自动弹出；用户主动关闭后不再骚扰。
  const aarHandledOutcomeRef = useRef<string>("");
  // 避免 onPostAar 重复提交同一局 AAR。
  const aarPostedSignatureRef = useRef<string>("");
  // 保存/另存状态提示，不依赖外部 toast。
  const [savingState, setSavingState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [snapshot, setSnapshot] = useState<SimulationSnapshot>(() =>
    buildSimulationSnapshot(game, "idle")
  );
  // 把 scenario.id 镜像到 React state，AISidebar 用它做 chat 历史的
  // localStorage 命名空间，切换 scenario 自动切换会话。
  const [scenarioId, setScenarioId] = useState<string>(
    () => game.currentScenario.id
  );

  const refreshSnapshot = useCallback(
    (runState: SimulationRunState = runStateRef.current) => {
      runStateRef.current = runState;
      setScenarioTime(game.currentScenario.currentTime);
      setSnapshot(buildSimulationSnapshot(game, runState));
      setScenarioId(game.currentScenario.id);
    },
    [game, setScenarioTime]
  );

  const pauseSimulation = useCallback(() => {
    game.scenarioPaused = true;
    refreshSnapshot("paused");
  }, [game, refreshSnapshot]);

  const playSimulation = useCallback(async () => {
    if (playLoopRunning.current) return;

    playLoopRunning.current = true;
    game.scenarioPaused = false;
    refreshSnapshot("running");

    try {
      while (!game.scenarioPaused && !game.checkGameEnded()) {
        const compression = Math.max(
          1,
          Math.floor(game.currentScenario.timeCompression || 1)
        );

        for (let i = 0; i < compression; i += 1) {
          game.step();
        }

        refreshSnapshot("running");

        // Keep Cesium/React responsive while still making time compression visible.
        await new Promise((resolve) => window.setTimeout(resolve, 80));
      }
    } finally {
      playLoopRunning.current = false;
      if (runStateRef.current === "running") {
        game.scenarioPaused = true;
        refreshSnapshot("paused");
      }
    }
  }, [game, refreshSnapshot]);

  const stepSimulation = useCallback(() => {
    game.scenarioPaused = true;
    game.step();
    refreshSnapshot("paused");
  }, [game, refreshSnapshot]);

  // Tracks the most recently activated scenario source so 重置 can reload
  // whatever the user is currently sandboxing in (SCS / Demo / 自建 / 导入)
  // instead of always falling back to SCS. Initialized to SCS to match the
  // `createAiccGame()` boot scenario.
  const lastLoadedScenarioRef = useRef<unknown>(SCSScenarioJson);

  // Shared loader: applies a parsed scenario object to the live Game while
  // resetting transient UI (placement / mission dialogs) so stale ids from the
  // previous scenario can't leak into the editor flow.
  const loadScenarioFromObject = useCallback(
    (raw: unknown) => {
      let cloned: { currentScenario?: { id?: string } };
      try {
        cloned = JSON.parse(JSON.stringify(raw));
      } catch (err) {
        console.error("[AICC] scenario clone failed:", err);
        window.alert("场景数据无效，无法加载。");
        return;
      }
      if (cloned?.currentScenario && cloned.currentScenario.id) {
        cloned.currentScenario.id = randomUUID();
      }
      try {
        game.scenarioPaused = true;
        game.loadScenario(JSON.stringify(cloned));
      } catch (err) {
        console.error("[AICC] loadScenario failed:", err);
        window.alert("场景加载失败：文件可能不是合法的 AICC 场景。");
        return;
      }
      // Remember the (cloned) source so 重置 can re-apply the same scenario
      // again without reusing the stale ids that loadScenario consumed.
      lastLoadedScenarioRef.current = cloned;
      setPlacement(null);
      setMissionCreatorOpen(false);
      setMissionEditorMissionId(null);
      refreshSnapshot("idle");
    },
    [game, refreshSnapshot]
  );

  const resetSimulation = useCallback(() => {
    loadScenarioFromObject(lastLoadedScenarioRef.current);
  }, [loadScenarioFromObject]);

  const handleNewScenario = useCallback(() => {
    if (
      !window.confirm(
        "创建新场景将清空当前所有阵营、单位和任务，是否继续？"
      )
    ) {
      return;
    }
    loadScenarioFromObject(blankScenarioJson);
  }, [loadScenarioFromObject]);

  const handleLoadDemoScenario = useCallback(() => {
    loadScenarioFromObject(defaultScenarioJson);
  }, [loadScenarioFromObject]);

  const handleLoadSCSScenario = useCallback(() => {
    loadScenarioFromObject(SCSScenarioJson);
  }, [loadScenarioFromObject]);

  const handleImportScenario = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.style.display = "none";
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      input.remove();
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        const txt = e.target?.result;
        if (typeof txt !== "string" || txt.length === 0) {
          window.alert("场景文件内容为空。");
          return;
        }
        try {
          const parsed = JSON.parse(txt);
          loadScenarioFromObject(parsed);
        } catch (err) {
          console.error("[AICC] import parse failed:", err);
          window.alert("场景文件解析失败：不是合法的 JSON。");
        }
      };
      reader.onerror = () => {
        console.error("[AICC] import read failed:", reader.error);
        window.alert("场景文件读取失败，请重试。");
      };
      reader.readAsText(file, "UTF-8");
    };
    document.body.appendChild(input);
    input.click();
  }, [loadScenarioFromObject]);

  const handleExportScenario = useCallback(() => {
    try {
      const json = game.exportCurrentScenario();
      const blob = new Blob([json], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const ts = new Date().toISOString().replace(/[:.]/g, "_");
      const safeName = (game.currentScenario.name || "aicc_scenario")
        .trim()
        .replace(/[^A-Za-z0-9_\-]+/g, "_")
        .slice(0, 60) || "aicc_scenario";
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safeName}_${ts}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      console.error("[AICC] export failed:", err);
      window.alert("场景导出失败，请稍后重试。");
    }
  }, [game]);

  const setSpeed = useCallback(
    (speed: number) => {
      game.currentScenario.timeCompression = speed;
      refreshSnapshot();
    },
    [game, refreshSnapshot]
  );

  const toggleGodMode = useCallback(() => {
    game.toggleGodMode();
    refreshSnapshot();
  }, [game, refreshSnapshot]);

  const toggleEraser = useCallback(() => {
    game.toggleEraserMode();
    refreshSnapshot();
  }, [game, refreshSnapshot]);

  const deleteMission = useCallback(
    (missionId: string) => {
      const mission = game.currentScenario.missions.find(
        (item) => item.id === missionId
      );
      if (!mission) return;
      if (!window.confirm(`确认删除任务「${mission.name}」？`)) return;

      game.deleteMission(missionId);
      setMissionEditorMissionId((openMissionId) =>
        openMissionId === missionId ? null : openMissionId
      );
      refreshSnapshot();
    },
    [game, refreshSnapshot]
  );

  useEffect(() => {
    refreshSnapshot("idle");

    return () => {
      game.scenarioPaused = true;
    };
  }, [game, refreshSnapshot]);

  // 轮询后端 runtime，仿真未在运行时每 3s 同步一次 MCP 变更到客户端。
  // 用上次拉取到的单位总数作为变化信号，避免无变化时重复加载场景。
  const runtimeUnitCountRef = useRef<number | null>(null);
  useEffect(() => {
    if (snapshot.runState === "running") return;

    const sync = async () => {
      try {
        const data = await getRuntimeScenario();
        const cs = (data as Record<string, unknown>)?.currentScenario as
          | Record<string, unknown>
          | undefined;
        if (!cs) return;
        const count = (
          ["aircraft", "ships", "facilities", "airbases", "weapons"] as const
        ).reduce(
          (s, k) => s + (Array.isArray(cs[k]) ? (cs[k] as unknown[]).length : 0),
          0
        );
        if (runtimeUnitCountRef.current !== count) {
          runtimeUnitCountRef.current = count;
          loadScenarioFromObject(data);
        }
      } catch {
        // best-effort，网络错误不影响前端正常运行
      }
    };

    void sync();
    const id = setInterval(sync, 3000);
    return () => clearInterval(id);
  }, [snapshot.runState, loadScenarioFromObject]);

  // 监听 outcome：每次新一局结束自动弹 AAR；用户关闭后不会重复弹。
  // 用 endedAt+reason+winnerSideId 拼成签名，确保 reset 后能再次触发。
  useEffect(() => {
    if (!snapshot.outcome.ended) {
      aarHandledOutcomeRef.current = "";
      return;
    }
    const signature = `${snapshot.outcome.reason}|${snapshot.outcome.winnerSideId}|${snapshot.outcome.endedAt}`;
    if (aarHandledOutcomeRef.current !== signature) {
      aarHandledOutcomeRef.current = signature;
      setAarOpen(true);
    }
    // 同时异步归档到后端（如果路由层提供了 onPostAar）。
    if (onPostAar && aarPostedSignatureRef.current !== signature) {
      aarPostedSignatureRef.current = signature;
      void Promise.resolve(
        onPostAar({
          outcomeReason: snapshot.outcome.reason ?? "",
          winnerSideId: snapshot.outcome.winnerSideId ?? "",
          // game.gameOutcome.endedAt 是 scenario currentTime（unix 秒），
          // 转 ISO 字符串以对齐后端 datetime 字段。
          endedAt: snapshot.outcome.endedAt
            ? new Date(snapshot.outcome.endedAt * 1000).toISOString()
            : new Date().toISOString(),
          summary: {
            scenarioName: snapshot.scenarioName,
            elapsedSeconds: snapshot.elapsedSeconds,
            sides: snapshot.sideStats,
          },
        })
      ).catch((err) => console.warn("[AICC] onPostAar failed", err));
    }
  }, [
    snapshot.outcome.ended,
    snapshot.outcome.reason,
    snapshot.outcome.winnerSideId,
    snapshot.outcome.endedAt,
    snapshot.scenarioName,
    snapshot.elapsedSeconds,
    snapshot.sideStats,
    onPostAar,
  ]);

  const SIDEBAR_MIN = 240;
  const SIDEBAR_STORAGE_KEY = "aicc.commandSidebarWidth";

  const [commandSidebarWidth, setCommandSidebarWidth] = useState<number | null>(
    () => {
      if (typeof window === "undefined") return null;
      try {
        const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
        if (!raw) return null;
        const value = Number(raw);
        return Number.isFinite(value) && value >= SIDEBAR_MIN ? value : null;
      } catch {
        return null;
      }
    }
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (commandSidebarWidth === null) {
        window.localStorage.removeItem(SIDEBAR_STORAGE_KEY);
      } else {
        window.localStorage.setItem(
          SIDEBAR_STORAGE_KEY,
          String(Math.round(commandSidebarWidth))
        );
      }
    } catch {
      // ignore quota / privacy errors
    }
  }, [commandSidebarWidth]);

  const sidebarRef = useRef<HTMLDivElement | null>(null);

  const handleSidebarResizeStart = (
    event: MouseEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth =
      sidebarRef.current?.getBoundingClientRect().width ?? 320;
    const sidebarMax = Math.max(
      360,
      Math.min(window.innerWidth - 360, 720)
    );

    const onMove = (moveEvent: globalThis.MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      const next = Math.min(
        sidebarMax,
        Math.max(SIDEBAR_MIN, startWidth + delta)
      );
      setCommandSidebarWidth(next);
    };

    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const handleSidebarResizeReset = () => setCommandSidebarWidth(null);

  const sidebarTrack =
    commandSidebarWidth !== null
      ? `${commandSidebarWidth}px`
      : "clamp(18rem, 24vw, 26rem)";
  // 仿真态势面板从地图右侧搬到地图下方后，右栏槽位留给 AI Sidebar；
  // AI Sidebar 展开时加一列，收起时不占列宽。
  const aiSidebarTrack = "clamp(20rem, 26vw, 28rem)";

  // AI command 返回的 scenario 应用回 game；复用现有的 loadScenario
  // 路径，后紧接一次 refreshSnapshot 让 UI 拿到最新单位 / 设施 / 任务。
  const handleApplyAiScenario = useCallback(
    (data: Record<string, unknown>) => {
      try {
        game.loadScenario(JSON.stringify(data));
        refreshSnapshot();
      } catch (err) {
        console.error("[AICC] AI scenario apply failed", err);
      }
    },
    [game, refreshSnapshot]
  );

  // 当前 game JSON 快照，供保存/另存为按钮提取。
  // game.exportCurrentScenario() 返回字符串，这里再 parse 成 object 与后端契约对齐。
  const captureCurrentScenarioData = useCallback((): Record<string, unknown> => {
    const raw = game.exportCurrentScenario();
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch (err) {
      console.error("[AICC] export scenario JSON parse failed", err);
      return {};
    }
  }, [game]);

  const handleSaveClick = useCallback(async () => {
    if (!onSave) return;
    setSavingState("saving");
    try {
      await Promise.resolve(onSave(captureCurrentScenarioData()));
      setSavingState("saved");
      window.setTimeout(() => setSavingState("idle"), 1500);
    } catch {
      setSavingState("error");
      window.setTimeout(() => setSavingState("idle"), 2000);
    }
  }, [onSave, captureCurrentScenarioData]);

  const handleSaveAsClick = useCallback(() => {
    if (!onRequestSaveAs) return;
    onRequestSaveAs(captureCurrentScenarioData());
  }, [onRequestSaveAs, captureCurrentScenarioData]);

  // 是否需要渲染顶部 mini bar（路由模式才显示；standalone 兼容老入口）。
  const showRouterChrome = Boolean(
    scenarioMeta && (onSave || onRequestSaveAs || onExit)
  );

  return (
    <div
      className="dark h-screen overflow-hidden bg-tactical-bg text-tactical-text lg:grid"
      style={{
        gridTemplateColumns: (() => {
          const railCol = `64px`;
          const leftCol = sidebarCollapsed ? null : sidebarTrack;
          const rightCol = aiSidebarOpen ? aiSidebarTrack : null;
          return [railCol, leftCol, `minmax(0,1fr)`, rightCol]
            .filter(Boolean)
            .join(" ");
        })(),
      }}
    >
      {showRouterChrome && scenarioMeta && (
        <div
          className="pointer-events-none fixed inset-x-0 top-0 z-[10000] flex justify-center px-2 py-2"
          style={{ paddingLeft: 72 /* leave room for the rail */ }}
        >
          <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-cyan-300/20 bg-[#050914]/85 px-3 py-1.5 text-xs text-slate-200 shadow-hud-cyan backdrop-blur">
            {onExit && (
              <button
                type="button"
                onClick={onExit}
                className="flex items-center gap-1 rounded-full px-2 py-0.5 text-slate-300 hover:bg-white/10 hover:text-slate-100"
                title="返回想定列表"
              >
                <ArrowLeft className="size-3.5" /> 返回
              </button>
            )}
            <span className="mx-1 h-3 w-px bg-cyan-300/20" />
            <span className="font-medium text-slate-100">
              {scenarioMeta.name}
            </span>
            {scenarioMeta.isTemplate && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-200">
                模板·只读
              </span>
            )}
            <span className="ml-1 text-[10px] text-slate-500">
              v{scenarioMeta.version}
            </span>
            <span className="mx-1 h-3 w-px bg-cyan-300/20" />
            {onSave && !scenarioMeta.isTemplate && (
              <button
                type="button"
                onClick={handleSaveClick}
                disabled={savingState === "saving"}
                className={cn(
                  "flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium transition-colors",
                  savingState === "saved"
                    ? "bg-emerald-500/25 text-emerald-200"
                    : savingState === "error"
                      ? "bg-red-500/25 text-red-200"
                      : "bg-cyan-400/20 text-cyan-100 hover:bg-cyan-400/30"
                )}
                title="保存到当前想定"
              >
                <Save className="size-3.5" />
                {savingState === "saving"
                  ? "保存中…"
                  : savingState === "saved"
                    ? "已保存"
                    : savingState === "error"
                      ? "保存失败"
                      : "保存"}
              </button>
            )}
            {onRequestSaveAs && (
              <button
                type="button"
                onClick={handleSaveAsClick}
                className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-slate-200 hover:bg-white/10"
                title="另存为新想定"
              >
                <Copy className="size-3.5" /> 另存为
              </button>
            )}
          </div>
        </div>
      )}

      <motion.nav
        animate={{ opacity: 1 }}
        className="hidden border-r border-cyan-300/10 bg-[#030912]/95 px-2 py-5 backdrop-blur-2xl lg:flex lg:flex-col"
        initial={{ opacity: 0 }}
      >
        <div className="mb-7 flex justify-center">
          <div className="grid size-11 place-items-center rounded-2xl border border-cyan-300/18 bg-cyan-300/8 text-cyan-100 shadow-hud-cyan">
            <Shield className="size-6" />
          </div>
        </div>

        <div className="flex flex-1 flex-col items-center gap-3">
          {railItems.map(({ id, label, icon: Icon }) => (
            <button
              aria-label={label}
              className={cn(
                "group grid size-11 place-items-center rounded-xl border text-slate-500 transition-all",
                activeRailItem === id
                  ? "border-cyan-300/25 bg-cyan-300/12 text-cyan-100 shadow-hud-cyan"
                  : "border-transparent hover:border-cyan-300/12 hover:bg-white/5 hover:text-slate-200"
              )}
              key={id}
              onClick={() => setActiveRailItem(id)}
              title={label}
              type="button"
            >
              <Icon className="size-5" />
            </button>
          ))}
        </div>

        <div className="flex flex-col items-center gap-3">
          <Button
            aria-label={
              aiSidebarOpen && aiSidebarTab === "chat"
                ? "关闭 AI 侧栏"
                : "打开 AI 侧栏"
            }
            className={cn(
              "size-10",
              aiSidebarOpen && aiSidebarTab === "chat"
                ? "text-cyan-100 shadow-hud-cyan"
                : "text-slate-400"
            )}
            onClick={() => {
              if (aiSidebarOpen && aiSidebarTab === "chat") {
                setAiSidebarOpen(false);
              } else {
                setAiSidebarOpen(true);
                setAiSidebarTab("chat");
              }
            }}
            size="icon"
            title="AI 助手"
            variant={
              aiSidebarOpen && aiSidebarTab === "chat" ? "tactical" : "ghost"
            }
          >
            <Sparkles className="size-4" />
          </Button>
          <Button
            aria-label={sidebarCollapsed ? "展开左侧栏" : "收起左侧栏"}
            className="size-10"
            onClick={() => setSidebarCollapsed((value) => !value)}
            size="icon"
            variant="ghost"
          >
            {sidebarCollapsed ? (
              <ChevronRight className="size-4" />
            ) : (
              <ChevronLeft className="size-4" />
            )}
          </Button>
          <Button
            aria-label="AI / 系统设置"
            className={cn(
              "size-10",
              aiSidebarOpen && aiSidebarTab === "settings"
                ? "text-cyan-100 shadow-hud-cyan"
                : "text-slate-400"
            )}
            onClick={() => {
              if (aiSidebarOpen && aiSidebarTab === "settings") {
                setAiSidebarOpen(false);
              } else {
                setAiSidebarOpen(true);
                setAiSidebarTab("settings");
              }
            }}
            size="icon"
            title="AI / 系统设置"
            variant={
              aiSidebarOpen && aiSidebarTab === "settings"
                ? "tactical"
                : "ghost"
            }
          >
            <Settings className="size-4" />
          </Button>
        </div>
      </motion.nav>

      {!sidebarCollapsed && (
        <div
          className="relative hidden h-full min-h-0 min-w-0 lg:flex"
          ref={sidebarRef}
        >
          <SimulationSidebar
            activePanel={activeRailItem}
            game={game}
            snapshot={snapshot}
            onPlay={() => void playSimulation()}
            onPause={pauseSimulation}
            onStep={stepSimulation}
            onReset={resetSimulation}
            onSetSpeed={setSpeed}
            onToggleGodMode={toggleGodMode}
            onToggleEraser={toggleEraser}
            showRoutes={showRoutes}
            showRanges={showRanges}
            onToggleRoutes={() => setShowRoutes((value) => !value)}
            onToggleRanges={() => setShowRanges((value) => !value)}
            onOpenMissionCreator={() => setMissionCreatorOpen(true)}
            onOpenMissionEditor={setMissionEditorMissionId}
            onDeleteMission={deleteMission}
            onBeginPlacement={setPlacement}
            onScenarioMutation={refreshSnapshot}
            onNewScenario={handleNewScenario}
            onLoadDemoScenario={handleLoadDemoScenario}
            onLoadSCSScenario={handleLoadSCSScenario}
            onImportScenario={handleImportScenario}
            onExportScenario={handleExportScenario}
          />
          <div
            aria-label="拖动调整左侧栏宽度"
            aria-orientation="vertical"
            className="group absolute inset-y-0 right-0 z-30 flex w-1.5 -translate-x-px cursor-col-resize items-center justify-center hover:bg-cyan-300/12"
            onDoubleClick={handleSidebarResizeReset}
            onMouseDown={handleSidebarResizeStart}
            role="separator"
            title="拖动调整宽度，双击复位"
          >
            <div className="h-12 w-[2px] rounded-full bg-cyan-300/0 transition-colors group-hover:bg-cyan-300/55" />
          </div>
        </div>
      )}

      <main className="relative flex min-h-0 min-w-0 flex-col overflow-hidden bg-[#050914]">
        <div className="relative z-20 flex items-center justify-between border-b border-cyan-300/10 bg-[#030912]/92 px-4 py-3 backdrop-blur-xl lg:hidden">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl border border-cyan-300/18 bg-cyan-300/8 text-cyan-100">
              <Map className="size-5" />
            </div>
            <div>
              <div className="text-base font-semibold text-slate-100">AICC</div>
              <div className="text-xs text-slate-500">仿真指挥平台</div>
            </div>
          </div>
          <Button size="icon" variant="ghost">
            <Settings className="size-4" />
          </Button>
        </div>

        {/*
          地图区域：占据 main 列剩余高度。Cesium 在 embedded 模式下用
          position:absolute 填满父容器，所以这里必须 relative + 显式高度。
        */}
        <div className="relative min-h-0 flex-1">
          <CesiumScenarioMap
            embedded
            game={game}
            missionCreatorOpen={missionCreatorOpen}
            missionEditorMissionId={missionEditorMissionId}
            mobileView={false}
            placement={placement}
            onMissionCreatorOpenChange={setMissionCreatorOpen}
            onMissionEditorMissionIdChange={setMissionEditorMissionId}
            onPlacementChange={setPlacement}
            onScenarioMutation={refreshSnapshot}
            showToolbar={false}
            showRanges={showRanges}
            showRoutes={showRoutes}
          />

          <div className="pointer-events-none absolute left-4 top-4 z-10 hidden max-w-xl rounded-2xl border border-cyan-300/12 bg-[#030912]/72 px-4 py-3 shadow-[0_18px_70px_rgba(0,0,0,0.42)] backdrop-blur-xl lg:block">
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "size-2.5 rounded-full",
                  snapshot.runState === "running"
                    ? "animate-tactical-pulse bg-emerald-300"
                    : snapshot.runState === "paused"
                      ? "bg-amber-300"
                      : "bg-cyan-300"
                )}
              />
              <div>
                <div className="text-sm font-semibold text-slate-100">
                  {snapshot.scenarioName}
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span>原生 AICC Game Engine</span>
                  <span className="text-cyan-300/60">/</span>
                  <span>{snapshot.timeCompression}x 倍率</span>
                  <span className="text-cyan-300/60">/</span>
                  <span>{snapshot.aircraft + snapshot.ships} 个机动单位</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 z-[1] tactical-grid opacity-45" />
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[2] h-28 bg-gradient-to-b from-[#050914] via-[#050914]/55 to-transparent" />
        </div>

        {/*
          仿真态势面板：固定在地图下方。原本作为 grid 第 4 列出现在右侧，
          现搬到地图列底部，4 个核心卡片在 lg+ 横向 4 列铺开，腾出右侧
          槽位给后续 AI 工具栏。
        */}
        <SimulationInspectorPanel game={game} snapshot={snapshot} />
      </main>

      <AISidebar
        activeTab={aiSidebarTab}
        onApplyScenario={handleApplyAiScenario}
        onOpenChange={setAiSidebarOpen}
        onResumePlay={playSimulation}
        onTabChange={setAiSidebarTab}
        open={aiSidebarOpen}
        scenarioId={scenarioId}
      />

      <AARDialog
        elapsedLabel={formatElapsedHMS(snapshot.elapsedSeconds)}
        objectiveEvent={game.currentScenario.lastObjectiveDestroyed}
        onClose={() => setAarOpen(false)}
        onReset={() => {
          setAarOpen(false);
          resetSimulation();
        }}
        open={aarOpen}
        outcome={snapshot.outcome}
        scenarioName={snapshot.scenarioName}
        sides={snapshot.sideStats.map<AARSideEntry>((side) => ({
          id: side.id,
          name: side.name,
          colorHex: side.colorHex,
          score: side.score,
          aircraft: side.aircraft,
          ships: side.ships,
          facilities: side.facilities,
          airbases: side.airbases,
        }))}
      />
    </div>
  );
}

function formatElapsedHMS(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}:${String(secs).padStart(2, "0")}`;
}
