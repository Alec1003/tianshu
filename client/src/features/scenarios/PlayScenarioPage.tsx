import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  activateScenario,
  createAarRecord,
  createScenario,
  getScenario,
  updateScenario,
} from "@/api/scenarios";
import type { ScenarioDetail } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import AITacticalCommandPlatform, {
  type SaveAarPayload,
  type ScenarioMeta,
} from "@/features/tactical/AITacticalCommandPlatform";

export default function PlayScenarioPage() {
  const { scenarioId = "" } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();

  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState("");
  const [saveAsBusy, setSaveAsBusy] = useState(false);
  const [pendingData, setPendingData] = useState<Record<
    string,
    unknown
  > | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const sc = await getScenario(scenarioId);
        if (cancelled) return;
        await activateScenario(scenarioId).catch(() => undefined);
        if (!cancelled) setScenario(sc);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "加载失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  const meta: ScenarioMeta | null = useMemo(() => {
    if (!scenario) return null;
    return {
      id: scenario.id,
      name: scenario.name,
      isTemplate: scenario.is_template,
      version: scenario.version,
    };
  }, [scenario]);

  const handleSave = useCallback(
    async (data: Record<string, unknown>) => {
      if (!scenario) return;
      if (scenario.is_template) {
        setPendingData(data);
        setSaveAsName(`${scenario.name} 副本`);
        setSaveAsOpen(true);
        return;
      }
      try {
        const updated = await updateScenario(scenario.id, { data });
        setScenario(updated);
      } catch (err) {
        window.alert(err instanceof ApiError ? err.message : "保存失败");
      }
    },
    [scenario]
  );

  const handleRequestSaveAs = useCallback(
    (data: Record<string, unknown>) => {
      setPendingData(data);
      setSaveAsName(scenario ? `${scenario.name} 副本` : "我的想定");
      setSaveAsOpen(true);
    },
    [scenario]
  );

  const handleSaveAsConfirm = async () => {
    if (!pendingData) return;
    const name = saveAsName.trim();
    if (!name) return;
    setSaveAsBusy(true);
    try {
      const created = await createScenario({ name, data: pendingData });
      setSaveAsOpen(false);
      setPendingData(null);
      navigate(`/play/${created.id}`, { replace: true });
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "另存为失败");
    } finally {
      setSaveAsBusy(false);
    }
  };

  const handlePostAar = useCallback(
    async (payload: SaveAarPayload) => {
      if (!scenario) return;
      try {
        await createAarRecord(scenario.id, {
          outcome_reason: payload.outcomeReason,
          winner_side_id: payload.winnerSideId,
          summary: payload.summary,
          ended_at: payload.endedAt,
        });
        if (!scenario.is_template && scenario.status !== "completed") {
          try {
            const promoted = await updateScenario(scenario.id, {
              status: "completed",
            });
            setScenario(promoted);
          } catch {
            // Best-effort status update; AAR save already succeeded.
          }
        }
      } catch {
        // AAR posting is best-effort and should not block the simulation UI.
      }
    },
    [scenario]
  );

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#050812] text-slate-100">
        <Card className="flex items-center gap-3 px-4 py-3 text-xs text-slate-400">
          <Loader2 className="size-4 animate-spin text-cyan-200" />
          正在加载推演工作区
        </Card>
      </div>
    );
  }

  if (error || !scenario || !meta) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#050812] p-4 text-slate-100">
        <Card className="w-full max-w-md p-4">
          <div className="rounded-lg border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs text-red-100">
            {error ?? "想定不存在"}
          </div>
          <Button
            className="mt-3"
            onClick={() => navigate("/scenarios")}
            type="button"
            variant="outline"
          >
            <ArrowLeft className="size-4" />
            返回想定列表
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <>
      <AITacticalCommandPlatform
        key={meta.id}
        scenarioMeta={meta}
        initialScenarioData={scenario.data}
        onSave={handleSave}
        onRequestSaveAs={handleRequestSaveAs}
        onExit={() => navigate("/scenarios")}
        onPostAar={handlePostAar}
      />

      <Dialog
        open={saveAsOpen}
        onOpenChange={(open) => {
          if (!saveAsBusy) setSaveAsOpen(open);
        }}
      >
        <DialogHeader>
          <DialogTitle>另存为新想定</DialogTitle>
          {scenario.is_template ? (
            <DialogDescription>
              系统模板不可直接修改，请另存为自己的想定后继续推演。
            </DialogDescription>
          ) : null}
        </DialogHeader>
        <DialogContent>
          <div className="space-y-3">
            {scenario.is_template ? (
              <div className="rounded-lg border border-cyan-300/12 bg-cyan-300/[0.04] px-3 py-2 text-xs leading-5 text-slate-400">
                模板数据会保留，只创建一个可编辑副本。
              </div>
            ) : null}
            <label className="block space-y-2">
              <span className="text-xs font-medium text-slate-300">
                想定名称
              </span>
              <input
                autoFocus
                className="h-9 w-full rounded-md border border-cyan-300/12 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300/35"
                onChange={(event) => setSaveAsName(event.target.value)}
                value={saveAsName}
              />
            </label>
          </div>
        </DialogContent>
        <DialogFooter>
          <Button
            disabled={saveAsBusy}
            onClick={() => setSaveAsOpen(false)}
            type="button"
            variant="ghost"
          >
            取消
          </Button>
          <Button
            disabled={saveAsBusy || !saveAsName.trim()}
            onClick={handleSaveAsConfirm}
            type="button"
          >
            {saveAsBusy ? "保存中" : "另存为"}
          </Button>
        </DialogFooter>
      </Dialog>
    </>
  );
}
