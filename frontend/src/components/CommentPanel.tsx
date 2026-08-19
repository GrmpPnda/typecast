import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listComments,
  updateComment,
  deleteComment,
  resolveAllComments,
} from "@/api/comments";
import {
  CheckCircle,
  Trash2,
  CheckCheck,
  MessageSquare,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useState, useEffect } from "react";
import type { Comment } from "@/types";
import type { CommentHighlight } from "@/extensions/comments";

interface CommentPanelProps {
  sceneId: string;
  activeCommentId: string | null;
  onActiveChange: (id: string | null) => void;
  onCommentsLoaded?: (highlights: CommentHighlight[]) => void;
}

export default function CommentPanel({
  sceneId,
  activeCommentId,
  onActiveChange,
  onCommentsLoaded,
}: CommentPanelProps) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [showResolved, setShowResolved] = useState(false);

  const { data: comments = [] } = useQuery({
    queryKey: ["comments", sceneId],
    queryFn: () => listComments(sceneId),
  });

  useEffect(() => {
    if (!onCommentsLoaded) return;
    const highlights: CommentHighlight[] = comments.map((c) => ({
      id: c.id,
      anchorText: c.anchor_text,
      content: c.content,
      resolved: c.resolved,
    }));
    onCommentsLoaded(highlights);
  }, [comments, onCommentsLoaded]);

  const resolveMutation = useMutation({
    mutationFn: (id: string) => updateComment(id, { resolved: true }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["comments", sceneId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteComment,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["comments", sceneId] }),
  });

  const resolveAllMutation = useMutation({
    mutationFn: () => resolveAllComments(sceneId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["comments", sceneId] }),
  });

  const unresolved = comments.filter((c) => !c.resolved);
  const resolved = comments.filter((c) => c.resolved);

  if (comments.length === 0) return null;

  return (
    <div className="mt-3 border-t border-tc-subtle/50 pt-3 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-tc-muted hover:text-tc-secondary transition-colors w-full"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <MessageSquare size={12} />
        <span>
          {unresolved.length} comment{unresolved.length !== 1 ? "s" : ""}
          {resolved.length > 0 && (
            <span className="text-tc-muted"> ({resolved.length} resolved)</span>
          )}
        </span>
        {expanded && unresolved.length > 1 && (
          <span
            onClick={(e) => {
              e.stopPropagation();
              resolveAllMutation.mutate();
            }}
            className="ml-auto flex items-center gap-1 text-tc-muted hover:text-tc-success transition-colors"
          >
            <CheckCheck size={12} />
            Resolve all
          </span>
        )}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {unresolved.map((comment) => (
            <CommentCard
              key={comment.id}
              comment={comment}
              isActive={comment.id === activeCommentId}
              onClick={() =>
                onActiveChange(
                  comment.id === activeCommentId ? null : comment.id
                )
              }
              onResolve={() => resolveMutation.mutate(comment.id)}
              onDelete={() => deleteMutation.mutate(comment.id)}
            />
          ))}

          {resolved.length > 0 && (
            <div>
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
                      onResolve={() => {}}
                      onDelete={() => deleteMutation.mutate(comment.id)}
                      resolved
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CommentCard({
  comment,
  isActive,
  onClick,
  onResolve,
  onDelete,
  resolved,
}: {
  comment: Comment;
  isActive: boolean;
  onClick: () => void;
  onResolve: () => void;
  onDelete: () => void;
  resolved?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={`px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors overflow-hidden ${
        isActive
          ? "bg-tc-secondary-subtle border border-tc-secondary/40"
          : "bg-tc-overlay/60 border border-tc-subtle/30 hover:bg-tc-overlay"
      }`}
    >
      {comment.anchor_text && (
        <p className="text-tc-secondary-accent/70 font-mono text-[10px] mb-1 break-words whitespace-pre-wrap">
          &ldquo;{comment.anchor_text}&rdquo;
        </p>
      )}
      <p className="text-tc-secondary leading-relaxed break-words whitespace-pre-wrap">
        {comment.content}
      </p>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-tc-muted">
          {comment.author === "ai" ? "AI Reviewer" : "You"}
        </span>
        <div className="flex items-center gap-1">
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
}
