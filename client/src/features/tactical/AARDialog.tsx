import { AnimatePresence, motion } from "framer-motion";
import { Crown, RefreshCcw, Trophy, X } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { GameOutcome, GameOutcomeReason } from "@/game/Game";
import type { ObjectiveDestroyedEvent } from "@/game/Scenario";

import { localizeSideName } from "@/i18n/entityNames";

const sideNameAlias: Record<string, string> = {
  ALLY: "盟友",
  BLUE: "蓝方",
  NEUTRAL: "中立",
  RED: "红方",
};

function normalizeSideName(name: string) {
  return sideNameAlias[name.toUpperCase()] ?? localizeSideName(name);
}

const reasonLabel: Record<GameOutcomeReason, string> = {
  "": "推演进行中",
  KEY_UNIT_DESTROYED: "关键单位被毁",
  ANNIHILATION: "全歼对手",
  TIMEOUT: "推演时长耗尽",
};

const reasonHint: Record<GameOutcomeReason, string> = {
  "": "",
  KEY_UNIT_DESTROYED:
    "关键目标（isObjective）已被击毁，由攻击方直接判胜，额外加 200 分。",
  ANNIHILATION:
    "对方所有作战单位（飞机 + 舰船 + 防空设施 + 机场）已全部覆灭。",
  TIMEOUT: "推演到达预设时长，按总分裁定胜方；分数相等时取首个登记方。",
};

const unitTypeLabel: Record<ObjectiveDestroyedEvent["unitType"], string> = {
  aircraft: "飞机",
  ship: "舰船",
  facility: "防空设施",
  airbase: "机场",
  weapon: "武器",
};

export interface AARSideEntry {
  id: string;
  name: string;
  colorHex: string;
  score: number;
  aircraft: number;
  ships: number;
  facilities: number;
  airbases: number;
}

interface AARDialogProps {
  open: boolean;
  onClose: () => void;
  onReset?: () => void;
  outcome: GameOutcome;
  sides: AARSideEntry[];
  scenarioName: string;
  elapsedLabel: string;
  objectiveEvent: ObjectiveDestroyedEvent | null;
}

function formatScore(value: number) {
  return Math.round(value).toLocaleString("zh-CN");
}

export default function AARDialog({
  open,
  onClose,
  onReset,
  outcome,
  sides,
  scenarioName,
  elapsedLabel,
  objectiveEvent,
}: AARDialogProps) {
  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (typeof document === "undefined") return null;

  const winner = sides.find((side) => side.id === outcome.winnerSideId);
  const sortedSides = [...sides].sort((a, b) => b.score - a.score);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-[200] grid place-items-center bg-[#020611]/82 px-4 backdrop-blur-md"
          exit={{ opacity: 0 }}
          initial={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
          transition={{ duration: 0.18 }}
        >
          <motion.div
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-cyan-300/20 bg-gradient-to-br from-[#06101e]/96 via-[#040b18]/96 to-[#020611]/96 shadow-[0_28px_120px_rgba(8,28,56,0.65)]"
            exit={{ opacity: 0, scale: 0.94, y: 12 }}
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            <div className="pointer-events-none absolute inset-0 opacity-30 [background:radial-gradient(120%_60%_at_50%_-10%,rgba(56,189,248,0.55),transparent_70%)]" />
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/55 to-transparent" />
            <button
              aria-label="关闭"
              className="absolute right-4 top-4 z-10 grid size-8 place-items-center rounded-full border border-cyan-300/15 bg-slate-950/55 text-slate-400 transition-colors hover:border-cyan-300/45 hover:text-cyan-100"
              onClick={onClose}
              type="button"
            >
              <X className="size-4" />
            </button>

            <div className="relative px-6 pt-7">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.32em] text-cyan-300/70">
                <Trophy className="size-3" />
                推演结束
              </div>
              <h2 className="mt-2 text-2xl font-semibold text-slate-100">
                {winner ? `${normalizeSideName(winner.name)} 获胜` : "胜负未定"}
              </h2>
              <div className="mt-1 text-xs text-slate-500">
                {scenarioName} · 推演用时 {elapsedLabel}
              </div>

              <div className="mt-4 rounded-xl border border-cyan-300/15 bg-cyan-300/4 p-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-cyan-100">
                  <Crown className="size-4" />
                  {reasonLabel[outcome.reason]}
                </div>
                <div className="mt-1 text-[12px] leading-relaxed text-slate-400">
                  {reasonHint[outcome.reason]}
                </div>
              </div>

              {objectiveEvent && (
                <div className="mt-3 rounded-xl border border-rose-400/20 bg-rose-500/8 p-3 text-[12px] leading-relaxed text-rose-100/80">
                  关键{unitTypeLabel[objectiveEvent.unitType]}{" "}
                  <span className="font-semibold text-rose-100">
                    {objectiveEvent.unitName}
                  </span>{" "}
                  已被击毁，攻击方记一场决定性胜利。
                </div>
              )}
            </div>

            <div className="px-6 pb-6 pt-4">
              <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.24em] text-slate-500">
                <span>各方战绩</span>
                <span>得分 / 剩余单位</span>
              </div>
              <div className="space-y-2">
                {sortedSides.map((side, index) => {
                  const remainingUnits =
                    side.aircraft + side.ships + side.facilities + side.airbases;
                  const isWinner = side.id === outcome.winnerSideId;
                  return (
                    <div
                      className={cn(
                        "rounded-xl border p-3 transition-colors",
                        isWinner
                          ? "border-cyan-300/45 bg-cyan-300/8"
                          : "border-cyan-300/12 bg-slate-950/45"
                      )}
                      key={side.id}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <span
                            className="size-3 shrink-0 rounded-full ring-2 ring-slate-950"
                            style={{ background: side.colorHex }}
                          />
                          <span
                            className={cn(
                              "truncate text-sm font-semibold",
                              isWinner ? "text-cyan-50" : "text-slate-200"
                            )}
                          >
                            {normalizeSideName(side.name)}
                          </span>
                          {index === 0 && sortedSides.length > 1 && (
                            <span className="rounded-full border border-cyan-300/45 px-1.5 py-px text-[9px] uppercase tracking-[0.18em] text-cyan-100">
                              #1
                            </span>
                          )}
                        </div>
                        <div className="text-right">
                          <div
                            className={cn(
                              "text-lg font-bold leading-none",
                              isWinner ? "text-cyan-100" : "text-slate-200"
                            )}
                          >
                            {formatScore(side.score)}
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-500">
                            剩余 {remainingUnits} 单位
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 grid grid-cols-4 gap-2 text-[11px] text-slate-400">
                        <div>
                          <div className="text-slate-500">飞机</div>
                          <div className="font-semibold text-slate-200">
                            {side.aircraft}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-500">舰船</div>
                          <div className="font-semibold text-slate-200">
                            {side.ships}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-500">SAM</div>
                          <div className="font-semibold text-slate-200">
                            {side.facilities}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-500">机场</div>
                          <div className="font-semibold text-slate-200">
                            {side.airbases}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-5 flex items-center justify-end gap-2">
                <Button onClick={onClose} variant="ghost">
                  关闭
                </Button>
                {onReset && (
                  <Button
                    onClick={() => {
                      onReset();
                      onClose();
                    }}
                    variant="tactical"
                  >
                    <RefreshCcw className="mr-1.5 size-4" />
                    重新开局
                  </Button>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
