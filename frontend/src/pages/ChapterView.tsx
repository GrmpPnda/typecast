import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useLocation, useOutletContext } from "react-router-dom";
import {
  ArrowLeft,
  Plus,
  PenLine,
  Save,
  X,
  StickyNote,
  ChevronDown,
  ChevronRight,
  Trash2,
  MoreHorizontal,
  Maximize2,
  BookOpenCheck,
  ImageIcon,
  EyeOff,
  Eye,
  Scissors,
  MessageSquareQuote,
  CheckCircle,
  Volume2,
  Square,
  ClipboardCopy,
} from "lucide-react";
import { getChapter, updateChapter } from "@/api/chapters";
import { listScenes, createScene, updateScene, deleteScene, splitScene } from "@/api/scenes";
import { getWork, updateWork } from "@/api/works";
import { useState, useRef, useCallback, useEffect } from "react";
import Markdown from "react-markdown";
import Editor from "@/components/Editor";
import type { EditorImage } from "@/components/Editor";
import TitlePageEditor from "@/components/TitlePageEditor";
import { listImages } from "@/api/images";
import { streamNarration, NarrationSegment } from "@/api/narration";
import { listCodexEntries } from "@/api/codex";
import { listConfig } from "@/api/config";
import { Scene, TitlePageConfig } from "@/types";
import { listComments, updateComment, deleteComment, clearCheckpoint } from "@/api/comments";
import type { CommentHighlight } from "@/extensions/comments";
import type { AppOutletContext } from "@/App";
import { diffRanges } from "@/diff";

function CollapsedImage({ alt, src }: { alt?: string; src?: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="my-3 border border-tc-subtle/50 rounded-lg overflow-hidden cursor-pointer"
      onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
    >
      {expanded ? (
        <img src={src} alt={alt || ""} className="max-w-full rounded-lg" />
      ) : (
        <div className="flex items-center gap-2 px-3 py-2 bg-tc-overlay/50 text-tc-muted text-xs">
          <ImageIcon size={14} />
          <span>{alt || "Image"}</span>
        </div>
      )}
    </div>
  );
}

const collapsedComponents = {
  img: ({ alt, src }: { alt?: string; src?: string }) => (
    <CollapsedImage alt={alt} src={src} />
  ),
};

const MATTER_TITLES = new Set([
  "dedication", "preface", "foreword", "introduction", "prologue",
  "epilogue", "afterword", "acknowledgments", "acknowledgements",
  "appendix", "glossary", "bibliography", "about the author",
  "also by", "colophon", "copyright", "half title", "title page",
]);

function hasSceneBreak(content: string): boolean {
  return /\n---\n|\n\*\*\*\n|\n___\n|^---$|^---\n|\n---$/m.test(content);
}

function InsertSceneButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <div className="group relative flex items-center justify-center py-1">
      <div className="absolute inset-x-0 top-1/2 h-px bg-tc-hover/0 group-hover:bg-tc-hover transition-colors" />
      <button
        onClick={onClick}
        disabled={disabled}
        className="relative z-10 flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
          text-tc-muted hover:text-tc-secondary bg-tc-base border border-tc-subtle/0 hover:border-tc-subtle
          opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
        title="Insert scene here"
      >
        <Plus size={12} />
        Add scene
      </button>
    </div>
  );
}

