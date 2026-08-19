import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node as PmNode } from "@tiptap/pm/model";
import { diffRanges } from "@/diff";

const aiDiffKey = new PluginKey("aiDiff");

function buildDecorations(doc: PmNode, checkpoint: string | null): DecorationSet {
  if (!checkpoint) return DecorationSet.empty;

  const fullText = doc.textContent;
  const ranges = diffRanges(checkpoint, fullText);
  if (ranges.length === 0) return DecorationSet.empty;

  const charToPos = buildCharToPos(doc);
  const decorations: Decoration[] = [];

  for (const range of ranges) {
    const from = charToPos(range.from);
    const to = charToPos(range.to);
    if (from !== null && to !== null && to > from) {
      decorations.push(
        Decoration.inline(from, to, { class: "ai-diff-highlight" })
      );
    }
  }

  return DecorationSet.create(doc, decorations);
}

function buildCharToPos(doc: PmNode): (charIdx: number) => number | null {
  const mapping: { charStart: number; posStart: number; length: number }[] = [];
  let charOffset = 0;

  doc.descendants((node, pos) => {
    if (node.isText && node.text) {
      mapping.push({ charStart: charOffset, posStart: pos, length: node.text.length });
      charOffset += node.text.length;
    }
  });

  return (charIdx: number) => {
    for (const seg of mapping) {
      if (charIdx >= seg.charStart && charIdx <= seg.charStart + seg.length) {
        return seg.posStart + (charIdx - seg.charStart);
      }
    }
    return null;
  };
}

export interface AiDiffOptions {
  checkpoint: string | null;
}

export const AiDiff = Extension.create<AiDiffOptions>({
  name: "aiDiff",

  addOptions() {
    return { checkpoint: null };
  },

  addProseMirrorPlugins() {
    const ext = this;
    return [
      new Plugin({
        key: aiDiffKey,
        state: {
          init(_, { doc }) {
            return buildDecorations(doc, ext.options.checkpoint);
          },
          apply(tr, oldSet) {
            const meta = tr.getMeta(aiDiffKey) || tr.getMeta("aiDiff");
            if (meta?.rebuild || tr.docChanged) {
              return buildDecorations(tr.doc, ext.options.checkpoint);
            }
            return oldSet.map(tr.mapping, tr.doc);
          },
        },
        props: {
          decorations(state) {
            return this.getState(state);
          },
        },
      }),
    ];
  },
});
