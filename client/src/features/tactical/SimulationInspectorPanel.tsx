import { motion } from "framer-motion";
import {
  Activity,
  CircleDot,
  ClipboardList,
  ShieldAlert,
  Terminal,
} from "lucide-react";
import Game, { type Mission } from "@/game/Game";
import {
  isHostileToCurrentSide,
  isScenarioObjectVisible,
} from "@/game/scenarioVisibility";
import type { SimulationSnapshot } from "./SimulationSidebar";

interface SimulationInspectorPanelProps {
  game: Game;
  snapshot: SimulationSnapshot;
}

const sideNameMap: Record<string, string> = {
  BLUE: "蓝方",
  RED: "红方",
  ALLY: "盟友",
  NEUTRAL: "中立",
};

const logTypeMap: Record<string, string> = {
  AIRCRAFT_CRASHED: "飞机坠毁",
  OTHER: "系统",
  RETURN_TO_BASE: "返航",
  STRIKE_MISSION_ABORTED: "打击中止",
  STRIKE_MISSION_SUCCESS: "打击成功",
  WEAPON_CRASHED: "武器坠毁",
  WEAPON_EXPENDED: "武器耗尽",
  WEAPON_HIT: "命中",
  WEAPON_LAUNCHED: "发射",
  WEAPON_MISSED: "脱靶",
};

function normalizeSideName(name: string) {
  return sideNameMap[name.toUpperCase()] ?? name;
}

function formatElapsed(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return `T+${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}:${String(secs).padStart(2, "0")}`;
}

