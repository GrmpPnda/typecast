import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, BookOpen, Layers, Eye, ImageIcon } from "lucide-react";
import { listSeries, createSeries } from "@/api/series";
import { listWorks, createWork } from "@/api/works";
import { listAllImages } from "@/api/images";
import { useState } from "react";
import { Series } from "@/types";
import WorksGrid from "@/components/WorksGrid";

export default function Library() {
  const queryClient = useQueryClient();
  const [showNewSeries, setShowNewSeries] = useState(false);
  const [showNewWork, setShowNewWork] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [showAllWorks, setShowAllWorks] = useState(true);
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  const { data: series = [] } = useQuery({
    queryKey: ["series"],
    queryFn: listSeries,
  });

  const { data: works = [] } = useQuery({
    queryKey: ["works"],
    queryFn: () => listWorks(),
  });

  const { data: allImages = [] } = useQuery({
    queryKey: ["images", "all"],
    queryFn: listAllImages,
  });

  const createSeriesMutation = useMutation({
    mutationFn: createSeries,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["series"] });
      setShowNewSeries(false);
      setNewTitle("");
    },
  });

  const createWorkMutation = useMutation({
    mutationFn: createWork,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["works"] });
      setShowNewWork(false);
      setNewTitle("");
      setNewAuthor("");
    },
  });

  const seriesMap = new Map<string, Series>();
  for (const s of series) seriesMap.set(s.id, s);

  const standaloneWorks = works.filter((w) => !w.series_id);
  const displayWorks = showAllWorks ? works : standaloneWorks;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Library</h1>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowNewSeries(true); setShowNewWork(false); }}
            className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            New Series
          </button>
          <button
            onClick={() => { setShowNewWork(true); setShowNewSeries(false); }}
            className="flex items-center gap-2 px-3 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            New Work
          </button>
        </div>
      </div>

      {(showNewSeries || showNewWork) && (
        <div className="mb-6 p-4 bg-tc-overlay rounded-lg">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={showNewSeries ? "Series title..." : "Work title..."}
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-tc-accent"
            autoFocus
          />
          {showNewWork && (
            <input
              type="text"
              value={newAuthor}
              onChange={(e) => setNewAuthor(e.target.value)}
              placeholder="Author name (required)"
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-tc-accent"
            />
          )}
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (showNewSeries) {
                  createSeriesMutation.mutate({ title: newTitle });
                } else {
                  createWorkMutation.mutate({ title: newTitle, author: newAuthor });
                }
              }}
              disabled={!newTitle.trim() || (showNewWork && !newAuthor.trim())}
              className="px-3 py-1.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded text-sm font-medium transition-colors"
            >
              Create
            </button>
            <button
              onClick={() => {
                setShowNewSeries(false);
                setShowNewWork(false);
                setNewTitle("");
                setNewAuthor("");
              }}
              className="px-3 py-1.5 bg-tc-hover hover:bg-tc-active rounded text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {series.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-semibold text-tc-secondary mb-4 flex items-center gap-2">
            <Layers size={20} />
            Series
          </h2>
          <div className="grid gap-3">
            {series.map((s) => (
              <Link
                key={s.id}
                to={`/series/${s.id}`}
                className="relative block rounded-lg overflow-hidden border border-tc-subtle hover:border-tc-strong transition-all group"
              >
                {s.cover_image_path ? (
                  <div className="h-28 relative">
                    <img
                      src={s.cover_image_path}
                      alt=""
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-r from-gray-900/90 via-gray-900/60 to-transparent" />
                    <div className="relative z-10 flex items-center h-full px-6">
                      <div>
                        <h3 className="text-lg font-bold group-hover:text-tc-accent transition-colors">
                          {s.title}
                        </h3>
                        {s.description && (
                          <p className="text-sm text-tc-secondary mt-0.5 line-clamp-1">
                            {s.description}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-28 bg-gradient-to-r from-gray-800 to-gray-900 flex items-center px-6">
                    <div>
                      <h3 className="text-lg font-bold group-hover:text-tc-accent transition-colors">
                        {s.title}
                      </h3>
                      {s.description && (
                        <p className="text-sm text-tc-tertiary mt-0.5 line-clamp-1">
                          {s.description}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}

      {displayWorks.length > 0 && (
        <section className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-tc-secondary flex items-center gap-2">
              <BookOpen size={20} />
              Works
            </h2>
            {series.length > 0 && (
              <button
                onClick={() => setShowAllWorks(!showAllWorks)}
                className={`flex items-center gap-1.5 text-xs transition-colors ${
                  showAllWorks ? "text-tc-accent" : "text-tc-muted hover:text-tc-secondary"
                }`}
              >
                <Eye size={12} />
                {showAllWorks ? "All works" : "Standalone only"}
              </button>
            )}
          </div>
          <WorksGrid works={displayWorks} seriesMap={seriesMap} />
        </section>
      )}

      {allImages.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-tc-secondary mb-4 flex items-center gap-2">
            <ImageIcon size={20} />
            Images
          </h2>
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2">
            {allImages.slice(0, 24).map((img) => (
              <button
                key={img.id}
                onClick={() => setPreviewImage(img.url)}
                className="aspect-square rounded overflow-hidden bg-tc-overlay border border-tc-subtle hover:border-tc-strong transition-colors"
              >
                <img
                  src={img.url}
                  alt={img.alt_text || ""}
                  className="w-full h-full object-cover"
                />
              </button>
            ))}
          </div>
          {allImages.length > 24 && (
            <p className="text-xs text-tc-muted mt-2">
              Showing 24 of {allImages.length} images
            </p>
          )}
        </section>
      )}

      {previewImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
          onClick={() => setPreviewImage(null)}
        >
          <img
            src={previewImage}
            alt=""
            className="max-h-[90vh] max-w-[90vw] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      {series.length === 0 && works.length === 0 && (
        <div className="text-center py-16 text-tc-muted">
          <BookOpen size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg">Your library is empty</p>
          <p className="text-sm mt-1">Create a series or work to get started</p>
        </div>
      )}
    </div>
  );
}
