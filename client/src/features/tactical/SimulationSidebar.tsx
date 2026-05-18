import { AnimatePresence, motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Clock3,
  Crosshair,
  Download,
  Edit3,
  FileText,
  FilePlus,
  ListChecks,
  MapPin,
  Pause,
  Plane,
  Play,
  Plus,
  Radar,
  RefreshCcw,
  Route,
  Satellite,
  Shield,
  Ship,
  SkipForward,
  Sparkles,
  Target,
  Trash2,
  Trophy,
  Upload,
  Waves,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DoctrineType } from "@/game/Doctrine";
import type Game from "@/game/Game";
import type { GameOutcome, Mission } from "@/game/Game";
import type Scenario from "@/game/Scenario";
import type Side from "@/game/Side";
import type { CesiumPlacement } from "@/gui/map/CesiumToolbar";
import SideEditor from "@/gui/map/toolbar/SideEditor";
import { AirbaseDb, AircraftDb, FacilityDb, ShipDb } from "@/game/db/UnitDb";
import {
  localizeAirbaseName,
  localizeClassName,
  localizeSideName,
  localizeUnitName,
} from "@/i18n/entityNames";
import { cn } from "@/lib/utils";

export type SimulationRunState = "idle" | "running" | "paused";
export type SimulationPanelId = "command" | "simulation" | "layers" | "assets";

export interface SimulationSideStats {
  id: string;
  name: string;
  colorHex: string;
  score: number;
  aircraft: number;
  ships: number;
  facilities: number;
  airbases: number;
}

export interface SimulationSnapshot {
  runState: SimulationRunState;
  scenarioName: string;
  timeCompression: number;
  currentTime: number;
  elapsedSeconds: number;
  duration: number;
  aircraft: number;
  ships: number;
  facilities: number;
  airbases: number;
  referencePoints: number;
  weapons: number;
  missions: number;
  sides: number;
  currentSideId: string;
  godMode: boolean;
  eraserMode: boolean;
  // 胜负判定状态 + 各阵营实时评分，供「战况」Section 与 AAR 弹窗复用。
  outcome: GameOutcome;
  sideStats: SimulationSideStats[];
}

interface SimulationSidebarProps {
  activePanel: SimulationPanelId;
  game: Game;
  snapshot: SimulationSnapshot;
  onPlay: () => void;
  onPause: () => void;
  onStep: () => void;
  onReset: () => void;
  onSetSpeed: (speed: number) => void;
  onToggleGodMode: () => void;
  onToggleEraser: () => void;
  showRoutes: boolean;
  showRanges: boolean;
  onToggleRoutes: () => void;
  onToggleRanges: () => void;
  onOpenMissionCreator: () => void;
  onOpenMissionEditor: (missionId: string) => void;
  onDeleteMission: (missionId: string) => void;
  onBeginPlacement: (placement: CesiumPlacement) => void;
  onScenarioMutation: () => void;
  onNewScenario: () => void;
  onLoadDemoScenario: () => void;
  onLoadSCSScenario: () => void;
  onImportScenario: () => void;
  onExportScenario: () => void;
}

const speeds = [1, 2, 4, 8, 16, 32, 64];

const sideNameMap: Record<string, string> = {
  ALLY: "盟友",
  BLUE: "蓝方",
  NEUTRAL: "中立",
  RED: "红方",
};

const panelMeta: Record<
  SimulationPanelId,
  { eyebrow: string; title: string; description: string }
> = {
  command: {
    eyebrow: "Command",
    title: "指挥控制台",
    description: "阵营、敌我关系和自动交战规则",
  },
  simulation: {
    eyebrow: "Simulation",
    title: "仿真控制台",
    description: "时间、推演状态和回放节奏",
  },
  layers: {
    eyebrow: "Map Layers",
    title: "图层与视角",
    description: "上帝视角、阵营视角和地图交互",
  },
  assets: {
    eyebrow: "Assets",
    title: "作战单位",
    description: "AICC 场景对象和可见单位统计",
  },
};

function normalizeSideName(name: string) {
  return sideNameMap[name.toUpperCase()] ?? localizeSideName(name);
}

function countUnitsForSide(scenario: Scenario, sideId: string) {
  return (
    scenario.aircraft.filter((unit) => unit.sideId === sideId).length +
    scenario.ships.filter((unit) => unit.sideId === sideId).length +
    scenario.facilities.filter((unit) => unit.sideId === sideId).length +
    scenario.airbases.filter((unit) => unit.sideId === sideId).length
  );
}

function isStrikeMission(
  mission: Mission
): mission is Mission & { assignedTargetIds: string[] } {
  return "assignedTargetIds" in mission;
}

function missionTypeLabel(mission: Mission) {
  return isStrikeMission(mission) ? "打击任务" : "巡逻任务";
}

function resolveScenarioObjectName(scenario: Scenario, id: string) {
  const target =
    scenario.getAircraft(id) ??
    scenario.getShip(id) ??
    scenario.getFacility(id) ??
    scenario.getAirbase(id) ??
    scenario.getReferencePoint(id);

  return target ? localizeUnitName(target.name) : id;
}

function missionUnitSummary(scenario: Scenario, mission: Mission) {
  const unitNames = mission.assignedUnitIds.map((id) =>
    resolveScenarioObjectName(scenario, id)
  );

  return unitNames.length > 0 ? unitNames.join("、") : "未设置执行单位";
}

function missionDetailSummary(scenario: Scenario, mission: Mission) {
  if (isStrikeMission(mission)) {
    const targets = mission.assignedTargetIds.map((id) =>
      resolveScenarioObjectName(scenario, id)
    );
    return targets.length > 0 ? `目标: ${targets.join("、")}` : "目标: 未设置";
  }

  const area = mission.assignedArea.map((point) =>
    localizeUnitName(point.name)
  );
  return area.length > 0 ? `区域: ${area.join("、")}` : "区域: 未设置";
}

