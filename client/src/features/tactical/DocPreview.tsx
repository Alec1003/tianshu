import { useEffect, useRef, useState } from "react";
import { Download, Loader2, X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { renderAsync } from "docx-preview";

// Simple Markdown to HTML converter
function markdownToHtml(md: string): string {
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="language-\${lang}">\${code.trim()}</code></pre>`
    )
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^---$/gm, "<hr />")
    .replace(/^\|(.+)\|$/gm, (line: string) => {
      const cells = line.slice(1, -1).split("|").map((c: string) => c.trim());
      if (cells.length > 0 && cells.every((c: string) => /^-+$/.test(c))) return "";
      return `<tr><td>\${cells.join("</td><td>")}</td></tr>`;
    })
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>")
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (match: string) => {
      if (match.includes("<ul>")) return match;
      return `<ol>\${match}</ol>`;
    });

  // Wrap non-tag lines in paragraph
  html = html.replace(/^([^<\n].+)$/gm, "<p>$1</p>");
  // Clean empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");
  return html;
}

interface DocPreviewProps {
  filename: string;
  onClose: () => void;
}

export default function DocPreview({ filename, onClose }: DocPreviewProps) {
  // docx-preview renders directly into the DOM
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const downloadUrl = `/api/doc/download/${encodeURIComponent(filename)}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const isMd = filename.toLowerCase().endsWith(".md");
        const resp = await fetch(downloadUrl);
        if (!resp.ok) throw new Error("Failed to fetch document");

        if (isMd) {
          const text = await resp.text();
          if (!containerRef.current || cancelled) return;
          const html = markdownToHtml(text);
          containerRef.current.innerHTML = html;
        } else {
          const arrayBuffer = await resp.arrayBuffer();
          if (!containerRef.current || cancelled) return;
          await renderAsync(
arrayBuffer, containerRef.current!, undefined, {
          
          inWrapper: true,
          breakPages: true,
          ignoreWidth: false,
          ignoreHeight: false,
        }
        );

        if (!cancelled) {
          // docx-preview renders directly into containerRef.current
          // docx-preview renders directly
        }
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
  }, [downloadUrl, filename]);

  return (
    <div className="absolute inset-0 z-50 flex flex-col bg-[#525659]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5 backdrop-blur-sm">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-cyan-300 font-medium">文档预览</span>
          <span className="text-slate-600">/</span>
          <span className="truncate max-w-[400px] text-slate-300">
            {filename}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <a
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-slate-300 transition-colors hover:bg-white/[0.08] hover:text-slate-100"
            download={filename}
            href={downloadUrl}
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
      <div className="flex min-h-0 flex-1 justify-center overflow-y-auto">
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
              href={downloadUrl}
            >
              <Download className="size-3.5" />
              下载文件查看
            </a>
          </div>
        )}
        <div
          ref={containerRef}
          className="docx-preview-container mx-auto"
          style={{ display: loading && !error ? "none" : "block" }}
        />
      </div>

      
    </div>
  );
}
