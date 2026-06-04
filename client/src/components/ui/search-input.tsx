import * as React from "react";
import { Search, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface SearchInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  onClear?: () => void;
}

const SearchInput = React.forwardRef<HTMLInputElement, SearchInputProps>(
  ({ className, onClear, value, ...props }, ref) => (
    <div className={cn("relative min-w-0", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
      <input
        ref={ref}
        type="search"
        value={value}
        className="h-9 w-full rounded-md border border-cyan-300/12 bg-slate-950/60 pl-9 pr-8 text-xs text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-300/35 focus:ring-2 focus:ring-cyan-300/10"
        {...props}
      />
      {onClear && value ? (
        <button
          aria-label="清空搜索"
          className="absolute right-2 top-1/2 grid size-5 -translate-y-1/2 place-items-center rounded text-slate-500 hover:bg-white/5 hover:text-slate-200"
          onClick={onClear}
          type="button"
        >
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  )
);
SearchInput.displayName = "SearchInput";

export { SearchInput };
