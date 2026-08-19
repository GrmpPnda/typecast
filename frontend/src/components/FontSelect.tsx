import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import { Font } from "@/types";

export const FONT_OPTIONS = [
  { label: "Georgia", value: "Georgia, serif" },
  { label: "Garamond", value: "'EB Garamond', Garamond, serif" },
  { label: "Palatino", value: "Palatino, 'Palatino Linotype', serif" },
  { label: "Baskerville", value: "Baskerville, 'Libre Baskerville', serif" },
  { label: "Caslon", value: "'Libre Caslon Text', 'Book Antiqua', serif" },
  { label: "Times New Roman", value: "'Times New Roman', Times, serif" },
  { label: "Merriweather", value: "Merriweather, serif" },
  { label: "Lora", value: "Lora, serif" },
  { label: "Crimson Text", value: "'Crimson Text', serif" },
  { label: "Source Serif", value: "'Source Serif 4', 'Source Serif Pro', serif" },
  { label: "Literata", value: "Literata, serif" },
  { label: "Noto Serif", value: "'Noto Serif', serif" },
  { label: "Arial", value: "Arial, 'sans serif'" },
  { label: "Helvetica", value: "Helvetica, 'sans serif'" },
  { label: "Verdana", value: "Verdana, 'sans serif'" },
];

export function parseFontSize(raw: string): { num: number; unit: "pt" | "em" } {
  const match = raw.match(/^([\d.]+)\s*(pt|em)$/i);
  if (match) return { num: parseFloat(match[1]), unit: match[2].toLowerCase() as "pt" | "em" };
  return { num: 1, unit: "em" };
}

export function FontSizeInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { num, unit } = parseFontSize(value);
  return (
    <div className="flex gap-1">
      <input
        type="number"
        step={unit === "pt" ? "0.5" : "0.05"}
        min="0"
        value={num}
        onChange={(e) => {
          const n = e.target.value !== "" ? parseFloat(e.target.value) : 0;
          onChange(`${n}${unit}`);
        }}
        className="flex-1 min-w-0 bg-tc-hover border border-tc-strong rounded-l px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
      />
      <select
        value={unit}
        onChange={(e) => {
          const newUnit = e.target.value as "pt" | "em";
          const converted = newUnit === "pt" && unit === "em" ? Math.round(num * 12) : newUnit === "em" && unit === "pt" ? +(num / 12).toFixed(2) : num;
          onChange(`${converted}${newUnit}`);
        }}
        className="bg-tc-hover border border-tc-strong rounded-r px-2 py-2 text-sm text-tc-tertiary focus:border-tc-accent focus:outline-none"
      >
        <option value="pt">pt</option>
        <option value="em">em</option>
      </select>
    </div>
  );
}

export function useFontFaceStyles(customFonts: Font[]) {
  useEffect(() => {
    const id = "typecast-custom-fonts";
    let style = document.getElementById(id) as HTMLStyleElement | null;
    if (!style) {
      style = document.createElement("style");
      style.id = id;
      document.head.appendChild(style);
    }
    style.textContent = customFonts
      .map(
        (f) =>
          `@font-face { font-family: '${f.family_name}'; src: url('${f.url}') format('${formatForMime(f.mime_type)}'); }`
      )
      .join("\n");
    return () => {
      if (style && !customFonts.length) {
        style.textContent = "";
      }
    };
  }, [customFonts]);
}

function formatForMime(mime: string): string {
  if (mime.includes("woff2")) return "woff2";
  if (mime.includes("woff")) return "woff";
  if (mime.includes("opentype") || mime.includes("otf")) return "opentype";
  return "truetype";
}

interface FontSelectProps {
  value: string;
  onChange: (v: string) => void;
  customFonts?: Font[];
  placeholder?: string;
  allowEmpty?: boolean;
}

export default function FontSelect({ value, onChange, customFonts = [], placeholder, allowEmpty }: FontSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const allOptions = [
    ...FONT_OPTIONS,
    ...customFonts.map((f) => ({
      label: `${f.family_name}${f.style !== "Regular" ? ` ${f.style}` : ""}`,
      value: `'${f.family_name}'`,
      isCustom: true,
    })),
  ];

  const current = allOptions.find((f) => f.value === value);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm text-left focus:border-tc-accent focus:outline-none flex items-center justify-between"
      >
        <span style={{ fontFamily: current?.value || "inherit" }} className={!current && !value ? "text-tc-muted" : ""}>
          {current?.label || placeholder || value || "Select font..."}
        </span>
        <ChevronDown size={14} className={`text-tc-tertiary transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full bg-tc-overlay border border-tc-subtle rounded-lg shadow-xl max-h-60 overflow-y-auto py-1">
          {allowEmpty && (
            <button
              type="button"
              onClick={() => { onChange(""); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                !value ? "bg-tc-accent/30 text-tc-accent" : "text-tc-muted hover:bg-tc-hover"
              }`}
            >
              {placeholder || "Default"}
            </button>
          )}
          {FONT_OPTIONS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => { onChange(f.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                f.value === value
                  ? "bg-tc-accent/30 text-tc-accent"
                  : "text-tc-secondary hover:bg-tc-hover"
              }`}
              style={{ fontFamily: f.value }}
            >
              {f.label}
            </button>
          ))}
          {customFonts.length > 0 && (
            <>
              <div className="border-t border-tc-subtle my-1" />
              <div className="px-3 py-1 text-xs text-tc-muted uppercase tracking-wider">Custom Fonts</div>
              {customFonts.map((f) => {
                const val = `'${f.family_name}'`;
                return (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => { onChange(val); setOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      val === value
                        ? "bg-tc-accent/30 text-tc-accent"
                        : "text-tc-secondary hover:bg-tc-hover"
                    }`}
                    style={{ fontFamily: `'${f.family_name}'` }}
                  >
                    {f.family_name}{f.style !== "Regular" ? ` ${f.style}` : ""}
                  </button>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
}