function SceneCard({
  scene,
  index,
  workId,
  chapterId,
  onDelete,
  onSplit,
  label,
  hideMenu,
  images,
  onImageUploaded,
  spellcheckEnabled,
  customDictionary,
  activeCommentId,
  onCommentClick,
  onStartComment,
  pollyEnabled,
}: {
  scene: Scene;
  index: number;
  workId: string;
  chapterId: string;
  onDelete: () => void;
  onSplit: () => void;
  label?: string;
  hideMenu?: boolean;
  images?: EditorImage[];
  onImageUploaded?: () => void;
  spellcheckEnabled?: boolean;
  customDictionary?: string[];
  activeCommentId: string | null;
  onCommentClick: (commentId: string) => void;
  onStartComment: (sceneId: string, anchorText: string, anchorFrom: number, anchorTo: number) => void;
  pollyEnabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState(scene.content);
  const [dirty, setDirty] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showSplitBanner, setShowSplitBanner] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [commentHighlights, setCommentHighlights] = useState<CommentHighlight[]>([]);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const proseRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const audioQueueRef = useRef<string[]>([]);
  const playingIndexRef = useRef<number>(-1);
  const [narrating, setNarrating] = useState<"loading" | "playing" | false>(false);
  const [narrationError, setNarrationError] = useState<string | null>(null);
  const [narrationSegments, setNarrationSegments] = useState<NarrationSegment[]>([]);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number>(-1);
  const [narrationExpanded, setNarrationExpanded] = useState(true);
  const narrationListRef = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; anchorText: string; commentId?: string;
  } | null>(null);

  const { data: comments = [] } = useQuery({
    queryKey: ["comments", scene.id],
    queryFn: () => listComments(scene.id),
  });

  useEffect(() => {
    const highlights: CommentHighlight[] = comments.map((c) => ({
      id: c.id,
      anchorText: c.anchor_text,
      content: c.content,
      resolved: c.resolved,
    }));
    setCommentHighlights(highlights);
  }, [comments]);

  const resolveMutation = useMutation({
    mutationFn: (id: string) => updateComment(id, { resolved: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", scene.id] });
      queryClient.invalidateQueries({ queryKey: ["chapter-comments", chapterId] });
    },
  });

  const deleteCommentMutation = useMutation({
    mutationFn: deleteComment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", scene.id] });
      queryClient.invalidateQueries({ queryKey: ["chapter-comments", chapterId] });
    },
  });

  useEffect(() => {
    if (!showMenu) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [showMenu]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [contextMenu]);

  useEffect(() => {
    if (activeSegmentIndex >= 0 && narrationListRef.current) {
      const el = narrationListRef.current.children[activeSegmentIndex] as HTMLElement;
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeSegmentIndex]);

  const activeCommentRef = useRef(activeCommentId);
  activeCommentRef.current = activeCommentId;

  const onCommentClickRef = useRef(onCommentClick);
  onCommentClickRef.current = onCommentClick;

  useEffect(() => {
    const container = proseRef.current;
    if (!container || editing || !scene.checkpoint) return;

    const ranges = diffRanges(scene.checkpoint, scene.content || "");
    if (ranges.length === 0) return;

    const collectSegments = () => {
      const w = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      const segs: { node: Text; start: number; end: number }[] = [];
      let offset = 0;
      while (w.nextNode()) {
        const node = w.currentNode as Text;
        const len = node.textContent?.length || 0;
        segs.push({ node, start: offset, end: offset + len });
        offset += len;
      }
      return segs;
    };

    for (const range of ranges) {
      const segments = collectSegments();
      const hits = segments
        .filter((seg) => seg.end > range.from && seg.start < range.to)
        .filter((seg) => !seg.node.parentElement?.closest(".ai-diff-highlight"));

      for (let i = hits.length - 1; i >= 0; i--) {
        const seg = hits[i];
        const nodeStart = Math.max(0, range.from - seg.start);
        const nodeEnd = Math.min(seg.node.textContent!.length, range.to - seg.start);
        if (nodeEnd <= nodeStart) continue;

        const r = document.createRange();
        r.setStart(seg.node, nodeStart);
        r.setEnd(seg.node, nodeEnd);

        const span = document.createElement("span");
        span.className = "ai-diff-highlight";
        r.surroundContents(span);
      }
    }

    return () => {
      container.querySelectorAll(".ai-diff-highlight").forEach((el) => {
        const parent = el.parentNode;
        if (!parent) return;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
        parent.normalize();
      });
    };
  }, [editing, scene.checkpoint, scene.content]);

  useEffect(() => {
    const container = proseRef.current;
    if (!container || editing) return;

    const unresolvedHighlights = commentHighlights.filter((c) => !c.resolved && c.anchorText);
    if (unresolvedHighlights.length === 0) return;

    const stripMd = (s: string) => s.replace(/(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)/g, "");

    const collectTextNodes = () => {
      const w = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      while (w.nextNode()) nodes.push(w.currentNode as Text);
      return nodes;
    };

    const findAndWrap = (needle: string, commentId: string): boolean => {
      const textNodes = collectTextNodes();
      let concat = "";
      const segments: { node: Text; start: number; end: number }[] = [];
      for (const node of textNodes) {
        const len = node.textContent?.length || 0;
        segments.push({ node, start: concat.length, end: concat.length + len });
        concat += node.textContent || "";
      }

      const idx = concat.indexOf(needle);
      if (idx === -1) return false;

      const endIdx = idx + needle.length;
      for (const seg of segments) {
        if (seg.end <= idx || seg.start >= endIdx) continue;
        const nodeStart = Math.max(0, idx - seg.start);
        const nodeEnd = Math.min(seg.node.textContent!.length, endIdx - seg.start);

        const range = document.createRange();
        range.setStart(seg.node, nodeStart);
        range.setEnd(seg.node, nodeEnd);

        const span = document.createElement("span");
        span.className = "comment-highlight";
        span.dataset.commentId = commentId;
        span.addEventListener("click", (e) => {
          e.stopPropagation();
          onCommentClickRef.current(commentId);
        });
        span.addEventListener("contextmenu", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const hl = unresolvedHighlights.find((h) => h.id === commentId);
          setContextMenu({ x: e.clientX, y: e.clientY, anchorText: hl?.anchorText || "", commentId });
        });
        range.surroundContents(span);
      }
      return true;
    };

    for (const hl of unresolvedHighlights) {
      if (!findAndWrap(hl.anchorText, hl.id)) {
        findAndWrap(stripMd(hl.anchorText), hl.id);
      }
    }

    return () => {
      container.querySelectorAll(".comment-highlight").forEach((el) => {
        const parent = el.parentNode;
        if (!parent) return;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
        parent.normalize();
      });
    };
  }, [commentHighlights, editing, scene.content]);

  useEffect(() => {
    const container = proseRef.current;
    if (!container) return;
    container.querySelectorAll(".comment-highlight").forEach((el) => {
      const id = (el as HTMLElement).dataset.commentId;
      el.classList.toggle("comment-active", id === activeCommentId);
    });
  }, [activeCommentId]);

  const startCommentFromSelection = () => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() || "";
    if (!text) return;
    const content = scene.content || "";
    const from = content.indexOf(text);
    onStartComment(
      scene.id,
      text,
      from >= 0 ? from : 0,
      from >= 0 ? from + text.length : 0,
    );
    setContextMenu(null);
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() || "";
    if (!text) return;
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, anchorText: text });
  };

  const saveMutation = useMutation({
    mutationFn: (content: string) => updateScene(scene.id, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenes", { chapterId }] });
      setDirty(false);
      setEditing(false);
      setShowSplitBanner(false);
    },
  });

  const handleEdit = () => {
    setEditContent(scene.content);
    setDirty(false);
    setShowSplitBanner(false);
    setEditing(true);
  };

  const handleCancel = () => {
    if (dirty && !confirm("Discard unsaved changes?")) return;
    setEditing(false);
    setDirty(false);
    setShowSplitBanner(false);
  };

  const handleSave = () => {
    if (hasSceneBreak(editContent)) {
      setShowSplitBanner(true);
    }
    saveMutation.mutate(editContent);
  };

  const handleChange = (newContent: string) => {
    setEditContent(newContent);
    setDirty(true);
    if (showSplitBanner && !hasSceneBreak(newContent)) {
      setShowSplitBanner(false);
    }
  };

  return (
    <div
      id={`scene-${scene.id}`}
      data-scene-id={scene.id}
      className="scene-block relative p-5 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50 group"
    >
      {showSplitBanner && (
        <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-tc-secondary-subtle border border-tc-secondary/30 text-xs">
          <Scissors size={13} className="text-tc-secondary-accent flex-shrink-0" />
          <span className="text-tc-secondary-accent/90 flex-1">
            This scene contains a scene break. Split into two scenes?
          </span>
          <button
            onClick={() => { setShowSplitBanner(false); onSplit(); }}
            className="px-2.5 py-1 rounded bg-tc-secondary-hover/30 hover:bg-tc-secondary-hover/50 text-tc-secondary-accent font-medium transition-colors"
          >
            Split
          </button>
          <button
            onClick={() => setShowSplitBanner(false)}
            className="p-0.5 text-tc-secondary-accent/50 hover:text-tc-secondary-accent transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-tc-muted font-medium">
          {scene.title || label || `Scene ${index + 1}`}
        </span>
        <div className="flex items-center gap-1">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={!dirty || saveMutation.isPending}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors ${
                  dirty
                    ? "bg-tc-accent hover:bg-tc-accent-hover text-tc-primary"
                    : "bg-tc-hover text-tc-muted"
                }`}
              >
                <Save size={12} />
                {saveMutation.isPending ? "Saving..." : "Save"}
              </button>
              <button
                onClick={handleCancel}
                className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
                title="Cancel"
              >
                <X size={14} />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEdit}
                className="p-1.5 text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100 rounded transition-all"
                title="Edit inline"
              >
                <PenLine size={14} />
              </button>
              <button
                onClick={startCommentFromSelection}
                className="p-1.5 text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100 rounded transition-all"
                title="Add comment on selected text"
              >
                <MessageSquareQuote size={14} />
              </button>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(scene.content || "");
                }}
                className="p-1.5 text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100 rounded transition-all"
                title="Copy markdown"
              >
                <ClipboardCopy size={14} />
              </button>
              {pollyEnabled && (
                <button
                  onClick={() => {
                    if (narrating) {
                      abortRef.current?.abort();
                      abortRef.current = null;
                      audioRef.current?.pause();
                      if (audioRef.current?.src) {
                        URL.revokeObjectURL(audioRef.current.src);
                        audioRef.current.src = "";
                      }
                      audioQueueRef.current = [];
                      playingIndexRef.current = -1;
                      setNarrating(false);
                      setNarrationSegments([]);
                      setActiveSegmentIndex(-1);
                    } else {
                      setNarrating("loading");
                      setNarrationError(null);
                      setNarrationSegments([]);
                      setActiveSegmentIndex(-1);
                      audioQueueRef.current = [];
                      playingIndexRef.current = -1;
                      const ctrl = new AbortController();
                      abortRef.current = ctrl;
                      streamNarration(workId, scene.id, (event) => {
                        if (ctrl.signal.aborted) return;
                        if (event.type === "error") {
                          setNarrationError(event.message);
                          setNarrating(false);
                          setNarrationSegments([]);
                          setActiveSegmentIndex(-1);
                        } else if (event.type === "segments") {
                          setNarrationSegments(event.segments);
                        } else if (event.type === "audio") {
                          const b64 = event.audio;
                          const blobUrl = URL.createObjectURL(
                            new Blob(
                              [Uint8Array.from(atob(b64), c => c.charCodeAt(0))],
                              { type: "audio/mpeg" }
                            )
                          );
                          audioQueueRef.current.push(blobUrl);
                          if (playingIndexRef.current === -1) {
                            playingIndexRef.current = 0;
                            setActiveSegmentIndex(0);
                            setNarrating("playing");
                            if (audioRef.current) {
                              audioRef.current.src = blobUrl;
                              audioRef.current.play();
                            }
                          }
                        } else if (event.type === "done") {
                          if (audioQueueRef.current.length === 0) {
                            setNarrating(false);
                            setNarrationSegments([]);
                          }
                        }
                      }, ctrl.signal);
                    }
                  }}
                  disabled={narrating === "loading"}
                  className={`p-1.5 rounded transition-all ${
                    narrating
                      ? "text-tc-accent hover:text-tc-accent"
                      : "text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100"
                  }`}
                  title={narrating === "loading" ? "Generating narration..." : narrating ? "Stop narration" : "Listen to scene"}
                >
                  {narrating === "loading" ? (
                    <Volume2 size={14} className="animate-pulse" />
                  ) : narrating ? (
                    <Square size={14} />
                  ) : (
                    <Volume2 size={14} />
                  )}
                </button>
              )}
              {!hideMenu && (
                <div className="relative" ref={menuRef}>
                  <button
                    onClick={() => setShowMenu(!showMenu)}
                    className="p-1.5 text-tc-muted hover:text-tc-secondary opacity-0 group-hover:opacity-100 rounded transition-all"
                  >
                    <MoreHorizontal size={14} />
                  </button>
                  {showMenu && (
                    <div className="absolute right-0 top-8 z-10 w-44 bg-tc-overlay border border-tc-subtle rounded-lg shadow-xl py-1">
                      <Link
                        to={`/work/${workId}/write/${scene.id}`}
                        className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary hover:bg-tc-hover transition-colors"
                      >
                        <Maximize2 size={13} />
                        Edit full screen
                      </Link>
                      {hasSceneBreak(scene.content) && (
                        <button
                          onClick={() => { setShowMenu(false); onSplit(); }}
                          className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary-accent hover:bg-tc-hover transition-colors w-full text-left"
                        >
                          <Scissors size={13} />
                          Split at break
                        </button>
                      )}
                      {scene.checkpoint && (
                        <button
                          onClick={async () => {
                            setShowMenu(false);
                            await clearCheckpoint(scene.id);
                            queryClient.invalidateQueries({ queryKey: ["scenes"] });
                          }}
                          className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary hover:bg-tc-hover transition-colors w-full text-left"
                        >
                          <CheckCircle size={13} />
                          Accept AI changes
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setShowMenu(false);
                          if (confirm(`Delete "${scene.title || "this scene"}"?`)) {
                            onDelete();
                          }
                        }}
                        className="flex items-center gap-2 px-3 py-2 text-sm text-tc-error hover:bg-tc-hover transition-colors w-full text-left"
                      >
                        <Trash2 size={13} />
                        Delete scene
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {narrating && narrationSegments.length > 0 && (
        <div className="mb-3 rounded-lg border border-tc-subtle/50 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-tc-overlay/50">
            <button
              onClick={() => setNarrationExpanded(!narrationExpanded)}
              className="p-0.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            >
              {narrationExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            <Volume2 size={14} className={`text-tc-accent ${narrating === "loading" ? "animate-pulse" : ""}`} />
            <span className="text-xs text-tc-tertiary">
              {narrating === "loading" ? "Generating narration..." : `Segment ${activeSegmentIndex + 1} of ${narrationSegments.length}`}
            </span>
            <button
              onClick={() => {
                abortRef.current?.abort();
                abortRef.current = null;
                audioRef.current?.pause();
                if (audioRef.current?.src) {
                  URL.revokeObjectURL(audioRef.current.src);
                  audioRef.current.src = "";
                }
                audioQueueRef.current = [];
                playingIndexRef.current = -1;
                setNarrating(false);
                setNarrationSegments([]);
                setActiveSegmentIndex(-1);
              }}
              className="ml-auto p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
              title="Stop"
            >
              <Square size={12} />
            </button>
          </div>
          {narrationExpanded && (
            <div ref={narrationListRef} className="px-3 py-2 max-h-32 overflow-y-auto text-xs space-y-1">
              {narrationSegments.map((seg, i) => (
                <div
                  key={i}
                  className={`flex gap-2 py-0.5 rounded transition-colors ${
                    i === activeSegmentIndex ? "bg-tc-accent/10 text-tc-secondary" : i < activeSegmentIndex ? "text-tc-muted" : "text-tc-muted"
                  }`}
                >
                  <span className={`shrink-0 font-medium w-20 truncate ${i === activeSegmentIndex ? "text-tc-accent" : ""}`}>
                    {seg.speaker === "NARRATOR" ? "Narrator" : seg.speaker}
                  </span>
                  <span className="truncate">{seg.text.slice(0, 120)}{seg.text.length > 120 ? "..." : ""}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {narrating && narrationSegments.length === 0 && (
        <div className="mb-3 flex items-center gap-3 px-3 py-2 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50">
          <Volume2 size={14} className="text-tc-accent animate-pulse" />
          <span className="text-xs text-tc-tertiary">Segmenting scene text...</span>
          <button
            onClick={() => {
              abortRef.current?.abort();
              abortRef.current = null;
              setNarrating(false);
            }}
            className="ml-auto p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            title="Cancel"
          >
            <Square size={12} />
          </button>
        </div>
      )}
      {narrationError && (
        <div className="mb-3 flex items-center gap-3 px-3 py-2 bg-tc-error-subtle rounded-lg border border-tc-error/50">
          <span className="text-xs text-tc-error">{narrationError}</span>
          <button
            onClick={() => setNarrationError(null)}
            className="ml-auto p-1 text-tc-error hover:text-tc-error rounded transition-colors"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {editing ? (
        <Editor
          content={editContent}
          onChange={handleChange}
          placeholder="Start writing..."
          images={images}
          workId={workId}
          onImageUploaded={onImageUploaded}
          spellcheckEnabled={spellcheckEnabled}
          customDictionary={customDictionary}
          comments={commentHighlights}
          activeCommentId={activeCommentId}
          onCommentClick={(id) => { if (id) onCommentClick(id); }}
          checkpoint={scene.checkpoint}
        />
      ) : (
        <>
          <div
            ref={proseRef}
            className="prose prose-invert prose-sm max-w-none text-tc-secondary leading-relaxed overflow-hidden break-words"
            onContextMenu={handleContextMenu}
            onDoubleClick={handleEdit}
          >
            {scene.content ? (
              <Markdown components={collapsedComponents}>{scene.content}</Markdown>
            ) : (
              <p className="text-tc-muted italic cursor-text" onClick={handleEdit}>
                Empty scene — click to write
              </p>
            )}
          </div>
          <p className="text-xs text-tc-muted mt-3">
            {scene.word_count.toLocaleString()} words
          </p>
        </>
      )}

      <audio
        ref={audioRef}
        onEnded={() => {
          if (audioRef.current?.src) {
            URL.revokeObjectURL(audioRef.current.src);
            audioRef.current.src = "";
          }
          const nextIdx = playingIndexRef.current + 1;
          if (nextIdx < audioQueueRef.current.length) {
            playingIndexRef.current = nextIdx;
            setActiveSegmentIndex(nextIdx);
            audioRef.current!.src = audioQueueRef.current[nextIdx];
            audioRef.current!.play();
          } else {
            playingIndexRef.current = -1;
            audioQueueRef.current = [];
            setNarrating(false);
            setNarrationSegments([]);
            setActiveSegmentIndex(-1);
          }
        }}
        onError={() => {
          playingIndexRef.current = -1;
          audioQueueRef.current = [];
          setNarrating(false);
          setNarrationSegments([]);
          setActiveSegmentIndex(-1);
          setNarrationError("Audio playback failed");
        }}
        className="hidden"
      />

      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed z-50 bg-tc-overlay border border-tc-subtle rounded-lg shadow-xl py-1 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {contextMenu.commentId ? (
            <>
              <button
                className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary hover:bg-tc-hover transition-colors w-full text-left"
                onMouseDown={(e) => {
                  e.preventDefault();
                  resolveMutation.mutate(contextMenu.commentId!);
                  setContextMenu(null);
                }}
              >
                <CheckCircle size={13} className="text-tc-success" />
                Resolve comment
              </button>
              <button
                className="flex items-center gap-2 px-3 py-2 text-sm text-tc-error hover:bg-tc-hover transition-colors w-full text-left"
                onMouseDown={(e) => {
                  e.preventDefault();
                  deleteCommentMutation.mutate(contextMenu.commentId!);
                  setContextMenu(null);
                }}
              >
                <Trash2 size={13} />
                Delete comment
              </button>
            </>
          ) : (
            <>
              <button
                className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary hover:bg-tc-hover transition-colors w-full text-left"
                onMouseDown={(e) => {
                  e.preventDefault();
                  startCommentFromSelection();
                }}
              >
                <MessageSquareQuote size={13} />
                Add comment
              </button>
              <button
                className="flex items-center gap-2 px-3 py-2 text-sm text-tc-secondary hover:bg-tc-hover transition-colors w-full text-left"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setContextMenu(null);
                  handleEdit();
                }}
              >
                <PenLine size={13} />
                Edit scene
              </button>
            </>
          )}
        </div>
      )}

    </div>
  );
}

export default function ChapterView() {
  const { id, chapterId } = useParams<{ id: string; chapterId: string }>();
  const queryClient = useQueryClient();
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const notesInitialized = useRef(false);
  const notesTimer = useRef<ReturnType<typeof setTimeout>>();
  const { openComments, startComment, activeCommentId } =
    useOutletContext<AppOutletContext>();

  const { data: chapter } = useQuery({
    queryKey: ["chapter", chapterId],
    queryFn: () => getChapter(chapterId!),
    enabled: !!chapterId,
  });

  const notesMutation = useMutation({
    mutationFn: (newNotes: string) => updateChapter(chapterId!, { notes: newNotes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapter", chapterId] });
    },
  });

  const toggleTitleMutation = useMutation({
    mutationFn: (show: boolean) => updateChapter(chapterId!, { show_title: show }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapter", chapterId] });
    },
  });

  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);

  const renameMutation = useMutation({
    mutationFn: (title: string) =>
      updateChapter(chapterId!, { title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapter", chapterId] });
      queryClient.invalidateQueries({ queryKey: ["chapters"] });
      setEditingTitle(false);
    },
  });

  const startRename = () => {
    setTitleDraft(chapter?.title || "");
    setEditingTitle(true);
    setTimeout(() => titleInputRef.current?.select(), 0);
  };

  const commitRename = () => {
    const trimmed = titleDraft.trim();
    if (trimmed !== (chapter?.title || "")) {
      renameMutation.mutate(trimmed);
    } else {
      setEditingTitle(false);
    }
  };

  if (chapter && !notesInitialized.current) {
    setNotes(chapter.notes);
    notesInitialized.current = true;
  }

  const handleNotesChange = useCallback(
    (value: string) => {
      setNotes(value);
      if (notesTimer.current) clearTimeout(notesTimer.current);
      notesTimer.current = setTimeout(() => {
        notesMutation.mutate(value);
      }, 1000);
    },
    [notesMutation]
  );

  const location = useLocation();

  const { data: scenes = [] } = useQuery({
    queryKey: ["scenes", { chapterId }],
    queryFn: () => listScenes(chapterId!),
    enabled: !!chapterId,
  });

  useEffect(() => {
    const hash = location.hash;
    if (!hash || scenes.length === 0) return;
    const el = document.getElementById(hash.slice(1));
    if (el) {
      requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, [location.hash, scenes]);

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

  const { data: codexEntries = [] } = useQuery({
    queryKey: ["codex", { workId: id }],
    queryFn: () => listCodexEntries({ workId: id }),
    enabled: !!id,
  });

  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });

  const customDictionary = codexEntries.map((e) => e.name);
  const globalSpellcheck = config.find((c) => c.key === "spellcheck_enabled")?.value !== "false";
  const pollyEnabled = config.find((c) => c.key === "polly_enabled")?.value === "true";

  const createSceneMutation = useMutation({
    mutationFn: createScene,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenes", { chapterId }] });
    },
  });

  const splitSceneMutation = useMutation({
    mutationFn: splitScene,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenes", { chapterId }] });
    },
  });

  const deleteSceneMutation = useMutation({
    mutationFn: deleteScene,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenes", { chapterId }] });
    },
  });

  const handleInsertScene = (atSortOrder: number) => {
    createSceneMutation.mutate({
      chapter_id: chapterId!,
      sort_order: atSortOrder,
    });
  };

  const handleCommentClick = useCallback(
    (commentId: string) => {
      openComments(commentId);
    },
    [openComments]
  );

  const handleStartComment = useCallback(
    (sceneId: string, anchorText: string, anchorFrom: number, anchorTo: number) => {
      startComment({ sceneId, anchorText, anchorFrom, anchorTo });
    },
    [startComment]
  );

  const { data: work } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const titlePageMutation = useMutation({
    mutationFn: (cfg: TitlePageConfig | null) => updateWork(id!, { title_page_config: cfg }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", id] });
    },
  });

  const isMatter = chapter
    ? MATTER_TITLES.has((chapter.title ?? "").toLowerCase().trim())
    : false;

  const isTitlePage = chapter
    ? (chapter.title ?? "").toLowerCase().trim() === "title page"
    : false;

  if (!chapter) return null;

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
          {!isMatter && chapter.number != null && (
            <p className="text-sm text-tc-muted mb-0.5">Chapter {chapter.number}</p>
          )}
          <div className="flex items-center gap-2">
            {editingTitle ? (
              <input
                ref={titleInputRef}
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setEditingTitle(false);
                }}
                onBlur={commitRename}
                placeholder={!isMatter && chapter.number != null ? `Chapter ${chapter.number}` : "Untitled"}
                className="text-2xl font-bold bg-transparent border-b-2 border-tc-accent outline-none text-tc-primary placeholder-gray-600 w-64"
              />
            ) : (
              <h1
                className="text-2xl font-bold cursor-pointer hover:text-tc-secondary transition-colors"
                onDoubleClick={startRename}
                title="Double-click to rename"
              >
                {chapter.title || (!isMatter && chapter.number != null ? `Chapter ${chapter.number}` : "Untitled")}
              </h1>
            )}
            <button
              onClick={() => toggleTitleMutation.mutate(!chapter.show_title)}
              className={`p-1 rounded transition-colors ${
                chapter.show_title
                  ? "text-tc-muted hover:text-tc-secondary"
                  : "text-tc-warning hover:text-tc-warning"
              }`}
              title={chapter.show_title ? "Title shown in reader — click to hide" : "Title hidden in reader — click to show"}
            >
              {chapter.show_title ? <Eye size={16} /> : <EyeOff size={16} />}
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const md = scenes.map((s) => s.content || "").filter(Boolean).join("\n\n---\n\n");
              navigator.clipboard.writeText(md);
            }}
            className="flex items-center gap-2 px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-tertiary hover:text-tc-secondary rounded-lg text-sm transition-colors"
            title="Copy chapter markdown"
          >
            <ClipboardCopy size={16} />
          </button>
          <Link
            to={`/work/${id}/read?chapter=${chapterId}`}
            className="flex items-center gap-2 px-3 py-2 bg-tc-overlay hover:bg-tc-hover text-tc-tertiary hover:text-tc-secondary rounded-lg text-sm transition-colors"
            title="Read from this chapter"
          >
            <BookOpenCheck size={16} />
          </Link>
          {!isMatter && (
            <button
              onClick={() => setShowNotes(!showNotes)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                showNotes ? "bg-tc-hover text-tc-secondary" : "bg-tc-overlay text-tc-tertiary hover:text-tc-secondary"
              }`}
            >
              <StickyNote size={16} />
              Notes
            </button>
          )}
        </div>
      </div>

      {showNotes && (
        <div className="mb-6 bg-tc-overlay/50 border border-tc-subtle rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <ChevronDown size={14} className="text-tc-muted" />
            <span className="text-sm font-medium text-tc-tertiary">Chapter Notes</span>
          </div>
          <textarea
            value={notes}
            onChange={(e) => handleNotesChange(e.target.value)}
            rows={6}
            placeholder="Chapter notes, outlines, reminders..."
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none resize-y font-mono"
          />
        </div>
      )}

      {isTitlePage && work ? (
        <div className="bg-tc-overlay/50 border border-tc-subtle/50 rounded-lg p-6">
          <TitlePageEditor
            work={work}
            config={work.title_page_config ?? null}
            onChange={(cfg) => titlePageMutation.mutate(cfg)}
          />
          {titlePageMutation.isPending && (
            <p className="text-xs text-tc-muted mt-3">Saving...</p>
          )}
        </div>
      ) : (
        <>
          <div className="grid gap-0">
            {scenes.map((scene, index) => (
              <div key={scene.id}>
                {!isMatter && index === 0 && scenes.length > 1 && (
                  <InsertSceneButton
                    onClick={() => handleInsertScene(scene.sort_order)}
                    disabled={createSceneMutation.isPending}
                  />
                )}
                <SceneCard
                  scene={scene}
                  index={index}
                  workId={id!}
                  chapterId={chapterId!}
                  onDelete={() => deleteSceneMutation.mutate(scene.id)}
                  onSplit={() => splitSceneMutation.mutate(scene.id)}
                  label={isMatter ? "Content" : undefined}
                  hideMenu={isMatter}
                  images={editorImages}
                  onImageUploaded={() => queryClient.invalidateQueries({ queryKey: ["images", id] })}
                  spellcheckEnabled={globalSpellcheck}
                  customDictionary={customDictionary}
                  activeCommentId={activeCommentId}
                  onCommentClick={handleCommentClick}
                  onStartComment={handleStartComment}
                  pollyEnabled={pollyEnabled}
                />
                {!isMatter && (
                  <InsertSceneButton
                    onClick={() => handleInsertScene(scene.sort_order + 1)}
                    disabled={createSceneMutation.isPending}
                  />
                )}
              </div>
            ))}
          </div>

          {scenes.length === 0 && !isMatter && (
            <div className="text-center py-12 text-tc-muted">
              <PenLine size={40} className="mx-auto mb-3 opacity-50" />
              <p className="mb-4">No scenes yet. Add one to start writing.</p>
              <button
                onClick={() => handleInsertScene(0)}
                disabled={createSceneMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus size={16} />
                Add Scene
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
