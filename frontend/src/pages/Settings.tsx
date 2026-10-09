import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  BookOpen,
  Save,
  X,
  Pencil,
  ChevronDown,
  ChevronRight,
  Copy,
  Upload,
  Download,
  RotateCcw,
  Sun,
  Moon,
  Check,
  Palette,
  Cloud,
  KeyRound,
  Shield,
  UserPlus,
  Users,
} from "lucide-react";
import {
  listProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
} from "@/api/profiles";
import { listFonts, uploadFont, deleteFont } from "@/api/fonts";
import { listConfig, updateConfig, fetchBedrockModels, fetchBedrockImageModels, BedrockModel } from "@/api/config";
import { downloadBackup, importBackup, restoreBackup } from "@/api/backup";
import { listVoices, PollyVoice } from "@/api/narration";
import {
  getDriveStatus,
  getDriveAuthUrl,
  disconnectDrive,
  listDriveBackups,
  backupToDrive,
  restoreFromDrive,
} from "@/api/gdrive";
import { changeMyPassword } from "@/api/auth";
import {
  listUsers,
  createUser,
  updateUser,
  resetUserPassword,
  deleteUser,
  ManagedUser,
} from "@/api/users";
import { useAuth } from "@/auth";
import { useState, useEffect, useRef } from "react";
import { Profile, CreateProfile, UpdateProfile, ProfileFormat, HeaderContent, HeaderPosition, TextAlign, Font } from "@/types";
import FontSelect, { FontSizeInput, useFontFaceStyles } from "@/components/FontSelect";
import { useTheme } from "@/theme";
import { themes } from "@/themes";

const HEADER_CONTENT_LABELS: Record<string, string> = {
  "": "None",
  title: "Book Title",
  author: "Author",
  chapter: "Chapter Number",
  chapter_title: "Chapter Title",
  page_number: "Page Number",
};

const BEDROCK_REGIONS = [
  "us-east-1",
  "us-east-2",
  "us-west-2",
  "eu-west-1",
  "eu-west-3",
  "eu-central-1",
  "ap-southeast-1",
  "ap-southeast-2",
  "ap-northeast-1",
];

