import { useQuery } from "@tanstack/react-query";
import { useState, useRef, useEffect, useCallback } from "react";
import { ImagePlus, X } from "lucide-react";
import { Work, TitlePageConfig, Font, WorkImage } from "@/types";
import { listFonts } from "@/api/fonts";
import { listImages, listAllImages, uploadImage } from "@/api/images";
import ImagePickerModal from "./ImagePickerModal";
import FontSelect, { FontSizeInput, parseFontSize, useFontFaceStyles } from "@/components/FontSelect";

function ToolbarSizeInput({
  value,
  onApply,
}: {
  value: string;
  onApply: (v: string) => void;
}) {
  const { num, unit } = parseFontSize(value);
  const [localNum, setLocalNum] = useState(String(num));
  const [localUnit, setLocalUnit] = useState(unit);

  useEffect(() => {
    const p = parseFontSize(value);
    setLocalNum(String(p.num));
    setLocalUnit(p.unit);
  }, [value]);

  const apply = () => {
    const n = parseFloat(localNum) || 0;
    if (n > 0) onApply(`${n}${localUnit}`);
  };

  return (
    <div className="flex">
      <input
        type="number"
        step={localUnit === "pt" ? "0.5" : "0.05"}
        min="0"
        value={localNum}
        onChange={(e) => setLocalNum(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply();
          }
        }}
        className="w-16 bg-tc-hover border border-tc-strong rounded-l px-2 py-1.5 text-xs focus:border-tc-accent focus:outline-none"
      />
      <select
        value={localUnit}
        onChange={(e) => {
          const newUnit = e.target.value as "pt" | "em";
          const n = parseFloat(localNum) || 0;
          const converted =
            newUnit === "pt" && localUnit === "em"
              ? Math.round(n * 12)
              : newUnit === "em" && localUnit === "pt"
                ? +(n / 12).toFixed(2)
                : n;
          setLocalNum(String(converted));
          setLocalUnit(newUnit);
        }}
        className="bg-tc-hover border border-tc-strong rounded-r px-1 py-1.5 text-xs text-tc-tertiary focus:border-tc-accent focus:outline-none"
      >
        <option value="pt">pt</option>
        <option value="em">em</option>
      </select>
    </div>
  );
}

