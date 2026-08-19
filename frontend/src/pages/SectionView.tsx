import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Save, BookOpenCheck } from "lucide-react";
import { getSection, updateSection } from "@/api/sections";
import { getWork } from "@/api/works";
import { listImages } from "@/api/images";
import { useState, useRef, useCallback, useEffect } from "react";
import Markdown from "react-markdown";
import Editor from "@/components/Editor";
import type { EditorImage } from "@/components/Editor";

export default function SectionView() {
  const { id, sectionId } = useParams<{ id: string; sectionId: string }>();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const contentInitialized = useRef(false);

  const { data: work } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const { data: section } = useQuery({
    queryKey: ["section", sectionId],
    queryFn: () => getSection(sectionId!),
    enabled: !!sectionId,
  });

  const { data: workImages = [] } = useQuery({
    queryKey: ["images", id],
    queryFn: () => listImages(id!),
    enabled: !!id,
  });

  const editorImages: EditorImage[] = workImages.map((img) => ({
    id: img.id,
    url: img.url,
    alt_text: img.alt_text,
    original_name: img.original_name,
  }));

  if (section && !contentInitialized.current) {
    setEditContent(section.content);
    contentInitialized.current = true;
  }

  useEffect(() => {
    contentInitialized.current = false;
  }, [sectionId]);

  const saveMutation = useMutation({
    mutationFn: (content: string) => updateSection(sectionId!, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["section", sectionId] });
      setDirty(false);
      setEditing(false);
    },
  });

  const handleEdit = useCallback(() => {
    if (section) {
      setEditContent(section.content);
      setDirty(false);
      setEditing(true);
    }
  }, [section]);

  const handleCancel = useCallback(() => {
    if (dirty && !confirm("Discard unsaved changes?")) return;
    setEditing(false);
    setDirty(false);
  }, [dirty]);

  const handleChange = useCallback((newContent: string) => {
    setEditContent(newContent);
    setDirty(true);
  }, []);

  if (!section || !work) return null;

  const label =
    section.title ||
    section.section_type
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Link
        to={`/work/${id}`}
        className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-6 text-sm"
      >
        <ArrowLeft size={16} />
        Back to Work
      </Link>

      <div className="flex items-center justify-between mb-8">
        <div>
          <p className="text-sm text-tc-muted mb-0.5">
            {section.placement === "front_matter" ? "Front Matter" : "Back Matter"}
          </p>
          <h1 className="text-2xl font-bold">{label}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/work/${id}/read`}
            className="flex items-center gap-2 px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-tertiary hover:text-tc-secondary rounded-lg text-sm transition-colors"
            title="Read"
          >
            <BookOpenCheck size={16} />
          </Link>
          {editing && (
            <button
              onClick={() => saveMutation.mutate(editContent)}
              disabled={!dirty || saveMutation.isPending}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                dirty
                  ? "bg-tc-accent hover:bg-tc-accent-hover text-tc-primary"
                  : "bg-tc-hover text-tc-muted"
              }`}
            >
              <Save size={14} />
              {saveMutation.isPending ? "Saving..." : "Save"}
            </button>
          )}
        </div>
      </div>

      <div className="relative p-5 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-tc-muted font-medium">Content</span>
          {!editing && (
            <button
              onClick={handleEdit}
              className="text-xs text-tc-muted hover:text-tc-secondary transition-colors"
            >
              Edit
            </button>
          )}
          {editing && (
            <button
              onClick={handleCancel}
              className="text-xs text-tc-muted hover:text-tc-secondary transition-colors"
            >
              Cancel
            </button>
          )}
        </div>

        {editing ? (
          <Editor
            content={editContent}
            onChange={handleChange}
            placeholder="Write section content..."
            images={editorImages}
            workId={id}
            onImageUploaded={() => queryClient.invalidateQueries({ queryKey: ["images", id] })}
          />
        ) : (
          <div
            className="prose prose-invert prose-sm max-w-none text-tc-secondary leading-relaxed cursor-text"
            onClick={handleEdit}
          >
            {section.content ? (
              <Markdown>{section.content}</Markdown>
            ) : (
              <p className="text-tc-muted italic">No content yet — click to write</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
