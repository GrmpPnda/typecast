import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Save, Trash2 } from "lucide-react";
import { getWork, updateWork, deleteWork } from "@/api/works";
import { listProfiles } from "@/api/profiles";
import { listSeries } from "@/api/series";
import { useState, useEffect, useCallback } from "react";
import { UpdateWork, Work } from "@/types";


function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const tag = input.trim();
      if (tag && !value.includes(tag)) {
        onChange([...value, tag]);
      }
      setInput("");
    }
    if (e.key === "Backspace" && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap gap-2 bg-tc-hover border border-tc-strong rounded px-3 py-2 focus-within:border-tc-accent">
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 px-2 py-0.5 bg-tc-accent/30 text-tc-accent rounded text-sm"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(value.filter((t) => t !== tag))}
            className="text-tc-accent hover:text-tc-accent"
          >
            &times;
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[120px] bg-transparent outline-none text-sm text-tc-primary placeholder-gray-500"
      />
    </div>
  );
}

export default function WorkSettings() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<UpdateWork>({});
  const [dirty, setDirty] = useState(false);

  const { data: work } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const { data: profiles = [] } = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const { data: allSeries = [] } = useQuery({
    queryKey: ["series"],
    queryFn: listSeries,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: UpdateWork) => updateWork(id!, payload),
    onSuccess: (updated: Work) => {
      queryClient.setQueryData(["work", id], updated);
      setDirty(false);
    },
  });

  const deleteWorkMutation = useMutation({
    mutationFn: () => deleteWork(id!),
    onSuccess: () => navigate("/"),
  });

  useEffect(() => {
    if (work) {
      setForm({
        title: work.title,
        subtitle: work.subtitle ?? "",
        author: work.author,
        status: work.status,
        isbn: work.isbn ?? "",
        publisher: work.publisher ?? "",
        website: work.website ?? "",
        publication_date: work.publication_date ?? "",
        edition: work.edition ?? "",
        language: work.language,
        genre: work.genre,
        tags: work.tags,
        blurb: work.blurb ?? "",
        description: work.description ?? "",
        word_count_target: work.word_count_target,
        notes: work.notes,
        ai_instructions: work.ai_instructions,
        default_profile_id: work.default_profile_id,
        series_id: work.series_id,
        sort_order: work.sort_order,
      });
    }
  }, [work]);

  const update = useCallback((patch: Partial<UpdateWork>) => {
    setForm((prev) => ({ ...prev, ...patch }));
    setDirty(true);
  }, []);

  const handleSave = () => {
    const cleaned: UpdateWork = { ...form };
    const nullableStrings: (keyof UpdateWork)[] = [
      "subtitle", "isbn", "publisher", "publication_date",
      "edition", "blurb", "description", "website",
    ];
    for (const key of nullableStrings) {
      if (cleaned[key] === "") {
        (cleaned as Record<string, unknown>)[key] = null;
      }
    }
    saveMutation.mutate(cleaned);
  };

  if (!work) return null;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <Link
          to={`/work/${id}`}
          className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary text-sm"
        >
          <ArrowLeft size={16} />
          Back to Work
        </Link>
        <button
          onClick={handleSave}
          disabled={!dirty || saveMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={16} />
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
      </div>

      <h1 className="text-2xl font-bold mb-8">Work Settings</h1>

      <div className="space-y-8">
        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Basic Info</h2>
          <div className="grid gap-4">
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Title</label>
              <input
                type="text"
                value={form.title ?? ""}
                onChange={(e) => update({ title: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Subtitle</label>
              <input
                type="text"
                value={form.subtitle ?? ""}
                onChange={(e) => update({ subtitle: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">
                Author <span className="text-tc-error">*</span>
              </label>
              <input
                type="text"
                value={form.author ?? ""}
                onChange={(e) => update({ author: e.target.value })}
                required
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Status</label>
              <select
                value={form.status ?? "draft"}
                onChange={(e) => update({ status: e.target.value as Work["status"] })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                <option value="draft">Draft</option>
                <option value="revision">Revision</option>
                <option value="complete">Complete</option>
                <option value="published">Published</option>
              </select>
            </div>
          </div>
        </section>

        {allSeries.length > 0 && (
          <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Series</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm text-tc-tertiary mb-1">Series</label>
                <select
                  value={form.series_id ?? ""}
                  onChange={(e) =>
                    update({ series_id: e.target.value || null })
                  }
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                >
                  <option value="">None (standalone)</option>
                  {allSeries.map((s) => (
                    <option key={s.id} value={s.id}>{s.title}</option>
                  ))}
                </select>
              </div>
              {form.series_id && (
                <div>
                  <label className="block text-sm text-tc-tertiary mb-1">Series Order</label>
                  <input
                    type="number"
                    min={1}
                    value={(form.sort_order ?? 0) + 1}
                    onChange={(e) => update({ sort_order: Math.max(0, parseInt(e.target.value || "1") - 1) })}
                    className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                  />
                  <p className="text-xs text-tc-muted mt-1">Position in the series (1 = first)</p>
                </div>
              )}
            </div>
          </section>
        )}

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Publishing</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">ISBN</label>
              <input
                type="text"
                value={form.isbn ?? ""}
                onChange={(e) => update({ isbn: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Publisher</label>
              <input
                type="text"
                value={form.publisher ?? ""}
                onChange={(e) => update({ publisher: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Website</label>
              <input
                type="text"
                value={form.website ?? ""}
                onChange={(e) => update({ website: e.target.value })}
                placeholder="yourwebsite.com"
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Publication Date</label>
              <input
                type="date"
                value={form.publication_date ?? ""}
                onChange={(e) => update({ publication_date: e.target.value || null })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Edition</label>
              <input
                type="text"
                value={form.edition ?? ""}
                onChange={(e) => update({ edition: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Language</label>
              <input
                type="text"
                value={form.language ?? "en"}
                onChange={(e) => update({ language: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
          </div>
        </section>

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Discovery</h2>
          <div className="grid gap-4">
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Genre</label>
              <TagInput
                value={form.genre ?? []}
                onChange={(genre) => update({ genre })}
                placeholder="Add genres (press Enter or comma)"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Tags</label>
              <TagInput
                value={form.tags ?? []}
                onChange={(tags) => update({ tags })}
                placeholder="Add tags (press Enter or comma)"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Blurb</label>
              <textarea
                value={form.blurb ?? ""}
                onChange={(e) => update({ blurb: e.target.value })}
                rows={4}
                placeholder="Back-cover marketing copy..."
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y"
              />
            </div>
            <div>
              <label className="block text-sm text-tc-tertiary mb-1">Description</label>
              <textarea
                value={form.description ?? ""}
                onChange={(e) => update({ description: e.target.value })}
                rows={3}
                placeholder="Internal description..."
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y"
              />
            </div>
          </div>
        </section>

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Writing</h2>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Word Count Target</label>
            <input
              type="number"
              value={form.word_count_target ?? ""}
              onChange={(e) =>
                update({ word_count_target: e.target.value ? parseInt(e.target.value) : null })
              }
              placeholder="e.g. 80000"
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
            />
          </div>
        </section>

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Reading Profile</h2>
          <p className="text-xs text-tc-muted mb-3">
            Select the default profile used for reading mode and export.
          </p>
          <select
            value={form.default_profile_id ?? ""}
            onChange={(e) =>
              update({ default_profile_id: e.target.value || null })
            }
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
          >
            <option value="">None</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.format.toUpperCase()})
              </option>
            ))}
          </select>
        </section>

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Notes</h2>
          <p className="text-xs text-tc-muted mb-2">Private Notes (not included in export)</p>
          <textarea
            value={form.notes ?? ""}
            onChange={(e) => update({ notes: e.target.value })}
            rows={12}
            placeholder="Your private notes, outlines, research..."
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y font-mono"
          />
        </section>

        <section className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">AI Instructions</h2>
          <p className="text-xs text-tc-muted mb-2">
            Guidelines for the AI assistant when working on this work — voice, style, conventions, priorities, things to avoid.
            {work.series_id && " Series-level instructions are also sent to the AI."}
          </p>
          <textarea
            value={form.ai_instructions ?? ""}
            onChange={(e) => update({ ai_instructions: e.target.value })}
            rows={8}
            placeholder="e.g. Write in first-person present tense. Keep dialogue sparse and punchy. Avoid adverbs..."
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y font-mono"
          />
        </section>

        <section className="border border-tc-error/50 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-tc-error mb-2">Danger Zone</h2>
          <p className="text-sm text-tc-muted mb-4">
            Permanently delete this work and all its chapters, scenes, and sections. This cannot be undone.
          </p>
          <button
            onClick={() => {
              if (confirm("Delete this entire work and all its chapters, scenes, and sections?")) {
                deleteWorkMutation.mutate();
              }
            }}
            disabled={deleteWorkMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 border border-tc-error text-tc-error hover:bg-tc-error-subtle hover:text-tc-error disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
          >
            <Trash2 size={16} />
            Delete Work
          </button>
        </section>
      </div>
    </div>
  );
}
