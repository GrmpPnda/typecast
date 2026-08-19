import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { EditorView } from "@tiptap/pm/view";
import type { Node as PmNode } from "@tiptap/pm/model";
import Typo from "typo-js";

const WORD_RE = /[a-zA-Z'\u2019\u00C0-\u024F]+/g;
const spellcheckKey = new PluginKey("spellcheck");

let typoInstance: Typo | null = null;
let typoLoading: Promise<Typo> | null = null;

function normalizeApostrophes(word: string): string {
  return word.replace(/[\u2019\u2018\u201B\u0060\u00B4]/g, "'");
}

async function getTypo(): Promise<Typo> {
  if (typoInstance) return typoInstance;
  if (typoLoading) return typoLoading;
  typoLoading = (async () => {
    const [affData, dicData] = await Promise.all([
      fetch("/dictionaries/en_US.aff").then((r) => r.text()),
      fetch("/dictionaries/en_US.dic").then((r) => r.text()),
    ]);
    typoInstance = new Typo("en_US", affData, dicData);
    return typoInstance;
  })();
  return typoLoading;
}

function addCustomWords(typo: Typo, words: string[]) {
  for (const raw of words) {
    for (const token of raw.split(/[\s-]+/)) {
      if (token.length < 2) continue;
      typo.dictionaryTable[token] = [[]];
      typo.dictionaryTable[token.toLowerCase()] = [[]];
    }
  }
}

let userDictionary: Set<string> = new Set();

function addToUserDictionary(typo: Typo, word: string) {
  const normalized = normalizeApostrophes(word);
  userDictionary.add(normalized.toLowerCase());
  typo.dictionaryTable[normalized] = [[]];
  typo.dictionaryTable[normalized.toLowerCase()] = [[]];
}

function isWordCorrect(typo: Typo, word: string): boolean {
  const normalized = normalizeApostrophes(word);
  if (userDictionary.has(normalized.toLowerCase())) return true;
  return typo.check(normalized) || typo.check(normalized.toLowerCase());
}

function buildDecorations(doc: PmNode, typo: Typo): DecorationSet {
  const decorations: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    let match: RegExpExecArray | null;
    WORD_RE.lastIndex = 0;
    while ((match = WORD_RE.exec(node.text)) !== null) {
      const word = match[0];
      if (word.length < 2) continue;
      if (/^[A-Z]+$/.test(word)) continue;
      if (/^\d+$/.test(word)) continue;
      if (!isWordCorrect(typo, word)) {
        const from = pos + match.index;
        const to = from + word.length;
        decorations.push(
          Decoration.inline(from, to, { class: "spellcheck-error" })
        );
      }
    }
  });
  return DecorationSet.create(doc, decorations);
}

let activeMenu: HTMLElement | null = null;

function removeMenu() {
  if (activeMenu) {
    activeMenu.remove();
    activeMenu = null;
  }
}

function showSpellMenu(
  view: EditorView,
  typo: Typo,
  word: string,
  from: number,
  to: number,
  x: number,
  y: number,
  forceRecheck: () => void,
) {
  removeMenu();

  const normalized = normalizeApostrophes(word);
  const suggestions = typo.suggest(normalized, 5);

  const menu = document.createElement("div");
  menu.className = "spellcheck-menu";
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;

  if (suggestions.length > 0) {
    for (const suggestion of suggestions) {
      const item = document.createElement("button");
      item.className = "spellcheck-menu-item spellcheck-suggestion";
      item.textContent = suggestion;
      item.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const tr = view.state.tr.replaceWith(
          from,
          to,
          view.state.schema.text(suggestion),
        );
        view.dispatch(tr);
        removeMenu();
      });
      menu.appendChild(item);
    }
  } else {
    const noSugg = document.createElement("div");
    noSugg.className = "spellcheck-menu-item spellcheck-no-suggestions";
    noSugg.textContent = "No suggestions";
    menu.appendChild(noSugg);
  }

  const divider = document.createElement("div");
  divider.className = "spellcheck-menu-divider";
  menu.appendChild(divider);

  const addBtn = document.createElement("button");
  addBtn.className = "spellcheck-menu-item spellcheck-add-word";
  addBtn.textContent = `Add "${word}" to dictionary`;
  addBtn.addEventListener("mousedown", (e) => {
    e.preventDefault();
    addToUserDictionary(typo, word);
    removeMenu();
    forceRecheck();
  });
  menu.appendChild(addBtn);

  document.body.appendChild(menu);
  activeMenu = menu;

  const dismiss = (e: MouseEvent) => {
    if (!menu.contains(e.target as Node)) {
      removeMenu();
      document.removeEventListener("mousedown", dismiss);
    }
  };
  setTimeout(() => document.addEventListener("mousedown", dismiss), 0);
}

