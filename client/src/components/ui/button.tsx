import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-cyan-300/20 bg-cyan-400/12 text-cyan-100 shadow-[0_0_28px_rgba(76,201,240,0.12)] hover:border-cyan-300/55 hover:bg-cyan-400/18",
        ghost:
          "text-slate-300 hover:bg-white/6 hover:text-cyan-100 hover:shadow-[inset_0_0_0_1px_rgba(76,201,240,0.18)]",
        tactical:
          "border border-cyan-300/25 bg-[#081523]/86 text-cyan-100 hover:border-cyan-300/55 hover:bg-cyan-400/12 hover:shadow-hud-cyan",
        danger:
          "border border-red-400/25 bg-red-500/10 text-red-100 hover:border-red-300/55 hover:bg-red-500/16 hover:shadow-hud-red",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 rounded-lg px-5",
        icon: "size-10",
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
