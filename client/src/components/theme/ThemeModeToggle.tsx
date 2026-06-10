import { useContext } from "react";
import { Moon, SunMedium } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeModeContext } from "@/gui/contextProviders/contexts/ThemeModeContext";
import { cn } from "@/lib/utils";

interface ThemeModeToggleProps {
  className?: string;
  showLabel?: boolean;
}

export default function ThemeModeToggle({
  className,
  showLabel = false,
}: ThemeModeToggleProps) {
  const { mode, toggleMode } = useContext(ThemeModeContext);
  const nextLabel = mode === "dark" ? "切换到浅色模式" : "切换到暗色模式";
  const Icon = mode === "dark" ? SunMedium : Moon;

  return (
    <Button
      aria-label={nextLabel}
      className={cn(showLabel ? "gap-2 px-3" : "size-9", className)}
      onClick={toggleMode}
      size={showLabel ? "sm" : "icon"}
      title={nextLabel}
      type="button"
      variant="ghost"
    >
      <Icon className="size-4" />
      {showLabel ? <span>{mode === "dark" ? "浅色" : "暗色"}</span> : null}
    </Button>
  );
}
