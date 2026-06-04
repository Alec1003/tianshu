import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEvent,
  type Dispatch,
  type FormEvent,
  type RefObject,
  type SetStateAction,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  Box,
  BrainCircuit,
  ChevronDown,
  Clock3,
  Copy as CopyIcon,
  Database,
  Edit3,
  Eye,
  FileInput,
  FolderKanban,
  LayoutGrid,
  List as ListIcon,
  LogOut,
  Map,
  MoreHorizontal,
  PackageOpen,
  Play,
  Plus,
  Radar,
  Sparkles,
  Star,
  Trash2,
  UploadCloud,
  User as UserIcon,
  Users,
  Waves,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { AppShell, type AppShellNavItem } from "@/components/layout/AppShell";
import {
  createScenario,
  deleteScenario,
  getScenario,
  listScenarios,
} from "@/api/scenarios";
import {
  createUnitAsset,
  deleteUnitAsset,
  generateUnitAsset,
  importUnitAssets,
  listUnitAssets,
  resetUnitAssets,
  updateUnitAsset,
} from "@/api/unitAssets";
import type {
  ScenarioListItem,
  ScenarioStatus,
  UnitAsset as ApiUnitAsset,
  UnitAssetCreatePayload,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/ui/search-input";
import { StatCard } from "@/components/ui/stat-card";
import { TabButton, Tabs } from "@/components/ui/tabs";
import { Toolbar, ToolbarGroup } from "@/components/ui/toolbar";
import { useAuth } from "@/features/auth/useAuth";
import Dba from "@/game/db/Dba";
import type { IAircraftModel } from "@/game/db/models/Aircraft";
import type { IAirbaseModel } from "@/game/db/models/Airbase";
import type { IFacilityModel } from "@/game/db/models/Facility";
import type { IShipModel } from "@/game/db/models/Ship";
import type { IWeaponModel } from "@/game/db/models/Weapon";
import { dbaToCatalog, unitAssetsToDba } from "@/game/db/unitAssetCatalog";
import {
  SetUnitDbContext,
  UnitDbContext,
} from "@/gui/contextProviders/contexts/UnitDbContext";
import { localizeUnitAssetName } from "@/i18n/entityNames";
import { cn } from "@/lib/utils";
import blankScenarioJson from "@/scenarios/blank_scenario.json";
import { projectMetrics } from "./scenarioMetrics";

const EMPTY_SCENARIO_DATA = blankScenarioJson as Record<string, unknown>;

type ViewMode = "grid" | "list";
type WorkspaceModule = "projects" | "templates" | "assets";
type VisualStatus = "live" | "simulation" | "draft" | "archived";
type UnitAssetType = "aircraft" | "ship" | "facility" | "airbase" | "weapon";
type UnitAssetRecord = {
  id: string;
  assetId: string;
  type: UnitAssetType;
  typeLabel: string;
  name: string;
  role: string;
  primaryMetric: string;
  secondaryMetric: string;
  status: string;
  isSystem: boolean;
  version: number;
  updatedAt: string;
  searchable: string;
  canonicalName?: string;
  raw:
    | IAircraftModel
    | IShipModel
    | IFacilityModel
    | IAirbaseModel
    | IWeaponModel;
};

const MODULES: Array<{
  id: WorkspaceModule;
  label: string;
  caption: string;
  icon: typeof FolderKanban;
}> = [
  {
    id: "projects",
    label: "项目管理",
    caption: "Projects",
    icon: FolderKanban,
  },
  {
    id: "templates",
    label: "模板中心",
    caption: "Template Hub",
    icon: PackageOpen,
  },
  {
    id: "assets",
    label: "数据资产",
    caption: "Data Assets",
    icon: Database,
  },
];

const MODULE_COPY: Record<
  WorkspaceModule,
  { title: string; subtitle: string; eyebrow: string }
> = {
  projects: {
    title: "项目管理",
    subtitle: "AI 驱动的仿真工作空间，创建、管理和运行你的战术场景。",
    eyebrow: "AI Tactical Workspace",
  },
  templates: {
    title: "模板中心",
    subtitle: "仅保存和浏览可复用推演模板，保持模板资产干净、稳定、可复用。",
    eyebrow: "Template Intelligence",
  },
  assets: {
    title: "数据资产",
    subtitle:
      "统一维护平台单位库，集中管理飞机、舰艇、地面设施、机场与武器模型。",
    eyebrow: "Unit Asset Registry",
  },
};

const VISUAL_STATUS_META: Record<
  VisualStatus,
  {
    label: string;
    tone: string;
    dot: string;
    accent: string;
    glow: string;
    action: string;
  }
> = {
  live: {
    label: "LIVE",
    tone: "border-emerald-300/35 bg-emerald-400/15 text-emerald-100",
    dot: "bg-emerald-300",
    accent: "emerald",
    glow: "rgba(16,185,129,0.34)",
    action: "继续推演",
  },
  simulation: {
    label: "SIMULATION",
    tone: "border-sky-300/35 bg-sky-400/15 text-sky-100",
    dot: "bg-sky-300",
    accent: "sky",
    glow: "rgba(14,165,233,0.32)",
    action: "继续推演",
  },
  draft: {
    label: "DRAFT",
    tone: "border-amber-300/35 bg-amber-400/15 text-amber-100",
    dot: "bg-amber-300",
    accent: "amber",
    glow: "rgba(245,158,11,0.28)",
    action: "编辑项目",
  },
  archived: {
    label: "ARCHIVED",
    tone: "border-slate-300/25 bg-slate-300/10 text-slate-200",
    dot: "bg-slate-300",
    accent: "slate",
    glow: "rgba(148,163,184,0.22)",
    action: "查看详情",
  },
};

const STATUS_META: Record<
  ScenarioStatus,
  { label: string; tone: string; dot: string }
> = {
  draft: {
    label: "草稿",
    tone: "border-amber-300/30 bg-amber-300/15 text-amber-100",
    dot: "bg-amber-300",
  },
  running: {
    label: "推演中",
    tone: "border-sky-300/30 bg-sky-300/15 text-sky-100",
    dot: "bg-sky-300",
  },
  completed: {
    label: "已归档",
    tone: "border-slate-300/25 bg-slate-300/10 text-slate-200",
    dot: "bg-slate-300",
  },
};

const UNIT_ASSET_TYPES: Array<{
  id: UnitAssetType | "all";
  label: string;
  icon: typeof BrainCircuit;
  tone: string;
}> = [
  {
    id: "all",
    label: "全部单位",
    icon: Database,
    tone: "from-cyan-400/20 to-blue-500/10",
  },
  {
    id: "aircraft",
    label: "飞机",
    icon: BrainCircuit,
    tone: "from-sky-400/20 to-blue-500/10",
  },
  {
    id: "ship",
    label: "舰艇",
    icon: Waves,
    tone: "from-cyan-400/18 to-teal-500/10",
  },
  {
    id: "facility",
    label: "地面设施",
    icon: Radar,
    tone: "from-emerald-400/18 to-cyan-500/10",
  },
  {
    id: "airbase",
    label: "机场",
    icon: Map,
    tone: "from-violet-400/18 to-blue-500/10",
  },
  {
    id: "weapon",
    label: "武器",
    icon: Activity,
    tone: "from-amber-400/18 to-red-500/10",
  },
];

function setScenarioClockToNow(data: Record<string, unknown>) {
  const currentScenario = data.currentScenario as
    | Record<string, unknown>
    | undefined;
  if (!currentScenario) return;
  const now = Math.floor(Date.now() / 1000);
  currentScenario.startTime = now;
  currentScenario.currentTime = now;
}

function cloneScenarioData(name: string): Record<string, unknown> {
  const data = JSON.parse(JSON.stringify(EMPTY_SCENARIO_DATA)) as Record<
    string,
    unknown
  >;
  const currentScenario = data.currentScenario as
    | Record<string, unknown>
    | undefined;
  if (currentScenario) currentScenario.name = name;
  setScenarioClockToNow(data);
  return data;
}

function statusOf(item: ScenarioListItem): ScenarioStatus {
  return (item.status ?? "draft") as ScenarioStatus;
}

function visualStatusOf(
  item: ScenarioListItem,
  index: number,
  isTemplateSection?: boolean
): VisualStatus {
  if (isTemplateSection) return "archived";
  const status = statusOf(item);
  if (status === "running") return index === 0 ? "live" : "simulation";
  if (status === "completed") return "archived";
  return index === 0 ? "live" : "draft";
}

function hashString(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) {
    h = (h * 31 + input.charCodeAt(i)) >>> 0;
  }
  return h;
}

