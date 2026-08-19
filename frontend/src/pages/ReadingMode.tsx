import { useQuery } from "@tanstack/react-query";
import { useParams, Link, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Columns2,
  FileText,
  Loader2,
} from "lucide-react";
import { getWork } from "@/api/works";
import { listChapters } from "@/api/chapters";
import { listScenes } from "@/api/scenes";
import { listProfiles } from "@/api/profiles";
import { listFonts } from "@/api/fonts";
import {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  memo,
  Fragment,
  ReactNode,
} from "react";
import Markdown from "react-markdown";
import { marked } from "marked";
import { Profile, TitlePageConfig } from "@/types";
import { useFontFaceStyles } from "@/components/FontSelect";



const MATTER_TITLES = new Set([
  "dedication", "preface", "foreword", "introduction", "prologue",
  "epilogue", "afterword", "acknowledgments", "acknowledgements",
  "appendix", "glossary", "bibliography", "about the author",
  "also by", "colophon", "copyright", "half title", "title page",
]);

const FRONT_MATTER_TITLES = new Set([
  "half title", "title page", "copyright", "dedication", "epigraph",
  "table of contents", "foreword", "preface", "acknowledgments",
  "acknowledgements", "introduction", "prologue",
]);

const BACK_MATTER_TITLES = new Set([
  "epilogue", "afterword", "appendix", "glossary", "bibliography",
  "about the author", "also by", "colophon", "index",
]);

const CENTERED_TITLES = new Set([
  "dedication", "epigraph", "half title", "title page",
]);

function isMatter(title: string | null): boolean {
  if (!title) return false;
  return MATTER_TITLES.has(title.toLowerCase().trim());
}

function isFrontMatter(title: string | null): boolean {
  if (!title) return false;
  return FRONT_MATTER_TITLES.has(title.toLowerCase().trim());
}

function isBackMatter(title: string | null): boolean {
  if (!title) return false;
  return BACK_MATTER_TITLES.has(title.toLowerCase().trim());
}

function isCentered(title: string | null): boolean {
  if (!title) return false;
  return CENTERED_TITLES.has(title.toLowerCase().trim());
}

function toRoman(n: number): string {
  const vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1];
  const syms = ["m", "cm", "d", "cd", "c", "xc", "l", "xl", "x", "ix", "v", "iv", "i"];
  let result = "";
  for (let i = 0; i < vals.length; i++) {
    while (n >= vals[i]) { result += syms[i]; n -= vals[i]; }
  }
  return result;
}

function useWorkContent(workId: string | undefined) {
  const { data: chapters = [], isLoading: chaptersLoading } = useQuery({
    queryKey: ["chapters", { workId }],
    queryFn: () => listChapters(workId!),
    enabled: !!workId,
  });

  const sceneQueries = useQuery({
    queryKey: ["all-scenes", workId, chapters.map((c) => c.id)],
    queryFn: async () => {
      const results = await Promise.all(
        chapters.map((ch) => listScenes(ch.id))
      );
      return chapters.map((ch, i) => ({
        chapter: ch,
        scenes: results[i],
      }));
    },
    enabled: chapters.length > 0,
  });

  return {
    data: sceneQueries.data ?? [],
    isLoading: chaptersLoading || sceneQueries.isLoading,
  };
}

type ChapterContent = {
  chapter: { id?: string; title: string | null; number: number | null; show_title: boolean };
  scenes: { id: string; title: string | null; content: string }[];
  isCover?: boolean;
  coverUrl?: string;
  titlePageConfig?: TitlePageConfig | null;
  workTitle?: string;
  workSubtitle?: string | null;
  workAuthor?: string;
};

interface ChapterHeadingStyle {
  fontFamily: string;
  fontSize?: string;
  fontWeight?: string;
  textAlign?: string;
  sink?: string;
}

function ChapterHeading({ chapter, headingStyle }: {
  chapter: { title: string | null; number: number | null; show_title: boolean };
  headingStyle: ChapterHeadingStyle;
}) {
  if (!chapter.show_title) return null;
  const hasNumber = chapter.number != null;
  const hasTitle = !!chapter.title;
  const matter = isMatter(chapter.title);
  const { fontFamily, fontSize, fontWeight, textAlign, sink } = headingStyle;
  const align = (textAlign as any) || "center";
  const titleText = hasTitle ? chapter.title : hasNumber ? `Chapter ${chapter.number}` : "Untitled";
  if (hasNumber && hasTitle && !matter) {
    return (
      <>
        <div style={{ fontFamily, fontWeight: fontWeight as any, fontSize: "1.2em", letterSpacing: "0.1em", textTransform: "uppercase" as const, textAlign: align, marginTop: sink || "3em", marginBottom: "0.2em", color: "#555" }}>
          Chapter {chapter.number}
        </div>
        <div style={{ fontFamily, fontSize: fontSize || "1.4em", fontWeight: (fontWeight as any) || "normal", textAlign: align, marginBottom: "2em" }}>
          {titleText}
        </div>
      </>
    );
  }
  if (matter) {
    return (
      <div style={{ fontFamily, fontSize: fontSize || "1.4em", fontWeight: (fontWeight as any) || "normal", textAlign: align, marginBottom: "2em" }}>
        {titleText}
      </div>
    );
  }
  return (
    <div style={{ fontFamily, fontSize: fontSize || "1.4em", fontWeight: (fontWeight as any) || "normal", textAlign: align, marginTop: sink || "3em", marginBottom: "2em" }}>
      {titleText}
    </div>
  );
}

const BLOCK_RE = /<(p|div|blockquote|ul|ol|h[1-6])\b[^>]*>(?:(?!<\1\b).)*?<\/\1>/gs;

function popLastBlock(html: string): [string, string] {
  const blocks = [...html.matchAll(BLOCK_RE)];
  if (!blocks.length) return ["", html];
  const last = blocks[blocks.length - 1];
  let remaining = html.slice(0, last.index!).trimEnd();
  const tail = html.slice(last.index! + last[0].length);
  if (tail.trim()) remaining += tail;
  return [last[0], remaining];
}

const IMAGE_ONLY_RE = /^!\[[^\]]*\]\([^)]+\)(\s*!\[[^\]]*\]\([^)]+\))*\s*$/;
function isImageOnly(content: string | null | undefined): boolean {
  const s = (content || "").trim();
  return s.length > 0 && IMAGE_ONLY_RE.test(s);
}

