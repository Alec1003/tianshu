import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Award,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileText,
  GitCommitVertical,
  History,
  Loader2,
  MapPinned,
  Play,
  Radio,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { listRuntimeTimeline } from "@/api/ai";
import {
  getScenarioTrainingScore,
  listScenarioTimeline,
} from "@/api/scenarios";
import type {
  RuntimeTimelineEvent,
  RuntimeTimelineResponse,
  RuntimeUnitChange,
  TrainingScoreResponse,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SimulationSnapshot } from "./SimulationSidebar";

type TimelineCategory = "all" | "command" | "runtime" | "scenario" | "aar";

interface TimelineReplayPanelProps {
  open: boolean;
  scenarioId?: string;
  runtimeScenarioId?: string;
  snapshot: SimulationSnapshot;
  onClose: () => void;
}

const categoryOptions: Array<{
  id: TimelineCategory;
  label: string;
}> = [
  { id: "all", label: "全部" },
  { id: "command", label: "命令" },
  { id: "runtime", label: "推演" },
  { id: "scenario", label: "场景" },
  { id: "aar", label: "AAR" },
];

const fieldLabels: Record<string, string> = {
  active: "启用状态",
  altitude: "高度",
  className: "型号",
  currentFuel: "当前油量",
  currentQuantity: "当前数量",
  fuelOffloadCapacity: "可卸油量",
  fuelRate: "耗油率",
  fuelTransferRate: "加油速率",
  heading: "航向",
  homeBaseId: "基地",
  isObjective: "任务目标",
  isTanker: "加油机",
  latitude: "纬度",
  lethality: "杀伤力",
  longitude: "经度",
  maxFuel: "最大油量",
  maxQuantity: "最大数量",
  name: "名称",
  range: "航程/射程",
  refuelRange: "加油范围",
  route: "航线",
  rtb: "返航",
  selected: "选中",
  sideId: "阵营",
  speed: "速度",
  targetId: "目标",
};

function categoryLabel(category: string) {
  if (category === "command") return "命令";
  if (category === "runtime") return "推演";
  if (category === "scenario") return "场景";
  if (category === "aar") return "AAR";
  return "事件";
}

function eventTitle(event: RuntimeTimelineEvent) {
  if (event.summary) return event.summary;
  if (event.event_type === "command.approved") return "审批通过";
  if (event.event_type === "command.rejected") return "审批驳回";
  if (event.event_type === "command.proposed") return "生成命令提案";
  if (event.event_type === "command.executed") return "命令执行";
  if (event.event_type === "runtime.step") return "推演推进";
  if (event.event_type === "runtime.reset") return "推演重置";
  if (event.event_type === "aar.created") return "生成 AAR 复盘";
  return event.action || event.event_type;
}

function eventIcon(event: RuntimeTimelineEvent) {
  if (event.event_type === "command.approved") return CheckCircle2;
  if (event.event_type === "command.rejected") return XCircle;
  if (event.category === "command") return Radio;
  if (event.category === "runtime") return Play;
  if (event.category === "scenario") return MapPinned;
  if (event.category === "aar") return FileText;
  return Activity;
}