function SubtitleEditor({
  value,
  defaultFont,
  defaultSize,
  customFonts,
  onChange,
  onDefaultFontChange,
  onDefaultSizeChange,
}: {
  value: string;
  defaultFont: string;
  defaultSize: string;
  customFonts: Font[];
  onChange: (html: string | null) => void;
  onDefaultFontChange: (v: string | null) => void;
  onDefaultSizeChange: (v: string) => void;
}) {
  const subtitleRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const savedRange = useRef<Range | null>(null);
  const toolbarActive = useRef(false);

  const [hasSelection, setHasSelection] = useState(false);
  const [selFont, setSelFont] = useState("");
  const [selSize, setSelSize] = useState("");
  const [selWeight, setSelWeight] = useState(400);
  const [selItalic, setSelItalic] = useState(false);

  const readSelectionFormatting = useCallback((range: Range) => {
    if (!subtitleRef.current) return;
    const node = range.startContainer;
    let el = (node.nodeType === Node.TEXT_NODE ? node.parentElement : node) as HTMLElement | null;

    let font = "";
    let size = "";
    let weight = 400;
    let italic = false;

    while (el && el !== subtitleRef.current) {
      if (!font && el.style.fontFamily) {
        const raw = window.getComputedStyle(el).fontFamily;
        const first = raw.split(",")[0].trim().replace(/^["']|["']$/g, "");
        font = `'${first}'`;
      }
      if (!size && el.style.fontSize) size = el.style.fontSize;
      if (el.style.fontWeight) {
        const w = el.style.fontWeight;
        weight = w === "bold" ? 700 : w === "normal" ? 400 : parseInt(w) || 400;
      }
      if (el.style.fontStyle === "italic") italic = true;
      el = el.parentElement;
    }

    setSelFont(font);
    setSelSize(size);
    setSelWeight(weight);
    setSelItalic(italic);
  }, []);

  // Capture the range snapshot on toolbar mousedown, before the browser
  // collapses the contenteditable selection due to focus shift.
  useEffect(() => {
    const toolbar = toolbarRef.current;
    if (!toolbar) return;
    const onDown = () => {
      toolbarActive.current = true;
      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0 && subtitleRef.current) {
        const r = sel.getRangeAt(0);
        if (subtitleRef.current.contains(r.commonAncestorContainer) && !r.collapsed) {
          savedRange.current = r.cloneRange();
        }
      }
    };
    const onUp = () => { toolbarActive.current = false; };
    toolbar.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    return () => {
      toolbar.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  useEffect(() => {
    const handler = () => {
      if (!subtitleRef.current) return;
      // While the user is interacting with toolbar controls, ignore selection
      // changes — the browser collapses the CE selection as an intermediate
      // step before focus moves, which would wipe savedRange.
      if (toolbarActive.current) return;

      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const range = sel.getRangeAt(0);

      if (!subtitleRef.current.contains(range.commonAncestorContainer)) return;

      if (range.collapsed) {
        savedRange.current = null;
        setHasSelection(false);
        return;
      }

      savedRange.current = range.cloneRange();
      setHasSelection(true);
      readSelectionFormatting(range);
    };
    document.addEventListener("selectionchange", handler);
    return () => document.removeEventListener("selectionchange", handler);
  }, [readSelectionFormatting]);

  const flushHTML = useCallback(() => {
    if (!subtitleRef.current) return;
    const html = subtitleRef.current.innerHTML || null;
    onChange(html);
  }, [onChange]);

  const applyToSelection = useCallback(
    (styleProp: string, styleValue: string) => {
      const range = savedRange.current;
      if (!range || !subtitleRef.current) return;
      if (range.collapsed) return;

      const fragment = range.extractContents();
      const span = document.createElement("span");
      (span.style as any)[styleProp] = styleValue;
      span.appendChild(fragment);
      range.insertNode(span);

      window.getSelection()?.removeAllRanges();
      savedRange.current = null;
      setHasSelection(false);
      flushHTML();
    },
    [flushHTML]
  );

  const handleFontChange = (v: string) => {
    if (hasSelection && savedRange.current) {
      applyToSelection("fontFamily", v);
    } else {
      onDefaultFontChange(v || null);
    }
  };

  const handleSizeApply = (v: string) => {
    if (hasSelection && savedRange.current) {
      applyToSelection("fontSize", v);
    } else {
      onDefaultSizeChange(v);
    }
  };

  const handleBold = () => {
    if (!hasSelection || !savedRange.current) return;
    applyToSelection("fontWeight", selWeight >= 700 ? "normal" : "bold");
  };

  const handleSemiBold = () => {
    if (!hasSelection || !savedRange.current) return;
    applyToSelection("fontWeight", selWeight === 600 ? "normal" : "600");
  };

  const handleItalic = () => {
    if (!hasSelection || !savedRange.current) return;
    applyToSelection("fontStyle", selItalic ? "normal" : "italic");
  };

  const handleWrapperBlur = (e: React.FocusEvent) => {
    if (wrapperRef.current?.contains(e.relatedTarget as Node)) return;
    flushHTML();
    savedRange.current = null;
    setHasSelection(false);
  };

  const displayFont = hasSelection ? selFont : defaultFont;
  const displaySize = hasSelection ? selSize || defaultSize : defaultSize;

  return (
    <div ref={wrapperRef} onBlur={handleWrapperBlur}>
      <div ref={toolbarRef} className="flex items-center gap-1.5 mb-1.5 p-1.5 bg-tc-overlay rounded-t border border-tc-strong border-b-0">
        <div className="w-44 shrink-0">
          <FontSelect
            value={displayFont}
            onChange={handleFontChange}
            customFonts={customFonts}
            allowEmpty={!hasSelection}
            placeholder={hasSelection ? "Inherited" : "Default subtitle font"}
          />
        </div>
        <ToolbarSizeInput value={displaySize} onApply={handleSizeApply} />
        <div className="flex gap-0.5 ml-1">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleBold}
            className={`w-7 h-7 flex items-center justify-center text-xs rounded transition-colors ${
              hasSelection && selWeight >= 700
                ? "bg-tc-accent/40 text-tc-accent border border-tc-accent/50"
                : "bg-tc-hover border border-tc-strong text-tc-secondary hover:bg-tc-active"
            } ${!hasSelection ? "opacity-40 cursor-default" : ""}`}
            style={{ fontWeight: 700 }}
          >
            B
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleSemiBold}
            className={`w-7 h-7 flex items-center justify-center text-xs rounded transition-colors ${
              hasSelection && selWeight === 600
                ? "bg-tc-accent/40 text-tc-accent border border-tc-accent/50"
                : "bg-tc-hover border border-tc-strong text-tc-secondary hover:bg-tc-active"
            } ${!hasSelection ? "opacity-40 cursor-default" : ""}`}
            style={{ fontWeight: 600, fontSize: "0.65rem" }}
          >
            SB
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleItalic}
            className={`w-7 h-7 flex items-center justify-center text-xs rounded transition-colors ${
              hasSelection && selItalic
                ? "bg-tc-accent/40 text-tc-accent border border-tc-accent/50"
                : "bg-tc-hover border border-tc-strong text-tc-secondary hover:bg-tc-active"
            } ${!hasSelection ? "opacity-40 cursor-default" : ""}`}
            style={{ fontStyle: "italic" }}
          >
            I
          </button>
        </div>
      </div>
      <div
        ref={subtitleRef}
        contentEditable
        suppressContentEditableWarning
        dangerouslySetInnerHTML={{ __html: value }}
        className="w-full min-h-[2.5rem] bg-tc-hover border border-tc-strong rounded-b px-3 py-2 text-sm focus:border-tc-accent focus:outline-none text-tc-secondary"
      />
    </div>
  );
}

function OrnamentPicker({
  workId,
  currentUrl,
  onSelect,
  onClear,
}: {
  workId: string;
  currentUrl: string | null;
  onSelect: (url: string) => void;
  onClear: () => void;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [scope, setScope] = useState<"work" | "all">("work");
  const { data: workImages = [], refetch } = useQuery<WorkImage[]>({
    queryKey: ["images", workId],
    queryFn: () => listImages(workId),
    enabled: !!workId,
  });
  const { data: allImages = [] } = useQuery<WorkImage[]>({
    queryKey: ["images", "all"],
    queryFn: () => listAllImages(),
    enabled: showPicker && scope === "all",
  });

  const displayImages = scope === "work" ? workImages : allImages;

  return (
    <div>
      <label className="block text-sm text-tc-tertiary mb-1">Ornament / Image</label>
      <p className="text-xs text-tc-muted mb-2">
        Displayed centered between subtitle and author.
      </p>
      {currentUrl ? (
        <div className="flex items-center gap-3">
          <img
            src={currentUrl}
            alt="Ornament"
            className="h-16 object-contain rounded border border-tc-subtle"
          />
          <button
            type="button"
            onClick={() => setShowPicker(true)}
            className="p-1 text-tc-muted hover:text-tc-secondary transition-colors"
            title="Change image"
          >
            <ImagePlus size={14} />
          </button>
          <button
            type="button"
            onClick={onClear}
            className="p-1 text-tc-muted hover:text-tc-error transition-colors"
            title="Remove image"
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowPicker(true)}
          className="flex items-center gap-2 px-3 py-2 text-xs bg-tc-hover border border-tc-strong rounded hover:bg-tc-active text-tc-secondary transition-colors"
        >
          <ImagePlus size={14} />
          Choose image
        </button>
      )}
      {showPicker && (
        <ImagePickerModal
          title="Choose Ornament Image"
          images={displayImages}
          onSelect={(img) => {
            onSelect(img.url);
            setShowPicker(false);
          }}
          onUpload={async (file) => {
            const img = await uploadImage(workId, file);
            refetch();
            onSelect(img.url);
            setShowPicker(false);
          }}
          onClose={() => setShowPicker(false)}
          filterTabs={[
            { key: "work", label: "This work" },
            { key: "all", label: "All images" },
          ]}
          activeFilter={scope}
          onFilterChange={(key) => setScope(key as "work" | "all")}
        />
      )}
    </div>
  );
}

export default function TitlePageEditor({
  work,
  config,
  onChange,
}: {
  work: Work;
  config: TitlePageConfig | null;
  onChange: (cfg: TitlePageConfig | null) => void;
}) {
  const { data: customFonts = [] } = useQuery<Font[]>({
    queryKey: ["fonts"],
    queryFn: listFonts,
  });
  useFontFaceStyles(customFonts);

  const cfg = config ?? {};
  const upd = (patch: Partial<TitlePageConfig>) => onChange({ ...cfg, ...patch });

  return (
    <div className="space-y-4">
      <p className="text-xs text-tc-muted">
        Customize how the title page appears in export and reading mode. Leave
        fields empty to use the work's title, subtitle, and author.
      </p>

      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Title</label>
            <input
              type="text"
              value={cfg.title_override ?? ""}
              onChange={(e) => upd({ title_override: e.target.value || null })}
              placeholder={work.title}
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">
              Title Font
            </label>
            <FontSelect
              value={cfg.title_font_family ?? ""}
              onChange={(v) => upd({ title_font_family: v || null })}
              customFonts={customFonts}
              allowEmpty
              placeholder="Default (profile font)"
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">
              Title Font Size
            </label>
            <FontSizeInput
              value={cfg.title_font_size ?? "2em"}
              onChange={(v) => upd({ title_font_size: v })}
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Author</label>
            <input
              type="text"
              value={cfg.author_override ?? ""}
              onChange={(e) =>
                upd({ author_override: e.target.value || null })
              }
              placeholder={work.author}
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">
              Author Font
            </label>
            <FontSelect
              value={cfg.author_font_family ?? ""}
              onChange={(v) => upd({ author_font_family: v || null })}
              customFonts={customFonts}
              allowEmpty
              placeholder="Default (profile font)"
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">
              Author Font Size
            </label>
            <FontSizeInput
              value={cfg.author_font_size ?? "1.2em"}
              onChange={(v) => upd({ author_font_size: v })}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm text-tc-tertiary mb-1">
            Author Position
          </label>
          <select
            value={cfg.author_position ?? "after_subtitle"}
            onChange={(e) =>
              upd({
                author_position:
                  e.target.value as TitlePageConfig["author_position"],
              })
            }
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
          >
            <option value="after_subtitle">After Title / Subtitle</option>
            <option value="bottom">Bottom of Page</option>
          </select>
        </div>

        <div>
          <label className="block text-sm text-tc-tertiary mb-1">Subtitle</label>
          <p className="text-xs text-tc-muted mb-2">
            Select text to format. Toolbar reflects selection or defaults. Size
            applies on Enter.
          </p>
          <SubtitleEditor
            value={cfg.subtitle_override ?? work.subtitle ?? ""}
            defaultFont={cfg.subtitle_font_family ?? ""}
            defaultSize={cfg.subtitle_font_size ?? "1em"}
            customFonts={customFonts}
            onChange={(html) => upd({ subtitle_override: html })}
            onDefaultFontChange={(v) =>
              upd({ subtitle_font_family: v })
            }
            onDefaultSizeChange={(v) => upd({ subtitle_font_size: v })}
          />
        </div>

        <OrnamentPicker
          workId={work.id}
          currentUrl={cfg.ornament_image_url ?? null}
          onSelect={(url) => upd({ ornament_image_url: url })}
          onClear={() => upd({ ornament_image_url: null })}
        />
      </div>

      <div className="p-4 bg-tc-base/50 rounded-lg border border-tc-subtle/50">
        <p className="text-xs text-tc-muted uppercase tracking-wide mb-3">
          Preview
        </p>
        <div
          className="text-center relative"
          style={{
            minHeight: cfg.author_position === "bottom" ? "20rem" : undefined,
          }}
        >
          <div
            style={{
              fontFamily: cfg.title_font_family || "inherit",
              fontSize: cfg.title_font_size || "2em",
              fontWeight: "bold",
            }}
            className="text-tc-primary"
          >
            {cfg.title_override || work.title}
          </div>
          {(cfg.subtitle_override || work.subtitle) && (
            <div
              style={{
                fontFamily: cfg.subtitle_font_family || "inherit",
                fontSize: cfg.subtitle_font_size || "1em",
              }}
              className="text-tc-secondary mt-2"
              dangerouslySetInnerHTML={{
                __html: cfg.subtitle_override || work.subtitle || "",
              }}
            />
          )}
          {cfg.ornament_image_url && (
            <div className="my-4 flex justify-center">
              <img
                src={cfg.ornament_image_url}
                alt="Ornament"
                className="max-h-24 object-contain"
              />
            </div>
          )}
          <div
            style={{
              fontFamily: cfg.author_font_family || "inherit",
              fontSize: cfg.author_font_size || "1.2em",
              ...(cfg.author_position === "bottom"
                ? { position: "absolute", bottom: 0, left: 0, right: 0 }
                : { marginTop: "2em" }),
            }}
            className="text-tc-tertiary"
          >
            {cfg.author_override || work.author}
          </div>
        </div>
      </div>
    </div>
  );
}
