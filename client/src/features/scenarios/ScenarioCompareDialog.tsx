import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRightLeft,
  Clock3,
  Download,
  GitBranch,
  Loader2,
  Radar,
  Route,
  Save,
  Trophy,
} from "lucide-react";

import { ApiError } from "@/api/client";
import {
  compareScenarios,
  createScenarioCompareReport,
  createScenarioBranch,
  listScenarioTrainingScoreRecords,
  updateScenarioCompareSession,
} from "@/api/scenarios";
import type {
  ScenarioCompareItem,
  ScenarioCompareResponse,
  ScenarioCompareSession,
  TrainingScoreRecord,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import {
  buildScenarioCompareSnapshot,
  buildScenarioCompareRestoreStateFromSession,
  resolveScenarioCompareItems,
  type ScenarioCompareRestoreState,
  type CompareScoreSource,
} from "./scenarioCompare";

type ScenarioCompareDialogProps = {
  scenarioIds: string[];
  open: boolean;
  onClose: () => void;
  onOpenScenario: (scenarioId: string) => void;
  initialRestoreState?: ScenarioCompareRestoreState | null;
  initialSession?: ScenarioCompareSession | null;
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

function safeSnapshotFileName(name: string): string {
  return (
    name
      .trim()
      .replace(/[^A-Za-z0-9_\-\u4e00-\u9fa5]+/g, "_")
      .slice(0, 48) || "tianshu_compare_snapshot"
  );
}

export default function ScenarioCompareDialog({
  scenarioIds,
  open,
  onClose,
  onOpenScenario,
  initialRestoreState,
  initialSession,
}: ScenarioCompareDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyWarning, setHistoryWarning] = useState<string | null>(null);
  const [data, setData] = useState<ScenarioCompareResponse | null>(null);
  const [baselineId, setBaselineId] = useState("");
  const [recordsByScenario, setRecordsByScenario] = useState<
    Record<string, TrainingScoreRecord[]>
  >({});
  const [selectedSources, setSelectedSources] = useState<
    Record<string, CompareScoreSource>
  >({});
  const [branchingScenarioId, setBranchingScenarioId] = useState<string | null>(
    null
  );
  const [exporting, setExporting] = useState(false);
  const [savingReport, setSavingReport] = useState(false);
  const [reportNotice, setReportNotice] = useState<string | null>(null);
  const [sessionSaveState, setSessionSaveState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const lastSavedSessionPayloadRef = useRef("");

  useEffect(() => {
    lastSavedSessionPayloadRef.current = JSON.stringify({
      baseline_id: initialSession?.state.baseline_id ?? "",
      scenario_ids: initialSession?.scenario_ids ?? [],
      selected_sources: initialSession?.state.selected_sources ?? {},
    });
    setSessionSaveState("idle");
  }, [initialSession]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function loadCompareData() {
      setLoading(true);
      setError(null);
      setHistoryWarning(null);
      setReportNotice(null);
      setSessionSaveState("idle");

      try {
        const response = await compareScenarios(scenarioIds);
        const restoredState =
          initialSession != null
            ? buildScenarioCompareRestoreStateFromSession(initialSession)
            : initialRestoreState;
        const historyResults = await Promise.all(
          response.items.map(async (item) => {
            try {
              const records = await listScenarioTrainingScoreRecords(item.id, {
                limit: 8,
              });
              return { scenarioId: item.id, records, failed: false };
            } catch {
              return {
                scenarioId: item.id,
                records: [] as TrainingScoreRecord[],
                failed: true,
              };
            }
          })
        );

        if (cancelled) return;

        const historyMap = Object.fromEntries(
          historyResults.map((entry) => [entry.scenarioId, entry.records])
        );
        const failedHistoryCount = historyResults.filter(
          (entry) => entry.failed
        ).length;

        setData(response);
        setRecordsByScenario(historyMap);
        setBaselineId((current) => {
          const restoredBaselineId = restoredState?.baselineId;
          if (
            restoredBaselineId &&
            response.items.some((item) => item.id === restoredBaselineId)
          ) {
            return restoredBaselineId;
          }
          if (current && response.items.some((item) => item.id === current)) {
            return current;
          }
          return response.baseline_id;
        });
        setSelectedSources((current) => {
          const restoredSources = restoredState?.selectedSources ?? {};
          const next: Record<string, CompareScoreSource> = {};
          response.items.forEach((item) => {
            const source = restoredSources[item.id] ?? current[item.id];
            next[item.id] =
              source === "live" ||
              historyMap[item.id]?.some((record) => record.id === source)
                ? (source ?? "live")
                : "live";
          });
          return next;
        });
        setHistoryWarning(
          failedHistoryCount > 0
            ? `${failedHistoryCount} 个方案的历史评分加载失败，当前先使用实时评分。`
            : null
        );
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "方案对比加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadCompareData();
    return () => {
      cancelled = true;
    };
  }, [initialRestoreState, initialSession, open, scenarioIds]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const resolvedItems = useMemo(
    () =>
      resolveScenarioCompareItems(items, recordsByScenario, selectedSources),
    [items, recordsByScenario, selectedSources]
  );
  const baseline = useMemo(
    () =>
      resolvedItems.find((item) => item.id === baselineId) ??
      resolvedItems.find((item) => item.id === data?.baseline_id) ??
      resolvedItems[0] ??
      null,
    [baselineId, data?.baseline_id, resolvedItems]
  );
  const highestScoreItem = useMemo(
    () =>
      [...resolvedItems].sort(
        (a, b) => b.activeScore.overall_score - a.activeScore.overall_score
      )[0] ?? null,
    [resolvedItems]
  );
  const snapshot = useMemo(() => {
    if (!data || !baseline) return null;
    return buildScenarioCompareSnapshot(data, baseline.id, resolvedItems);
  }, [baseline, data, resolvedItems]);

  useEffect(() => {
    if (!open || !initialSession || !baseline || resolvedItems.length === 0)
      return;

    const payload = {
      baseline_id: baseline.id,
      scenario_ids: resolvedItems.map((item) => item.id),
      state: {
        baseline_id: baseline.id,
        selected_sources: Object.fromEntries(
          resolvedItems.map((item) => [item.id, item.scoreSourceId])
        ),
      },
    };
    const encoded = JSON.stringify(payload);
    if (encoded === lastSavedSessionPayloadRef.current) return;

    const timeout = window.setTimeout(async () => {
      setSessionSaveState("saving");
      try {
        await updateScenarioCompareSession(initialSession.id, payload);
        lastSavedSessionPayloadRef.current = encoded;
        setSessionSaveState("saved");
      } catch {
        setSessionSaveState("error");
      }
    }, 400);

    return () => window.clearTimeout(timeout);
  }, [baseline, initialSession, open, resolvedItems]);

  const handleSelectSource = (
    scenarioId: string,
    sourceId: CompareScoreSource
  ) => {
    setSelectedSources((current) => ({
      ...current,
      [scenarioId]: sourceId,
    }));
  };

  const handleCreateBranch = async (item: ScenarioCompareItem) => {
    const nextDepth = (item.branch_meta?.branch_depth ?? 0) + 1;
    setBranchingScenarioId(item.id);
    try {
      const created = await createScenarioBranch(item.id, {
        name: `${item.name} / 分支 ${nextDepth}`,
        description: item.description,
        status: "draft",
      });
      onClose();
      onOpenScenario(created.id);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "创建分支失败");
    } finally {
      setBranchingScenarioId(null);
    }
  };

  const handleExportSnapshot = () => {
    if (!snapshot || !baseline) return;
    setExporting(true);
    try {
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const timestamp = new Date().toISOString().replace(/[:.]/g, "_");
      anchor.href = url;
      anchor.download = `${safeSnapshotFileName(baseline.name)}_compare_${timestamp}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      window.alert("导出对比快照失败，请稍后重试。");
    } finally {
      setExporting(false);
    }
  };

  const handleSaveReport = async () => {
    if (!snapshot || !baseline) return;
    setSavingReport(true);
    setReportNotice(null);
    try {
      await createScenarioCompareReport({
        title: `${baseline.name} 对比报告`,
        baseline_id: baseline.id,
        scenario_ids: resolvedItems.map((item) => item.id),
        snapshot,
      });
      setReportNotice("对比报告已保存，可在“对比报告”面板中查看。");
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "保存对比报告失败");
    } finally {
      setSavingReport(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/72 p-4 backdrop-blur-md"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <Card className="flex h-[min(88vh,980px)] w-full max-w-[1460px] flex-col overflow-hidden rounded-2xl border-cyan-200/15 bg-[#06101c] shadow-[0_32px_120px_rgba(0,0,0,0.52)]">
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
              评分来源可切换为实时评分或历史归档评分；继续分支始终基于当前项目状态创建。
            </div>
            {initialSession && (
              <div className="mt-2 text-xs text-slate-500">
                会话状态：
                {sessionSaveState === "saving"
                  ? "保存中"
                  : sessionSaveState === "saved"
                    ? "已保存"
                    : sessionSaveState === "error"
                      ? "保存失败"
                      : "已加载"}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 md:flex">
              <label className="text-xs text-slate-500">基线方案</label>
              <select
                value={baseline?.id ?? ""}
                onChange={(event) => setBaselineId(event.target.value)}
                className="h-10 rounded-xl border border-cyan-200/15 bg-slate-950/55 px-3 text-sm text-slate-200 outline-none focus:border-cyan-200/35"
              >
                {resolvedItems.map((item) => (
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
              onClick={() => void handleSaveReport()}
              disabled={!snapshot || savingReport}
            >
              {savingReport ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Save className="size-4" />
              )}
              保存报告
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
              onClick={handleExportSnapshot}
              disabled={!snapshot || exporting}
            >
              <Download className="size-4" />
              导出快照
            </Button>
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
              {historyWarning && (
                <div className="rounded-xl border border-amber-300/20 bg-amber-400/[0.08] px-4 py-3 text-sm text-amber-100">
                  {historyWarning}
                </div>
              )}
              {reportNotice && (
                <div className="rounded-xl border border-emerald-300/20 bg-emerald-400/[0.08] px-4 py-3 text-sm text-emerald-100">
                  {reportNotice}
                </div>
              )}

              <div className="grid gap-3 lg:grid-cols-4">
                <MetricTile
                  icon={Trophy}
                  label="基线总分"
                  value={`${baseline.activeScore.overall_score}`}
                  hint={`${baseline.activeScore.grade} · ${baseline.name}`}
                />
                <MetricTile
                  icon={Radar}
                  label="当前对比数"
                  value={`${resolvedItems.length}`}
                  hint="最多同时对比 4 个方案"
                />
                <MetricTile
                  icon={Route}
                  label="最高分方案"
                  value={`${highestScoreItem?.activeScore.overall_score ?? 0}`}
                  hint={highestScoreItem?.name ?? "暂无"}
                />
                <MetricTile
                  icon={Clock3}
                  label="最近推演活动"
                  value={relativeTime(
                    [...resolvedItems]
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
                  className="grid min-w-[1100px] gap-4"
                  style={{
                    gridTemplateColumns: `repeat(${Math.max(resolvedItems.length, 2)}, minmax(320px, 1fr))`,
                  }}
                >
                  {resolvedItems.map((item) => {
                    const scoreDelta =
                      item.activeScore.overall_score -
                      baseline.activeScore.overall_score;
                    const branchBusy = branchingScenarioId === item.id;

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
                              <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-slate-300">
                                {item.scoreSourceLabel}
                              </span>
                              {item.id === baseline.id && (
                                <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-emerald-200">
                                  基线
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="ghost"
                              className="rounded-lg border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                              onClick={() => setBaselineId(item.id)}
                              disabled={item.id === baseline.id}
                            >
                              设为基线
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              className="rounded-lg border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                              onClick={() => onOpenScenario(item.id)}
                            >
                              打开
                            </Button>
                          </div>
                        </div>

                        <div className="mt-4 rounded-xl border border-cyan-200/10 bg-white/[0.02] p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <div className="text-[11px] uppercase tracking-wide text-slate-500">
                                评分来源
                              </div>
                              <div className="mt-1 text-sm text-slate-300">
                                当前对比所采用的评分版本
                              </div>
                            </div>
                            <select
                              value={item.scoreSourceId}
                              onChange={(event) =>
                                handleSelectSource(item.id, event.target.value)
                              }
                              className="h-10 min-w-[220px] rounded-xl border border-cyan-200/15 bg-slate-950/55 px-3 text-sm text-slate-200 outline-none focus:border-cyan-200/35"
                            >
                              {item.availableSources.map((source) => (
                                <option key={source.id} value={source.id}>
                                  {source.label}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2 text-xs">
                            {item.latestScoreRecord ? (
                              <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 text-slate-400">
                                最近归档{" "}
                                {relativeTime(
                                  item.latestScoreRecord.created_at
                                )}
                              </span>
                            ) : (
                              <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 text-slate-400">
                                暂无历史归档评分
                              </span>
                            )}
                            {item.trendFromLatestRecord !== null && (
                              <span
                                className={cn(
                                  "rounded-full border px-2 py-1",
                                  item.trendFromLatestRecord > 0
                                    ? "border-emerald-300/20 bg-emerald-300/[0.08] text-emerald-100"
                                    : item.trendFromLatestRecord < 0
                                      ? "border-rose-300/20 bg-rose-300/[0.08] text-rose-100"
                                      : "border-white/10 bg-white/[0.03] text-slate-400"
                                )}
                              >
                                较最近归档 {signed(item.trendFromLatestRecord)}
                              </span>
                            )}
                            {item.liveScoreDelta !== null && (
                              <span
                                className={cn(
                                  "rounded-full border px-2 py-1",
                                  item.liveScoreDelta > 0
                                    ? "border-emerald-300/20 bg-emerald-300/[0.08] text-emerald-100"
                                    : item.liveScoreDelta < 0
                                      ? "border-rose-300/20 bg-rose-300/[0.08] text-rose-100"
                                      : "border-white/10 bg-white/[0.03] text-slate-400"
                                )}
                              >
                                较实时评分 {signed(item.liveScoreDelta)}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-3">
                          <StatCell
                            label="训练总分"
                            value={`${item.activeScore.overall_score}`}
                            delta={item.id === baseline.id ? null : scoreDelta}
                          />
                          <StatCell
                            label="推演等级"
                            value={item.activeScore.grade}
                            helper={item.activeScore.confidence}
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
                            {item.activeScore.dimensions.map((dimension) => {
                              const baselineDimension =
                                baseline.activeScore.dimensions.find(
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
                              {item.activeScore.strengths
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
                              {item.activeScore.improvements
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

                        <div className="mt-4 flex items-center justify-between gap-3 border-t border-cyan-200/10 pt-4">
                          <div className="text-xs text-slate-500">
                            基于评分结果做判断，分支仍从当前场景版本继续。
                          </div>
                          <Button
                            type="button"
                            className="rounded-xl border border-cyan-200/20 bg-gradient-to-r from-cyan-400 to-blue-600 text-white shadow-[0_18px_46px_rgba(14,165,233,0.28)] hover:shadow-[0_22px_56px_rgba(14,165,233,0.38)]"
                            onClick={() => void handleCreateBranch(item)}
                            disabled={branchBusy}
                          >
                            {branchBusy ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <GitBranch className="size-4" />
                            )}
                            继续分支
                          </Button>
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