function findMisspelledWordAt(
  view: EditorView,
  pos: number,
): { word: string; from: number; to: number } | null {
  const decoSet = spellcheckKey.getState(view.state);
  if (!decoSet) return null;

  const resolved = view.state.doc.resolve(pos);
  const node = resolved.parent;
  if (!node.isTextblock) return null;

  const textOffset = pos - resolved.start();
  let offset = 0;
  for (let i = 0; i < node.childCount; i++) {
    const child = node.child(i);
    if (!child.isText || !child.text) {
      offset += child.nodeSize;
      continue;
    }
    const childEnd = offset + child.text.length;
    if (textOffset >= offset && textOffset <= childEnd) {
      const localOffset = textOffset - offset;
      WORD_RE.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = WORD_RE.exec(child.text)) !== null) {
        if (localOffset >= match.index && localOffset <= match.index + match[0].length) {
          const from = resolved.start() + offset + match.index;
          const to = from + match[0].length;
          const decosAt = decoSet.find(from, to);
          if (decosAt.length > 0) {
            return { word: match[0], from, to };
          }
          return null;
        }
      }
    }
    offset += child.text.length;
  }
  return null;
}

export interface SpellcheckOptions {
  enabled: boolean;
  customWords: string[];
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    spellcheck: {
      toggleSpellcheck: () => ReturnType;
    };
  }
}

export const Spellcheck = Extension.create<SpellcheckOptions>({
  name: "spellcheck",

  addOptions() {
    return {
      enabled: true,
      customWords: [],
    };
  },

  addStorage() {
    return {
      enabled: this.options.enabled,
      typoReady: false,
    };
  },

  addCommands() {
    return {
      toggleSpellcheck:
        () =>
        ({ editor }) => {
          editor.storage.spellcheck.enabled =
            !editor.storage.spellcheck.enabled;
          // Force re-decoration by dispatching an empty transaction
          const { state } = editor.view;
          const tr = state.tr.setMeta(spellcheckKey, { forceUpdate: true });
          editor.view.dispatch(tr);
          return true;
        },
    };
  },

  addProseMirrorPlugins() {
    const extensionThis = this;
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    let currentCustomWords: string[] = [];
    let cachedTypo: Typo | null = null;
    let latestView: EditorView | null = null;

    function forceRecheck() {
      if (!latestView) return;
      const { state } = latestView;
      const tr = state.tr.setMeta(spellcheckKey, { forceUpdate: true });
      latestView.dispatch(tr);
    }

    return [
      new Plugin({
        key: spellcheckKey,
        state: {
          init() {
            return DecorationSet.empty;
          },
          apply(tr, oldSet) {
            const meta = tr.getMeta(spellcheckKey);
            if (meta?.decorations) {
              return meta.decorations;
            }
            if (meta?.forceUpdate) {
              return DecorationSet.empty;
            }
            if (tr.docChanged) {
              return DecorationSet.empty;
            }
            return oldSet.map(tr.mapping, tr.doc);
          },
        },
        view(editorView: EditorView) {
          latestView = editorView;

          function scheduleCheck() {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => runCheck(editorView), 300);
          }

          async function runCheck(view: EditorView) {
            if (!extensionThis.storage.enabled) {
              const { state } = view;
              const tr = state.tr.setMeta(spellcheckKey, {
                decorations: DecorationSet.empty,
              });
              view.dispatch(tr);
              return;
            }

            const typo = await getTypo();
            cachedTypo = typo;

            const newWords = extensionThis.options.customWords;
            if (newWords !== currentCustomWords) {
              addCustomWords(typo, newWords);
              currentCustomWords = newWords;
            }

            const decorations = buildDecorations(view.state.doc, typo);
            const { state } = view;
            const tr = state.tr.setMeta(spellcheckKey, { decorations });
            view.dispatch(tr);
          }

          scheduleCheck();

          return {
            update() {
              latestView = editorView;
              scheduleCheck();
            },
            destroy() {
              if (debounceTimer) clearTimeout(debounceTimer);
              removeMenu();
              latestView = null;
            },
          };
        },
        props: {
          decorations(state) {
            return this.getState(state);
          },
          handleDOMEvents: {
            contextmenu(view, event) {
              if (!cachedTypo || !extensionThis.storage.enabled) return false;

              const pos = view.posAtCoords({
                left: event.clientX,
                top: event.clientY,
              });
              if (!pos) return false;

              const found = findMisspelledWordAt(view, pos.pos);
              if (!found) return false;

              event.preventDefault();
              showSpellMenu(
                view,
                cachedTypo,
                found.word,
                found.from,
                found.to,
                event.clientX,
                event.clientY,
                forceRecheck,
              );
              return true;
            },
          },
        },
      }),
    ];
  },
});
