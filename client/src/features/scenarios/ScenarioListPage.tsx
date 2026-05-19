// 项目管理（"我的想定" + 系统模板）。
//
// 视觉策略：
//   - 顶栏 + 大 banner + 标签页 + 卡片网格/列表，整页保持 cyan HUD 风格。
//   - 每张项目卡片承载：缩略占位 + 名称 + 描述 + 状态 chip + 时间 + 操作。
//   - 复制项目 = 拉详情 -> 以 " 副本" 后缀新建；删除走 dropdown menu。
//   - 缩略图后端无字段，按 (id, status) 算稳定的渐变占位。
//
// 状态推断规则（同 status 字段语义）：
//   draft       新建未推演（卡片描边 cyan）
//   running     已进入推演但未结束（卡片描边 amber）
//   completed   gameOutcome.ended === true（卡片描边 emerald）

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  Bell,
  ChevronDown,
  Clock3,
  Copy as CopyIcon,
  HelpCircle,
  LayoutGrid,
  List as ListIcon,
  LogOut,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Sparkles,
  Star,
  Trash2,
  User as UserIcon,
} from "lucide-react";

import { ApiError } from "@/api/client";
import {
  createScenario,
  deleteScenario,
  getScenario,
  listScenarios,
} from "@/api/scenarios";
import type { ScenarioListItem, ScenarioStatus } from "@/api/types";
import { useAuth } from "@/features/auth/AuthContext";
import { cn } from "@/lib/utils";
import blankScenarioJson from "@/scenarios/blank_scenario.json";

// Use the canonical blank_scenario.json so the stored data always has the
// { currentScenario: {...}, currentSideId, ... } shape that Game.loadScenario
// expects. The old inline object was missing the `currentScenario` wrapper and
// caused an immediate crash when opening a newly-created blank project.
const EMPTY_SCENARIO_DATA = blankScenarioJson as Record<string, unknown>;

const STATUS_META: Record<
  ScenarioStatus,
  { label: string; tone: string; dot: string }
> = {
  draft: {
    label: "草稿",
    tone: "border-cyan-300/30 bg-cyan-300/15 text-cyan-100",
    dot: "bg-cyan-300",
  },
  running: {
    label: "推演中",
    tone: "border-amber-300/30 bg-amber-300/15 text-amber-100",
    dot: "bg-amber-300",
  },
  completed: {
    label: "已完成",
    tone: "border-emerald-300/30 bg-emerald-300/15 text-emerald-100",
    dot: "bg-emerald-300",
  },
};

function statusOf(it: ScenarioListItem): ScenarioStatus {
  // 后端返回的 status 字段是权威来源；保留 fallback 以兼容旧库。
  return (it.status ?? "draft") as ScenarioStatus;
}

function fmtTime(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
  } catch {
    return iso;
  }
}

// 给每张卡片算一个稳定的渐变缩略图（按 id 取色相）。这样列表里看起来每个项目
// 都有"自己的小地图卡片"，但又不需要后端真的存图。
function thumbStyle(id: string, status: ScenarioStatus): React.CSSProperties {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const hue = h % 360;
  const accent = status === "completed" ? 150 : status === "running" ? 35 : 200;
  return {
    backgroundImage: [
      `radial-gradient(120% 80% at 70% 30%, hsla(${accent},80%,55%,0.35), transparent 60%)`,
      `radial-gradient(80% 60% at 25% 80%, hsla(${(hue + 40) % 360},75%,55%,0.30), transparent 60%)`,
      `linear-gradient(135deg, #0a1224 0%, #050914 100%)`,
    ].join(","),
  };
}

type ViewMode = "grid" | "list";

