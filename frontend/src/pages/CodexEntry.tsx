import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Save, Trash2, PenLine, X, Upload, Star, ImageIcon, Download } from "lucide-react";
import { getCodexEntry, updateCodexEntry, deleteCodexEntry } from "@/api/codex";
import { uploadCodexImage, updateCodexImage, deleteCodexImage } from "@/api/codex-images";
import { listVoices, PollyVoice } from "@/api/narration";
import { useState, useEffect, useRef } from "react";
import { CodexEntry as CodexEntryType, CodexImage, Work, Series } from "@/types";
import Markdown from "react-markdown";
import Editor from "@/components/Editor";

const ENTRY_TYPES: CodexEntryType["entry_type"][] = [
  "character",
  "location",
  "event",
  "species",
  "item",
  "timeline",
  "custom",
];

export default function CodexEntryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [entryType, setEntryType] =
    useState<CodexEntryType["entry_type"]>("character");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [workIds, setWorkIds] = useState<string[]>([]);
  const [seriesIds, setSeriesIds] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [contentDirty, setContentDirty] = useState(false);
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [showImages, setShowImages] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [viewImage, setViewImage] = useState<CodexImage | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: entry } = useQuery({
    queryKey: ["codex", id],
    queryFn: () => getCodexEntry(id!),
    enabled: !!id,
  });

  const { data: allWorks = [] } = useQuery({
    queryKey: ["works"],
    queryFn: async () => {
      const { data } = await (await import("@/api/client")).default.get<Work[]>("/works");
      return data;
    },
  });

  const { data: allSeries = [] } = useQuery({
    queryKey: ["series"],
    queryFn: async () => {
      const { data } = await (await import("@/api/client")).default.get<Series[]>("/series");
      return data;
    },
  });

  const { data: voices = [] } = useQuery<PollyVoice[]>({
    queryKey: ["polly-voices"],
    queryFn: listVoices,
    staleTime: Infinity,
  });

  const updateMutation = useMutation({
    mutationFn: (overrideContent?: string) =>
      updateCodexEntry(id!, {
        name,
        entry_type: entryType,
        content: overrideContent ?? content,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        voice_id: entryType === "character" ? voiceId : undefined,
        work_ids: workIds,
        series_ids: seriesIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["codex"] });
    },
  });

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    setUploading(true);
    try {
      await uploadCodexImage(id, file);
      queryClient.invalidateQueries({ queryKey: ["codex", id] });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSetPrimary = async (imageId: string) => {
    await updateCodexImage(imageId, { is_primary: true });
    queryClient.invalidateQueries({ queryKey: ["codex", id] });
  };

  const handleDeleteImage = async (img: CodexImage) => {
    if (!confirm(`Delete "${img.original_name}"?`)) return;
    await deleteCodexImage(img.id);
    queryClient.invalidateQueries({ queryKey: ["codex", id] });
  };

  useEffect(() => {
    if (entry) {
      setName(entry.name);
      setEntryType(entry.entry_type);
      setContent(entry.content);
      setTags(entry.tags.join(", "));
      setVoiceId(entry.voice_id ?? null);
      setWorkIds(entry.work_ids ?? []);
      setSeriesIds(entry.series_ids ?? []);
    }
  }, [entry]);

  if (!entry) return null;

  const handleEditContent = () => {
    setEditContent(content);
    setContentDirty(false);
    setEditing(true);
  };

  const handleCancelEdit = () => {
    if (contentDirty && !confirm("Discard unsaved changes?")) return;
    setEditing(false);
    setContentDirty(false);
  };

  const handleSaveContent = () => {
    setContent(editContent);
    updateMutation.mutate(editContent, {
      onSuccess: () => {
        setEditing(false);
        setContentDirty(false);
      },
    });
  };

  const handleContentChange = (newContent: string) => {
    setEditContent(newContent);
    setContentDirty(true);
  };

  const toggleWork = (wid: string) => {
    setWorkIds((prev) =>
      prev.includes(wid) ? prev.filter((i) => i !== wid) : [...prev, wid]
    );
  };

  const toggleSeries = (sid: string) => {
    setSeriesIds((prev) =>
      prev.includes(sid) ? prev.filter((i) => i !== sid) : [...prev, sid]
    );
  };

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <Link
        to="/codex"
        className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-6 text-sm"
      >
        <ArrowLeft size={16} />
        Back to Codex
      </Link>

      <div className="space-y-4">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full bg-tc-overlay border border-tc-subtle rounded-lg px-4 py-3 text-lg font-medium focus:outline-none focus:border-tc-accent"
        />

        <div className="flex gap-4">
          <select
            value={entryType}
            onChange={(e) =>
              setEntryType(e.target.value as CodexEntryType["entry_type"])
            }
            className="bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
          >
            {ENTRY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>

          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="Tags (comma-separated)"
            className="flex-1 bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
          />
        </div>

        {entryType === "character" && (
          <div className="flex items-center gap-3">
            <label className="text-sm text-tc-tertiary whitespace-nowrap">
              Narration Voice
            </label>
            <select
              value={voiceId || ""}
              onChange={(e) => setVoiceId(e.target.value || null)}
              className="flex-1 bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
            >
              <option value="">None (use narrator voice)</option>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} — {v.gender}, {v.language}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="relative p-5 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50 group">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-tc-muted font-medium">Content</span>
            <div className="flex items-center gap-1">
              {editing ? (
                <>
                  <button
                    onClick={handleSaveContent}
                    disabled={!contentDirty || updateMutation.isPending}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors ${
                      contentDirty
                        ? "bg-tc-accent hover:bg-tc-accent-hover text-tc-primary"
                        : "bg-tc-hover text-tc-muted"
                    }`}
                  >
                    <Save size={12} />
                    {updateMutation.isPending ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
                    title="Cancel"
                  >
                    <X size={14} />
                  </button>
                </>
              ) : (
                <button
                  onClick={handleEditContent}
                  className="p-1.5 text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100 rounded transition-all"
                  title="Edit content"
                >
                  <PenLine size={14} />
                </button>
              )}
            </div>
          </div>

          {editing ? (
            <Editor
              content={editContent}
              onChange={handleContentChange}
              placeholder="Write entry content..."
            />
          ) : (
            <div
              className="prose prose-invert prose-sm max-w-none text-tc-secondary leading-relaxed overflow-hidden break-words cursor-text"
              onClick={handleEditContent}
            >
              {content ? (
                <Markdown>{content}</Markdown>
              ) : (
                <p className="text-tc-muted italic">No content — click to write</p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setShowImages(!showImages)}
              className="flex items-center gap-2 text-xs font-semibold text-tc-tertiary uppercase tracking-wide hover:text-tc-secondary transition-colors"
            >
              <ImageIcon size={14} />
              Images ({entry.images?.length || 0})
              <span className="text-[10px] text-tc-muted">
                {showImages ? "▼" : "▶"}
              </span>
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1.5 px-3 py-1 bg-tc-overlay hover:bg-tc-hover text-tc-tertiary hover:text-tc-secondary rounded text-xs font-medium transition-colors"
            >
              <Upload size={12} />
              {uploading ? "Uploading..." : "Upload"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              onChange={handleImageUpload}
              className="hidden"
            />
          </div>
          {showImages && entry.images && entry.images.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {entry.images.map((img: CodexImage) => (
                <div
                  key={img.id}
                  className={`relative group rounded-lg overflow-hidden border ${
                    img.is_primary
                      ? "border-tc-accent ring-1 ring-tc-accent/30"
                      : "border-tc-subtle"
                  }`}
                >
                  <img
                    src={img.url}
                    alt={img.alt_text || img.original_name}
                    className="w-full h-32 object-cover"
                  />
                  {img.is_primary && (
                    <span className="absolute top-1.5 left-1.5 flex items-center gap-1 px-1.5 py-0.5 bg-tc-accent/90 rounded text-[10px] font-medium text-tc-primary pointer-events-none">
                      <Star size={10} fill="currentColor" />
                      Primary
                    </span>
                  )}
                  <div
                    className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center gap-2 pb-10 cursor-pointer"
                    onClick={() => setViewImage(img)}
                  >
                    {!img.is_primary && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSetPrimary(img.id); }}
                        className="p-1.5 bg-tc-overlay/80 hover:bg-tc-accent text-tc-secondary hover:text-tc-primary rounded transition-colors"
                        title="Set as primary"
                      >
                        <Star size={14} />
                      </button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteImage(img); }}
                      className="p-1.5 bg-tc-overlay/80 hover:bg-tc-error-subtle text-tc-secondary hover:text-tc-primary rounded transition-colors"
                      title="Delete image"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div className="px-2 py-1.5 bg-tc-base/80 text-[11px] text-tc-tertiary truncate">
                    {img.original_name}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {(allWorks.length > 0 || allSeries.length > 0) && (
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide">
              Associations
            </h3>
            {allSeries.length > 0 && (
              <div>
                <p className="text-xs text-tc-muted mb-2">Series</p>
                <div className="flex flex-wrap gap-2">
                  {allSeries.map((s: Series) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => toggleSeries(s.id)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                        seriesIds.includes(s.id)
                          ? "bg-tc-accent text-tc-primary"
                          : "bg-tc-overlay text-tc-tertiary hover:text-tc-secondary border border-tc-subtle"
                      }`}
                    >
                      {s.title}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {allWorks.length > 0 && (
              <div>
                <p className="text-xs text-tc-muted mb-2">Works</p>
                <div className="flex flex-wrap gap-2">
                  {allWorks.map((w: Work) => (
                    <button
                      key={w.id}
                      type="button"
                      onClick={() => toggleWork(w.id)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                        workIds.includes(w.id)
                          ? "bg-tc-accent text-tc-primary"
                          : "bg-tc-overlay text-tc-tertiary hover:text-tc-secondary border border-tc-subtle"
                      }`}
                    >
                      {w.title}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={() => updateMutation.mutate(undefined)}
            className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
          >
            <Save size={16} />
            Save
          </button>
          <button
            onClick={() => {
              if (confirm(`Delete "${name}"? This cannot be undone.`)) {
                deleteCodexEntry(id!).then(() => {
                  queryClient.invalidateQueries({ queryKey: ["codex"] });
                  navigate("/codex");
                });
              }
            }}
            className="flex items-center gap-2 px-4 py-2 bg-tc-overlay hover:bg-tc-error-subtle text-tc-tertiary hover:text-tc-error rounded-lg text-sm font-medium transition-colors"
          >
            <Trash2 size={16} />
            Delete
          </button>
        </div>
      </div>

      {viewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setViewImage(null)}
        >
          <div
            className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="absolute top-2 right-2 flex items-center gap-2 z-10">
              <button
                onClick={async () => {
                  const res = await fetch(viewImage.url);
                  const blob = await res.blob();
                  const a = document.createElement("a");
                  a.href = URL.createObjectURL(blob);
                  a.download = viewImage.original_name;
                  a.click();
                  URL.revokeObjectURL(a.href);
                }}
                className="p-2 bg-tc-overlay/80 hover:bg-tc-hover text-tc-secondary hover:text-tc-primary rounded-lg transition-colors"
                title="Download"
              >
                <Download size={16} />
              </button>
              <button
                onClick={() => setViewImage(null)}
                className="p-2 bg-tc-overlay/80 hover:bg-tc-hover text-tc-secondary hover:text-tc-primary rounded-lg transition-colors"
                title="Close"
              >
                <X size={16} />
              </button>
            </div>
            <img
              src={viewImage.url}
              alt={viewImage.alt_text || viewImage.original_name}
              className="max-w-full max-h-[85vh] object-contain rounded-lg"
            />
            <p className="mt-2 text-sm text-tc-tertiary">{viewImage.original_name}</p>
          </div>
        </div>
      )}
    </div>
  );
}
