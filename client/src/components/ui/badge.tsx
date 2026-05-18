import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-cyan-300/24 bg-cyan-300/10 text-cyan-100",
        success: "border-emerald-300/24 bg-emerald-300/10 text-emerald-200",
        danger: "border-red-300/24 bg-red-500/10 text-red-200",
        muted: "border-slate-500/20 bg-white/5 text-slate-300",
        warning: "border-amber-300/24 bg-amber-300/10 text-amber-200",
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