function relativeTime(iso: string): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "刚刚更新";
  const diff = Date.now() - time;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "刚刚更新";
  if (diff < hour)
    return `${Math.max(1, Math.floor(diff / minute))} 分钟前更新`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前更新`;
  if (diff < day * 14) return `${Math.floor(diff / day)} 天前更新`;
  return new Date(iso).toLocaleDateString();
}

function thumbStyle(id: string, status: VisualStatus): CSSProperties {
  const h = hashString(id);
  const hue = status === "draft" ? 42 : status === "archived" ? 218 : h % 360;
  const accent =
    status === "live"
      ? 156
      : status === "simulation"
        ? 202
        : status === "draft"
          ? 38
          : 220;
  return {
    backgroundColor: "#07111d",
    borderColor: `hsla(${accent},90%,58%,0.18)`,
  };
}

export default function ScenarioListPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const unitDb = useContext(UnitDbContext);

  const [items, setItems] = useState<ScenarioListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("grid");
  const [query, setQuery] = useState("");
  const [activeModule, setActiveModule] = useState<WorkspaceModule>("projects");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!accountOpen) return;
    const onDoc = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) {
        setAccountOpen(false);
      }
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
      setError(err instanceof ApiError ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const myScenarios = useMemo(
    () => items.filter((item) => !item.is_template),
    [items]
  );
  const templates = useMemo(
    () => items.filter((item) => item.is_template),
    [items]
  );
  const unitAssetCount =
    unitDb.getAircraftDb().length +
    unitDb.getShipDb().length +
    unitDb.getFacilityDb().length +
    unitDb.getAirbaseDb().length +
    unitDb.getWeaponDb().length;

  const moduleItems = useMemo(() => {
    if (activeModule === "templates") return templates;
    if (activeModule === "assets") return [];
    return myScenarios;
  }, [activeModule, myScenarios, templates]);

  const queryText = query.trim().toLowerCase();
  const filteredItems = useMemo(() => {
    if (!queryText) return moduleItems;
    return moduleItems.filter((item) =>
      [
        item.name,
        item.description,
        item.status,
        item.owner_id,
        item.created_at,
        item.updated_at,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(queryText)
    );
  }, [moduleItems, queryText]);

  const activeCopy = MODULE_COPY[activeModule];
  const activeModuleLabel =
    MODULES.find((module) => module.id === activeModule)?.label ?? "项目管理";
  const isProjectWorkspace = activeModule === "projects";
  const isTemplateWorkspace = activeModule === "templates";
  const shellNavItems = useMemo<AppShellNavItem[]>(
    () =>
      MODULES.map((module) => ({
        id: module.id,
        label: module.label,
        caption: module.caption,
        icon: module.icon,
        badge:
          module.id === "projects"
            ? myScenarios.length
            : module.id === "templates"
              ? templates.length
              : unitAssetCount,
      })),
    [myScenarios.length, templates.length, unitAssetCount]
  );
  const runningCount = useMemo(
    () => myScenarios.filter((item) => statusOf(item) === "running").length,
    [myScenarios]
  );
  const completedCount = useMemo(
    () => myScenarios.filter((item) => statusOf(item) === "completed").length,
    [myScenarios]
  );

  const handleOpen = (id: string) => navigate(`/play/${id}`);

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`确定删除项目「${name}」？此操作不可撤销。`)) return;
    try {
      await deleteScenario(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "删除失败");
    }
  };

  const handleDuplicate = async (item: ScenarioListItem) => {
    try {
      const source = await getScenario(item.id);
      const copyName = `${item.name} 副本`;
      const data = JSON.parse(JSON.stringify(source.data)) as Record<
        string,
        unknown
      >;
      const currentScenario = data.currentScenario as
        | Record<string, unknown>
        | undefined;
      if (currentScenario) currentScenario.name = copyName;
      const created = await createScenario({
        name: copyName,
        description: item.description,
        data,
        status: "draft",
      });
      navigate(`/play/${created.id}`);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "复制失败");
    }
  };

  return (
    <AppShell
      activeNavItem={activeModule}
      actions={
        isProjectWorkspace ? (
          <Button onClick={() => setDialogOpen(true)} type="button">
            <Plus className="size-4" />
            新建项目
          </Button>
        ) : null
      }
      description={activeCopy.subtitle}
      eyebrow={activeCopy.eyebrow}
      navItems={shellNavItems}
      onNavItemSelect={(id) => {
        setActiveModule(id as WorkspaceModule);
        setQuery("");
      }}
      rightPanel={
        activeModule === "assets" ? undefined : (
          <WorkspaceDetailPanel
            isTemplateSection={isTemplateWorkspace}
            items={filteredItems}
            onCreate={
              isProjectWorkspace ? () => setDialogOpen(true) : undefined
            }
            onOpen={handleOpen}
          />
        )
      }
      title={activeCopy.title}
      topRight={
        <AccountMenu
          userEmail={user?.email}
          displayName={user?.display_name || user?.email || "Operator"}
          isSuperuser={Boolean(user?.is_superuser)}
          accountOpen={accountOpen}
          setAccountOpen={setAccountOpen}
          accountRef={accountRef}
          onLogout={logout}
        />
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <StatCard
            caption="本地可编辑工作项"
            icon={FolderKanban}
            label="自定义项目"
            tone="cyan"
            value={myScenarios.length}
          />
          <StatCard
            caption="后端系统模板"
            icon={PackageOpen}
            label="系统模板"
            tone="slate"
            value={templates.length}
          />
          <StatCard
            caption="平台单位库"
            icon={Database}
            label="单位资产"
            tone="green"
            value={unitAssetCount}
          />
          <StatCard
            caption={`${completedCount} 已归档`}
            icon={Activity}
            label="运行中"
            tone="amber"
            value={runningCount}
          />
        </div>

        {error && (
          <div className="rounded-lg border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs text-red-100">
            {error}
          </div>
        )}

        <Card className="p-3">
          <Toolbar className="border-0 bg-transparent p-0">
            <ToolbarGroup>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-slate-100">
                    {activeModuleLabel}
                  </h2>
                  <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-slate-500">
                    {activeModule === "assets"
                      ? unitAssetCount
                      : filteredItems.length}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {activeModule === "assets"
                    ? "管理飞机、舰艇、设施、机场与武器数据。"
                    : "搜索、筛选并打开推演工作项。"}
                </p>
              </div>
            </ToolbarGroup>
            <ToolbarGroup>
              {activeModule !== "assets" && (
                <SearchInput
                  className="w-full sm:w-64"
                  onChange={(event) => setQuery(event.target.value)}
                  onClear={() => setQuery("")}
                  placeholder="搜索名称、状态、描述"
                  value={query}
                />
              )}
              <select
                value={activeModule}
                onChange={(event) => {
                  setActiveModule(event.target.value as WorkspaceModule);
                  setQuery("");
                }}
                className="h-9 rounded-md border border-cyan-300/12 bg-slate-950/60 px-2.5 text-xs text-slate-300 outline-none focus:border-cyan-300/35"
              >
                {MODULES.map((module) => (
                  <option key={module.id} value={module.id}>
                    {module.label}
                  </option>
                ))}
              </select>
              {activeModule !== "assets" && (
                <Tabs>
                  <TabButton
                    active={view === "grid"}
                    onClick={() => setView("grid")}
                    title="网格视图"
                  >
                    <LayoutGrid className="size-4" />
                  </TabButton>
                  <TabButton
                    active={view === "list"}
                    onClick={() => setView("list")}
                    title="列表视图"
                  >
                    <ListIcon className="size-4" />
                  </TabButton>
                </Tabs>
              )}
            </ToolbarGroup>
          </Toolbar>

          <div className="mt-4">
            {loading ? (
              <Skeleton view={view} />
            ) : activeModule === "assets" ? (
              <DataAssetWorkspace />
            ) : filteredItems.length === 0 ? (
              <Empty
                title={
                  isTemplateWorkspace ? "暂无匹配模板" : "没有匹配的工作项"
                }
                description={
                  isTemplateWorkspace
                    ? "调整搜索条件，或等待管理员沉淀新的推演模板。"
                    : "调整搜索条件，或新建一个推演项目开始构建你的 AI 战术工作空间。"
                }
                onAction={
                  isTemplateWorkspace ? undefined : () => setDialogOpen(true)
                }
              />
            ) : view === "grid" ? (
              <ProjectGrid
                items={filteredItems}
                isTemplateSection={isTemplateWorkspace}
                onOpen={handleOpen}
                onDuplicate={isTemplateWorkspace ? undefined : handleDuplicate}
                onDelete={isTemplateWorkspace ? undefined : handleDelete}
              />
            ) : (
              <ProjectList
                items={filteredItems}
                isTemplateSection={isTemplateWorkspace}
                onOpen={handleOpen}
                onDuplicate={isTemplateWorkspace ? undefined : handleDuplicate}
                onDelete={isTemplateWorkspace ? undefined : handleDelete}
              />
            )}
          </div>
        </Card>
      </div>

      {dialogOpen && (
        <CreateScenarioDialog
          onClose={() => setDialogOpen(false)}
          onCreated={(id) => {
            setDialogOpen(false);
            navigate(`/play/${id}`);
          }}
        />
      )}
    </AppShell>
  );
}

function AccountMenu({
  userEmail,
  displayName,
  isSuperuser,
  accountOpen,
  setAccountOpen,
  accountRef,
  onLogout,
}: {
  userEmail?: string;
  displayName: string;
  isSuperuser: boolean;
  accountOpen: boolean;
  setAccountOpen: Dispatch<SetStateAction<boolean>>;
  accountRef: RefObject<HTMLDivElement>;
  onLogout: () => void;
}) {
  return (
    <div ref={accountRef} className="relative">
      <button
        type="button"
        onClick={() => setAccountOpen((value) => !value)}
        className="flex h-9 items-center gap-2 rounded-md border border-cyan-300/12 bg-slate-950/55 px-2 text-xs text-slate-100 transition-colors hover:border-cyan-300/25 hover:bg-white/[0.045]"
      >
        <span className="grid size-7 place-items-center rounded-full border border-cyan-300/12 bg-cyan-300/10 text-cyan-100">
          <UserIcon className="size-4" />
        </span>
        <span className="hidden max-w-[9rem] truncate md:block">
          {displayName}
        </span>
        <ChevronDown className="size-4 text-slate-500" />
      </button>

      {accountOpen && (
        <div className="absolute right-0 top-full mt-2 w-64 overflow-hidden rounded-lg border border-cyan-300/14 bg-[#08111c] shadow-[0_10px_28px_rgba(0,0,0,0.34)]">
          <div className="border-b border-cyan-200/10 px-4 py-3 text-sm">
            <div className="font-medium text-slate-100">{displayName}</div>
            <div className="mt-1 truncate text-xs text-slate-500">
              {userEmail}
            </div>
            {isSuperuser && (
              <span className="mt-2 inline-flex rounded-full border border-amber-300/25 bg-amber-300/10 px-2 py-0.5 text-[10px] text-amber-200">
                管理员
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              setAccountOpen(false);
              onLogout();
            }}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-slate-300 hover:bg-white/[0.04]"
          >
            <LogOut className="size-4 text-slate-500" />
            退出登录
          </button>
        </div>
      )}
    </div>
  );
}

interface ProjectActions {
  items: ScenarioListItem[];
  onOpen: (id: string) => void;
  onDuplicate?: (item: ScenarioListItem) => void;
  onDelete?: (id: string, name: string) => void;
  isTemplateSection?: boolean;
}

function ProjectGrid({
  items,
  onOpen,
  onDuplicate,
  onDelete,
  isTemplateSection,
}: ProjectActions) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-4">
      {items.map((item, index) => (
        <ProjectCard
          key={item.id}
          item={item}
          index={index}
          onOpen={() => onOpen(item.id)}
          onDuplicate={onDuplicate ? () => onDuplicate(item) : undefined}
          onDelete={onDelete ? () => onDelete(item.id, item.name) : undefined}
          isTemplateSection={isTemplateSection}
        />
      ))}
    </div>
  );
}

function ProjectCard({
  item,
  index,
  onOpen,
  onDuplicate,
  onDelete,
  isTemplateSection,
}: {
  item: ScenarioListItem;
  index: number;
  onOpen: () => void;
  onDuplicate?: () => void;
  onDelete?: () => void;
  isTemplateSection?: boolean;
}) {
  const visualStatus = visualStatusOf(item, index, isTemplateSection);
  const visualMeta = VISUAL_STATUS_META[visualStatus];
  const metrics = projectMetrics(item);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  return (
    <Card
      className={cn(
        "group relative overflow-hidden rounded-lg bg-[#08111c] transition-colors",
        "border-cyan-200/10 hover:border-cyan-200/30"
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="relative block aspect-[16/9] w-full overflow-hidden text-left"
        style={thumbStyle(item.id, visualStatus)}
      >
        <MapThumbnail status={visualStatus} />
        <div className="absolute left-3 top-3">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-wide",
              visualMeta.tone
            )}
          >
            <span className={cn("size-1.5 rounded-full", visualMeta.dot)} />
            {visualMeta.label}
          </span>
        </div>
        <span className="absolute right-3 top-3 grid size-8 place-items-center rounded-md border border-white/10 bg-slate-950/70 text-slate-300 transition-colors hover:text-amber-200">
          <Star className="size-4" />
        </span>
      </button>

      <div className="relative px-4 pb-4 pt-3">
        <div className="text-sm font-semibold text-white line-clamp-1">
          {item.name}
        </div>
        <p className="mt-1 min-h-[2.5rem] text-xs leading-5 text-slate-500 line-clamp-2">
          {item.description ||
            "暂无描述，可进入项目继续配置目标、任务与推演参数。"}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1">
            <Activity className="size-3.5" />
            {metrics.tasks} 任务
          </span>
          <span className="inline-flex items-center gap-1">
            <Map className="size-3.5" />
            {metrics.units} 单位
          </span>
          <span className="inline-flex items-center gap-1">
            <Users className="size-3.5" />
            {metrics.sides} 阵营
          </span>
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-cyan-200/10 pt-3">
          <span className="mr-auto text-xs text-slate-500">
            {relativeTime(item.updated_at)}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onOpen}
            className="h-8 rounded-md border border-cyan-200/10 bg-cyan-200/[0.04] px-3 text-cyan-100 hover:bg-cyan-200/[0.08]"
          >
            <Play className="size-3.5" />
            {visualMeta.action}
          </Button>
          <div ref={menuRef} className="relative">
            <button
              type="button"
              title="更多操作"
              onClick={() => setMenuOpen((value) => !value)}
              className="grid size-8 place-items-center rounded-md text-slate-500 hover:bg-white/[0.06] hover:text-slate-200"
            >
              <MoreHorizontal className="size-4" />
            </button>
            {menuOpen && (
              <ProjectMenu
                onOpen={onOpen}
                onDuplicate={onDuplicate}
                onDelete={onDelete}
                close={() => setMenuOpen(false)}
              />
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function ProjectMenu({
  onOpen,
  onDuplicate,
  onDelete,
  close,
}: {
  onOpen: () => void;
  onDuplicate?: () => void;
  onDelete?: () => void;
  close: () => void;
}) {
  return (
    <div className="absolute bottom-full right-0 z-20 mb-2 w-40 overflow-hidden rounded-lg border border-cyan-200/15 bg-[#08111c] shadow-[0_10px_28px_rgba(0,0,0,0.34)]">
      <button
        type="button"
        onClick={() => {
          close();
          onOpen();
        }}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-200 hover:bg-white/[0.05]"
      >
        <Eye className="size-3.5 text-cyan-200" />
        查看详情
      </button>
      {onDuplicate && (
        <button
          type="button"
          onClick={() => {
            close();
            onDuplicate();
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-200 hover:bg-white/[0.05]"
        >
          <CopyIcon className="size-3.5 text-slate-400" />
          复制项目
        </button>
      )}
      {onDelete && (
        <button
          type="button"
          onClick={() => {
            close();
            onDelete();
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-red-300 hover:bg-red-500/10"
        >
          <Trash2 className="size-3.5" />
          删除项目
        </button>
      )}
    </div>
  );
}

function MapThumbnail({ status }: { status: VisualStatus }) {
  const lineTone =
    status === "draft"
      ? "rgba(251,191,36,0.58)"
      : status === "archived"
        ? "rgba(148,163,184,0.52)"
        : status === "live"
          ? "rgba(52,211,153,0.62)"
          : "rgba(56,189,248,0.62)";
  return (
    <>
      <div className="absolute inset-0 tactical-grid opacity-45" />
      <svg
        className="absolute inset-0 h-full w-full opacity-80"
        viewBox="0 0 420 238"
        aria-hidden
      >
        <path
          d="M22 148 C 82 82, 142 208, 208 124 S 330 60, 398 132"
          fill="none"
          stroke={lineTone}
          strokeWidth="1.4"
        />
        <path
          d="M42 70 C 112 118, 122 48, 202 82 S 318 166, 382 82"
          fill="none"
          stroke="rgba(125,211,252,0.22)"
          strokeWidth="1"
          strokeDasharray="4 8"
        />
        {[74, 168, 236, 314, 362].map((x, index) => (
          <g key={x}>
            <circle
              cx={x}
              cy={index % 2 ? 94 : 142}
              r="15"
              fill="rgba(2,6,18,0.58)"
              stroke="rgba(226,232,240,0.26)"
            />
            <path
              d={`M${x - 5} ${index % 2 ? 96 : 144} L${x} ${index % 2 ? 86 : 134} L${x + 5} ${index % 2 ? 96 : 144} M${x} ${index % 2 ? 86 : 134} V${index % 2 ? 104 : 152}`}
              stroke="rgba(226,232,240,0.72)"
              strokeWidth="1.3"
              strokeLinecap="round"
            />
          </g>
        ))}
      </svg>
      <div className="absolute inset-0 border-t border-cyan-300/8 bg-[#020612]/35" />
    </>
  );
}

function ProjectList({
  items,
  onOpen,
  onDuplicate,
  onDelete,
  isTemplateSection,
}: ProjectActions) {
  return (
    <div className="overflow-hidden rounded-lg border border-cyan-200/10 bg-slate-950/32">
      <table className="min-w-full text-xs">
        <thead className="bg-white/[0.035] text-xs text-slate-500">
          <tr>
            <th className="px-4 py-3 text-left font-medium">项目</th>
            <th className="px-4 py-3 text-left font-medium">状态</th>
            <th className="px-4 py-3 text-left font-medium">任务</th>
            <th className="px-4 py-3 text-left font-medium">单位</th>
            <th className="px-4 py-3 text-left font-medium">更新时间</th>
            <th className="px-4 py-3 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const visualStatus = visualStatusOf(item, index, isTemplateSection);
            const visualMeta = VISUAL_STATUS_META[visualStatus];
            const metrics = projectMetrics(item);
            return (
              <tr
                key={item.id}
                className="border-t border-cyan-200/5 hover:bg-white/[0.03]"
              >
                <td
                  className="max-w-[360px] cursor-pointer px-4 py-4"
                  onClick={() => onOpen(item.id)}
                >
                  <div className="font-medium text-slate-100">{item.name}</div>
                  <div className="mt-1 truncate text-xs text-slate-500">
                    {item.description || "暂无描述"}
                  </div>
                </td>
                <td className="px-4 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold",
                      visualMeta.tone
                    )}
                  >
                    <span
                      className={cn("size-1.5 rounded-full", visualMeta.dot)}
                    />
                    {visualMeta.label}
                  </span>
                </td>
                <td className="px-4 py-4 text-slate-400">{metrics.tasks}</td>
                <td className="px-4 py-4 text-slate-400">{metrics.units}</td>
                <td className="px-4 py-4 text-xs text-slate-500">
                  {relativeTime(item.updated_at)}
                </td>
                <td className="px-4 py-4 text-right">
                  <div className="inline-flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onOpen(item.id)}
                      className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-cyan-200 hover:bg-cyan-300/10"
                    >
                      <Play className="size-3.5" />
                      打开
                    </button>
                    {onDuplicate && (
                      <button
                        type="button"
                        onClick={() => onDuplicate(item)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5"
                      >
                        <CopyIcon className="size-3.5" />
                        复制
                      </button>
                    )}
                    {onDelete && (
                      <button
                        type="button"
                        onClick={() => onDelete(item.id, item.name)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-red-300 hover:bg-red-500/10"
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

function WorkspaceDetailPanel({
  items,
  isTemplateSection,
  onCreate,
  onOpen,
}: {
  items: ScenarioListItem[];
  isTemplateSection: boolean;
  onCreate?: () => void;
  onOpen: (id: string) => void;
}) {
  const latestItems = items.slice(0, 5);
  const activeCount = items.filter(
    (item) => statusOf(item) === "running"
  ).length;
  const unitTotal = items.reduce(
    (total, item) => total + Math.max(0, item.unit_count ?? 0),
    0
  );

  return (
    <Card className="sticky top-[80px] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-50">
            {isTemplateSection ? "模板详情" : "项目详情"}
          </h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {isTemplateSection
              ? "系统模板只读，可复制为个人项目后推演。"
              : "当前列表的运行状态、单位规模和最近更新。"}
          </p>
        </div>
        <span className="rounded-full border border-cyan-300/16 bg-cyan-300/8 px-2 py-0.5 text-[11px] text-cyan-100">
          {items.length}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <DetailMetric label="运行中" value={String(activeCount)} />
        <DetailMetric label="单位总量" value={String(unitTotal)} />
      </div>

      <div className="mt-4 border-t border-cyan-300/10 pt-4">
        <div className="mb-2 text-xs font-medium text-slate-300">最近更新</div>
        {latestItems.length === 0 ? (
          <EmptyState
            className="min-h-32 px-3 py-5"
            description="当前筛选条件下暂无项目。"
            title="暂无数据"
          />
        ) : (
          <div className="space-y-1">
            {latestItems.map((item, index) => {
              const visualStatus = visualStatusOf(
                item,
                index,
                isTemplateSection
              );
              const meta = VISUAL_STATUS_META[visualStatus];
              return (
                <button
                  className="flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-2 text-left hover:border-cyan-300/12 hover:bg-white/[0.035]"
                  key={item.id}
                  onClick={() => onOpen(item.id)}
                  type="button"
                >
                  <span
                    className={cn("size-1.5 shrink-0 rounded-full", meta.dot)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium text-slate-200">
                      {item.name}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-slate-600">
                      {relativeTime(item.updated_at)}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {onCreate ? (
        <Button
          className="mt-4 w-full"
          onClick={onCreate}
          type="button"
          variant="outline"
        >
          <Plus className="size-4" />
          新建项目
        </Button>
      ) : null}
    </Card>
  );
}

function DataAssetWorkspace() {
  const { user } = useAuth();
  const setUnitDb = useContext(SetUnitDbContext);
  const importRef = useRef<HTMLInputElement | null>(null);
  const [activeType, setActiveType] = useState<UnitAssetType | "all">("all");
  const [localQuery, setLocalQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<UnitAssetRecord | null>(
    null
  );
  const [assetError, setAssetError] = useState<string | null>(null);
  const [assetLoading, setAssetLoading] = useState(true);
  const [apiAssets, setApiAssets] = useState<ApiUnitAsset[]>([]);
  const [importMode, setImportMode] = useState<"skip" | "replace">("skip");

  const reloadAssets = useCallback(async () => {
    setAssetLoading(true);
    setAssetError(null);
    try {
      const rows = await listUnitAssets();
      setApiAssets(rows);
    } catch (err) {
      setAssetError(err instanceof ApiError ? err.message : "加载单位库失败");
    } finally {
      setAssetLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadAssets();
  }, [reloadAssets]);

  const unitDb = useMemo(() => unitAssetsToDba(apiAssets), [apiAssets]);

  useEffect(() => {
    if (assetLoading || assetError) return;
    setUnitDb(unitDb);
  }, [assetError, assetLoading, setUnitDb, unitDb]);

  const assets = useMemo(() => buildUnitAssetRecords(apiAssets), [apiAssets]);
  const assetCounts = useMemo(() => countUnitAssets(assets), [assets]);
  const mergedQuery = localQuery.trim().toLowerCase();

  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      const typeMatch = activeType === "all" || asset.type === activeType;
      const queryMatch =
        !mergedQuery || asset.searchable.toLowerCase().includes(mergedQuery);
      return typeMatch && queryMatch;
    });
  }, [activeType, assets, mergedQuery]);

  useEffect(() => {
    if (filteredAssets.length === 0) {
      setSelectedId(null);
      return;
    }
    if (
      !selectedId ||
      !filteredAssets.some((asset) => asset.id === selectedId)
    ) {
      setSelectedId(filteredAssets[0].id);
    }
  }, [filteredAssets, selectedId]);

  const selectedAsset =
    filteredAssets.find((asset) => asset.id === selectedId) ??
    filteredAssets[0] ??
    null;

  const handleExport = () => {
    const blob = new Blob([unitDb.exportToJson()], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `tianshu-unit-assets-${new Date()
      .toISOString()
      .slice(0, 10)}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setNotice("单位库已导出为 JSON 文件。");
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const nextDb = new Dba();
      nextDb.importFromJson(await file.text());
      const result = await importUnitAssets({
        ...dbaToCatalog(nextDb),
        replace_existing: importMode === "replace",
      });
      setApiAssets(result.assets);
      setAssetError(null);
      setActiveType("all");
      setNotice(
        `单位库已导入（${importMode === "replace" ? "覆盖自定义" : "冲突跳过"}）：新增 ${result.created}，更新 ${result.updated}，跳过 ${result.skipped}。`
      );
    } catch (err) {
      setAssetError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "单位库导入失败"
      );
    } finally {
      input.value = "";
    }
  };

  const canWriteAsset = (asset: UnitAssetRecord | null) =>
    Boolean(asset && (!asset.isSystem || user?.is_superuser));

  const handleDeleteAsset = async (asset: UnitAssetRecord) => {
    if (!canWriteAsset(asset)) return;
    if (!window.confirm(`删除单位资产「${asset.name}」？此操作不可撤销。`)) {
      return;
    }
    try {
      await deleteUnitAsset(asset.assetId);
      setApiAssets((prev) => prev.filter((item) => item.id !== asset.assetId));
      setSelectedId(null);
      setAssetError(null);
      setNotice(`已删除单位资产「${asset.name}」。`);
    } catch (err) {
      setAssetError(err instanceof ApiError ? err.message : "删除单位资产失败");
    }
  };

  const handleReset = async () => {
    if (!window.confirm("恢复默认单位库？当前用户添加的单位资产会被移除。")) {
      return;
    }
    try {
      const rows = await resetUnitAssets();
      setApiAssets(rows);
      setAssetError(null);
      setActiveType("all");
      setNotice("已恢复默认平台单位库。");
    } catch (err) {
      setAssetError(
        err instanceof ApiError ? err.message : "恢复默认单位库失败"
      );
    }
  };

  return (
    <div className="space-y-5">
      <input
        ref={importRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={handleImport}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {UNIT_ASSET_TYPES.map((type) => {
              const Icon = type.icon;
              const active = activeType === type.id;
              const count =
                type.id === "all" ? assets.length : (assetCounts[type.id] ?? 0);
              return (
                <button
                  key={type.id}
                  type="button"
                  onClick={() => setActiveType(type.id)}
                  className={cn(
                    "group relative overflow-hidden rounded-lg border p-3 text-left transition-colors",
                    active
                      ? "border-cyan-300/30 bg-cyan-300/[0.08]"
                      : "border-cyan-300/10 bg-slate-950/35 hover:border-cyan-300/22 hover:bg-white/[0.035]"
                  )}
                >
                  <div className="relative">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="grid size-8 place-items-center rounded-md border border-cyan-300/12 bg-cyan-300/[0.06] text-cyan-100">
                        <Icon className="size-5" />
                      </span>
                      <span className="text-lg font-semibold text-white">
                        {count}
                      </span>
                    </div>
                    <div className="text-xs font-medium text-slate-100">
                      {type.label}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">
                      Platform Unit Assets
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <Toolbar>
            <ToolbarGroup className="flex-1">
              <SearchInput
                className="w-full"
                value={localQuery}
                onChange={(event) => setLocalQuery(event.target.value)}
                onClear={() => setLocalQuery("")}
                placeholder="搜索单位名称、类型、指标、加油机、防空、武器..."
              />
            </ToolbarGroup>
            <ToolbarGroup>
              <Button type="button" onClick={() => setAddDialogOpen(true)}>
                <Plus className="size-4" />
                添加单位
              </Button>
              <select
                value={importMode}
                onChange={(event) =>
                  setImportMode(event.target.value as "skip" | "replace")
                }
                className="h-9 rounded-md border border-cyan-300/12 bg-slate-950/60 px-2.5 text-xs text-slate-300 outline-none focus:border-cyan-300/35"
              >
                <option value="skip">冲突跳过</option>
                <option value="replace">覆盖自定义</option>
              </select>
              <Button
                type="button"
                variant="ghost"
                onClick={() => importRef.current?.click()}
              >
                <UploadCloud className="size-4" />
                导入单位库
              </Button>
              <Button type="button" variant="ghost" onClick={handleExport}>
                <FileInput className="size-4" />
                导出单位库
              </Button>
              <Button
                type="button"
                variant="outline"
                className="border-amber-300/18 bg-amber-300/[0.04] text-amber-100 hover:bg-amber-300/[0.08]"
                onClick={handleReset}
              >
                恢复默认
              </Button>
            </ToolbarGroup>
          </Toolbar>

          {notice && (
            <div className="rounded-lg border border-emerald-300/20 bg-emerald-400/[0.08] px-3 py-2 text-xs text-emerald-100">
              {notice}
            </div>
          )}

          {assetError && (
            <div className="rounded-lg border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs text-red-100">
              {assetError}
            </div>
          )}

          <div className="max-h-[70vh] overflow-y-auto pr-2 [scrollbar-color:rgba(125,211,252,0.36)_rgba(15,23,42,0.26)] [scrollbar-width:thin]">
            {assetLoading ? (
              <Skeleton view="grid" />
            ) : filteredAssets.length === 0 ? (
              <Empty
                title="没有匹配的单位资产"
                description="调整搜索条件，或手动添加飞机、舰艇、地面设施、机场与武器单位。"
                actionLabel="添加单位"
                onAction={() => setAddDialogOpen(true)}
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                {filteredAssets.map((asset) => (
                  <UnitAssetCard
                    key={asset.id}
                    asset={asset}
                    active={asset.id === selectedAsset?.id}
                    onSelect={() => setSelectedId(asset.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <UnitAssetDetail
          asset={selectedAsset}
          total={assets.length}
          canWrite={canWriteAsset(selectedAsset)}
          onEdit={
            selectedAsset ? () => setEditingAsset(selectedAsset) : undefined
          }
          onDelete={
            selectedAsset
              ? () => void handleDeleteAsset(selectedAsset)
              : undefined
          }
        />
      </div>

      {addDialogOpen && (
        <AddUnitAssetDialog
          mode="create"
          onClose={() => setAddDialogOpen(false)}
          onSave={async (payload, typeLabel) => {
            const created = await createUnitAsset(payload);
            setApiAssets((prev) => [...prev, created]);
            setAddDialogOpen(false);
            setActiveType(created.type);
            setSelectedId(created.id);
            setLocalQuery("");
            setAssetError(null);
            setNotice(`已添加 ${typeLabel}，单位库已保存到后端数据库。`);
          }}
        />
      )}

      {editingAsset && (
        <AddUnitAssetDialog
          mode="edit"
          initialAsset={editingAsset}
          onClose={() => setEditingAsset(null)}
          onSave={async (payload, typeLabel) => {
            const updated = await updateUnitAsset(editingAsset.assetId, {
              data: payload.data,
            });
            setApiAssets((prev) =>
              prev.map((item) => (item.id === updated.id ? updated : item))
            );
            setEditingAsset(null);
            setActiveType(updated.type);
            setSelectedId(updated.id);
            setLocalQuery("");
            setAssetError(null);
            setNotice(`已更新 ${typeLabel}，单位库已保存到后端数据库。`);
          }}
        />
      )}
    </div>
  );
}

type AddUnitForm = {
  type: UnitAssetType;
  name: string;
  speed: string;
  maxFuel: string;
  fuelRate: string;
  range: string;
  lethality: string;
  latitude: string;
  longitude: string;
  country: string;
  isTanker: boolean;
  fuelOffloadCapacity: string;
  fuelTransferRate: string;
  refuelRange: string;
  isElectronicWarfare: boolean;
  jammingRange: string;
  jammingStrength: string;
  jammingModes: string;
  communicationDisruption: string;
};

const DEFAULT_UNIT_FORM: AddUnitForm = {
  type: "aircraft",
  name: "",
  speed: "",
  maxFuel: "",
  fuelRate: "",
  range: "",
  lethality: "",
  latitude: "",
  longitude: "",
  country: "",
  isTanker: false,
  fuelOffloadCapacity: "",
  fuelTransferRate: "",
  refuelRange: "",
  isElectronicWarfare: false,
  jammingRange: "",
  jammingStrength: "",
  jammingModes: "radar,communications",
  communicationDisruption: "",
};

function AddUnitAssetDialog({
  mode,
  initialAsset,
  onClose,
  onSave,
}: {
  mode: "create" | "edit";
  initialAsset?: UnitAssetRecord;
  onClose: () => void;
  onSave: (payload: UnitAssetCreatePayload, typeLabel: string) => Promise<void>;
}) {
  const isEditing = mode === "edit";
  const [form, setForm] = useState<AddUnitForm>(() =>
    initialAsset
      ? unitAssetFormFromRecord(initialAsset)
      : { ...DEFAULT_UNIT_FORM }
  );
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiNotice, setAiNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const activeTypeMeta =
    UNIT_ASSET_TYPES.find((type) => type.id === form.type) ??
    UNIT_ASSET_TYPES[1];
  const Icon = activeTypeMeta.icon;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting && !generating) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [generating, onClose, submitting]);

  const update = (patch: Partial<AddUnitForm>) => {
    setForm((prev) => ({ ...prev, ...patch }));
    setError(null);
    setAiNotice(null);
  };

  const handleGenerate = async () => {
    const query = [form.name, aiPrompt]
      .map((value) => value.trim())
      .filter(Boolean)
      .join(" ");
    if (!query) {
      setError("请先输入型号或在 AI 生成描述中说明目标单位。");
      return;
    }
    setGenerating(true);
    setError(null);
    setAiNotice(null);
    try {
      const result = await generateUnitAsset({
        type: form.type,
        query,
        context:
          "Generate editable 天枢平台 unit asset form values for a simulation database.",
      });
      setForm((prev) => ({
        ...prev,
        ...unitAssetFormFromData(result.type, result.data),
      }));
      const sourceLabel = result.source === "llm" ? "模型生成" : "本地估算";
      const confidence = Math.round(result.confidence * 100);
      const warningText = result.warnings.length
        ? ` ${result.warnings[0]}`
        : "";
      setAiNotice(
        `AI 已填充参数（${sourceLabel}，可信度 ${confidence}%）。${warningText}`
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "AI 生成单位参数失败"
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { payload, typeLabel } = createUnitAssetPayloadFromForm(form);
      await onSave(payload, typeLabel);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "添加单位失败"
      );
    } finally {
      setSubmitting(false);
    }
  };

  const needsMobility =
    form.type === "aircraft" || form.type === "ship" || form.type === "weapon";

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(event) => {
        if (
          event.target === event.currentTarget &&
          !submitting &&
          !generating
        ) {
          onClose();
        }
      }}
    >
      <Card className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-lg border-cyan-200/15 bg-[#08111c] p-4 shadow-[0_10px_28px_rgba(0,0,0,0.34)]">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-md border border-cyan-200/20 bg-cyan-300/10 text-cyan-200">
            <Icon className="size-5" />
          </span>
          <div>
            <div className="text-lg font-semibold text-slate-100">
              {isEditing ? "编辑单位资产" : "添加单位资产"}
            </div>
            <div className="text-sm text-slate-500">
              {isEditing
                ? "调整单位参数后会同步到当前单位选择数据源。"
                : "手动维护平台单位库，新增后会同步到当前单位选择数据源。"}
            </div>
          </div>
        </div>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm text-slate-400">
                单位类型
              </span>
              <select
                value={form.type}
                onChange={(event) =>
                  update({
                    ...DEFAULT_UNIT_FORM,
                    type: event.target.value as UnitAssetType,
                  })
                }
                disabled={submitting || generating || isEditing}
                className="h-9 w-full rounded-md border border-cyan-200/15 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none focus:border-cyan-200/45"
              >
                {UNIT_ASSET_TYPES.filter((type) => type.id !== "all").map(
                  (type) => (
                    <option key={type.id} value={type.id}>
                      {type.label}
                    </option>
                  )
                )}
              </select>
            </label>

            <AssetFormInput
              label={form.type === "airbase" ? "机场名称" : "型号 / 类别名称"}
              value={form.name}
              onChange={(value) => update({ name: value })}
              placeholder={
                form.type === "aircraft"
                  ? "例如：J-20 / KC-135R"
                  : form.type === "ship"
                    ? "例如：Destroyer"
                    : form.type === "facility"
                      ? "例如：HQ-9"
                      : form.type === "weapon"
                        ? "例如：AIM-120"
                        : "例如：Guam AFB"
              }
              required
            />
          </div>

          {!isEditing && (
            <div className="rounded-lg border border-cyan-200/10 bg-cyan-300/[0.035] p-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
                <label className="block min-w-0 flex-1">
                  <span className="mb-2 flex items-center gap-2 text-sm text-cyan-100">
                    <Sparkles className="size-4" />
                    AI 生成单位参数
                  </span>
                  <input
                    value={aiPrompt}
                    onChange={(event) => {
                      setAiPrompt(event.target.value);
                      setError(null);
                      setAiNotice(null);
                    }}
                    placeholder="补充用途、国家、版本或别名，例如：空中加油机 / 五代战斗机 / 舰载预警机"
                    className="h-9 w-full rounded-md border border-cyan-200/15 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-200/45"
                  />
                </label>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={handleGenerate}
                  disabled={submitting || generating}
                  className="h-9 rounded-md border border-cyan-200/20 bg-slate-950/35 px-3 text-xs text-cyan-100 hover:bg-cyan-300/[0.08]"
                >
                  <Sparkles className="size-4" />
                  {generating ? "生成中..." : "AI 生成"}
                </Button>
              </div>
              {aiNotice && (
                <div className="mt-3 rounded-lg border border-emerald-300/20 bg-emerald-400/[0.08] px-3 py-2 text-xs text-emerald-100">
                  {aiNotice}
                </div>
              )}
            </div>
          )}

          {needsMobility && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <AssetFormInput
                label="速度"
                value={form.speed}
                onChange={(value) => update({ speed: value })}
                placeholder="900"
                type="number"
                required
              />
              <AssetFormInput
                label="最大燃料"
                value={form.maxFuel}
                onChange={(value) => update({ maxFuel: value })}
                placeholder="12000"
                type="number"
                required
              />
              <AssetFormInput
                label="燃料消耗"
                value={form.fuelRate}
                onChange={(value) => update({ fuelRate: value })}
                placeholder="3200"
                type="number"
                required
              />
              <AssetFormInput
                label="探测半径 / 射程"
                value={form.range}
                onChange={(value) => update({ range: value })}
                placeholder="120"
                type="number"
                required
              />
            </div>
          )}

          {form.type === "aircraft" && (
            <div className="rounded-lg border border-cyan-200/10 bg-white/[0.025] p-3">
              <label className="flex items-center gap-3 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={form.isTanker}
                  onChange={(event) =>
                    update({ isTanker: event.target.checked })
                  }
                  className="size-4 accent-cyan-400"
                />
                该飞机具备空中加油能力
              </label>
              {form.isTanker && (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
                  <AssetFormInput
                    label="可卸载燃料"
                    value={form.fuelOffloadCapacity}
                    onChange={(value) => update({ fuelOffloadCapacity: value })}
                    placeholder="45000"
                    type="number"
                  />
                  <AssetFormInput
                    label="加油速率"
                    value={form.fuelTransferRate}
                    onChange={(value) => update({ fuelTransferRate: value })}
                    placeholder="1200"
                    type="number"
                  />
                  <AssetFormInput
                    label="加油半径"
                    value={form.refuelRange}
                    onChange={(value) => update({ refuelRange: value })}
                    placeholder="900"
                    type="number"
                  />
                </div>
              )}
              <label className="mt-4 flex items-center gap-3 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={form.isElectronicWarfare}
                  onChange={(event) =>
                    update({ isElectronicWarfare: event.target.checked })
                  }
                  className="size-4 accent-cyan-400"
                />
                电子战 / 雷达干扰能力
              </label>
              {form.isElectronicWarfare && (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
                  <AssetFormInput
                    label="干扰半径"
                    value={form.jammingRange}
                    onChange={(value) => update({ jammingRange: value })}
                    placeholder="150"
                    type="number"
                  />
                  <AssetFormInput
                    label="干扰强度"
                    value={form.jammingStrength}
                    onChange={(value) => update({ jammingStrength: value })}
                    placeholder="0.55"
                    type="number"
                  />
                  <AssetFormInput
                    label="通信扰动"
                    value={form.communicationDisruption}
                    onChange={(value) =>
                      update({ communicationDisruption: value })
                    }
                    placeholder="0.35"
                    type="number"
                  />
                  <AssetFormInput
                    label="干扰模式"
                    value={form.jammingModes}
                    onChange={(value) => update({ jammingModes: value })}
                    placeholder="radar,communications"
                  />
                </div>
              )}
            </div>
          )}

          {form.type === "facility" && (
            <AssetFormInput
              label="探测 / 交战半径"
              value={form.range}
              onChange={(value) => update({ range: value })}
              placeholder="250"
              type="number"
              required
            />
          )}

          {form.type === "airbase" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <AssetFormInput
                label="国家 / 地区"
                value={form.country}
                onChange={(value) => update({ country: value })}
                placeholder="US"
                required
              />
              <AssetFormInput
                label="纬度"
                value={form.latitude}
                onChange={(value) => update({ latitude: value })}
                placeholder="13.58"
                type="number"
                required
              />
              <AssetFormInput
                label="经度"
                value={form.longitude}
                onChange={(value) => update({ longitude: value })}
                placeholder="144.92"
                type="number"
                required
              />
            </div>
          )}

          {form.type === "weapon" && (
            <AssetFormInput
              label="杀伤概率 / 杀伤值"
              value={form.lethality}
              onChange={(value) => update({ lethality: value })}
              placeholder="0.82"
              type="number"
              required
            />
          )}

          {error && (
            <div className="rounded-lg border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs text-red-100">
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={submitting || generating}
              className="rounded-md px-3 text-slate-300 hover:bg-white/[0.06]"
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={submitting || generating}
              className="rounded-md border border-cyan-200/25 bg-cyan-300/12 px-3 text-cyan-50"
            >
              {submitting
                ? "保存中..."
                : isEditing
                  ? "保存修改"
                  : "添加到单位库"}
            </Button>
          </div>
        </form>
      </Card>
    </div>,
    document.body
  );
}

function AssetFormInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "number";
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm text-slate-400">
        {label}
        {required && <span className="ml-1 text-red-400">*</span>}
      </span>
      <input
        type={type}
        step={type === "number" ? "any" : undefined}
        required={required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-md border border-cyan-200/15 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-200/45"
      />
    </label>
  );
}

function createUnitAssetPayloadFromForm(form: AddUnitForm): {
  payload: UnitAssetCreatePayload;
  typeLabel: string;
} {
  const name = form.name.trim();
  if (!name) throw new Error("请填写单位名称。");
  let data: Record<string, unknown>;

  if (form.type === "aircraft") {
    data = {
      className: name,
      speed: readNumber(form.speed, "速度"),
      maxFuel: readNumber(form.maxFuel, "最大燃料"),
      fuelRate: readNumber(form.fuelRate, "燃料消耗"),
      range: readNumber(form.range, "探测半径"),
      isTanker: form.isTanker,
      fuelOffloadCapacity: form.isTanker
        ? readOptionalNumber(form.fuelOffloadCapacity)
        : 0,
      fuelTransferRate: form.isTanker
        ? readOptionalNumber(form.fuelTransferRate)
        : 0,
      refuelRange: form.isTanker ? readOptionalNumber(form.refuelRange) : 0,
      isElectronicWarfare: form.isElectronicWarfare,
      jammingRange: form.isElectronicWarfare
        ? readOptionalNumber(form.jammingRange)
        : 0,
      jammingStrength: form.isElectronicWarfare
        ? readOptionalNumber(form.jammingStrength)
        : 0,
      jammingModes: form.isElectronicWarfare
        ? form.jammingModes
            .split(",")
            .map((mode) => mode.trim())
            .filter(Boolean)
        : [],
      communicationDisruption: form.isElectronicWarfare
        ? readOptionalNumber(form.communicationDisruption)
        : 0,
      dataSource: {
        speedSrc: "Manual",
        maxFuelSrc: "Manual",
        fuelRateSrc: "Manual",
        rangeSrc: "Manual",
      },
      units: {
        speedUnit: "kts",
        maxFuelUnit: "kg",
        fuelRateUnit: "kg/h",
        rangeUnit: "nm",
        jammingRangeUnit: "nm",
      },
    };
  } else if (form.type === "ship") {
    data = {
      className: name,
      speed: readNumber(form.speed, "速度"),
      maxFuel: readNumber(form.maxFuel, "最大燃料"),
      fuelRate: readNumber(form.fuelRate, "燃料消耗"),
      range: readNumber(form.range, "探测半径"),
      dataSource: {
        speedSrc: "Manual",
        maxFuelSrc: "Manual",
        fuelRateSrc: "Manual",
        rangeSrc: "Manual",
      },
      units: {
        speedUnit: "kts",
        maxFuelUnit: "kg",
        fuelRateUnit: "kg/h",
        rangeUnit: "nm",
      },
    };
  } else if (form.type === "facility") {
    data = { className: name, range: readNumber(form.range, "半径") };
  } else if (form.type === "airbase") {
    data = {
      name,
      country: form.country.trim() || "Unknown",
      latitude: readNumber(form.latitude, "纬度"),
      longitude: readNumber(form.longitude, "经度"),
    };
  } else {
    data = {
      className: name,
      speed: readNumber(form.speed, "速度"),
      maxFuel: readNumber(form.maxFuel, "最大燃料"),
      fuelRate: readNumber(form.fuelRate, "燃料消耗"),
      range: readNumber(form.range, "射程"),
      lethality: readNumber(form.lethality, "杀伤值"),
    };
  }

  const typeLabel =
    UNIT_ASSET_TYPES.find((type) => type.id === form.type)?.label ?? "单位";
  return { payload: { type: form.type, data }, typeLabel };
}

function readNumber(value: string, label: string) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${label} 需要填写有效数字。`);
  return parsed;
}

function readOptionalNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toFormValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value)
    ? String(value)
    : "";
}

function unitAssetFormFromData(
  type: UnitAssetType,
  data: Record<string, unknown>
): Partial<AddUnitForm> {
  return {
    type,
    name:
      type === "airbase"
        ? String(data.name ?? "")
        : String(data.className ?? ""),
    speed: toFormValue(data.speed),
    maxFuel: toFormValue(data.maxFuel),
    fuelRate: toFormValue(data.fuelRate),
    range: toFormValue(data.range),
    lethality: toFormValue(data.lethality),
    latitude: toFormValue(data.latitude),
    longitude: toFormValue(data.longitude),
    country: typeof data.country === "string" ? data.country : "",
    isTanker: Boolean(data.isTanker),
    fuelOffloadCapacity: toFormValue(data.fuelOffloadCapacity),
    fuelTransferRate: toFormValue(data.fuelTransferRate),
    refuelRange: toFormValue(data.refuelRange),
    isElectronicWarfare: Boolean(data.isElectronicWarfare),
    jammingRange: toFormValue(data.jammingRange),
    jammingStrength: toFormValue(data.jammingStrength),
    jammingModes: Array.isArray(data.jammingModes)
      ? data.jammingModes.join(",")
      : typeof data.jammingModes === "string"
        ? data.jammingModes
        : "radar,communications",
    communicationDisruption: toFormValue(data.communicationDisruption),
  };
}

const UNIT_ASSET_STATUS_LABELS: Record<string, string> = {
  "TANKER READY": "加油机就绪",
  "EW READY": "电子战就绪",
  "AIR ASSET": "空中单位",
  "SURFACE ASSET": "水面舰艇",
  "GROUND ASSET": "地面设施",
  AIRBASE: "机场节点",
  "BASE ASSET": "基地资产",
  WEAPON: "武器模型",
  "WEAPON ASSET": "武器资产",
};

const UNIT_ASSET_FIELD_LABELS: Record<string, string> = {
  className: "型号名称",
  name: "名称",
  speed: "速度",
  maxFuel: "最大燃料",
  fuelRate: "燃料消耗",
  range: "探测半径 / 射程",
  rangeRole: "范围口径",
  rangeConfidence: "范围可信度",
  rangeNotes: "范围说明",
  ferryRangeNm: "转场航程",
  combatRadiusNm: "作战半径",
  missionRangeNm: "任务半径",
  enduranceRangeNm: "续航里程",
  targetTypes: "目标类型",
  lethality: "杀伤值",
  latitude: "纬度",
  longitude: "经度",
  country: "国家 / 地区",
  isTanker: "加油能力",
  fuelOffloadCapacity: "可卸载燃油",
  fuelTransferRate: "输油速率",
  refuelRange: "加油半径",
  isElectronicWarfare: "电子战能力",
  jammingRange: "干扰半径",
  jammingStrength: "干扰强度",
  jammingModes: "干扰模式",
  communicationDisruption: "通信扰动",
};

const UNIT_ASSET_SOURCE_LABELS: Record<string, string> = {
  speedSrc: "速度来源",
  maxFuelSrc: "燃料来源",
  fuelRateSrc: "消耗来源",
  rangeSrc: "范围来源",
  ferryRangeSrc: "航程来源",
  enduranceRangeSrc: "续航来源",
};

const COUNTRY_LABELS: Record<string, string> = {
  Australia: "澳大利亚",
  Germany: "德国",
  Greenland: "格陵兰",
  Guam: "关岛",
  Italy: "意大利",
  Japan: "日本",
  Qatar: "卡塔尔",
  Spain: "西班牙",
  "South Korea": "韩国",
  Turkey: "土耳其",
  "United Kingdom": "英国",
  Unknown: "未知",
  USA: "美国",
};

function localizeAssetDisplayName(type: UnitAssetType, name: string) {
  return localizeUnitAssetName(type, name);
}

function localizeAssetStatus(status: string) {
  return UNIT_ASSET_STATUS_LABELS[status] ?? status;
}

function localizeCountry(country: string) {
  return COUNTRY_LABELS[country] ?? country;
}

function localizeMeasureUnit(unit: string | undefined) {
  const normalized = unit?.toLowerCase();
  if (!normalized) return "";
  if (normalized === "knots" || normalized === "kts") return "节";
  if (normalized === "nm") return "海里";
  if (normalized === "km") return "公里";
  if (normalized === "lbs" || normalized === "lb") return "磅";
  if (normalized === "lbs/hr" || normalized === "lb/hr") return "磅/小时";
  if (normalized === "kg") return "千克";
  if (normalized === "kg/h") return "千克/小时";
  return unit ?? "";
}

function formatSpeedMetric(value: number, unit?: string) {
  const unitLabel = localizeMeasureUnit(unit || "kts");
  return unitLabel ? `${value} ${unitLabel}` : String(value);
}

function formatRangeMetric(prefix: string, value: number, unit?: string) {
  const unitLabel = localizeMeasureUnit(unit || "nm");
  return unitLabel ? `${prefix} ${value} ${unitLabel}` : `${prefix} ${value}`;
}

function formatAssetFieldValue(
  asset: UnitAssetRecord,
  key: string,
  value: unknown
) {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") {
    if (key === "className") return localizeAssetDisplayName(asset.type, value);
    if (key === "name" && asset.type === "airbase") {
      return localizeAssetDisplayName("airbase", value);
    }
    if (key === "country") return localizeCountry(value);
    if (value === "Manual") return "手动录入";
    if (value === "missing") return "未提供";
  }
  return String(value);
}

function unitAssetFormFromRecord(asset: UnitAssetRecord): AddUnitForm {
  const raw = asset.raw as unknown as Record<string, unknown>;
  return {
    ...DEFAULT_UNIT_FORM,
    ...unitAssetFormFromData(asset.type, raw),
    name:
      asset.type === "airbase"
        ? String(raw.name ?? asset.name)
        : String(raw.className ?? asset.name),
  };
}

function buildUnitAssetRecords(apiAssets: ApiUnitAsset[]): UnitAssetRecord[] {
  return apiAssets.map((asset) => {
    if (asset.type === "aircraft") {
      const unit = asset.data as unknown as IAircraftModel;
      const canonicalName = unit.className;
      const role = unit.isElectronicWarfare
        ? "电子战机"
        : unit.isTanker
          ? "空中加油机"
          : classifyAircraft(canonicalName);
      return makeAssetRecord({
        id: asset.id,
        assetId: asset.id,
        type: "aircraft",
        typeLabel: "飞机",
        name: localizeAssetDisplayName("aircraft", canonicalName),
        canonicalName,
        role,
        primaryMetric: formatSpeedMetric(unit.speed, unit.units?.speedUnit),
        secondaryMetric: formatRangeMetric(
          "探测",
          unit.range,
          unit.units?.rangeUnit
        ),
        status: unit.isElectronicWarfare
          ? "EW READY"
          : unit.isTanker
            ? "TANKER READY"
            : "AIR ASSET",
        raw: unit,
        isSystem: asset.is_system,
        version: asset.version,
        updatedAt: asset.updated_at,
        extra: [
          unit.maxFuel,
          unit.fuelRate,
          unit.isTanker ? "tanker refuel fuelOffload" : "",
          unit.isElectronicWarfare
            ? `electronic warfare ewar jammer jamming ${unit.jammingRange ?? ""} ${unit.jammingStrength ?? ""}`
            : "",
        ].join(" "),
      });
    }

    if (asset.type === "ship") {
      const unit = asset.data as unknown as IShipModel;
      const canonicalName = unit.className;
      return makeAssetRecord({
        id: asset.id,
        assetId: asset.id,
        type: "ship",
        typeLabel: "舰艇",
        name: localizeAssetDisplayName("ship", canonicalName),
        canonicalName,
        role: classifyShip(canonicalName),
        primaryMetric: formatSpeedMetric(unit.speed, unit.units?.speedUnit),
        secondaryMetric: formatRangeMetric(
          "探测",
          unit.range,
          unit.units?.rangeUnit
        ),
        status: "SURFACE ASSET",
        raw: unit,
        isSystem: asset.is_system,
        version: asset.version,
        updatedAt: asset.updated_at,
        extra: [unit.maxFuel, unit.fuelRate].join(" "),
      });
    }

    if (asset.type === "facility") {
      const unit = asset.data as unknown as IFacilityModel;
      const canonicalName = unit.className;
      return makeAssetRecord({
        id: asset.id,
        assetId: asset.id,
        type: "facility",
        typeLabel: "地面设施",
        name: localizeAssetDisplayName("facility", canonicalName),
        canonicalName,
        role: "防空 / 雷达 / 地面节点",
        primaryMetric: `${unit.range} 公里`,
        secondaryMetric: "探测 / 交战半径",
        status: "GROUND ASSET",
        raw: unit,
        isSystem: asset.is_system,
        version: asset.version,
        updatedAt: asset.updated_at,
        extra: "sam radar air defense facility",
      });
    }

    if (asset.type === "airbase") {
      const unit = asset.data as unknown as IAirbaseModel;
      const canonicalName = unit.name;
      return makeAssetRecord({
        id: asset.id,
        assetId: asset.id,
        type: "airbase",
        typeLabel: "机场",
        name: localizeAssetDisplayName("airbase", canonicalName),
        canonicalName,
        role: unit.country ? localizeCountry(unit.country) : "机场节点",
        primaryMetric: `${unit.latitude.toFixed(2)}, ${unit.longitude.toFixed(2)}`,
        secondaryMetric: "部署 / 起降节点",
        status: "AIRBASE",
        raw: unit,
        isSystem: asset.is_system,
        version: asset.version,
        updatedAt: asset.updated_at,
        extra: [unit.country, unit.latitude, unit.longitude].join(" "),
      });
    }

    const unit = asset.data as unknown as IWeaponModel;
    const canonicalName = unit.className;
    return makeAssetRecord({
      id: asset.id,
      assetId: asset.id,
      type: "weapon",
      typeLabel: "武器",
      name: localizeAssetDisplayName("weapon", canonicalName),
      canonicalName,
      role: "导弹 / 武器模型",
      primaryMetric: formatSpeedMetric(unit.speed, "kts"),
      secondaryMetric: formatRangeMetric("射程", unit.range, "nm"),
      status: "WEAPON",
      raw: unit,
      isSystem: asset.is_system,
      version: asset.version,
      updatedAt: asset.updated_at,
      extra: [unit.maxFuel, unit.fuelRate, unit.lethality].join(" "),
    });
  });
}

function buildUnitAssets(unitDb: Dba): UnitAssetRecord[] {
  const aircraft = unitDb.getAircraftDb().map((unit) => {
    const canonicalName = unit.className;
    const role = unit.isElectronicWarfare
      ? "电子战机"
      : unit.isTanker
        ? "空中加油机"
        : classifyAircraft(canonicalName);
    return makeAssetRecord({
      type: "aircraft",
      typeLabel: "飞机",
      name: localizeAssetDisplayName("aircraft", canonicalName),
      canonicalName,
      role,
      primaryMetric: formatSpeedMetric(unit.speed, unit.units?.speedUnit),
      secondaryMetric: formatRangeMetric(
        "探测",
        unit.range,
        unit.units?.rangeUnit
      ),
      status: unit.isElectronicWarfare
        ? "EW READY"
        : unit.isTanker
          ? "TANKER READY"
          : "AIR ASSET",
      raw: unit,
      extra: [
        unit.maxFuel,
        unit.fuelRate,
        unit.isTanker ? "tanker refuel fuelOffload" : "",
        unit.isElectronicWarfare
          ? `electronic warfare ewar jammer jamming ${unit.jammingRange ?? ""} ${unit.jammingStrength ?? ""}`
          : "",
      ].join(" "),
    });
  });

  const ships = unitDb.getShipDb().map((unit) =>
    makeAssetRecord({
      type: "ship",
      typeLabel: "舰艇",
      name: localizeAssetDisplayName("ship", unit.className),
      canonicalName: unit.className,
      role: classifyShip(unit.className),
      primaryMetric: formatSpeedMetric(unit.speed, unit.units?.speedUnit),
      secondaryMetric: formatRangeMetric(
        "探测",
        unit.range,
        unit.units?.rangeUnit
      ),
      status: "SURFACE ASSET",
      raw: unit,
      extra: [unit.maxFuel, unit.fuelRate].join(" "),
    })
  );

  const facilities = unitDb.getFacilityDb().map((unit) =>
    makeAssetRecord({
      type: "facility",
      typeLabel: "地面设施",
      name: localizeAssetDisplayName("facility", unit.className),
      canonicalName: unit.className,
      role: "防空 / 雷达 / 地面节点",
      primaryMetric: `${unit.range} 公里`,
      secondaryMetric: "探测 / 交战半径",
      status: "GROUND ASSET",
      raw: unit,
      extra: "sam radar air defense facility",
    })
  );

  const airbases = unitDb.getAirbaseDb().map((unit) =>
    makeAssetRecord({
      type: "airbase",
      typeLabel: "机场",
      name: localizeAssetDisplayName("airbase", unit.name),
      canonicalName: unit.name,
      role: unit.country ? localizeCountry(unit.country) : "机场节点",
      primaryMetric: unit.country ? localizeCountry(unit.country) : "未知",
      secondaryMetric: `${unit.latitude.toFixed(2)}, ${unit.longitude.toFixed(2)}`,
      status: "BASE ASSET",
      raw: unit,
      extra: [unit.latitude, unit.longitude].join(" "),
    })
  );

  const weapons = unitDb.getWeaponDb().map((unit) =>
    makeAssetRecord({
      type: "weapon",
      typeLabel: "武器",
      name: localizeAssetDisplayName("weapon", unit.className),
      canonicalName: unit.className,
      role: "武器挂载 / 弹药",
      primaryMetric: `杀伤 ${unit.lethality}`,
      secondaryMetric: `射程 ${unit.range} 公里`,
      status: "WEAPON ASSET",
      raw: unit,
      extra: [unit.speed, unit.maxFuel, unit.fuelRate].join(" "),
    })
  );

  return [...aircraft, ...ships, ...facilities, ...airbases, ...weapons];
}

function makeAssetRecord({
  id,
  assetId,
  type,
  typeLabel,
  name,
  role,
  primaryMetric,
  secondaryMetric,
  status,
  isSystem,
  version,
  updatedAt,
  raw,
  canonicalName,
  extra,
}: Omit<
  UnitAssetRecord,
  "id" | "assetId" | "isSystem" | "version" | "updatedAt" | "searchable"
> & {
  id?: string;
  assetId?: string;
  isSystem?: boolean;
  version?: number;
  updatedAt?: string;
  extra?: string;
}) {
  const recordKey = canonicalName || name;
  const statusLabel = localizeAssetStatus(status);
  return {
    id: id ?? `${type}:${recordKey}`,
    assetId: assetId ?? `${type}:${recordKey}`,
    type,
    typeLabel,
    name,
    canonicalName,
    role,
    primaryMetric,
    secondaryMetric,
    status: statusLabel,
    isSystem: isSystem ?? true,
    version: version ?? 1,
    updatedAt: updatedAt ?? "",
    raw,
    searchable: [
      type,
      typeLabel,
      name,
      canonicalName ?? "",
      role,
      primaryMetric,
      secondaryMetric,
      status,
      statusLabel,
      extra ?? "",
    ].join(" "),
  };
}

function countUnitAssets(assets: UnitAssetRecord[]) {
  return assets.reduce(
    (acc, asset) => {
      acc[asset.type] = (acc[asset.type] ?? 0) + 1;
      return acc;
    },
    {} as Record<UnitAssetType, number>
  );
}

function classifyAircraft(className: string) {
  const lower = className.toLowerCase();
  if (
    lower.includes("ea-") ||
    lower.includes("ef-111") ||
    lower.includes("growler") ||
    lower.includes("prowler") ||
    lower.includes("raven") ||
    lower.includes("electronic") ||
    lower.includes("jammer") ||
    lower.includes("电子战") ||
    lower.includes("干扰")
  ) {
    return "电子战机";
  }
  if (lower.includes("kc-") || lower.includes("tanker")) return "空中加油机";
  if (lower.includes("b-")) return "轰炸机";
  if (lower.includes("c-")) return "运输机";
  if (lower.includes("f-") || lower.includes("fighter")) return "战斗机";
  return "航空平台";
}

function classifyShip(className: string) {
  const lower = className.toLowerCase();
  if (lower.includes("carrier")) return "航母 / 航空作战";
  if (lower.includes("destroyer")) return "驱逐舰";
  if (lower.includes("frigate")) return "护卫舰";
  if (lower.includes("patrol")) return "巡逻艇";
  return "水面舰艇";
}

function UnitAssetCard({
  asset,
  active,
  onSelect,
}: {
  asset: UnitAssetRecord;
  active: boolean;
  onSelect: () => void;
}) {
  const Icon =
    UNIT_ASSET_TYPES.find((type) => type.id === asset.type)?.icon ?? Box;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "group relative overflow-hidden rounded-lg border p-3 text-left transition-colors",
        active
          ? "border-cyan-300/30 bg-cyan-300/[0.075]"
          : "border-cyan-200/10 bg-slate-950/28 hover:border-cyan-200/24 hover:bg-white/[0.04]"
      )}
    >
      <div className="relative flex gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-md border border-cyan-300/12 bg-cyan-300/[0.06] text-cyan-100">
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="mb-2 inline-flex rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-[10px] font-medium text-cyan-100">
            {asset.typeLabel}
          </span>
          <span className="block truncate text-sm font-semibold text-white">
            {asset.name}
          </span>
          <span className="mt-1 block truncate text-xs text-slate-500">
            {asset.role}
          </span>
          <span className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
            <span className="rounded-md bg-white/[0.04] px-2 py-1">
              {asset.primaryMetric}
            </span>
            <span className="rounded-md bg-white/[0.04] px-2 py-1">
              {asset.secondaryMetric}
            </span>
          </span>
        </span>
      </div>
    </button>
  );
}

function UnitAssetDetail({
  asset,
  total,
  canWrite,
  onEdit,
  onDelete,
}: {
  asset: UnitAssetRecord | null;
  total: number;
  canWrite: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  if (!asset) {
    return (
      <Card className="rounded-lg border-cyan-200/10 bg-slate-950/24 p-4">
        <div className="text-sm text-slate-500">选择一个单位查看详细参数。</div>
      </Card>
    );
  }

  const entries = Object.entries(asset.raw).filter(
    ([, value]) => typeof value !== "object" || value === null
  );
  const detailEntries = entries.map(([key, value]) => ({
    key,
    label: UNIT_ASSET_FIELD_LABELS[key] ?? key,
    value: formatAssetFieldValue(asset, key, value),
  }));
  const source =
    "dataSource" in asset.raw && asset.raw.dataSource
      ? Object.entries(asset.raw.dataSource as Record<string, string>).filter(
          ([, value]) => Boolean(value)
        )
      : [];

  return (
    <Card className="sticky top-20 h-fit overflow-hidden rounded-lg border-cyan-200/10 bg-[#08111c] p-4">
      <div className="relative">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-200/80">
              单位资产详情
            </div>
            <h3 className="mt-2 text-xl font-semibold text-white">
              {asset.name}
            </h3>
            <p className="mt-1 text-sm text-slate-500">{asset.role}</p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <span className="rounded-full border border-emerald-300/20 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-100">
              {asset.status}
            </span>
            <span className="rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-[11px] text-cyan-100">
              {asset.isSystem ? "系统默认" : "自定义"}
            </span>
          </div>
        </div>

        {canWrite && (
          <div className="mb-5 flex gap-2">
            <Button
              type="button"
              variant="ghost"
              className="h-9 flex-1 rounded-md border border-cyan-200/15 bg-white/[0.035] text-slate-200 hover:bg-white/[0.06]"
              onClick={onEdit}
            >
              <Edit3 className="size-4" />
              编辑
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-9 flex-1 rounded-md border border-red-300/15 bg-red-400/[0.04] text-red-100 hover:bg-red-400/[0.08]"
              onClick={onDelete}
            >
              <Trash2 className="size-4" />
              删除
            </Button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <DetailMetric label="资产类型" value={asset.typeLabel} />
          <DetailMetric label="资产版本" value={`v${asset.version}`} />
          <DetailMetric label="主指标" value={asset.primaryMetric} />
          <DetailMetric label="辅助指标" value={asset.secondaryMetric} />
        </div>

        <div className="mt-5">
          <div className="mb-3 text-sm font-medium text-slate-200">参数</div>
          <div className="space-y-2">
            {detailEntries.map((entry) => (
              <div
                key={entry.key}
                className="flex items-center justify-between gap-3 rounded-md border border-white/8 bg-white/[0.035] px-3 py-2 text-xs"
              >
                <span className="text-slate-500">{entry.label}</span>
                <span className="max-w-[12rem] truncate text-right text-slate-100">
                  {entry.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {source.length > 0 && (
          <div className="mt-5">
            <div className="mb-3 text-sm font-medium text-slate-200">
              数据来源
            </div>
            <div className="space-y-2">
              {source.map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-md border border-cyan-200/10 bg-cyan-200/[0.035] px-3 py-2 text-xs text-slate-400"
                >
                  <span className="mr-2 text-cyan-200">
                    {UNIT_ASSET_SOURCE_LABELS[key] ?? key}
                  </span>
                  {formatAssetFieldValue(asset, key, value)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-cyan-200/10 bg-white/[0.035] p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-slate-100">
        {value}
      </div>
    </div>
  );
}

function Empty({
  title,
  description,
  actionLabel = "新建项目",
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-cyan-200/15 bg-slate-950/30 px-6 py-10 text-center">
      <div className="grid size-10 place-items-center rounded-md border border-cyan-200/20 bg-cyan-300/10 text-cyan-200">
        <Sparkles className="size-5" />
      </div>
      <div className="mt-3 text-sm font-semibold text-slate-100">{title}</div>
      <div className="mt-1 max-w-md text-xs leading-5 text-slate-500">
        {description}
      </div>
      {onAction && (
        <Button
          type="button"
          onClick={onAction}
          className="mt-4 rounded-md border border-cyan-200/25 bg-cyan-300/12 px-3 text-cyan-50"
        >
          <Plus className="size-4" />
          {actionLabel}
        </Button>
      )}
    </div>
  );
}

function Skeleton({ view }: { view: ViewMode }) {
  if (view === "list") {
    return (
      <div className="overflow-hidden rounded-lg border border-cyan-200/10 bg-slate-950/30">
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-4 border-b border-cyan-200/5 px-4 py-4 last:border-0"
          >
            <div className="h-3 w-36 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-20 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-16 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-28 animate-pulse rounded bg-white/5" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div
          key={index}
          className="overflow-hidden rounded-lg border border-cyan-200/10 bg-[#06111f]/70"
        >
          <div className="aspect-[16/9] animate-pulse bg-white/5" />
          <div className="space-y-3 p-4">
            <div className="h-4 w-2/3 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-full animate-pulse rounded bg-white/5" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-white/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

function CreateScenarioDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("项目名称为必填");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createScenario({
        name: name.trim(),
        description: description.trim(),
        status: "draft",
        data: cloneScenarioData(name.trim()),
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose();
      }}
    >
      <Card className="w-full max-w-md rounded-lg border-cyan-200/15 bg-[#08111c] p-4 shadow-[0_10px_28px_rgba(0,0,0,0.34)]">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-md border border-cyan-200/20 bg-cyan-300/10 text-cyan-200">
            <Plus className="size-5" />
          </span>
          <div>
            <div className="text-lg font-semibold text-slate-100">
              新建推演项目
            </div>
            <div className="text-sm text-slate-500">基于空白工作区创建项目</div>
          </div>
        </div>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm text-slate-400">
              项目名称 <span className="text-red-400">*</span>
            </label>
            <input
              autoFocus
              required
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：东海防空压力分析推演"
              className="w-full rounded-md border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-200/45"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm text-slate-400">
              项目描述
            </label>
            <textarea
              rows={3}
              maxLength={500}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="简要说明本项目的推演目标、想定背景或评估方向"
              className="w-full resize-none rounded-md border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-200/45"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs text-red-100">
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={submitting}
              className="rounded-md px-3 text-slate-300 hover:bg-white/[0.06]"
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-md border border-cyan-200/25 bg-cyan-300/12 px-3 text-cyan-50"
            >
              {submitting ? "创建中..." : "创建并进入"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