function SceneContent({ scenes, fontFamily, matchExport }: {
  scenes: ChapterContent["scenes"];
  fontFamily: string;
  matchExport?: boolean;
}) {
  const html = useMemo(() => {
    if (!matchExport) return null;
    const sceneHtmls = scenes.map((s) => {
      const raw = (s.content || "").trim();
      if (isImageOnly(raw)) {
        const parsed = marked.parse(raw) as string;
        return `<div class="full-page-image">${parsed}</div>`;
      }
      return raw ? (marked.parse(raw) as string) : "";
    });
    const breakDiv = '<div style="text-align:center;margin:1.5em 0;letter-spacing:0.5em;opacity:0.4">***</div>';
    const transitions: string[] = [];
    for (let j = 1; j < sceneHtmls.length; j++) {
      if (isImageOnly(scenes[j - 1].content) || isImageOnly(scenes[j].content)) {
        transitions.push("");
      } else {
        const [lastBlock, rest] = popLastBlock(sceneHtmls[j - 1]);
        sceneHtmls[j - 1] = rest;
        transitions.push('<div style="break-inside:avoid">' + lastBlock + breakDiv + '</div>');
      }
    }
    const parts: string[] = [];
    for (let j = 0; j < sceneHtmls.length; j++) {
      if (j > 0) parts.push(transitions[j - 1]);
      parts.push(sceneHtmls[j]);
    }
    return parts.join("\n");
  }, [scenes, matchExport]);

  if (matchExport && html != null) {
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return (
    <>
      {scenes.map((scene, i) => {
        const imgOnly = isImageOnly(scene.content);
        const prevImgOnly = i > 0 && isImageOnly(scenes[i - 1].content);
        return (
          <Fragment key={scene.id}>
            {i > 0 && !prevImgOnly && !imgOnly && (
              <div
                className="text-center"
                style={{ margin: "1.5em 0" }}
              >
                <span className="tracking-[0.5em] opacity-40">***</span>
              </div>
            )}
            {scene.title && (
              <h2
                className="text-lg font-semibold mt-6 mb-3"
                style={{ fontFamily, breakAfter: "avoid" }}
              >
                {scene.title}
              </h2>
            )}
            {imgOnly ? (
              <div className="full-page-image">
                <Markdown>{scene.content}</Markdown>
              </div>
            ) : (
              <Markdown>{scene.content}</Markdown>
            )}
          </Fragment>
        );
      })}
    </>
  );
}

function TitlePageContent({ config, workTitle, workSubtitle, workAuthor, bottomOffset }: {
  config: TitlePageConfig;
  workTitle: string;
  workSubtitle: string | null;
  workAuthor: string;
  bottomOffset?: string;
}) {
  const title = config.title_override || workTitle;
  const subtitle = config.subtitle_override || workSubtitle || "";
  const author = config.author_override || workAuthor;
  const isBottom = config.author_position === "bottom";

  return (
    <div style={{
      textAlign: "center",
      paddingTop: "30%",
      height: "100%",
      position: "relative",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
    }}>
      <div style={{
        fontFamily: config.title_font_family || "inherit",
        fontSize: config.title_font_size || "2em",
        fontWeight: "bold",
        marginBottom: "0.5em",
      }}>
        {title}
      </div>
      {subtitle && (
        <div
          style={{
            fontFamily: config.subtitle_font_family || "inherit",
            fontSize: config.subtitle_font_size || "1em",
            marginBottom: "1em",
          }}
          dangerouslySetInnerHTML={{ __html: subtitle }}
        />
      )}
      {config.ornament_image_url && (
        <div style={{ margin: isBottom ? "auto 0" : "1em 0", display: "flex", justifyContent: "center" }}>
          <img src={config.ornament_image_url} alt="" style={{ maxHeight: "6em", objectFit: "contain" }} />
        </div>
      )}
      <div style={{
        fontFamily: config.author_font_family || "inherit",
        fontSize: config.author_font_size || "1.2em",
        ...(isBottom
          ? { marginTop: "auto", paddingBottom: bottomOffset || "0.5em" }
          : { marginTop: config.ornament_image_url ? "1em" : "2em" }),
      }}>
        {author}
      </div>
    </div>
  );
}

function ChapterBody({ content, fontFamily, headingStyle, titlePageConfig, workTitle, workSubtitle, workAuthor, authorBottomOffset, matchExport }: {
  content: ChapterContent;
  fontFamily: string;
  headingStyle: ChapterHeadingStyle;
  titlePageConfig?: TitlePageConfig | null;
  workTitle?: string;
  workSubtitle?: string | null;
  workAuthor?: string;
  authorBottomOffset?: string;
  matchExport?: boolean;
}) {
  const isTitlePage = content.chapter.title?.toLowerCase().trim() === "title page";
  if (isTitlePage && titlePageConfig && workTitle && workAuthor) {
    return (
      <TitlePageContent
        config={titlePageConfig}
        workTitle={workTitle}
        workSubtitle={workSubtitle ?? null}
        workAuthor={workAuthor}
        bottomOffset={authorBottomOffset}
      />
    );
  }

  const centered = isCentered(content.chapter.title);
  return (
    <div style={centered ? { textAlign: "center", paddingTop: "30%" } : undefined}>
      <ChapterHeading chapter={content.chapter} headingStyle={headingStyle} />
      <SceneContent scenes={content.scenes} fontFamily={fontFamily} matchExport={matchExport} />
    </div>
  );
}

function useResizeHeight() {
  const [height, setHeight] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: HTMLDivElement | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    if (node) {
      const observer = new ResizeObserver(() => {
        setHeight(node.clientHeight);
      });
      observer.observe(node);
      observerRef.current = observer;
    } else {
      setHeight(0);
    }
  }, []);

  return { ref, height };
}

function ColumnPaginator({
  height,
  gap,
  page,
  children,
  onTotalPages,
  className,
  style,
  matchExport,
}: {
  height: number;
  gap: number;
  page: number;
  children: ReactNode;
  onTotalPages: (n: number) => void;
  className?: string;
  style?: React.CSSProperties;
  matchExport?: boolean;
}) {
  const innerRef = useRef<HTMLDivElement>(null);
  const [colWidth, setColWidth] = useState(0);

  useEffect(() => {
    const el = innerRef.current;
    if (!el || !height) return;

    const frame = requestAnimationFrame(() => {
      const cw = el.parentElement?.clientWidth ?? el.clientWidth;
      setColWidth(cw);
      const total = el.scrollWidth;
      const pages = Math.max(1, Math.ceil(total / (cw + gap)));
      onTotalPages(pages);
    });
    return () => cancelAnimationFrame(frame);
  }, [height, gap, onTotalPages, children]);

  if (!height) return null;

  return (
    <div style={{ overflow: "hidden", height, ...style }} className={className}>
      <style>{`
.col-paginator p > img { max-height: ${Math.floor(height * 0.98)}px !important; max-width: 100% !important; width: auto !important; height: auto !important; object-fit: contain; break-inside: avoid; margin: 0 !important; display: block; }
.col-paginator p:has(> img:only-child) { margin: 0 !important; padding: 0 !important; line-height: 0 !important; break-inside: avoid; }
.col-paginator .full-page-image { break-before: column; break-after: column; break-inside: avoid; display: grid; place-items: center; height: ${height}px; max-height: ${height}px; box-sizing: border-box; overflow: hidden; }
.col-paginator .full-page-image p { margin: 0 !important; padding: 0 !important; line-height: 0 !important; }
.col-paginator .full-page-image img { max-width: 100% !important; max-height: ${height}px !important; object-fit: contain; display: block; }
${matchExport ? `
.col-paginator p { margin: 0.5em 0 0 0 !important; text-indent: 0 !important; }
.col-paginator p:first-child { margin-top: 0 !important; }
.col-paginator h1, .col-paginator h2, .col-paginator h3 { margin-top: 0 !important; margin-bottom: 0 !important; }
` : ""}
`}</style>
      <div
        ref={innerRef}
        className="col-paginator"
        style={{
          columnWidth: `${colWidth || 9999}px`,
          columnCount: colWidth ? undefined : 1,
          columnGap: `${gap}px`,
          columnFill: "auto",
          height: "100%",
          transform: `translateX(${-page * (colWidth + gap)}px)`,
          transition: "none",
          orphans: 2,
          widows: 2,
        }}
      >
        {children}
      </div>
    </div>
  );
}