function formatLogTime(timestamp: number, scenarioStartTime: number) {
  if (timestamp > 10_000_000_000) {
    return new Date(timestamp).toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  return formatElapsed(timestamp - scenarioStartTime);
}

function statusLabel(snapshot: SimulationSnapshot) {
  if (snapshot.runState === "running") return "SIMULATION ACTIVE";
  if (snapshot.runState === "paused") return "SIMULATION PAUSED";
  return "STANDBY";
}

function missionTypeLabel(mission: Mission) {
  return "assignedTargetIds" in mission ? "打击任务" : "巡逻任务";
}

export default function SimulationInspectorPanel({
  game,
  snapshot,
}: SimulationInspectorPanelProps) {
  const scenario = game.currentScenario;
  const visibility = {
    godMode: snapshot.godMode,
    currentSideId: snapshot.currentSideId,
  };
  const progress =
    snapshot.duration > 0
      ? Math.min(100, (snapshot.elapsedSeconds / snapshot.duration) * 100)
      : 0;

  const sideSummaries = scenario.sides.map((side) => {
    const hostile = isHostileToCurrentSide(
      scenario,
      side.id,
      snapshot.currentSideId
    );
    const restricted = !snapshot.godMode && hostile;
    const visibleAircraft = scenario.aircraft.filter(
      (unit) =>
        unit.sideId === side.id &&
        isScenarioObjectVisible(scenario, unit, visibility)
    ).length;
    const visibleShips = scenario.ships.filter(
      (unit) =>
        unit.sideId === side.id &&
        isScenarioObjectVisible(scenario, unit, visibility)
    ).length;
    const visibleFacilities = scenario.facilities.filter(
      (unit) =>
        unit.sideId === side.id &&
        isScenarioObjectVisible(scenario, unit, visibility)
    ).length;
    const detectedCount = visibleAircraft + visibleShips + visibleFacilities;

    return {
      id: side.id,
      name: normalizeSideName(side.name),
      color: side.color,
      hostile,
      restricted,
      detectedCount,
      aircraft: restricted
        ? visibleAircraft
        : scenario.aircraft.filter((unit) => unit.sideId === side.id).length,
      ships: restricted
        ? visibleShips
        : scenario.ships.filter((unit) => unit.sideId === side.id).length,
      facilities: restricted
        ? visibleFacilities
        : scenario.facilities.filter((unit) => unit.sideId === side.id).length,
      missions: restricted
        ? "未知"
        : scenario.missions.filter((mission) => mission.sideId === side.id)
            .length,
    };
  });

  const recentLogs = game.simulationLogs
    .getLogs()
    .filter(
      (log) =>
        snapshot.godMode ||
        !isHostileToCurrentSide(scenario, log.sideId, snapshot.currentSideId)
    )
    .slice(-8)
    .reverse();
  const activeMissions = scenario.missions
    .filter(
      (mission) =>
        snapshot.godMode ||
        !isHostileToCurrentSide(
          scenario,
          mission.sideId,
          snapshot.currentSideId
        )
    )
    .slice(0, 6);

  return (
    <motion.aside
      animate={{ opacity: 1, y: 0 }}
      className="hidden shrink-0 border-t border-cyan-400/20 bg-[#020610]/80 backdrop-blur-2xl shadow-[0_-8px_40px_rgba(8,145,178,0.08)] lg:flex lg:h-[200px] lg:flex-row"
      initial={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      {/* 1. STATUS MODULE (Left) */}
      <div className="relative flex w-72 shrink-0 flex-col justify-between overflow-hidden border-r border-cyan-400/10 bg-cyan-950/10 p-4">
        <div className="pointer-events-none absolute inset-0 mix-blend-overlay opacity-10" />

        <div className="relative z-10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`size-2 rounded-full ${
                snapshot.runState === "running"
                  ? "animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                  : "bg-amber-400"
              }`}
            />
            <span className="font-mono text-[11px] font-semibold tracking-[0.2em] text-cyan-400">
              {statusLabel(snapshot)}
            </span>
          </div>
          <span className="rounded border border-cyan-400/20 bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
            {snapshot.timeCompression}x
          </span>
        </div>

        <div className="relative z-10 mt-auto">
          <div className="font-mono text-[2.2rem] font-light tracking-tight text-slate-100 drop-shadow-[0_0_8px_rgba(255,255,255,0.2)]">
            {formatElapsed(snapshot.elapsedSeconds)}
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] uppercase tracking-widest text-slate-500">
            <span className="truncate pr-2">{snapshot.scenarioName}</span>
            <span className="text-cyan-500/70">{Math.round(progress)}%</span>
          </div>
          <div className="mt-2 h-[2px] w-full overflow-hidden rounded-full bg-slate-800/80">
            <div
              className="h-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.6)] transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* 2. AI TACTICAL TIMELINE (Middle) */}
      <div className="relative flex flex-1 flex-col overflow-hidden p-4">
        <div className="pointer-events-none absolute right-1/4 top-0 h-full w-96 bg-cyan-500/5 blur-[80px]" />

        <div className="mb-3 flex shrink-0 items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-cyan-400/60">
          <Terminal className="size-3" />
          <span>Tactical Timeline</span>
          <div className="ml-2 h-px flex-1 bg-gradient-to-r from-cyan-400/20 to-transparent" />
        </div>

        <div className="flex-1 overflow-y-auto pr-4 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
          <div className="flex flex-col">
            {recentLogs.length > 0 ? (
              recentLogs.map((log) => (
                <div
                  key={log.id}
                  className="group relative flex items-start gap-4"
                >
                  {/* Timeline Line */}
                  <div className="absolute bottom-[-16px] left-[3px] top-4 w-px bg-cyan-400/10 group-last:hidden" />

                  {/* Timeline Dot */}
                  <div className="relative z-10 mt-1.5 flex shrink-0 items-center justify-center bg-[#020610]">
                    <div className="size-2 rounded-full border border-cyan-400/50 bg-cyan-950 transition-all group-hover:bg-cyan-400 group-hover:shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
                  </div>

                  {/* Content */}
                  <div className="flex-1 pb-3">
                    <div className="rounded-lg border border-white/[0.02] bg-white/[0.01] px-3 py-2 transition-colors group-hover:border-cyan-400/20 group-hover:bg-cyan-400/5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] text-cyan-400/60">
                          {formatLogTime(log.timestamp, scenario.startTime)}
                        </span>
                        <span className="rounded border border-emerald-400/20 bg-emerald-400/10 px-1.5 py-px text-[9px] text-emerald-300">
                          {logTypeMap[log.type] ?? log.type}
                        </span>
                        <span className="ml-auto truncate font-mono text-[10px] text-slate-600 opacity-0 transition-opacity group-hover:opacity-100">
                          {log.id.split("-")[0]}
                        </span>
                      </div>
                      <div className="mt-1.5 text-xs leading-relaxed text-slate-300">
                        {log.message}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="mt-2 flex items-center gap-3 font-mono text-xs text-slate-600">
                <div className="size-1.5 animate-pulse rounded-full bg-slate-800" />
                Awaiting tactical events...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. FORCES & MISSIONS (Right) */}
      <div className="relative flex w-[320px] shrink-0 flex-col border-l border-cyan-400/10 bg-[#01040a] p-4 shadow-[inset_10px_0_20px_rgba(0,0,0,0.2)]">
        <div className="mb-3 flex shrink-0 items-center justify-between text-[10px] uppercase tracking-[0.2em] text-cyan-400/60">
          <div className="flex items-center gap-2">
            <ShieldAlert className="size-3" />
            <span>Forces & Queue</span>
          </div>
          <span className="font-mono text-cyan-500/80">
            {snapshot.aircraft + snapshot.ships} ACTV
          </span>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto pr-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-cyan-900/50">
          {sideSummaries.map((side) => (
            <div
              key={side.id}
              className="flex flex-col justify-center rounded-lg border border-cyan-400/10 bg-cyan-950/10 px-3 py-2 transition-colors hover:border-cyan-400/30"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="size-1.5 rounded-full"
                    style={{
                      backgroundColor: side.color,
                      boxShadow: `0 0 6px ${side.color}`,
                    }}
                  />
                  <span className="text-xs font-semibold text-slate-200">
                    {side.name}
                  </span>
                </div>
                <div className="flex items-center gap-2 font-mono text-[10px] text-slate-400">
                  <span title="Aircraft">A/C: {side.aircraft}</span>
                  <span className="text-slate-600">|</span>
                  <span title="Ships">SHP: {side.ships}</span>
                  <span className="text-slate-600">|</span>
                  <span className="text-cyan-400/80" title="Missions">
                    MSN: {side.missions}
                  </span>
                </div>
              </div>
            </div>
          ))}

          {/* Minimal Mission Queue */}
          <div className="mt-3 border-t border-cyan-400/10 pt-3">
            <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
              Active Missions
            </div>
            {activeMissions.length > 0 ? (
              <div className="space-y-1">
                {activeMissions.map((m) => (
                  <div
                    key={m.id}
                    className="flex items-center gap-2 text-[11px]"
                  >
                    <CircleDot className="size-3 text-emerald-400/70" />
                    <span className="truncate text-slate-300">{m.name}</span>
                    <span className="ml-auto shrink-0 rounded bg-white/5 px-1 font-mono text-[9px] text-slate-500">
                      {missionTypeLabel(m).slice(0, 2)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="font-mono text-[10px] text-slate-600">
                No active missions
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.aside>
  );
}
