import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] transition-colors",
  {
    variants: {
      variant: {
        default: "border-cyan-300/24 bg-cyan-300/10 text-cyan-100",
        success: "border-emerald-300/24 bg-emerald-300/10 text-emerald-200",
        danger: "border-red-300/24 bg-red-500/10 text-red-200",
        muted: "border-slate-500/20 bg-white/5 text-slate-300",
        warning: "border-amber-300/24 bg-amber-300/10 text-amber-200",
        info: "border-sky-300/24 bg-sky-300/10 text-sky-200",
        offline: "border-slate-600/30 bg-slate-800/70 text-slate-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge };
