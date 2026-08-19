import { Link } from "react-router-dom";
import { Work, Series } from "@/types";
import { useState } from "react";
import { ArrowUpDown, LayoutGrid, List } from "lucide-react";

type SortOption = "title" | "updated" | "published" | "series_order";
type ViewMode = "covers" | "list";

interface WorksGridProps {
  works: Work[];
  showViewToggle?: boolean;
  defaultView?: ViewMode;
  defaultSort?: SortOption;
  seriesMap?: Map<string, Series>;
}

function sortWorks(works: Work[], sort: SortOption): Work[] {
  return [...works].sort((a, b) => {
    switch (sort) {
      case "series_order":
        return a.sort_order - b.sort_order;
      case "title":
        return a.title.localeCompare(b.title);
      case "updated":
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      case "published":
        if (!a.publication_date && !b.publication_date) return 0;
        if (!a.publication_date) return 1;
        if (!b.publication_date) return -1;
        return new Date(b.publication_date).getTime() - new Date(a.publication_date).getTime();
    }
  });
}

function seriesLabel(work: Work, seriesMap?: Map<string, Series>): string | null {
  if (!work.series_id || !seriesMap) return null;
  const s = seriesMap.get(work.series_id);
  if (!s) return null;
  return `${s.title} Book ${work.sort_order + 1}`;
}

export default function WorksGrid({ works, showViewToggle = false, defaultView = "covers", defaultSort = "title", seriesMap }: WorksGridProps) {
  const [sort, setSort] = useState<SortOption>(defaultSort);
  const [view, setView] = useState<ViewMode>(defaultView);

  const sorted = sortWorks(works, sort);

  if (works.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center gap-1.5 text-xs text-tc-muted">
          <ArrowUpDown size={12} />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortOption)}
            className="bg-transparent border-none text-tc-tertiary text-xs focus:outline-none cursor-pointer hover:text-tc-secondary"
          >
            {defaultSort === "series_order" && (
              <option value="series_order">Series Order</option>
            )}
            <option value="title">A–Z</option>
            <option value="updated">Last Modified</option>
            <option value="published">Published Date</option>
          </select>
        </div>
        {showViewToggle && (
          <div className="flex items-center gap-0.5 ml-auto">
            <button
              onClick={() => setView("covers")}
              className={`p-1.5 rounded ${view === "covers" ? "text-tc-secondary bg-tc-hover" : "text-tc-muted hover:text-tc-secondary"}`}
              title="Cover view"
            >
              <LayoutGrid size={14} />
            </button>
            <button
              onClick={() => setView("list")}
              className={`p-1.5 rounded ${view === "list" ? "text-tc-secondary bg-tc-hover" : "text-tc-muted hover:text-tc-secondary"}`}
              title="List view"
            >
              <List size={14} />
            </button>
          </div>
        )}
      </div>

      {view === "covers" ? (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-4">
          {sorted.map((w) => {
            const sl = seriesLabel(w, seriesMap);
            return (
              <Link key={w.id} to={`/work/${w.id}`} className="group">
                <div className="aspect-[2/3] rounded-md overflow-hidden bg-tc-overlay border border-tc-subtle group-hover:border-tc-strong transition-colors shadow-md group-hover:shadow-lg">
                  {w.cover_image_path ? (
                    <img
                      src={w.cover_image_path}
                      alt={w.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center p-2">
                      <span className="text-xs text-tc-muted text-center leading-tight font-medium">
                        {w.title}
                      </span>
                    </div>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-tc-secondary truncate group-hover:text-tc-primary transition-colors">
                  {w.title}
                </p>
                {sl && (
                  <p className="text-[10px] text-tc-accent/70 truncate">{sl}</p>
                )}
                {!sl && w.author && (
                  <p className="text-[10px] text-tc-muted truncate">{w.author}</p>
                )}
              </Link>
            );
          })}
        </div>
      ) : (
        <div className="grid gap-2">
          {sorted.map((w) => {
            const sl = seriesLabel(w, seriesMap);
            return (
              <Link
                key={w.id}
                to={`/work/${w.id}`}
                className="flex items-center gap-3 p-3 bg-tc-overlay hover:bg-tc-hover rounded-lg border border-tc-subtle hover:border-tc-strong transition-colors"
              >
                {w.cover_image_path ? (
                  <img
                    src={w.cover_image_path}
                    alt=""
                    className="w-8 h-12 object-cover rounded shrink-0"
                  />
                ) : (
                  <div className="w-8 h-12 bg-tc-hover rounded shrink-0" />
                )}
                <div className="min-w-0">
                  <h3 className="text-sm font-medium truncate">{w.title}</h3>
                  {sl && (
                    <p className="text-[10px] text-tc-accent/70 truncate">{sl}</p>
                  )}
                  {!sl && w.author && (
                    <p className="text-xs text-tc-muted truncate">{w.author}</p>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