function Section({
  title,
  icon: Icon,
  children,
  defaultOpen = true,
}: {
  title: string;
  icon?: LucideIcon;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-cyan-300/12 bg-[#07111d]/70 shadow-[inset_0_1px_0_rgba(103,232,249,0.08)] overflow-hidden">
      <details className="group" open={defaultOpen}>
        <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
          {Icon && (
            <div className="grid size-7 place-items-center rounded-lg border border-cyan-300/14 bg-cyan-300/8 text-cyan-200">
              <Icon className="size-4" />
            </div>
          )}
          <span className="text-sm font-semibold text-slate-100">{title}</span>
          <ChevronDown className="ml-auto size-4 text-slate-500 transition-transform group-open:rotate-180" />
        </summary>
        <div className="px-3 pb-3 pt-1">{children}</div>
      </details>
    </div>
  );
}

function MissionSummaryCard({
  mission,
  scenario,
  onEdit,
  onDelete,
}: {
  mission: Mission;
  scenario: Scenario;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="box-border block w-full min-w-0 max-w-full overflow-hidden rounded-xl border border-cyan-300/10 bg-slate-950/32 p-3 text-left transition-all hover:border-cyan-300/35 hover:bg-cyan-300/8">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-100">
            {localizeUnitName(mission.name)}
          </div>
          <div className="mt-2 flex max-w-full flex-wrap gap-1.5">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px]",
                isStrikeMission(mission)
                  ? "border-red-300/20 bg-red-400/10 text-red-200"
                  : "border-emerald-300/20 bg-emerald-300/10 text-emerald-200"
              )}
            >
              {missionTypeLabel(mission)}
            </span>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px]",
                mission.active
                  ? "border-cyan-300/18 bg-cyan-300/8 text-cyan-200"
                  : "border-slate-500/20 bg-white/5 text-slate-400"
              )}
            >
              {mission.active ? "启用" : "停用"}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            aria-label={`编辑任务 ${mission.name}`}
            className="grid size-8 place-items-center rounded-lg border border-cyan-300/14 bg-cyan-300/8 text-cyan-100 transition-all hover:border-cyan-300/45"
            onClick={onEdit}
            title="编辑任务"
            type="button"
          >
            <Edit3 className="size-3.5" />
          </button>
          <button
            aria-label={`删除任务 ${mission.name}`}
            className="grid size-8 place-items-center rounded-lg border border-red-300/14 bg-red-500/8 text-red-200 transition-all hover:border-red-300/45"
            onClick={onDelete}
            title="删除任务"
            type="button"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs">
        <span className="text-slate-500">阵营</span>
        <span className="truncate text-slate-400">
          {normalizeSideName(scenario.getSideName(mission.sideId))}
        </span>
        <span className="text-slate-500">单位</span>
        <span className="truncate text-slate-400">
          {missionUnitSummary(scenario, mission)}
        </span>
        <span className="text-slate-500">范围</span>
        <span className="truncate text-slate-500">
          {missionDetailSummary(scenario, mission)}
        </span>
      </div>
    </div>
  );
}

function CountTile({
  icon: Icon,
  label,
  value,
  tone = "cyan",
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  tone?: "cyan" | "red" | "green";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-slate-950/35 p-3 transition-all hover:bg-white/[0.04]",
        tone === "cyan" && "border-cyan-300/14 text-cyan-100",
        tone === "red" && "border-red-300/14 text-red-100",
        tone === "green" && "border-emerald-300/14 text-emerald-100"
      )}
    >
      <Icon className="mb-2 size-5" />
      <div className="font-mono text-lg font-bold leading-none">{value}</div>
      <div className="mt-1 text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