export default function ScenarioListPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [items, setItems] = useState<ScenarioListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [view, setView] = useState<ViewMode>("grid");
  const [search, setSearch] = useState("");

  const [dialogOpen, setDialogOpen] = useState(false);

  // 顶栏头像下拉
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!accountOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!accountRef.current?.contains(e.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [accountOpen]);

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

  const myScenarios = useMemo(
    () => items.filter((it) => !it.is_template),
    [items]
  );
  const templates = useMemo(
    () => items.filter((it) => it.is_template),
    [items]
  );

  const filteredMine = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return myScenarios;
    return myScenarios.filter(
      (it) =>
        it.name.toLowerCase().includes(q) ||
        (it.description || "").toLowerCase().includes(q)
    );
  }, [myScenarios, search]);

  const handleOpen = (id: string) => navigate(`/play/${id}`);

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`确定删除项目「${name}」？此操作不可撤销。`)) return;
    try {
      await deleteScenario(id);
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "删除失败");
    }
  };

  const handleDuplicate = async (it: ScenarioListItem) => {
    try {
      // 拉完整 data 再以副本名 POST 一份。模板复制等同于"以模板新建"。
      const detail = await getScenario(it.id);
      const created = await createScenario({
        name: `${it.name} 副本`,
        description: it.description,
        data: detail.data,
        status: "draft",
      });
      // 直接进入新副本，让用户立即可编辑。
      navigate(`/play/${created.id}`);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "复制失败");
    }
  };

  return (
    <div className="dark min-h-screen bg-[#050914] text-slate-100">
      {/* 顶栏 */}
      <header className="sticky top-0 z-30 border-b border-cyan-300/10 bg-[#050914]/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1500px] items-center gap-4 px-6">
          <div className="flex items-center gap-2">
            <div className="grid size-7 place-items-center rounded-lg border border-cyan-300/30 bg-gradient-to-br from-cyan-400/30 to-sky-500/20 text-cyan-100">
              <Sparkles className="size-4" />
            </div>
            <span className="text-sm font-semibold tracking-wide text-slate-100">
              项目管理
            </span>
          </div>

          <div className="flex-1" />

          <button
            type="button"
            title="通知 (v2 开放)"
            className="grid size-9 place-items-center rounded-full text-slate-400 hover:bg-white/10 hover:text-slate-100"
          >
            <Bell className="size-4" />
          </button>
          <button
            type="button"
            title="帮助"
            className="grid size-9 place-items-center rounded-full text-slate-400 hover:bg-white/10 hover:text-slate-100"
          >
            <HelpCircle className="size-4" />
          </button>

          {/* 头像下拉 */}
          <div ref={accountRef} className="relative">
            <button
              type="button"
              onClick={() => setAccountOpen((v) => !v)}
              className="flex items-center gap-2 rounded-full border border-cyan-300/15 bg-white/[0.03] py-1 pl-1 pr-2 text-xs text-slate-200 hover:border-cyan-300/30 hover:bg-white/[0.07]"
            >
              <span className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-cyan-400/40 to-sky-500/30 text-cyan-50">
                <UserIcon className="size-3.5" />
              </span>
              <span className="max-w-[8rem] truncate">
                {user?.display_name || user?.email || "指挥官"}
              </span>
              <ChevronDown className="size-3.5 text-slate-400" />
            </button>
            {accountOpen && (
              <div className="absolute right-0 top-full mt-2 w-56 overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0a1224] shadow-hud-cyan">
                <div className="border-b border-cyan-300/10 px-3 py-2.5 text-xs">
                  <div className="font-medium text-slate-100">
                    {user?.display_name || "指挥官"}
                  </div>
                  <div className="mt-0.5 truncate text-slate-400">
                    {user?.email}
                  </div>
                  {user?.is_superuser && (
                    <span className="mt-1.5 inline-block rounded-full bg-amber-400/15 px-2 py-0.5 text-[10px] text-amber-200">
                      管理员
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAccountOpen(false);
                    logout();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-200 hover:bg-white/5"
                >
                  <LogOut className="size-3.5 text-slate-400" />
                  退出登录
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-6 pb-12 pt-6">
        {/* Banner */}
        <section
          className="relative overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#0a1224] px-6 py-5 sm:px-8 sm:py-6"
          style={{
            backgroundImage:
              "radial-gradient(60% 120% at 90% 0%, rgba(56,189,248,0.18), transparent 60%), radial-gradient(40% 100% at 0% 100%, rgba(99,102,241,0.18), transparent 60%)",
          }}
        >
          <div className="pointer-events-none absolute inset-0 tactical-grid opacity-40" />
          <div className="relative z-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-wide text-slate-50">
                项目管理
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                创建、管理和协同作战项目，集中查看推演状态与历史
              </p>
            </div>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-400 to-sky-400 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-hud-cyan transition-opacity hover:opacity-95"
            >
              <Plus className="size-4" />
              新建项目
            </button>
          </div>
        </section>

        {/* Tabs + 视图切换 + 搜索 */}
        <section className="mt-6 flex flex-wrap items-center gap-3 border-b border-cyan-300/10 pb-3">
          <div className="relative">
            <span className="px-1 pb-2 text-sm font-semibold text-cyan-200">
              我的项目
              <span className="ml-1.5 text-xs text-slate-500">
                ({filteredMine.length})
              </span>
            </span>
            <span className="absolute inset-x-0 -bottom-[13px] h-[2px] rounded-full bg-gradient-to-r from-cyan-400 to-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />
          </div>
          <span className="px-1 pb-2 text-sm text-slate-500">
            系统模板
            <span className="ml-1.5 text-xs text-slate-600">({templates.length})</span>
          </span>

          <div className="flex-1" />

          <div className="flex items-center gap-2 rounded-xl border border-cyan-300/10 bg-slate-950/40 px-3 py-1.5 text-xs text-slate-300">
            <Search className="size-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="搜索项目"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-40 bg-transparent text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none"
            />
          </div>

          <div className="flex overflow-hidden rounded-xl border border-cyan-300/15 bg-slate-950/40">
            <button
              type="button"
              onClick={() => setView("grid")}
              title="网格视图"
              className={cn(
                "grid size-8 place-items-center transition-colors",
                view === "grid"
                  ? "bg-cyan-400/15 text-cyan-200"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <LayoutGrid className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => setView("list")}
              title="列表视图"
              className={cn(
                "grid size-8 place-items-center transition-colors",
                view === "list"
                  ? "bg-cyan-400/15 text-cyan-200"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <ListIcon className="size-4" />
            </button>
          </div>
        </section>

        {/* 主体 */}
        {error && (
          <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        {loading ? (
          <Skeleton view={view} />
        ) : (
          <>
            <div className="mt-6">
              {filteredMine.length === 0 ? (
                <Empty
                  title="还没有项目"
                  description="点击右上角「新建项目」开始你的第一个推演项目，或选择下方系统模板复制使用。"
                  onAction={() => setDialogOpen(true)}
                />
              ) : view === "grid" ? (
                <CardGrid
                  items={filteredMine}
                  onOpen={handleOpen}
                  onDuplicate={handleDuplicate}
                  onDelete={handleDelete}
                />
              ) : (
                <CardList
                  items={filteredMine}
                  onOpen={handleOpen}
                  onDuplicate={handleDuplicate}
                  onDelete={handleDelete}
                />
              )}
            </div>

            {templates.length > 0 && (
              <div className="mt-12">
                <div className="mb-3 flex items-baseline gap-2">
                  <h2 className="text-sm font-semibold text-slate-200">
                    系统模板
                  </h2>
                  <span className="text-xs text-slate-500">
                    可直接进入预览，或通过「复制」创建为自己的项目
                  </span>
                </div>
                <CardGrid
                  items={templates}
                  isTemplateSection
                  onOpen={handleOpen}
                  onDuplicate={handleDuplicate}
                  onDelete={undefined}
                />
              </div>
            )}
          </>
        )}
      </main>

      {dialogOpen && (
        <CreateScenarioDialog
          templates={templates}
          onClose={() => setDialogOpen(false)}
          onCreated={(id) => {
            setDialogOpen(false);
            navigate(`/play/${id}`);
          }}
        />
      )}
    </div>
  );
}

// ===================== Card Grid / List =====================

interface CardActionProps {
  items: ScenarioListItem[];
  onOpen: (id: string) => void;
  onDuplicate: (it: ScenarioListItem) => void;
  onDelete?: (id: string, name: string) => void;
  isTemplateSection?: boolean;
}

function CardGrid({
  items,
  onOpen,
  onDuplicate,
  onDelete,
  isTemplateSection,
}: CardActionProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {items.map((it) => (
        <ProjectCard
          key={it.id}
          item={it}
          onOpen={() => onOpen(it.id)}
          onDuplicate={() => onDuplicate(it)}
          onDelete={onDelete ? () => onDelete(it.id, it.name) : undefined}
          isTemplateSection={isTemplateSection}
        />
      ))}
    </div>
  );
}

function ProjectCard({
  item,
  onOpen,
  onDuplicate,
  onDelete,
  isTemplateSection,
}: {
  item: ScenarioListItem;
  onOpen: () => void;
  onDuplicate: () => void;
  onDelete?: () => void;
  isTemplateSection?: boolean;
}) {
  const status = statusOf(item);
  const meta = STATUS_META[status];
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-cyan-300/10 bg-[#0a1224]/80 transition-colors hover:border-cyan-300/25">
      {/* 缩略图 */}
      <button
        type="button"
        onClick={onOpen}
        className="relative aspect-[16/10] overflow-hidden text-left"
        style={thumbStyle(item.id, status)}
        title="进入项目"
      >
        <div className="pointer-events-none absolute inset-0 tactical-grid opacity-50" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#050914]/80 via-transparent to-transparent" />
        {/* 收藏 */}
        <span className="absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-black/30 text-slate-300 backdrop-blur transition-colors hover:text-amber-200">
          <Star className="size-3.5" />
        </span>
        {/* 模板 / 状态 chip */}
        <div className="absolute left-2 top-2 flex items-center gap-1.5">
          {isTemplateSection ? (
            <span className="rounded-full border border-amber-300/40 bg-amber-300/15 px-2 py-0.5 text-[10px] font-medium text-amber-100">
              模板
            </span>
          ) : (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                meta.tone
              )}
            >
              <span className={cn("size-1.5 rounded-full", meta.dot)} />
              {meta.label}
            </span>
          )}
        </div>
      </button>

      {/* 内容 */}
      <div className="flex flex-1 flex-col gap-1 px-4 pt-3">
        <div className="text-sm font-semibold text-slate-100 line-clamp-1">
          {item.name}
        </div>
        <div className="text-xs text-slate-400 line-clamp-2 min-h-[2.4em]">
          {item.description || "暂无描述"}
        </div>
        <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <Clock3 className="size-3" /> {fmtTime(item.updated_at)}
          </span>
          <span className="opacity-50">v{item.version}</span>
        </div>
      </div>

      {/* 操作条 */}
      <div className="mt-3 flex items-center gap-1 border-t border-cyan-300/10 px-3 py-2">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-300/10"
        >
          <Play className="size-3.5" />
          进入项目
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5"
        >
          <CopyIcon className="size-3.5" />
          复制项目
        </button>
        <div className="flex-1" />
        {onDelete && (
          <div ref={menuRef} className="relative">
            <button
              type="button"
              title="更多"
              onClick={() => setMenuOpen((v) => !v)}
              className="grid size-7 place-items-center rounded-lg text-slate-400 hover:bg-white/5 hover:text-slate-200"
            >
              <MoreHorizontal className="size-4" />
            </button>
            {menuOpen && (
              <div className="absolute bottom-full right-0 mb-1 w-36 overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0a1224] shadow-hud-cyan">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onDelete();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-red-300 hover:bg-red-500/10"
                >
                  <Trash2 className="size-3.5" />
                  删除项目
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CardList({ items, onOpen, onDuplicate, onDelete }: CardActionProps) {
  return (
    <div className="overflow-hidden rounded-2xl border border-cyan-300/10 bg-[#0a1224]/70">
      <table className="min-w-full text-sm">
        <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">名称</th>
            <th className="px-4 py-2.5 text-left font-medium">描述</th>
            <th className="px-4 py-2.5 text-left font-medium">状态</th>
            <th className="px-4 py-2.5 text-left font-medium">创建时间</th>
            <th className="px-4 py-2.5 text-left font-medium">最近更新</th>
            <th className="px-4 py-2.5 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const meta = STATUS_META[statusOf(it)];
            return (
              <tr
                key={it.id}
                className="border-t border-cyan-300/5 hover:bg-white/[0.02]"
              >
                <td
                  className="px-4 py-3 font-medium text-slate-100 cursor-pointer"
                  onClick={() => onOpen(it.id)}
                >
                  {it.name}
                </td>
                <td className="px-4 py-3 text-xs text-slate-400 max-w-[360px] truncate">
                  {it.description || "—"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                      meta.tone
                    )}
                  >
                    <span className={cn("size-1.5 rounded-full", meta.dot)} />
                    {meta.label}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">
                  {fmtTime(it.created_at)}
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">
                  {fmtTime(it.updated_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onOpen(it.id)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-cyan-200 hover:bg-cyan-300/10"
                    >
                      <Play className="size-3.5" />
                      进入
                    </button>
                    <button
                      type="button"
                      onClick={() => onDuplicate(it)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/5"
                    >
                      <CopyIcon className="size-3.5" />
                      复制
                    </button>
                    {onDelete && (
                      <button
                        type="button"
                        onClick={() => onDelete(it.id, it.name)}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-red-300 hover:bg-red-500/10"
                      >
                        <Trash2 className="size-3.5" />
                        删除
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ===================== Empty / Skeleton =====================

function Empty({
  title,
  description,
  onAction,
}: {
  title: string;
  description: string;
  onAction: () => void;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-cyan-300/15 bg-[#0a1224]/40 px-6 py-14 text-center">
      <div className="grid size-12 place-items-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200">
        <Sparkles className="size-5" />
      </div>
      <div className="mt-4 text-base font-semibold text-slate-100">{title}</div>
      <div className="mt-1 max-w-md text-xs text-slate-400">{description}</div>
      <button
        type="button"
        onClick={onAction}
        className="mt-5 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-400 to-sky-400 px-4 py-2 text-sm font-semibold text-slate-950 shadow-hud-cyan hover:opacity-95"
      >
        <Plus className="size-4" /> 新建项目
      </button>
    </div>
  );
}

function Skeleton({ view }: { view: ViewMode }) {
  if (view === "list") {
    return (
      <div className="mt-6 overflow-hidden rounded-2xl border border-cyan-300/10 bg-[#0a1224]/40">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-4 border-b border-cyan-300/5 px-4 py-4 last:border-0"
          >
            <div className="h-3 w-32 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-48 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-16 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-24 animate-pulse rounded bg-white/5" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="overflow-hidden rounded-2xl border border-cyan-300/10 bg-[#0a1224]/60"
        >
          <div className="aspect-[16/10] animate-pulse bg-white/5" />
          <div className="space-y-2 p-4">
            <div className="h-3 w-2/3 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-full animate-pulse rounded bg-white/5" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-white/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ===================== Create Dialog =====================

function CreateScenarioDialog({
  templates,
  onClose,
  onCreated,
}: {
  templates: ScenarioListItem[];
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState<string>("__blank__");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("项目名称为必填");
      return;
    }
    setSubmitting(true);
    try {
      // Deep-clone so we can set currentScenario.name without mutating the
      // cached import. The internal game name must match the project name so
      // the tactical HUD overlay doesn't show the template's original name.
      let data: Record<string, unknown> = JSON.parse(
        JSON.stringify(EMPTY_SCENARIO_DATA)
      ) as Record<string, unknown>;
      if (templateId !== "__blank__") {
        const tpl = await getScenario(templateId);
        data = JSON.parse(JSON.stringify(tpl.data)) as Record<string, unknown>;
      }
      const cs = (data as { currentScenario?: Record<string, unknown> })
        .currentScenario;
      if (cs) cs.name = name.trim();
      const created = await createScenario({
        name: name.trim(),
        description: description.trim(),
        status: "draft",
        data,
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-md rounded-2xl border border-cyan-300/15 bg-[#0a1224] p-6 shadow-hud-cyan"
      >
        <div className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-xl border border-cyan-300/25 bg-cyan-300/10 text-cyan-200">
            <Plus className="size-4" />
          </span>
          <div>
            <div className="text-base font-semibold text-slate-100">
              新建项目
            </div>
            <div className="text-xs text-slate-400">
              基于模板创建一个新的推演项目
            </div>
          </div>
        </div>

        <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-xs text-slate-400">
              项目名称 <span className="text-red-400">*</span>
            </label>
            <input
              autoFocus
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：东海防空压力分析推演"
              className="w-full rounded-xl border border-cyan-300/15 bg-slate-950/50 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-300/40 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-400">
              项目描述（可选）
            </label>
            <textarea
              rows={3}
              maxLength={500}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要说明本项目的推演目标、想定背景"
              className="w-full resize-none rounded-xl border border-cyan-300/15 bg-slate-950/50 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-300/40 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-400">
              基于模板
            </label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full rounded-xl border border-cyan-300/15 bg-slate-950/50 px-3 py-2.5 text-sm text-slate-100 focus:border-cyan-300/40 focus:outline-none"
            >
              <option value="__blank__">空白项目（无单位）</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-xl px-4 py-2 text-sm text-slate-300 hover:bg-white/5"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-400 to-sky-400 px-4 py-2 text-sm font-semibold text-slate-950 shadow-hud-cyan transition-opacity hover:opacity-95 disabled:opacity-60"
            >
              {submitting ? "创建中…" : "创建并进入"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