const BEDROCK_MODELS = [
  { id: "us.anthropic.claude-opus-4-8", label: "Claude Opus 4.8 (Anthropic)" },
  { id: "us.anthropic.claude-opus-4-7", label: "Claude Opus 4.7 (Anthropic)" },
  { id: "us.anthropic.claude-sonnet-4-6", label: "Claude Sonnet 4.6 (Anthropic)" },
  { id: "us.anthropic.claude-fable-5", label: "Claude Fable 5 (Anthropic)" },
  { id: "us.anthropic.claude-opus-4-6-v1", label: "Claude Opus 4.6 (Anthropic)" },
  { id: "us.anthropic.claude-opus-4-5-20251101-v1:0", label: "Claude Opus 4.5 (Anthropic)" },
  { id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0", label: "Claude Sonnet 4.5 (Anthropic)" },
  { id: "us.anthropic.claude-opus-4-1-20250805-v1:0", label: "Claude Opus 4.1 (Anthropic)" },
  { id: "us.anthropic.claude-sonnet-4-20250514-v1:0", label: "Claude Sonnet 4 (Anthropic)" },
  { id: "us.anthropic.claude-haiku-4-5-20251001-v1:0", label: "Claude Haiku 4.5 (Anthropic)" },
  { id: "us.anthropic.claude-3-5-haiku-20241022-v1:0", label: "Claude 3.5 Haiku (Anthropic)" },
];

const IMAGE_PROVIDER_OPTIONS = [
  { value: "", label: "Same as text provider" },
  { value: "openai", label: "OpenAI" },
  { value: "bedrock", label: "AWS Bedrock" },
];

const OPENAI_IMAGE_MODELS = [
  { id: "gpt-image-1", label: "GPT Image 1 (Latest)" },
  { id: "dall-e-3", label: "DALL-E 3" },
  { id: "dall-e-2", label: "DALL-E 2" },
];

const BEDROCK_IMAGE_MODELS = [
  { id: "amazon.nova-canvas-v1:0", label: "Nova Canvas (Amazon)" },
  { id: "stability.sd3-5-large-v1:0", label: "SD 3.5 Large (Stability AI)" },
  { id: "stability.sd3-large-v1:0", label: "SD 3 Large (Stability AI)" },
  { id: "stability.stable-image-core-v1:0", label: "Stable Image Core (Stability AI)" },
];

const HEADER_POS_LABELS: Record<string, string> = {
  center: "Center",
  outer: "Outside (alternating)",
};

interface ProfileFormData {
  name: string;
  format: ProfileFormat;
  description: string;
  page_width?: number;
  page_height?: number;
  margin_top?: number;
  margin_bottom?: number;
  margin_inner?: number;
  margin_outer?: number;
  font_family: string;
  font_size: string;
  line_height: number;
  header_footer: boolean;
  include_cover: boolean;
  include_toc: boolean;
  page_numbers_start_at_content: boolean;
  header_recto: HeaderContent;
  header_verso: HeaderContent;
  header_position: HeaderPosition;
  footer_recto: HeaderContent;
  footer_verso: HeaderContent;
  footer_position: string;
  header_font_family: string;
  header_font_size: string;
  header_font_weight: string;
  header_from_edge?: number;
  footer_from_edge?: number;
  front_matter_roman: boolean;
  text_align: TextAlign;
  chapter_font_family: string;
  chapter_font_size: string;
  chapter_font_weight: string;
  chapter_align: string;
  chapter_sink?: number;
  chapters_start_recto: boolean;
  back_matter_page_numbers: boolean;
}

const EMPTY_FORM: ProfileFormData = {
  name: "",
  format: "epub",
  description: "",
  font_family: "Georgia, serif",
  font_size: "1em",
  line_height: 1.5,
  header_footer: false,
  include_cover: true,
  include_toc: true,
  page_numbers_start_at_content: true,
  header_recto: "",
  header_verso: "",
  header_position: "outer",
  footer_recto: "",
  footer_verso: "",
  footer_position: "center",
  header_font_family: "",
  header_font_size: "9pt",
  header_font_weight: "",
  front_matter_roman: false,
  text_align: "justify",
  chapter_font_family: "",
  chapter_font_size: "1.4em",
  chapter_font_weight: "normal",
  chapter_align: "center",
  chapters_start_recto: false,
  back_matter_page_numbers: true,
};

function profileToForm(p: Profile): ProfileFormData {
  return {
    name: p.name,
    format: p.format,
    description: p.description ?? "",
    page_width: p.page_width ?? undefined,
    page_height: p.page_height ?? undefined,
    margin_top: p.margin_top ?? undefined,
    margin_bottom: p.margin_bottom ?? undefined,
    margin_inner: p.margin_inner ?? undefined,
    margin_outer: p.margin_outer ?? undefined,
    font_family: p.font_family,
    font_size: p.font_size,
    line_height: p.line_height,
    header_footer: p.header_footer,
    include_cover: p.include_cover,
    include_toc: p.include_toc,
    page_numbers_start_at_content: p.page_numbers_start_at_content,
    header_recto: (p.header_recto ?? "") as HeaderContent,
    header_verso: (p.header_verso ?? "") as HeaderContent,
    header_position: p.header_position ?? "outer",
    footer_recto: (p.footer_recto ?? "") as HeaderContent,
    footer_verso: (p.footer_verso ?? "") as HeaderContent,
    footer_position: p.footer_position ?? "center",
    header_font_family: p.header_font_family ?? "",
    header_font_size: p.header_font_size ?? "9pt",
    header_font_weight: p.header_font_weight ?? "",
    header_from_edge: p.header_from_edge ?? undefined,
    footer_from_edge: p.footer_from_edge ?? undefined,
    front_matter_roman: p.front_matter_roman ?? false,
    text_align: p.text_align ?? "justify",
    chapter_font_family: p.chapter_font_family ?? "",
    chapter_font_size: p.chapter_font_size ?? "1.4em",
    chapter_font_weight: p.chapter_font_weight ?? "normal",
    chapter_align: p.chapter_align ?? "center",
    chapter_sink: p.chapter_sink ?? undefined,
    chapters_start_recto: p.chapters_start_recto ?? false,
    back_matter_page_numbers: p.back_matter_page_numbers ?? true,
  };
}

function DetailRow({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  if (value === null || value === undefined || value === "") return null;
  const display = typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  return (
    <div className="flex justify-between py-1">
      <span className="text-xs text-tc-muted">{label}</span>
      <span className="text-xs text-tc-secondary">{display}</span>
    </div>
  );
}

function ProfileDetails({ profile }: { profile: Profile }) {
  const isPdf = profile.format === "pdf";
  return (
    <div className="mt-3 pt-3 border-t border-tc-subtle/50 grid gap-x-8 gap-y-0 sm:grid-cols-2">
      <div>
        <p className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-1">Typography</p>
        <DetailRow label="Font Family" value={profile.font_family} />
        <DetailRow label="Font Size" value={profile.font_size} />
        <DetailRow label="Line Height" value={profile.line_height} />
        {isPdf && <DetailRow label="Text Alignment" value={{ justify: "Justified", left: "Left", right: "Right", center: "Center" }[profile.text_align] ?? profile.text_align} />}
      </div>
      {isPdf && (
        <div>
          <p className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-1">Chapter Headings</p>
          <DetailRow label="Font" value={profile.chapter_font_family || "Same as body"} />
          <DetailRow label="Title Size" value={profile.chapter_font_size || "1.4em"} />
          <DetailRow label="Weight" value={profile.chapter_font_weight || "normal"} />
          <DetailRow label="Alignment" value={{ center: "Center", left: "Left", right: "Right" }[profile.chapter_align ?? "center"] ?? profile.chapter_align} />
          <DetailRow label="Sink" value={profile.chapter_sink != null ? `${profile.chapter_sink}em` : "3em (default)"} />
        </div>
      )}
      {isPdf && (
        <div>
          <p className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-1">Page Dimensions</p>
          <DetailRow label="Width" value={profile.page_width != null ? `${profile.page_width} in` : null} />
          <DetailRow label="Height" value={profile.page_height != null ? `${profile.page_height} in` : null} />
          <DetailRow label="Margin Top" value={profile.margin_top != null ? `${profile.margin_top} in` : null} />
          <DetailRow label="Margin Bottom" value={profile.margin_bottom != null ? `${profile.margin_bottom} in` : null} />
          <DetailRow label="Margin Inner" value={profile.margin_inner != null ? `${profile.margin_inner} in` : null} />
          <DetailRow label="Margin Outer" value={profile.margin_outer != null ? `${profile.margin_outer} in` : null} />
        </div>
      )}
      <div className={isPdf ? "sm:col-span-2 mt-1" : ""}>
        <p className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-1">Options</p>
        <DetailRow label="Include Cover" value={profile.include_cover} />
        <DetailRow label="Include Table of Contents" value={profile.include_toc} />
        {isPdf && <DetailRow label="Chapters Start Recto" value={profile.chapters_start_recto} />}
        {isPdf && (
          <>
            {(profile.header_recto || profile.header_verso) && (
              <>
                <DetailRow label="Header (Recto)" value={HEADER_CONTENT_LABELS[profile.header_recto ?? ""] ?? "None"} />
                <DetailRow label="Header (Verso)" value={HEADER_CONTENT_LABELS[profile.header_verso ?? ""] ?? "None"} />
                <DetailRow label="Header Position" value={HEADER_POS_LABELS[profile.header_position] ?? profile.header_position} />
              </>
            )}
            {(profile.footer_recto || profile.footer_verso) && (
              <>
                <DetailRow label="Footer (Recto)" value={HEADER_CONTENT_LABELS[profile.footer_recto ?? ""] ?? "None"} />
                <DetailRow label="Footer (Verso)" value={HEADER_CONTENT_LABELS[profile.footer_verso ?? ""] ?? "None"} />
                <DetailRow label="Footer Position" value={HEADER_POS_LABELS[profile.footer_position] ?? profile.footer_position} />
              </>
            )}
            {profile.page_numbers && (
              <>
                <DetailRow label="Start Numbering at Content" value={profile.page_numbers_start_at_content} />
                <DetailRow label="Continue in Back Matter" value={profile.back_matter_page_numbers} />
                <DetailRow label="Front Matter Roman Numerals" value={profile.front_matter_roman} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function DimensionInput({ label, value, onChange, placeholder }: {
  label: string;
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder: string;
}) {
  return (
    <div>
      <label className="block text-xs text-tc-tertiary mb-1">{label}</label>
      <div className="relative">
        <input
          type="number"
          step="0.001"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value !== "" ? parseFloat(e.target.value) : undefined)}
          placeholder={placeholder}
          className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 pr-8 text-sm focus:border-tc-accent focus:outline-none"
        />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-tc-muted">in</span>
      </div>
    </div>
  );
}

function ProfileForm({
  initial,
  onSave,
  onCancel,
  saving,
  isNew,
}: {
  initial: ProfileFormData;
  onSave: (data: ProfileFormData) => void;
  onCancel: () => void;
  saving: boolean;
  isNew: boolean;
}) {
  const [form, setForm] = useState(initial);
  const isPdf = form.format === "pdf";
  const { data: customFonts = [] } = useQuery<Font[]>({
    queryKey: ["fonts"],
    queryFn: listFonts,
  });

  const update = (patch: Partial<ProfileFormData>) =>
    setForm((f) => ({ ...f, ...patch }));

  return (
    <div className="p-5 bg-tc-overlay/50 border border-tc-subtle rounded-lg space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-xs text-tc-tertiary mb-1">Name</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => update({ name: e.target.value })}
            placeholder="My Custom Profile"
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
            autoFocus={isNew}
          />
        </div>
        <div>
          <label className="block text-xs text-tc-tertiary mb-1">Format</label>
          <select
            value={form.format}
            onChange={(e) => update({ format: e.target.value as ProfileFormat })}
            disabled={!isNew}
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none disabled:opacity-60"
          >
            <option value="epub">ePub</option>
            <option value="pdf">PDF</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs text-tc-tertiary mb-1">Description</label>
        <input
          type="text"
          value={form.description}
          onChange={(e) => update({ description: e.target.value })}
          placeholder="Optional description..."
          className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
        />
      </div>

      {isPdf && (
        <>
          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Page Dimensions
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <DimensionInput label="Page Width" value={form.page_width} onChange={(v) => update({ page_width: v })} placeholder="6" />
            <DimensionInput label="Page Height" value={form.page_height} onChange={(v) => update({ page_height: v })} placeholder="9" />
          </div>
          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Margins
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <DimensionInput label="Top" value={form.margin_top} onChange={(v) => update({ margin_top: v })} placeholder="0.75" />
            <DimensionInput label="Bottom" value={form.margin_bottom} onChange={(v) => update({ margin_bottom: v })} placeholder="0.75" />
            <DimensionInput label="Inner (spine)" value={form.margin_inner} onChange={(v) => update({ margin_inner: v })} placeholder="0.875" />
            <DimensionInput label="Outer" value={form.margin_outer} onChange={(v) => update({ margin_outer: v })} placeholder="0.625" />
          </div>
        </>
      )}

      <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
        Typography
      </h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="block text-xs text-tc-tertiary mb-1">Font Family</label>
          <FontSelect
            value={form.font_family ?? ""}
            onChange={(v) => update({ font_family: v })}
            customFonts={customFonts}
          />
        </div>
        <div>
          <label className="block text-xs text-tc-tertiary mb-1">Font Size</label>
          <FontSizeInput
            value={form.font_size ?? "1em"}
            onChange={(v) => update({ font_size: v })}
          />
        </div>
        <div>
          <label className="block text-xs text-tc-tertiary mb-1">Line Height</label>
          <input
            type="number" step="0.1" value={form.line_height ?? ""}
            onChange={(e) => update({ line_height: e.target.value ? parseFloat(e.target.value) : 1.5 })}
            placeholder="1.5"
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
          />
        </div>
        {isPdf && (
          <div>
            <label className="block text-xs text-tc-tertiary mb-1">Text Alignment</label>
            <select
              value={form.text_align}
              onChange={(e) => update({ text_align: e.target.value as TextAlign })}
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
            >
              <option value="justify">Justified</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
              <option value="center">Center</option>
            </select>
          </div>
        )}
      </div>

      <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
        Options
      </h3>
      <div className="flex flex-wrap gap-6">
        <label className="flex items-center gap-2 text-sm text-tc-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={form.include_cover}
            onChange={(e) => update({ include_cover: e.target.checked })}
            className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
          />
          Include Cover
        </label>
        <label className="flex items-center gap-2 text-sm text-tc-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={form.include_toc}
            onChange={(e) => update({ include_toc: e.target.checked })}
            className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
          />
          Include Table of Contents
        </label>
        {isPdf && (
          <label className="flex items-center gap-2 text-sm text-tc-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={form.chapters_start_recto}
              onChange={(e) => update({ chapters_start_recto: e.target.checked })}
              className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
            />
            Chapters start on right page
          </label>
        )}
      </div>

      {isPdf && (
        <>
          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Headers
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Recto (right pages)</label>
              <select
                value={form.header_recto}
                onChange={(e) => update({ header_recto: e.target.value as HeaderContent })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_CONTENT_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Verso (left pages)</label>
              <select
                value={form.header_verso}
                onChange={(e) => update({ header_verso: e.target.value as HeaderContent })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_CONTENT_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Position</label>
              <select
                value={form.header_position}
                onChange={(e) => update({ header_position: e.target.value as HeaderPosition })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_POS_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <DimensionInput
              label="Header from top edge"
              value={form.header_from_edge}
              onChange={(v) => update({ header_from_edge: v })}
              placeholder="0.3"
            />
          </div>

          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Footers
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Recto (right pages)</label>
              <select
                value={form.footer_recto}
                onChange={(e) => update({ footer_recto: e.target.value as HeaderContent })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_CONTENT_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Verso (left pages)</label>
              <select
                value={form.footer_verso}
                onChange={(e) => update({ footer_verso: e.target.value as HeaderContent })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_CONTENT_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Position</label>
              <select
                value={form.footer_position}
                onChange={(e) => update({ footer_position: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {Object.entries(HEADER_POS_LABELS).map(([val, lbl]) => (
                  <option key={val} value={val}>{lbl}</option>
                ))}
              </select>
            </div>
            <DimensionInput
              label="Footer from bottom edge"
              value={form.footer_from_edge}
              onChange={(v) => update({ footer_from_edge: v })}
              placeholder="0.3"
            />
          </div>

          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Header / Footer Typeface
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Font</label>
              <div className="flex gap-1 items-center">
                <FontSelect
                  value={form.header_font_family || form.font_family}
                  onChange={(v) => update({ header_font_family: v })}
                  customFonts={customFonts}
                />
                {form.header_font_family && (
                  <button
                    type="button"
                    onClick={() => update({ header_font_family: "" })}
                    className="text-tc-muted hover:text-tc-secondary shrink-0"
                    title="Reset to body font"
                  >×</button>
                )}
              </div>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Font Size</label>
              <FontSizeInput
                value={form.header_font_size || "9pt"}
                onChange={(v) => update({ header_font_size: v })}
              />
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Font Weight</label>
              <select
                value={form.header_font_weight}
                onChange={(e) => update({ header_font_weight: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                <option value="">Normal</option>
                <option value="bold">Bold</option>
                <option value="lighter">Light</option>
              </select>
            </div>
          </div>

          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Page Numbering
          </h3>
          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-tc-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={form.page_numbers_start_at_content}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const patch: Partial<ProfileFormData> = { page_numbers_start_at_content: checked };
                  if (!checked) patch.front_matter_roman = false;
                  update(patch);
                }}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
              />
              Start numbering at content
            </label>
            <label className="flex items-center gap-2 text-sm text-tc-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={form.back_matter_page_numbers}
                onChange={(e) => update({ back_matter_page_numbers: e.target.checked })}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
              />
              Continue numbering in back matter
            </label>
            <label className={`flex items-center gap-2 text-sm cursor-pointer ${form.page_numbers_start_at_content ? "text-tc-secondary" : "text-tc-muted"}`}>
              <input
                type="checkbox"
                checked={form.front_matter_roman}
                disabled={!form.page_numbers_start_at_content}
                onChange={(e) => update({ front_matter_roman: e.target.checked })}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0 disabled:opacity-40"
              />
              Number front matter (roman numerals)
            </label>
          </div>
          <h3 className="text-xs font-semibold text-tc-tertiary uppercase tracking-wide pt-2">
            Chapter Headings
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Font Family</label>
              <div className="flex gap-1 items-center">
                <FontSelect
                  value={form.chapter_font_family || form.font_family}
                  onChange={(v) => update({ chapter_font_family: v })}
                  customFonts={customFonts}
                />
                {form.chapter_font_family && (
                  <button
                    type="button"
                    onClick={() => update({ chapter_font_family: "" })}
                    className="text-tc-muted hover:text-tc-secondary shrink-0"
                    title="Reset to body font"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              {!form.chapter_font_family && (
                <p className="text-[10px] text-tc-muted mt-0.5">Same as body</p>
              )}
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Title Size</label>
              <FontSizeInput
                value={form.chapter_font_size || "1.4em"}
                onChange={(v) => update({ chapter_font_size: v })}
              />
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Weight</label>
              <select
                value={form.chapter_font_weight}
                onChange={(e) => update({ chapter_font_weight: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                <option value="normal">Normal</option>
                <option value="bold">Bold</option>
                <option value="lighter">Light</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Alignment</label>
              <select
                value={form.chapter_align}
                onChange={(e) => update({ chapter_align: e.target.value })}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                <option value="center">Center</option>
                <option value="left">Left</option>
                <option value="right">Right</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Sink (top margin)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  value={form.chapter_sink ?? ""}
                  onChange={(e) => update({ chapter_sink: e.target.value !== "" ? parseFloat(e.target.value) : undefined })}
                  placeholder="3"
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 pr-8 text-sm focus:border-tc-accent focus:outline-none"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-tc-muted">em</span>
              </div>
            </div>
          </div>
        </>
      )}

      <div className="flex gap-2 pt-2">
        <button
          onClick={() => onSave(form)}
          disabled={!form.name.trim() || saving}
          className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={14} />
          {saving ? "Saving..." : isNew ? "Create Profile" : "Save Changes"}
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors"
        >
          <X size={14} />
          Cancel
        </button>
      </div>
    </div>
  );
}

function FontsSection() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const { data: fonts = [] } = useQuery<Font[]>({
    queryKey: ["fonts"],
    queryFn: listFonts,
  });

  useFontFaceStyles(fonts);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadFont(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fonts"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteFont(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fonts"] });
    },
  });

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
      e.target.value = "";
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Custom Fonts</h2>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Upload size={14} />
          {uploadMutation.isPending ? "Uploading..." : "Upload Font"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".ttf,.otf,.woff,.woff2"
          onChange={handleUpload}
          className="hidden"
        />
      </div>

      {fonts.length === 0 ? (
        <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
          <p className="text-sm text-tc-muted">
            No custom fonts uploaded. Upload TTF, OTF, WOFF, or WOFF2 files to use them in profiles and title pages.
          </p>
        </div>
      ) : (
        <div className="grid gap-2">
          {fonts.map((f) => (
            <div
              key={f.id}
              className="flex items-center justify-between p-3 bg-tc-overlay/50 border border-tc-subtle/50 rounded-lg group"
            >
              <div className="flex items-center gap-4 min-w-0">
                <span
                  className="text-lg text-tc-secondary truncate"
                  style={{ fontFamily: `'${f.family_name}'` }}
                >
                  {f.family_name}
                </span>
                <span className="text-xs text-tc-muted shrink-0">
                  {f.style} &middot; {formatSize(f.size_bytes)} &middot; {f.original_name}
                </span>
              </div>
              <button
                onClick={() => {
                  if (confirm(`Delete font "${f.family_name}"?`)) {
                    deleteMutation.mutate(f.id);
                  }
                }}
                className="p-1.5 text-tc-muted hover:text-tc-error rounded transition-colors opacity-0 group-hover:opacity-100"
                title="Delete font"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {uploadMutation.isError && (
        <p className="text-sm text-tc-error mt-2">
          Upload failed: {(uploadMutation.error as Error).message}
        </p>
      )}
    </section>
  );
}

function EditorConfigSection() {
  const queryClient = useQueryClient();
  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });

  const getVal = (key: string) => config.find((c) => c.key === key)?.value ?? "";

  const [spellcheck, setSpellcheck] = useState(true);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config.length > 0) {
      setSpellcheck(getVal("spellcheck_enabled") !== "false");
      setDirty(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateConfig([
        { key: "spellcheck_enabled", value: spellcheck ? "true" : "false" },
      ]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] });
      setDirty(false);
    },
  });

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Editor</h2>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!dirty || saveMutation.isPending}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={14} />
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
      </div>
      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={spellcheck}
            onChange={(e) => { setSpellcheck(e.target.checked); setDirty(true); }}
            className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
          />
          <div>
            <span className="text-sm text-tc-secondary">Enable spellcheck</span>
            <p className="text-xs text-tc-muted mt-0.5">
              Highlight misspelled words in the editor. Codex entry names are automatically added to the dictionary.
              Can also be toggled per-editor from the toolbar.
            </p>
          </div>
        </label>
      </div>
    </section>
  );
}

function AIConfigSection() {
  const queryClient = useQueryClient();
  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });

  const getVal = (key: string) => config.find((c) => c.key === key)?.value ?? "";

  const [provider, setProvider] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [anthropicModel, setAnthropicModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");
  const [bedrockEnabled, setBedrockEnabled] = useState(false);
  const [bedrockRegion, setBedrockRegion] = useState("");
  const [bedrockModelId, setBedrockModelId] = useState("");
  const [bedrockAwsProfile, setBedrockAwsProfile] = useState("");
  const [imageProvider, setImageProvider] = useState("");
  const [imageModel, setImageModel] = useState("");
  const [bedrockImageRegion, setBedrockImageRegion] = useState("");
  const [dirty, setDirty] = useState(false);
  const [bedrockModels, setBedrockModels] = useState<BedrockModel[]>(BEDROCK_MODELS);
  const [refreshingModels, setRefreshingModels] = useState(false);
  const [bedrockImageModels, setBedrockImageModels] = useState<BedrockModel[]>(BEDROCK_IMAGE_MODELS);
  const [refreshingImageModels, setRefreshingImageModels] = useState(false);

  useEffect(() => {
    if (config.length > 0) {
      setProvider(getVal("ai_provider"));
      setAnthropicKey(getVal("anthropic_api_key"));
      setOpenaiKey(getVal("openai_api_key"));
      setAnthropicModel(getVal("anthropic_model"));
      setOpenaiModel(getVal("openai_model"));
      setBedrockEnabled(getVal("bedrock_enabled") === "true");
      const rawRegion = getVal("bedrock_region");
      setBedrockRegion(BEDROCK_REGIONS.includes(rawRegion) ? rawRegion : BEDROCK_REGIONS[0]);
      const rawModelId = getVal("bedrock_model_id");
      const validModelId = bedrockModels.some((m) => m.id === rawModelId);
      if (validModelId) {
        setBedrockModelId(rawModelId);
      } else if (rawModelId) {
        setBedrockModels((prev) => {
          if (prev.some((m) => m.id === rawModelId)) return prev;
          return [...prev, { id: rawModelId, label: rawModelId }];
        });
        setBedrockModelId(rawModelId);
      } else {
        setBedrockModelId(bedrockModels[0].id);
      }
      setBedrockAwsProfile(getVal("bedrock_aws_profile"));
      setImageProvider(getVal("image_provider"));
      setBedrockImageRegion(getVal("bedrock_image_region"));
      const rawImageModel = getVal("image_model");
      if (rawImageModel && !bedrockImageModels.some((m) => m.id === rawImageModel) && !OPENAI_IMAGE_MODELS.some((m) => m.id === rawImageModel)) {
        setBedrockImageModels((prev) => {
          if (prev.some((m) => m.id === rawImageModel)) return prev;
          return [...prev, { id: rawImageModel, label: rawImageModel }];
        });
      }
      setImageModel(rawImageModel);
      setDirty(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateConfig([
        { key: "ai_provider", value: provider },
        { key: "anthropic_api_key", value: anthropicKey, is_secret: true },
        { key: "openai_api_key", value: openaiKey, is_secret: true },
        { key: "anthropic_model", value: anthropicModel },
        { key: "openai_model", value: openaiModel },
        { key: "bedrock_enabled", value: bedrockEnabled ? "true" : "false" },
        { key: "bedrock_region", value: bedrockRegion },
        { key: "bedrock_model_id", value: bedrockModelId },
        { key: "bedrock_aws_profile", value: bedrockAwsProfile },
        { key: "image_provider", value: imageProvider },
        { key: "image_model", value: imageModel },
        { key: "bedrock_image_region", value: bedrockImageRegion },
      ]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] });
      setDirty(false);
    },
  });

  const upd = <T,>(setter: React.Dispatch<React.SetStateAction<T>>) =>
    (val: T) => { setter(val); setDirty(true); };

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">AI Configuration</h2>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!dirty || saveMutation.isPending}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={14} />
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
      </div>

      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-5">
        <div>
          <label className="block text-sm text-tc-tertiary mb-1">Default Provider</label>
          <select
            value={provider}
            onChange={(e) => upd(setProvider)(e.target.value)}
            className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
          >
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI (GPT)</option>
            {bedrockEnabled && <option value="bedrock">AWS Bedrock</option>}
          </select>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide">Anthropic</h3>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">API Key</label>
              <input
                type="password"
                value={anthropicKey}
                onChange={(e) => upd(setAnthropicKey)(e.target.value)}
                placeholder="sk-ant-..."
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm font-mono focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Model</label>
              <input
                type="text"
                value={anthropicModel}
                onChange={(e) => upd(setAnthropicModel)(e.target.value)}
                placeholder="claude-sonnet-4-20250514"
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide">OpenAI</h3>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">API Key</label>
              <input
                type="password"
                value={openaiKey}
                onChange={(e) => upd(setOpenaiKey)(e.target.value)}
                placeholder="sk-..."
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm font-mono focus:border-tc-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Model</label>
              <input
                type="text"
                value={openaiModel}
                onChange={(e) => upd(setOpenaiModel)(e.target.value)}
                placeholder="gpt-4o"
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              />
            </div>
          </div>
        </div>

        <div className="border-t border-tc-subtle pt-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide">
              AWS Bedrock
            </h3>
            <label className="flex items-center gap-2 text-sm text-tc-tertiary cursor-pointer">
              <input
                type="checkbox"
                checked={bedrockEnabled}
                onChange={(e) => {
                  upd(setBedrockEnabled)(e.target.checked);
                  if (!e.target.checked && provider === "bedrock") {
                    upd(setProvider)("anthropic");
                  }
                }}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
              />
              Enable
            </label>
          </div>
          {bedrockEnabled ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Region</label>
                <select
                  value={bedrockRegion}
                  onChange={(e) => upd(setBedrockRegion)(e.target.value)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                >
                  {BEDROCK_REGIONS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">AWS Profile</label>
                <input
                  type="text"
                  value={bedrockAwsProfile}
                  onChange={(e) => upd(setBedrockAwsProfile)(e.target.value)}
                  placeholder="default (uses environment credentials)"
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs text-tc-tertiary mb-1">Model</label>
                <div className="flex gap-2">
                  <select
                    value={bedrockModelId}
                    onChange={(e) => upd(setBedrockModelId)(e.target.value)}
                    className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                  >
                    {bedrockModels.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={async () => {
                      setRefreshingModels(true);
                      try {
                        const fetched = await fetchBedrockModels();
                        if (fetched.length > 0) {
                          const merged = [...BEDROCK_MODELS];
                          for (const m of fetched) {
                            if (!merged.some((e) => e.id === m.id)) {
                              merged.push(m);
                            }
                          }
                          setBedrockModels(merged);
                          if (!merged.some((m) => m.id === bedrockModelId)) {
                            upd(setBedrockModelId)(merged[0].id);
                          }
                        }
                      } catch {
                        // keep existing list on failure
                      } finally {
                        setRefreshingModels(false);
                      }
                    }}
                    disabled={refreshingModels}
                    className="px-3 py-2 bg-tc-hover border border-tc-strong rounded text-xs text-tc-secondary hover:bg-tc-active disabled:opacity-50 transition-colors whitespace-nowrap"
                    title="Refresh model list from AWS"
                  >
                    {refreshingModels ? "..." : "Refresh"}
                  </button>
                </div>
                <p className="text-xs text-tc-muted mt-1 font-mono truncate">{bedrockModelId}</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-tc-muted">
              Enable to use AWS Bedrock as an AI provider. Requires AWS credentials configured on the host.
            </p>
          )}
        </div>

        <div className="border-t border-tc-subtle pt-5">
          <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-3">
            Image Generation
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Image Provider</label>
              <select
                value={imageProvider}
                onChange={(e) => {
                  upd(setImageProvider)(e.target.value);
                  upd(setImageModel)("");
                }}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {IMAGE_PROVIDER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            {(imageProvider === "bedrock" || (!imageProvider && provider === "bedrock")) && (
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Image Region Override</label>
                <select
                  value={bedrockImageRegion}
                  onChange={(e) => upd(setBedrockImageRegion)(e.target.value)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                >
                  <option value="">Same as Bedrock region ({bedrockRegion})</option>
                  {BEDROCK_REGIONS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <p className="text-xs text-tc-muted mt-1">
                  Some image models are only available in specific regions (e.g. Stability AI in us-west-2).
                </p>
              </div>
            )}
            <div className={(imageProvider === "bedrock" || (!imageProvider && provider === "bedrock")) ? "sm:col-span-2" : ""}>
              <label className="block text-xs text-tc-tertiary mb-1">Image Model</label>
              {(imageProvider === "openai" || (!imageProvider && provider === "openai")) ? (
                <select
                  value={imageModel}
                  onChange={(e) => upd(setImageModel)(e.target.value)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                >
                  <option value="">Default (GPT Image 1)</option>
                  {OPENAI_IMAGE_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              ) : (imageProvider === "bedrock" || (!imageProvider && provider === "bedrock")) ? (
                <div className="flex gap-2">
                  <select
                    value={imageModel}
                    onChange={(e) => upd(setImageModel)(e.target.value)}
                    className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
                  >
                    <option value="">Default (Nova Canvas)</option>
                    {bedrockImageModels.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={async () => {
                      setRefreshingImageModels(true);
                      try {
                        const fetched = await fetchBedrockImageModels();
                        if (fetched.length > 0) {
                          const merged = [...BEDROCK_IMAGE_MODELS];
                          for (const m of fetched) {
                            if (!merged.some((e) => e.id === m.id)) {
                              merged.push(m);
                            }
                          }
                          setBedrockImageModels(merged);
                          if (imageModel && !merged.some((m) => m.id === imageModel)) {
                            upd(setImageModel)("");
                          }
                        }
                      } catch {
                        // keep existing list on failure
                      } finally {
                        setRefreshingImageModels(false);
                      }
                    }}
                    disabled={refreshingImageModels}
                    className="px-3 py-2 bg-tc-hover border border-tc-strong rounded text-xs text-tc-secondary hover:bg-tc-active disabled:opacity-50 transition-colors whitespace-nowrap"
                    title="Refresh image model list from AWS"
                  >
                    {refreshingImageModels ? "..." : "Refresh"}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-tc-muted py-2">
                  Select OpenAI or Bedrock as image provider — Anthropic does not support image generation.
                </p>
              )}
            </div>
          </div>
          <p className="text-xs text-tc-muted mt-2">
            Choose a separate provider and model for image generation, independent of the text AI.
            Requires the selected provider's API key or credentials to be configured above.
          </p>
        </div>

        <p className="text-xs text-tc-muted">
          API keys are encrypted at rest. They never leave this device.
        </p>
      </div>
    </section>
  );
}

const POLLY_ENGINES = [
  { id: "long-form", label: "Long-form (best for narration)" },
  { id: "neural", label: "Neural" },
  { id: "generative", label: "Generative" },
];

function NarrationConfigSection() {
  const queryClient = useQueryClient();
  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });
  const { data: voices = [] } = useQuery<PollyVoice[]>({
    queryKey: ["polly-voices"],
    queryFn: listVoices,
    staleTime: Infinity,
  });

  const getVal = (key: string) => config.find((c) => c.key === key)?.value ?? "";

  const [enabled, setEnabled] = useState(false);
  const [region, setRegion] = useState("us-east-1");
  const [narratorVoice, setNarratorVoice] = useState("Ruth");
  const [engine, setEngine] = useState("long-form");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config.length > 0) {
      setEnabled(getVal("polly_enabled") === "true");
      setRegion(getVal("polly_region") || "us-east-1");
      setNarratorVoice(getVal("polly_narrator_voice") || "Ruth");
      setEngine(getVal("polly_engine") || "long-form");
      setDirty(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateConfig([
        { key: "polly_enabled", value: enabled ? "true" : "false" },
        { key: "polly_region", value: region },
        { key: "polly_narrator_voice", value: narratorVoice },
        { key: "polly_engine", value: engine },
      ]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] });
      setDirty(false);
    },
  });

  const upd = <T,>(setter: React.Dispatch<React.SetStateAction<T>>) =>
    (val: T) => { setter(val); setDirty(true); };

  const filteredVoices = voices.filter((v) => v.engines.includes(engine));

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Narration (Amazon Polly)</h2>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!dirty || saveMutation.isPending}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={14} />
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
      </div>

      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-5">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => upd(setEnabled)(e.target.checked)}
            className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
          />
          <div>
            <span className="text-sm text-tc-secondary">Enable narration</span>
            <p className="text-xs text-tc-muted mt-0.5">
              Use Amazon Polly to read scenes aloud with per-character voices.
              Requires AWS credentials configured on the host.
            </p>
          </div>
        </label>

        {enabled && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Region</label>
              <select
                value={region}
                onChange={(e) => upd(setRegion)(e.target.value)}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {BEDROCK_REGIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-tc-tertiary mb-1">Engine</label>
              <select
                value={engine}
                onChange={(e) => {
                  upd(setEngine)(e.target.value);
                  const newFiltered = voices.filter(
                    (v) => v.engines.includes(e.target.value)
                  );
                  if (!newFiltered.find((v) => v.id === narratorVoice)) {
                    upd(setNarratorVoice)(newFiltered[0]?.id ?? "Ruth");
                  }
                }}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {POLLY_ENGINES.map((e) => (
                  <option key={e.id} value={e.id}>{e.label}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-tc-tertiary mb-1">
                Default Narrator Voice
              </label>
              <select
                value={narratorVoice}
                onChange={(e) => upd(setNarratorVoice)(e.target.value)}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:border-tc-accent focus:outline-none"
              >
                {filteredVoices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} — {v.gender}, {v.language}
                  </option>
                ))}
              </select>
              <p className="text-xs text-tc-muted mt-1">
                Used for narration and characters without an assigned voice.
                Assign character voices in the Codex.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function Settings() {
  // Install-wide settings (profiles, fonts, AI and narration configuration,
  // Google Drive, backups) are administrator-only on the server; show them only
  // to administrators instead of letting every save fail with 403. In local
  // mode the single user is an administrator, so nothing is hidden.
  const { user: currentUser } = useAuth();
  const isAdmin = !!currentUser?.is_admin;

  const queryClient = useQueryClient();
  const { data: profiles = [] } = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const [showNew, setShowNew] = useState(false);
  const [newFormData, setNewFormData] = useState<ProfileFormData>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedBuiltin, setExpandedBuiltin] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (data: CreateProfile) => createProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setShowNew(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateProfile }) =>
      updateProfile(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const handleCreate = (form: ProfileFormData) => {
    const hasPageNumbers = form.footer_recto === "page_number" || form.footer_verso === "page_number"
      || form.header_recto === "page_number" || form.header_verso === "page_number";
    const payload: CreateProfile = {
      name: form.name,
      format: form.format,
      description: form.description || undefined,
      font_family: form.font_family || undefined,
      font_size: form.font_size || undefined,
      line_height: form.line_height,
      header_footer: form.header_footer,
      include_cover: form.include_cover,
      include_toc: form.include_toc,
      page_numbers: hasPageNumbers,
      page_numbers_start_at_content: form.page_numbers_start_at_content,
      header_recto: form.header_recto || undefined,
      header_verso: form.header_verso || undefined,
      header_position: form.header_position,
      footer_recto: form.footer_recto || undefined,
      footer_verso: form.footer_verso || undefined,
      footer_position: form.footer_position,
      header_font_family: form.header_font_family || undefined,
      header_font_size: form.header_font_size || undefined,
      header_font_weight: form.header_font_weight || undefined,
      header_from_edge: form.header_from_edge,
      footer_from_edge: form.footer_from_edge,
      front_matter_roman: form.front_matter_roman,
      text_align: form.text_align,
      chapter_font_family: form.chapter_font_family || undefined,
      chapter_font_size: form.chapter_font_size || undefined,
      chapter_font_weight: form.chapter_font_weight || undefined,
      chapter_align: form.chapter_align || undefined,
      chapter_sink: form.chapter_sink,
      chapters_start_recto: form.chapters_start_recto,
      back_matter_page_numbers: form.back_matter_page_numbers,
    };
    if (form.format === "pdf") {
      payload.page_width = form.page_width;
      payload.page_height = form.page_height;
      payload.margin_top = form.margin_top;
      payload.margin_bottom = form.margin_bottom;
      payload.margin_inner = form.margin_inner;
      payload.margin_outer = form.margin_outer;
    }
    createMutation.mutate(payload);
  };

  const handleUpdate = (id: string, form: ProfileFormData) => {
    const hasPageNumbers = form.footer_recto === "page_number" || form.footer_verso === "page_number"
      || form.header_recto === "page_number" || form.header_verso === "page_number";
    const data: UpdateProfile = {
      name: form.name,
      description: form.description || undefined,
      font_family: form.font_family || undefined,
      font_size: form.font_size || undefined,
      line_height: form.line_height,
      header_footer: form.header_footer,
      include_cover: form.include_cover,
      include_toc: form.include_toc,
      page_numbers: hasPageNumbers,
      page_numbers_start_at_content: form.page_numbers_start_at_content,
      header_recto: form.header_recto || null,
      header_verso: form.header_verso || null,
      header_position: form.header_position,
      footer_recto: form.footer_recto || null,
      footer_verso: form.footer_verso || null,
      footer_position: form.footer_position,
      header_font_family: form.header_font_family || null,
      header_font_size: form.header_font_size || null,
      header_font_weight: form.header_font_weight || null,
      header_from_edge: form.header_from_edge ?? null,
      footer_from_edge: form.footer_from_edge ?? null,
      front_matter_roman: form.front_matter_roman,
      text_align: form.text_align,
      chapter_font_family: form.chapter_font_family || null,
      chapter_font_size: form.chapter_font_size || null,
      chapter_font_weight: form.chapter_font_weight || null,
      chapter_align: form.chapter_align || null,
      chapter_sink: form.chapter_sink ?? null,
      chapters_start_recto: form.chapters_start_recto,
      back_matter_page_numbers: form.back_matter_page_numbers,
      page_width: form.page_width ?? null,
      page_height: form.page_height ?? null,
      margin_top: form.margin_top ?? null,
      margin_bottom: form.margin_bottom ?? null,
      margin_inner: form.margin_inner ?? null,
      margin_outer: form.margin_outer ?? null,
    };
    updateMutation.mutate({ id, data });
  };

  const handleDuplicate = (p: Profile) => {
    const form = profileToForm(p);
    form.name = `Copy of ${p.name}`;
    setNewFormData(form);
    setShowNew(true);
    setEditingId(null);
  };

  const handleNewProfile = () => {
    setNewFormData(EMPTY_FORM);
    setShowNew(true);
    setEditingId(null);
  };

  const builtinProfiles = profiles.filter((p) => p.is_builtin);
  const customProfiles = profiles.filter((p) => !p.is_builtin);

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Settings</h1>
      <p className="text-sm text-tc-muted mb-8">
        {isAdmin
          ? "Manage export profiles, reader profiles, and AI configuration."
          : "Manage your account and appearance. Install-wide settings are managed by an administrator."}
      </p>

      {isAdmin && (<>
      <section className="mb-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Export / Reader Profiles</h2>
          {!showNew && (
            <button
              onClick={handleNewProfile}
              className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} />
              New Profile
            </button>
          )}
        </div>

        {showNew && (
          <div className="mb-6">
            <ProfileForm
              initial={newFormData}
              onSave={handleCreate}
              onCancel={() => setShowNew(false)}
              saving={createMutation.isPending}
              isNew
            />
          </div>
        )}

        {builtinProfiles.length > 0 && (
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-3">
              Built-in Profiles
            </h3>
            <div className="grid gap-3">
              {builtinProfiles.map((p) => {
                const expanded = expandedBuiltin === p.id;
                return (
                  <div
                    key={p.id}
                    className="p-4 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50 group"
                  >
                    <button
                      onClick={() => setExpandedBuiltin(expanded ? null : p.id)}
                      className="flex items-center justify-between w-full text-left"
                    >
                      <div className="flex items-center gap-3">
                        {expanded ? (
                          <ChevronDown size={16} className="text-tc-muted" />
                        ) : (
                          <ChevronRight size={16} className="text-tc-muted" />
                        )}
                        <div>
                          <span className="text-sm font-medium text-tc-secondary">
                            {p.name}
                          </span>
                          <span className="text-xs text-tc-muted ml-2">
                            {p.format.toUpperCase()}
                          </span>
                          {p.description && (
                            <p className="text-xs text-tc-muted mt-0.5">
                              {p.description}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          onClick={(e) => { e.stopPropagation(); handleDuplicate(p); }}
                          className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                          title="Duplicate as custom profile"
                        >
                          <Copy size={14} />
                        </span>
                        <span className="text-xs text-tc-muted">Built-in</span>
                      </div>
                    </button>
                    {expanded && <ProfileDetails profile={p} />}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-tc-muted uppercase tracking-wide mb-3">
            Custom Profiles
          </h3>
          {customProfiles.length === 0 && !showNew && (
            <p className="text-sm text-tc-muted py-4">
              No custom profiles yet. Create one or duplicate a built-in profile to get started.
            </p>
          )}
          <div className="grid gap-3">
            {customProfiles.map((p) =>
              editingId === p.id ? (
                <ProfileForm
                  key={p.id}
                  initial={profileToForm(p)}
                  onSave={(form) => handleUpdate(p.id, form)}
                  onCancel={() => setEditingId(null)}
                  saving={updateMutation.isPending}
                  isNew={false}
                />
              ) : (
                <div
                  key={p.id}
                  className="flex items-center justify-between p-4 bg-tc-overlay/50 rounded-lg border border-tc-subtle/50 group"
                >
                  <div className="flex items-center gap-3">
                    <BookOpen size={16} className="text-tc-muted" />
                    <div>
                      <span className="text-sm font-medium text-tc-secondary">
                        {p.name}
                      </span>
                      <span className="text-xs text-tc-muted ml-2">
                        {p.format.toUpperCase()}
                      </span>
                      {p.description && (
                        <p className="text-xs text-tc-muted mt-0.5">
                          {p.description}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all">
                    <button
                      onClick={() => handleDuplicate(p)}
                      className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
                      title="Duplicate"
                    >
                      <Copy size={14} />
                    </button>
                    <button
                      onClick={() => { setEditingId(p.id); setShowNew(false); }}
                      className="p-1.5 text-tc-muted hover:text-tc-secondary rounded transition-colors"
                      title="Edit"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete profile "${p.name}"?`)) {
                          deleteMutation.mutate(p.id);
                        }
                      }}
                      className="p-1.5 text-tc-muted hover:text-tc-error rounded transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </section>

      </>)}

      <AccountSection />
      <UsersSection />
      <ThemeSection />
      {isAdmin && (
        <>
          <FontsSection />
          <EditorConfigSection />
          <AIConfigSection />
          <NarrationConfigSection />
          <GoogleDriveSection />
          <BackupRestoreSection />
        </>
      )}
    </div>
  );
}

/** Extract a readable message from an axios error, falling back to a default. */
function apiError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
    ?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function AccountSection() {
  const { user, authMode } = useAuth();
  const sso = authMode === "proxy";
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: () => changeMyPassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      setError(null);
      setDone(true);
    },
    onError: (err) => {
      setDone(false);
      setError(apiError(err, "Could not change the password."));
    },
  });

  const mismatch = confirm.length > 0 && next !== confirm;
  const tooShort = next.length > 0 && next.length < 8;
  const canSubmit =
    current.length > 0 && next.length >= 8 && next === confirm && !mutation.isPending;

  return (
    <section className="mb-10">
      <div className="flex items-center gap-2 mb-4">
        <KeyRound size={18} className="text-tc-muted" />
        <h2 className="text-lg font-semibold">Account</h2>
      </div>
      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-4">
        <p className="text-xs text-tc-muted">
          Signed in{sso && " with single sign-on"} as{" "}
          <span className="text-tc-secondary">{user?.email}</span>
          {user?.is_admin && " (administrator)"}
        </p>
        {sso && (
          <p className="text-xs text-tc-muted">
            Your password is managed by your organisation&apos;s sign-in, not by Typecast.
          </p>
        )}

        {!sso && <form
          className="space-y-3 max-w-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) mutation.mutate();
          }}
        >
          <div>
            <label className="block text-xs text-tc-muted mb-1">Current password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="w-full px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-tc-muted mb-1">New password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="w-full px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
            {tooShort && (
              <p className="text-xs text-tc-error mt-1">Use at least 8 characters.</p>
            )}
          </div>
          <div>
            <label className="block text-xs text-tc-muted mb-1">Confirm new password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
            {mismatch && (
              <p className="text-xs text-tc-error mt-1">Passwords do not match.</p>
            )}
          </div>

          {error && <p className="text-xs text-tc-error">{error}</p>}
          {done && <p className="text-xs text-tc-success">Password changed.</p>}

          <button
            type="submit"
            disabled={!canSubmit}
            className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
          >
            <Save size={14} />
            {mutation.isPending ? "Changing..." : "Change password"}
          </button>
        </form>}
      </div>
    </section>
  );
}

/**
 * Admin-only account management. Self-service signup is disabled on the server,
 * so this is the only way accounts are created after the first admin.
 */
function UsersSection() {
  const { user, authMode } = useAuth();
  // Single sign-on: accounts link to a person's identity the first time they
  // sign in, matched by email, so there is no password to set or reset.
  const sso = authMode === "proxy";
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    email: "",
    username: "",
    display_name: "",
    password: "",
    is_admin: false,
  });

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
    enabled: !!user?.is_admin,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] });
  const fail = (fallback: string) => (err: unknown) => setError(apiError(err, fallback));

  const createMutation = useMutation({
    mutationFn: () => createUser(sso ? { ...form, password: undefined } : form),
    onSuccess: () => {
      invalidate();
      setShowCreate(false);
      setError(null);
      setForm({ email: "", username: "", display_name: "", password: "", is_admin: false });
    },
    onError: fail("Could not create the account."),
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Parameters<typeof updateUser>[1] }) =>
      updateUser(id, updates),
    onSuccess: () => {
      invalidate();
      setError(null);
    },
    onError: fail("Could not update the account."),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ id, purge }: { id: string; purge: boolean }) => deleteUser(id, purge),
    onSuccess: () => {
      invalidate();
      setError(null);
    },
    onError: fail("Could not delete the account."),
  });

  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      resetUserPassword(id, password),
    onSuccess: () => setError(null),
    onError: fail("Could not reset the password."),
  });

  // Hidden entirely for non-admins rather than shown disabled: the endpoints
  // return 403 and an empty table would just look broken.
  if (!user?.is_admin) return null;

  const handleDelete = (target: ManagedUser) => {
    if (!window.confirm(`Delete the account ${target.email}?`)) return;
    deleteMutation.mutate(
      { id: target.id, purge: false },
      {
        onError: (err) => {
          const detail = apiError(err, "Could not delete the account.");
          // The server refuses when the account owns content, because the
          // foreign keys cascade. Make the consequence explicit before retrying.
          if (detail.includes("purge=true")) {
            if (window.confirm(`${detail}\n\nPermanently delete the account AND its content?`)) {
              deleteMutation.mutate({ id: target.id, purge: true });
              return;
            }
            setError(null);
            return;
          }
          setError(detail);
        },
      }
    );
  };

  const handleReset = (target: ManagedUser) => {
    const password = window.prompt(`New password for ${target.email} (at least 8 characters):`);
    if (!password) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    resetMutation.mutate({ id: target.id, password });
  };

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users size={18} className="text-tc-muted" />
          <h2 className="text-lg font-semibold">Users</h2>
        </div>
        <button
          onClick={() => { setShowCreate((v) => !v); setError(null); }}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
        >
          <UserPlus size={14} />
          Add user
        </button>
      </div>

      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-4">
        <p className="text-xs text-tc-muted">
          {sso
            ? "Add people by the email they sign in with; their account links the first time they sign in. "
            : "Self-service registration is disabled, so accounts are created here. "}
          Deactivating an account revokes access immediately while keeping its work; deleting one
          destroys everything it owns.
        </p>

        {error && <p className="text-xs text-tc-error">{error}</p>}

        {showCreate && (
          <form
            className="grid grid-cols-2 gap-3 p-4 bg-tc-hover/40 border border-tc-subtle rounded-lg"
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
          >
            <input
              placeholder="Email"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
            <input
              placeholder="Username"
              required
              minLength={3}
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
            <input
              placeholder="Display name"
              required
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              className="px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
            />
            {!sso && (
              <input
                placeholder="Password (8+ characters)"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="px-3 py-2 bg-tc-hover border border-tc-strong rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-tc-accent"
              />
            )}
            <label className="col-span-2 flex items-center gap-2 text-sm text-tc-secondary">
              <input
                type="checkbox"
                checked={form.is_admin}
                onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent focus:ring-offset-0"
              />
              Administrator (can manage users)
            </label>
            <div className="col-span-2 flex gap-2">
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium"
              >
                {createMutation.isPending ? "Creating..." : "Create"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="px-3 py-2 bg-tc-hover hover:bg-tc-overlay rounded-lg text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {isLoading ? (
          <p className="text-sm text-tc-muted">Loading...</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-tc-muted border-b border-tc-subtle">
                <th className="pb-2 font-medium">User</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-tc-subtle/50 last:border-0">
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-tc-secondary">{u.display_name}</span>
                      {u.is_admin && (
                        <span title="Administrator">
                          <Shield size={12} className="text-tc-accent" />
                        </span>
                      )}
                      {u.id === user?.id && (
                        <span className="text-xs text-tc-muted">(you)</span>
                      )}
                    </div>
                    <div className="text-xs text-tc-muted">
                      {u.email} &middot; @{u.username}
                    </div>
                  </td>
                  <td className="py-3">
                    <span
                      className={
                        u.is_active ? "text-xs text-tc-success" : "text-xs text-tc-error"
                      }
                    >
                      {u.is_active ? "Active" : "Disabled"}
                    </span>
                    {sso && !u.sso_linked && (
                      <div className="text-xs text-tc-muted">Not signed in yet</div>
                    )}
                  </td>
                  <td className="py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() =>
                          patchMutation.mutate({ id: u.id, updates: { is_admin: !u.is_admin } })
                        }
                        className="px-2 py-1 bg-tc-hover hover:bg-tc-overlay rounded text-xs"
                      >
                        {u.is_admin ? "Revoke admin" : "Make admin"}
                      </button>
                      <button
                        onClick={() =>
                          patchMutation.mutate({ id: u.id, updates: { is_active: !u.is_active } })
                        }
                        className="px-2 py-1 bg-tc-hover hover:bg-tc-overlay rounded text-xs"
                      >
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                      {!sso && (
                        <button
                          onClick={() => handleReset(u)}
                          title="Set a new password"
                          className="p-1 text-tc-muted hover:text-tc-secondary rounded"
                        >
                          <KeyRound size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(u)}
                        title="Delete account"
                        className="p-1 text-tc-muted hover:text-tc-error rounded"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function GoogleDriveSection() {
  const queryClient = useQueryClient();
  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: listConfig,
  });
  const { data: status } = useQuery({
    queryKey: ["gdrive", "status"],
    queryFn: getDriveStatus,
  });

  const getVal = (key: string) => config.find((c) => c.key === key)?.value ?? "";

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (config.length > 0) {
      setClientId(getVal("gdrive_client_id"));
      setClientSecret(getVal("gdrive_client_secret"));
      setDirty(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateConfig([
        { key: "gdrive_client_id", value: clientId },
        { key: "gdrive_client_secret", value: clientSecret, is_secret: true },
      ]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.invalidateQueries({ queryKey: ["gdrive", "status"] });
      setDirty(false);
    },
  });

  const handleConnect = async () => {
    setMessage(null);
    try {
      const { auth_url } = await getDriveAuthUrl();
      // Consent happens in a popup; Google redirects back to the callback route,
      // which closes the tab itself. Poll status so the UI catches up.
      window.open(auth_url, "_blank", "width=520,height=680");
      const poll = setInterval(async () => {
        const next = await queryClient.fetchQuery({
          queryKey: ["gdrive", "status"],
          queryFn: getDriveStatus,
        });
        if (next.connected) {
          clearInterval(poll);
          setMessage({ type: "success", text: "Google Drive connected." });
        }
      }, 2000);
      // Give up polling after two minutes so it doesn't run forever.
      setTimeout(() => clearInterval(poll), 120_000);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMessage({ type: "error", text: detail || "Could not start authorisation." });
    }
  };

  const disconnectMutation = useMutation({
    mutationFn: disconnectDrive,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gdrive", "status"] });
      queryClient.invalidateQueries({ queryKey: ["config"] });
      setMessage({ type: "success", text: "Google Drive disconnected." });
    },
  });

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cloud size={18} className="text-tc-tertiary" />
          <h2 className="text-lg font-semibold">Google Drive</h2>
        </div>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!dirty || saveMutation.isPending}
          className="flex items-center gap-2 px-3 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
      </div>

      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-4">
        <p className="text-sm text-tc-tertiary">
          Send exports to your own Google Drive. Word, HTML, text, and Markdown exports can be
          converted into native Google Docs so a reader can comment on them in the browser.
        </p>

        <div className="flex items-center gap-2 text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              status?.connected ? "bg-tc-success" : "bg-tc-muted"
            }`}
          />
          {status?.connected ? (
            <span className="text-tc-secondary">
              Connected{status.account_email ? ` as ${status.account_email}` : ""}
            </span>
          ) : status?.configured ? (
            <span className="text-tc-tertiary">Credentials saved, not yet authorised</span>
          ) : (
            <span className="text-tc-tertiary">Not configured</span>
          )}
        </div>

        {status?.error && <p className="text-sm text-tc-error">{status.error}</p>}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm text-tc-secondary mb-1.5">Client ID</label>
            <input
              type="text"
              value={clientId}
              onChange={(e) => { setClientId(e.target.value); setDirty(true); }}
              placeholder="xxxxx.apps.googleusercontent.com"
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
            />
          </div>
          <div>
            <label className="block text-sm text-tc-secondary mb-1.5">Client Secret</label>
            <input
              type="password"
              value={clientSecret}
              onChange={(e) => { setClientSecret(e.target.value); setDirty(true); }}
              placeholder="GOCSPX-..."
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleConnect}
            disabled={!status?.configured || dirty}
            className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
            title={dirty ? "Save your credentials first" : undefined}
          >
            <Cloud size={14} />
            {status?.connected ? "Reconnect" : "Connect Google Drive"}
          </button>
          {status?.connected && (
            <button
              onClick={() => disconnectMutation.mutate()}
              disabled={disconnectMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors"
            >
              {disconnectMutation.isPending ? "Disconnecting..." : "Disconnect"}
            </button>
          )}
        </div>

        {message && (
          <p className={`text-sm ${message.type === "success" ? "text-tc-success" : "text-tc-error"}`}>
            {message.text}
          </p>
        )}

        <details className="text-xs text-tc-muted">
          <summary className="cursor-pointer hover:text-tc-tertiary">Setup steps</summary>
          <ol className="mt-2 space-y-1 list-decimal list-inside leading-relaxed">
            <li>
              In the{" "}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noreferrer"
                className="text-tc-accent hover:underline"
              >
                Google Cloud console
              </a>
              , create a project and enable the Google Drive API.
            </li>
            <li>Create an OAuth client of type "Web application".</li>
            <li>
              Add this authorised redirect URI:{" "}
              <code className="text-tc-tertiary">{status?.redirect_uri ?? ""}</code>
            </li>
            <li>Paste the client ID and secret above, save, then Connect.</li>
          </ol>
          <p className="mt-2 leading-relaxed">
            Typecast requests only the <code className="text-tc-tertiary">drive.file</code> scope, so
            it can see nothing in your Drive except the files it creates. Publish the OAuth app
            (rather than leaving it in Testing) or Google will expire the authorisation every 7 days.
            Running with <code className="text-tc-tertiary">--ssl</code> changes the redirect URI, so
            register both the http and https forms if you use both modes.
          </p>
        </details>
      </div>
    </section>
  );
}

function ThemeSection() {
  const { config, setPreset, setMode, setOverrides } = useTheme();
  const [customAccent, setCustomAccent] = useState(config.overrides?.accentBase || "");

  const handleAccentChange = (color: string) => {
    setCustomAccent(color);
    if (color) {
      setOverrides({ accentBase: color, accentHover: color });
    } else {
      setOverrides(undefined);
    }
  };

  return (
    <section className="mb-10">
      <div className="flex items-center gap-2 mb-4">
        <Palette size={18} className="text-tc-tertiary" />
        <h2 className="text-lg font-semibold">Theme</h2>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-tc-secondary mb-2">Preset</label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {themes.map((t) => (
              <button
                key={t.id}
                onClick={() => setPreset(t.id)}
                className={`relative px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                  config.presetId === t.id
                    ? "border-tc-accent bg-tc-accent-subtle text-tc-primary"
                    : "border-tc-subtle bg-tc-overlay text-tc-secondary hover:border-tc-strong"
                }`}
              >
                <div className="flex items-center gap-2">
                  <div className="flex gap-0.5">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: t.dark.bgPage }} />
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: t.dark.accentBase }} />
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: t.light.bgPage, border: "1px solid #ccc" }} />
                  </div>
                  {t.name}
                </div>
                {config.presetId === t.id && (
                  <Check size={14} className="absolute top-1 right-1 text-tc-accent" />
                )}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm text-tc-secondary mb-2">Mode</label>
          <div className="flex gap-2">
            <button
              onClick={() => setMode("dark")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
                config.mode === "dark"
                  ? "border-tc-accent bg-tc-accent-subtle text-tc-primary"
                  : "border-tc-subtle bg-tc-overlay text-tc-secondary hover:border-tc-strong"
              }`}
            >
              <Moon size={14} />
              Dark
            </button>
            <button
              onClick={() => setMode("light")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
                config.mode === "light"
                  ? "border-tc-accent bg-tc-accent-subtle text-tc-primary"
                  : "border-tc-subtle bg-tc-overlay text-tc-secondary hover:border-tc-strong"
              }`}
            >
              <Sun size={14} />
              Light
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm text-tc-secondary mb-2">Custom accent color</label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={customAccent || config.mode === "dark" ? themes.find(t => t.id === config.presetId)?.dark.accentBase || "#4f46e5" : themes.find(t => t.id === config.presetId)?.light.accentBase || "#4f46e5"}
              onChange={(e) => handleAccentChange(e.target.value)}
              className="w-8 h-8 rounded cursor-pointer border border-tc-subtle"
            />
            {customAccent && (
              <button
                onClick={() => handleAccentChange("")}
                className="text-xs text-tc-tertiary hover:text-tc-secondary"
              >
                Reset to default
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/** "3 works, 42 chapters, 121 scenes" from a load summary, biggest things first. */
function describeRows(rows: Record<string, number>): string {
  const labels: [string, string][] = [
    ["works", "work"], ["series", "series"], ["chapters", "chapter"], ["scenes", "scene"],
    ["codex_entries", "codex entry"], ["images", "image"], ["conversations", "conversation"],
  ];
  const parts = labels
    .filter(([table]) => (rows[table] ?? 0) > 0)
    .map(([table, noun]) => {
      const n = rows[table];
      const plural = n === 1 || noun === "series" ? noun : noun.replace(/y$/, "ie") + "s";
      return `${n} ${plural}`;
    });
  return parts.length ? parts.join(", ") : "nothing";
}

function BackupRestoreSection() {
  const queryClient = useQueryClient();
  const [downloading, setDownloading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const importRef = useRef<HTMLInputElement>(null);

  const handleBackup = async () => {
    setDownloading(true);
    setMessage(null);
    try {
      await downloadBackup();
      setMessage({ type: "success", text: "Backup downloaded." });
    } catch (err) {
      setMessage({ type: "error", text: apiError(err, "Failed to create backup.") });
    } finally {
      setDownloading(false);
    }
  };

  const handleRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm(
      "Restore replaces ALL data on this server, including every account, with the " +
      "backup's contents. Anything not in the backup is lost.\n\n" +
      "To bring works from another install into this one, use Import instead.\n\nContinue?"
    )) {
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setRestoring(true);
    setMessage(null);
    try {
      const result = await restoreBackup(file);
      const dropped = result.secrets_dropped
        ? ` ${result.secrets_dropped} stored API key(s) were encrypted by a different ` +
          "server and were not restored; re-enter them below."
        : "";
      setMessage({ type: "success", text: `${result.message ?? "Restored."}${dropped}` });
    } catch (err) {
      // The server explains refusals (wrong format, newer schema, a single-user
      // backup on a multi-user server), so show its reason rather than a guess.
      setMessage({ type: "error", text: apiError(err, "Failed to restore backup.") });
    } finally {
      setRestoring(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (importRef.current) importRef.current.value = "";
    if (!file) return;
    setImporting(true);
    setMessage(null);
    try {
      // Check first, so the confirmation can say exactly what will arrive.
      const preview = await importBackup(file, true);
      const conflicts = preview.file_conflicts.length
        ? `\n\n${preview.file_conflicts.length} file(s) already exist here with different ` +
          "contents and will be left as they are."
        : "";
      if (!confirm(
        `Import ${describeRows(preview.rows)} into your account?` +
        "\n\nYour existing works are not changed. Accounts, stored API keys, and the " +
        "Google Drive connection are not imported; set those up on this server." +
        conflicts
      )) {
        return;
      }
      const result = await importBackup(file);
      // New works, profiles, and fonts: every cached list is now stale.
      await queryClient.invalidateQueries();
      setMessage({
        type: "success",
        text:
          `Imported ${describeRows(result.rows)} and ${result.files_written} file(s). ` +
          "Re-enter any API keys this server needs below.",
      });
    } catch (err) {
      setMessage({ type: "error", text: apiError(err, "Import failed.") });
    } finally {
      setImporting(false);
    }
  };

  const busy = downloading || restoring || importing;

  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold mb-4">Backup & Restore</h2>
      <div className="bg-tc-overlay/50 border border-tc-subtle rounded-lg p-6 space-y-4">
        <p className="text-sm text-tc-tertiary">
          Download everything on this server (works, settings, images, and AI conversations) as
          a ZIP file. Backups work with either database, so one taken from a SQLite install can
          be loaded into a PostgreSQL one and the other way round.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleBackup}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
          >
            <Download size={14} />
            {downloading ? "Creating backup..." : "Download Backup"}
          </button>
          <label
            title="Add a backup's works to your account, keeping everything already here"
            className={`flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors ${busy ? "opacity-50 pointer-events-none" : "cursor-pointer"}`}
          >
            <Upload size={14} />
            {importing ? "Importing..." : "Import into my account"}
            <input
              ref={importRef}
              type="file"
              accept=".zip"
              onChange={handleImport}
              className="hidden"
              disabled={busy}
            />
          </label>
          <label
            title="Replace everything on this server with a backup"
            className={`flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors ${busy ? "opacity-50 pointer-events-none" : "cursor-pointer"}`}
          >
            <RotateCcw size={14} />
            {restoring ? "Restoring..." : "Restore from Backup"}
            <input
              ref={fileRef}
              type="file"
              accept=".zip"
              onChange={handleRestore}
              className="hidden"
              disabled={busy}
            />
          </label>
        </div>
        {message && (
          <p className={`text-sm whitespace-pre-line ${message.type === "success" ? "text-tc-success" : "text-tc-error"}`}>
            {message.text}
          </p>
        )}
        <div className="text-xs text-tc-muted space-y-1">
          <p>
            <span className="text-tc-secondary">Import</span> adds a backup&apos;s works to your
            account and leaves everything else alone. Use it to move works from one install to
            another.
          </p>
          <p>
            <span className="text-tc-secondary">Restore</span> replaces everything on this
            server, accounts included, with the backup. Use it to recover this install from its
            own backup.
          </p>
          <p>
            API keys travel only in encrypted form, which another server cannot read, so
            re-enter them after moving to a new install.
          </p>
        </div>

        <DriveBackupPanel />
      </div>
    </section>
  );
}

/** Push backups to Google Drive and restore from them. Hidden until Drive is connected. */
function DriveBackupPanel() {
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["gdrive", "status"],
    queryFn: getDriveStatus,
    staleTime: 60_000,
  });
  const connected = status?.connected ?? false;

  // Retention deletes archives from Drive, so it is opt-in and off by default.
  const [prune, setPrune] = useState(false);
  const [keep, setKeep] = useState(5);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const { data: backups = [], isFetching: loadingBackups } = useQuery({
    queryKey: ["gdrive", "backups"],
    queryFn: listDriveBackups,
    enabled: connected,
  });

  const backupMutation = useMutation({
    mutationFn: () => backupToDrive(prune ? keep : undefined),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["gdrive", "backups"] });
      const pruned = result.pruned.length
        ? ` ${result.pruned.length} older backup${result.pruned.length === 1 ? "" : "s"} removed.`
        : "";
      setMessage({
        type: "success",
        text: `Uploaded ${result.name} (${formatBytes(result.size)}).${pruned}`,
      });
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMessage({ type: "error", text: detail || "Backup to Drive failed." });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (fileId: string) => restoreFromDrive(fileId),
    onSuccess: (result) => setMessage({ type: "success", text: result.message }),
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMessage({ type: "error", text: detail || "Restore from Drive failed." });
    },
  });

  const handleRestore = (fileId: string, name: string) => {
    // Unrecoverable, so the archive name goes in the prompt to make the user
    // check they picked the one they meant.
    if (
      !confirm(
        `Restore ${name}?\n\nThis replaces ALL local data (works, settings, images) with the ` +
          `contents of this backup. Anything written since it was taken is lost.`
      )
    ) {
      return;
    }
    setMessage(null);
    restoreMutation.mutate(fileId);
  };

  if (!connected) {
    return (
      <p className="text-xs text-tc-muted border-t border-tc-subtle pt-4">
        Connect Google Drive above to keep off-machine copies of your backups.
      </p>
    );
  }

  return (
    <div className="border-t border-tc-subtle pt-4 space-y-3">
      <div className="flex items-center gap-2">
        <Cloud size={14} className="text-tc-tertiary" />
        <h3 className="text-sm font-medium text-tc-secondary">Google Drive</h3>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => { setMessage(null); backupMutation.mutate(); }}
          disabled={backupMutation.isPending || restoreMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Cloud size={14} />
          {backupMutation.isPending ? "Uploading..." : "Back up to Drive"}
        </button>

        <label className="flex items-center gap-2 text-xs text-tc-tertiary">
          <input
            type="checkbox"
            checked={prune}
            onChange={(e) => setPrune(e.target.checked)}
            className="accent-tc-accent"
          />
          Keep only the newest
          <input
            type="number"
            min={1}
            max={100}
            value={keep}
            disabled={!prune}
            onChange={(e) => setKeep(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
            className="w-14 bg-tc-hover border border-tc-strong rounded px-2 py-1 text-xs disabled:opacity-50 focus:outline-none focus:border-tc-accent"
          />
          <span>backups</span>
        </label>
      </div>

      {prune && (
        <p className="text-xs text-tc-warning">
          Older backups beyond {keep} will be deleted from Drive after the upload succeeds.
        </p>
      )}

      {message && (
        <p className={`text-sm ${message.type === "success" ? "text-tc-success" : "text-tc-error"}`}>
          {message.text}
        </p>
      )}

      <div>
        <p className="text-xs text-tc-muted mb-2">
          {loadingBackups
            ? "Loading backups..."
            : backups.length === 0
              ? "No backups in Drive yet."
              : `${backups.length} backup${backups.length === 1 ? "" : "s"} in Drive`}
        </p>
        {backups.length > 0 && (
          <ul className="space-y-1 max-h-52 overflow-y-auto">
            {backups.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between gap-3 bg-tc-hover/50 rounded px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs text-tc-secondary truncate">{b.name}</p>
                  <p className="text-[11px] text-tc-muted">
                    {b.size !== null ? formatBytes(b.size) : "unknown size"}
                  </p>
                </div>
                <button
                  onClick={() => handleRestore(b.id, b.name)}
                  disabled={restoreMutation.isPending || backupMutation.isPending}
                  className="flex items-center gap-1.5 px-2.5 py-1 bg-tc-hover hover:bg-tc-active disabled:opacity-50 rounded text-xs transition-colors shrink-0"
                >
                  <RotateCcw size={12} />
                  Restore
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
