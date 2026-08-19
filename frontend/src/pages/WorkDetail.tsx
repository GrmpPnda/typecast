import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft, FileText, Settings, BookOpen, Trash2, BookOpenCheck,
  ChevronUp, ChevronDown, ChevronRight, ImagePlus, X, Download, Layers,
  Cloud, ExternalLink,
} from "lucide-react";
import { getWork } from "@/api/works";
import { uploadCover, deleteCover, setCoverFromImage } from "@/api/uploads";
import CoverPicker from "@/components/CoverPicker";
import { listChapters, createChapter, deleteChapter, reorderChapters } from "@/api/chapters";
import { createScene } from "@/api/scenes";
import { listSections, deleteSection } from "@/api/sections";
import { listProfiles } from "@/api/profiles";
import { exportWork } from "@/api/export";
import {
  getDriveStatus,
  exportWorkToDrive,
  CONVERTIBLE_FORMATS,
  DriveExportResult,
} from "@/api/gdrive";
import { Chapter, SectionType, Profile } from "@/types";
import { useState, useCallback } from "react";
import ImageGallery from "@/components/ImageGallery";

const MATTER_TITLES = new Set([
  "dedication", "preface", "foreword", "introduction", "prologue",
  "epilogue", "afterword", "acknowledgments", "acknowledgements",
  "appendix", "glossary", "bibliography", "about the author",
  "also by", "colophon", "copyright", "half title", "title page",
]);

function isMatter(ch: Chapter): boolean {
  return MATTER_TITLES.has((ch.title ?? "").toLowerCase().trim());
}

const FRONT_MATTER_TITLES = [
  "Half Title", "Title Page", "Copyright", "Dedication", "Epigraph",
  "Table of Contents", "Foreword", "Preface", "Acknowledgments",
  "Introduction", "Prologue",
];

const BACK_MATTER_TITLES = [
  "Epilogue", "Afterword", "Acknowledgments", "Appendix", "Glossary",
  "Bibliography", "Index", "About the Author", "Also By", "Colophon",
];

const FRONT_MATTER_SET = new Set(FRONT_MATTER_TITLES.map((t) => t.toLowerCase()));
const BACK_MATTER_SET = new Set(BACK_MATTER_TITLES.map((t) => t.toLowerCase()));

function classifyMatter(ch: Chapter): "front" | "back" | "body" {
  const title = (ch.title ?? "").toLowerCase().trim();
  if (FRONT_MATTER_SET.has(title)) return "front";
  if (BACK_MATTER_SET.has(title)) return "back";
  return "body";
}

const FRONT_MATTER_TYPES: { value: SectionType; label: string }[] = [
  { value: "half_title", label: "Half Title" },
  { value: "title_page", label: "Title Page" },
  { value: "copyright", label: "Copyright" },
  { value: "dedication", label: "Dedication" },
  { value: "epigraph", label: "Epigraph" },
  { value: "table_of_contents", label: "Table of Contents" },
  { value: "foreword", label: "Foreword" },
  { value: "preface", label: "Preface" },
  { value: "acknowledgments_front", label: "Acknowledgments" },
  { value: "introduction", label: "Introduction" },
  { value: "prologue", label: "Prologue" },
];

const BACK_MATTER_TYPES: { value: SectionType; label: string }[] = [
  { value: "epilogue", label: "Epilogue" },
  { value: "afterword", label: "Afterword" },
  { value: "acknowledgments_back", label: "Acknowledgments" },
  { value: "appendix", label: "Appendix" },
  { value: "glossary", label: "Glossary" },
  { value: "bibliography", label: "Bibliography" },
  { value: "index", label: "Index" },
  { value: "about_author", label: "About the Author" },
  { value: "also_by", label: "Also By" },
  { value: "colophon", label: "Colophon" },
];

