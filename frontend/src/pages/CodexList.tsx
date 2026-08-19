import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Plus, Tag, ArrowLeft } from "lucide-react";
import { listCodexEntries, createCodexEntry } from "@/api/codex";
import { getWork } from "@/api/works";
import { listSeries } from "@/api/series";
import { useState } from "react";
import { CodexEntry, Series, Work } from "@/types";
import client from "@/api/client";

const ENTRY_TYPES: CodexEntry["entry_type"][] = [
  "character",
  "location",
  "event",
  "species",
  "item",
  "timeline",
  "custom",
];

export default function CodexList() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const workId = searchParams.get("work") ?? undefined;
  const seriesId = searchParams.get("series") ?? undefined;

  const [activeFilter, setActiveFilter] = useState<string | undefined>();
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<CodexEntry["entry_type"]>("character");

  const { data: work } = useQuery({
    queryKey: ["work", workId],
    queryFn: () => getWork(workId!),
    enabled: !!workId,
  });

  const { data: allSeries = [] } = useQuery({
    queryKey: ["series"],
    queryFn: listSeries,
  });

  const { data: allWorks = [] } = useQuery({
    queryKey: ["works"],
    queryFn: async () => {
      const { data } = await client.get<Work[]>("/works");
      return data;
    },
  });

  const series = seriesId ? allSeries.find((s: Series) => s.id === seriesId) : undefined;

  const { data: entries = [] } = useQuery({
    queryKey: ["codex", { entryType: activeFilter, workId, seriesId }],
    queryFn: () => listCodexEntries({ entryType: activeFilter, workId, seriesId }),
  });

  const createMutation = useMutation({
    mutationFn: createCodexEntry,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["codex"] });
      setShowNew(false);
      setNewName("");
    },
  });

  const setFilter = (key: "work" | "series", value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
      if (key === "work") next.delete("series");
      if (key === "series") next.delete("work");
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };

  const backLink = workId
    ? `/work/${workId}`
    : seriesId
    ? `/series/${seriesId}`
    : undefined;

  const title = work
    ? `Codex — ${work.title}`
    : series
    ? `Codex — ${series.title}`
    : "Codex";

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {backLink && (
        <Link
          to={backLink}
          className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-4 text-sm"
        >
          <ArrowLeft size={16} />
          Back to {work ? work.title : series?.title}
        </Link>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{title}</h1>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          New Entry
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveFilter(undefined)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              !activeFilter
                ? "bg-tc-accent text-tc-primary"
                : "bg-tc-overlay text-tc-tertiary hover:text-tc-secondary"
            }`}
          >
            All
          </button>
          {ENTRY_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => setActiveFilter(type)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium capitalize transition-colors ${
                activeFilter === type
                  ? "bg-tc-accent text-tc-primary"
                  : "bg-tc-overlay text-tc-tertiary hover:text-tc-secondary"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        {!backLink && (allWorks.length > 0 || allSeries.length > 0) && (
          <div className="flex items-center gap-2 ml-auto">
            {allWorks.length > 0 && (
              <select
                value={workId ?? ""}
                onChange={(e) => setFilter("work", e.target.value)}
                className="bg-tc-overlay border border-tc-subtle rounded-lg px-2.5 py-1.5 text-xs text-tc-secondary focus:border-tc-accent focus:outline-none"
              >
                <option value="">All works</option>
                {allWorks.map((w: Work) => (
                  <option key={w.id} value={w.id}>{w.title}</option>
                ))}
              </select>
            )}
            {allSeries.length > 0 && (
              <select
                value={seriesId ?? ""}
                onChange={(e) => setFilter("series", e.target.value)}
                className="bg-tc-overlay border border-tc-subtle rounded-lg px-2.5 py-1.5 text-xs text-tc-secondary focus:border-tc-accent focus:outline-none"
              >
                <option value="">All series</option>
                {allSeries.map((s: Series) => (
                  <option key={s.id} value={s.id}>{s.title}</option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>

      {showNew && (
        <div className="mb-6 p-4 bg-tc-overlay rounded-lg space-y-3">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Entry name..."
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
            autoFocus
          />
          <select
            value={newType}
            onChange={(e) =>
              setNewType(e.target.value as CodexEntry["entry_type"])
            }
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
          >
            {ENTRY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <button
              onClick={() =>
                createMutation.mutate({
                  name: newName,
                  entry_type: newType,
                  work_ids: workId ? [workId] : [],
                  series_ids: seriesId ? [seriesId] : [],
                })
              }
              disabled={!newName.trim()}
              className="px-3 py-1.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded text-sm font-medium transition-colors"
            >
              Create
            </button>
            <button
              onClick={() => {
                setShowNew(false);
                setNewName("");
              }}
              className="px-3 py-1.5 bg-tc-hover hover:bg-tc-active rounded text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3">
        {entries.map((entry) => (
          <Link
            key={entry.id}
            to={`/codex/${entry.id}`}
            className="flex items-center gap-4 p-4 bg-tc-overlay hover:bg-tc-hover rounded-lg border border-tc-subtle hover:border-tc-strong transition-colors"
          >
            {entry.primary_image_url && (
              <img
                src={entry.primary_image_url}
                alt={entry.name}
                className="w-10 h-10 rounded object-cover flex-shrink-0"
              />
            )}
            <div className="flex-1 min-w-0">
              <h3 className="font-medium">{entry.name}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs px-2 py-0.5 bg-tc-hover rounded-full text-tc-tertiary capitalize">
                  {entry.entry_type}
                </span>
                {entry.tags.length > 0 && (
                  <span className="flex items-center gap-1 text-xs text-tc-muted">
                    <Tag size={12} />
                    {entry.tags.length}
                  </span>
                )}
              </div>
            </div>
            {!workId && !seriesId && (entry.work_ids.length > 0 || entry.series_ids.length > 0) && (
              <div className="text-xs text-tc-muted">
                {entry.work_ids.length > 0 && (
                  <span>{entry.work_ids.length} work{entry.work_ids.length > 1 ? "s" : ""}</span>
                )}
                {entry.work_ids.length > 0 && entry.series_ids.length > 0 && " · "}
                {entry.series_ids.length > 0 && (
                  <span>{entry.series_ids.length} series</span>
                )}
              </div>
            )}
          </Link>
        ))}
      </div>

      {entries.length === 0 && (
        <div className="text-center py-12 text-tc-muted">
          <p>No codex entries found.</p>
        </div>
      )}
    </div>
  );
}
