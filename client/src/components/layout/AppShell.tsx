import * as React from "react";
import type { LucideIcon } from "lucide-react";

import BrandLogo from "@/components/brand/BrandLogo";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface AppShellNavItem {
  id: string;
  label: string;
  caption?: string;
  icon: LucideIcon;
  badge?: string | number;
}

interface AppShellProps {
  navItems: AppShellNavItem[];
  activeNavItem: string;
  onNavItemSelect: (id: string) => void;
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: React.ReactNode;
  topRight?: React.ReactNode;
  children: React.ReactNode;
  rightPanel?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

function AppShell({
  navItems,
  activeNavItem,
  onNavItemSelect,
  title,
  description,
  eyebrow,
  actions,
  topRight,
  children,
  rightPanel,
  footer,
  className,
}: AppShellProps) {
  return (
    <div
      className={cn(
        "dark min-h-screen overflow-hidden bg-[#050812] text-slate-100",
        className
      )}
    >
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] border-r border-cyan-300/10 bg-[#070c16] px-3 py-4 shadow-[inset_-1px_0_0_rgba(125,211,252,0.03)] lg:flex lg:flex-col">
        <div className="flex items-center gap-3 px-2">
          <BrandLogo frameClassName="size-9 rounded-lg shadow-none backdrop-blur-none" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-50">
              TianShu
            </div>
            <div className="truncate text-[11px] text-slate-400">
              AI Command Center
            </div>
          </div>
        </div>

        <nav className="mt-6 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.id === activeNavItem;
            return (
              <button
                key={item.id}
                className={cn(
                  "group flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/55",
                  active
                    ? "border-cyan-300/20 bg-cyan-300/10 text-cyan-50"
                    : "border-transparent text-slate-300 hover:bg-white/[0.045] hover:text-slate-100"
                )}
                onClick={() => onNavItemSelect(item.id)}
                type="button"
              >
                <span
                  className={cn(
                    "grid size-8 shrink-0 place-items-center rounded-md border",
                    active
                      ? "border-cyan-300/18 bg-cyan-300/10 text-cyan-100"
                      : "border-slate-800 bg-slate-950/45 text-slate-400 group-hover:text-slate-200"
                  )}
                >
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium">
                    {item.label}
                  </span>
                  {item.caption ? (
                    <span className="mt-0.5 block truncate text-[11px] text-slate-400">
                      {item.caption}
                    </span>
                  ) : null}
                </span>
                {item.badge !== undefined ? (
                  <Badge variant={active ? "default" : "offline"}>
                    {item.badge}
                  </Badge>
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="mt-auto px-2 text-[11px] leading-5 text-slate-500">
          {footer ?? (
            <>
              <div>运行边界: 后端 Runtime</div>
              <div>v0.2.0</div>
            </>
          )}
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col lg:pl-[232px]">
        <header className="sticky top-0 z-20 border-b border-cyan-300/10 bg-[#050812]/96 backdrop-blur-xl">
          <div className="flex min-h-[64px] items-center gap-3 px-4 py-3 lg:px-5">
            <div className="lg:hidden">
              <BrandLogo frameClassName="size-9 rounded-lg shadow-none backdrop-blur-none" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-2">
                {eyebrow ? (
                  <Badge className="hidden sm:inline-flex" variant="info">
                    {eyebrow}
                  </Badge>
                ) : null}
                <h1 className="truncate text-base font-semibold text-slate-50">
                  {title}
                </h1>
              </div>
              {description ? (
                <p className="mt-1 max-w-3xl truncate text-xs text-slate-500">
                  {description}
                </p>
              ) : null}
            </div>
            {actions ? (
              <div className="flex shrink-0 items-center gap-2">{actions}</div>
            ) : null}
            {topRight ? <div className="shrink-0">{topRight}</div> : null}
          </div>
          <nav className="flex gap-2 overflow-x-auto border-t border-cyan-300/8 px-4 py-2 lg:hidden">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.id === activeNavItem;
              return (
                <button
                  key={item.id}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                    active
                      ? "border-cyan-300/22 bg-cyan-300/10 text-cyan-50"
                      : "border-transparent text-slate-400 hover:bg-white/[0.045] hover:text-slate-100"
                  )}
                  onClick={() => onNavItemSelect(item.id)}
                  type="button"
                >
                  <Icon className="size-3.5" />
                  <span>{item.label}</span>
                  {item.badge !== undefined ? (
                    <Badge variant={active ? "default" : "offline"}>
                      {item.badge}
                    </Badge>
                  ) : null}
                </button>
              );
            })}
          </nav>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-5">
          {rightPanel ? (
            <div className="grid min-h-full gap-4 xl:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_392px]">
              <div className="min-w-0">{children}</div>
              <div className="min-w-0">{rightPanel}</div>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}

export { AppShell };
