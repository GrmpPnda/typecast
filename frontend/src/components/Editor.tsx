import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import {
  Bold,
  Italic,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Code as CodeIcon,
  CodeXml,
  Minus,
  Undo,
  Redo,
  Code,
  Eye,
  ImageIcon,
  SpellCheck,
} from "lucide-react";
import { useEffect, useCallback, useRef, useState } from "react";
import { marked } from "marked";
import TurndownService from "turndown";
import { uploadImage } from "@/api/images";
import ImagePickerModal from "./ImagePickerModal";
import { Spellcheck } from "@/extensions/spellcheck";
import { Comments, CommentHighlight } from "@/extensions/comments";
import { AiDiff } from "@/extensions/ai-diff";

const turndown = new TurndownService({
  headingStyle: "atx",
  emDelimiter: "*",
  bulletListMarker: "-",
});

function mdToHtml(md: string): string {
  return marked.parse(md, { async: false }) as string;
}

function htmlToMd(html: string): string {
  return turndown.turndown(html);
}

export interface EditorImage {
  id: string;
  url: string;
  alt_text: string;
  original_name: string;
}

interface EditorProps {
  content: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  images?: EditorImage[];
  workId?: string;
  onImageUploaded?: () => void;
  spellcheckEnabled?: boolean;
  customDictionary?: string[];
  comments?: CommentHighlight[];
  activeCommentId?: string | null;
  onCommentClick?: (commentId: string) => void;
  checkpoint?: string | null;
}

