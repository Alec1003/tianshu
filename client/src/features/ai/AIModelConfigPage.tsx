import { ArrowLeft, Bot } from "lucide-react";
import { useNavigate } from "react-router-dom";

import ModelConfigCenter from "./ModelConfigCenter";

export default function AIModelConfigPage() {
  const navigate = useNavigate();

  return (
    <div className="tactical-grid relative flex min-h-screen items-center justify-center overflow-hidden bg-[#030712] px-4 py-6 text-slate-100 sm:px-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_12%,rgba(34,211,238,0.16),transparent_28%),radial-gradient(circle_at_82%_22%,rgba(59,130,246,0.13),transparent_30%),linear-gradient(180deg,rgba(3,7,18,0.12),rgba(3,7,18,0.88))]" />
      <div className="relative flex w-full max-w-[960px] flex-col">
        <header className="mb-3 flex items-center justify-between gap-3">
          <button
            className="inline-flex h-8 items-center gap-2 rounded-md border border-cyan-300/10 bg-slate-950/40 px-2.5 text-sm text-slate-400 transition-colors hover:border-cyan-300/25 hover:bg-slate-900/80 hover:text-slate-100"
            onClick={() => navigate(-1)}
            type="button"
          >
            <ArrowLeft className="size-4" />
            返回
          </button>
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-300/[0.06] px-3 py-1 text-xs text-cyan-100 shadow-[0_0_28px_rgba(34,211,238,0.08)] backdrop-blur">
            <Bot className="size-3.5" />
            AI 模型配置中心
          </div>
        </header>

        <ModelConfigCenter />
      </div>
    </div>
  );
}
