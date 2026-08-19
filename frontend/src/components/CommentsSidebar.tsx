import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listChapterComments,
  createComment,
  updateComment,
  deleteComment,
  resolveAllComments,
  applyComment,
  revertScene,
  clearCheckpoint,
  rewriteScene,
} from "@/api/comments";
import { listScenes } from "@/api/scenes";
import {
  MessageSquare,
  X,
  CheckCircle,
  Trash2,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Undo2,
  Save,
} from "lucide-react";
import { useState, useEffect, useRef } from "react";
import type { Comment, Scene } from "@/types";
import type { PendingComment } from "@/App";

interface CommentsSidebarProps {
  chapterId: string;
  activeCommentId: string | null;
  onActiveChange: (id: string | null) => void;
  pendingComment: PendingComment | null;
  onPendingClear: () => void;
  onClose: () => void;
}

export default function CommentsSidebar({
  chapterId,
  activeCommentId,
  onActiveChange,
  pendingComment,
  onPendingClear,
  onClose,
}: CommentsSidebarProps) {
  const queryClient = useQueryClient();
  const [showResolved, setShowResolved] = useState(false);
  const [commentText, setCommentText] = useState("");
  const activeRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: comments = [] } = useQuery({
    queryKey: ["chapter-comments", chapterId],
    queryFn: () => listChapterComments(chapterId),
    enabled: !!chapterId,
  });

  const { data: scenes = [] } = useQuery({
    queryKey: ["scenes", { chapterId }],
    queryFn: () => listScenes(chapterId),
    enabled: !!chapterId,
  });

  const sceneMap = new Map<string, Scene>();
  for (const s of scenes) sceneMap.set(s.id, s);

  useEffect(() => {
    if (activeCommentId && activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeCommentId]);

  const resolveMutation = useMutation({
    mutationFn: (id: string) => updateComment(id, { resolved: true }),
    onSuccess: () => invalidateComments(),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteComment,
    onSuccess: () => invalidateComments(),
  });

  const resolveAllMutation = useMutation({
    mutationFn: (sceneId: string) => resolveAllComments(sceneId),
    onSuccess: () => invalidateComments(),
  });

  const addCommentMutation = useMutation({
    mutationFn: (data: { sceneId: string; anchorText: string; anchorFrom: number; anchorTo: number; content: string }) =>
      createComment(data.sceneId, {
        anchor_text: data.anchorText,
        anchor_from: data.anchorFrom,
        anchor_to: data.anchorTo,
        content: data.content,
        author: "user",
      }),
    onSuccess: () => {
      invalidateComments();
      setCommentText("");
      onPendingClear();
    },
  });

  useEffect(() => {
    if (pendingComment && textareaRef.current) {
      setCommentText("");
      textareaRef.current.focus();
    }
  }, [pendingComment]);

  const [applyError, setApplyError] = useState<string | null>(null);

  const applyMutation = useMutation({
    mutationFn: applyComment,
    onSuccess: () => {
      setApplyError(null);
      invalidateAll();
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to apply suggestion";
      setApplyError(msg);
      setTimeout(() => setApplyError(null), 4000);
    },
  });

  const revertMutation = useMutation({
    mutationFn: revertScene,
    onSuccess: () => {
      invalidateAll();
    },
  });

  const clearCheckpointMutation = useMutation({
    mutationFn: clearCheckpoint,
    onSuccess: () => {
      invalidateAll();
    },
  });

  const rewriteMutation = useMutation({
    mutationFn: rewriteScene,
    onSuccess: () => {
      invalidateAll();
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Rewrite failed";
      setApplyError(msg);
      setTimeout(() => setApplyError(null), 4000);
    },
  });

  function invalidateAll() {
    invalidateComments();
    queryClient.invalidateQueries({ queryKey: ["scenes", { chapterId }] });
  }

  function invalidateComments() {
    queryClient.invalidateQueries({ queryKey: ["chapter-comments", chapterId] });
    for (const s of scenes) {
      queryClient.invalidateQueries({ queryKey: ["comments", s.id] });
    }
  }

  function scrollToHighlight(commentId: string) {
    onActiveChange(commentId);
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-comment-id="${commentId}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  const scenesWithCheckpoints = scenes.filter((s) => s.checkpoint != null);

  const unresolved = comments.filter((c) => !c.resolved);
  const resolved = comments.filter((c) => c.resolved);

  const groupedUnresolved = groupByScene(unresolved, scenes);

  return (
    <div className="h-full flex flex-col bg-tc-page border-l border-tc-default">
      <div className="flex items-center justify-between px-4 py-3 border-b border-tc-default">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-tc-secondary-accent" />
          <h2 className="text-sm font-semibold text-tc-secondary">Comments</h2>
          {unresolved.length > 0 && (
            <span className="px-1.5 py-0.5 text-[10px] font-medium bg-tc-secondary-subtle text-tc-secondary-accent rounded-full">
              {unresolved.length}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1 text-tc-muted hover:text-tc-secondary transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {applyError && (
          <div className="bg-tc-error-subtle border border-tc-error/40 rounded-lg px-3 py-2 text-xs text-tc-error">
            {applyError}
          </div>
        )}
        {pendingComment && (
          <div className="bg-tc-overlay/80 border border-tc-secondary/30 rounded-lg p-3">
            <p className="text-[10px] text-tc-secondary-accent/70 font-mono mb-2 break-words leading-tight">
              &ldquo;{pendingComment.anchorText}&rdquo;
            </p>
            <textarea
              ref={textareaRef}
              autoFocus
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Add your comment..."
              rows={2}
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm text-tc-secondary placeholder-gray-500 focus:border-tc-accent focus:outline-none resize-none"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && commentText.trim()) {
                  addCommentMutation.mutate({
                    sceneId: pendingComment.sceneId,
                    anchorText: pendingComment.anchorText,
                    anchorFrom: pendingComment.anchorFrom,
                    anchorTo: pendingComment.anchorTo,
                    content: commentText.trim(),
                  });
                }
                if (e.key === "Escape") {
                  onPendingClear();
                  setCommentText("");
                }
              }}
            />
            <div className="flex items-center justify-between mt-2">
              <span className="text-[10px] text-tc-muted">
                {"\u2318"}+Enter to submit, Esc to cancel
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { onPendingClear(); setCommentText(""); }}
                  className="px-2 py-1 text-xs text-tc-muted hover:text-tc-secondary transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    if (!commentText.trim()) return;
                    addCommentMutation.mutate({
                      sceneId: pendingComment.sceneId,
                      anchorText: pendingComment.anchorText,
                      anchorFrom: pendingComment.anchorFrom,
                      anchorTo: pendingComment.anchorTo,
                      content: commentText.trim(),
                    });
                  }}
                  disabled={!commentText.trim() || addCommentMutation.isPending}
                  className="px-3 py-1 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 text-tc-primary text-xs rounded font-medium transition-colors"
                >
                  {addCommentMutation.isPending ? "Adding..." : "Add Comment"}
                </button>
              </div>
            </div>
          </div>
        )}

        {scenesWithCheckpoints.length > 0 && (
          <div className="space-y-2">
            {scenesWithCheckpoints.map((s) => (
              <div key={s.id} className="bg-tc-accent-subtle border border-tc-accent/30 rounded-lg px-3 py-2 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-tc-accent">
                  <Save size={12} />
                  <span>{s.title || `Scene ${scenes.indexOf(s) + 1}`} — checkpointed</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => revertMutation.mutate(s.id)}
                    className="flex items-center gap-1 px-2 py-1 text-[10px] text-tc-secondary-accent hover:text-tc-secondary-accent bg-tc-secondary-subtle hover:bg-tc-secondary-subtle rounded transition-colors"
                    title="Revert to checkpoint"
                  >
                    <Undo2 size={10} /> Revert
                  </button>
                  <button
                    onClick={() => clearCheckpointMutation.mutate(s.id)}
                    className="flex items-center gap-1 px-2 py-1 text-[10px] text-tc-success hover:text-tc-success bg-tc-success-subtle hover:bg-tc-success-subtle rounded transition-colors"
                    title="Accept changes and clear checkpoint"
                  >
                    <CheckCircle size={10} /> Accept
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {comments.length === 0 && !pendingComment ? (
          <div className="text-center py-12 text-tc-muted text-sm">
            <MessageSquare size={32} className="mx-auto mb-3 opacity-30" />
            <p>No comments yet</p>
            <p className="text-xs mt-1 text-tc-muted">
              Select text and right-click to add a comment,
              or ask the AI reviewer.
            </p>
          </div>
        ) : (
          <>
            {groupedUnresolved.map(({ scene, comments: sceneComments }) => (
              <div key={scene.id}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-medium text-tc-muted uppercase tracking-wider">
                    {scene.title || `Scene ${scenes.indexOf(scene) + 1}`}
                  </span>
                  <div className="flex items-center gap-2">
                    {sceneComments.length > 1 && (
                      <button
                        onClick={() => rewriteMutation.mutate(scene.id)}
                        disabled={rewriteMutation.isPending}
                        className="flex items-center gap-1 text-[10px] text-tc-accent hover:text-tc-accent bg-tc-accent-subtle hover:bg-tc-accent-subtle px-1.5 py-0.5 rounded transition-colors disabled:opacity-50"
                      >
                        <Sparkles size={10} />
                        {rewriteMutation.isPending ? "Rewriting..." : "Rewrite"}
                      </button>
                    )}
                    {sceneComments.length > 1 && (
                      <button
                        onClick={() => resolveAllMutation.mutate(scene.id)}
                        className="flex items-center gap-1 text-[10px] text-tc-muted hover:text-tc-success transition-colors"
                      >
                        <CheckCheck size={10} />
                        Resolve all
                      </button>
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  {sceneComments.map((comment) => (
                    <CommentCard
                      key={comment.id}
                      ref={comment.id === activeCommentId ? activeRef : undefined}
                      comment={comment}
                      isActive={comment.id === activeCommentId}
                      onClick={() =>
                        onActiveChange(
                          comment.id === activeCommentId ? null : comment.id
                        )
                      }
                      onDoubleClick={() => scrollToHighlight(comment.id)}
                      onResolve={() => resolveMutation.mutate(comment.id)}
                      onDelete={() => deleteMutation.mutate(comment.id)}
                      onApply={comment.suggestion ? () => applyMutation.mutate(comment.id) : undefined}
                    />
                  ))}
                </div>
              </div>
            ))}

            {resolved.length > 0 && (
              <div className="border-t border-tc-default pt-3">
                <button
                  onClick={() => setShowResolved(!showResolved)}
                  className="flex items-center gap-1 text-xs text-tc-muted hover:text-tc-tertiary transition-colors"
                >
                  {showResolved ? (
                    <ChevronDown size={12} />
                  ) : (
                    <ChevronRight size={12} />
                  )}
                  {resolved.length} resolved
                </button>
                {showResolved && (
                  <div className="space-y-2 mt-2 opacity-50">
                    {resolved.map((comment) => (
                      <CommentCard
                        key={comment.id}
                        comment={comment}
                        isActive={false}
                        onClick={() => {}}
                        onDoubleClick={() => scrollToHighlight(comment.id)}
                        onResolve={() => {}}
                        onDelete={() => deleteMutation.mutate(comment.id)}
                        resolved
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function groupByScene(
  comments: Comment[],
  scenes: Scene[]
): { scene: Scene; comments: Comment[] }[] {
  const groups: { scene: Scene; comments: Comment[] }[] = [];
  const sceneMap = new Map<string, Comment[]>();

  for (const c of comments) {
    const existing = sceneMap.get(c.scene_id);
    if (existing) {
      existing.push(c);
    } else {
      sceneMap.set(c.scene_id, [c]);
    }
  }

  for (const scene of scenes) {
    const sceneComments = sceneMap.get(scene.id);
    if (sceneComments && sceneComments.length > 0) {
      groups.push({ scene, comments: sceneComments });
    }
  }

  return groups;
}

import { forwardRef } from "react";

const CommentCard = forwardRef<
  HTMLDivElement,
  {
    comment: Comment;
    isActive: boolean;
    onClick: () => void;
    onDoubleClick: () => void;
    onResolve: () => void;
    onDelete: () => void;
    onApply?: () => void;
    resolved?: boolean;
  }
>(function CommentCard(
  { comment, isActive, onClick, onDoubleClick, onResolve, onDelete, onApply, resolved },
  ref
) {
  return (
    <div
      ref={ref}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
        isActive
          ? "bg-tc-secondary-subtle border border-tc-secondary/40"
          : "bg-tc-overlay/60 border border-tc-subtle/30 hover:bg-tc-overlay"
      }`}
    >
      {comment.anchor_text && (
        <p className="text-tc-secondary-accent/70 font-mono text-[10px] mb-1 break-words whitespace-pre-wrap leading-tight">
          &ldquo;{comment.anchor_text}&rdquo;
        </p>
      )}
      <p className="text-tc-secondary leading-relaxed break-words whitespace-pre-wrap">
        {comment.content}
      </p>
      {comment.suggestion && !resolved && (
        <div className="mt-1.5 px-2 py-1.5 bg-tc-success-subtle border border-tc-success/30 rounded text-[10px]">
          <span className="text-green-500 font-medium">Suggestion: </span>
          <span className="text-tc-success/80 break-words whitespace-pre-wrap">{comment.suggestion}</span>
        </div>
      )}
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-tc-muted">
          {comment.author === "ai" ? "AI Reviewer" : "You"}
        </span>
        <div className="flex items-center gap-1">
          {onApply && !resolved && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onApply();
              }}
              className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-tc-accent hover:text-tc-accent bg-tc-accent-subtle hover:bg-tc-accent-subtle rounded transition-colors"
              title="Apply suggestion"
            >
              <Sparkles size={10} /> Apply
            </button>
          )}
          {!resolved && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onResolve();
              }}
              className="p-1 text-tc-muted hover:text-tc-success transition-colors"
              title="Resolve"
            >
              <CheckCircle size={12} />
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-1 text-tc-muted hover:text-tc-error transition-colors"
            title="Delete"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </div>
  );
});
