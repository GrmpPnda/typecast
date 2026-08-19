import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node as PmNode } from "@tiptap/pm/model";

export interface CommentHighlight {
  id: string;
  anchorText: string;
  content: string;
  resolved: boolean;
}

const commentKey = new PluginKey("comments");

function stripMd(s: string): string {
  return s.replace(/(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)/g, "");
}

function findAnchorInDoc(
  doc: PmNode,
  anchorText: string
): { from: number; to: number } | null {
  if (!anchorText) return null;

  const stripped = stripMd(anchorText);
  let result: { from: number; to: number } | null = null;

  doc.descendants((node, pos) => {
    if (result) return false;
    if (!node.isTextblock) return;

    const text = node.textContent;
    for (const needle of [anchorText, stripped]) {
      const idx = text.indexOf(needle);
      if (idx === -1) continue;
      result = {
        from: pos + 1 + idx,
        to: pos + 1 + idx + needle.length,
      };
      return false;
    }
  });

  return result;
}

function buildDecorations(
  doc: PmNode,
  comments: CommentHighlight[],
  activeId: string | null
): DecorationSet {
  const decorations: Decoration[] = [];

  for (const comment of comments) {
    if (comment.resolved) continue;

    const pos = findAnchorInDoc(doc, comment.anchorText);
    if (!pos) continue;

    const isActive = comment.id === activeId;
    decorations.push(
      Decoration.inline(pos.from, pos.to, {
        class: isActive
          ? "comment-highlight comment-active"
          : "comment-highlight",
        "data-comment-id": comment.id,
      })
    );
  }

  return DecorationSet.create(doc, decorations);
}

export interface CommentsOptions {
  comments: CommentHighlight[];
  activeCommentId: string | null;
  onCommentClick?: (commentId: string) => void;
}

export const Comments = Extension.create<CommentsOptions>({
  name: "comments",

  addOptions() {
    return {
      comments: [],
      activeCommentId: null,
      onCommentClick: undefined,
    };
  },

  addProseMirrorPlugins() {
    const extensionThis = this;

    return [
      new Plugin({
        key: commentKey,
        state: {
          init(_, { doc }) {
            return buildDecorations(
              doc,
              extensionThis.options.comments,
              extensionThis.options.activeCommentId
            );
          },
          apply(tr, oldSet) {
            const meta = tr.getMeta(commentKey) || tr.getMeta("comments");
            if (meta?.decorations) return meta.decorations;
            if (meta?.rebuild || tr.docChanged) {
              return buildDecorations(
                tr.doc,
                extensionThis.options.comments,
                extensionThis.options.activeCommentId
              );
            }
            return oldSet.map(tr.mapping, tr.doc);
          },
        },
        props: {
          decorations(state) {
            return this.getState(state);
          },
          handleClick(_view, _pos, event) {
            const target = event.target as HTMLElement;
            const highlight = target.closest?.("[data-comment-id]");
            if (!highlight) return false;

            const commentId = highlight.getAttribute("data-comment-id");
            if (commentId && extensionThis.options.onCommentClick) {
              extensionThis.options.onCommentClick(commentId);
            }
            return false;
          },
        },
      }),
    ];
  },
});
