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
  Boxes,
  ChevronLeft,
  ChevronRight,
  Command,
  Crosshair,
  Layers3,
  Map,
  Settings,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Game from "@/game/Game";
import Scenario from "@/game/Scenario";
import { SetScenarioTimeContext } from "@/gui/contextProviders/contexts/ScenarioTimeContext";
import CesiumScenarioMap from "@/gui/map/CesiumScenarioMap";
import type { CesiumPlacement } from "@/gui/map/CesiumToolbar";
import SCSScenarioJson from "@/scenarios/SCS.json";
import blankScenarioJson from "@/scenarios/blank_scenario.json";
import defaultScenarioJson from "@/scenarios/default_scenario.json";
import { isScenarioObjectVisible } from "@/game/scenarioVisibility";
import { cn } from "@/lib/utils";
import { randomUUID } from "@/utils/generateUUID";
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

function createAiccGame() {
  const currentScenario = new Scenario({
    id: randomUUID(),
    name: "AICC Tactical Simulation",
    startTime: 1699073110,
    duration: 14400,
  });
  const game = new Game(currentScenario);
  game.loadScenario(JSON.stringify(SCSScenarioJson));
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

export default function AITacticalCommandPlatform() {
  const [game] = useState(createAiccGame);
  const setScenarioTime = useContext(SetScenarioTimeContext);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeRailItem, setActiveRailItem] =
    useState<SimulationPanelId>("simulation");
  const [missionCreatorOpen, setMissionCreatorOpen] = useState(false);
  const [missionEditorMissionId, setMissionEditorMissionId] = useState<
    string | null
  >(null);
  const [showRoutes, setShowRoutes] = useState(false);
  const [showRanges, setShowRanges] = useState(false);
  const [placement, setPlacement] = useState<CesiumPlacement | null>(null);
  const runStateRef = useRef<SimulationRunState>("idle");
  const playLoopRunning = useRef(false);
  const [aarOpen, setAarOpen] = useState(false);
  // 仅在「未关闭过此局 AAR」时自动弹出；用户主动关闭后不再骚扰。
  const aarHandledOutcomeRef = useRef<string>("");
  const [snapshot, setSnapshot] = useState<SimulationSnapshot>(() =>
    buildSimulationSnapshot(game, "idle")
  );

  const refreshSnapshot = useCallback(
    (runState: SimulationRunState = runStateRef.current) => {
      runStateRef.current = runState;
      setScenarioTime(game.currentScenario.currentTime);
      setSnapshot(buildSimulationSnapshot(game, runState));
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
  }, [
    snapshot.outcome.ended,
    snapshot.outcome.reason,
    snapshot.outcome.winnerSideId,
    snapshot.outcome.endedAt,
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
  const rightSidebarTrack = "clamp(18rem, 24vw, 26rem)";

  return (
    <div
      className="dark h-screen overflow-hidden bg-tactical-bg text-tactical-text lg:grid"
      style={{
        gridTemplateColumns: sidebarCollapsed
          ? `64px minmax(0,1fr) ${rightSidebarTrack}`
          : `64px ${sidebarTrack} minmax(0,1fr) ${rightSidebarTrack}`,
      }}
    >
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
            aria-label="系统设置"
            className="size-10"
            size="icon"
            variant="ghost"
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

      <main className="relative min-h-0 overflow-hidden bg-[#050914]">
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
      </main>

      <SimulationInspectorPanel game={game} snapshot={snapshot} />

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
