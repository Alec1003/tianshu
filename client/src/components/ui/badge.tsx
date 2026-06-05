import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium leading-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.025)] transition-colors",
  {
    variants: {
      variant: {
        default: "border-tactical-active bg-tactical-accent/10 text-slate-100",
        success:
          "border-tactical-green/30 bg-tactical-green/10 text-emerald-100",
        danger: "border-tactical-red/32 bg-tactical-red/10 text-red-100",
        muted: "border-tactical-line bg-white/[0.035] text-slate-300",
        warning: "border-tactical-amber/32 bg-tactical-amber/10 text-amber-100",
        info: "border-tactical-active bg-tactical-accent/10 text-slate-100",
        offline: "border-slate-600/25 bg-slate-900/62 text-slate-400",
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
