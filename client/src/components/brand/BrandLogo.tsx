import DubheMark from "@/gui/assets/svg/dubhe-mark.svg";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  frameClassName?: string;
  imageClassName?: string;
}

export function BrandLogo({
  className,
  frameClassName,
  imageClassName,
}: Readonly<BrandLogoProps>) {
  return (
    <div className={cn("relative", className)}>
      <div
        className={cn(
          "relative grid place-items-center overflow-hidden rounded-2xl border border-cyan-200/20 bg-white/[0.04] shadow-[0_0_32px_rgba(56,189,248,0.16)] backdrop-blur-xl",
          frameClassName
        )}
      >
        <div className="absolute inset-2 rounded-xl bg-gradient-to-br from-cyan-300/20 to-blue-500/16" />
        <img
          src={DubheMark}
          alt="天枢平台 Logo"
          className={cn(
            "relative z-10 h-[68%] w-[68%] object-contain",
            imageClassName
          )}
        />
      </div>
    </div>
  );
}

export default BrandLogo;
