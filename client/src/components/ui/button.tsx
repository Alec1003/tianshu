import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border text-xs font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#050812] active:translate-y-px disabled:pointer-events-none disabled:opacity-45 motion-reduce:transition-none motion-reduce:active:translate-y-0 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border-cyan-300/28 bg-cyan-300/12 text-cyan-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.045)] hover:border-cyan-300/50 hover:bg-cyan-300/18 hover:shadow-hud-cyan",
        secondary:
          "border-slate-700/80 bg-slate-900/78 text-slate-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] hover:border-slate-500/90 hover:bg-slate-800/90 hover:text-slate-50",
        outline:
          "border-cyan-300/18 bg-slate-950/20 text-slate-200 hover:border-cyan-300/38 hover:bg-cyan-300/10 hover:text-cyan-50",
        ghost:
          "border-transparent bg-transparent text-slate-400 hover:border-white/10 hover:bg-white/[0.055] hover:text-slate-100",
        tactical:
          "border-cyan-300/22 bg-[#0b1826] text-cyan-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] hover:border-cyan-300/42 hover:bg-cyan-300/12 hover:text-cyan-50",
        danger:
          "border-red-400/28 bg-red-500/10 text-red-100 hover:border-red-300/50 hover:bg-red-500/18 hover:text-red-50 hover:shadow-hud-red",
        destructive:
          "border-red-400/28 bg-red-500/10 text-red-100 hover:border-red-300/50 hover:bg-red-500/18 hover:text-red-50 hover:shadow-hud-red",
      },
      size: {
        default: "h-9 px-3 py-2",
        sm: "h-8 px-2.5",
        lg: "h-10 px-4",
        icon: "size-9 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
