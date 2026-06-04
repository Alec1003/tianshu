import * as React from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DrawerProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
  side?: "right" | "left";
}

function Drawer({
  open,
  onOpenChange,
  children,
  className,
  side = "right",
}: DrawerProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange?.(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onOpenChange, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60">
      <button
        aria-label="关闭抽屉"
        className="absolute inset-0 cursor-default"
        onClick={() => onOpenChange?.(false)}
        type="button"
      />
      <aside
        className={cn(
          "absolute inset-y-0 w-[min(420px,calc(100vw-1rem))] overflow-hidden border-cyan-300/14 bg-[#08111c] text-slate-100 shadow-[0_12px_40px_rgba(0,0,0,0.42)]",
          side === "right" ? "right-0 border-l" : "left-0 border-r",
          className
        )}
      >
        {children}
      </aside>
    </div>
  );
}

function DrawerHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("border-b border-cyan-300/10 px-4 py-3", className)}
      {...props}
    />
  );
}

function DrawerTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("text-sm font-semibold text-slate-50", className)}
      {...props}
    />
  );
}

function DrawerContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("h-full overflow-y-auto p-4", className)} {...props} />
  );
}

function DrawerCloseButton({
  onClick,
  className,
}: {
  onClick?: () => void;
  className?: string;
}) {
  return (
    <Button
      aria-label="关闭"
      className={cn("absolute right-3 top-3", className)}
      onClick={onClick}
      size="icon"
      type="button"
      variant="ghost"
    >
      <X className="size-4" />
    </Button>
  );
}

export { Drawer, DrawerHeader, DrawerTitle, DrawerContent, DrawerCloseButton };