function InfoRow({
  label,
  value,
  tone = "cyan",
}: {
  label: string;
  value: ReactNode;
  tone?: "cyan" | "green" | "red" | "amber";
}) {
  return (
    <div className="min-w-0 rounded-xl border border-cyan-300/10 bg-slate-950/32 px-3 py-2.5">
      <span className="block truncate text-[11px] text-slate-500">{label}</span>
      <span
        className={cn(
          "mt-1 block truncate font-mono text-xs",
          tone === "cyan" && "text-cyan-200",
          tone === "green" && "text-emerald-200",
          tone === "red" && "text-red-200",
          tone === "amber" && "text-amber-200"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function DoctrineRow({
  label,
  enabled,
  description,
}: {
  label: string;
  enabled?: boolean;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-cyan-300/10 bg-slate-950/35 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-100">{label}</span>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[11px]",
            enabled
              ? "border-emerald-300/24 bg-emerald-300/10 text-emerald-200"
              : "border-slate-500/20 bg-white/5 text-slate-400"
          )}
        >
          {enabled ? "启用" : "关闭"}
        </span>
      </div>
      <div className="mt-1 text-xs leading-relaxed text-slate-500">
        {description}
      </div>
    </div>
  );
}

function PlacementActionCard({
  icon: Icon,
  title,
  description,
  disabled,
  onClick,
  className,
  expanded,
  controls,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  disabled?: boolean;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
  className?: string;
  expanded?: boolean;
  controls?: string;
}) {
  return (
    <button
      aria-controls={controls}
      aria-expanded={expanded}
      className={cn(
        "box-border block w-full min-w-0 max-w-full rounded-xl border p-3 text-left transition-all",
        disabled
          ? "cursor-not-allowed border-slate-700/50 bg-slate-950/20 text-slate-600"
          : "border-cyan-300/10 bg-slate-950/32 hover:border-cyan-300/35 hover:bg-cyan-300/8",
        expanded && "border-cyan-300/38 bg-cyan-300/10 shadow-hud-cyan",
        className
      )}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-lg border",
            disabled
              ? "border-slate-700/50 bg-white/5 text-slate-600"
              : "border-cyan-300/14 bg-cyan-300/8 text-cyan-100"
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">
            {title}
          </div>
          <div className="mt-1 truncate text-[11px] text-slate-500">
            {description}
          </div>
        </div>
        {typeof expanded === "boolean" && (
          <ChevronRight
            className={cn(
              "ml-auto mt-1 size-4 shrink-0 text-slate-500 transition-transform",
              expanded && "rotate-90 text-cyan-200"
            )}
          />
        )}
      </div>
    </button>
  );
}

type PlacementMenuType = "aircraft" | "ship" | "facility" | "airbase";

interface PlacementOption {
  key: string;
  className: string;
  name: string;
  raw: string;
  badges: string[];
}

const placementTypeMeta: Record<
  PlacementMenuType,
  { icon: LucideIcon; title: string; eyebrow: string }
> = {
  aircraft: { icon: Plane, title: "选择飞机型号", eyebrow: "Aircraft" },
  ship: { icon: Ship, title: "选择舰船型号", eyebrow: "Ship" },
  facility: { icon: Shield, title: "选择防空设施", eyebrow: "Facility" },
  airbase: { icon: Radar, title: "选择机场", eyebrow: "Airbase" },
};

function buildPlacementOptions(type: PlacementMenuType): PlacementOption[] {
  if (type === "aircraft") {
    return AircraftDb.map((a) => ({
      key: a.className,
      className: a.className,
      name: localizeClassName(a.className),
      raw: a.className,
      badges: [
        `${a.speed} kt`,
        `${a.range} nm`,
        `${a.maxFuel.toLocaleString()} lbs`,
      ],
    }));
  }
  if (type === "ship") {
    return ShipDb.map((s) => ({
      key: s.className,
      className: s.className,
      name: localizeClassName(s.className),
      raw: s.className,
      badges: [`${s.speed} kt`, `${s.range} nm`],
    }));
  }
  if (type === "facility") {
    return FacilityDb.map((f) => ({
      key: f.className,
      className: f.className,
      name: localizeClassName(f.className),
      raw: f.className,
      badges: [`射程 ${f.range} nm`],
    }));
  }
  return AirbaseDb.map((a) => ({
    key: a.name,
    className: a.name,
    name: localizeAirbaseName(a.name),
    raw: a.name,
    badges: [a.country],
  }));
}

function PlacementOptionItem({
  badges,
  icon: Icon,
  name,
  onSelect,
  raw,
}: {
  badges: string[];
  icon: LucideIcon;
  name: string;
  onSelect: () => void;
  raw: string;
}) {
  return (
    <button
      className="w-full min-w-0 rounded-xl border border-cyan-300/10 bg-slate-950/32 p-3 text-left transition-all hover:border-cyan-300/35 hover:bg-cyan-300/8"
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-start gap-2.5">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-cyan-300/14 bg-cyan-300/8 text-cyan-100">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-100">
            {name}
          </div>
          {raw && raw !== name && (
            <div className="mt-1 truncate text-[11px] text-slate-500">
              {raw}
            </div>
          )}
          {badges.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {badges.map((badge, idx) => (
                <span
                  key={`${badge}-${idx}`}
                  className={cn(
                    "rounded-full border px-2 py-0.5 font-mono text-[10px]",
                    idx === 0
                      ? "border-cyan-300/14 bg-cyan-300/8 text-cyan-200"
                      : "border-cyan-300/10 bg-white/[0.03] text-slate-400"
                  )}
                >
                  {badge}
                </span>
              ))}
            </div>
          )}
        </div>
        <ChevronRight className="mt-2 size-4 shrink-0 text-slate-500" />
      </div>
    </button>
  );
}

function PlacementFloatingMenu({
  anchorRect,
  innerRef,
  onClose,
  onSelect,
  type,
}: {
  anchorRect: DOMRect;
  innerRef: React.RefObject<HTMLDivElement>;
  onClose: () => void;
  onSelect: (className: string) => void;
  type: PlacementMenuType;
}) {
  const meta = placementTypeMeta[type];
  const options = buildPlacementOptions(type);
  const Icon = meta.icon;
  const margin = 12;
  const width = 320;
  const viewportWidth =
    typeof window === "undefined" ? 1280 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined" ? 800 : window.innerHeight;
  const left = Math.min(
    Math.max(anchorRect.right + margin, margin),
    Math.max(viewportWidth - width - margin, margin)
  );
  const maxHeight = Math.max(viewportHeight - 2 * margin, 240);
  const headerHeight = 92;
  const itemHeight = 84;
  const listPadding = 24;
  const estimatedContentHeight =
    options.length === 0
      ? 120
      : options.length * itemHeight + listPadding;
  const estimatedHeight = Math.min(
    maxHeight,
    headerHeight + estimatedContentHeight
  );
  const top = Math.max(
    margin,
    Math.min(anchorRect.top, viewportHeight - estimatedHeight - margin)
  );

  return (
    <motion.div
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="pointer-events-auto fixed z-[60] flex flex-col overflow-hidden rounded-2xl border border-cyan-300/18 bg-[#07111d]/95 shadow-[0_24px_72px_rgba(0,0,0,0.55)] backdrop-blur-2xl"
      exit={{ opacity: 0, y: 14, scale: 0.97 }}
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      ref={innerRef}
      role="dialog"
      style={{ top, left, width, maxHeight }}
      transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="flex items-start justify-between gap-3 border-b border-cyan-300/10 px-4 py-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-cyan-300/14 bg-cyan-300/8 text-cyan-100">
            <Icon className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-300/70">
              AICC {meta.eyebrow}
            </div>
            <div className="mt-0.5 truncate text-sm font-semibold text-slate-100">
              {meta.title}
            </div>
            <div className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">
              选择型号后在地图左键落点部署，按 Esc 取消
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="rounded-full border border-cyan-300/14 bg-cyan-300/8 px-2 py-0.5 font-mono text-[10px] text-cyan-200">
            {options.length}
          </span>
          <button
            aria-label="关闭"
            className="grid size-7 place-items-center rounded-lg border border-cyan-300/12 bg-white/5 text-slate-400 transition-all hover:border-cyan-300/35 hover:text-cyan-100"
            onClick={onClose}
            type="button"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {options.length === 0 ? (
          <div className="rounded-xl border border-dashed border-cyan-300/12 bg-slate-950/30 px-3 py-6 text-center text-xs text-slate-500">
            该类型暂无可选项
          </div>
        ) : (
          options.map((option) => (
            <PlacementOptionItem
              badges={option.badges}
              icon={Icon}
              key={option.key}
              name={option.name}
              onSelect={() => onSelect(option.className)}
              raw={option.raw}
            />
          ))
        )}
      </div>
    </motion.div>
  );
}

function SideControlCard({
  active,
  side,
  unitCount,
  hostileCount,
  allyCount,
  onSelect,
  onEdit,
}: {
  active: boolean;
  side: Side;
  unitCount: number;
  hostileCount: number;
  allyCount: number;
  onSelect: () => void;
  onEdit: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-3 transition-all",
        active
          ? "border-cyan-300/38 bg-cyan-300/10 shadow-hud-cyan"
          : "border-cyan-300/10 bg-slate-950/32 hover:border-cyan-300/28 hover:bg-white/[0.04]"
      )}
    >
      <div className="flex items-start gap-2">
        <button
          className="min-w-0 flex-1 text-left"
          onClick={onSelect}
          type="button"
        >
          <div className="flex min-w-0 items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-full ring-2 ring-white/10"
              style={{ backgroundColor: side.color }}
            />
            <span className="truncate text-sm font-semibold text-slate-100">
              {normalizeSideName(side.name)}
            </span>
            {active && (
              <span className="shrink-0 rounded-full border border-cyan-300/18 bg-cyan-300/8 px-1.5 py-0.5 text-[10px] text-cyan-200">
                当前
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded-full border border-slate-500/18 bg-white/5 px-2 py-0.5 text-[10px] text-slate-400">
              单位 {unitCount}
            </span>
            <span className="rounded-full border border-red-300/18 bg-red-500/8 px-2 py-0.5 text-[10px] text-red-200">
              敌对 {hostileCount}
            </span>
            <span className="rounded-full border border-emerald-300/18 bg-emerald-300/8 px-2 py-0.5 text-[10px] text-emerald-200">
              友方 {allyCount}
            </span>
          </div>
        </button>
        <button
          aria-label={`编辑阵营 ${side.name}`}
          className="grid size-8 shrink-0 place-items-center rounded-lg border border-cyan-300/14 bg-cyan-300/8 text-cyan-100 transition-all hover:border-cyan-300/45"
          onClick={onEdit}
          title="编辑阵营与关系"
          type="button"
        >
          <Edit3 className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

function CapabilityCard({
  icon: Icon,
  title,
  description,
  status,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  status: string;
}) {
  return (
    <div className="rounded-lg border border-cyan-300/10 bg-slate-950/35 p-3">
      <div className="flex items-start gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-cyan-300/14 bg-cyan-300/8 text-cyan-100">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-100">
              {title}
            </span>
            <span className="rounded-full border border-cyan-300/14 bg-cyan-300/8 px-2 py-0.5 text-[10px] text-cyan-200">
              {status}
            </span>
          </div>
          <div className="mt-1 text-xs leading-relaxed text-slate-500">
            {description}
          </div>
        </div>
      </div>
    </div>
  );
}

function LayerToggleCard({
  icon: Icon,
  title,
  description,
  enabled,
  onToggle,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-all hover:border-cyan-300/40 hover:bg-cyan-300/8",
        enabled
          ? "border-cyan-300/38 bg-cyan-300/10 shadow-hud-cyan"
          : "border-cyan-300/10 bg-slate-950/35"
      )}
      onClick={onToggle}
      type="button"
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-xl border",
            enabled
              ? "border-cyan-300/35 bg-cyan-300/12 text-cyan-100"
              : "border-slate-500/18 bg-white/5 text-slate-500"
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-100">
              {title}
            </span>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px]",
                enabled
                  ? "border-emerald-300/24 bg-emerald-300/10 text-emerald-200"
                  : "border-slate-500/20 bg-white/5 text-slate-400"
              )}
            >
              {enabled ? "手动开启" : "手动关闭"}
            </span>
          </div>
          <div className="mt-1 text-xs leading-relaxed text-slate-500">
            {description}
          </div>
        </div>
      </div>
    </button>
  );
}

