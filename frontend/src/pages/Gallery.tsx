import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Images,
  Search,
  Trash2,
  X,
  CheckSquare,
  Square,
  Download,
  ExternalLink,
  Tag,
  ArrowRightLeft,
  BookOpen,
} from "lucide-react";
import { useState, useMemo } from "react";
import {
  listGallery,
  updateGalleryImage,
  reassignImage,
  bulkDeleteImages,
  galleryRawId,
  GalleryItem,
} from "@/api/gallery";
import { listWorks } from "@/api/works";

type SortKey = "date" | "name" | "size";
type SourceFilter = "all" | "gallery" | "cover" | "codex";

const SOURCE_LABELS: Record<string, string> = {
  gallery: "Gallery",
  cover: "Cover",
  codex: "Codex",
};

function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Gallery() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [workFilter, setWorkFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<GalleryItem | null>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["gallery"],
    queryFn: listGallery,
  });

  const { data: works = [] } = useQuery({
    queryKey: ["works"],
    queryFn: () => listWorks(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["gallery"] });

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => bulkDeleteImages(ids.map(galleryRawId)),
    onSuccess: () => {
      invalidate();
      setSelected(new Set());
      setSelectMode(false);
    },
  });

  const works_with_images = useMemo(() => {
    const ids = new Set(items.map((i) => i.work_id).filter(Boolean));
    return works.filter((w) => ids.has(w.id));
  }, [items, works]);

  const filtered = useMemo(() => {
    let result = items;
    if (workFilter !== "all") result = result.filter((i) => i.work_id === workFilter);
    if (sourceFilter !== "all") result = result.filter((i) => i.source === sourceFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (i) =>
          i.original_name.toLowerCase().includes(q) ||
          i.alt_text.toLowerCase().includes(q) ||
          i.tags.toLowerCase().includes(q) ||
          (i.work_title || "").toLowerCase().includes(q) ||
          (i.codex_entry_name || "").toLowerCase().includes(q)
      );
    }
    const sorted = [...result];
    if (sortKey === "name") {
      sorted.sort((a, b) => a.original_name.localeCompare(b.original_name));
    } else if (sortKey === "size") {
      sorted.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
    } else {
      sorted.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    }
    return sorted;
  }, [items, workFilter, sourceFilter, search, sortKey]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCardClick = (item: GalleryItem) => {
    if (selectMode) {
      if (item.manageable) toggleSelect(item.id);
    } else {
      setDetail(item);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <Images size={24} className="text-tc-tertiary" />
          <h1 className="text-2xl font-bold text-tc-primary">Image Gallery</h1>
        </div>
        <div className="flex items-center gap-2">
          {selectMode ? (
            <>
              <span className="text-sm text-tc-tertiary">{selected.size} selected</span>
              <button
                onClick={() => bulkDeleteMutation.mutate([...selected])}
                disabled={selected.size === 0 || bulkDeleteMutation.isPending}
                className="flex items-center gap-2 px-3 py-2 bg-tc-error-subtle text-tc-error rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
              >
                <Trash2 size={16} />
                Delete
              </button>
              <button
                onClick={() => { setSelectMode(false); setSelected(new Set()); }}
                className="px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-secondary rounded-lg text-sm font-medium transition-colors"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={() => setSelectMode(true)}
              className="flex items-center gap-2 px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-secondary rounded-lg text-sm font-medium transition-colors"
            >
              <CheckSquare size={16} />
              Select
            </button>
          )}
        </div>
      </div>
      <p className="text-sm text-tc-muted mb-6">
        All images across your works — gallery uploads, covers, and codex entries.
      </p>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-tc-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, alt text, tags..."
            className="w-full bg-tc-input border border-tc-input rounded-lg pl-9 pr-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent"
          />
        </div>
        <select
          value={workFilter}
          onChange={(e) => setWorkFilter(e.target.value)}
          className="bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-secondary focus:outline-none focus:border-tc-accent"
        >
          <option value="all">All works</option>
          {works_with_images.map((w) => (
            <option key={w.id} value={w.id}>{w.title}</option>
          ))}
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}
          className="bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-secondary focus:outline-none focus:border-tc-accent"
        >
          <option value="all">All types</option>
          <option value="gallery">Gallery</option>
          <option value="cover">Covers</option>
          <option value="codex">Codex</option>
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-secondary focus:outline-none focus:border-tc-accent"
        >
          <option value="date">Newest</option>
          <option value="name">Name</option>
          <option value="size">Largest</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-tc-muted text-sm">Loading...</p>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-tc-muted">
          <Images size={48} className="mx-auto mb-4 opacity-40" />
          <p className="text-sm">No images found.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {filtered.map((item) => {
            const isSelected = selected.has(item.id);
            return (
              <div
                key={item.id}
                onClick={() => handleCardClick(item)}
                className={`group relative aspect-square rounded-lg overflow-hidden border cursor-pointer transition-colors ${
                  isSelected ? "border-tc-accent ring-2 ring-tc-accent" : "border-tc-subtle hover:border-tc-strong"
                }`}
              >
                <img
                  src={item.url}
                  alt={item.alt_text || item.original_name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                {/* Source badge */}
                <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide rounded bg-tc-page/80 text-tc-secondary">
                  {SOURCE_LABELS[item.source]}
                </span>
                {/* Select checkbox */}
                {selectMode && item.manageable && (
                  <div className="absolute top-1.5 right-1.5 text-tc-primary drop-shadow">
                    {isSelected ? <CheckSquare size={18} className="text-tc-accent" /> : <Square size={18} />}
                  </div>
                )}
                {/* Info overlay */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <p className="text-[10px] text-white truncate">{item.original_name}</p>
                  <p className="text-[9px] text-white/70">
                    {item.width && item.height ? `${item.width}×${item.height}` : ""} {formatBytes(item.size_bytes)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {detail && (
        <DetailModal
          item={detail}
          works={works}
          onClose={() => setDetail(null)}
          onChanged={(updated) => { setDetail(updated); invalidate(); }}
        />
      )}
    </div>
  );
}

function DetailModal({
  item,
  works,
  onClose,
  onChanged,
}: {
  item: GalleryItem;
  works: { id: string; title: string }[];
  onClose: () => void;
  onChanged: (updated: GalleryItem) => void;
}) {
  const queryClient = useQueryClient();
  const [altText, setAltText] = useState(item.alt_text);
  const [tags, setTags] = useState(item.tags);
  const [reassignTo, setReassignTo] = useState("");

  const updateMutation = useMutation({
    mutationFn: () => updateGalleryImage(galleryRawId(item.id), { alt_text: altText, tags }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      onChanged(updated);
    },
  });

  const reassignMutation = useMutation({
    mutationFn: () => reassignImage(galleryRawId(item.id), reassignTo),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      onChanged(updated);
    },
  });

  const dirty = altText !== item.alt_text || tags !== item.tags;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="bg-tc-base border border-tc-subtle rounded-xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col md:flex-row"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Image preview */}
        <div className="md:w-1/2 bg-tc-page flex items-center justify-center p-4">
          <img src={item.url} alt={item.alt_text} className="max-w-full max-h-[70vh] object-contain rounded" />
        </div>
        {/* Detail panel */}
        <div className="md:w-1/2 p-5 overflow-y-auto flex flex-col">
          <div className="flex items-start justify-between mb-4">
            <div>
              <span className="px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded bg-tc-overlay text-tc-tertiary">
                {SOURCE_LABELS[item.source]}
              </span>
              <h2 className="text-sm font-semibold text-tc-primary mt-2 break-words">{item.original_name}</h2>
            </div>
            <button onClick={onClose} className="p-1 text-tc-muted hover:text-tc-secondary">
              <X size={18} />
            </button>
          </div>

          <dl className="text-xs space-y-1 mb-4">
            <div className="flex justify-between">
              <dt className="text-tc-muted">Dimensions</dt>
              <dd className="text-tc-secondary">{item.width && item.height ? `${item.width}×${item.height}` : "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-tc-muted">Size</dt>
              <dd className="text-tc-secondary">{formatBytes(item.size_bytes)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-tc-muted">Work</dt>
              <dd className="text-tc-secondary">
                {item.work_id ? (
                  <Link to={`/work/${item.work_id}`} className="text-tc-accent hover:underline flex items-center gap-1">
                    {item.work_title} <ExternalLink size={11} />
                  </Link>
                ) : "—"}
              </dd>
            </div>
            {item.codex_entry_id && (
              <div className="flex justify-between">
                <dt className="text-tc-muted">Codex entry</dt>
                <dd className="text-tc-secondary">
                  <Link to={`/codex/${item.codex_entry_id}`} className="text-tc-accent hover:underline flex items-center gap-1">
                    <BookOpen size={11} /> {item.codex_entry_name}
                  </Link>
                </dd>
              </div>
            )}
          </dl>

          {item.manageable ? (
            <div className="space-y-4 flex-1">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Alt text</label>
                <textarea
                  value={altText}
                  onChange={(e) => setAltText(e.target.value)}
                  rows={2}
                  className="w-full bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent resize-none"
                />
              </div>
              <div>
                <label className="text-xs text-tc-tertiary mb-1 flex items-center gap-1">
                  <Tag size={11} /> Tags (comma-separated)
                </label>
                <input
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="e.g. character, chapter1, concept-art"
                  className="w-full bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent"
                />
              </div>
              <button
                onClick={() => updateMutation.mutate()}
                disabled={!dirty || updateMutation.isPending}
                className="w-full py-2 bg-tc-accent hover:bg-tc-accent-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
              >
                {updateMutation.isPending ? "Saving..." : "Save changes"}
              </button>

              <div className="pt-4 border-t border-tc-subtle">
                <label className="text-xs text-tc-tertiary mb-1 flex items-center gap-1">
                  <ArrowRightLeft size={11} /> Reassign to work
                </label>
                <div className="flex gap-2">
                  <select
                    value={reassignTo}
                    onChange={(e) => setReassignTo(e.target.value)}
                    className="flex-1 bg-tc-input border border-tc-input rounded-lg px-3 py-2 text-sm text-tc-secondary focus:outline-none focus:border-tc-accent"
                  >
                    <option value="">Select work...</option>
                    {works.filter((w) => w.id !== item.work_id).map((w) => (
                      <option key={w.id} value={w.id}>{w.title}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => reassignMutation.mutate()}
                    disabled={!reassignTo || reassignMutation.isPending}
                    className="px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-secondary rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
                  >
                    Move
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-tc-muted italic flex-1">
              {item.source === "cover"
                ? "Cover images are managed from the work's cover settings."
                : "Codex images are managed from their codex entry."}
            </p>
          )}

          <a
            href={item.url}
            download={item.original_name}
            className="mt-4 flex items-center justify-center gap-2 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-secondary rounded-lg text-sm font-medium transition-colors"
          >
            <Download size={14} /> Download
          </a>
        </div>
      </div>
    </div>
  );
}
