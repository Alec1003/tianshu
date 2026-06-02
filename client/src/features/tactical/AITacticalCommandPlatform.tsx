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
import Game, { type GameOutcome, type GameOutcomeReason } from "@/game/Game";
import Scenario from "@/game/Scenario";
import type {
  RuntimeOutcome,
  RuntimeCreateSideRequest,
  RuntimeAddWeaponRequest,
  RuntimeDeleteWeaponRequest,
  RuntimeDeployUnitRequest,
  RuntimeMoveUnitRequest,
  RuntimeSetUnitPositionRequest,
  RuntimeSnapshot,
  RuntimeUnitType,
  RuntimeUpdateSideRequest,
  RuntimeUpdateUnitRequest,
  RuntimeUpdateWeaponQuantityRequest,
  RuntimeVisibility,
  RuntimeVisibilitySide,
  RuntimeVisibleObjectType,
} from "@/api/types";
import RuntimeController from "@/runtime/RuntimeController";
import { SetScenarioTimeContext } from "@/gui/contextProviders/contexts/ScenarioTimeContext";
import CesiumScenarioMap, {
  type CesiumSceneModeKey,
} from "@/gui/map/CesiumScenarioMap";
import type {
  CesiumBaseLayerKey,
  CesiumPlacement,
} from "@/gui/map/CesiumMapTypes";
import SCSScenarioJson from "@/scenarios/SCS.json";
import blankScenarioJson from "@/scenarios/blank_scenario.json";
import defaultScenarioJson from "@/scenarios/default_scenario.json";
import { cn } from "@/lib/utils";
import { randomUUID } from "@/utils/generateUUID";
import AISidebar from "./AISidebar";
import SimulationInspectorPanel from "./SimulationInspectorPanel";
import TimelineReplayPanel from "./TimelineReplayPanel";
import TopTacticalBar from "./TopTacticalBar";
import SimulationSidebar, {
  type SimulationPanelId,
  type SimulationRunState,
  type SimulationSideStats,
  type SimulationSnapshot,
} from "./SimulationSidebar";
import AARDialog, { type AARSideEntry } from "./AARDialog";
import { SIDE_COLOR } from "@/utils/colors";
import type { SideDoctrine } from "@/game/Doctrine";

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

function cloneDefaultScenarioWithNow(scenarioJson: object): object {
  const cloned = JSON.parse(JSON.stringify(scenarioJson)) as {
    currentScenario?: {
      startTime?: number;
      currentTime?: number;
    };
  };
  const now = Math.floor(Date.now() / 1000);
  if (cloned.currentScenario) {
    cloned.currentScenario.startTime = now;
    cloned.currentScenario.currentTime = now;
  }
  return cloned;
}

// 从任意 scenario JSON 创建一个全新的 Game 实例。传 null/undefined 则走默认 SCS。
// 独立出来是为了让 PlayScenarioPage 能传入远端拉取的 JSON。
function runtimeOutcomeToGameOutcome(outcome: RuntimeOutcome): GameOutcome {
  const reason: GameOutcomeReason =
    outcome.reason === "KEY_UNIT_DESTROYED" || outcome.reason === "TIMEOUT"
      ? outcome.reason
      : "";
  return {
    ended: outcome.ended,
    winnerSideId: outcome.winner_side_id ?? "",
    reason,
    endedAt: outcome.ended_at ?? 0,
  };
}

function runtimeRunState(
  snapshot: RuntimeSnapshot,
  fallback: SimulationRunState = "paused"
): SimulationRunState {
  if (snapshot.running) return "running";
  if (snapshot.paused) return "paused";
  return fallback;
}

function scenarioSignature(scenario: Record<string, unknown>): string {
  try {
    return JSON.stringify(scenario);
  } catch {
    return "";
  }
}

function cloneScenarioRecord(raw: unknown): Record<string, unknown> {
  const cloned = JSON.parse(JSON.stringify(raw)) as Record<string, unknown>;
  if (!cloned || typeof cloned !== "object") {
    throw new Error("Scenario payload must be an object");
  }
  return cloned;
}

