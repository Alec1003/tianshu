import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  caption?: string;
  icon?: LucideIcon;
  tone?: "cyan" | "green" | "amber" | "red" | "slate";
}

const toneClass: Record<NonNullable<StatCardProps["tone"]>, string> = {
  cyan: "text-cyan-200 bg-cyan-300/8 border-cyan-300/16",
  green: "text-emerald-200 bg-emerald-300/8 border-emerald-300/16",
  amber: "text-amber-200 bg-amber-300/8 border-amber-300/16",
  red: "text-red-200 bg-red-300/8 border-red-300/16",
  slate: "text-slate-200 bg-white/[0.035] border-slate-700/70",
};

function StatCard({
  label,
  value,
  caption,
  icon: Icon,
  tone = "cyan",
}: StatCardProps) {
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[11px] text-slate-400">{label}</div>
          <div className="mt-1 truncate text-lg font-semibold tabular-nums text-slate-50">
            {value}
          </div>
          {caption ? (
            <div className="mt-1 truncate text-[11px] text-slate-400">
              {caption}
            </div>
          ) : null}
        </div>
        {Icon ? (
          <span
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-md border",
              toneClass[tone]
            )}
          >
            <Icon className="size-4" />
          </span>
        ) : null}
      </div>
    </Card>
  );
}

export { StatCard };