function CoverView({
  coverUrl,
  onNext,
  onPrev,
  mode,
}: {
  coverUrl: string;
  onNext?: () => void;
  onPrev?: () => void;
  mode: "epub" | "pdf";
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || (e.target as HTMLElement).isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); onNext?.(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); onPrev?.(); }
      else if (e.key === "Escape") window.history.back();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onNext, onPrev]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-hidden flex items-center justify-center p-8">
        <img
          src={coverUrl}
          alt="Cover"
          className={mode === "epub"
            ? "max-h-full max-w-full object-contain rounded-lg shadow-2xl"
            : "max-h-full max-w-full object-contain shadow-2xl"}
        />
      </div>
      <footer className="flex items-center justify-between px-6 py-2 bg-gray-900 border-t border-gray-800 shrink-0">
        <button onClick={onPrev} disabled={!onPrev}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          <ChevronLeft size={16} /> Previous
        </button>
        <span className="text-xs text-gray-500">Cover</span>
        <button onClick={onNext} disabled={!onNext}
          className="flex items-center gap-1 justify-end text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          Next <ChevronRight size={16} />
        </button>
      </footer>
    </div>
  );
}

function EpubReader({
  content,
  profile,
  chapterIndex,
  onNextChapter,
  onPrevChapter,
  navDirectionRef,
}: {
  content: ChapterContent;
  profile: Profile | undefined;
  chapterIndex: number;
  onNextChapter?: () => void;
  onPrevChapter?: () => void;
  navDirectionRef: React.MutableRefObject<"backward" | null>;
}) {
  const [page, setPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const wantLastPageRef = useRef(false);

  const fontFamily = profile?.font_family ?? "Georgia, serif";
  const fontSize = profile?.font_size ?? "1.1em";
  const lineHeight = profile?.line_height ?? 1.8;
  const chHeadingStyle: ChapterHeadingStyle = {
    fontFamily: profile?.chapter_font_family || fontFamily,
    fontSize: profile?.chapter_font_size || "1.4em",
    fontWeight: profile?.chapter_font_weight || "normal",
    textAlign: profile?.chapter_align || "center",
  };

  const { ref: outerRef, height } = useResizeHeight();

  useEffect(() => {
    if (navDirectionRef.current === "backward") {
      wantLastPageRef.current = true;
      navDirectionRef.current = null;
      setPage(Math.max(0, totalPages - 1));
    } else {
      setPage(0);
    }
  }, [chapterIndex]);
  useEffect(() => {
    if (page >= totalPages) setPage(Math.max(0, totalPages - 1));
  }, [totalPages, page]);

  const handleTotalPages = useCallback((n: number) => {
    setTotalPages(n);
    if (wantLastPageRef.current) {
      wantLastPageRef.current = false;
      setPage(Math.max(0, n - 1));
    }
  }, []);

  const isLastPage = page >= totalPages - 1;
  const isFirstPage = page === 0;

  const goNext = useCallback(() => {
    if (isLastPage) { onNextChapter?.(); }
    else { setPage((p) => p + 1); }
  }, [isLastPage, onNextChapter]);

  const goPrev = useCallback(() => {
    if (isFirstPage) { onPrevChapter?.(); }
    else { setPage((p) => p - 1); }
  }, [isFirstPage, onPrevChapter]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || (e.target as HTMLElement).isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); goNext(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); goPrev(); }
      else if (e.key === "Escape") window.history.back();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  if (content.isCover && content.coverUrl) {
    return (
      <CoverView
        coverUrl={content.coverUrl}
        onNext={onNextChapter}
        onPrev={onPrevChapter}
        mode="epub"
      />
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-hidden px-10 py-8 max-w-[50em] mx-auto w-full">
        <div ref={outerRef} className="h-full">
          <ColumnPaginator
            height={height}
            gap={80}
            page={page}
            onTotalPages={handleTotalPages}
            className="prose prose-invert max-w-none text-gray-300"
            style={{ fontFamily, fontSize, lineHeight }}
          >
            <ChapterBody content={content} fontFamily={fontFamily} headingStyle={chHeadingStyle} titlePageConfig={content.titlePageConfig} workTitle={content.workTitle} workSubtitle={content.workSubtitle} workAuthor={content.workAuthor} />
          </ColumnPaginator>
        </div>
      </div>

      <footer className="flex items-center justify-between px-6 py-2 bg-gray-900 border-t border-gray-800 shrink-0">
        <button onClick={goPrev} disabled={isFirstPage && !onPrevChapter}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          <ChevronLeft size={16} /> Previous
        </button>
        <span className="text-xs text-gray-500">
          Page {page + 1} of {totalPages}
        </span>
        <button onClick={goNext} disabled={isLastPage && !onNextChapter}
          className="flex items-center gap-1 justify-end text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          Next <ChevronRight size={16} />
        </button>
      </footer>
    </div>
  );
}

function PdfReader({
  content,
  profile,
  chapterIndex,
  onNextChapter,
  onPrevChapter,
  navDirectionRef,
  pageOffset,
  totalBookPages,
  onPageCount,
  workTitle,
  workAuthor,
  bodyPageOffset,
  hasCover,
}: {
  content: ChapterContent;
  profile: Profile;
  chapterIndex: number;
  onNextChapter?: () => void;
  onPrevChapter?: () => void;
  navDirectionRef: React.MutableRefObject<"backward" | null>;
  pageOffset: number;
  totalBookPages: number;
  onPageCount: (chapterIndex: number, count: number) => void;
  workTitle: string;
  workAuthor: string;
  hasCover: boolean;
  bodyPageOffset: number;
}) {
  const [page, setPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const wantLastPageRef = useRef(false);

  const fontFamily = profile.font_family;
  const fontSize = profile.font_size;
  const lineHeight = profile.line_height;
  const chHeadingStyle: ChapterHeadingStyle = {
    fontFamily: profile.chapter_font_family || fontFamily,
    fontSize: profile.chapter_font_size || "1.4em",
    fontWeight: profile.chapter_font_weight || "normal",
    textAlign: profile.chapter_align || "center",
    sink: profile.chapter_sink != null ? `${profile.chapter_sink}em` : undefined,
  };

  const { ref: innerRef, height: innerHeight } = useResizeHeight();

  useEffect(() => {
    if (navDirectionRef.current === "backward") {
      wantLastPageRef.current = true;
      navDirectionRef.current = null;
      setPage(Math.max(0, totalPages - 1));
    } else {
      setPage(0);
    }
  }, [chapterIndex]);
  useEffect(() => {
    if (page >= totalPages) setPage(Math.max(0, totalPages - 1));
  }, [totalPages, page]);

  const handleTotalPages = useCallback((n: number) => {
    setTotalPages(n);
    onPageCount(chapterIndex, n);
    if (wantLastPageRef.current) {
      wantLastPageRef.current = false;
      setPage(Math.max(0, n - 1));
    }
  }, [onPageCount, chapterIndex]);

  const isLastPage = page >= totalPages - 1;
  const isFirstPage = page === 0;

  const goNext = useCallback(() => {
    if (isLastPage) { onNextChapter?.(); }
    else { setPage((p) => p + 1); }
  }, [isLastPage, onNextChapter]);

  const goPrev = useCallback(() => {
    if (isFirstPage) { onPrevChapter?.(); }
    else { setPage((p) => p - 1); }
  }, [isFirstPage, onPrevChapter]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || (e.target as HTMLElement).isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); goNext(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); goPrev(); }
      else if (e.key === "Escape") window.history.back();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  useEffect(() => {
    if (content.isCover) onPageCount(chapterIndex, 1);
  }, [content.isCover, chapterIndex, onPageCount]);

  if (content.isCover && content.coverUrl) {
    return (
      <CoverView
        coverUrl={content.coverUrl}
        onNext={onNextChapter}
        onPrev={onPrevChapter}
        mode="pdf"
      />
    );
  }

  const absPage = pageOffset + page;
  const isFm = content.isCover || isFrontMatter(content.chapter.title);
  const isBm = isBackMatter(content.chapter.title);
  const bmPn = profile.back_matter_page_numbers ?? true;
  const suppressNumber = isFm || (isBm && !bmPn);
  const startAtContent = profile.page_numbers_start_at_content;
  const fmRoman = !!(profile.front_matter_roman && startAtContent);
  const coverPages = hasCover ? 1 : 0;

  let displayPageNumber: number | undefined;
  let isRomanPage = false;
  const isCenteredPage = isCentered(content.chapter.title);
  if (profile.page_numbers) {
    if (startAtContent && suppressNumber) {
      if (fmRoman && isFm && !content.isCover && !isCenteredPage) {
        displayPageNumber = absPage - coverPages + 1;
        isRomanPage = true;
      }
    } else if (startAtContent) {
      displayPageNumber = absPage - bodyPageOffset + 1;
    } else {
      displayPageNumber = absPage + 1;
    }
  }

  const isRectoPage = absPage % 2 === 0;
  const pdfPageContext: PageContext = {
    workTitle,
    workAuthor,
    chapterTitle: content.chapter.title,
    chapterNumber: content.chapter.number,
    isFrontMatter: suppressNumber,
    roman: isRomanPage,
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-hidden flex justify-center py-6">
        <div className="rounded shadow-2xl overflow-hidden">
          <PdfPageShell
            profile={profile}
            isRecto={isRectoPage}
            pageNumber={displayPageNumber}
            pageContext={pdfPageContext}
          >
            <div ref={innerRef} className="h-full">
              <ColumnPaginator
                height={innerHeight}
                gap={60}
                page={page}
                onTotalPages={handleTotalPages}
                className="max-w-none text-gray-800"
                matchExport
                style={{ fontFamily, fontSize, lineHeight, textAlign: (profile.text_align ?? "justify") as any }}
              >
                <ChapterBody content={content} fontFamily={fontFamily} headingStyle={chHeadingStyle} titlePageConfig={content.titlePageConfig} workTitle={content.workTitle} workSubtitle={content.workSubtitle} workAuthor={content.workAuthor} authorBottomOffset={`${profile.margin_bottom ?? 0.75}in`} matchExport />
              </ColumnPaginator>
            </div>
          </PdfPageShell>
        </div>
      </div>

      <footer className="flex items-center justify-between px-6 py-2 bg-gray-900 border-t border-gray-800 shrink-0">
        <button onClick={goPrev} disabled={isFirstPage && !onPrevChapter}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          <ChevronLeft size={16} /> Previous
        </button>
        <span className="text-xs text-gray-500">
          Page {pageOffset + page + 1}{totalBookPages > 0 ? ` of ${totalBookPages}` : ""}
        </span>
        <button onClick={goNext} disabled={isLastPage && !onNextChapter}
          className="flex items-center gap-1 justify-end text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          Next <ChevronRight size={16} />
        </button>
      </footer>
    </div>
  );
}

type PageContext = {
  workTitle: string;
  workAuthor: string;
  chapterTitle: string | null;
  chapterNumber: number | null;
  isFrontMatter: boolean;
  roman?: boolean;
};

function resolveHeaderText(
  value: string | null | undefined,
  ctx: PageContext,
  pageNumber?: number,
  roman?: boolean,
): string | null {
  if (!value) return null;
  if (value === "title") return ctx.workTitle;
  if (value === "author") return ctx.workAuthor;
  if (value === "chapter") return ctx.chapterNumber != null ? `Chapter ${ctx.chapterNumber}` : null;
  if (value === "chapter_title") return ctx.chapterTitle || null;
  if (value === "page_number") return pageNumber != null ? (roman ? toRoman(pageNumber) : String(pageNumber)) : null;
  return null;
}

function headerAlign(position: string, isRecto: boolean): "left" | "center" | "right" {
  if (position === "center") return "center";
  return isRecto ? "right" : "left";
}

function PdfPageShell({
  profile,
  isRecto,
  children,
  pageNumber,
  pageContext,
}: {
  profile: Profile;
  isRecto: boolean;
  children?: ReactNode;
  pageNumber?: number;
  pageContext?: PageContext;
}) {
  const pageWidth = `${profile.page_width ?? 6}in`;
  const pageHeight = `${profile.page_height ?? 9}in`;
  const rawMt = profile.margin_top ?? 0.75;
  const rawMb = profile.margin_bottom ?? 0.75;
  const marginInner = `${profile.margin_inner ?? 0.875}in`;
  const marginOuter = `${profile.margin_outer ?? 0.625}in`;
  const fontFamily = profile.font_family;

  const hasAnyHeader = !!(profile.header_recto || profile.header_verso);
  const hasAnyFooter = !!(profile.footer_recto || profile.footer_verso);
  const hdrFromEdge = profile.header_from_edge ?? 0.3;
  const ftrFromEdge = profile.footer_from_edge ?? 0.3;
  const hdrZone = rawMt;
  const ftrZone = rawMb;

  const headerContentKey = isRecto ? profile.header_recto : profile.header_verso;
  const fmRoman = pageContext?.isFrontMatter && pageContext?.roman;
  const showHeader = pageContext && (!pageContext.isFrontMatter || fmRoman) && !!headerContentKey;
  const headerText = showHeader
    ? resolveHeaderText(headerContentKey, pageContext, pageNumber, !!fmRoman)
    : null;

  const footerContentKey = isRecto ? profile.footer_recto : profile.footer_verso;
  const showFooter = pageContext && (!pageContext.isFrontMatter || fmRoman) && !!footerContentKey;
  const footerText = showFooter
    ? resolveHeaderText(footerContentKey, pageContext, pageNumber, !!fmRoman)
    : null;

  const hfFontFamily = profile.header_font_family || fontFamily;
  const hfFontSize = profile.header_font_size || "9pt";
  const hfFontWeight = profile.header_font_weight || undefined;

  return (
    <div
      className="bg-white flex-shrink-0 flex flex-col"
      style={{
        width: pageWidth,
        height: pageHeight,
        paddingLeft: isRecto ? marginInner : marginOuter,
        paddingRight: isRecto ? marginOuter : marginInner,
        paddingTop: (hasAnyHeader || hasAnyFooter) ? `${hdrFromEdge}in` : `${rawMt}in`,
        paddingBottom: (hasAnyHeader || hasAnyFooter) ? `${ftrFromEdge}in` : `${rawMb}in`,
      }}
    >
      {(hasAnyHeader || hasAnyFooter) && (
        <div
          className="shrink-0"
          style={{
            height: `${hdrZone}in`,
            display: "flex",
            alignItems: "flex-start",
          }}
        >
          {headerText ? (
            <div
              className="text-gray-400 w-full"
              style={{
                fontFamily: hfFontFamily,
                fontSize: hfFontSize,
                fontWeight: hfFontWeight,
                textAlign: headerAlign(profile.header_position, isRecto),
              }}
            >
              {headerText}
            </div>
          ) : null}
        </div>
      )}
      <div className="flex-1 min-h-0">{children}</div>
      {(hasAnyHeader || hasAnyFooter) && (
        <div
          className="shrink-0"
          style={{
            height: `${ftrZone}in`,
            display: "flex",
            alignItems: "flex-end",
          }}
        >
          {footerText ? (
            <div
              className="text-gray-400 w-full"
              style={{
                fontFamily: hfFontFamily,
                fontSize: hfFontSize,
                fontWeight: hfFontWeight,
                textAlign: headerAlign(profile.footer_position ?? "center", isRecto),
              }}
            >
              {footerText}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function PdfChapterMeasurer({
  content,
  profile,
  onPageCount,
}: {
  content: ChapterContent;
  profile: Profile;
  onPageCount: (count: number) => void;
}) {
  const { ref: innerRef, height: innerHeight } = useResizeHeight();
  const fontFamily = profile.font_family;
  const fontSize = profile.font_size;
  const lineHeight = profile.line_height;
  const chHeadingStyle: ChapterHeadingStyle = {
    fontFamily: profile.chapter_font_family || fontFamily,
    fontSize: profile.chapter_font_size || "1.4em",
    fontWeight: profile.chapter_font_weight || "normal",
    textAlign: profile.chapter_align || "center",
    sink: profile.chapter_sink != null ? `${profile.chapter_sink}em` : undefined,
  };

  const handleTotalPages = useCallback(
    (n: number) => onPageCount(n),
    [onPageCount]
  );

  return (
    <div className="absolute" style={{ left: "-9999px", visibility: "hidden" }}>
      <PdfPageShell profile={profile} isRecto>
        <div ref={innerRef} className="h-full">
          <ColumnPaginator
            height={innerHeight}
            gap={60}
            page={0}
            onTotalPages={handleTotalPages}
            className="max-w-none text-gray-800"
            matchExport
            style={{ fontFamily, fontSize, lineHeight, textAlign: (profile.text_align ?? "justify") as any }}
          >
            <ChapterBody content={content} fontFamily={fontFamily} headingStyle={chHeadingStyle} titlePageConfig={content.titlePageConfig} workTitle={content.workTitle} workSubtitle={content.workSubtitle} workAuthor={content.workAuthor} authorBottomOffset={`${profile.margin_bottom ?? 0.75}in`} matchExport />
          </ColumnPaginator>
        </div>
      </PdfPageShell>
    </div>
  );
}

function PdfChapterPage({
  content,
  profile,
  pageInChapter,
  isRecto,
  pageContext,
  displayPageNumber,
}: {
  content: ChapterContent;
  profile: Profile;
  pageInChapter: number;
  isRecto: boolean;
  pageContext?: PageContext;
  displayPageNumber?: number;
}) {
  const { ref: innerRef, height: innerHeight } = useResizeHeight();
  const fontFamily = profile.font_family;
  const fontSize = profile.font_size;
  const lineHeight = profile.line_height;
  const chHeadingStyle: ChapterHeadingStyle = {
    fontFamily: profile.chapter_font_family || fontFamily,
    fontSize: profile.chapter_font_size || "1.4em",
    fontWeight: profile.chapter_font_weight || "normal",
    textAlign: profile.chapter_align || "center",
    sink: profile.chapter_sink != null ? `${profile.chapter_sink}em` : undefined,
  };
  const noop = useCallback(() => {}, []);

  if (content.isCover && content.coverUrl) {
    const pw = `${profile.page_width ?? 6}in`;
    const ph = `${profile.page_height ?? 9}in`;
    return (
      <div className="bg-white flex-shrink-0" style={{ width: pw, height: ph }}>
        <img src={content.coverUrl} alt="Cover" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </div>
    );
  }

  return (
    <PdfPageShell
      profile={profile}
      isRecto={isRecto}
      pageNumber={displayPageNumber}
      pageContext={pageContext}
    >
      <div ref={innerRef} className="h-full">
        <ColumnPaginator
          height={innerHeight}
          gap={60}
          page={pageInChapter}
          onTotalPages={noop}
          className="max-w-none text-gray-800"
          matchExport
          style={{ fontFamily, fontSize, lineHeight, textAlign: (profile.text_align ?? "justify") as any }}
        >
          <ChapterBody content={content} fontFamily={fontFamily} headingStyle={chHeadingStyle} titlePageConfig={content.titlePageConfig} workTitle={content.workTitle} workSubtitle={content.workSubtitle} workAuthor={content.workAuthor} authorBottomOffset={`${profile.margin_bottom ?? 0.75}in`} matchExport />
        </ColumnPaginator>
      </div>
    </PdfPageShell>
  );
}

const MemoizedMeasurer = memo(function MemoizedMeasurer({
  content,
  profile,
  chapterIdx,
  onPageCount,
}: {
  content: ChapterContent;
  profile: Profile;
  chapterIdx: number;
  onPageCount: (idx: number, count: number) => void;
}) {
  const handleCount = useCallback(
    (count: number) => onPageCount(chapterIdx, count),
    [chapterIdx, onPageCount]
  );
  useEffect(() => {
    if (content.isCover) onPageCount(chapterIdx, 1);
  }, [content.isCover, chapterIdx, onPageCount]);
  if (content.isCover) return null;
  return (
    <PdfChapterMeasurer content={content} profile={profile} onPageCount={handleCount} />
  );
});

function PdfSpreadReader({
  allContent,
  profile,
  initialChapterIndex,
  workTitle,
  workAuthor,
  onChapterChange,
}: {
  allContent: ChapterContent[];
  profile: Profile;
  initialChapterIndex: number;
  workTitle: string;
  workAuthor: string;
  onChapterChange?: (chapterIndex: number) => void;
}) {
  const [chapterPageCounts, setChapterPageCounts] = useState<number[]>([]);
  const [spread, setSpread] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const lastReportedChapter = useRef<number>(-1);

  const handlePageCount = useCallback(
    (chapterIdx: number, count: number) => {
      setChapterPageCounts((prev) => {
        if (prev[chapterIdx] === count) return prev;
        const next = [...prev];
        next[chapterIdx] = count;
        return next;
      });
    },
    []
  );

  const allMeasured = chapterPageCounts.length === allContent.length &&
    chapterPageCounts.every((c) => c != null);

  const hasCover = allContent.length > 0 && allContent[0].isCover;

  const chaptersStartRecto = profile.chapters_start_recto ?? false;

  const virtualPages = useMemo(() => {
    if (!allMeasured) return [];
    const pages: number[] = [];
    if (hasCover) {
      pages.push(0);
      pages.push(-1);
    }
    let absPage = 1;
    const startIdx = hasCover ? 1 : 0;
    for (let ci = startIdx; ci < allContent.length; ci++) {
      const count = chapterPageCounts[ci] ?? 1;
      const ch = allContent[ci];
      const isBody = !ch.isCover && !isFrontMatter(ch.chapter.title) && !isBackMatter(ch.chapter.title);
      if (chaptersStartRecto && isBody && pages.length > 0) {
        if (pages.length % 2 !== 0) {
          pages.push(-1);
        }
      }
      for (let p = 0; p < count; p++) {
        pages.push(absPage + p);
      }
      absPage += count;
    }
    return pages;
  }, [allMeasured, chapterPageCounts, hasCover, allContent, chaptersStartRecto]);

  const totalPages = useMemo(() => {
    if (!allMeasured) return 1;
    return virtualPages.filter((p) => p >= 0).length;
  }, [allMeasured, virtualPages]);

  const spreadBodyPageOffset = useMemo(() => {
    if (!allMeasured) return 0;
    let offset = 1;
    const startIdx = hasCover ? 1 : 0;
    for (let i = startIdx; i < allContent.length; i++) {
      const ch = allContent[i];
      if (!ch.isCover && !isMatter(ch.chapter.title)) break;
      offset += chapterPageCounts[i] ?? 0;
    }
    return offset;
  }, [allMeasured, allContent, chapterPageCounts, hasCover]);

  // Spread 0 = cover (single), then pairs from index 1 onward
  const totalSpreads = hasCover
    ? 1 + Math.ceil((virtualPages.length - 1) / 2)
    : Math.ceil(virtualPages.length / 2);

  const spreadToPages = useCallback((s: number): [number, number] => {
    if (hasCover) {
      if (s === 0) return [0, -1]; // cover only, -1 = no right page
      const base = 1 + (s - 1) * 2;
      return [
        base < virtualPages.length ? virtualPages[base] : -1,
        base + 1 < virtualPages.length ? virtualPages[base + 1] : -1,
      ];
    }
    return [
      s * 2 < virtualPages.length ? virtualPages[s * 2] : -1,
      s * 2 + 1 < virtualPages.length ? virtualPages[s * 2 + 1] : -1,
    ];
  }, [hasCover, virtualPages]);

  const fmRomanSpread = !!(profile.front_matter_roman && profile.page_numbers_start_at_content);

  const getDisplayPageInfo = useCallback((absPage: number, chapterContent: ChapterContent): { num: number | undefined; roman: boolean } => {
    if (!profile.page_numbers) return { num: undefined, roman: false };
    const isFm = chapterContent.isCover || isFrontMatter(chapterContent.chapter.title);
    const isBm = isBackMatter(chapterContent.chapter.title);
    const bmPn = profile.back_matter_page_numbers ?? true;
    const suppress = isFm || (isBm && !bmPn);
    if (profile.page_numbers_start_at_content) {
      if (suppress) {
        if (fmRomanSpread && isFm && !chapterContent.isCover && !isCentered(chapterContent.chapter.title)) {
          return { num: absPage - (hasCover ? 1 : 0) + 1, roman: true };
        }
        return { num: undefined, roman: false };
      }
      return { num: absPage - spreadBodyPageOffset + 1, roman: false };
    }
    return { num: absPage + 1, roman: false };
  }, [profile.page_numbers, profile.page_numbers_start_at_content, profile.back_matter_page_numbers, spreadBodyPageOffset, fmRomanSpread, hasCover]);

  const resolveAbsolutePage = useCallback(
    (absPage: number): { chapterIndex: number; pageInChapter: number } | null => {
      if (absPage === 0) return null;
      if (!allMeasured) return null;
      // Skip the cover entry (index 0) when counting — it's handled separately
      const startCi = hasCover ? 1 : 0;
      let remaining = absPage - 1;
      for (let ci = startCi; ci < chapterPageCounts.length; ci++) {
        if (remaining < chapterPageCounts[ci]) {
          return { chapterIndex: ci, pageInChapter: remaining };
        }
        remaining -= chapterPageCounts[ci];
      }
      return null;
    },
    [allMeasured, chapterPageCounts, hasCover]
  );

  const absPageToSpread = useCallback((absPage: number): number => {
    if (hasCover && absPage === 0) return 0;
    const vpIdx = virtualPages.indexOf(absPage);
    if (vpIdx < 0) return 0;
    if (hasCover) {
      return 1 + Math.floor((vpIdx - 1) / 2);
    }
    return Math.floor(vpIdx / 2);
  }, [hasCover, virtualPages]);

  useEffect(() => {
    if (!allMeasured) return;
    if (initialChapterIndex === lastReportedChapter.current) return;
    lastReportedChapter.current = initialChapterIndex;
    if (hasCover && initialChapterIndex === 0) { setSpread(0); return; }
    let absPage = hasCover ? 1 : 0;
    const startCi = hasCover ? 1 : 0;
    for (let ci = startCi; ci < initialChapterIndex && ci < chapterPageCounts.length; ci++) {
      absPage += chapterPageCounts[ci];
    }
    setSpread(absPageToSpread(absPage));
  }, [initialChapterIndex, allMeasured, chapterPageCounts, hasCover, absPageToSpread]);

  const isCoverSpread = hasCover && spread === 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const compute = () => {
      const pw = (profile.page_width ?? 6) * 96;
      const ph = (profile.page_height ?? 9) * 96;
      const spreadW = isCoverSpread ? pw : pw * 2 + 2;
      const spreadH = ph;
      const pad = 32;
      const availW = el.clientWidth - pad * 2;
      const availH = el.clientHeight - pad * 2;
      setScale(Math.min(1, availW / spreadW, availH / spreadH));
    };
    compute();
    const observer = new ResizeObserver(compute);
    observer.observe(el);
    return () => observer.disconnect();
  }, [profile.page_width, profile.page_height, isCoverSpread]);

  const [leftPageIdx, rightPageIdx] = spreadToPages(spread);
  const leftResolved = leftPageIdx >= 0 ? resolveAbsolutePage(leftPageIdx) : null;
  const rightResolved = rightPageIdx >= 0 ? resolveAbsolutePage(rightPageIdx) : null;

  useEffect(() => {
    if (!onChapterChange) return;
    let ci: number;
    if (hasCover && spread === 0) { ci = 0; }
    else { ci = rightResolved?.chapterIndex ?? leftResolved?.chapterIndex ?? 0; }
    if (ci !== lastReportedChapter.current) {
      lastReportedChapter.current = ci;
      onChapterChange(ci);
    }
  }, [spread, leftResolved?.chapterIndex, rightResolved?.chapterIndex, onChapterChange, hasCover]);

  const goNext = useCallback(() => {
    setSpread((s) => Math.min(s + 1, totalSpreads - 1));
  }, [totalSpreads]);

  const goPrev = useCallback(() => {
    setSpread((s) => Math.max(s - 1, 0));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || (e.target as HTMLElement).isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); goNext(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); goPrev(); }
      else if (e.key === "Escape") window.history.back();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  const pageWidth = `${profile.page_width ?? 6}in`;
  const pageHeight = `${profile.page_height ?? 9}in`;

  return (
    <div className="flex flex-col h-full">
      {allContent.map((ch, ci) => (
        <MemoizedMeasurer
          key={ci}
          content={ch}
          profile={profile}
          chapterIdx={ci}
          onPageCount={handlePageCount}
        />
      ))}

      <div ref={containerRef} className="flex-1 overflow-hidden flex items-center justify-center">
        <div
          style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
        >
          {hasCover && spread === 0 ? (
            <div className="rounded shadow-2xl overflow-hidden" style={{ width: pageWidth, height: pageHeight }}>
              <PdfChapterPage
                content={allContent[0]}
                profile={profile}
                pageInChapter={0}
                isRecto
              />
            </div>
          ) : (() => {
            const leftContent = leftResolved ? allContent[leftResolved.chapterIndex] : null;
            const rightContent = rightResolved ? allContent[rightResolved.chapterIndex] : null;
            const leftInfo = leftContent ? getDisplayPageInfo(leftPageIdx, leftContent) : { num: undefined, roman: false };
            const rightInfo = rightContent ? getDisplayPageInfo(rightPageIdx, rightContent) : { num: undefined, roman: false };
            return (
            <div className="flex" style={{ gap: "2px" }}>
              <div className="rounded-l shadow-2xl overflow-hidden" style={{ width: pageWidth, height: pageHeight }}>
                {leftResolved && leftContent ? (
                  <PdfChapterPage
                    content={leftContent}
                    profile={profile}
                    pageInChapter={leftResolved.pageInChapter}
                    isRecto={false}
                    displayPageNumber={leftInfo.num}
                    pageContext={{
                      workTitle,
                      workAuthor,
                      chapterTitle: leftContent.chapter.title,
                      chapterNumber: leftContent.chapter.number,
                      isFrontMatter: isFrontMatter(leftContent.chapter.title) || (isBackMatter(leftContent.chapter.title) && !(profile.back_matter_page_numbers ?? true)),
                      roman: leftInfo.roman,
                    }}
                  />
                ) : (
                  <PdfPageShell profile={profile} isRecto={false} />
                )}
              </div>
              <div className="rounded-r shadow-2xl overflow-hidden" style={{ width: pageWidth, height: pageHeight }}>
                {rightResolved && rightContent ? (
                  <PdfChapterPage
                    content={rightContent}
                    profile={profile}
                    pageInChapter={rightResolved.pageInChapter}
                    isRecto
                    displayPageNumber={rightInfo.num}
                    pageContext={{
                      workTitle,
                      workAuthor,
                      chapterTitle: rightContent.chapter.title,
                      chapterNumber: rightContent.chapter.number,
                      isFrontMatter: isFrontMatter(rightContent.chapter.title) || (isBackMatter(rightContent.chapter.title) && !(profile.back_matter_page_numbers ?? true)),
                      roman: rightInfo.roman,
                    }}
                  />
                ) : (
                  <PdfPageShell profile={profile} isRecto />
                )}
              </div>
            </div>
            );
          })()}
        </div>
      </div>

      <footer className="flex items-center justify-between px-6 py-2 bg-gray-900 border-t border-gray-800 shrink-0">
        <button onClick={goPrev} disabled={spread === 0}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          <ChevronLeft size={16} /> Previous
        </button>
        <span className="text-xs text-gray-500">
          {hasCover && spread === 0
            ? `Page 1 of ${totalPages}`
            : (() => {
                const displayLeft = leftPageIdx >= 0 ? leftPageIdx + 1 : null;
                const displayRight = rightPageIdx >= 0 ? rightPageIdx + 1 : null;
                const lo = displayLeft ?? displayRight ?? 1;
                const hi = displayRight ?? displayLeft ?? 1;
                return lo === hi
                  ? `Page ${lo} of ${totalPages}`
                  : `Pages ${lo}–${Math.min(hi, totalPages)} of ${totalPages}`;
              })()}
        </span>
        <button onClick={goNext} disabled={spread >= totalSpreads - 1}
          className="flex items-center gap-1 justify-end text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30 transition-colors w-24">
          Next <ChevronRight size={16} />
        </button>
      </footer>
    </div>
  );
}

export default function ReadingMode() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const chapterParam = searchParams.get("chapter");

  const { data: work, isLoading: workLoading } = useQuery({
    queryKey: ["work", id],
    queryFn: () => getWork(id!),
    enabled: !!id,
  });

  const { data: profiles = [], isLoading: profilesLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const { data: customFonts = [] } = useQuery({
    queryKey: ["fonts"],
    queryFn: listFonts,
  });
  useFontFaceStyles(customFonts);

  const { data: rawContent, isLoading: contentLoading } = useWorkContent(id);
  const content: ChapterContent[] = useMemo(() => {
    const enriched = rawContent.map((entry) => ({
      ...entry,
      titlePageConfig: work?.title_page_config,
      workTitle: work?.title,
      workSubtitle: work?.subtitle,
      workAuthor: work?.author,
    }));
    if (!work?.cover_image_path) return enriched;
    const coverEntry: ChapterContent = {
      chapter: { title: null, number: null, show_title: false },
      scenes: [],
      isCover: true,
      coverUrl: work.cover_image_path,
    };
    return [coverEntry, ...enriched];
  }, [rawContent, work?.cover_image_path, work?.title_page_config, work?.title, work?.subtitle, work?.author]);
  const [chapterIndex, setChapterIndex] = useState(0);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);

  useEffect(() => {
    if (work?.default_profile_id && !selectedProfileId) {
      setSelectedProfileId(work.default_profile_id);
    }
  }, [work, selectedProfileId]);

  useEffect(() => {
    if (chapterParam && content.length > 0) {
      const idx = content.findIndex((c) => c.chapter.id === chapterParam);
      if (idx >= 0) setChapterIndex(idx);
    }
  }, [chapterParam, content]);

  const profile = useMemo(
    () => profiles.find((p) => p.id === selectedProfileId),
    [profiles, selectedProfileId]
  );

  const [twoPage, setTwoPage] = useState(false);
  const isPdf = profile?.format === "pdf";
  const currentChapter = content[chapterIndex];
  const hasNext = chapterIndex < content.length - 1;
  const hasPrev = chapterIndex > 0;

  const [chapterPageCounts, setChapterPageCounts] = useState<Record<number, number>>({});
  const handlePageCount = useCallback((ci: number, count: number) => {
    setChapterPageCounts((prev) => (prev[ci] === count ? prev : { ...prev, [ci]: count }));
  }, []);
  const pageOffset = useMemo(() => {
    let offset = 0;
    for (let i = 0; i < chapterIndex; i++) {
      offset += chapterPageCounts[i] ?? 1;
    }
    return offset;
  }, [chapterIndex, chapterPageCounts]);
  const totalBookPages = useMemo(() => {
    let total = 0;
    for (let i = 0; i < content.length; i++) {
      total += chapterPageCounts[i] ?? 1;
    }
    return total;
  }, [content.length, chapterPageCounts]);
  const bodyPageOffset = useMemo(() => {
    let offset = 0;
    for (let i = 0; i < content.length; i++) {
      const ch = content[i];
      if (!ch.isCover && !isMatter(ch.chapter.title)) break;
      offset += chapterPageCounts[i] ?? 1;
    }
    return offset;
  }, [content, chapterPageCounts]);
  const navDirectionRef = useRef<"backward" | null>(null);
  const goNextChapter = useCallback(() => {
    navDirectionRef.current = null;
    if (hasNext) setChapterIndex((i) => i + 1);
  }, [hasNext]);
  const goPrevChapter = useCallback(() => {
    navDirectionRef.current = "backward";
    if (hasPrev) setChapterIndex((i) => i - 1);
  }, [hasPrev]);

  const isLoading = workLoading || profilesLoading || contentLoading;

  if (!work) return (
    <div className="flex items-center justify-center h-full bg-gray-950">
      <Loader2 size={24} className="animate-spin text-gray-600" />
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-gray-950">
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-4">
          <Link
            to={chapterParam ? `/work/${id}/chapter/${chapterParam}` : `/work/${id}`}
            className="text-gray-400 hover:text-gray-200 transition-colors"
          >
            <ArrowLeft size={18} />
          </Link>
          <span className="text-sm text-gray-300 font-medium">{work.title}</span>
          {content.length > 0 && currentChapter && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setChapterIndex((i) => Math.max(i - 1, 0))}
                disabled={chapterIndex === 0}
                className="text-gray-500 hover:text-gray-300 disabled:opacity-30 transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="text-xs text-gray-500">
                {currentChapter.isCover
                  ? "Cover"
                  : currentChapter.chapter.title
                  ? currentChapter.chapter.title
                  : `Chapter ${currentChapter.chapter.number ?? chapterIndex + 1}`}
              </span>
              <button
                onClick={() => setChapterIndex((i) => Math.min(i + 1, content.length - 1))}
                disabled={chapterIndex === content.length - 1}
                className="text-gray-500 hover:text-gray-300 disabled:opacity-30 transition-colors"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {isPdf && (
            <button
              onClick={() => setTwoPage(!twoPage)}
              className={`p-1.5 rounded transition-colors ${
                twoPage ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300"
              }`}
              title={twoPage ? "Single page view" : "Two-page spread"}
            >
              {twoPage ? <FileText size={14} /> : <Columns2 size={14} />}
            </button>
          )}
          <BookOpen size={14} className="text-gray-500" />
          <select
            value={selectedProfileId ?? ""}
            onChange={(e) => setSelectedProfileId(e.target.value || null)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-indigo-500 focus:outline-none"
          >
            <option value="">Default (ePub)</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.format.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">
        {currentChapter ? (
          isPdf && profile && twoPage ? (
            <PdfSpreadReader
              allContent={content}
              profile={profile}
              initialChapterIndex={chapterIndex}
              workTitle={work.title}
              workAuthor={work.author}
              onChapterChange={setChapterIndex}
            />
          ) : isPdf && profile ? (
            <PdfReader content={currentChapter} profile={profile} chapterIndex={chapterIndex}
              onNextChapter={hasNext ? goNextChapter : undefined}
              onPrevChapter={hasPrev ? goPrevChapter : undefined}
              navDirectionRef={navDirectionRef}
              pageOffset={pageOffset} totalBookPages={totalBookPages}
              onPageCount={handlePageCount}
              workTitle={work.title} workAuthor={work.author}
              bodyPageOffset={bodyPageOffset}
              hasCover={!!work.cover_image_path} />
          ) : (
            <EpubReader content={currentChapter} profile={profile} chapterIndex={chapterIndex}
              onNextChapter={hasNext ? goNextChapter : undefined}
              onPrevChapter={hasPrev ? goPrevChapter : undefined}
              navDirectionRef={navDirectionRef} />
          )
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={24} className="animate-spin text-gray-600" />
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <BookOpen size={48} className="mx-auto mb-4 opacity-30" />
              <p>No content yet.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