function createAiccGameFromJson(scenarioJson: object | null | undefined): Game {
  const now = Math.floor(Date.now() / 1000);
  const currentScenario = new Scenario({
    id: randomUUID(),
    name: "天枢战术推演",
    startTime: now,
    currentTime: now,
    duration: 14400,
  });
  const game = new Game(currentScenario);
  const source = scenarioJson ?? cloneDefaultScenarioWithNow(SCSScenarioJson);
  try {
    game.loadScenario(JSON.stringify(source));
  } catch (err) {
    console.error(
      "[AICC] createAiccGameFromJson: loadScenario failed, falling back to SCS",
      err
    );
    game.loadScenario(
      JSON.stringify(cloneDefaultScenarioWithNow(SCSScenarioJson))
    );
    // Defer the alert so it doesn't block the synchronous useState initializer.
    window.setTimeout(() => {
      window.alert(
        "场景数据格式无效，已加载默认 SCS 场景。请重新保存或联系管理员。"
      );
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

function getRuntimeSideVisibility(
  visibility: RuntimeVisibility | null | undefined,
  currentSideId: string
): RuntimeVisibilitySide | null {
  if (!visibility) return null;
  return (
    visibility.by_side[currentSideId] ??
    visibility.by_side[visibility.current_side_id] ??
    null
  );
}

function visibilityCount(
  sideVisibility: RuntimeVisibilitySide | null,
  key: RuntimeVisibleObjectType,
  fallback: number,
  godMode: boolean
): number {
  if (godMode) return fallback;
  return sideVisibility?.visible_counts?.[key] ?? 0;
}

function buildSimulationSnapshot(
  game: Game,
  runState: SimulationRunState,
  runtimeVisibility: RuntimeVisibility | null = null
): SimulationSnapshot {
  const scenario = game.currentScenario;
  const elapsedSeconds = Math.max(0, scenario.currentTime - scenario.startTime);
  const sideVisibility = getRuntimeSideVisibility(
    runtimeVisibility,
    game.currentSideId
  );

  return {
    runState,
    scenarioName: scenario.name,
    timeCompression: scenario.timeCompression || 1,
    currentTime: scenario.currentTime,
    elapsedSeconds,
    duration: scenario.duration,
    aircraft: visibilityCount(
      sideVisibility,
      "aircraft",
      scenario.aircraft.length,
      game.godMode
    ),
    ships: visibilityCount(
      sideVisibility,
      "ships",
      scenario.ships.length,
      game.godMode
    ),
    facilities: visibilityCount(
      sideVisibility,
      "facilities",
      scenario.facilities.length,
      game.godMode
    ),
    airbases: visibilityCount(
      sideVisibility,
      "airbases",
      scenario.airbases.length,
      game.godMode
    ),
    referencePoints: visibilityCount(
      sideVisibility,
      "referencePoints",
      scenario.referencePoints.length,
      game.godMode
    ),
    weapons: visibilityCount(
      sideVisibility,
      "weapons",
      scenario.weapons.length,
      game.godMode
    ),
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
    visibility: runtimeVisibility,
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
  onCreateBranch?: (data: Record<string, unknown>) => void;
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
  onCreateBranch,
  onExit,
  onPostAar,
}: AITacticalCommandPlatformProps = {}) {
  // game 是引用型，useState 仅初始化一次；实际切换想定走下面 useEffect
  // 调 loadScenario，避免重建 Cesium。
  const [game] = useState<Game>(() =>
    createAiccGameFromJson(initialScenarioData ?? null)
  );
  const initialRuntimeScenarioRef = useRef<Record<string, unknown>>(
    cloneScenarioRecord(
      initialScenarioData ?? cloneDefaultScenarioWithNow(SCSScenarioJson)
    )
  );
  const latestRuntimeScenarioRef = useRef<Record<string, unknown>>(
    initialRuntimeScenarioRef.current
  );
  const runtimeControllerRef = useRef<RuntimeController | null>(null);
  if (runtimeControllerRef.current === null) {
    runtimeControllerRef.current = new RuntimeController(
      undefined,
      scenarioMeta?.id
    );
  }
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
  const [timelinePanelOpen, setTimelinePanelOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [showRoutes, setShowRoutes] = useState(false);
  const [showRanges, setShowRanges] = useState(false);
  const [mapSceneMode, setMapSceneMode] = useState<CesiumSceneModeKey>("2d");
  const [mapBaseLayer, setMapBaseLayer] =
    useState<CesiumBaseLayerKey>("satellite");
  const [placement, setPlacement] = useState<CesiumPlacement | null>(null);
  const runStateRef = useRef<SimulationRunState>("idle");
  const playLoopRunning = useRef(false);
  const runtimeVisibilityRef = useRef<RuntimeVisibility | null>(null);
  const runtimeScenarioSignatureRef = useRef("");
  const runtimeBootstrappedRef = useRef(false);
  const runtimeReadyRef = useRef(false);
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
  const chatScenarioId = scenarioMeta?.id ?? scenarioId;
  const autoOpenedAiScenarioRef = useRef<string>("");

  const refreshSnapshot = useCallback(
    (runState: SimulationRunState = runStateRef.current) => {
      runStateRef.current = runState;
      setScenarioTime(game.currentScenario.currentTime);
      setSnapshot(
        buildSimulationSnapshot(game, runState, runtimeVisibilityRef.current)
      );
      setScenarioId(game.currentScenario.id);
    },
    [game, setScenarioTime]
  );

  const applyRuntimeSnapshot = useCallback(
    (
      runtimeSnapshot: RuntimeSnapshot,
      runState: SimulationRunState = runtimeRunState(runtimeSnapshot),
      options: { preserveTimeCompression?: boolean } = {}
    ) => {
      const previousTimeCompression = game.currentScenario.timeCompression || 1;
      game.loadScenario(JSON.stringify(runtimeSnapshot.scenario));
      if (options.preserveTimeCompression) {
        game.currentScenario.timeCompression = previousTimeCompression;
      }
      runtimeVisibilityRef.current = runtimeSnapshot.visibility ?? null;
      game.scenarioPaused = runtimeSnapshot.paused;
      game.gameOutcome = runtimeOutcomeToGameOutcome(runtimeSnapshot.outcome);
      latestRuntimeScenarioRef.current = runtimeSnapshot.scenario;
      runtimeScenarioSignatureRef.current = scenarioSignature(
        runtimeSnapshot.scenario
      );
      refreshSnapshot(runState);
    },
    [game, refreshSnapshot]
  );

  const pauseSimulation = useCallback(() => {
    playLoopRunning.current = false;
    game.scenarioPaused = true;
    refreshSnapshot("paused");
    void runtimeControllerRef.current
      ?.pause()
      .then((runtimeSnapshot) =>
        applyRuntimeSnapshot(runtimeSnapshot, "paused", {
          preserveTimeCompression: true,
        })
      )
      .catch((err) => console.error("[AICC] runtime pause failed:", err));
  }, [applyRuntimeSnapshot, game, refreshSnapshot]);

  const playSimulation = useCallback(async () => {
    if (playLoopRunning.current) return;

    playLoopRunning.current = true;

    try {
      const startedSnapshot = await runtimeControllerRef.current?.start();
      if (startedSnapshot) {
        applyRuntimeSnapshot(startedSnapshot, "running", {
          preserveTimeCompression: true,
        });
      }

      while (playLoopRunning.current) {
        const compression = Math.max(
          1,
          Math.floor(game.currentScenario.timeCompression || 1)
        );

        const runtimeSnapshot =
          await runtimeControllerRef.current?.step(compression);
        if (!runtimeSnapshot) break;

        applyRuntimeSnapshot(
          runtimeSnapshot,
          runtimeSnapshot.outcome.ended ? "paused" : "running",
          { preserveTimeCompression: true }
        );
        if (runtimeSnapshot.outcome.ended) break;

        // Keep Cesium/React responsive while still making time compression visible.
        await new Promise((resolve) => window.setTimeout(resolve, 80));
      }
    } catch (err) {
      console.error("[AICC] runtime play failed:", err);
      window.alert("后端推演启动失败，请稍后重试。");
    } finally {
      playLoopRunning.current = false;
      if (runStateRef.current === "running") {
        try {
          const pausedSnapshot = await runtimeControllerRef.current?.pause();
          if (pausedSnapshot) {
            applyRuntimeSnapshot(pausedSnapshot, "paused", {
              preserveTimeCompression: true,
            });
          }
        } catch (err) {
          console.error("[AICC] runtime pause after play failed:", err);
          game.scenarioPaused = true;
          refreshSnapshot("paused");
        }
      }
    }
  }, [applyRuntimeSnapshot, game, refreshSnapshot]);

  const stepSimulation = useCallback(() => {
    playLoopRunning.current = false;
    game.scenarioPaused = true;
    refreshSnapshot("paused");
    void runtimeControllerRef.current
      ?.step(1)
      .then((runtimeSnapshot) =>
        applyRuntimeSnapshot(runtimeSnapshot, "paused", {
          preserveTimeCompression: true,
        })
      )
      .catch((err) => {
        console.error("[AICC] runtime step failed:", err);
        window.alert("后端单步推演失败，请稍后重试。");
      });
  }, [applyRuntimeSnapshot, game, refreshSnapshot]);

  // Tracks the latest backend-accepted scenario so reset can reload the same
  // source without treating the browser render adapter as authoritative.
  const lastLoadedScenarioRef = useRef<unknown>(
    initialRuntimeScenarioRef.current
  );

  // Shared loader: sends the parsed scenario to the backend runtime first, then
  // applies the canonical snapshot returned by that runtime.
  const loadScenarioFromObject = useCallback(
    async (raw: unknown) => {
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
      runtimeVisibilityRef.current = null;
      setPlacement(null);
      setMissionCreatorOpen(false);
      setMissionEditorMissionId(null);
      try {
        const runtimeSnapshot =
          await runtimeControllerRef.current?.loadScenario(
            cloned as Record<string, unknown>
          );
        if (runtimeSnapshot) {
          lastLoadedScenarioRef.current = runtimeSnapshot.scenario;
          applyRuntimeSnapshot(runtimeSnapshot, "idle");
          runtimeReadyRef.current = true;
        }
      } catch (err) {
        console.error("[AICC] runtime scenario load failed:", err);
        window.alert("后端推演引擎加载场景失败，请检查场景数据后重试。");
      }
    },
    [applyRuntimeSnapshot]
  );

  const resetSimulation = useCallback(() => {
    playLoopRunning.current = false;
    game.scenarioPaused = true;
    refreshSnapshot("idle");
    void runtimeControllerRef.current
      ?.reset()
      .then((runtimeSnapshot) => applyRuntimeSnapshot(runtimeSnapshot, "idle"))
      .catch((err) => {
        console.error("[AICC] runtime reset failed:", err);
        void loadScenarioFromObject(lastLoadedScenarioRef.current);
      });
  }, [applyRuntimeSnapshot, game, loadScenarioFromObject, refreshSnapshot]);

  useEffect(() => {
    if (runtimeBootstrappedRef.current) return;
    runtimeBootstrappedRef.current = true;

    const currentScenario = initialRuntimeScenarioRef.current;

    lastLoadedScenarioRef.current = currentScenario;
    void runtimeControllerRef.current
      ?.loadScenario(currentScenario)
      .then((runtimeSnapshot) => {
        applyRuntimeSnapshot(runtimeSnapshot, "idle");
        runtimeReadyRef.current = true;
      })
      .catch((err) => {
        console.error("[AICC] initial runtime sync failed:", err);
        window.alert("当前场景同步到后端推演引擎失败，推演控制暂不可用。");
      });
  }, [applyRuntimeSnapshot]);

  const handleNewScenario = useCallback(() => {
    if (
      !window.confirm("创建新场景将清空当前所有阵营、单位和任务，是否继续？")
    ) {
      return;
    }
    void loadScenarioFromObject(blankScenarioJson);
  }, [loadScenarioFromObject]);

  const handleLoadDemoScenario = useCallback(() => {
    void loadScenarioFromObject(defaultScenarioJson);
  }, [loadScenarioFromObject]);

  const handleLoadSCSScenario = useCallback(() => {
    void loadScenarioFromObject(SCSScenarioJson);
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
          void loadScenarioFromObject(parsed);
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
      const scenario = latestRuntimeScenarioRef.current;
      const json = JSON.stringify(scenario, null, 2);
      const blob = new Blob([json], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const ts = new Date().toISOString().replace(/[:.]/g, "_");
      const currentScenario = scenario.currentScenario as
        | { name?: unknown }
        | undefined;
      const safeName =
        String(currentScenario?.name || "tianshu_scenario")
          .trim()
          .replace(/[^A-Za-z0-9_-]+/g, "_")
          .slice(0, 60) || "tianshu_scenario";
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
  }, []);

  const exportCurrentScenarioObject = useCallback((): Record<
    string,
    unknown
  > | null => {
    return latestRuntimeScenarioRef.current;
  }, []);

  const applyRuntimeMutation = useCallback(
    async (
      mutation: (controller: RuntimeController) => Promise<RuntimeSnapshot>
    ) => {
      const controller = runtimeControllerRef.current;
      if (!controller) return;
      const runtimeSnapshot = await mutation(controller);
      applyRuntimeSnapshot(runtimeSnapshot, runtimeRunState(runtimeSnapshot), {
        preserveTimeCompression: true,
      });
      runtimeReadyRef.current = true;
    },
    [applyRuntimeSnapshot]
  );

  const deployRuntimeUnit = useCallback(
    (unit: RuntimeDeployUnitRequest) =>
      applyRuntimeMutation((controller) => controller.deployUnit(unit)),
    [applyRuntimeMutation]
  );

  const deleteRuntimeUnit = useCallback(
    (unitType: RuntimeUnitType, unitId: string) =>
      applyRuntimeMutation((controller) =>
        controller.deleteUnit(unitType, unitId)
      ),
    [applyRuntimeMutation]
  );

  const moveRuntimeUnit = useCallback(
    (
      unitType: RuntimeMoveUnitRequest["unit_type"],
      unitId: string,
      route: number[][]
    ) =>
      applyRuntimeMutation((controller) =>
        controller.moveUnit({ unit_type: unitType, unit_id: unitId, route })
      ),
    [applyRuntimeMutation]
  );

  const setRuntimeUnitPosition = useCallback(
    (position: RuntimeSetUnitPositionRequest) =>
      applyRuntimeMutation((controller) =>
        controller.setUnitPosition(position)
      ),
    [applyRuntimeMutation]
  );

  const updateRuntimeUnit = useCallback(
    (update: RuntimeUpdateUnitRequest) =>
      applyRuntimeMutation((controller) => controller.updateUnit(update)),
    [applyRuntimeMutation]
  );

  const addRuntimeWeapon = useCallback(
    (weapon: RuntimeAddWeaponRequest) =>
      applyRuntimeMutation((controller) => controller.addWeapon(weapon)),
    [applyRuntimeMutation]
  );

  const deleteRuntimeWeapon = useCallback(
    (weapon: RuntimeDeleteWeaponRequest) =>
      applyRuntimeMutation((controller) => controller.deleteWeapon(weapon)),
    [applyRuntimeMutation]
  );

  const updateRuntimeWeaponQuantity = useCallback(
    (weapon: RuntimeUpdateWeaponQuantityRequest) =>
      applyRuntimeMutation((controller) =>
        controller.updateWeaponQuantity(weapon)
      ),
    [applyRuntimeMutation]
  );

  const switchRuntimeSide = useCallback(
    (sideId: string) =>
      applyRuntimeMutation((controller) => controller.setCurrentSide(sideId)),
    [applyRuntimeMutation]
  );

  const createRuntimeSide = useCallback(
    (
      name: string,
      color: string,
      hostiles: string[],
      allies: string[],
      doctrine: SideDoctrine
    ) =>
      applyRuntimeMutation((controller) =>
        controller.createSide({
          name,
          color,
          hostiles,
          allies,
          doctrine: doctrine as unknown as RuntimeCreateSideRequest["doctrine"],
        })
      ),
    [applyRuntimeMutation]
  );

  const updateRuntimeSide = useCallback(
    (
      sideId: string,
      name: string,
      color: string,
      hostiles: string[],
      allies: string[],
      doctrine: SideDoctrine
    ) =>
      applyRuntimeMutation((controller) =>
        controller.updateSide(sideId, {
          name,
          color,
          hostiles,
          allies,
          doctrine: doctrine as unknown as RuntimeUpdateSideRequest["doctrine"],
        })
      ),
    [applyRuntimeMutation]
  );

  const deleteRuntimeSide = useCallback(
    (sideId: string) =>
      applyRuntimeMutation((controller) => controller.deleteSide(sideId)),
    [applyRuntimeMutation]
  );

  const createRuntimePatrolMission = useCallback(
    (name: string, assignedUnitIds: string[], referencePointIds: string[]) =>
      applyRuntimeMutation((controller) =>
        controller.createPatrolMission({
          name,
          assigned_unit_ids: assignedUnitIds,
          reference_point_ids: referencePointIds,
        })
      ),
    [applyRuntimeMutation]
  );

  const createRuntimeStrikeMission = useCallback(
    (name: string, assignedUnitIds: string[], assignedTargetIds: string[]) =>
      applyRuntimeMutation((controller) =>
        controller.createStrikeMission({
          name,
          assigned_unit_ids: assignedUnitIds,
          assigned_target_ids: assignedTargetIds,
        })
      ),
    [applyRuntimeMutation]
  );

  const updateRuntimePatrolMission = useCallback(
    (
      missionId: string,
      name: string,
      assignedUnitIds: string[],
      referencePointIds: string[]
    ) =>
      applyRuntimeMutation((controller) =>
        controller.updatePatrolMission(missionId, {
          name,
          assigned_unit_ids: assignedUnitIds,
          reference_point_ids: referencePointIds,
        })
      ),
    [applyRuntimeMutation]
  );

  const updateRuntimeStrikeMission = useCallback(
    (
      missionId: string,
      name: string,
      assignedUnitIds: string[],
      assignedTargetIds: string[]
    ) =>
      applyRuntimeMutation((controller) =>
        controller.updateStrikeMission(missionId, {
          name,
          assigned_unit_ids: assignedUnitIds,
          assigned_target_ids: assignedTargetIds,
        })
      ),
    [applyRuntimeMutation]
  );

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

  const deleteRuntimeMission = useCallback(
    (missionId: string) =>
      applyRuntimeMutation((controller) => controller.deleteMission(missionId)),
    [applyRuntimeMutation]
  );

  const deleteMission = useCallback(
    (missionId: string) => {
      const mission = game.currentScenario.missions.find(
        (item) => item.id === missionId
      );
      if (!mission) return;
      if (!window.confirm(`确认删除任务「${mission.name}」？`)) return;

      setMissionEditorMissionId((openMissionId) =>
        openMissionId === missionId ? null : openMissionId
      );
      void deleteRuntimeMission(missionId).catch((err) => {
        console.error("[AICC] runtime mission delete failed:", err);
        window.alert("后端删除任务失败，请稍后重试。");
      });
    },
    [deleteRuntimeMission, game]
  );

  useEffect(() => {
    refreshSnapshot("idle");

    return () => {
      playLoopRunning.current = false;
      game.scenarioPaused = true;
      void runtimeControllerRef.current
        ?.pause()
        .catch((err) =>
          console.error("[AICC] runtime cleanup pause failed", err)
        );
    };
  }, [game, refreshSnapshot]);

  // Poll the backend runtime while local playback is stopped so MCP-side
  // changes become visible without running a second simulation engine.
  useEffect(() => {
    if (scenarioMeta) return;
    if (!runtimeReadyRef.current) return;
    if (snapshot.runState === "running") return;

    const sync = async () => {
      try {
        const runtimeSnapshot = await runtimeControllerRef.current?.refresh();
        if (!runtimeSnapshot) return;

        const nextSignature = scenarioSignature(runtimeSnapshot.scenario);
        if (runtimeScenarioSignatureRef.current !== nextSignature) {
          applyRuntimeSnapshot(
            runtimeSnapshot,
            runtimeRunState(runtimeSnapshot),
            {
              preserveTimeCompression: true,
            }
          );
        }
      } catch {
        // best-effort，网络错误不影响前端正常运行
      }
    };

    void sync();
    const id = setInterval(sync, 3000);
    return () => clearInterval(id);
  }, [applyRuntimeSnapshot, scenarioMeta, snapshot.runState]);

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

  const handleSidebarResizeStart = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarRef.current?.getBoundingClientRect().width ?? 320;
    const sidebarMax = Math.max(360, Math.min(window.innerWidth - 360, 720));

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
      void runtimeControllerRef.current
        ?.refresh()
        .then((runtimeSnapshot) =>
          applyRuntimeSnapshot(
            runtimeSnapshot,
            runtimeRunState(runtimeSnapshot),
            {
              preserveTimeCompression: true,
            }
          )
        )
        .catch((err) => {
          console.error("[AICC] AI runtime refresh failed", err);
          latestRuntimeScenarioRef.current = data;
        });
    },
    [applyRuntimeSnapshot]
  );

  // Save / Save As use the authoritative backend runtime snapshot.
  const captureCurrentScenarioData = useCallback((): Record<
    string,
    unknown
  > => {
    return exportCurrentScenarioObject() ?? {};
  }, [exportCurrentScenarioObject]);

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

  const handleCreateBranchClick = useCallback(() => {
    if (!onCreateBranch) return;
    onCreateBranch(captureCurrentScenarioData());
  }, [onCreateBranch, captureCurrentScenarioData]);

  const toggleTimelinePanel = useCallback(() => {
    if (!timelinePanelOpen) setAiSidebarOpen(false);
    setTimelinePanelOpen((value) => !value);
  }, [timelinePanelOpen]);

  useEffect(() => {
    const projectId = scenarioMeta?.id;
    if (!projectId || autoOpenedAiScenarioRef.current === projectId) return;
    autoOpenedAiScenarioRef.current = projectId;
    setTimelinePanelOpen(false);
    setAiSidebarOpen(true);
  }, [scenarioMeta?.id]);

  const toggleAiSidebar = useCallback(() => {
    if (!aiSidebarOpen) setTimelinePanelOpen(false);
    setAiSidebarOpen((value) => !value);
  }, [aiSidebarOpen]);

  // 是否需要渲染顶部 mini bar（路由模式才显示；standalone 兼容老入口）。
  const showRouterChrome = Boolean(
    scenarioMeta && (onSave || onRequestSaveAs || onCreateBranch || onExit)
  );

  return (
    <div
      className="dark h-screen overflow-hidden bg-tactical-bg text-tactical-text lg:grid"
      style={{
        gridTemplateColumns: [
          "64px",
          sidebarCollapsed ? "0px" : sidebarTrack,
          "minmax(0,1fr)",
          aiSidebarOpen ? aiSidebarTrack : "0px",
        ].join(" "),
        gridTemplateRows: "3.5rem minmax(0,1fr)",
      }}
    >
      <motion.nav
        animate={{ opacity: 1 }}
        className="hidden border-r border-cyan-300/10 bg-[#030912]/95 px-2 py-5 backdrop-blur-2xl lg:flex lg:flex-col"
        initial={{ opacity: 0 }}
        style={{ gridColumn: "1 / 2", gridRow: "1 / 3" }}
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
            aria-label={aiSidebarOpen ? "关闭 AI 侧栏" : "打开 AI 侧栏"}
            className={cn(
              "size-10",
              aiSidebarOpen ? "text-cyan-100 shadow-hud-cyan" : "text-slate-400"
            )}
            onClick={toggleAiSidebar}
            size="icon"
            title="AI 助手"
            variant={aiSidebarOpen ? "tactical" : "ghost"}
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
              settingsModalOpen
                ? "text-cyan-100 shadow-hud-cyan"
                : "text-slate-400"
            )}
            onClick={() => setSettingsModalOpen((value) => !value)}
            size="icon"
            title="AI / 系统设置"
            variant={settingsModalOpen ? "tactical" : "ghost"}
          >
            <Settings className="size-4" />
          </Button>
        </div>
      </motion.nav>

      {!sidebarCollapsed && (
        <div
          className="relative hidden h-full min-h-0 min-w-0 lg:flex"
          ref={sidebarRef}
          style={{ gridColumn: "2 / 3", gridRow: "1 / 3" }}
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
            onSwitchSide={switchRuntimeSide}
            onCreateSide={createRuntimeSide}
            onUpdateSide={updateRuntimeSide}
            onDeleteSide={deleteRuntimeSide}
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

      <div
        className="relative z-40 min-w-0"
        style={{ gridColumn: "3 / 5", gridRow: "1 / 2" }}
      >
        <TopTacticalBar
          snapshot={snapshot}
          aiSidebarOpen={aiSidebarOpen}
          onToggleAiSidebar={toggleAiSidebar}
          settingsOpen={settingsModalOpen}
          onToggleSettings={() => setSettingsModalOpen((value) => !value)}
          scenarioMeta={scenarioMeta}
          onExit={onExit}
          onSave={onSave ? () => void handleSaveClick() : undefined}
          onRequestSaveAs={
            onRequestSaveAs ? () => handleSaveAsClick() : undefined
          }
          onCreateBranch={
            onCreateBranch ? () => handleCreateBranchClick() : undefined
          }
          savingState={savingState}
          timelineOpen={timelinePanelOpen}
          onToggleTimeline={toggleTimelinePanel}
          mapSceneMode={mapSceneMode}
          onToggleMapSceneMode={() =>
            setMapSceneMode((value) => (value === "3d" ? "2d" : "3d"))
          }
        />
      </div>

      <main
        className="relative isolate z-0 flex min-h-0 min-w-0 flex-col overflow-hidden bg-[#050914]"
        style={{ gridColumn: "3 / 4", gridRow: "2 / 3" }}
      >
        {/*
          地图区域：占据 main 列剩余高度。Cesium 在 embedded 模式下用
          position:absolute 填满父容器，所以这里必须 relative + 显式高度。
        */}
        <div className="relative min-h-0 flex-1">
          <CesiumScenarioMap
            baseLayer={mapBaseLayer}
            embedded
            game={game}
            missionCreatorOpen={missionCreatorOpen}
            missionEditorMissionId={missionEditorMissionId}
            mobileView={false}
            placement={placement}
            onMissionCreatorOpenChange={setMissionCreatorOpen}
            onMissionEditorMissionIdChange={setMissionEditorMissionId}
            onBaseLayerChange={setMapBaseLayer}
            onPlacementChange={setPlacement}
            onPlay={() => void playSimulation()}
            onPause={pauseSimulation}
            onStep={stepSimulation}
            onReset={resetSimulation}
            onDeployUnit={deployRuntimeUnit}
            onDeleteUnit={deleteRuntimeUnit}
            onMoveUnit={moveRuntimeUnit}
            onSetUnitPosition={setRuntimeUnitPosition}
            onUpdateUnit={updateRuntimeUnit}
            onAddWeapon={addRuntimeWeapon}
            onDeleteWeapon={deleteRuntimeWeapon}
            onUpdateWeaponQuantity={updateRuntimeWeaponQuantity}
            onCreatePatrolMission={createRuntimePatrolMission}
            onCreateStrikeMission={createRuntimeStrikeMission}
            onUpdatePatrolMission={updateRuntimePatrolMission}
            onUpdateStrikeMission={updateRuntimeStrikeMission}
            onDeleteMission={deleteRuntimeMission}
            onSceneModeChange={setMapSceneMode}
            runtimeVisibility={snapshot.visibility}
            sceneMode={mapSceneMode}
            showToolbar={false}
            showRanges={showRanges}
            showRoutes={showRoutes}
          />

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
        activeTab="chat"
        onApplyScenario={handleApplyAiScenario}
        onOpenChange={setAiSidebarOpen}
        onResumePlay={playSimulation}
        onSettingsOpenChange={setSettingsModalOpen}
        onTabChange={() => setAiSidebarOpen(true)}
        mapBaseLayer={mapBaseLayer}
        open={aiSidebarOpen}
        onMapBaseLayerChange={setMapBaseLayer}
        scenarioId={chatScenarioId}
        settingsOpen={settingsModalOpen}
        panelClassName="shadow-[-24px_0_70px_rgba(0,0,0,0.35)]"
        panelStyle={{ gridColumn: "4 / 5", gridRow: "2 / 3" }}
      />

      <TimelineReplayPanel
        onClose={() => setTimelinePanelOpen(false)}
        open={timelinePanelOpen}
        runtimeScenarioId={scenarioId}
        scenarioId={scenarioMeta?.id}
        snapshot={snapshot}
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
