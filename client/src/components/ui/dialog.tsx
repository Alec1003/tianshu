import * as React from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
  labelledBy?: string;
}

function Dialog({
  open,
  onOpenChange,
  children,
  className,
  labelledBy,
}: DialogProps) {
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
    <div
      aria-labelledby={labelledBy}
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
    >
      <button
        aria-label="关闭弹窗"
        className="absolute inset-0 cursor-default"
        onClick={() => onOpenChange?.(false)}
        type="button"
      />
      <div
        className={cn(
          "relative max-h-[90vh] w-full max-w-lg overflow-hidden rounded-lg border border-cyan-300/14 bg-[#08111c] text-slate-100 shadow-[0_12px_40px_rgba(0,0,0,0.42)]",
          className
        )}
      >
        {children}
      </div>
    </div>
  );
}

function DialogHeader({
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

function DialogTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        "text-sm font-semibold tracking-normal text-slate-50",
        className
      )}
      {...props}
    />
  );
}

function DialogDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("mt-1 text-xs leading-5 text-slate-400", className)}
      {...props}
    />
  );
}

function DialogContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("overflow-y-auto p-4", className)} {...props} />;
}

function DialogFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 border-t border-cyan-300/10 px-4 py-3",
        className
      )}
      {...props}
    />
  );
}

function DialogCloseButton({
  className,
  onClick,
}: {
  className?: string;
  onClick?: () => void;
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

export {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogContent,
  DialogFooter,
  DialogCloseButton,
};
