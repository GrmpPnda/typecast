import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useBlocker } from "react-router-dom";
import { ArrowLeft, Save, StickyNote, X, ClipboardCopy } from "lucide-react";
import { getScene, updateScene } from "@/api/scenes";
import { listImages } from "@/api/images";
import { listCodexEntries } from "@/api/codex";
import { listConfig } from "@/api/config";
import Editor from "@/components/Editor";
import type { EditorImage } from "@/components/Editor";
import { useState, useEffect, useRef, useCallback } from "react";
import { Scene } from "@/types";

export default function WritingEditor() {
  const { id: workId, sceneId } = useParams<{ id: string; sceneId: string }>();
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const [wordCount, setWordCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const [sceneStatus, setSceneStatus] = useState<Scene["status"]>("draft");
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>();
  const notesTimer = useRef<ReturnType<typeof setTimeout>>();

  const { data: scene } = useQuery({
    queryKey: ["scene", sceneId],
    queryFn: () => getScene(sceneId!),
    enabled: !!sceneId,
  });

  const { data: workImages = [] } = useQuery({
    queryKey: ["images", workId],
    queryFn: () => listImages(workId!),
    enabled: !!workId,
  });

  const editorImages: EditorImage[] = workImages.map((img) => ({
    id: img.id,
    url: img.url,
    alt_text: img.alt_text,
    original_name: img.original_name,
  }));

  const { data: codexEntries = [] } = useQuery({
    queryKey: ["codex", { workId }],
    queryFn: () => listCodexEntries({ workId }),
    enabled: !!workId,
  });

  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });

  const customDictionary = codexEntries.map((e) => e.name);
  const globalSpellcheck = config.find((c) => c.key === "spellcheck_enabled")?.value !== "false";

  const saveMutation = useMutation({
    mutationFn: (newContent: string) =>
      updateScene(sceneId!, { content: newContent }),
    onMutate: () => setSaving(true),
    onSettled: () => {
      setSaving(false);
      setDirty(false);
    },
  });

  const notesMutation = useMutation({
    mutationFn: (newNotes: string) =>
      updateScene(sceneId!, { notes: newNotes }),
  });

  useEffect(() => {
    if (scene) {
      setContent(scene.content);
      setWordCount(scene.word_count);
      setNotes(scene.notes);
      setSceneStatus(scene.status);
    }
  }, [scene]);

  const countWords = useCallback((text: string) => {
    const stripped = text.replace(/[#*_~`>\-|]/g, "").trim();
    if (!stripped) return 0;
    return stripped.split(/\s+/).length;
  }, []);

  const handleChange = useCallback(
    (newContent: string) => {
      setContent(newContent);
      setWordCount(countWords(newContent));
      setDirty(true);

      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
      debounceTimer.current = setTimeout(() => {
        saveMutation.mutate(newContent);
      }, 1500);
    },
    [saveMutation, countWords]
  );

  const handleSave = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    saveMutation.mutate(content);
  }, [saveMutation, content]);

  const handleNotesChange = useCallback(
    (newNotes: string) => {
      setNotes(newNotes);
      if (notesTimer.current) clearTimeout(notesTimer.current);
      notesTimer.current = setTimeout(() => {
        notesMutation.mutate(newNotes);
      }, 1000);
    },
    [notesMutation]
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (notesTimer.current) clearTimeout(notesTimer.current);
    };
  }, [handleSave]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const blocker = useBlocker(dirty);

  useEffect(() => {
    if (blocker.state === "blocked") {
      if (window.confirm("You have unsaved changes. Leave without saving?")) {
        blocker.proceed();
      } else {
        blocker.reset();
      }
    }
  }, [blocker]);

  if (!scene) return null;

  const statusLabel = {
    outline: "Outline",
    draft: "Draft",
    revision: "Revision",
    final: "Final",
  };

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between px-6 py-3 border-b border-tc-default bg-tc-base/80 backdrop-blur shrink-0">
        <div className="flex items-center gap-4">
          <Link
            to={`/work/${workId}/chapter/${scene.chapter_id}`}
            className="text-tc-tertiary hover:text-tc-secondary transition-colors"
          >
            <ArrowLeft size={20} />
          </Link>
          <h1 className="font-medium text-tc-secondary">
            {scene.title || "Untitled Scene"}
          </h1>
          <span className="px-2 py-0.5 rounded text-xs bg-tc-hover text-tc-tertiary">
            {statusLabel[sceneStatus]}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm text-tc-muted">
          {saving && <span className="text-tc-accent">Saving...</span>}
          <span>{wordCount.toLocaleString()} words</span>
          <button
            onClick={handleSave}
            disabled={!dirty && !saving}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              dirty
                ? "bg-tc-accent hover:bg-tc-accent-hover text-tc-primary"
                : "bg-tc-overlay text-tc-muted"
            }`}
            title="Save (⌘S)"
          >
            <Save size={14} />
            Save
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(content)}
            className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            title="Copy markdown"
          >
            <ClipboardCopy size={18} />
          </button>
          <button
            onClick={() => setShowNotes(!showNotes)}
            className={`p-1.5 rounded transition-colors ${
              showNotes ? "bg-tc-hover text-tc-secondary" : "text-tc-muted hover:text-tc-secondary"
            }`}
            title="Toggle Notes"
          >
            <StickyNote size={18} />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
          <Editor
            content={content}
            onChange={handleChange}
            placeholder="Begin your scene..."
            images={editorImages}
            workId={workId}
            onImageUploaded={() => queryClient.invalidateQueries({ queryKey: ["images", workId] })}
            spellcheckEnabled={globalSpellcheck}
            customDictionary={customDictionary}
          />
        </main>

        {showNotes && (
          <aside className="w-80 border-l border-tc-default bg-tc-base flex flex-col shrink-0">
            <div className="flex items-center justify-between px-4 py-3 border-b border-tc-default">
              <span className="text-sm font-medium text-tc-secondary">Scene Notes</span>
              <button
                onClick={() => setShowNotes(false)}
                className="text-tc-muted hover:text-tc-secondary transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <textarea
              value={notes}
              onChange={(e) => handleNotesChange(e.target.value)}
              placeholder="Scene notes, reminders, research..."
              className="flex-1 p-4 bg-transparent text-sm text-tc-secondary placeholder-gray-600 resize-none focus:outline-none font-mono"
            />
          </aside>
        )}
      </div>
    </div>
  );
}
