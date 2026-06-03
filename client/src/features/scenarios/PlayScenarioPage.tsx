// Wraps the tactical platform with a `scenarioId` route param.
//
// Fetches the scenario JSON from the API once, then hands it to
// AITacticalCommandPlatform via props together with save / save-as / aar-post
// callbacks. The tactical platform itself stays oblivious to the API layer.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import { ApiError } from "@/api/client";
import {
  activateScenario,
  createAarRecord,
  createScenario,
  getScenario,
  updateScenario,
} from "@/api/scenarios";
import type { ScenarioDetail } from "@/api/types";
import AITacticalCommandPlatform, {
  type ScenarioMeta,
  type SaveAarPayload,
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
  // The tactical platform calls onRequestSaveAs with the latest JSON. We hold
  // it in state so the dialog can submit it once the user confirms a name.
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

        // 把 DB 想定同步进后端 runtime，让 MCP 工具和 /api/ai/command
        // 操作的是当前打开的项目，而不是默认的 SCS 场景。best-effort。
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
        // Read-only: bubble up a save-as request so the platform can route to
        // the dialog below.
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
        // 一局结束 -> 项目状态 completed（仅本人项目）。
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
      <Box
        sx={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (error || !scenario || !meta) {
    return (
      <Box sx={{ p: 4 }}>
        <Stack spacing={2} sx={{ maxWidth: 480 }}>
          <Alert severity="error">{error ?? "想定不存在"}</Alert>
          <Button
            variant="outlined"
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate("/scenarios")}
          >
            返回想定列表
          </Button>
        </Stack>
      </Box>
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
        onClose={() => (saveAsBusy ? null : setSaveAsOpen(false))}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>另存为新想定</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {scenario.is_template && (
              <Typography variant="body2" color="text.secondary">
                系统模板不可直接修改,请另存为属于您自己的想定。
              </Typography>
            )}
            <TextField
              label="想定名称"
              autoFocus
              fullWidth
              value={saveAsName}
              onChange={(e) => setSaveAsName(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveAsOpen(false)} disabled={saveAsBusy}>
            取消
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveAsConfirm}
            disabled={saveAsBusy || !saveAsName.trim()}
          >
            {saveAsBusy ? "保存中…" : "另存为"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
