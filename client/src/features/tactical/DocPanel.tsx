import { useEffect, useState } from "react";
import { FileText, Folder, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface DocFile {
  name: string;
  size_bytes: number;
  size_kb: number;
  modified: string;
}

interface DocPanelProps {
  docFolder?: string;
  onPreview: (filename: string) => void;
  previewFile: string | null;
}

export default function DocPanel({ docFolder, onPreview, previewFile }: DocPanelProps) {
  const [files, setFiles] = useState<DocFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!docFolder) {
      setFiles([]);
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    setError(null);
    const params = `?doc_folder=${encodeURIComponent(docFolder)}`;
    fetch(`/api/doc/list${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject("Failed to load")))
      .then((data) => {
        if (!cancelled) setFiles(data.files ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [docFolder]);

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-xs text-slate-500">
        <Loader2 className="mr-2 size-4 animate-spin text-cyan-300" />
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-red-400/20 bg-red-500/[0.06] px-3 py-2 text-xs text-red-300">
        {error}
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-xs text-slate-500">
        <Folder className="size-8 text-slate-600" />
        <span className="max-w-full truncate text-slate-400">
          {docFolder ?? "未绑定项目文件夹"}
        </span>
        <span>暂无文档</span>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {files.map((file) => (
        <button
          className={cn(
            "flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left text-xs transition-colors",
            previewFile === file.name
              ? "border-tactical-active bg-tactical-accent/10 text-slate-100"
              : "border-transparent hover:border-tactical-line hover:bg-white/[0.03] text-slate-400"
          )}
          key={file.name}
          onClick={() => onPreview(file.name)}
          type="button"
        >
          <FileText className="mt-0.5 size-4 shrink-0 text-cyan-300/70" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-slate-200">
              {file.name}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {file.size_kb} KB · {formatDate(file.modified)}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