function eventTone(event: RuntimeTimelineEvent) {
  if (event.event_type === "command.approved") return "emerald";
  if (event.event_type === "command.rejected") return "red";
  if (event.category === "command") return "cyan";
  if (event.category === "runtime") return "amber";
  if (event.category === "scenario") return "blue";
  if (event.category === "aar") return "violet";
  return "slate";
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

function formatRuntimeTime(value?: number | null) {
  if (value === null || value === undefined) return "未记录";
  if (value > 1_000_000_000) {
    return new Date(value * 1000).toLocaleString("zh-CN", {
      hour12: false,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }
  return `T+${formatElapsed(value)}`;
}

function formatWallTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "空";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "string") return value || "空";
  if (Array.isArray(value)) return `数组(${value.length})`;
  if (typeof value === "object") return "对象";
  return String(value);
}

function confidenceLabel(value: string) {
  if (value === "high") return "高";
  if (value === "medium") return "中";
  if (value === "low") return "低";
  return value || "未知";
}

function scoreTone(score: number) {
  if (score >= 85) return "emerald";
  if (score >= 70) return "cyan";
  if (score >= 60) return "amber";
  return "red";
}

function unitChangeLabel(change: RuntimeUnitChange) {
  if (change.change_type === "added") return "新增";
  if (change.change_type === "removed") return "移除";
  return "更新";
}

function unitChangeTone(change: RuntimeUnitChange) {
  if (change.change_type === "added") return "emerald";
  if (change.change_type === "removed") return "red";
  return "cyan";
}

function unitChangeSummary(change: RuntimeUnitChange) {
  if (change.change_type !== "updated") {
    return change.name || change.unit_id;
  }
  const fields = Object.keys(change.fields ?? {});
  if (fields.length === 0) return change.name || change.unit_id;
  return fields
    .slice(0, 4)
    .map((field) => fieldLabels[field] ?? field)
    .join("、");
}

function countUnitChanges(events: RuntimeTimelineEvent[]) {
  return events.reduce((sum, event) => sum + event.unit_changes.length, 0);
}

function StatTile({
  label,
  value,
  icon,
}: {
  label: string;
  value: ReactNode;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-cyan-300/10 bg-slate-950/35 p-3">
      <div className="mb-2 text-cyan-200">{icon}</div>
      <div className="font-mono text-lg font-bold leading-none text-slate-100">
        {value}
      </div>
      <div className="mt-1 text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

function ChangeBadge({ change }: { change: RuntimeUnitChange }) {
  const tone = unitChangeTone(change);
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[10px]",
        tone === "emerald" &&
          "border-emerald-300/24 bg-emerald-300/10 text-emerald-200",
        tone === "red" && "border-red-300/24 bg-red-500/10 text-red-200",
        tone === "cyan" && "border-cyan-300/18 bg-cyan-300/8 text-cyan-200"
      )}
    >
      <span>{unitChangeLabel(change)}</span>
      <span className="truncate">{change.name || change.unit_id}</span>
    </span>
  );
}

