import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft,
  Clock3,
  GitBranch,
  Loader2,
  Radar,
  Route,
  Trophy,
} from "lucide-react";

import { compareScenarios } from "@/api/scenarios";
import type { ScenarioCompareItem, ScenarioCompareResponse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type ScenarioCompareDialogProps = {
  scenarioIds: string[];
  open: boolean;
  onClose: () => void;
  onOpenScenario: (scenarioId: string) => void;
};

function relativeTime(iso?: string | null): string {
  if (!iso) return "暂无记录";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "暂无记录";
  const diff = Date.now() - time;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "刚刚更新";
  if (diff < hour) return `${Math.max(1, Math.floor(diff / minute))} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < day * 14) return `${Math.floor(diff / day)} 天前`;
  return new Date(iso).toLocaleDateString();
}

function deltaTone(value: number): string {
  if (value > 0) return "text-emerald-300";
  if (value < 0) return "text-rose-300";
  return "text-slate-400";
}

function signed(value: number): string {
  if (value > 0) return `+${value}`;
  return `${value}`;
}

export default function ScenarioCompareDialog({
  scenarioIds,
  open,
  onClose,
  onOpenScenario,
}: ScenarioCompareDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ScenarioCompareResponse | null>(null);
  const [baselineId, setBaselineId] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void compareScenarios(scenarioIds)
      .then((response) => {
        if (cancelled) return;
        setData(response);
        setBaselineId((current) => {
          if (current && response.items.some((item) => item.id === current)) {
            return current;
          }
          return response.baseline_id;
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "方案对比加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, scenarioIds]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const baseline = useMemo(
    () =>
      items.find((item) => item.id === baselineId) ??
      items.find((item) => item.id === data?.baseline_id) ??
      items[0] ??
      null,
    [baselineId, data?.baseline_id, items]
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/72 p-4 backdrop-blur-md"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <Card className="flex h-[min(86vh,920px)] w-full max-w-[1400px] flex-col overflow-hidden rounded-2xl border-cyan-200/15 bg-[#06101c] shadow-[0_32px_120px_rgba(0,0,0,0.52)]">
        <div className="flex items-center justify-between border-b border-cyan-200/10 px-6 py-5">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-3 py-1 text-xs text-cyan-100">
              <ArrowRightLeft className="size-3.5" />
              方案对比台
            </div>
            <div className="mt-3 text-xl font-semibold text-slate-100">
              并行对比推演方案
            </div>
            <div className="mt-1 text-sm text-slate-500">
              对比训练评分、时间线沉淀和复盘密度，优先找出更值得继续推演的分支。
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 md:flex">
              <label className="text-xs text-slate-500">基线方案</label>
              <select
                value={baseline?.id ?? ""}
                onChange={(event) => setBaselineId(event.target.value)}
                className="h-10 rounded-xl border border-cyan-200/15 bg-slate-950/55 px-3 text-sm text-slate-200 outline-none focus:border-cyan-200/35"
              >
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <Button
              type="button"
              variant="ghost"
              className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
              onClick={onClose}
            >
              关闭
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex h-full items-center justify-center text-slate-400">
              <Loader2 className="mr-2 size-4 animate-spin" />
              正在生成方案对比摘要...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-rose-400/20 bg-rose-500/[0.08] px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          ) : !baseline ? (
            <div className="rounded-xl border border-cyan-200/10 bg-slate-950/30 px-4 py-3 text-sm text-slate-400">
              请选择至少两个项目进行对比。
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-3 lg:grid-cols-4">
                <MetricTile
                  icon={Trophy}
                  label="基线总分"
                  value={`${baseline.training_score.overall_score}`}
                  hint={`${baseline.training_score.grade} · ${baseline.name}`}
                />
                <MetricTile
                  icon={Radar}
                  label="当前对比数"
                  value={`${items.length}`}
                  hint="最多同时对比 4 个方案"
                />
                <MetricTile
                  icon={Route}
                  label="最高分方案"
                  value={`${
                    [...items].sort(
                      (a, b) =>
                        b.training_score.overall_score -
                        a.training_score.overall_score
                    )[0]?.training_score.overall_score ?? 0
                  }`}
                  hint={
                    [...items].sort(
                      (a, b) =>
                        b.training_score.overall_score -
                        a.training_score.overall_score
                    )[0]?.name ?? "暂无"
                  }
                />
                <MetricTile
                  icon={Clock3}
                  label="最近推演活动"
                  value={relativeTime(
                    [...items]
                      .map((item) => item.latest_event_at)
                      .filter(Boolean)
                      .sort()
                      .at(-1) ?? null
                  )}
                  hint="基于时间线事件"
                />
              </div>

              <div className="overflow-x-auto">
                <div
                  className="grid min-w-[920px] gap-4"
                  style={{
                    gridTemplateColumns: `repeat(${Math.max(items.length, 2)}, minmax(280px, 1fr))`,
                  }}
                >
                  {items.map((item) => {
                    const scoreDelta =
                      item.training_score.overall_score -
                      baseline.training_score.overall_score;
                    return (
                      <Card
                        key={item.id}
                        className={cn(
                          "rounded-2xl border bg-slate-950/28 p-4",
                          item.id === baseline.id
                            ? "border-cyan-200/30 shadow-[0_0_0_1px_rgba(125,211,252,0.15)]"
                            : "border-cyan-200/10"
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-base font-semibold text-slate-100">
                              {item.name}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                              <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5">
                                v{item.version}
                              </span>
                              {item.branch_meta && (
                                <span className="inline-flex items-center gap-1 rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-cyan-100">
                                  <GitBranch className="size-3" />
                                  {item.branch_meta.branch_label}
                                </span>
                              )}
                              {item.id === baseline.id && (
                                <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-emerald-200">
                                  基线
                                </span>
                              )}
                            </div>
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            className="rounded-lg border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                            onClick={() => onOpenScenario(item.id)}
                          >
                            打开
                          </Button>
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-3">
                          <StatCell
                            label="训练总分"
                            value={`${item.training_score.overall_score}`}
                            delta={item.id === baseline.id ? null : scoreDelta}
                          />
                          <StatCell
                            label="推演等级"
                            value={item.training_score.grade}
                            helper={item.training_score.confidence}
                          />
                          <StatCell
                            label="任务 / 单位"
                            value={`${item.mission_count} / ${item.unit_count}`}
                          />
                          <StatCell
                            label="时间线事件"
                            value={`${item.timeline_event_count}`}
                            delta={
                              item.id === baseline.id
                                ? null
                                : item.timeline_event_count -
                                  baseline.timeline_event_count
                            }
                          />
                          <StatCell
                            label="AAR 记录"
                            value={`${item.aar_count}`}
                            delta={
                              item.id === baseline.id
                                ? null
                                : item.aar_count - baseline.aar_count
                            }
                          />
                          <StatCell
                            label="最近更新"
                            value={relativeTime(item.updated_at)}
                            helper={relativeTime(item.latest_event_at)}
                          />
                        </div>

                        <div className="mt-4 rounded-xl border border-cyan-200/10 bg-white/[0.025] p-3">
                          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                            评分维度
                          </div>
                          <div className="space-y-2">
                            {item.training_score.dimensions.map((dimension) => {
                              const baselineDimension =
                                baseline.training_score.dimensions.find(
                                  (candidate) => candidate.key === dimension.key
                                );
                              const delta = baselineDimension
                                ? dimension.score - baselineDimension.score
                                : null;
                              return (
                                <div
                                  key={dimension.key}
                                  className="flex items-center justify-between gap-3 text-sm"
                                >
                                  <div className="min-w-0">
                                    <div className="truncate text-slate-200">
                                      {dimension.label}
                                    </div>
                                    <div className="truncate text-xs text-slate-500">
                                      {dimension.summary}
                                    </div>
                                  </div>
                                  <div className="shrink-0 text-right">
                                    <div className="font-medium text-slate-100">
                                      {dimension.score}
                                    </div>
                                    {delta !== null &&
                                      item.id !== baseline.id && (
                                        <div
                                          className={cn(
                                            "text-xs",
                                            deltaTone(delta)
                                          )}
                                        >
                                          {signed(delta)}
                                        </div>
                                      )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        <div className="mt-4 space-y-2 text-sm">
                          <div>
                            <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                              优势
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {item.training_score.strengths
                                .slice(0, 3)
                                .map((entry) => (
                                  <span
                                    key={entry}
                                    className="rounded-full border border-emerald-300/15 bg-emerald-300/[0.08] px-2 py-1 text-xs text-emerald-100"
                                  >
                                    {entry}
                                  </span>
                                ))}
                            </div>
                          </div>
                          <div>
                            <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                              待改进
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {item.training_score.improvements
                                .slice(0, 3)
                                .map((entry) => (
                                  <span
                                    key={entry}
                                    className="rounded-full border border-amber-300/15 bg-amber-300/[0.08] px-2 py-1 text-xs text-amber-100"
                                  >
                                    {entry}
                                  </span>
                                ))}
                            </div>
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function MetricTile({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Trophy;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-cyan-200/10 bg-slate-950/28 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-500">
        <Icon className="size-3.5 text-cyan-300" />
        {label}
      </div>
      <div className="mt-3 text-2xl font-semibold text-slate-100">{value}</div>
      <div className="mt-1 text-sm text-slate-500">{hint}</div>
    </div>
  );
}

function StatCell({
  label,
  value,
  delta = null,
  helper,
}: {
  label: string;
  value: string;
  delta?: number | null;
  helper?: string;
}) {
  return (
    <div className="rounded-xl border border-cyan-200/10 bg-white/[0.02] p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
      <div className="mt-1 min-h-[1rem] text-xs">
        {delta !== null && delta !== undefined ? (
          <span className={deltaTone(delta)}>{signed(delta)}</span>
        ) : (
          <span className="text-slate-500">{helper ?? ""}</span>
        )}
      </div>
    </div>
  );
}
