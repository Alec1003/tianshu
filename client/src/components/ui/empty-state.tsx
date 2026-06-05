import * as React from "react";
import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-44 flex-col items-center justify-center rounded-lg border border-dashed border-cyan-300/14 bg-slate-950/35 px-6 py-8 text-center",
        className
      )}
    >
      <div className="grid size-10 place-items-center rounded-md border border-cyan-300/16 bg-cyan-300/8 text-cyan-200">
        {icon ?? <Inbox className="size-5" />}
      </div>
      <h3 className="mt-3 text-sm font-semibold text-slate-100">{title}</h3>
      {description ? (
        <p className="mt-1 max-w-md text-xs leading-5 text-slate-500">
          {description}
        </p>
      ) : null}
      {actionLabel && onAction ? (
        <Button className="mt-4" onClick={onAction} type="button">
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}

export { EmptyState };
