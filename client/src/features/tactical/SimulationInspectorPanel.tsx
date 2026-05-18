import { motion } from "framer-motion";
import {
  Activity,
  CircleDot,
  ClipboardList,
  ShieldAlert,
  Terminal,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  if (snapshot.runState === "running") return "推演运行中";
  if (snapshot.runState === "paused") return "推演暂停";
  return "待命";
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
      animate={{ opacity: 1, x: 0 }}
      className="hidden min-h-0 border-l border-cyan-300/10 bg-[#050b13]/90 p-3 backdrop-blur-2xl lg:flex lg:flex-col"
      initial={{ opacity: 0, x: 18 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-3 px-1">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-cyan-300/70">
              Simulation Ops
            </div>
            <div className="mt-1 text-lg font-semibold text-slate-100">
              仿真态势面板
            </div>
          </div>
          <div className="rounded-full border border-cyan-300/20 bg-cyan-300/8 px-2.5 py-1 text-[11px] text-cyan-100">
            仿真优先
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
        <Card className="border-cyan-300/12 bg-[#07111d]/82">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-emerald-300" />
              当前推演
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-xl border border-cyan-300/10 bg-slate-950/35 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-100">
                    {statusLabel(snapshot)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {snapshot.scenarioName}
                  </div>
                </div>
                <div className="font-mono text-sm text-cyan-200">
                  {snapshot.timeCompression}x
                </div>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-900">
                <div
                  className="h-full rounded-full bg-emerald-300 transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                <span>{formatElapsed(snapshot.elapsedSeconds)}</span>
                <span>{Math.round(progress)}%</span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {[
                [
                  "单位",
                  snapshot.aircraft + snapshot.ships + snapshot.facilities,
                ],
                ["任务", snapshot.missions],
                ["武器", snapshot.weapons],
              ].map(([label, value]) => (
                <div
                  className="rounded-lg border border-cyan-300/10 bg-white/[0.03] p-3 text-center"
                  key={label}
                >
                  <div className="font-mono text-lg font-bold text-cyan-100">
                    {value}
                  </div>
                  <div className="text-[11px] text-slate-500">{label}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-cyan-300/12 bg-[#07111d]/82">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="size-4 text-cyan-200" />
              阵营态势
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {sideSummaries.map((side) => (
              <div
                className="rounded-xl border border-cyan-300/10 bg-slate-950/35 p-3"
                key={side.id}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className="size-2.5 rounded-full"
                      style={{ backgroundColor: side.color }}
                    />
                    <span className="text-sm font-semibold text-slate-100">
                      {side.name}
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {side.id === snapshot.currentSideId
                      ? "当前视角"
                      : side.restricted
                        ? side.detectedCount > 0
                          ? `探测到 ${side.detectedCount} 个目标`
                          : "未探测"
                        : "可观测"}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                  {[
                    ["机", side.aircraft],
                    ["舰", side.ships],
                    ["设", side.facilities],
                    ["任", side.missions],
                  ].map(([label, value]) => (
                    <div
                      className="rounded-md bg-white/[0.04] px-2 py-1.5"
                      key={label}
                    >
                      <div className="font-mono text-sm text-cyan-100">
                        {value}
                      </div>
                      <div className="text-[10px] text-slate-500">{label}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border-cyan-300/12 bg-[#07111d]/82">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <ClipboardList className="size-4 text-emerald-300" />
              任务队列
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {activeMissions.length > 0 ? (
              activeMissions.map((mission) => (
                <div
                  className="flex items-center justify-between rounded-lg border border-cyan-300/10 bg-slate-950/35 px-3 py-2"
                  key={mission.id}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm text-slate-100">
                      {mission.name}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {missionTypeLabel(mission)}
                    </div>
                  </div>
                  <CircleDot className="size-4 shrink-0 text-emerald-300" />
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-dashed border-cyan-300/12 bg-white/[0.02] p-4 text-center text-xs text-slate-500">
                当前没有任务。可在地图单位详情里规划航线或创建任务。
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-cyan-300/12 bg-[#07111d]/82">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <Terminal className="size-4 text-cyan-200" />
              仿真日志
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="min-h-36 rounded-xl border border-cyan-300/10 bg-[#020711] p-3 font-mono text-[11px] leading-relaxed text-slate-400">
              {recentLogs.length > 0 ? (
                recentLogs.map((log) => (
                  <div className="mb-2 last:mb-0" key={log.id}>
                    <span className="text-cyan-300/70">
                      {formatLogTime(log.timestamp, scenario.startTime)}
                    </span>
                    <span className="mx-2 text-slate-600">|</span>
                    <span className="text-emerald-300/80">
                      {logTypeMap[log.type] ?? log.type}
                    </span>
                    <span className="mx-2 text-slate-600">|</span>
                    <span>{log.message}</span>
                  </div>
                ))
              ) : (
                <div className="text-slate-600">
                  等待推演事件。点击“开始”或“单步”后，武器发射、命中、返航等事件会在这里出现。
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="mt-auto border-cyan-300/10 bg-white/[0.03]">
          <CardContent className="p-4 text-xs leading-relaxed text-slate-400">
            当前右侧面板只显示 AICC 仿真态势、阵营态势、任务队列和事件日志。
          </CardContent>
        </Card>
      </div>
    </motion.aside>
  );
}
