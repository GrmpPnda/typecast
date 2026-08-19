import { useState, useCallback, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, ChevronDown, Download, RefreshCw, Image as ImageIcon, Type, Palette,
} from "lucide-react";
import { getWork } from "@/api/works";
import { listImages } from "@/api/images";
import { listFonts } from "@/api/fonts";
import { getProfile } from "@/api/profiles";
import {
  getCoverDimensions,
  previewCover,
  downloadCover,
  CoverDimensions,
  CoverGenerateRequest,
} from "@/api/cover";
import FontSelect, { useFontFaceStyles } from "@/components/FontSelect";

const TRIM_PRESETS = [
  { label: '5" × 8"', w: 5, h: 8 },
  { label: '5.25" × 8"', w: 5.25, h: 8 },
  { label: '5.5" × 8.5"', w: 5.5, h: 8.5 },
  { label: '6" × 9"', w: 6, h: 9 },
  { label: '6.14" × 9.21"', w: 6.14, h: 9.21 },
  { label: '7" × 10"', w: 7, h: 10 },
  { label: '8.5" × 11"', w: 8.5, h: 11 },
];

export default function CoverProduction() {
  const { id } = useParams<{ id: string }>();

  const { data: work } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const { data: images = [] } = useQuery({
    queryKey: ["images", { workId: id }],
    queryFn: () => listImages(id!),
    enabled: !!id,
  });

  const { data: fonts = [] } = useQuery({
    queryKey: ["fonts"],
    queryFn: listFonts,
  });

  useFontFaceStyles(fonts);

  const { data: defaultProfile } = useQuery({
    queryKey: ["profile", work?.default_profile_id],
    queryFn: () => getProfile(work!.default_profile_id!),
    enabled: !!work?.default_profile_id,
  });

  const [trimWidth, setTrimWidth] = useState(6);
  const [trimHeight, setTrimHeight] = useState(9);
  const [pageCount, setPageCount] = useState(300);
  const [spineFactor, setSpineFactor] = useState(0.0025);
  const [coverType, setCoverType] = useState<"paperback" | "hardcover">("paperback");
  const [flapWidth, setFlapWidth] = useState(3.5);
  const [spineText, setSpineText] = useState("");
  const [backBlurb, setBackBlurb] = useState("");
  const [bgColor, setBgColor] = useState("#1a1a2e");
  const [textColor, setTextColor] = useState("#FFFFFF");
  const [spineFontFamily, setSpineFontFamily] = useState("");
  const [blurbFontFamily, setBlurbFontFamily] = useState("");
  const [barcodeZone, setBarcodeZone] = useState(true);
  const [backTitle, setBackTitle] = useState("");
  const [backOverlayOpacity, setBackOverlayOpacity] = useState(180);
  const [frontImagePath, setFrontImagePath] = useState<string | null>(null);
  const [backImagePath, setBackImagePath] = useState<string | null>(null);
  const [backLogoPath, setBackLogoPath] = useState<string | null>(null);
  const [backWebsite, setBackWebsite] = useState("");
  const [frontFlapText, setFrontFlapText] = useState("");
  const [backFlapText, setBackFlapText] = useState("");
  const [outputFormat, setOutputFormat] = useState<"pdf" | "docx" | "png">("pdf");
  const [showFormatMenu, setShowFormatMenu] = useState(false);
  const [showImagePicker, setShowImagePicker] = useState<"front" | "back" | "logo" | null>(null);

  const [dims, setDims] = useState<CoverDimensions | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);

  useEffect(() => {
    if (work) {
      if (!spineText) setSpineText(work.title);
      if (!backTitle) setBackTitle(work.title);
      if (!backBlurb && work.blurb) setBackBlurb(work.blurb);
      if (!backWebsite && work.website) setBackWebsite(work.website);
      if (!frontImagePath && work.cover_image_path) setFrontImagePath(work.cover_image_path);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [work]);

  useEffect(() => {
    if (defaultProfile) {
      if (!spineFontFamily && defaultProfile.font_family) setSpineFontFamily(defaultProfile.font_family);
      if (!blurbFontFamily && defaultProfile.font_family) setBlurbFontFamily(defaultProfile.font_family);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultProfile]);

  useEffect(() => {
    getCoverDimensions(trimWidth, trimHeight, pageCount, spineFactor, coverType, flapWidth).then(setDims);
  }, [trimWidth, trimHeight, pageCount, spineFactor, coverType, flapWidth]);

  const requestBody = useMemo((): CoverGenerateRequest => ({
    trim_width: trimWidth,
    trim_height: trimHeight,
    page_count: pageCount,
    spine_factor: spineFactor,
    cover_type: coverType,
    flap_width: flapWidth,
    front_image_path: frontImagePath,
    back_image_path: backImagePath,
    spine_text: spineText,
    back_title: backTitle,
    back_blurb: backBlurb,
    background_color: bgColor,
    text_color: textColor,
    spine_font_family: spineFontFamily || null,
    blurb_font_family: blurbFontFamily || null,
    barcode_zone: barcodeZone,
    back_overlay_opacity: backOverlayOpacity,
    back_logo_path: backLogoPath,
    back_website: backWebsite,
    front_flap_text: frontFlapText,
    back_flap_text: backFlapText,
  }), [trimWidth, trimHeight, pageCount, spineFactor, coverType, flapWidth, frontImagePath, backImagePath, spineText, backTitle, backBlurb, bgColor, textColor, spineFontFamily, blurbFontFamily, barcodeZone, backOverlayOpacity, backLogoPath, backWebsite, frontFlapText, backFlapText]);

  const handlePreview = useCallback(async () => {
    if (!id) return;
    setGenerating(true);
    try {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const url = await previewCover(id, requestBody);
      setPreviewUrl(url);
    } finally {
      setGenerating(false);
    }
  }, [id, requestBody, previewUrl]);

  const handleDownload = useCallback(async (fmt: "pdf" | "docx" | "png" = outputFormat) => {
    if (!id || !work) return;
    setDownloading(true);
    try {
      const blob = await downloadCover(id, { ...requestBody, output_format: fmt });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${work.title || "cover"}_full_cover.${fmt}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }, [id, work, requestBody, outputFormat]);

  const handlePresetChange = useCallback((w: number, h: number) => {
    setTrimWidth(w);
    setTrimHeight(h);
  }, []);

  const currentPreset = TRIM_PRESETS.find((p) => p.w === trimWidth && p.h === trimHeight);

  if (!work) return null;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <Link
        to={`/work/${id}`}
        className="inline-flex items-center gap-2 text-tc-tertiary hover:text-tc-secondary mb-6 text-sm"
      >
        <ArrowLeft size={16} />
        Back to {work.title}
      </Link>

      <h1 className="text-2xl font-bold mb-6">Cover Production</h1>

      <div className="grid lg:grid-cols-[400px_1fr] gap-8">
        {/* Controls Panel */}
        <div className="space-y-6">
          {/* Trim Size */}
          <section className="p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
            <h3 className="text-sm font-semibold text-tc-secondary mb-3 flex items-center gap-2">
              <Type size={14} />
              Page Dimensions
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Trim Size Preset</label>
                <select
                  value={currentPreset ? `${currentPreset.w}x${currentPreset.h}` : "custom"}
                  onChange={(e) => {
                    if (e.target.value === "custom") return;
                    const [w, h] = e.target.value.split("x").map(Number);
                    handlePresetChange(w, h);
                  }}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                >
                  {TRIM_PRESETS.map((p) => (
                    <option key={`${p.w}x${p.h}`} value={`${p.w}x${p.h}`}>{p.label}</option>
                  ))}
                  {!currentPreset && <option value="custom">Custom</option>}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-tc-tertiary mb-1">Width (in)</label>
                  <input
                    type="number"
                    step="0.25"
                    min="4"
                    max="12"
                    value={trimWidth}
                    onChange={(e) => setTrimWidth(parseFloat(e.target.value) || 6)}
                    className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                  />
                </div>
                <div>
                  <label className="block text-xs text-tc-tertiary mb-1">Height (in)</label>
                  <input
                    type="number"
                    step="0.25"
                    min="5"
                    max="14"
                    value={trimHeight}
                    onChange={(e) => setTrimHeight(parseFloat(e.target.value) || 9)}
                    className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Page Count</label>
                <input
                  type="number"
                  step="1"
                  min="24"
                  max="2000"
                  value={pageCount}
                  onChange={(e) => setPageCount(parseInt(e.target.value) || 300)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                />
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">
                  Spine Factor (in/page)
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0.001"
                  max="0.005"
                  value={spineFactor}
                  onChange={(e) => setSpineFactor(parseFloat(e.target.value) || 0.0025)}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                />
                <p className="text-xs text-tc-muted mt-1">B&N Press default: 0.0025</p>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Cover Type</label>
                <select
                  value={coverType}
                  onChange={(e) => setCoverType(e.target.value as "paperback" | "hardcover")}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                >
                  <option value="paperback">Paperback</option>
                  <option value="hardcover">Hardcover (Dust Jacket)</option>
                </select>
              </div>
              {coverType === "hardcover" && (
                <div>
                  <label className="block text-xs text-tc-tertiary mb-1">Flap Width (in)</label>
                  <input
                    type="number"
                    step="0.25"
                    min="2"
                    max="6"
                    value={flapWidth}
                    onChange={(e) => setFlapWidth(parseFloat(e.target.value) || 3.5)}
                    className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                  />
                  <p className="text-xs text-tc-muted mt-1">Standard: 3.5"</p>
                </div>
              )}
            </div>
          </section>

          {/* Calculated Dimensions */}
          {dims && (
            <section className="p-4 bg-tc-overlay/60 rounded-lg border border-tc-subtle/50">
              <h3 className="text-sm font-semibold text-tc-secondary mb-2">Calculated Dimensions</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div>
                  <span className="text-tc-muted">Spine width:</span>{" "}
                  <span className="text-tc-secondary">{dims.spine_width.toFixed(3)}"</span>
                </div>
                <div>
                  <span className="text-tc-muted">Bleed:</span>{" "}
                  <span className="text-tc-secondary">{dims.bleed}"</span>
                </div>
                <div>
                  <span className="text-tc-muted">Total width:</span>{" "}
                  <span className="text-tc-secondary">{dims.total_width.toFixed(3)}"</span>
                </div>
                <div>
                  <span className="text-tc-muted">Total height:</span>{" "}
                  <span className="text-tc-secondary">{dims.total_height.toFixed(3)}"</span>
                </div>
                <div className="col-span-2">
                  <span className="text-tc-muted">Pixels:</span>{" "}
                  <span className="text-tc-secondary">{dims.total_width_px} × {dims.total_height_px} @ 300dpi</span>
                </div>
              </div>
            </section>
          )}

          {/* Cover Images */}
          <section className="p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
            <h3 className="text-sm font-semibold text-tc-secondary mb-3 flex items-center gap-2">
              <ImageIcon size={14} />
              Cover Images
            </h3>
            <div className="space-y-3">
              <ImageSelector
                label="Front Cover"
                currentPath={frontImagePath}
                coverPath={work.cover_image_path}
                allImages={images.map((i) => ({ url: i.url, name: i.original_name }))}
                onSelect={setFrontImagePath}
                isOpen={showImagePicker === "front"}
                onToggle={() => setShowImagePicker(showImagePicker === "front" ? null : "front")}
              />
              <ImageSelector
                label="Back Cover"
                currentPath={backImagePath}
                coverPath={work.cover_image_path}
                allImages={images.map((i) => ({ url: i.url, name: i.original_name }))}
                onSelect={setBackImagePath}
                isOpen={showImagePicker === "back"}
                onToggle={() => setShowImagePicker(showImagePicker === "back" ? null : "back")}
              />
              <ImageSelector
                label="Back Cover Logo"
                currentPath={backLogoPath}
                coverPath={null}
                allImages={images.map((i) => ({ url: i.url, name: i.original_name }))}
                onSelect={setBackLogoPath}
                isOpen={showImagePicker === "logo"}
                onToggle={() => setShowImagePicker(showImagePicker === "logo" ? null : "logo")}
                hint="Publisher/rating logo, bottom-left of back cover"
              />
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Website</label>
                <input
                  type="text"
                  value={backWebsite}
                  onChange={(e) => setBackWebsite(e.target.value)}
                  placeholder="yourwebsite.com"
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                />
                <p className="text-xs text-tc-muted mt-1">Displayed above logo on back cover</p>
              </div>
            </div>
          </section>

          {/* Text */}
          <section className="p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
            <h3 className="text-sm font-semibold text-tc-secondary mb-3 flex items-center gap-2">
              <Type size={14} />
              Text
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Spine Text</label>
                <input
                  type="text"
                  value={spineText}
                  onChange={(e) => setSpineText(e.target.value)}
                  placeholder={work.title}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                />
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Spine Font</label>
                <FontSelect
                  value={spineFontFamily}
                  onChange={setSpineFontFamily}
                  customFonts={fonts}
                  placeholder="Default"
                  allowEmpty
                />
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Back Cover Title</label>
                <input
                  type="text"
                  value={backTitle}
                  onChange={(e) => setBackTitle(e.target.value)}
                  placeholder={work.title}
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent"
                />
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Back Cover Blurb</label>
                <textarea
                  value={backBlurb}
                  onChange={(e) => setBackBlurb(e.target.value)}
                  rows={6}
                  placeholder="Enter back cover text..."
                  className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent resize-y"
                />
                <p className="text-xs text-tc-muted mt-1">Renders over back cover image with dark overlay</p>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Blurb Font</label>
                <FontSelect
                  value={blurbFontFamily}
                  onChange={setBlurbFontFamily}
                  customFonts={fonts}
                  placeholder="Default"
                  allowEmpty
                />
              </div>
              {coverType === "hardcover" && (
                <>
                  <div>
                    <label className="block text-xs text-tc-tertiary mb-1">Front Flap Text</label>
                    <textarea
                      value={frontFlapText}
                      onChange={(e) => setFrontFlapText(e.target.value)}
                      rows={4}
                      placeholder="Book description, praise quotes..."
                      className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent resize-y"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-tc-tertiary mb-1">Back Flap Text</label>
                    <textarea
                      value={backFlapText}
                      onChange={(e) => setBackFlapText(e.target.value)}
                      rows={4}
                      placeholder="Author bio, photo credit..."
                      className="w-full bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm focus:outline-none focus:border-tc-accent resize-y"
                    />
                  </div>
                </>
              )}
            </div>
          </section>

          {/* Appearance */}
          <section className="p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
            <h3 className="text-sm font-semibold text-tc-secondary mb-3 flex items-center gap-2">
              <Palette size={14} />
              Appearance
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Background Color</label>
                <div className="flex gap-2">
                  <input
                    type="color"
                    value={bgColor}
                    onChange={(e) => setBgColor(e.target.value)}
                    className="h-9 w-9 shrink-0 rounded border border-tc-strong bg-transparent cursor-pointer"
                  />
                  <input
                    type="text"
                    value={bgColor}
                    onChange={(e) => setBgColor(e.target.value)}
                    className="flex-1 min-w-0 bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-tc-accent"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">Text Color</label>
                <div className="flex gap-2">
                  <input
                    type="color"
                    value={textColor}
                    onChange={(e) => setTextColor(e.target.value)}
                    className="h-9 w-9 shrink-0 rounded border border-tc-strong bg-transparent cursor-pointer"
                  />
                  <input
                    type="text"
                    value={textColor}
                    onChange={(e) => setTextColor(e.target.value)}
                    className="flex-1 min-w-0 bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-tc-accent"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-tc-tertiary cursor-pointer">
                <input
                  type="checkbox"
                  checked={barcodeZone}
                  onChange={(e) => setBarcodeZone(e.target.checked)}
                  className="rounded border-tc-strong bg-tc-hover text-tc-accent focus:ring-tc-accent"
                />
                Show ISBN barcode safe zone
              </label>
              <div>
                <label className="block text-xs text-tc-tertiary mb-1">
                  Back Cover Overlay Opacity ({Math.round(backOverlayOpacity / 255 * 100)}%)
                </label>
                <input
                  type="range"
                  min="0"
                  max="255"
                  value={backOverlayOpacity}
                  onChange={(e) => setBackOverlayOpacity(parseInt(e.target.value))}
                  className="w-full accent-indigo-500"
                />
                <p className="text-xs text-tc-muted mt-1">Dark overlay behind text on back cover image</p>
              </div>
            </div>
          </section>

          {/* Actions */}
          <div className="space-y-3">
            <button
              onClick={handlePreview}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
            >
              <RefreshCw size={14} className={generating ? "animate-spin" : ""} />
              {generating ? "Generating..." : "Generate Preview"}
            </button>
            <div className="relative flex">
              <button
                onClick={() => handleDownload()}
                disabled={downloading || !previewUrl}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-tc-hover hover:bg-tc-active disabled:opacity-50 rounded-l-lg text-sm font-medium transition-colors"
              >
                <Download size={14} />
                {downloading ? "Downloading..." : `Download ${outputFormat.toUpperCase()}`}
              </button>
              <button
                onClick={() => setShowFormatMenu(!showFormatMenu)}
                disabled={downloading || !previewUrl}
                className="px-2.5 py-2.5 bg-tc-hover hover:bg-tc-active disabled:opacity-50 rounded-r-lg border-l border-tc-strong text-sm transition-colors"
              >
                <ChevronDown size={14} />
              </button>
              {showFormatMenu && (
                <div className="absolute top-full right-0 mt-1 bg-tc-hover border border-tc-strong rounded-lg shadow-xl z-10 overflow-hidden min-w-[160px]">
                  {([["pdf", "PDF (Print-ready)"], ["docx", "DOCX (Editable)"], ["png", "PNG (300 DPI)"]] as const).map(([fmt, label]) => (
                    <button
                      key={fmt}
                      onClick={() => { setOutputFormat(fmt); setShowFormatMenu(false); handleDownload(fmt); }}
                      className={`w-full text-left px-4 py-2 text-sm hover:bg-tc-active transition-colors ${fmt === outputFormat ? "text-tc-accent" : "text-tc-secondary"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Preview Panel */}
        <div className="lg:sticky lg:top-8 lg:self-start">
          <div className="p-4 bg-tc-overlay rounded-lg border border-tc-subtle">
            <h3 className="text-sm font-semibold text-tc-secondary mb-3">Preview</h3>
            {previewUrl ? (
              <div
                className="relative cursor-pointer group"
                onClick={() => setShowPreviewModal(true)}
                title="Click to enlarge"
              >
                <img
                  src={previewUrl}
                  alt="Full cover preview"
                  className="w-full rounded border border-tc-subtle group-hover:border-tc-accent/50 transition-colors"
                />
                {dims && <CoverOverlay dims={dims} />}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors rounded flex items-center justify-center">
                  <span className="opacity-0 group-hover:opacity-100 transition-opacity text-xs bg-black/60 text-tc-secondary px-2 py-1 rounded">
                    Click to enlarge
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-tc-muted">
                <ImageIcon size={48} className="mb-3 opacity-30" />
                <p className="text-sm">Click "Generate Preview" to see your cover</p>
                {dims && (
                  <p className="text-xs text-tc-muted mt-2">
                    {dims.total_width_px} × {dims.total_height_px}px at 300dpi
                  </p>
                )}
              </div>
            )}
          </div>

          {showPreviewModal && previewUrl && (
            <div
              className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-8"
              onClick={() => setShowPreviewModal(false)}
            >
              <img
                src={previewUrl}
                alt="Full cover preview"
                className="max-h-[90vh] max-w-[95vw] object-contain rounded-lg shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function CoverOverlay({ dims }: { dims: CoverDimensions }) {
  const tw = dims.total_width;
  const spinePct = (dims.spine_width / tw) * 100;
  const spineLeftPct = (dims.spine_x / tw) * 100;

  if (dims.cover_type === "hardcover" && dims.flap_width) {
    const backFlapPct = ((dims.flap_width + dims.bleed) / tw) * 100;
    const backPct = ((dims.trim_width + dims.bleed) / tw) * 100;
    const frontPct = backPct;
    const frontFlapPct = backFlapPct;
    const frontLeftPct = (dims.front_x / tw) * 100;
    const frontFlapLeftPct = (dims.front_flap_x! / tw) * 100;

    return (
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 bottom-0 border-r border-red-500/30" style={{ left: `${backFlapPct}%`, width: 0 }} />
        <div className="absolute top-0 bottom-0 border-l border-r border-red-500/30" style={{ left: `${spineLeftPct}%`, width: `${spinePct}%` }}>
          <span className="absolute top-1 left-1/2 -translate-x-1/2 text-[9px] text-tc-error/60 whitespace-nowrap">spine</span>
        </div>
        <div className="absolute top-0 bottom-0 border-l border-red-500/30" style={{ left: `${frontFlapLeftPct}%`, width: 0 }} />
        <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${backFlapPct / 2}%`, transform: "translateX(-50%)" }}>back flap</span>
        <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${backFlapPct + backPct / 2}%`, transform: "translateX(-50%)" }}>back cover</span>
        <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${frontLeftPct + frontPct / 2}%`, transform: "translateX(-50%)" }}>front cover</span>
        <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${frontFlapLeftPct + frontFlapPct / 2}%`, transform: "translateX(-50%)" }}>front flap</span>
      </div>
    );
  }

  const backPct = ((dims.trim_width + dims.bleed) / tw) * 100;

  return (
    <div className="absolute inset-0 pointer-events-none">
      <div
        className="absolute top-0 bottom-0 border-l border-r border-red-500/30"
        style={{ left: `${spineLeftPct}%`, width: `${spinePct}%` }}
      >
        <span className="absolute top-1 left-1/2 -translate-x-1/2 text-[9px] text-tc-error/60 whitespace-nowrap">spine</span>
      </div>
      <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${backPct / 2}%`, transform: "translateX(-50%)" }}>back cover</span>
      <span className="absolute bottom-1 text-[9px] text-tc-error/40" style={{ left: `${spineLeftPct + spinePct + (100 - spineLeftPct - spinePct) / 2}%`, transform: "translateX(-50%)" }}>front cover</span>
    </div>
  );
}


function ImageSelector({
  label,
  currentPath,
  coverPath,
  allImages,
  onSelect,
  isOpen,
  onToggle,
  hint,
}: {
  label: string;
  currentPath: string | null;
  coverPath: string | null;
  allImages: { url: string; name: string }[];
  onSelect: (path: string | null) => void;
  isOpen: boolean;
  onToggle: () => void;
  hint?: string;
}) {
  const displayName = useMemo(() => {
    if (!currentPath) return null;
    if (coverPath && currentPath === coverPath) return "Book Cover";
    const match = allImages.find((i) => i.url === currentPath);
    if (match) return match.name;
    return currentPath.split("/").pop() ?? "Image";
  }, [currentPath, coverPath, allImages]);

  return (
    <div>
      <label className="block text-xs text-tc-tertiary mb-1">{label}</label>
      <div className="flex gap-2 items-center">
        {currentPath && (
          <img src={currentPath} alt={label} className="h-10 w-8 object-cover rounded border border-tc-strong" />
        )}
        <button
          onClick={onToggle}
          className="flex-1 bg-tc-hover border border-tc-strong rounded px-3 py-2 text-sm text-left text-tc-tertiary hover:border-tc-strong transition-colors truncate"
        >
          {displayName ?? "Select image..."}
        </button>
        {currentPath && (
          <button
            onClick={() => onSelect(null)}
            className="text-xs text-tc-muted hover:text-tc-error transition-colors px-2"
          >
            Clear
          </button>
        )}
      </div>
      {isOpen && (
        <div className="mt-2 p-2 bg-tc-hover/50 rounded border border-tc-strong max-h-48 overflow-y-auto">
          {coverPath && (
            <button
              onClick={() => { onSelect(coverPath); onToggle(); }}
              className="w-full flex items-center gap-2 p-2 rounded hover:bg-tc-active/50 text-sm text-left"
            >
              <img src={coverPath} alt="Book cover" className="h-10 w-8 object-cover rounded" />
              <span className="text-tc-secondary">Book Cover</span>
            </button>
          )}
          {allImages.map((img) => (
            <button
              key={img.url}
              onClick={() => { onSelect(img.url); onToggle(); }}
              className="w-full flex items-center gap-2 p-2 rounded hover:bg-tc-active/50 text-sm text-left"
            >
              <img src={img.url} alt={img.name} className="h-10 w-8 object-cover rounded" />
              <span className="text-tc-secondary truncate">{img.name}</span>
            </button>
          ))}
          {!coverPath && allImages.length === 0 && (
            <p className="text-xs text-tc-muted p-2">No images available. Upload images in the work gallery.</p>
          )}
        </div>
      )}
      {hint && <p className="text-xs text-tc-muted mt-1">{hint}</p>}
    </div>
  );
}
