import { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, GitBranch, Loader2, Play, Trash2 } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  deleteScenarioCompareSession,
  listScenarioCompareSessions,
} from "@/api/scenarios";
import type { ScenarioCompareSession } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ScenarioCompareSessionsDialogProps = {
  open: boolean;
  onClose: () => void;
  onOpenScenario: (scenarioId: string) => void;
  onOpenCompare: (compareSession: ScenarioCompareSession) => void;
};

function formatDateTime(iso?: string | null): string {
  if (!iso) return "暂无";
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return "暂无";
  return time.toLocaleString();
}

export default function ScenarioCompareSessionsDialog({
  open,
  onClose,
  onOpenScenario,
  onOpenCompare,
}: ScenarioCompareSessionsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ScenarioCompareSession[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function loadSessions() {
      setLoading(true);
      setError(null);
      try {
        const response = await listScenarioCompareSessions({ limit: 40 });
        if (!cancelled) setSessions(response);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载对比会话失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const totalComparedScenarios = useMemo(
    () =>
      sessions.reduce((sum, session) => sum + session.scenario_ids.length, 0),
    [sessions]
  );

  const handleDelete = async (compareSession: ScenarioCompareSession) => {
    if (!window.confirm(`确定删除对比会话「${compareSession.title}」？`))
      return;
    setDeletingId(compareSession.id);
    try {
      await deleteScenarioCompareSession(compareSession.id);
      setSessions((current) =>
        current.filter((item) => item.id !== compareSession.id)
      );
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "删除对比会话失败");
    } finally {
      setDeletingId(null);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center bg-black/72 p-4 backdrop-blur-md"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <Card className="flex h-[min(84vh,920px)] w-full max-w-[1180px] flex-col overflow-hidden rounded-2xl border-cyan-200/15 bg-[#06101c] shadow-[0_32px_120px_rgba(0,0,0,0.52)]">
        <div className="flex items-center justify-between border-b border-cyan-200/10 px-6 py-5">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-3 py-1 text-xs text-cyan-100">
              <GitBranch className="size-3.5" />
              对比会话
            </div>
            <div className="mt-3 text-xl font-semibold text-slate-100">
              已保存的多方案对比工作台
            </div>
            <div className="mt-1 text-sm text-slate-500">
              这里保存的是仍可继续调整基线、评分来源和分支方案的对比会话。
            </div>
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

        <div className="min-h-0 flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex h-full items-center justify-center text-slate-400">
              <Loader2 className="mr-2 size-4 animate-spin" />
              正在加载对比会话...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-rose-400/20 bg-rose-500/[0.08] px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          ) : sessions.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-cyan-200/15 bg-slate-950/24 px-6 py-14 text-center">
              <div className="text-base font-semibold text-slate-100">
                还没有保存任何对比会话
              </div>
              <div className="mt-2 text-sm text-slate-500">
                从项目卡片发起“三方案对比”，或后续在对比工作台里继续保存状态。
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-3 md:grid-cols-3">
                <MetricTile label="会话数量" value={`${sessions.length}`} />
                <MetricTile
                  label="累计纳入方案"
                  value={`${totalComparedScenarios}`}
                />
                <MetricTile
                  label="最近更新"
                  value={formatDateTime(sessions[0]?.updated_at)}
                />
              </div>

              <div className="space-y-4">
                {sessions.map((compareSession) => (
                  <Card
                    key={compareSession.id}
                    className="rounded-2xl border border-cyan-200/10 bg-slate-950/28 p-5"
                  >
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-lg font-semibold text-slate-100">
                            {compareSession.title}
                          </div>
                          <span className="rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-xs text-cyan-100">
                            基线：{compareSession.baseline_scenario_id}
                          </span>
                          <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-xs text-slate-400">
                            {compareSession.scenario_ids.length} 个方案
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
                          <span>
                            创建时间：
                            {formatDateTime(compareSession.created_at)}
                          </span>
                          <span>
                            最近更新：
                            {formatDateTime(compareSession.updated_at)}
                          </span>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {compareSession.scenario_ids.map((scenarioId) => (
                            <span
                              key={scenarioId}
                              className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-300"
                            >
                              {scenarioId ===
                              compareSession.baseline_scenario_id
                                ? "基线 / "
                                : ""}
                              {scenarioId}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                          onClick={() => onOpenCompare(compareSession)}
                        >
                          <ArrowRightLeft className="size-4" />
                          打开对比
                        </Button>
                        {compareSession.source_scenario_id && (
                          <Button
                            type="button"
                            variant="ghost"
                            className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                            onClick={() =>
                              onOpenScenario(compareSession.source_scenario_id!)
                            }
                          >
                            <Play className="size-4" />
                            打开源方案
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-rose-300/15 bg-rose-400/[0.04] text-rose-100 hover:bg-rose-400/[0.08]"
                          onClick={() => void handleDelete(compareSession)}
                          disabled={deletingId === compareSession.id}
                        >
                          {deletingId === compareSession.id ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Trash2 className="size-4" />
                          )}
                          删除
                        </Button>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-cyan-200/10 bg-slate-950/28 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-3 text-2xl font-semibold text-slate-100">{value}</div>
    </div>
  );
}
