import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft,
  Download,
  FileText,
  Loader2,
  Trash2,
} from "lucide-react";

import { ApiError } from "@/api/client";
import {
  deleteScenarioCompareReport,
  listScenarioCompareReports,
} from "@/api/scenarios";
import type {
  ScenarioCompareReport,
  ScenarioCompareSnapshot,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ScenarioCompareReportsDialogProps = {
  open: boolean;
  onClose: () => void;
  onOpenScenario: (scenarioId: string) => void;
  onOpenCompare: (report: ScenarioCompareReport) => void;
};

function safeSnapshotFileName(name: string): string {
  return (
    name
      .trim()
      .replace(/[^A-Za-z0-9_\-\u4e00-\u9fa5]+/g, "_")
      .slice(0, 48) || "tianshu_compare_snapshot"
  );
}

function formatDateTime(iso?: string | null): string {
  if (!iso) return "暂无";
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return "暂无";
  return time.toLocaleString();
}

function exportSnapshot(title: string, snapshot: ScenarioCompareSnapshot) {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const timestamp = new Date().toISOString().replace(/[:.]/g, "_");
  anchor.href = url;
  anchor.download = `${safeSnapshotFileName(title)}_${timestamp}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ScenarioCompareReportsDialog({
  open,
  onClose,
  onOpenScenario,
  onOpenCompare,
}: ScenarioCompareReportsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<ScenarioCompareReport[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function loadReports() {
      setLoading(true);
      setError(null);
      try {
        const response = await listScenarioCompareReports({ limit: 40 });
        if (!cancelled) setReports(response);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载对比报告失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadReports();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const totalComparedScenarios = useMemo(
    () =>
      reports.reduce((sum, report) => sum + report.snapshot.items.length, 0),
    [reports]
  );

  const handleDelete = async (report: ScenarioCompareReport) => {
    if (!window.confirm(`确定删除对比报告「${report.title}」？`)) return;
    setDeletingId(report.id);
    try {
      await deleteScenarioCompareReport(report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "删除对比报告失败");
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
              <FileText className="size-3.5" />
              对比报告
            </div>
            <div className="mt-3 text-xl font-semibold text-slate-100">
              已保存的方案对比快照
            </div>
            <div className="mt-1 text-sm text-slate-500">
              这里保存的是对比当时的评分来源、基线和快照内容，可直接回看或导出。
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
              正在加载对比报告...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-rose-400/20 bg-rose-500/[0.08] px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          ) : reports.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-cyan-200/15 bg-slate-950/24 px-6 py-14 text-center">
              <div className="text-base font-semibold text-slate-100">
                还没有保存任何对比报告
              </div>
              <div className="mt-2 text-sm text-slate-500">
                在方案对比面板中点击“保存报告”后，这里会出现历史快照。
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-3 md:grid-cols-3">
                <MetricTile label="报告数量" value={`${reports.length}`} />
                <MetricTile
                  label="累计对比场景"
                  value={`${totalComparedScenarios}`}
                />
                <MetricTile
                  label="最近生成"
                  value={formatDateTime(reports[0]?.created_at)}
                />
              </div>

              <div className="space-y-4">
                {reports.map((report) => (
                  <Card
                    key={report.id}
                    className="rounded-2xl border border-cyan-200/10 bg-slate-950/28 p-5"
                  >
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-lg font-semibold text-slate-100">
                            {report.title}
                          </div>
                          <span className="rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-xs text-cyan-100">
                            基线：{report.snapshot.baseline_name}
                          </span>
                          <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-xs text-slate-400">
                            {report.snapshot.items.length} 个方案
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
                          <span>
                            保存时间：{formatDateTime(report.created_at)}
                          </span>
                          <span>
                            对比生成：
                            {formatDateTime(report.snapshot.generated_at)}
                          </span>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {report.snapshot.items.map((item) => (
                            <span
                              key={item.id}
                              className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-300"
                            >
                              {item.baseline ? "基线 · " : ""}
                              {item.name} · {item.score.overall_score}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                          onClick={() => onOpenCompare(report)}
                        >
                          <ArrowRightLeft className="size-4" />
                          打开对比
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                          onClick={() =>
                            onOpenScenario(report.baseline_scenario_id)
                          }
                        >
                          打开基线
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-cyan-200/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                          onClick={() =>
                            exportSnapshot(report.title, report.snapshot)
                          }
                        >
                          <Download className="size-4" />
                          导出快照
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-xl border border-rose-300/15 bg-rose-400/[0.04] text-rose-100 hover:bg-rose-400/[0.08]"
                          onClick={() => void handleDelete(report)}
                          disabled={deletingId === report.id}
                        >
                          {deletingId === report.id ? (
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