function SectionBlock({
  title,
  icon,
  onAdd,
  addLabel,
  showAdd = true,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  onAdd?: () => void;
  addLabel?: string;
  showAdd?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(true);
  return (
    <section className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-semibold text-tc-tertiary uppercase tracking-wide hover:text-tc-secondary transition-colors"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {icon}
          {title}
        </button>
        {showAdd && onAdd && (
          <button
            onClick={onAdd}
            className="text-xs text-tc-muted hover:text-tc-secondary transition-colors"
          >
            {addLabel}
          </button>
        )}
      </div>
      {expanded && children}
    </section>
  );
}

const POS_LABELS: Record<string, string> = {
  center: "Center", left: "Left", right: "Right", outside: "Outside (alternating)",
};

const HF_CONTENT_LABELS: Record<string, string> = {
  "": "None", title: "Book Title", author: "Author", chapter: "Chapter Number",
  chapter_title: "Chapter Title",
};

const HF_POS_LABELS: Record<string, string> = {
  center: "Center", outer: "Outside (alternating)",
};

function ExportProfileDetails({ profile: p }: { profile: Profile }) {
  const [open, setOpen] = useState(false);
  const isPdf = p.format === "pdf";
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-tc-muted hover:text-tc-secondary transition-colors"
      >
        <ChevronDown size={12} className={`transition-transform ${open ? "" : "-rotate-90"}`} />
        Profile details
      </button>
      {open && (
        <div className="mt-2 p-3 bg-tc-hover/40 rounded border border-tc-subtle/50 grid gap-x-6 gap-y-0 sm:grid-cols-2 text-xs">
          <div>
            <span className="text-tc-muted">Font:</span>{" "}
            <span className="text-tc-secondary">{p.font_family}</span>
          </div>
          <div>
            <span className="text-tc-muted">Size:</span>{" "}
            <span className="text-tc-secondary">{p.font_size}</span>
          </div>
          <div>
            <span className="text-tc-muted">Line Height:</span>{" "}
            <span className="text-tc-secondary">{p.line_height}</span>
          </div>
          {isPdf && (
            <div>
              <span className="text-tc-muted">Text Align:</span>{" "}
              <span className="text-tc-secondary">{{ justify: "Justified", left: "Left", right: "Right", center: "Center" }[p.text_align] ?? p.text_align}</span>
            </div>
          )}
          {isPdf && p.page_width != null && (
            <div>
              <span className="text-tc-muted">Page:</span>{" "}
              <span className="text-tc-secondary">{p.page_width}&times;{p.page_height} in</span>
            </div>
          )}
          {isPdf && p.margin_top != null && (
            <div>
              <span className="text-tc-muted">Margins:</span>{" "}
              <span className="text-tc-secondary">
                {p.margin_top}/{p.margin_bottom}/{p.margin_inner}/{p.margin_outer} in
              </span>
            </div>
          )}
          <div>
            <span className="text-tc-muted">Cover:</span>{" "}
            <span className="text-tc-secondary">{p.include_cover ? "Yes" : "No"}</span>
          </div>
          <div>
            <span className="text-tc-muted">TOC:</span>{" "}
            <span className="text-tc-secondary">{p.include_toc ? "Yes" : "No"}</span>
          </div>
          {isPdf && (
            <div>
              <span className="text-tc-muted">Page Numbers:</span>{" "}
              <span className="text-tc-secondary">
                {p.page_numbers
                  ? `${POS_LABELS[p.page_number_position] ?? p.page_number_position}${p.page_numbers_start_at_content ? ", start at content" : ""}`
                  : "Off"}
              </span>
            </div>
          )}
          {isPdf && p.chapters_start_recto && (
            <div>
              <span className="text-tc-muted">Chapters:</span>{" "}
              <span className="text-tc-secondary">Start on right page</span>
            </div>
          )}
          {isPdf && (p.header_recto || p.header_verso) && (
            <div className="sm:col-span-2">
              <span className="text-tc-muted">Headers:</span>{" "}
              <span className="text-tc-secondary">
                {[
                  p.header_recto && `Recto: ${HF_CONTENT_LABELS[p.header_recto] ?? p.header_recto}`,
                  p.header_verso && `Verso: ${HF_CONTENT_LABELS[p.header_verso] ?? p.header_verso}`,
                ].filter(Boolean).join(", ")}
                {` (${HF_POS_LABELS[p.header_position] ?? p.header_position})`}
              </span>
            </div>
          )}
          {isPdf && (p.footer_recto || p.footer_verso) && (
            <div className="sm:col-span-2">
              <span className="text-tc-muted">Footers:</span>{" "}
              <span className="text-tc-secondary">
                {[
                  p.footer_recto && `Recto: ${HF_CONTENT_LABELS[p.footer_recto] ?? p.footer_recto}`,
                  p.footer_verso && `Verso: ${HF_CONTENT_LABELS[p.footer_verso] ?? p.footer_verso}`,
                ].filter(Boolean).join(", ")}
                {` (${HF_POS_LABELS[p.footer_position] ?? p.footer_position})`}
              </span>
            </div>
          )}
          {isPdf && (
            <div className="sm:col-span-2">
              <span className="text-tc-muted">Chapter Headings:</span>{" "}
              <span className="text-tc-secondary">
                {p.chapter_font_family || "body font"}, {p.chapter_font_size || "1.4em"}, {p.chapter_font_weight || "normal"}, {
                  { center: "centered", left: "left", right: "right" }[p.chapter_align ?? "center"] ?? p.chapter_align
                }{p.chapter_sink != null ? `, sink ${p.chapter_sink}em` : ""}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function WorkDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showNewChapter, setShowNewChapter] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [showAddFrontMatter, setShowAddFrontMatter] = useState(false);
  const [showAddBackMatter, setShowAddBackMatter] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [exportFormat, setExportFormat] = useState("pdf");
  const [exportProfileId, setExportProfileId] = useState<string>("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [includeImages, setIncludeImages] = useState(false);
  const [compressImages, setCompressImages] = useState(false);
  const [showCoverPreview, setShowCoverPreview] = useState(false);
  const [convertToDoc, setConvertToDoc] = useState(true);
  // Drive destination. Both empty means the Typecast folder root and a filename
  // derived from the work title.
  const [driveFolderPath, setDriveFolderPath] = useState("");
  const [driveFilename, setDriveFilename] = useState("");
  const [drivePending, setDrivePending] = useState(false);
  const [driveResult, setDriveResult] = useState<DriveExportResult | null>(null);

  const { data: work } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const { data: chapters = [] } = useQuery({
    queryKey: ["chapters", { workId: id }],
    queryFn: () => listChapters(id!),
    enabled: !!id,
  });

  const { data: sections = [] } = useQuery({
    queryKey: ["sections", { workId: id }],
    queryFn: () => listSections(id!),
    enabled: !!id,
  });

  const { data: profiles = [] } = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  // Only fetched while the export panel is open; the Drive button stays hidden
  // until the integration is actually connected in Settings.
  const { data: driveStatus } = useQuery({
    queryKey: ["gdrive", "status"],
    queryFn: getDriveStatus,
    enabled: showExport,
    staleTime: 60_000,
  });

  const createChapterMutation = useMutation({
    mutationFn: createChapter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", { workId: id }] });
      setShowNewChapter(false);
      setNewTitle("");
    },
  });

  const deleteChapterMutation = useMutation({
    mutationFn: deleteChapter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", { workId: id }] });
    },
  });

  const HIDE_TITLE_MATTER = new Set(["title page", "copyright", "dedication", "half title"]);

  const createMatterMutation = useMutation({
    mutationFn: async (title: string) => {
      const hideTitle = HIDE_TITLE_MATTER.has(title.toLowerCase());
      const chapter = await createChapter({
        work_id: id!,
        title,
        show_title: !hideTitle,
      });
      await createScene({ chapter_id: chapter.id, sort_order: 0 });
      return chapter;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", { workId: id }] });
      setShowAddFrontMatter(false);
      setShowAddBackMatter(false);
    },
  });

  const deleteSectionMutation = useMutation({
    mutationFn: deleteSection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sections", { workId: id }] });
    },
  });

  const [showCoverPicker, setShowCoverPicker] = useState(false);

  const uploadCoverMutation = useMutation({
    mutationFn: (file: File) => uploadCover(id!, file),
    onSuccess: (data) => {
      const bustUrl = `${data.cover_image_path}?t=${Date.now()}`;
      queryClient.setQueryData(["work", id], (old: any) =>
        old ? { ...old, cover_image_path: bustUrl } : old
      );
      queryClient.invalidateQueries({ queryKey: ["works"] });
    },
  });

  const setCoverFromImageMutation = useMutation({
    mutationFn: (imageUrl: string) => setCoverFromImage(id!, imageUrl),
    onSuccess: (data) => {
      const bustUrl = `${data.cover_image_path}?t=${Date.now()}`;
      queryClient.setQueryData(["work", id], (old: any) =>
        old ? { ...old, cover_image_path: bustUrl } : old
      );
      queryClient.invalidateQueries({ queryKey: ["works"] });
      setShowCoverPicker(false);
    },
  });

  const deleteCoverMutation = useMutation({
    mutationFn: () => deleteCover(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", id] });
      queryClient.invalidateQueries({ queryKey: ["works"] });
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (items: { id: string; sort_order: number; number?: number | null }[]) =>
      reorderChapters(id!, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", { workId: id }] });
    },
  });

  const moveChapter = useCallback(
    (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= chapters.length) return;

      const movingChapter = chapters[index];
      const targetChapter = chapters[target];
      const movingIsMatter = isMatter(movingChapter);
      const targetIsMatter = isMatter(targetChapter);

      if (
        !movingIsMatter &&
        !targetIsMatter &&
        !confirm(
          "Reordering chapters will re-number them to match their new positions. Existing chapter titles will be preserved. Continue?"
        )
      ) {
        return;
      }

      const reordered = [...chapters];
      [reordered[index], reordered[target]] = [reordered[target], reordered[index]];

      let chapterNum = 1;
      const items = reordered.map((ch, i) => {
        const matter = isMatter(ch);
        const num = matter ? ch.number : chapterNum++;
        return { id: ch.id, sort_order: i, number: num };
      });

      reorderMutation.mutate(items);
    },
    [chapters, reorderMutation]
  );

  const moveMatterChapter = useCallback(
    (group: Chapter[], index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= group.length) return;
      const a = group[index];
      const b = group[target];
      const reordered = [...chapters];
      const ai = reordered.findIndex((ch) => ch.id === a.id);
      const bi = reordered.findIndex((ch) => ch.id === b.id);
      if (ai === -1 || bi === -1) return;
      [reordered[ai], reordered[bi]] = [reordered[bi], reordered[ai]];
      let chapterNum = 1;
      const items = reordered.map((ch, i) => ({
        id: ch.id,
        sort_order: i,
        number: isMatter(ch) ? ch.number : chapterNum++,
      }));
      reorderMutation.mutate(items);
    },
    [chapters, reorderMutation]
  );

  const handleExport = useCallback(async () => {
    if (!id) return;
    setExporting(true);
    setExportError("");
    try {
      const profileParam = (exportFormat === "pdf" || exportFormat === "epub" || exportFormat === "docx") ? exportProfileId || undefined : undefined;
      const imagesParam = (exportFormat === "markdown") ? includeImages : undefined;
      const compressParam = (exportFormat === "epub") ? compressImages : undefined;
      const blob = await exportWork(id, exportFormat, profileParam, imagesParam || undefined, compressParam || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const ext = exportFormat === "markdown" ? "md" : exportFormat;
      a.href = url;
      a.download = `${work?.title || "export"}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setExportError("Export failed. Check that the backend is running and try again.");
    } finally {
      setExporting(false);
    }
  }, [id, exportFormat, exportProfileId, includeImages, compressImages, work?.title]);

  const handleSendToDrive = useCallback(async () => {
    if (!id) return;
    setDrivePending(true);
    setExportError("");
    setDriveResult(null);
    try {
      const usesProfile =
        exportFormat === "pdf" || exportFormat === "epub" || exportFormat === "docx";
      const result = await exportWorkToDrive(id, {
        format: exportFormat,
        profile_id: usesProfile ? exportProfileId || undefined : undefined,
        include_images: exportFormat === "markdown" ? includeImages : undefined,
        compress_images: exportFormat === "epub" ? compressImages : undefined,
        convert_to_google_doc: convertToDoc,
        folder_path: driveFolderPath.trim() || undefined,
        filename: driveFilename.trim() || undefined,
      });
      setDriveResult(result);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setExportError(detail || "Upload to Google Drive failed. Check Settings and try again.");
    } finally {
      setDrivePending(false);
    }
  }, [
    id,
    exportFormat,
    exportProfileId,
    includeImages,
    compressImages,
    convertToDoc,
    driveFolderPath,
    driveFilename,
  ]);

  const frontMatterChapters = chapters.filter((ch) => classifyMatter(ch) === "front");
  const backMatterChapters = chapters.filter((ch) => classifyMatter(ch) === "back");
  const bodyChapters = chapters.filter((ch) => classifyMatter(ch) === "body");

  const frontMatterSections = sections.filter((s) => s.placement === "front_matter");
  const backMatterSections = sections.filter((s) => s.placement === "back_matter");

  if (!work) return null;

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-6 text-sm"
      >
        <ArrowLeft size={16} />
        Back to Library
      </Link>

      <div className="flex gap-6 mb-8">
        <div className="shrink-0">
          {work.cover_image_path ? (
            <div className="relative group">
              <img
                src={work.cover_image_path}
                alt="Cover"
                onClick={() => setShowCoverPreview(true)}
                className="w-32 h-48 object-cover rounded-lg shadow-lg cursor-pointer"
              />
              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowCoverPicker(true); }}
                  className="p-2 bg-tc-hover rounded-full text-tc-secondary hover:bg-tc-active transition-colors"
                  title="Change cover"
                >
                  <ImagePlus size={16} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("Remove cover image?")) deleteCoverMutation.mutate();
                  }}
                  className="p-2 bg-tc-hover rounded-full text-tc-error hover:bg-tc-active transition-colors"
                  title="Remove cover"
                >
                  <X size={16} />
                </button>
              </div>
              {showCoverPreview && (
                <div
                  className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
                  onClick={() => setShowCoverPreview(false)}
                >
                  <img
                    src={work.cover_image_path}
                    alt="Cover preview"
                    className="max-h-[90vh] max-w-[90vw] object-contain rounded-lg shadow-2xl"
                    onClick={(e) => e.stopPropagation()}
                  />
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={() => setShowCoverPicker(true)}
              className="w-32 h-48 border-2 border-dashed border-tc-subtle rounded-lg flex flex-col items-center justify-center text-tc-muted hover:border-tc-strong hover:text-tc-tertiary transition-colors"
            >
              <ImagePlus size={24} className="mb-1" />
              <span className="text-xs">Add Cover</span>
            </button>
          )}
          {showCoverPicker && (
            <CoverPicker
              workId={id!}
              onSelectImage={(url) => setCoverFromImageMutation.mutate(url)}
              onUpload={(file) => {
                uploadCoverMutation.mutate(file);
                setShowCoverPicker(false);
              }}
              onClose={() => setShowCoverPicker(false)}
            />
          )}
        </div>
        <div className="flex-1 flex flex-col">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-2xl font-bold">{work.title}</h1>
              {work.author && (
                <p className="text-tc-tertiary text-sm mt-1">by {work.author}</p>
              )}
              {work.description && (
                <p className="text-tc-muted text-sm mt-1 line-clamp-2">{work.description}</p>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <Link
                to={`/work/${id}/settings`}
                className="p-2 text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay rounded-lg transition-colors"
                title="Settings"
              >
                <Settings size={18} />
              </Link>
              <Link
                to={`/work/${id}/read`}
                className="p-2 text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay rounded-lg transition-colors"
                title="Read"
              >
                <BookOpenCheck size={18} />
              </Link>
              <Link
                to={`/work/${id}/cover`}
                className="p-2 text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay rounded-lg transition-colors"
                title="Cover Production"
              >
                <Layers size={18} />
              </Link>
              <button
                onClick={() => setShowExport(!showExport)}
                className={`p-2 rounded-lg transition-colors ${
                  showExport
                    ? "bg-tc-accent text-tc-primary"
                    : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay"
                }`}
                title="Export"
              >
                <Download size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {showExport && (
        <div className="mb-6 p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-tc-secondary flex items-center gap-2">
              <Download size={14} />
              Export Work
            </h3>
            <button
              onClick={() => setShowExport(false)}
              className="text-tc-muted hover:text-tc-secondary transition-colors"
            >
              <X size={16} />
            </button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-tc-tertiary mb-1.5">Format</label>
              <select
                value={exportFormat}
                onChange={(e) => {
                  setExportFormat(e.target.value);
                  setExportProfileId("");
                }}
                className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
              >
                <option value="pdf">PDF</option>
                <option value="epub">ePub</option>
                <option value="docx">Word (.docx)</option>
                <option value="markdown">Markdown</option>
                <option value="html">HTML</option>
                <option value="txt">Plain Text</option>
              </select>
            </div>
            {(exportFormat === "pdf" || exportFormat === "epub" || exportFormat === "docx") && (
              <div>
                <label className="block text-xs text-tc-tertiary mb-1.5">Profile</label>
                <select
                  value={exportProfileId}
                  onChange={(e) => setExportProfileId(e.target.value)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                >
                  <option value="">Default</option>
                  {profiles
                    .filter((p) => p.format === (exportFormat === "docx" ? "pdf" : exportFormat))
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} {p.is_builtin ? "(built-in)" : ""}
                      </option>
                    ))}
                </select>
              </div>
            )}
          </div>
          {exportProfileId && (() => {
            const p = profiles.find((pr) => pr.id === exportProfileId);
            if (!p) return null;
            return <ExportProfileDetails profile={p} />;
          })()}
          {exportFormat === "markdown" && (
            <label className="mt-3 flex items-center gap-2 text-sm text-tc-tertiary cursor-pointer">
              <input
                type="checkbox"
                checked={includeImages}
                onChange={(e) => setIncludeImages(e.target.checked)}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent"
              />
              Include image tags
            </label>
          )}
          {exportFormat === "epub" && (
            <label className="mt-3 flex items-center gap-2 text-sm text-tc-tertiary cursor-pointer">
              <input
                type="checkbox"
                checked={compressImages}
                onChange={(e) => setCompressImages(e.target.checked)}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent"
              />
              Compress images (keeps ePub under 20 MB)
            </label>
          )}
          {driveStatus?.connected && CONVERTIBLE_FORMATS.has(exportFormat) && (
            <label className="mt-3 flex items-center gap-2 text-sm text-tc-tertiary cursor-pointer">
              <input
                type="checkbox"
                checked={convertToDoc}
                onChange={(e) => setConvertToDoc(e.target.checked)}
                className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent"
              />
              Convert to a Google Doc when sending to Drive
            </label>
          )}
          {driveStatus?.connected && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1.5">
                  Drive folder
                </label>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-tc-muted shrink-0">Typecast /</span>
                  <input
                    type="text"
                    value={driveFolderPath}
                    onChange={(e) => setDriveFolderPath(e.target.value)}
                    placeholder="(top level)"
                    className="w-full bg-tc-hover border border-tc-strong rounded px-2 py-1.5 text-xs focus:outline-none focus:border-tc-accent"
                  />
                </div>
                <p className="mt-1 text-[11px] text-tc-muted">
                  Subfolders are created if they do not exist. Use / to nest.
                </p>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1.5">
                  File name
                </label>
                <input
                  type="text"
                  value={driveFilename}
                  onChange={(e) => setDriveFilename(e.target.value)}
                  placeholder={work.title}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-2 py-1.5 text-xs focus:outline-none focus:border-tc-accent"
                />
                <p className="mt-1 text-[11px] text-tc-muted">
                  Defaults to the work title. The extension is added for you.
                </p>
              </div>
            </div>
          )}
          {exportError && (
            <p className="mt-3 text-sm text-tc-error">{exportError}</p>
          )}
          {driveResult && (
            <div className="mt-3 flex items-center gap-2 text-sm text-tc-secondary">
              <Cloud size={14} className="text-tc-success shrink-0" />
              <span>
                Sent <span className="font-medium">{driveResult.name}</span> to Typecast
                {driveResult.folder_path ? ` / ${driveResult.folder_path}` : ""} in Google Drive.
              </span>
              {driveResult.web_view_link && (
                <a
                  href={driveResult.web_view_link}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-tc-accent hover:underline"
                >
                  Open
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              onClick={handleExport}
              disabled={exporting || drivePending}
              className="flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
            >
              {exporting ? (
                <>Exporting...</>
              ) : (
                <>
                  <Download size={14} />
                  Export {{ pdf: "PDF", epub: "ePub", docx: "Word", markdown: "Markdown", html: "HTML", txt: "Plain Text" }[exportFormat]}
                </>
              )}
            </button>
            {driveStatus?.connected && (
              <button
                onClick={handleSendToDrive}
                disabled={exporting || drivePending}
                className="flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active border border-tc-strong text-tc-secondary disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
                title={
                  driveStatus.account_email
                    ? `Upload to ${driveStatus.account_email}`
                    : "Upload to Google Drive"
                }
              >
                <Cloud size={14} />
                {drivePending ? "Sending..." : "Send to Google Drive"}
              </button>
            )}
          </div>
        </div>
      )}

      <ImageGallery workId={id!} />

      <SectionBlock
        title="Front Matter"
        icon={<BookOpen size={14} />}
        onAdd={() => setShowAddFrontMatter(true)}
        addLabel="+ Add"
        showAdd={!showAddFrontMatter}
      >
        {showAddFrontMatter && (
          <div className="mb-2 p-3 bg-tc-overlay rounded-lg flex items-center gap-2">
            <select
              className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-1.5 text-sm focus:border-tc-accent focus:outline-none"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) createMatterMutation.mutate(e.target.value);
              }}
            >
              <option value="" disabled>Select type...</option>
              {FRONT_MATTER_TITLES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              onClick={() => setShowAddFrontMatter(false)}
              className="px-2 py-1.5 text-sm text-tc-tertiary hover:text-tc-secondary"
            >
              Cancel
            </button>
          </div>
        )}
        <div className="grid gap-2">
          {frontMatterChapters.map((ch, idx) => (
            <div
              key={ch.id}
              onClick={() => navigate(`/work/${id}/chapter/${ch.id}`)}
              className="flex items-center justify-between p-3 bg-tc-overlay/60 rounded border border-tc-subtle/50 text-sm group hover:border-tc-strong transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <BookOpen size={14} className="text-tc-muted" />
                <span className="text-tc-secondary">{ch.title}</span>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={(e) => { e.stopPropagation(); moveMatterChapter(frontMatterChapters, idx, -1); }}
                  disabled={idx === 0 || reorderMutation.isPending}
                  className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); moveMatterChapter(frontMatterChapters, idx, 1); }}
                  disabled={idx === frontMatterChapters.length - 1 || reorderMutation.isPending}
                  className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${ch.title}"?`)) deleteChapterMutation.mutate(ch.id);
                  }}
                  className="text-tc-muted hover:text-tc-error p-0.5"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {frontMatterSections.map((s) => (
            <Link
              key={s.id}
              to={`/work/${id}/section/${s.id}`}
              className="flex items-center justify-between p-3 bg-tc-overlay/60 rounded border border-tc-subtle/50 text-sm group hover:border-tc-strong transition-colors"
            >
              <div className="flex items-center gap-3">
                <BookOpen size={14} className="text-tc-muted" />
                <span className="text-tc-secondary">
                  {s.title || FRONT_MATTER_TYPES.find((t) => t.value === s.section_type)?.label || s.section_type}
                </span>
              </div>
              <button
                onClick={(e) => { e.preventDefault(); deleteSectionMutation.mutate(s.id); }}
                className="text-tc-muted hover:text-tc-error opacity-0 group-hover:opacity-100 transition-all"
              >
                <Trash2 size={14} />
              </button>
            </Link>
          ))}
        </div>
      </SectionBlock>

      <SectionBlock
        title="Chapters"
        icon={<FileText size={14} />}
        onAdd={() => setShowNewChapter(true)}
        addLabel="+ Add"
        showAdd={!showNewChapter}
      >
        {showNewChapter && (
          <div className="mb-2 p-3 bg-tc-overlay rounded-lg">
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Chapter title..."
              className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-tc-accent"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={() =>
                  createChapterMutation.mutate({
                    work_id: id!,
                    title: newTitle,
                  })
                }
                disabled={!newTitle.trim()}
                className="px-3 py-1.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded text-sm font-medium transition-colors"
              >
                Create
              </button>
              <button
                onClick={() => {
                  setShowNewChapter(false);
                  setNewTitle("");
                }}
                className="px-3 py-1.5 bg-tc-hover hover:bg-tc-active rounded text-sm font-medium transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        <div className="grid gap-3">
          {bodyChapters.map((chapter, index) => (
            <div
              key={chapter.id}
              className="flex items-center justify-between p-4 bg-tc-overlay rounded-lg border border-tc-subtle group"
            >
              <Link
                to={`/work/${id}/chapter/${chapter.id}`}
                className="flex items-center gap-4 flex-1 hover:text-tc-primary transition-colors"
              >
                <span className="text-tc-muted text-sm font-mono w-8">
                  {String(chapter.number ?? index + 1).padStart(2, "0")}
                </span>
                <FileText size={18} className="text-tc-muted" />
                <h3 className="font-medium">
                  {chapter.title || `Chapter ${chapter.number ?? index + 1}`}
                </h3>
              </Link>
              <div className="flex items-center gap-1">
                <div className="flex flex-col opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={() => {
                      const fullIndex = chapters.indexOf(chapter);
                      moveChapter(fullIndex, -1);
                    }}
                    disabled={chapters.indexOf(chapter) === 0 || reorderMutation.isPending}
                    className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    onClick={() => {
                      const fullIndex = chapters.indexOf(chapter);
                      moveChapter(fullIndex, 1);
                    }}
                    disabled={chapters.indexOf(chapter) === chapters.length - 1 || reorderMutation.isPending}
                    className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                  >
                    <ChevronDown size={14} />
                  </button>
                </div>
                <button
                  onClick={() => {
                    if (confirm(`Delete "${chapter.title || "this chapter"}" and all its scenes?`)) {
                      deleteChapterMutation.mutate(chapter.id);
                    }
                  }}
                  className="text-tc-muted hover:text-tc-error opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
        {bodyChapters.length === 0 && !showNewChapter && (
          <div className="text-center py-8 text-tc-muted">
            <FileText size={32} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm">No chapters yet.</p>
          </div>
        )}
      </SectionBlock>

      <SectionBlock
        title="Back Matter"
        icon={<BookOpen size={14} />}
        onAdd={() => setShowAddBackMatter(true)}
        addLabel="+ Add"
        showAdd={!showAddBackMatter}
      >
        {showAddBackMatter && (
          <div className="mb-2 p-3 bg-tc-overlay rounded-lg flex items-center gap-2">
            <select
              className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-1.5 text-sm focus:border-tc-accent focus:outline-none"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) createMatterMutation.mutate(e.target.value);
              }}
            >
              <option value="" disabled>Select type...</option>
              {BACK_MATTER_TITLES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              onClick={() => setShowAddBackMatter(false)}
              className="px-2 py-1.5 text-sm text-tc-tertiary hover:text-tc-secondary"
            >
              Cancel
            </button>
          </div>
        )}
        <div className="grid gap-2">
          {backMatterChapters.map((ch, idx) => (
            <div
              key={ch.id}
              onClick={() => navigate(`/work/${id}/chapter/${ch.id}`)}
              className="flex items-center justify-between p-3 bg-tc-overlay/60 rounded border border-tc-subtle/50 text-sm group hover:border-tc-strong transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <BookOpen size={14} className="text-tc-muted" />
                <span className="text-tc-secondary">{ch.title}</span>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={(e) => { e.stopPropagation(); moveMatterChapter(backMatterChapters, idx, -1); }}
                  disabled={idx === 0 || reorderMutation.isPending}
                  className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); moveMatterChapter(backMatterChapters, idx, 1); }}
                  disabled={idx === backMatterChapters.length - 1 || reorderMutation.isPending}
                  className="text-tc-muted hover:text-tc-secondary disabled:opacity-20 p-0.5"
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${ch.title}"?`)) deleteChapterMutation.mutate(ch.id);
                  }}
                  className="text-tc-muted hover:text-tc-error p-0.5"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {backMatterSections.map((s) => (
            <Link
              key={s.id}
              to={`/work/${id}/section/${s.id}`}
              className="flex items-center justify-between p-3 bg-tc-overlay/60 rounded border border-tc-subtle/50 text-sm group hover:border-tc-strong transition-colors"
            >
              <div className="flex items-center gap-3">
                <BookOpen size={14} className="text-tc-muted" />
                <span className="text-tc-secondary">
                  {s.title || BACK_MATTER_TYPES.find((t) => t.value === s.section_type)?.label || s.section_type}
                </span>
              </div>
              <button
                onClick={(e) => { e.preventDefault(); deleteSectionMutation.mutate(s.id); }}
                className="text-tc-muted hover:text-tc-error opacity-0 group-hover:opacity-100 transition-all"
              >
                <Trash2 size={14} />
              </button>
            </Link>
          ))}
        </div>
      </SectionBlock>

    </div>
  );
}