export default function Editor({
  content,
  onChange,
  placeholder = "Start writing...",
  images,
  workId,
  onImageUploaded,
  spellcheckEnabled = true,
  customDictionary = [],
  comments: commentHighlights = [],
  activeCommentId = null,
  onCommentClick,
  checkpoint = null,
}: EditorProps) {
  const [rawMode, setRawMode] = useState(false);
  const [rawContent, setRawContent] = useState(content);
  const [showImagePicker, setShowImagePicker] = useState(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const suppressUpdate = useRef(false);
  const editorRef = useRef<ReturnType<typeof useEditor>>(null);

  const handleUploadAndInsert = useCallback(
    async (file: File) => {
      if (!workId) return;
      const img = await uploadImage(workId, file);
      onImageUploaded?.();
      editorRef.current
        ?.chain()
        .focus()
        .setImage({ src: img.url, alt: img.alt_text || img.original_name })
        .run();
    },
    [workId, onImageUploaded]
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      Image.configure({ inline: false, allowBase64: false }),
      Placeholder.configure({ placeholder }),
      Spellcheck.configure({
        enabled: spellcheckEnabled,
        customWords: customDictionary,
      }),
      Comments.configure({
        comments: commentHighlights,
        activeCommentId,
        onCommentClick,
      }),
      AiDiff.configure({
        checkpoint,
      }),
    ],
    content: mdToHtml(content),
    onUpdate: ({ editor: e }) => {
      if (suppressUpdate.current) return;
      const md = htmlToMd(e.getHTML());
      onChangeRef.current(md);
    },
    editorProps: {
      attributes: {
        class:
          "prose prose-invert prose-sm max-w-none min-h-[60vh] px-6 py-4 focus:outline-none",
        spellcheck: "false",
      },
      handleDrop: (_view, event) => {
        const files = event.dataTransfer?.files;
        if (!files?.length) return false;
        const file = files[0];
        if (!file.type.startsWith("image/")) return false;
        event.preventDefault();
        uploadHandlerRef.current?.(file);
        return true;
      },
      handlePaste: (_view, event) => {
        const files = event.clipboardData?.files;
        if (!files?.length) return false;
        const file = files[0];
        if (!file.type.startsWith("image/")) return false;
        event.preventDefault();
        uploadHandlerRef.current?.(file);
        return true;
      },
    },
  });

  const uploadHandlerRef = useRef(handleUploadAndInsert);
  uploadHandlerRef.current = handleUploadAndInsert;
  editorRef.current = editor;

  // Sync spellcheck enabled state when prop changes
  useEffect(() => {
    if (!editor) return;
    const currentEnabled = editor.storage.spellcheck?.enabled;
    if (currentEnabled !== spellcheckEnabled) {
      editor.storage.spellcheck.enabled = spellcheckEnabled;
      // Trigger re-decoration
      editor.commands.toggleSpellcheck();
      editor.commands.toggleSpellcheck();
    }
  }, [editor, spellcheckEnabled]);

  // Sync custom dictionary when it changes
  useEffect(() => {
    if (!editor) return;
    // Updating options triggers the plugin view's update which re-checks
    (editor.extensionManager.extensions.find(
      (e) => e.name === "spellcheck"
    ) as typeof Spellcheck | undefined)?.options &&
      Object.assign(
        editor.extensionManager.extensions.find((e) => e.name === "spellcheck")!.options,
        { customWords: customDictionary }
      );
  }, [editor, customDictionary]);

  useEffect(() => {
    if (!editor) return;
    const ext = editor.extensionManager.extensions.find(
      (e) => e.name === "comments"
    );
    if (!ext) return;
    Object.assign(ext.options, {
      comments: commentHighlights,
      activeCommentId,
      onCommentClick,
    });
    const { state } = editor.view;
    const tr = state.tr.setMeta("comments", { rebuild: true });
    editor.view.dispatch(tr);
  }, [editor, commentHighlights, activeCommentId, onCommentClick]);

  useEffect(() => {
    if (!editor) return;
    const ext = editor.extensionManager.extensions.find(
      (e) => e.name === "aiDiff"
    );
    if (!ext) return;
    ext.options.checkpoint = checkpoint;
    const { state } = editor.view;
    const tr = state.tr.setMeta("aiDiff", { rebuild: true });
    editor.view.dispatch(tr);
  }, [editor, checkpoint]);

  useEffect(() => {
    if (rawMode) {
      setRawContent(content);
    } else if (editor) {
      const currentMd = htmlToMd(editor.getHTML());
      if (content !== currentMd) {
        suppressUpdate.current = true;
        editor.commands.setContent(mdToHtml(content), false);
        suppressUpdate.current = false;
      }
    }
  }, [content, editor, rawMode]);

  const switchToRaw = useCallback(() => {
    if (editor) {
      setRawContent(htmlToMd(editor.getHTML()));
    }
    setRawMode(true);
  }, [editor]);

  const switchToRich = useCallback(() => {
    onChangeRef.current(rawContent);
    if (editor) {
      suppressUpdate.current = true;
      editor.commands.setContent(mdToHtml(rawContent), false);
      suppressUpdate.current = false;
    }
    setRawMode(false);
  }, [editor, rawContent]);

  const handleRawChange = useCallback(
    (value: string) => {
      setRawContent(value);
      onChangeRef.current(value);
    },
    []
  );

  const ToolbarButton = useCallback(
    ({
      onClick,
      active,
      children,
      title,
    }: {
      onClick: () => void;
      active?: boolean;
      children: React.ReactNode;
      title?: string;
    }) => (
      <button
        type="button"
        onClick={onClick}
        title={title}
        className={`p-2 rounded hover:bg-tc-hover transition-colors ${
          active ? "bg-tc-hover text-tc-primary" : "text-tc-tertiary"
        }`}
      >
        {children}
      </button>
    ),
    []
  );

  if (!editor) return null;

  const spellcheckActive = editor.storage.spellcheck?.enabled ?? true;

  return (
    <div className="border border-tc-subtle rounded-lg overflow-hidden bg-tc-overlay">
      <div className="flex items-center justify-between px-2 py-1 border-b border-tc-subtle bg-tc-overlay">
        <div className="flex items-center gap-0.5 flex-wrap">
          {!rawMode && (
            <>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBold().run()}
                active={editor.isActive("bold")}
                title="Bold"
              >
                <Bold size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleItalic().run()}
                active={editor.isActive("italic")}
                title="Italic"
              >
                <Italic size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleStrike().run()}
                active={editor.isActive("strike")}
                title="Strikethrough"
              >
                <Strikethrough size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleCode().run()}
                active={editor.isActive("code")}
                title="Inline Code"
              >
                <CodeIcon size={16} />
              </ToolbarButton>
              <div className="w-px h-5 bg-tc-hover mx-1" />
              <ToolbarButton
                onClick={() =>
                  editor.chain().focus().toggleHeading({ level: 1 }).run()
                }
                active={editor.isActive("heading", { level: 1 })}
                title="Heading 1"
              >
                <Heading1 size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() =>
                  editor.chain().focus().toggleHeading({ level: 2 }).run()
                }
                active={editor.isActive("heading", { level: 2 })}
                title="Heading 2"
              >
                <Heading2 size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() =>
                  editor.chain().focus().toggleHeading({ level: 3 }).run()
                }
                active={editor.isActive("heading", { level: 3 })}
                title="Heading 3"
              >
                <Heading3 size={16} />
              </ToolbarButton>
              <div className="w-px h-5 bg-tc-hover mx-1" />
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBulletList().run()}
                active={editor.isActive("bulletList")}
                title="Bullet List"
              >
                <List size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                active={editor.isActive("orderedList")}
                title="Numbered List"
              >
                <ListOrdered size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBlockquote().run()}
                active={editor.isActive("blockquote")}
                title="Blockquote"
              >
                <Quote size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                active={editor.isActive("codeBlock")}
                title="Code Block"
              >
                <CodeXml size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().setHorizontalRule().run()}
                title="Horizontal Rule"
              >
                <Minus size={16} />
              </ToolbarButton>
              <div className="w-px h-5 bg-tc-hover mx-1" />
              <ToolbarButton
                onClick={() => editor.chain().focus().undo().run()}
                title="Undo"
              >
                <Undo size={16} />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().redo().run()}
                title="Redo"
              >
                <Redo size={16} />
              </ToolbarButton>
              <div className="w-px h-5 bg-tc-hover mx-1" />
              <ToolbarButton
                onClick={() => editor.commands.toggleSpellcheck()}
                active={spellcheckActive}
                title={spellcheckActive ? "Spellcheck on" : "Spellcheck off"}
              >
                <SpellCheck size={16} />
              </ToolbarButton>
              {(workId || (images && images.length > 0)) && (
                <>
                  <div className="w-px h-5 bg-tc-hover mx-1" />
                  <ToolbarButton
                    onClick={() => setShowImagePicker(true)}
                    title="Insert image"
                  >
                    <ImageIcon size={16} />
                  </ToolbarButton>
                </>
              )}
            </>
          )}
        </div>
        <ToolbarButton
          onClick={rawMode ? switchToRich : switchToRaw}
          active={rawMode}
          title={rawMode ? "Rich text" : "Markdown source"}
        >
          {rawMode ? <Eye size={16} /> : <Code size={16} />}
        </ToolbarButton>
      </div>

      {rawMode ? (
        <textarea
          value={rawContent}
          onChange={(e) => handleRawChange(e.target.value)}
          placeholder={placeholder}
          className="w-full min-h-[60vh] px-6 py-4 bg-transparent text-sm text-tc-secondary placeholder-gray-600 resize-none focus:outline-none font-mono leading-relaxed"
        />
      ) : (
        <EditorContent editor={editor} />
      )}

      {showImagePicker && (
        <ImagePickerModal
          title="Insert Image"
          images={(images || []) as import("@/types").WorkImage[]}
          onSelect={(img) => {
            editor
              ?.chain()
              .focus()
              .setImage({ src: img.url, alt: img.alt_text || img.original_name })
              .run();
            setShowImagePicker(false);
          }}
          onUpload={workId ? (file) => {
            handleUploadAndInsert(file);
            setShowImagePicker(false);
          } : undefined}
          onClose={() => setShowImagePicker(false)}
        />
      )}
    </div>
  );
}
