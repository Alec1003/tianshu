import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  BrainCircuit,
  Copy,
  Cpu,
  History,
  LogOut,
  Save,
  Settings,
  Signal,
  UserCircle,
} from "lucide-react";
import BrandLogo from "@/components/brand/BrandLogo";
import ThemeModeToggle from "@/components/theme/ThemeModeToggle";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/useAuth";
import type { SimulationSnapshot } from "./SimulationSidebar";

interface TopTacticalBarProps {
  snapshot: SimulationSnapshot;
  aiSidebarOpen: boolean;
  onToggleAiSidebar: () => void;
  settingsOpen?: boolean;
  onToggleSettings?: () => void;
  scenarioMeta?: {
    name: string;
    version: number;
    isTemplate?: boolean;
    description?: string;
  };
  onExit?: () => void;
  onSave?: () => void;
  onRequestSaveAs?: () => void;
  savingState?: "idle" | "saving" | "saved" | "error";
  timelineOpen?: boolean;
  onToggleTimeline?: () => void;
  mapSceneMode?: "2d" | "3d";
  onToggleMapSceneMode?: () => void;
}

export default function TopTacticalBar({
  snapshot,
  aiSidebarOpen,
  onToggleAiSidebar,
  settingsOpen,
  onToggleSettings,
  scenarioMeta,
  onExit,
  onSave,
  onRequestSaveAs,
  savingState,
  timelineOpen,
  onToggleTimeline,
  mapSceneMode = "2d",
  onToggleMapSceneMode,
}: TopTacticalBarProps) {
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement | null>(null);
  const isRunning = snapshot.runState === "running";
  const operatorName =
    user?.display_name?.trim() || user?.email?.split("@")[0] || "操作员";
  const operatorInitial = operatorName.trim().slice(0, 1).toUpperCase();

  useEffect(() => {
    if (!userMenuOpen) return;

    const closeOnPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && userMenuRef.current?.contains(target)) return;
      setUserMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setUserMenuOpen(false);
    };

    document.addEventListener("pointerdown", closeOnPointerDown);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnPointerDown);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [userMenuOpen]);

  // Calculate generic tactical balance (Active Units)
  const totalUnits = snapshot.aircraft + snapshot.ships + snapshot.facilities;

  // Find BLUE and RED for a generic advantage bar if possible
  const blueSide = snapshot.sideStats.find((s) =>
    s.id.toUpperCase().includes("BLUE")
  );
  const redSide = snapshot.sideStats.find((s) =>
    s.id.toUpperCase().includes("RED")
  );
  const blueUnits = blueSide ? blueSide.aircraft + blueSide.ships : 0;
  const redUnits = redSide ? redSide.aircraft + redSide.ships : 0;
  const showBalance = blueUnits > 0 || redUnits > 0;
  const blueRatio = showBalance
    ? (blueUnits / (blueUnits + redUnits)) * 100
    : 50;

  return (
    <header className="relative z-40 flex h-14 shrink-0 items-center justify-between border-b border-tactical-line bg-tactical-panel/96 px-4 shadow-[inset_0_-1px_0_rgba(255,255,255,0.025),0_10px_34px_rgba(0,0,0,0.22)] backdrop-blur-xl">
      {/* 1. LEFT: Platform Identity */}
      <div className="flex items-center gap-4">
        {onExit && (
          <button
            aria-label="返回想定列表"
            onClick={onExit}
            className="group flex size-8 items-center justify-center rounded-lg border border-tactical-line bg-white/[0.03] text-slate-400 transition-all hover:border-tactical-active hover:bg-tactical-accent/8 hover:text-slate-100"
            title="返回想定列表"
            type="button"
          >
            <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" />
          </button>
        )}

        <div className="flex items-center gap-3">
          <div className="relative">
            <BrandLogo
              frameClassName="size-8 rounded-lg border-tactical-line bg-white/[0.04] shadow-none"
              imageClassName="scale-[1.04]"
            />
            <div className="absolute -bottom-1 -right-1 size-2 rounded-full border border-tactical-bg bg-tactical-green" />
          </div>
          <div className="hidden sm:block">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-bold tracking-widest text-slate-100">
                天枢
              </span>
              <span className="rounded border border-tactical-line bg-white/[0.035] px-1 py-px text-[9px] text-slate-300">
                控制台
              </span>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-slate-400">
              战术推演工作站
            </div>
          </div>
        </div>

        <div className="h-6 w-px bg-tactical-line" />

        <div className="hidden lg:block">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-slate-200">
              {scenarioMeta?.name || snapshot.scenarioName || "未命名想定"}
            </span>
            {scenarioMeta?.isTemplate && (
              <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-amber-400">
                模板
              </span>
            )}
            {scenarioMeta?.version !== undefined && (
              <span className="font-mono text-[10px] text-slate-500">
                v{scenarioMeta.version}
              </span>
            )}
            {isRunning && (
              <span className="ml-1 flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[9px] uppercase tracking-widest text-emerald-400">
                <span className="tactical-state-dot size-1.5 animate-pulse rounded-full bg-emerald-400" />
                推演中
              </span>
            )}
            <span className="ml-1 flex items-center gap-1.5 rounded-md border border-tactical-line bg-white/[0.035] px-2 py-0.5 text-[9px] text-slate-300">
              <BrainCircuit className="size-3 text-tactical-accent" />
              参谋工具
            </span>
          </div>
        </div>
      </div>

      {/* 2. MIDDLE: Tactical Status Bus */}
      <div className="hidden flex-1 justify-center xl:flex">
        <div className="flex items-center gap-5 rounded-md border border-tactical-line bg-white/[0.025] px-5 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
          <div className="flex items-center gap-2">
            <Activity className="size-3 text-tactical-accent" />
            <span className="font-mono text-[10px] text-slate-400">态势</span>
            <span className="font-mono text-xs font-bold text-amber-400">
              三级
            </span>
          </div>

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <Cpu className="size-3 text-tactical-accent" />
            <span className="font-mono text-[10px] text-slate-400">AI</span>
            <span className="font-mono text-xs font-bold text-tactical-accent">
              在线
            </span>
          </div>

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <Signal
              className={cn(
                "size-3",
                isRunning ? "text-emerald-400 animate-pulse" : "text-slate-400"
              )}
            />
            <span className="font-mono text-[10px] text-slate-400">状态</span>
            <span
              className={cn(
                "font-mono text-xs font-bold",
                isRunning ? "text-emerald-400" : "text-amber-400"
              )}
            >
              {isRunning ? "运行" : "待命"}
            </span>
          </div>

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-slate-400">倍速</span>
            <span className="font-mono text-xs font-bold text-slate-200">
              {snapshot.timeCompression}x
            </span>
          </div>

          {showBalance && (
            <>
              <div className="h-3 w-px bg-white/10" />
              <div className="flex w-24 items-center gap-2">
                <span className="font-mono text-[9px] text-blue-400">蓝方</span>
                <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-red-900/50">
                  <div
                    className="absolute inset-y-0 left-0 bg-blue-500"
                    style={{ width: `${blueRatio}%` }}
                  />
                </div>
                <span className="font-mono text-[9px] text-red-400">红方</span>
              </div>
            </>
          )}

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-slate-400">单位</span>
            <span className="font-mono text-xs font-bold text-slate-200">
              {totalUnits}
            </span>
          </div>
        </div>
      </div>

      {/* 3. RIGHT: Quick Actions & Save */}
      <div className="flex items-center gap-3">
        {/* Router actions (Save / Save As) */}
        {(onSave || onRequestSaveAs) && (
          <div className="flex items-center gap-2 border-r border-tactical-line pr-3">
            {onSave && !scenarioMeta?.isTemplate && (
              <button
                type="button"
                onClick={onSave}
                disabled={savingState === "saving"}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-widest transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55",
                  savingState === "saved"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : savingState === "error"
                      ? "border-red-500/30 bg-red-500/10 text-red-300"
                      : "border-tactical-active bg-tactical-accent/10 text-slate-100 hover:border-tactical-accent/55 hover:bg-tactical-accent/14"
                )}
                title="保存到当前想定"
              >
                <Save className="size-3.5" />
                <span className="hidden sm:inline">
                  {savingState === "saving"
                    ? "保存中"
                    : savingState === "saved"
                      ? "已保存"
                      : savingState === "error"
                        ? "失败"
                        : "保存"}
                </span>
              </button>
            )}
            {onRequestSaveAs && (
              <button
                type="button"
                onClick={onRequestSaveAs}
                className="flex items-center gap-1.5 rounded-md border border-tactical-line bg-white/[0.03] px-3 py-1 text-[10px] font-semibold text-slate-300 transition-colors hover:border-tactical-active hover:bg-tactical-accent/8 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55"
                title="另存为新想定"
              >
                <Copy className="size-3.5" />
                <span className="hidden sm:inline">另存</span>
              </button>
            )}
          </div>
        )}

        <div className="hidden items-center gap-1 md:flex">
          <button
            aria-label={mapSceneMode === "3d" ? "切换二维地图" : "切换三维地图"}
            className="grid size-8 place-items-center rounded-md bg-transparent text-slate-300 transition-colors hover:bg-white/5 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!onToggleMapSceneMode}
            onClick={onToggleMapSceneMode}
            title={mapSceneMode === "3d" ? "切换为二维地图" : "切换为三维地图"}
            type="button"
          >
            <span className="font-mono text-[10px] font-bold">
              {mapSceneMode === "3d" ? "2D" : "3D"}
            </span>
          </button>
        </div>

        <div className="hidden h-6 w-px bg-tactical-line md:block" />

        <button
          aria-label={timelineOpen ? "关闭推演回放" : "打开推演回放"}
          disabled={!onToggleTimeline}
          onClick={() => onToggleTimeline && onToggleTimeline()}
          className={cn(
            "flex h-8 items-center gap-2 rounded-md border px-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55",
            timelineOpen
              ? "border-tactical-active bg-tactical-accent/10 text-slate-100"
              : "border-tactical-line bg-white/[0.03] text-slate-300 hover:border-tactical-active hover:bg-tactical-accent/8 hover:text-slate-100"
          )}
          title={timelineOpen ? "关闭推演回放" : "打开推演回放"}
          type="button"
        >
          <History className="size-4" />
          <span className="hidden font-mono text-[10px] font-bold uppercase tracking-wider sm:inline">
            回放
          </span>
        </button>

        <button
          aria-label={aiSidebarOpen ? "关闭 AI 助手" : "打开 AI 助手"}
          onClick={() => onToggleAiSidebar()}
          className={cn(
            "flex h-8 items-center gap-2 rounded-md border px-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55",
            aiSidebarOpen
              ? "border-tactical-active bg-tactical-accent/10 text-slate-100"
              : "border-tactical-line bg-white/[0.03] text-slate-300 hover:border-tactical-active hover:bg-tactical-accent/8 hover:text-slate-100"
          )}
          title={aiSidebarOpen ? "关闭 AI 助手" : "打开 AI 助手"}
          type="button"
        >
          <BrainCircuit className="size-4" />
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider">
            AI 助手
          </span>
        </button>

        <ThemeModeToggle className="size-8 text-slate-300 hover:text-slate-100" />

        <button
          aria-label={settingsOpen ? "关闭战术配置中心" : "打开战术配置中心"}
          disabled={!onToggleSettings}
          onClick={() => onToggleSettings && onToggleSettings()}
          className={cn(
            "grid size-8 place-items-center rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55",
            settingsOpen
              ? "border-tactical-active bg-tactical-accent/10 text-slate-100"
              : "border-transparent bg-transparent text-slate-300 hover:bg-white/5 hover:text-slate-100"
          )}
          title={settingsOpen ? "关闭战术配置中心" : "打开战术配置中心"}
          type="button"
        >
          <Settings className="size-4" />
        </button>

        <div className="relative ml-1" ref={userMenuRef}>
          <button
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
            aria-label="当前操作员"
            className={cn(
              "grid size-8 place-items-center rounded-full border bg-tactical-control transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55",
              userMenuOpen
                ? "border-tactical-active text-slate-100"
                : "border-tactical-line text-slate-300 hover:border-tactical-active hover:text-slate-100"
            )}
            onClick={() => setUserMenuOpen((value) => !value)}
            title="当前操作员"
            type="button"
          >
            <UserCircle className="size-6" />
          </button>

          {userMenuOpen && (
            <div
              className="absolute right-0 top-11 z-50 w-72 overflow-hidden rounded-lg border border-tactical-line bg-tactical-panel/98 shadow-[0_18px_44px_rgba(0,0,0,0.38)] backdrop-blur-xl"
              role="menu"
            >
              <div className="border-b border-white/10 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid size-10 place-items-center rounded-full border border-tactical-line bg-white/[0.04] font-mono text-sm font-bold text-slate-100">
                    {operatorInitial}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-100">
                      {operatorName}
                    </div>
                    <div className="truncate font-mono text-[11px] text-slate-500">
                      {user?.email ?? "未登录"}
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <span className="rounded border border-tactical-line bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-300">
                    {user?.is_superuser ? "管理员" : "操作员"}
                  </span>
                  {user?.is_verified && (
                    <span className="rounded border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-emerald-300">
                      已验证
                    </span>
                  )}
                </div>
              </div>

              {onToggleSettings && (
                <button
                  className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-slate-300 transition-colors hover:bg-white/[0.045] hover:text-slate-100"
                  onClick={() => {
                    setUserMenuOpen(false);
                    onToggleSettings();
                  }}
                  role="menuitem"
                  type="button"
                >
                  <Settings className="size-4" />
                  打开配置中心
                </button>
              )}

              <button
                className="flex w-full items-center gap-3 border-t border-white/10 px-4 py-3 text-left text-sm text-red-200 transition-colors hover:bg-red-500/10 hover:text-red-100"
                onClick={() => {
                  setUserMenuOpen(false);
                  logout();
                }}
                role="menuitem"
                type="button"
              >
                <LogOut className="size-4" />
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