function ScenarioActionButton({
  icon: Icon,
  label,
  description,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      className="flex flex-col items-center gap-1.5 rounded-xl border border-cyan-300/14 bg-slate-950/45 px-2 py-3 text-center transition-all hover:border-cyan-300/45 hover:bg-cyan-300/8 hover:shadow-hud-cyan"
      onClick={onClick}
      type="button"
    >
      <div className="grid size-9 place-items-center rounded-lg border border-cyan-300/18 bg-cyan-300/8 text-cyan-100">
        <Icon className="size-4" />
      </div>
      <div className="text-sm font-semibold text-slate-100">{label}</div>
      <div className="text-[10px] leading-tight text-slate-500">
        {description}
      </div>
    </button>
  );
}

const OUTCOME_REASON_LABEL: Record<GameOutcome["reason"], string> = {
  "": "推演进行中",
  KEY_UNIT_DESTROYED: "关键单位被毁",
  ANNIHILATION: "全歼对手",
  TIMEOUT: "时长耗尽",
};

function formatScoreCompact(value: number) {
  if (!Number.isFinite(value)) return "0";
  return Math.round(value).toLocaleString("zh-CN");
}

function renderBattleStatusSection(snapshot: SimulationSnapshot): ReactNode {
  const { outcome, sideStats, elapsedSeconds, duration } = snapshot;
  const sortedSides = [...sideStats].sort((a, b) => b.score - a.score);
  const maxScore = sortedSides.reduce(
    (acc, side) => Math.max(acc, side.score),
    0
  );
  const winner = outcome.ended
    ? sideStats.find((side) => side.id === outcome.winnerSideId)
    : undefined;
  const durationProgress =
    duration > 0
      ? Math.min(100, Math.max(0, (elapsedSeconds / duration) * 100))
      : 0;

  return (
    <div className="space-y-2.5">
      {outcome.ended && (
        <div
          className={cn(
            "rounded-xl border p-3",
            "border-cyan-300/35 bg-gradient-to-br from-cyan-400/14 via-cyan-300/6 to-transparent shadow-hud-cyan"
          )}
        >
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-cyan-200/80">
            <Trophy className="size-3" />
            推演结束
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <div className="truncate text-sm font-semibold text-cyan-50">
              {winner
                ? `${
                    sideNameMap[winner.name.toUpperCase()] ??
                    localizeSideName(winner.name)
                  } 获胜`
                : "胜负未定"}
            </div>
            <div className="text-[10px] text-cyan-300/70">
              {OUTCOME_REASON_LABEL[outcome.reason]}
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-cyan-300/12 bg-white/[0.03] p-3">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.24em] text-slate-500">
          <span>推演用时</span>
          <span>
            {formatElapsed(elapsedSeconds)}
            {duration > 0 ? ` / ${formatElapsed(duration)}` : ""}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800/55">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-cyan-300 to-emerald-300 transition-[width] duration-300 ease-out"
            style={{ width: `${durationProgress}%` }}
          />
        </div>
      </div>

      {sortedSides.length === 0 ? (
        <div className="rounded-xl border border-cyan-300/10 bg-slate-950/35 p-3 text-xs text-slate-500">
          当前场景无阵营。
        </div>
      ) : (
        <div className="space-y-2">
          {sortedSides.map((side, index) => {
            const ratio =
              maxScore > 0 ? Math.min(100, (side.score / maxScore) * 100) : 0;
            const remaining =
              side.aircraft + side.ships + side.facilities + side.airbases;
            const isLeader = index === 0 && side.score > 0;
            return (
              <div
                className={cn(
                  "rounded-xl border p-2.5 transition-colors",
                  isLeader
                    ? "border-cyan-300/35 bg-cyan-300/6"
                    : "border-cyan-300/10 bg-slate-950/35"
                )}
                key={side.id}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="size-2.5 shrink-0 rounded-full ring-2 ring-slate-950"
                      style={{ background: side.colorHex }}
                    />
                    <span className="truncate text-[12px] font-semibold text-slate-200">
                      {sideNameMap[side.name.toUpperCase()] ??
                        localizeSideName(side.name)}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1 text-right">
                    <span
                      className={cn(
                        "text-sm font-bold leading-none",
                        isLeader ? "text-cyan-100" : "text-slate-200"
                      )}
                    >
                      {formatScoreCompact(side.score)}
                    </span>
                    <span className="text-[10px] text-slate-500">分</span>
                  </div>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-800/55">
                  <div
                    className={cn(
                      "h-full rounded-full transition-[width] duration-300 ease-out",
                      isLeader
                        ? "bg-gradient-to-r from-cyan-300 to-emerald-300"
                        : "bg-slate-600"
                    )}
                    style={{ width: `${ratio}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                  <span>剩余 {remaining} 单位</span>
                  <span>
                    ✈ {side.aircraft} · 🚢 {side.ships} · 🛰 {side.facilities} · 🏭{" "}
                    {side.airbases}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatElapsed(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}:${String(secs).padStart(2, "0")}`;
}

function runStateLabel(runState: SimulationRunState) {
  if (runState === "running") return "运行中";
  if (runState === "paused") return "已暂停";
  return "待命";
}

export default function SimulationSidebar({
  activePanel,
  game,
  snapshot,
  onPlay,
  onPause,
  onStep,
  onReset,
  onSetSpeed,
  onToggleGodMode,
  onToggleEraser,
  showRoutes,
  showRanges,
  onToggleRoutes,
  onToggleRanges,
  onOpenMissionCreator,
  onOpenMissionEditor,
  onDeleteMission,
  onBeginPlacement,
  onScenarioMutation,
  onNewScenario,
  onLoadDemoScenario,
  onLoadSCSScenario,
  onImportScenario,
  onExportScenario,
}: SimulationSidebarProps) {
  const scenario = game.currentScenario;
  const meta = panelMeta[activePanel];
  const [sideEditorState, setSideEditorState] = useState<{
    anchorEl: HTMLElement | null;
    sideId: string | null;
  }>({
    anchorEl: null,
    sideId: null,
  });
  const [placementMenu, setPlacementMenu] = useState<{
    type: PlacementMenuType;
    anchorRect: DOMRect;
  } | null>(null);
  const placementMenuRef = useRef<HTMLDivElement | null>(null);
  const progress =
    snapshot.duration > 0
      ? Math.min(100, (snapshot.elapsedSeconds / snapshot.duration) * 100)
      : 0;
  const currentSide = scenario.getSide(snapshot.currentSideId);
  const currentSideName = currentSide
    ? normalizeSideName(currentSide.name)
    : "未选择";
  const hostileSides = snapshot.currentSideId
    ? scenario.sides.filter((side) =>
        scenario.isHostile(snapshot.currentSideId, side.id)
      )
    : [];
  const hostileSideNames = hostileSides
    .map((side) => normalizeSideName(side.name))
    .join(" / ");
  const sideDoctrine =
    scenario.doctrine[snapshot.currentSideId] ??
    scenario.getDefaultSideDoctrine();
  const visibleObjectCount =
    snapshot.aircraft +
    snapshot.ships +
    snapshot.facilities +
    snapshot.airbases +
    snapshot.weapons;
  const totalObjectCount =
    scenario.aircraft.length +
    scenario.ships.length +
    scenario.facilities.length +
    scenario.airbases.length +
    scenario.weapons.length;
  const currentSideMissions = scenario.missions.filter(
    (mission) => mission.sideId === snapshot.currentSideId
  ).length;
  const allMissions = scenario.missions;
  const selectedSideForEditor = sideEditorState.sideId
    ? scenario.getSide(sideEditorState.sideId)
    : undefined;
  const editorSideId = selectedSideForEditor?.id ?? "";
  const hasCurrentSide = Boolean(snapshot.currentSideId);
  const defaultAircraftClass = AircraftDb[0]?.className ?? "F-35A Lightning II";
  const defaultShipClass = ShipDb[0]?.className ?? "Aircraft Carrier";
  const defaultFacilityClass = FacilityDb[0]?.className ?? "S-400 Triumf";
  const defaultAirbaseName = AirbaseDb[0]?.name ?? "Airbase";

  const openSideEditor = (
    event: MouseEvent<HTMLButtonElement>,
    sideId: string | null
  ) => {
    setSideEditorState({
      anchorEl: event.currentTarget,
      sideId,
    });
  };

  const closeSideEditor = () => {
    setSideEditorState({
      anchorEl: null,
      sideId: null,
    });
  };

  const refreshScenarioAfterSideMutation = () => {
    closeSideEditor();
    onScenarioMutation();
  };

  const closePlacementMenu = () => setPlacementMenu(null);

  const openPlacementMenu = (
    type: PlacementMenuType,
    event: MouseEvent<HTMLButtonElement>
  ) => {
    if (!hasCurrentSide) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setPlacementMenu((prev) =>
      prev?.type === type ? null : { type, anchorRect: rect }
    );
  };

  const beginPlacement = (placement: CesiumPlacement) => {
    closePlacementMenu();
    onBeginPlacement(placement);
  };

  useEffect(() => {
    if (!placementMenu) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePlacementMenu();
    };
    const handleMouseDown = (event: globalThis.MouseEvent) => {
      const target = event.target as Node | null;
      if (target && placementMenuRef.current?.contains(target)) return;
      const element = event.target as HTMLElement | null;
      if (element?.closest("[data-placement-area]")) return;
      closePlacementMenu();
    };
    const handleResize = () => closePlacementMenu();
    const handleScroll = (event: Event) => {
      const target = event.target as Node | null;
      if (target && placementMenuRef.current?.contains(target)) return;
      closePlacementMenu();
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", handleResize);
    document.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [placementMenu]);

  function renderCommandPanel() {
    return (
      <>
        <Section title="当前指挥视角" icon={Waves}>
          <div className="grid grid-cols-2 gap-2">
            <InfoRow label="当前阵营" value={currentSideName} />
            <InfoRow
              label="敌对阵营"
              tone={hostileSides.length > 0 ? "red" : "green"}
              value={hostileSideNames || "无"}
            />
            <InfoRow label="本方任务" value={currentSideMissions} />
            <InfoRow
              label="视角模式"
              tone={snapshot.godMode ? "amber" : "cyan"}
              value={snapshot.godMode ? "全域视角" : "阵营视角"}
            />
          </div>
        </Section>

        <Section title="阵营与敌对关系" icon={Satellite}>
          <div className="space-y-2.5">
            <button
              className="box-border block w-full min-w-0 max-w-full rounded-lg border border-dashed border-cyan-300/35 bg-cyan-300/[0.04] px-3 py-2.5 text-center transition-all hover:border-cyan-300/60 hover:bg-cyan-300/10 hover:shadow-hud-cyan"
              onClick={(event) => openSideEditor(event, null)}
              type="button"
            >
              <div className="flex items-center justify-center gap-2">
                <Plus className="size-4 text-cyan-200" />
                <span className="text-sm font-semibold text-cyan-100">
                  新增阵营
                </span>
              </div>
              <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                创建阵营，并配置敌对、友方和交战规则
              </div>
            </button>

            <div className="space-y-2">
              {scenario.sides.length === 0 ? (
                <div className="rounded-lg border border-dashed border-cyan-300/12 bg-slate-950/30 px-3 py-4 text-center text-xs text-slate-500">
                  暂无阵营。请先新增一个阵营，再部署单位。
                </div>
              ) : (
                scenario.sides.map((side) => (
                  <SideControlCard
                    active={side.id === snapshot.currentSideId}
                    allyCount={scenario.relationships.getAllies(side.id).length}
                    hostileCount={
                      scenario.relationships.getHostiles(side.id).length
                    }
                    key={side.id}
                    onEdit={(event) => openSideEditor(event, side.id)}
                    onSelect={() => {
                      game.switchCurrentSide(side.id);
                      onScenarioMutation();
                    }}
                    side={side}
                    unitCount={countUnitsForSide(scenario, side.id)}
                  />
                ))
              )}
            </div>
          </div>
        </Section>

        <Section title="单位部署" icon={Route}>
          <div className="space-y-3" data-placement-area>
            <div className="rounded-xl border border-cyan-300/10 bg-white/[0.03] p-3 text-xs leading-relaxed text-slate-400">
              当前部署阵营：
              <span className="font-semibold text-cyan-100">
                {currentSideName}
              </span>
              。选择类型后，在地图上左键落点部署；按 Esc 取消部署。
            </div>
            <div className="space-y-2.5">
              <PlacementActionCard
                description={
                  placementMenu?.type === "aircraft"
                    ? "选择具体机型"
                    : `默认 ${localizeClassName(defaultAircraftClass)}`
                }
                disabled={!hasCurrentSide}
                expanded={placementMenu?.type === "aircraft"}
                icon={Plane}
                onClick={(event) => openPlacementMenu("aircraft", event)}
                title="部署飞机"
              />
              <PlacementActionCard
                description={
                  placementMenu?.type === "ship"
                    ? "选择具体舰船型号"
                    : `默认 ${localizeClassName(defaultShipClass)}`
                }
                disabled={!hasCurrentSide}
                expanded={placementMenu?.type === "ship"}
                icon={Ship}
                onClick={(event) => openPlacementMenu("ship", event)}
                title="部署舰船"
              />
              <PlacementActionCard
                description={
                  placementMenu?.type === "facility"
                    ? "选择防空设施型号"
                    : `默认 ${localizeClassName(defaultFacilityClass)}`
                }
                disabled={!hasCurrentSide}
                expanded={placementMenu?.type === "facility"}
                icon={Shield}
                onClick={(event) => openPlacementMenu("facility", event)}
                title="部署防空设施"
              />
              <PlacementActionCard
                description={
                  placementMenu?.type === "airbase"
                    ? "选择机场位置"
                    : `默认 ${localizeAirbaseName(defaultAirbaseName)}`
                }
                disabled={!hasCurrentSide}
                expanded={placementMenu?.type === "airbase"}
                icon={Radar}
                onClick={(event) => openPlacementMenu("airbase", event)}
                title="部署机场"
              />
              <PlacementActionCard
                description="创建任务区域或航线参考点"
                disabled={!hasCurrentSide}
                icon={MapPin}
                onClick={() => beginPlacement({ type: "referencePoint" })}
                title="部署参考点"
              />
            </div>
          </div>
        </Section>

        <Section title="自动交战规则" icon={ListChecks}>
          <div className="space-y-2">
            <DoctrineRow
              description="允许飞机对敌方飞机、设施、舰船和机场执行机会攻击。"
              enabled={sideDoctrine[DoctrineType.AIRCRAFT_ATTACK_HOSTILE]}
              label="飞机主动攻击"
            />
            <DoctrineRow
              description="敌机进入探测范围后，飞机会自动追击目标。"
              enabled={sideDoctrine[DoctrineType.AIRCRAFT_CHASE_HOSTILE]}
              label="飞机追击目标"
            />
            <DoctrineRow
              description="防空设施会对进入射程的敌方飞机或来袭武器开火。"
              enabled={sideDoctrine[DoctrineType.SAM_ATTACK_HOSTILE]}
              label="防空自动拦截"
            />
            <DoctrineRow
              description="舰船会使用舰载武器拦截敌机和来袭武器。"
              enabled={sideDoctrine[DoctrineType.SHIP_ATTACK_HOSTILE]}
              label="舰船自动防御"
            />
          </div>
        </Section>

        <Section title="指挥入口" icon={MapPin}>
          <div className="space-y-2.5">
            <button
              className="box-border block w-full min-w-0 max-w-full rounded-lg border border-cyan-300/10 bg-slate-950/35 p-3 text-left transition-all hover:border-cyan-300/35 hover:bg-cyan-300/8"
              onClick={onOpenMissionCreator}
              type="button"
            >
              <div className="flex items-center gap-2">
                <Crosshair className="size-4 text-cyan-200" />
                <span className="text-sm font-medium text-slate-100">
                  创建任务
                </span>
              </div>
              <div className="mt-1 text-xs leading-relaxed text-slate-500">
                创建巡逻或打击任务，绑定执行飞机与目标/区域
              </div>
            </button>
            <div className="flex items-center justify-between gap-3 pt-1">
              <div className="flex items-center gap-2">
                <ListChecks className="size-4 text-cyan-200" />
                <span className="text-sm font-semibold text-slate-100">
                  所有任务
                </span>
              </div>
              <span className="rounded-full border border-cyan-300/14 bg-cyan-300/8 px-2 py-0.5 font-mono text-[10px] text-cyan-200">
                {allMissions.length}
              </span>
            </div>
            <div className="space-y-2">
              {allMissions.length === 0 ? (
                <div className="rounded-xl border border-dashed border-cyan-300/12 bg-slate-950/30 px-3 py-4 text-center text-xs text-slate-500">
                  暂无任务，先创建一个巡逻或打击任务。
                </div>
              ) : (
                allMissions.map((mission) => (
                  <MissionSummaryCard
                    key={mission.id}
                    mission={mission}
                    scenario={scenario}
                    onDelete={() => onDeleteMission(mission.id)}
                    onEdit={() => onOpenMissionEditor(mission.id)}
                  />
                ))
              )}
            </div>
          </div>
        </Section>
      </>
    );
  }

  function renderSimulationPanel() {
    return (
      <>
        <Section title="场景管理" icon={FileText}>
          <div className="space-y-2.5">
            <div className="rounded-xl border border-cyan-300/10 bg-white/[0.03] p-3 text-xs leading-relaxed text-slate-400">
              当前场景：
              <span className="font-semibold text-cyan-100">
                {scenario.name || "未命名"}
              </span>
              。新建或导入会替换当前推演状态，建议先导出留档。
            </div>
            <div className="grid grid-cols-3 gap-2">
              <ScenarioActionButton
                icon={FilePlus}
                label="新建"
                description="清空场景"
                onClick={onNewScenario}
              />
              <ScenarioActionButton
                icon={Upload}
                label="导入"
                description="选择 JSON"
                onClick={onImportScenario}
              />
              <ScenarioActionButton
                icon={Download}
                label="导出"
                description="保存到本地"
                onClick={onExportScenario}
              />
            </div>
            <div className="rounded-xl border border-cyan-300/10 bg-slate-950/35 p-3">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-cyan-300/70">
                <Sparkles className="size-3" />
                预设场景
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  className="rounded-lg border border-cyan-300/14 bg-slate-950/45 px-3 py-2 text-left transition-all hover:border-cyan-300/40 hover:bg-cyan-300/8"
                  onClick={onLoadDemoScenario}
                  type="button"
                >
                  <div className="text-sm font-semibold text-slate-100">
                    Demo 场景
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    入门演示，少量单位
                  </div>
                </button>
                <button
                  className="rounded-lg border border-cyan-300/14 bg-slate-950/45 px-3 py-2 text-left transition-all hover:border-cyan-300/40 hover:bg-cyan-300/8"
                  onClick={onLoadSCSScenario}
                  type="button"
                >
                  <div className="text-sm font-semibold text-slate-100">
                    南海打击
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    SCS 默认推演
                  </div>
                </button>
              </div>
            </div>
          </div>
        </Section>

        <Section title="战况" icon={Trophy}>
          {renderBattleStatusSection(snapshot)}
        </Section>

        <Section title="推演控制" icon={Activity}>
          <div className="grid grid-cols-4 gap-2">
            <Button
              className={cn(
                "h-16 flex-col",
                snapshot.runState === "running" && "shadow-hud-cyan"
              )}
              onClick={onPlay}
              variant="tactical"
            >
              <Play className="size-5" />
              <span className="text-[11px]">开始</span>
            </Button>
            <Button
              className={cn(
                "h-16 flex-col",
                snapshot.runState === "paused" && "shadow-hud-cyan"
              )}
              onClick={onPause}
              variant="tactical"
            >
              <Pause className="size-5" />
              <span className="text-[11px]">暂停</span>
            </Button>
            <Button
              className="h-16 flex-col"
              onClick={onStep}
              variant="tactical"
            >
              <SkipForward className="size-5" />
              <span className="text-[11px]">单步</span>
            </Button>
            <Button
              className="h-16 flex-col"
              onClick={onReset}
              variant="tactical"
            >
              <RefreshCcw className="size-5" />
              <span className="text-[11px]">重置</span>
            </Button>
          </div>

          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs text-slate-400">时间倍率</span>
              <span className="rounded border border-cyan-300/18 bg-cyan-300/8 px-2 py-0.5 font-mono text-xs text-cyan-200">
                {snapshot.timeCompression}x
              </span>
            </div>
            <div className="grid grid-cols-7 gap-1.5">
              {speeds.map((speed) => (
                <button
                  className={cn(
                    "rounded-md border px-2 py-1.5 text-xs transition-all",
                    snapshot.timeCompression === speed
                      ? "border-cyan-300/55 bg-cyan-300/16 text-cyan-100 shadow-hud-cyan"
                      : "border-cyan-300/10 bg-slate-950/35 text-slate-500 hover:text-slate-200"
                  )}
                  key={speed}
                  onClick={() => onSetSpeed(speed)}
                  type="button"
                >
                  {speed}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="text-slate-400">推演进度</span>
              <span className="font-mono text-cyan-200">
                {formatElapsed(snapshot.elapsedSeconds)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-900">
              <div
                className="h-full rounded-full bg-cyan-300 shadow-hud-cyan transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </Section>

        <Section title="仿真状态" icon={Clock3}>
          <div className="space-y-2">
            <InfoRow label="当前时间" value={`${snapshot.currentTime}s`} />
            <InfoRow
              label="推演状态"
              value={runStateLabel(snapshot.runState)}
            />
            <InfoRow label="场景任务" value={snapshot.missions} />
            <InfoRow label="飞行武器" value={snapshot.weapons} />
          </div>
        </Section>
      </>
    );
  }

  function renderLayersPanel() {
    return (
      <>
        <Section title="视角与可见性" icon={Crosshair}>
          <div className="grid grid-cols-2 gap-2">
            <Button
              className={cn(
                "justify-start",
                snapshot.godMode && "border-cyan-300/60 bg-cyan-300/14"
              )}
              onClick={onToggleGodMode}
              variant="tactical"
            >
              <Satellite className="size-4" />
              {snapshot.godMode ? "全域视角" : "阵营视角"}
            </Button>
            <Button
              className={cn(
                "justify-start",
                snapshot.eraserMode && "border-red-300/60 bg-red-500/14"
              )}
              onClick={onToggleEraser}
              variant={snapshot.eraserMode ? "danger" : "tactical"}
            >
              <Target className="size-4" />
              删除模式
            </Button>
          </div>

          <div className="mt-3 rounded-lg border border-cyan-300/10 bg-white/[0.03] p-3 text-xs leading-relaxed text-slate-400">
            {snapshot.godMode
              ? "全域视角会显示全部阵营单位、武器和完整战场细节。"
              : "阵营视角只显示己方/友方单位，敌方单位需进入探测范围后才会出现。"}
          </div>
        </Section>

        <Section title="地图叠加层" icon={Radar}>
          <div className="space-y-2">
            <CapabilityCard
              description="Cesium 地图会按当前视角同步显示可见单位和武器。"
              icon={Waves}
              status="自动"
              title="态势图层"
            />
            <LayerToggleCard
              description="点击后显示或隐藏单位航线；航线数据由航路系统维护。"
              icon={Route}
              enabled={showRoutes}
              onToggle={onToggleRoutes}
              title="航线"
            />
            <LayerToggleCard
              description="点击后显示或隐藏防空设施、舰船和飞机的探测/交战圈。"
              icon={Radar}
              enabled={showRanges}
              onToggle={onToggleRanges}
              title="探测与交战范围"
            />
          </div>
        </Section>

        <Section title="可见对象口径" icon={Target}>
          <div className="grid grid-cols-2 gap-2">
            <CountTile
              icon={Target}
              label="当前可见"
              value={visibleObjectCount}
            />
            <CountTile
              icon={Shield}
              label="全域对象"
              value={totalObjectCount}
            />
          </div>
        </Section>
      </>
    );
  }

  function renderAssetsPanel() {
    return (
      <>
        <Section title="可见对象" icon={Activity}>
          <div className="grid grid-cols-3 gap-2">
            <CountTile icon={Plane} label="飞机" value={snapshot.aircraft} />
            <CountTile icon={Ship} label="舰船" value={snapshot.ships} />
            <CountTile
              icon={Shield}
              label="设施"
              tone="red"
              value={snapshot.facilities}
            />
            <CountTile icon={Radar} label="机场" value={snapshot.airbases} />
            <CountTile
              icon={Target}
              label="武器"
              tone="red"
              value={snapshot.weapons}
            />
            <CountTile
              icon={Crosshair}
              label="任务"
              tone="green"
              value={snapshot.missions}
            />
          </div>
        </Section>

        <Section title="全域编成" icon={ListChecks}>
          <div className="space-y-2">
            <InfoRow label="飞机总数" value={scenario.aircraft.length} />
            <InfoRow label="舰船总数" value={scenario.ships.length} />
            <InfoRow label="防空/设施" value={scenario.facilities.length} />
            <InfoRow label="机场总数" value={scenario.airbases.length} />
            <InfoRow label="参考点" value={scenario.referencePoints.length} />
          </div>
        </Section>

        <Section title="单位操作" icon={Edit3}>
          <div className="space-y-2">
            <CapabilityCard
              description="点击地图单位可打开详情，查看挂载、航线、状态和阵营。"
              icon={Activity}
              status="可用"
              title="单位详情"
            />
            <CapabilityCard
              description="在单位详情里执行手动攻击、自动攻击、返航和航线规划。"
              icon={Crosshair}
              status="可用"
              title="战术动作"
            />
          </div>
        </Section>
      </>
    );
  }

  return (
    <motion.aside
      animate={{ opacity: 1, x: 0 }}
      className="hidden min-h-0 w-full min-w-0 shrink-0 overflow-hidden border-r border-cyan-300/10 bg-[#050b13]/88 p-4 backdrop-blur-2xl lg:flex lg:flex-col"
      initial={{ opacity: 0, x: -18 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-4 px-1">
        <div className="text-xs uppercase tracking-[0.26em] text-cyan-300/70">
          AICC {meta.eyebrow}
        </div>
        <div className="mt-1.5 text-xl font-semibold text-slate-100">
          {meta.title}
        </div>
        <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
          {meta.description}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div
          className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-0"
          style={{ scrollbarGutter: "stable" }}
        >
          {activePanel === "command" && renderCommandPanel()}
          {activePanel === "simulation" && renderSimulationPanel()}
          {activePanel === "layers" && renderLayersPanel()}
          {activePanel === "assets" && renderAssetsPanel()}
        </div>
      </div>

      <SideEditor
        addSide={(name, color, hostiles, allies, doctrine) => {
          game.addSide(name, color, hostiles, allies, doctrine);
          const createdSide = scenario.sides[scenario.sides.length - 1];
          if (createdSide) {
            game.switchCurrentSide(createdSide.id);
          }
          refreshScenarioAfterSideMutation();
        }}
        allies={
          editorSideId ? scenario.relationships.getAllies(editorSideId) : []
        }
        anchorEl={sideEditorState.anchorEl}
        deleteSide={(sideId) => {
          const side = scenario.getSide(sideId);
          const sideName = side ? normalizeSideName(side.name) : sideId;
          if (
            !window.confirm(
              `确认删除阵营「${sideName}」？该阵营的单位、任务、武器和参考点都会一起删除。`
            )
          ) {
            return;
          }
          game.deleteSide(sideId);
          refreshScenarioAfterSideMutation();
        }}
        doctrine={
          editorSideId
            ? scenario.getSideDoctrine(editorSideId)
            : scenario.getDefaultSideDoctrine()
        }
        handleCloseOnMap={closeSideEditor}
        hostiles={
          editorSideId ? scenario.relationships.getHostiles(editorSideId) : []
        }
        open={Boolean(sideEditorState.anchorEl)}
        side={selectedSideForEditor}
        sides={scenario.sides}
        updateSide={(sideId, name, color, hostiles, allies, doctrine) => {
          game.updateSide(sideId, name, color, hostiles, allies, doctrine);
          refreshScenarioAfterSideMutation();
        }}
      />
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {placementMenu && (
              <PlacementFloatingMenu
                anchorRect={placementMenu.anchorRect}
                innerRef={placementMenuRef}
                key={placementMenu.type}
                onClose={closePlacementMenu}
                onSelect={(className) =>
                  beginPlacement({
                    type: placementMenu.type,
                    className,
                  })
                }
                type={placementMenu.type}
              />
            )}
          </AnimatePresence>,
          document.body
        )}
    </motion.aside>
  );
}
