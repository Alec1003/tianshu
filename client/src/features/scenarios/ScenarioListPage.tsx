// "我的想定" + 系统模板列表入口。

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  MenuItem,
  Select,
  Stack,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import LogoutIcon from "@mui/icons-material/Logout";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import StarIcon from "@mui/icons-material/Star";

import { ApiError } from "@/api/client";
import {
  createScenario,
  deleteScenario,
  getScenario,
  listScenarios,
} from "@/api/scenarios";
import type { ScenarioListItem } from "@/api/types";
import { useAuth } from "@/features/auth/AuthContext";

const EMPTY_SCENARIO_DATA: Record<string, unknown> = {
  // Minimal valid scenario shape consistent with client/src/scenarios/blank_scenario.json
  // We keep this here so the "new blank" button works even when seeding hasn't
  // run yet. The real blank template (with full defaults) will overwrite it
  // when the user creates from the template card.
  id: "",
  name: "",
  startTime: 1699073110,
  currentTime: 1699073110,
  duration: 14400,
  sides: [],
  aircraft: [],
  ships: [],
  facilities: [],
  airbases: [],
  weapons: [],
  referencePoints: [],
  missions: [],
  relationships: { hostiles: {}, allies: {} },
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ScenarioListPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [items, setItems] = useState<ScenarioListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogName, setDialogName] = useState("");
  const [dialogTemplateId, setDialogTemplateId] = useState<string>("__blank__");
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listScenarios(true);
      setItems(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const templates = useMemo(() => items.filter((it) => it.is_template), [items]);
  const myScenarios = useMemo(
    () => items.filter((it) => !it.is_template),
    [items]
  );

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`确定删除想定「${name}」?此操作不可撤销。`)) return;
    try {
      await deleteScenario(id);
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "删除失败");
    }
  };

  const handleCreate = async () => {
    const name = dialogName.trim();
    if (!name) return;
    setCreating(true);
    try {
      let data: Record<string, unknown> = EMPTY_SCENARIO_DATA;
      if (dialogTemplateId !== "__blank__") {
        // Fork from template: pull full JSON then strip the embedded id so the
        // backend assigns a fresh one.
        const tpl = await getScenario(dialogTemplateId);
        data = { ...tpl.data, name };
      }
      const created = await createScenario({ name, data });
      setDialogOpen(false);
      setDialogName("");
      setDialogTemplateId("__blank__");
      navigate(`/play/${created.id}`);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", backgroundColor: "#f7f9fc" }}>
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar sx={{ gap: 1 }}>
          <Typography variant="h6" sx={{ flex: 1, fontWeight: 600 }}>
            AICC 想定中心
          </Typography>
          <Typography variant="body2" sx={{ mr: 2, color: "text.secondary" }}>
            {user?.display_name || user?.email}
            {user?.is_superuser ? " · 管理员" : ""}
          </Typography>
          <IconButton onClick={logout} title="退出登录">
            <LogoutIcon />
          </IconButton>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack
          direction="row"
          spacing={2}
          sx={{ mb: 3, alignItems: "center" }}
        >
          <Typography variant="h5" sx={{ flex: 1, fontWeight: 600 }}>
            想定管理
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialogOpen(true)}
          >
            新建想定
          </Button>
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress />
          </Box>
        ) : (
          <Stack spacing={4}>
            <Section
              title="我的想定"
              empty="还没有想定，点击右上角「新建想定」开始"
              items={myScenarios}
              onOpen={(id) => navigate(`/play/${id}`)}
              onDelete={handleDelete}
            />
            <Divider />
            <Section
              title="系统模板"
              empty="暂无系统模板"
              items={templates}
              onOpen={(id) => navigate(`/play/${id}`)}
              templateBadge
            />
          </Stack>
        )}
      </Container>

      <Dialog
        open={dialogOpen}
        onClose={() => (creating ? null : setDialogOpen(false))}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>新建想定</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            <TextField
              label="想定名称"
              autoFocus
              fullWidth
              value={dialogName}
              onChange={(e) => setDialogName(e.target.value)}
            />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                以模板为基础
              </Typography>
              <Select
                fullWidth
                value={dialogTemplateId}
                onChange={(e) => setDialogTemplateId(String(e.target.value))}
              >
                <MenuItem value="__blank__">空白想定(无单位)</MenuItem>
                {templates.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.name}
                  </MenuItem>
                ))}
              </Select>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDialogOpen(false)}
            disabled={creating}
          >
            取消
          </Button>
          <Button
            variant="contained"
            onClick={handleCreate}
            disabled={creating || !dialogName.trim()}
          >
            {creating ? "创建中…" : "创建并进入"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

interface SectionProps {
  title: string;
  empty: string;
  items: ScenarioListItem[];
  onOpen: (id: string) => void;
  onDelete?: (id: string, name: string) => void;
  templateBadge?: boolean;
}

function Section({ title, empty, items, onOpen, onDelete, templateBadge }: SectionProps) {
  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 600 }}>
        {title}
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {empty}
        </Typography>
      ) : (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(2, 1fr)",
              md: "repeat(3, 1fr)",
            },
            gap: 2,
          }}
        >
          {items.map((it) => (
            <Card key={it.id} sx={{ position: "relative" }}>
              <CardActionArea onClick={() => onOpen(it.id)}>
                <CardContent>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                    {templateBadge && (
                      <Chip
                        icon={<StarIcon sx={{ fontSize: 14 }} />}
                        label="模板"
                        size="small"
                        color="warning"
                        sx={{ height: 22 }}
                      />
                    )}
                    <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
                      {it.name}
                    </Typography>
                  </Stack>
                  {it.description && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        mb: 1,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {it.description}
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    更新时间 {formatTime(it.updated_at)} · v{it.version}
                  </Typography>
                </CardContent>
              </CardActionArea>
              <Stack
                direction="row"
                spacing={0.5}
                sx={{ position: "absolute", right: 8, bottom: 8 }}
              >
                <Button
                  size="small"
                  startIcon={<PlayArrowIcon />}
                  onClick={() => onOpen(it.id)}
                >
                  打开
                </Button>
                {onDelete && (
                  <IconButton
                    size="small"
                    color="error"
                    onClick={() => onDelete(it.id, it.name)}
                    title="删除"
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </Stack>
            </Card>
          ))}
        </Box>
      )}
    </Box>
  );
}