function ScorePanel({
  score,
  loading,
  error,
  hasScenario,
}: {
  score: TrainingScoreResponse | null;
  loading: boolean;
  error: string | null;
  hasScenario: boolean;
}) {
  if (!hasScenario) {
    return (
      <div className="rounded-2xl border border-dashed border-cyan-300/12 bg-slate-950/30 px-4 py-3 text-xs text-slate-500">
        当前运行态尚未绑定项目，保存或进入项目后可生成训练评分。
      </div>
    );
  }

  if (loading && !score) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-cyan-300/12 bg-slate-950/35 px-4 py-3 text-xs text-cyan-100">
        <Loader2 className="size-4 animate-spin" />
        正在计算训练评分
      </div>
    );
  }

  if (error && !score) {
    return (
      <div className="rounded-2xl border border-red-300/20 bg-red-500/10 px-4 py-3 text-xs text-red-200">
        {error}
      </div>
    );
  }

  if (!score) return null;

  const tone = scoreTone(score.overall_score);
  return (
    <div className="rounded-2xl border border-cyan-300/12 bg-slate-950/35 p-4">
      <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-cyan-300/70">
            <Award className="size-3.5" />
            Training Score
          </div>
          <div className="mt-3 flex items-end gap-2">
            <span
              className={cn(
                "font-mono text-5xl font-bold leading-none",
                tone === "emerald" && "text-emerald-200",
                tone === "cyan" && "text-cyan-100",
                tone === "amber" && "text-amber-200",
                tone === "red" && "text-red-200"
              )}
            >
              {score.overall_score}
            </span>
            <span className="pb-1 text-sm text-slate-500">/ 100</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-cyan-300/18 bg-cyan-300/8 px-2.5 py-1 text-xs text-cyan-100">
              {score.grade}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-400">
              置信度 {confidenceLabel(score.confidence)}
            </span>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {score.dimensions.map((dimension) => {
            const dimensionTone = scoreTone(dimension.score);
            return (
              <div
                className="rounded-xl border border-cyan-300/10 bg-white/[0.03] p-3"
                key={dimension.key}
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold text-slate-200">
                    {dimension.label}
                  </span>
                  <span className="font-mono text-xs text-cyan-100">
                    {dimension.score}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      dimensionTone === "emerald" && "bg-emerald-300",
                      dimensionTone === "cyan" && "bg-cyan-300",
                      dimensionTone === "amber" && "bg-amber-300",
                      dimensionTone === "red" && "bg-red-300"
                    )}
                    style={{ width: `${dimension.score}%` }}
                  />
                </div>
                <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-slate-500">
                  {dimension.summary}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-emerald-300/10 bg-emerald-300/[0.04] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-emerald-200">
            <CheckCircle2 className="size-4" />
            优势
          </div>
          <ul className="space-y-1.5 text-[11px] leading-relaxed text-slate-400">
            {score.strengths.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-amber-300/10 bg-amber-300/[0.04] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-amber-200">
            <BarChart3 className="size-4" />
            改进
          </div>
          <ul className="space-y-1.5 text-[11px] leading-relaxed text-slate-400">
            {score.improvements.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function TimelineItem({
  event,
  selected,
  onSelect,
}: {
  event: RuntimeTimelineEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = eventIcon(event);
  const tone = eventTone(event);

  return (
    <button
      className={cn(
        "group relative w-full rounded-2xl border p-3 text-left transition-all",
        selected
          ? "border-cyan-300/45 bg-cyan-300/10 shadow-hud-cyan"
          : "border-cyan-300/10 bg-slate-950/35 hover:border-cyan-300/30 hover:bg-cyan-300/6"
      )}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-xl border",
            tone === "emerald" &&
              "border-emerald-300/24 bg-emerald-300/10 text-emerald-200",
            tone === "red" && "border-red-300/24 bg-red-500/10 text-red-200",
            tone === "amber" &&
              "border-amber-300/24 bg-amber-300/10 text-amber-200",
            tone === "blue" && "border-sky-300/24 bg-sky-300/10 text-sky-200",
            tone === "violet" &&
              "border-violet-300/24 bg-violet-300/10 text-violet-200",
            tone === "cyan" &&
              "border-cyan-300/20 bg-cyan-300/10 text-cyan-200",
            tone === "slate" && "border-slate-500/20 bg-white/5 text-slate-300"
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-semibold text-slate-100">
              {eventTitle(event)}
            </span>
            <span className="shrink-0 rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-400">
              {categoryLabel(event.category)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
            <span className="font-mono text-cyan-200/80">
              {formatRuntimeTime(event.current_time)}
            </span>
            <span>{formatWallTime(event.created_at)}</span>
            <span>操作者 {event.actor || "system"}</span>
          </div>
          {event.unit_changes.length > 0 && (
            <div className="mt-2 flex max-w-full flex-wrap gap-1.5">
              {event.unit_changes.slice(0, 3).map((change) => (
                <ChangeBadge
                  change={change}
                  key={`${event.id}-${change.change_type}-${change.unit_type}-${change.unit_id}`}
                />
              ))}
              {event.unit_changes.length > 3 && (
                <span className="rounded-full border border-cyan-300/10 bg-white/[0.03] px-2 py-0.5 text-[10px] text-slate-500">
                  +{event.unit_changes.length - 3}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function EventDetail({ event }: { event: RuntimeTimelineEvent | undefined }) {
  if (!event) {
    return (
      <div className="rounded-2xl border border-dashed border-cyan-300/12 bg-slate-950/30 p-5 text-center text-sm text-slate-500">
        选择左侧事件查看单位变化与原始载荷摘要。
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-cyan-300/12 bg-slate-950/35 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-100">
            {eventTitle(event)}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {event.event_type} · {formatRuntimeTime(event.current_time)}
          </div>
        </div>
        <span className="rounded border border-cyan-300/18 bg-cyan-300/8 px-2 py-1 text-[10px] text-cyan-200">
          {event.action || "event"}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
            <GitCommitVertical className="size-4 text-cyan-200" />
            单位状态变化
          </div>
          {event.unit_changes.length === 0 ? (
            <div className="rounded-xl border border-cyan-300/10 bg-white/[0.03] px-3 py-3 text-xs text-slate-500">
              此事件没有记录单位状态差异。
            </div>
          ) : (
            <div className="space-y-2">
              {event.unit_changes.map((change) => (
                <div
                  className="rounded-xl border border-cyan-300/10 bg-white/[0.03] p-3"
                  key={`${event.id}-detail-${change.change_type}-${change.unit_type}-${change.unit_id}`}
                >
                  <div className="flex min-w-0 items-center justify-between gap-3">
                    <ChangeBadge change={change} />
                    <span className="truncate font-mono text-[10px] text-slate-500">
                      {change.unit_type}/{change.unit_id}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-400">
                    {unitChangeSummary(change)}
                  </div>
                  {change.change_type === "updated" && (
                    <div className="mt-2 grid gap-1.5">
                      {Object.entries(change.fields ?? {})
                        .slice(0, 6)
                        .map(([field, diff]) => (
                          <div
                            className="grid grid-cols-[88px_minmax(0,1fr)] gap-2 rounded-lg bg-slate-950/45 px-2 py-1.5 text-[11px]"
                            key={`${change.unit_id}-${field}`}
                          >
                            <span className="text-slate-500">
                              {fieldLabels[field] ?? field}
                            </span>
                            <span className="min-w-0 truncate text-slate-300">
                              {formatValue(diff.before)}
                              {" -> "}
                              {formatValue(diff.after)}
                            </span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
            <FileText className="size-4 text-cyan-200" />
            事件载荷
          </div>
          <pre className="max-h-48 overflow-auto rounded-xl border border-cyan-300/10 bg-[#020712]/70 p-3 text-[11px] leading-relaxed text-slate-400">
            {JSON.stringify(event.payload ?? {}, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function TimelineReplayPanel({
  open,
  scenarioId,
  runtimeScenarioId,
  snapshot,
  onClose,
}: TimelineReplayPanelProps) {
  const [events, setEvents] = useState<RuntimeTimelineEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string>("");
  const [category, setCategory] = useState<TimelineCategory>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trainingScore, setTrainingScore] =
    useState<TrainingScoreResponse | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreError, setScoreError] = useState<string | null>(null);

  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response: RuntimeTimelineResponse = scenarioId
        ? await listScenarioTimeline(scenarioId, { limit: 300 })
        : await listRuntimeTimeline({
            scenarioId: runtimeScenarioId,
            limit: 300,
          });
      setEvents(response.events);
      setSelectedEventId((current) => {
        if (current && response.events.some((event) => event.id === current)) {
          return current;
        }
        return response.events[response.events.length - 1]?.id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "时间线加载失败");
    } finally {
      setLoading(false);
    }
  }, [runtimeScenarioId, scenarioId]);

  const fetchTrainingScore = useCallback(async () => {
    if (!scenarioId) {
      setTrainingScore(null);
      setScoreError(null);
      setScoreLoading(false);
      return;
    }
    setScoreLoading(true);
    setScoreError(null);
    try {
      setTrainingScore(await getScenarioTrainingScore(scenarioId));
    } catch (err) {
      setScoreError(err instanceof Error ? err.message : "训练评分加载失败");
    } finally {
      setScoreLoading(false);
    }
  }, [scenarioId]);

  const refreshAll = useCallback(() => {
    void fetchTimeline();
    void fetchTrainingScore();
  }, [fetchTimeline, fetchTrainingScore]);

  useEffect(() => {
    if (!open) return;
    refreshAll();
    const timelineTimer = window.setInterval(() => void fetchTimeline(), 5000);
    const scoreTimer = window.setInterval(
      () => void fetchTrainingScore(),
      10000
    );
    return () => {
      window.clearInterval(timelineTimer);
      window.clearInterval(scoreTimer);
    };
  }, [fetchTimeline, fetchTrainingScore, open, refreshAll]);

  const filteredEvents = useMemo(() => {
    if (category === "all") return events;
    return events.filter((event) => event.category === category);
  }, [category, events]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId),
    [events, selectedEventId]
  );

  const categoryCounts = useMemo(() => {
    return events.reduce<Record<TimelineCategory, number>>(
      (acc, event) => {
        acc.all += 1;
        if (event.category in acc) {
          acc[event.category as TimelineCategory] += 1;
        }
        return acc;
      },
      { all: 0, command: 0, runtime: 0, scenario: 0, aar: 0 }
    );
  }, [events]);

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          animate={{ opacity: 1, x: 0 }}
          className="fixed bottom-3 right-3 top-14 z-[70] flex w-[min(1080px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-cyan-300/18 bg-[#050b13]/95 shadow-[0_24px_90px_rgba(0,0,0,0.62)] backdrop-blur-2xl"
          exit={{ opacity: 0, x: 28 }}
          initial={{ opacity: 0, x: 28 }}
          role="dialog"
          aria-label="推演回放与 AAR 时间线"
          transition={{ duration: 0.2, ease: "easeOut" }}
        >
          <div className="relative border-b border-cyan-300/10 px-5 py-4">
            <div className="pointer-events-none absolute inset-0 tactical-grid opacity-25" />
            <div className="relative flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.26em] text-cyan-300/70">
                  <History className="size-3.5" />
                  Replay / AAR
                </div>
                <div className="mt-1.5 truncate text-lg font-semibold text-slate-100">
                  推演回放时间线
                </div>
                <div className="mt-1 truncate text-xs text-slate-500">
                  {snapshot.scenarioName} ·{" "}
                  {formatRuntimeTime(snapshot.currentTime)}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  aria-label="刷新时间线"
                  className="size-9"
                  disabled={loading || scoreLoading}
                  onClick={refreshAll}
                  size="icon"
                  title="刷新时间线"
                  variant="ghost"
                >
                  {loading || scoreLoading ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RefreshCcw className="size-4" />
                  )}
                </Button>
                <Button
                  aria-label="关闭推演回放"
                  className="size-9"
                  onClick={onClose}
                  size="icon"
                  title="关闭"
                  variant="ghost"
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 border-b border-cyan-300/10 px-5 py-4 sm:grid-cols-4">
            <StatTile
              icon={<GitCommitVertical className="size-4" />}
              label="事件"
              value={events.length}
            />
            <StatTile
              icon={<Radio className="size-4" />}
              label="命令"
              value={categoryCounts.command}
            />
            <StatTile
              icon={<ShieldCheck className="size-4" />}
              label="AAR"
              value={categoryCounts.aar}
            />
            <StatTile
              icon={<Sparkles className="size-4" />}
              label="单位变化"
              value={countUnitChanges(events)}
            />
          </div>

          <div className="border-b border-cyan-300/10 px-5 py-4">
            <ScorePanel
              error={scoreError}
              hasScenario={Boolean(scenarioId)}
              loading={scoreLoading}
              score={trainingScore}
            />
          </div>

          <div className="border-b border-cyan-300/10 px-5 py-3">
            <div className="flex flex-wrap gap-2">
              {categoryOptions.map((item) => (
                <button
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs transition-all",
                    category === item.id
                      ? "border-cyan-300/45 bg-cyan-300/12 text-cyan-100 shadow-hud-cyan"
                      : "border-cyan-300/10 bg-slate-950/35 text-slate-500 hover:border-cyan-300/30 hover:text-slate-200"
                  )}
                  key={item.id}
                  onClick={() => setCategory(item.id)}
                  type="button"
                >
                  {item.label}
                  <span className="ml-1.5 font-mono text-[10px]">
                    {categoryCounts[item.id]}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="mx-4 mt-3 rounded-xl border border-red-300/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(220px,0.7fr)] gap-4 overflow-hidden p-5 xl:grid-cols-[minmax(0,1fr)_minmax(330px,0.78fr)] xl:grid-rows-1">
            <div className="min-h-0 overflow-y-auto pr-1">
              <div className="relative space-y-2">
                <div className="absolute bottom-2 left-[18px] top-2 w-px bg-cyan-300/12" />
                {filteredEvents.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-cyan-300/12 bg-slate-950/30 p-6 text-center">
                    <Clock3 className="mx-auto mb-3 size-6 text-cyan-200/70" />
                    <div className="text-sm font-semibold text-slate-300">
                      暂无回放事件
                    </div>
                    <div className="mt-1 text-xs leading-relaxed text-slate-500">
                      执行命令、审批、单步推演或生成 AAR 后，这里会形成时间线。
                    </div>
                  </div>
                ) : (
                  filteredEvents.map((event) => (
                    <TimelineItem
                      event={event}
                      key={event.id}
                      onSelect={() => setSelectedEventId(event.id)}
                      selected={event.id === selectedEventId}
                    />
                  ))
                )}
              </div>
            </div>
            <div className="min-h-0 overflow-y-auto">
              <EventDetail event={selectedEvent} />
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
