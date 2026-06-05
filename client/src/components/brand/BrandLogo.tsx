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
          "relative grid place-items-center overflow-hidden rounded-lg border border-cyan-200/16 bg-cyan-300/[0.06]",
          frameClassName
        )}
      >
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
