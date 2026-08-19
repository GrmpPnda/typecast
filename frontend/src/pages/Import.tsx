import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Upload, FileText, Loader2 } from "lucide-react";
import { importMarkdownFile, importMarkdownPaste } from "@/api/imports";

export default function Import() {
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [useAi, setUseAi] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [pastedContent, setPastedContent] = useState("");
  const [dragOver, setDragOver] = useState(false);

  const options = {
    title: title || undefined,
    author: author || undefined,
    useAi,
  };

  const fileMutation = useMutation({
    mutationFn: (f: File) => importMarkdownFile(f, options),
    onSuccess: (work) => navigate(`/work/${work.id}`),
  });

  const pasteMutation = useMutation({
    mutationFn: (content: string) => importMarkdownPaste(content, options),
    onSuccess: (work) => navigate(`/work/${work.id}`),
  });

  const isLoading = fileMutation.isPending || pasteMutation.isPending;
  const error = fileMutation.error || pasteMutation.error;

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && (dropped.name.endsWith(".md") || dropped.name.endsWith(".txt"))) {
      setFile(dropped);
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleImport = () => {
    if (file) {
      fileMutation.mutate(file);
    } else if (pastedContent.trim()) {
      pasteMutation.mutate(pastedContent);
    }
  };

  const canImport = (file || pastedContent.trim()) && !isLoading;

  return (
    <div className="max-w-2xl mx-auto py-10 px-4">
      <h1 className="text-2xl font-bold text-tc-primary mb-8">Import</h1>

      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-tc-tertiary mb-1">
              Title override
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Leave blank to auto-detect"
              className="w-full rounded-lg bg-tc-overlay border border-tc-subtle px-3 py-2 text-sm text-tc-primary placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-tc-accent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tc-tertiary mb-1">
              Author override
            </label>
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Leave blank to auto-detect"
              className="w-full rounded-lg bg-tc-overlay border border-tc-subtle px-3 py-2 text-sm text-tc-primary placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-tc-accent"
            />
          </div>
        </div>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={useAi}
            onChange={(e) => setUseAi(e.target.checked)}
            className="h-4 w-4 rounded border-tc-strong bg-tc-overlay text-tc-accent focus:ring-tc-accent"
          />
          <span className="text-sm text-tc-secondary">Use AI parsing</span>
          <span className="text-xs text-tc-muted">
            Uses your configured AI provider to intelligently split the document. Disable for simple heading-based splitting.
          </span>
        </label>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors ${
            dragOver
              ? "border-tc-accent bg-tc-accent/10"
              : "border-tc-subtle bg-tc-overlay/50 hover:border-tc-strong"
          }`}
        >
          <Upload size={32} className="text-tc-muted mb-3" />
          {file ? (
            <div className="flex items-center gap-2 text-sm text-tc-secondary">
              <FileText size={16} />
              <span>{file.name}</span>
              <button
                onClick={() => setFile(null)}
                className="ml-2 text-xs text-tc-muted hover:text-tc-secondary"
              >
                Remove
              </button>
            </div>
          ) : (
            <>
              <p className="text-sm text-tc-secondary mb-1">
                Drag and drop a .md or .txt file here
              </p>
              <p className="text-xs text-tc-muted">or click to browse</p>
            </>
          )}
          <input
            type="file"
            accept=".md,.txt"
            onChange={handleFileChange}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
        </div>

        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-tc-hover" />
          <span className="text-xs text-tc-muted uppercase tracking-wider">or</span>
          <div className="flex-1 h-px bg-tc-hover" />
        </div>

        <div>
          <label className="block text-sm font-medium text-tc-tertiary mb-1">
            Paste markdown content
          </label>
          <textarea
            value={pastedContent}
            onChange={(e) => setPastedContent(e.target.value)}
            rows={10}
            placeholder={"# Chapter 1\n\nYour content here...\n\n# Chapter 2\n\n..."}
            className="w-full rounded-lg bg-tc-overlay border border-tc-subtle px-3 py-2 text-sm text-tc-primary placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-tc-accent resize-y font-mono"
          />
        </div>

        {error && (
          <div className="rounded-lg bg-tc-error-subtle border border-tc-error px-4 py-3 text-sm text-tc-error">
            Import failed. Please check your file and try again.
          </div>
        )}

        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-tc-tertiary">
            <Loader2 size={16} className="animate-spin" />
            Importing... This may take a moment if using AI parsing.
          </div>
        )}

        <button
          onClick={handleImport}
          disabled={!canImport}
          className="w-full rounded-lg bg-tc-accent px-4 py-3 text-sm font-medium text-tc-primary transition-colors hover:bg-tc-accent disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Import
        </button>
      </div>
    </div>
  );
}
