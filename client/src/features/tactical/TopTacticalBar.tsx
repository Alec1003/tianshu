import { motion } from "framer-motion";
import {
  Activity,
  ArrowLeft,
  BrainCircuit,
  Copy,
  Cpu,
  Save,
  Settings,
  Shield,
  Signal,
  UserCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
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
  mapSceneMode = "2d",
  onToggleMapSceneMode,
}: TopTacticalBarProps) {
  const isRunning = snapshot.runState === "running";

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
    <header className="relative z-40 flex h-14 shrink-0 items-center justify-between border-b border-cyan-400/20 bg-[#01040a]/90 px-4 backdrop-blur-2xl shadow-[0_4px_30px_rgba(8,145,178,0.1)]">
      {/* Background Scanning Animation */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-20">
        <motion.div
          animate={{ x: ["-100%", "200%"] }}
          transition={{ repeat: Infinity, duration: 8, ease: "linear" }}
          className="h-full w-1/4 bg-gradient-to-r from-transparent via-cyan-400/10 to-transparent skew-x-12"
        />
      </div>

      {/* 1. LEFT: Platform Identity */}
      <div className="flex items-center gap-4">
        {onExit && (
          <button
            aria-label="返回想定列表"
            onClick={onExit}
            className="group flex size-8 items-center justify-center rounded-lg border border-cyan-400/20 bg-cyan-950/20 text-cyan-500/70 transition-all hover:border-cyan-400/50 hover:bg-cyan-400/10 hover:text-cyan-300 hover:shadow-[0_0_12px_rgba(34,211,238,0.15)]"
            title="返回想定列表"
            type="button"
          >
            <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" />
          </button>
        )}

        <div className="flex items-center gap-3">
          <div className="relative grid size-8 place-items-center rounded-lg border border-cyan-400/30 bg-cyan-950/40 text-cyan-300 shadow-[0_0_12px_rgba(34,211,238,0.2)]">
            <Shield className="size-4" />
            <div className="absolute -bottom-1 -right-1 size-2.5 rounded-full border border-[#01040a] bg-emerald-400" />
          </div>
          <div className="hidden sm:block">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-bold tracking-widest text-slate-100">
                AICC
              </span>
              <span className="rounded border border-cyan-400/20 bg-cyan-400/10 px-1 py-px font-mono text-[9px] uppercase text-cyan-300">
                指挥
              </span>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-cyan-500/70">
              AI 战术指挥网络
            </div>
          </div>
        </div>

        <div className="h-6 w-px bg-cyan-400/20" />

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
                <span className="size-1.5 animate-pulse rounded-full bg-emerald-400" />
                推演中
              </span>
            )}
            <span className="ml-1 flex items-center gap-1.5 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2 py-0.5 text-[9px] uppercase tracking-widest text-cyan-300">
              <BrainCircuit className="size-3" />
              AI 驱动中
            </span>
          </div>
        </div>
      </div>

      {/* 2. MIDDLE: Tactical Status Bus */}
      <div className="hidden flex-1 justify-center xl:flex">
        <div className="flex items-center gap-6 rounded-full border border-white/5 bg-white/[0.02] px-6 py-1.5 shadow-inner">
          <div className="flex items-center gap-2">
            <Activity className="size-3 text-cyan-500" />
            <span className="font-mono text-[10px] text-slate-400">态势</span>
            <span className="font-mono text-xs font-bold text-amber-400">
              三级
            </span>
          </div>

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <Cpu className="size-3 text-cyan-500" />
            <span className="font-mono text-[10px] text-slate-400">AI</span>
            <span className="font-mono text-xs font-bold text-cyan-400 shadow-cyan-400 drop-shadow-md">
              在线
            </span>
          </div>

          <div className="h-3 w-px bg-white/10" />

          <div className="flex items-center gap-2">
            <Signal
              className={cn(
                "size-3",
                isRunning ? "text-emerald-400 animate-pulse" : "text-slate-500"
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
                    className="absolute inset-y-0 left-0 bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"
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
          <div className="flex items-center gap-2 pr-3 border-r border-cyan-400/20">
            {onSave && !scenarioMeta?.isTemplate && (
              <button
                type="button"
                onClick={onSave}
                disabled={savingState === "saving"}
                className={cn(
                  "flex items-center gap-1.5 rounded border px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-widest transition-all",
                  savingState === "saved"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : savingState === "error"
                      ? "border-red-500/30 bg-red-500/10 text-red-300"
                      : "border-cyan-400/30 bg-cyan-400/10 text-cyan-300 hover:border-cyan-400/50 hover:bg-cyan-400/20 hover:shadow-[0_0_8px_rgba(34,211,238,0.15)]"
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
                className="flex items-center gap-1.5 rounded border border-white/10 bg-white/5 px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-widest text-slate-300 transition-all hover:border-cyan-400/30 hover:bg-cyan-400/5 hover:text-cyan-300 hover:shadow-[0_0_8px_rgba(34,211,238,0.1)]"
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
            className="grid size-8 place-items-center rounded bg-transparent text-slate-400 transition-colors hover:bg-white/5 hover:text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
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

        <div className="hidden h-6 w-px bg-cyan-400/20 md:block" />

        <button
          aria-label={aiSidebarOpen ? "关闭 AI 助手" : "打开 AI 助手"}
          onClick={() => onToggleAiSidebar()}
          className={cn(
            "flex h-8 items-center gap-2 rounded border px-3 transition-all",
            aiSidebarOpen
              ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-300 shadow-[0_0_12px_rgba(34,211,238,0.2)]"
              : "border-white/5 bg-white/5 text-slate-300 hover:border-cyan-400/30 hover:bg-cyan-400/5 hover:text-cyan-300"
          )}
          title={aiSidebarOpen ? "关闭 AI 助手" : "打开 AI 助手"}
          type="button"
        >
          <BrainCircuit className="size-4" />
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider">
            AI 助手
          </span>
        </button>

        <button
          aria-label={settingsOpen ? "关闭战术配置中心" : "打开战术配置中心"}
          disabled={!onToggleSettings}
          onClick={() => onToggleSettings && onToggleSettings()}
          className={cn(
            "grid size-8 place-items-center rounded border transition-all",
            settingsOpen
              ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-300"
              : "border-transparent bg-transparent text-slate-400 hover:bg-white/5 hover:text-cyan-300"
          )}
          title={settingsOpen ? "关闭战术配置中心" : "打开战术配置中心"}
          type="button"
        >
          <Settings className="size-4" />
        </button>

        <button
          aria-label="当前操作员"
          className="ml-1 grid size-8 place-items-center rounded-full border border-cyan-400/20 bg-[#01040a]"
          title="当前操作员"
          type="button"
        >
          <UserCircle className="size-6 text-slate-400" />
        </button>
      </div>
    </header>
  );
}
