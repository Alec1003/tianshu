import * as React from "react";

import { cn } from "@/lib/utils";

function Tabs({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "inline-flex overflow-hidden rounded-md border border-cyan-300/12 bg-slate-950/55 p-0.5",
        className
      )}
      {...props}
    />
  );
}

interface TabButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

const TabButton = React.forwardRef<HTMLButtonElement, TabButtonProps>(
  ({ active, className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex h-8 items-center justify-center gap-2 rounded px-2.5 text-xs font-medium text-slate-500 transition-colors hover:text-slate-200",
        active && "bg-cyan-300/12 text-cyan-100",
        className
      )}
      type="button"
      {...props}
    />
  )
);
TabButton.displayName = "TabButton";

export { Tabs, TabButton };
