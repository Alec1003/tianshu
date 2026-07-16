import { useEffect, useRef, useState } from "react";
import { Download, Loader2, X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { renderAsync } from "docx-preview";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

interface DocPreviewProps {
  filename: string;
  onClose: () => void;
  docFolder?: string;
}

export default function DocPreview({
  filename,
  onClose,
  docFolder,
}: DocPreviewProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string>("");
  const docxContainerRef = useRef<HTMLDivElement>(null);

  const downloadUrl = docFolder
    ? `/api/doc/download/${encodeURIComponent(filename)}?doc_folder=${encodeURIComponent(docFolder)}`
    : "";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (!docFolder) {
      setLoading(false);
      setError("未绑定项目文件夹");
      return () => {
        cancelled = true;
      };
    }

    (async () => {
      try {
        const isMd = filename.toLowerCase().endsWith(".md");
        const resp = await fetch(downloadUrl);
        if (!resp.ok) throw new Error("Failed to fetch document");

        if (isMd) {
          const text = await resp.text();
          if (!cancelled) setMarkdown(text);
        } else {
          const arrayBuffer = await resp.arrayBuffer();
          if (!docxContainerRef.current || cancelled) return;
          await renderAsync(
            arrayBuffer, docxContainerRef.current, undefined, {
              inWrapper: true,
              breakPages: true,
              ignoreWidth: false,
              ignoreHeight: false,
            }
          );
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message ?? String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [docFolder, downloadUrl, filename]);

  const isMd = filename.toLowerCase().endsWith(".md");

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[24px] border border-white/[0.08] bg-[#101721]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-cyan-300 font-medium">文档预览</span>
          <span className="text-slate-600">/</span>
          <span className="truncate max-w-[400px] text-slate-300">{filename}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <a
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-slate-300 transition-colors hover:bg-white/[0.08] hover:text-slate-100"
            download={filename}
            href={downloadUrl || "#"}
          >
            <Download className="size-3.5" />
            下载
          </a>
          <Button
            onClick={onClose}
            size="icon"
            variant="ghost"
            className="size-8 text-slate-400 hover:text-slate-100"
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex min-h-0 flex-1 justify-center overflow-y-auto bg-[#161d28]">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="size-6 animate-spin text-cyan-300/50" />
          </div>
        )}
        {error && (
          <div className="flex flex-col items-center justify-center gap-3 py-20 text-slate-500">
            <AlertTriangle className="size-8 text-amber-500/50" />
            <p className="text-xs">{error}</p>
            <a
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/[0.08] px-3 text-xs text-slate-400 hover:text-slate-200"
              download={filename}
              href={downloadUrl || "#"}
            >
              <Download className="size-3.5" />
              下载文件查看
            </a>
          </div>
        )}

        {/* Markdown rendered with react-markdown */}
        {!loading && !error && isMd && (
          <div className="w-full max-w-4xl px-6 py-6 xl:px-8">
            <div className="markdown-body rounded-[20px] border border-white/[0.06] bg-[#0c1118] px-6 py-6 shadow-[0_24px_60px_rgba(0,0,0,0.24)]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{
                  a: ({ href, children, ...props }) => (
                    <a
                      href={href}
                      rel="noopener noreferrer"
                      target="_blank"
                      {...props}
                    >
                      {children}
                    </a>
                  ),
                  img: ({ src, alt, ...props }) => (
                    <img
                      alt={alt ?? ""}
                      className="h-auto max-w-full rounded-lg border border-white/[0.08]"
                      loading="lazy"
                      src={src}
                      {...props}
                    />
                  ),
                  table: ({ children, ...props }) => (
                    <div className="mb-4 overflow-x-auto">
                      <table
                        className="min-w-full border-collapse"
                        {...props}
                      >
                        {children}
                      </table>
                    </div>
                  ),
                }}
              >
                {markdown}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {/* DOCX rendered content */}
        <div
          ref={docxContainerRef}
          className="docx-preview-container mx-auto px-4 py-4"
          style={{ display: loading || error || isMd ? "none" : "block" }}
        />
      </div>
    </div>
  );
}
