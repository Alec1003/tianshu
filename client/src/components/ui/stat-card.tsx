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
  cyan: "text-slate-100 bg-tactical-accent/10 border-tactical-active",
  green: "text-emerald-100 bg-tactical-green/10 border-tactical-green/25",
  amber: "text-amber-100 bg-tactical-amber/10 border-tactical-amber/25",
  red: "text-red-100 bg-tactical-red/10 border-tactical-red/25",
  slate: "text-slate-200 bg-white/[0.03] border-tactical-line",
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
          <div className="mt-1 truncate font-mono text-lg font-semibold tabular-nums text-slate-50">
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
