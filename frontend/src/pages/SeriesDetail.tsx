import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, BookOpen, ChevronUp, ChevronDown, X, Bot, Save, ImagePlus, Trash2 } from "lucide-react";
import { getSeries, updateSeries, uploadSeriesCover, deleteSeriesCover, setSeriesCoverFromImage } from "@/api/series";
import { listAllImages } from "@/api/images";
import ImagePickerModal from "@/components/ImagePickerModal";
import { listWorks, updateWork } from "@/api/works";
import { useState, useCallback, useRef, useEffect } from "react";
import { Work } from "@/types";
import client from "@/api/client";
import WorksGrid from "@/components/WorksGrid";

export default function SeriesDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [showAddWork, setShowAddWork] = useState(false);
  const [showAiInstructions, setShowAiInstructions] = useState(false);
  const [aiInstructions, setAiInstructions] = useState("");
  const [aiDirty, setAiDirty] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const aiInitialized = useRef(false);

  const { data: series } = useQuery({
    queryKey: ["series", id],
    queryFn: () => getSeries(id!),
    enabled: !!id,
  });

  const { data: works = [] } = useQuery({
    queryKey: ["works", { seriesId: id }],
    queryFn: () => listWorks(id!),
    enabled: !!id,
  });

  const { data: allWorks = [] } = useQuery({
    queryKey: ["works"],
    queryFn: async () => {
      const { data } = await client.get<Work[]>("/works");
      return data;
    },
  });

  const unassignedWorks = allWorks.filter(
    (w) => !w.series_id || w.series_id === id
  ).filter((w) => !works.some((sw) => sw.id === w.id));

  const sortedWorks = [...works].sort((a, b) => a.sort_order - b.sort_order);

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["works", { seriesId: id }] });
    queryClient.invalidateQueries({ queryKey: ["works"] });
  }, [queryClient, id]);

  const assignMutation = useMutation({
    mutationFn: (workId: string) =>
      updateWork(workId, { series_id: id, sort_order: works.length }),
    onSuccess: invalidateAll,
  });

  const removeMutation = useMutation({
    mutationFn: async (workId: string) => {
      await updateWork(workId, { series_id: null, sort_order: 0 });
      const remaining = sortedWorks
        .filter((w) => w.id !== workId)
        .map((w, i) => updateWork(w.id, { sort_order: i }));
      await Promise.all(remaining);
    },
    onSuccess: invalidateAll,
  });

  const reorderMutation = useMutation({
    mutationFn: async ({ index, direction }: { index: number; direction: -1 | 1 }) => {
      const target = index + direction;
      if (target < 0 || target >= sortedWorks.length) return;
      const reordered = [...sortedWorks];
      [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
      await Promise.all(
        reordered.map((w, i) => updateWork(w.id, { sort_order: i }))
      );
    },
    onSuccess: invalidateAll,
  });

  const aiMutation = useMutation({
    mutationFn: (instructions: string) => updateSeries(id!, { ai_instructions: instructions }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["series", id] });
      setAiDirty(false);
    },
  });

  const coverUploadMutation = useMutation({
    mutationFn: (file: File) => uploadSeriesCover(id!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["series", id] });
      queryClient.invalidateQueries({ queryKey: ["series"] });
    },
  });

  const coverDeleteMutation = useMutation({
    mutationFn: () => deleteSeriesCover(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["series", id] });
      queryClient.invalidateQueries({ queryKey: ["series"] });
    },
  });

  const [showBannerPicker, setShowBannerPicker] = useState(false);

  const setCoverFromImageMutation = useMutation({
    mutationFn: (imageUrl: string) => setSeriesCoverFromImage(id!, imageUrl),
    onSuccess: (data) => {
      const bustUrl = `${data.cover_image_path}?t=${Date.now()}`;
      queryClient.setQueryData(["series", id], (old: any) =>
        old ? { ...old, cover_image_path: bustUrl } : old
      );
      queryClient.invalidateQueries({ queryKey: ["series"] });
      setShowBannerPicker(false);
    },
  });

  const { data: allImages = [] } = useQuery({
    queryKey: ["images", "all"],
    queryFn: listAllImages,
    enabled: showBannerPicker,
  });

  useEffect(() => {
    if (series && !aiInitialized.current) {
      setAiInstructions(series.ai_instructions || "");
      aiInitialized.current = true;
    }
  }, [series]);

  if (!series) return null;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-6 text-sm"
      >
        <ArrowLeft size={16} />
        Back to Library
      </Link>

      <div className="relative rounded-lg overflow-hidden border border-tc-subtle mb-8 group/banner">
        {series.cover_image_path ? (
          <div className="h-36 relative">
            <img
              src={series.cover_image_path}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-r from-gray-900/90 via-gray-900/60 to-transparent" />
            <div className="relative z-10 flex items-center h-full px-6">
              <div>
                <h1 className="text-2xl font-bold">{series.title}</h1>
                {series.description && (
                  <p className="text-tc-secondary mt-1">{series.description}</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="h-36 bg-gradient-to-r from-gray-800 to-gray-900 flex items-center px-6">
            <div>
              <h1 className="text-2xl font-bold">{series.title}</h1>
              {series.description && (
                <p className="text-tc-tertiary mt-1">{series.description}</p>
              )}
            </div>
          </div>
        )}
        <div className="absolute top-3 right-3 z-20 flex items-center gap-1.5 opacity-0 group-hover/banner:opacity-100 transition-opacity">
          <button
            onClick={() => setShowBannerPicker(true)}
            className="p-1.5 bg-tc-base/80 hover:bg-tc-overlay rounded text-tc-secondary hover:text-tc-primary transition-colors"
            title={series.cover_image_path ? "Change banner image" : "Set banner image"}
          >
            <ImagePlus size={14} />
          </button>
          {series.cover_image_path && (
            <button
              onClick={() => {
                if (confirm("Remove banner image?")) coverDeleteMutation.mutate();
              }}
              className="p-1.5 bg-tc-base/80 hover:bg-tc-error-subtle rounded text-tc-secondary hover:text-tc-error transition-colors"
              title="Remove banner image"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {showBannerPicker && (
        <ImagePickerModal
          title="Choose Banner Image"
          images={allImages}
          onSelect={(img) => setCoverFromImageMutation.mutate(img.url)}
          onUpload={(file) => {
            coverUploadMutation.mutate(file);
            setShowBannerPicker(false);
          }}
          onClose={() => setShowBannerPicker(false)}
        />
      )}

      <div className="flex items-center gap-2 mb-6">
        <Link
          to={`/codex?series=${id}`}
          className="flex items-center gap-2 px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-secondary rounded-lg text-sm font-medium transition-colors"
        >
          <BookOpen size={16} />
          Codex
        </Link>
        <button
          onClick={() => setEditMode(!editMode)}
          className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            editMode ? "bg-tc-accent text-tc-primary" : "bg-tc-overlay hover:bg-tc-hover text-tc-secondary"
          }`}
        >
          {editMode ? "Done" : "Edit Order"}
        </button>
      </div>

      <div className="mb-6">
        <button
          onClick={() => setShowAiInstructions(!showAiInstructions)}
          className="flex items-center gap-2 text-sm text-tc-muted hover:text-tc-secondary transition-colors"
        >
          <Bot size={14} />
          AI Instructions
        </button>
        {showAiInstructions && (
          <div className="mt-3 bg-tc-overlay/50 border border-tc-subtle rounded-lg p-4">
            <p className="text-xs text-tc-muted mb-2">
              Guidelines for the AI assistant across all works in this series.
            </p>
            <textarea
              value={aiInstructions}
              onChange={(e) => {
                setAiInstructions(e.target.value);
                setAiDirty(true);
              }}
              rows={6}
              placeholder="e.g. This series uses British English. The magic system follows strict conservation laws..."
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y font-mono"
            />
            <button
              onClick={() => aiMutation.mutate(aiInstructions)}
              disabled={!aiDirty || aiMutation.isPending}
              className="mt-2 flex items-center gap-2 px-3 py-1.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded text-xs font-medium transition-colors"
            >
              <Save size={12} />
              {aiMutation.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        )}
      </div>

      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-tc-secondary flex items-center gap-2">
            <BookOpen size={20} />
            Works
          </h2>
          {!showAddWork && unassignedWorks.length > 0 && editMode && (
            <button
              onClick={() => setShowAddWork(true)}
              className="text-xs text-tc-muted hover:text-tc-secondary transition-colors"
            >
              + Add
            </button>
          )}
        </div>

        {showAddWork && (
          <div className="mb-4 p-3 bg-tc-overlay rounded-lg flex items-center gap-2">
            <select
              className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-1.5 text-sm focus:border-tc-accent focus:outline-none"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) {
                  assignMutation.mutate(e.target.value);
                  setShowAddWork(false);
                }
              }}
            >
              <option value="" disabled>Select a work...</option>
              {unassignedWorks.map((w) => (
                <option key={w.id} value={w.id}>{w.title}</option>
              ))}
            </select>
            <button
              onClick={() => setShowAddWork(false)}
              className="px-2 py-1.5 text-sm text-tc-tertiary hover:text-tc-secondary"
            >
              Cancel
            </button>
          </div>
        )}

        {editMode ? (
          sortedWorks.length > 0 ? (
            <div className="grid gap-2">
              {sortedWorks.map((work, index) => (
                <div
                  key={work.id}
                  className="flex items-center justify-between p-3 bg-tc-overlay rounded-lg border border-tc-subtle group"
                >
                  <Link
                    to={`/work/${work.id}`}
                    className="flex items-center gap-3 flex-1 min-w-0"
                  >
                    <span className="text-tc-muted text-sm font-mono w-6 shrink-0">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {work.cover_image_path ? (
                      <img src={work.cover_image_path} alt="" className="w-8 h-12 object-cover rounded shrink-0" />
                    ) : (
                      <div className="w-8 h-12 bg-tc-hover rounded shrink-0" />
                    )}
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium truncate">{work.title}</h3>
                    </div>
                  </Link>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <div className="flex flex-col">
                      <button
                        onClick={() => reorderMutation.mutate({ index, direction: -1 })}
                        disabled={index === 0 || reorderMutation.isPending}
                        className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                      >
                        <ChevronUp size={14} />
                      </button>
                      <button
                        onClick={() => reorderMutation.mutate({ index, direction: 1 })}
                        disabled={index === sortedWorks.length - 1 || reorderMutation.isPending}
                        className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                      >
                        <ChevronDown size={14} />
                      </button>
                    </div>
                    <button
                      onClick={() => {
                        if (confirm(`Remove "${work.title}" from this series?`))
                          removeMutation.mutate(work.id);
                      }}
                      className="text-tc-muted hover:text-tc-error p-0.5"
                      title="Remove from series"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-tc-muted text-sm">No works in this series yet.</p>
          )
        ) : (
          sortedWorks.length > 0 ? (
            <WorksGrid works={sortedWorks} showViewToggle defaultSort="series_order" />
          ) : (
            <p className="text-tc-muted text-sm">No works in this series yet.</p>
          )
        )}
      </section>
    </div>
  );
}
