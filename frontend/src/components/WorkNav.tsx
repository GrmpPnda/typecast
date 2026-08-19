import { useQuery } from "@tanstack/react-query";
import { NavLink, useParams, useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, FileText, PenLine, BookOpen, Layers, Tag, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { getWork } from "@/api/works";
import { listChapters } from "@/api/chapters";
import { listScenes } from "@/api/scenes";
import { listSections } from "@/api/sections";
import { listCodexEntries } from "@/api/codex";
import { Chapter, CodexEntry } from "@/types";
import { useState, useEffect, useRef } from "react";

const MATTER_TITLES = new Set([
  "dedication", "preface", "foreword", "introduction", "prologue",
  "epilogue", "afterword", "acknowledgments", "acknowledgements",
  "appendix", "glossary", "bibliography", "about the author",
  "also by", "colophon", "copyright", "half title", "title page",
]);

function useVisibleSceneId() {
  const [visibleId, setVisibleId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    const visibleEntries = new Map<string, number>();

    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.sceneId;
          if (!id) continue;
          if (entry.isIntersecting) {
            visibleEntries.set(id, entry.intersectionRatio);
          } else {
            visibleEntries.delete(id);
          }
        }
        let bestId: string | null = null;
        let bestRatio = 0;
        for (const [id, ratio] of visibleEntries) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestId = id;
          }
        }
        if (bestId) setVisibleId(bestId);
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] }
    );

    const observe = () => {
      const blocks = document.querySelectorAll(".scene-block[data-scene-id]");
      blocks.forEach((el) => observerRef.current?.observe(el));
    };

    observe();
    const mo = new MutationObserver(observe);
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      observerRef.current?.disconnect();
      mo.disconnect();
    };
  }, []);

  return visibleId;
}

const FRONT_SET = new Set([
  "half title", "title page", "copyright", "dedication", "epigraph",
  "table of contents", "foreword", "preface", "acknowledgments",
  "acknowledgements", "introduction", "prologue",
]);

const BACK_SET = new Set([
  "epilogue", "afterword", "appendix", "glossary", "bibliography",
  "about the author", "also by", "colophon", "index",
]);

function isMatter(title: string | null): boolean {
  if (!title) return false;
  return MATTER_TITLES.has(title.toLowerCase().trim());
}

function classifyChapter(ch: Chapter): "front" | "back" | "body" {
  const t = (ch.title ?? "").toLowerCase().trim();
  if (FRONT_SET.has(t)) return "front";
  if (BACK_SET.has(t)) return "back";
  return "body";
}

function ChapterItem({ workId, chapter, readingMode }: { workId: string; chapter: Chapter; readingMode?: boolean }) {
  const { chapterId } = useParams();
  const navigate = useNavigate();
  const visibleSceneId = useVisibleSceneId();
  const isActiveChapter = chapterId === chapter.id;
  const [expanded, setExpanded] = useState(true);
  const matter = isMatter(chapter.title);

  const { data: scenes = [] } = useQuery({
    queryKey: ["scenes", { chapterId: chapter.id }],
    queryFn: () => listScenes(chapter.id),
  });

  const chapterHref = readingMode
    ? `/work/${workId}/read?chapter=${chapter.id}`
    : `/work/${workId}/chapter/${chapter.id}`;

  const handleChapterClick = readingMode
    ? (e: React.MouseEvent) => {
        e.preventDefault();
        navigate(`/work/${workId}/read?chapter=${chapter.id}`, { replace: true });
      }
    : undefined;

  return (
    <div>
      <div className="flex items-center">
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-0.5 text-tc-muted hover:text-tc-tertiary transition-colors"
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <NavLink
          to={chapterHref}
          onClick={handleChapterClick}
          className={`flex-1 flex items-center gap-2 px-2 py-1 rounded text-sm truncate transition-colors ${
            isActiveChapter
              ? "bg-tc-accent/20 text-tc-accent"
              : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50"
          }`}
        >
          <FileText size={13} className="shrink-0" />
          <span className="truncate">
            {chapter.title || `Chapter ${chapter.number ?? ""}`}
          </span>
        </NavLink>
      </div>
      {expanded && scenes.length > 0 && !readingMode && (
        <div className="ml-5 border-l border-tc-default pl-2 mt-0.5 space-y-0.5">
          {scenes.map((scene, idx) => {
            const isVisible = isActiveChapter && visibleSceneId === scene.id;
            return (
              <a
                key={scene.id}
                href={`/work/${workId}/chapter/${chapter.id}#scene-${scene.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  if (isActiveChapter) {
                    document
                      .getElementById(`scene-${scene.id}`)
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  } else {
                    navigate(
                      `/work/${workId}/chapter/${chapter.id}#scene-${scene.id}`
                    );
                  }
                }}
                className={`flex items-center gap-2 px-2 py-1 rounded text-xs truncate transition-colors ${
                  isVisible
                    ? "bg-tc-accent/20 text-tc-accent"
                    : "text-tc-muted hover:text-tc-secondary hover:bg-tc-overlay/50"
                }`}
              >
                <PenLine size={11} className="shrink-0" />
                <span className="truncate">
                  {scene.title || (matter ? "Content" : `Scene ${idx + 1}`)}
                </span>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

const ENTRY_TYPE_ICONS: Record<CodexEntry["entry_type"], string> = {
  character: "C",
  location: "L",
  event: "E",
  species: "S",
  item: "I",
  timeline: "T",
  custom: "?",
};

function CollapsibleSection({
  icon: Icon,
  label,
  defaultOpen = true,
  children,
}: {
  icon: typeof Layers;
  label: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-tc-muted hover:text-tc-secondary transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Icon size={13} />
        {label}
      </button>
      {open && <div className="mt-0.5 ml-3 border-l border-tc-default pl-1">{children}</div>}
    </div>
  );
}

export default function WorkNav({ workId, readingMode, collapsed, onToggle }: { workId: string; readingMode?: boolean; collapsed?: boolean; onToggle?: () => void }) {
  const { id: routeWorkId } = useParams();

  const { data: work } = useQuery({
    queryKey: ["work", workId],
    queryFn: () => getWork(workId),
    enabled: !!workId,
  });

  const { data: chapters = [] } = useQuery({
    queryKey: ["chapters", { workId }],
    queryFn: () => listChapters(workId),
    enabled: !!workId,
  });

  const { data: sections = [] } = useQuery({
    queryKey: ["sections", { workId }],
    queryFn: () => listSections(workId),
    enabled: !!workId,
  });

  const { data: codexEntries = [] } = useQuery({
    queryKey: ["codex", { workId }],
    queryFn: () => listCodexEntries({ workId }),
    enabled: !!workId,
  });

  const { sectionId } = useParams<{ sectionId?: string }>();
  const frontSections = sections.filter((s) => s.placement === "front_matter");
  const backSections = sections.filter((s) => s.placement === "back_matter");
  const frontChapters = chapters.filter((ch) => classifyChapter(ch) === "front");
  const bodyChapters = chapters.filter((ch) => classifyChapter(ch) === "body");
  const backChapters = chapters.filter((ch) => classifyChapter(ch) === "back");

  if (!work) return null;

  if (collapsed) {
    return (
      <div className="flex flex-col h-full">
        <div className="p-2 border-b border-tc-default flex items-center justify-center min-h-[57px]">
          <button
            onClick={onToggle}
            className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            title="Expand book nav"
          >
            <PanelLeftOpen size={16} />
          </button>
        </div>
      </div>
    );
  }

  const sectionLabel = (s: (typeof sections)[0]) =>
    s.title || s.section_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-tc-default">
        <NavLink
          to={`/work/${workId}`}
          className={`flex-1 min-w-0 transition-colors ${
            routeWorkId === workId
              ? "text-tc-primary"
              : "text-tc-secondary hover:text-tc-primary"
          }`}
        >
          <h2 className="text-sm font-semibold truncate">{work.title}</h2>
          {work.author && (
            <p className="text-xs text-tc-muted truncate mt-0.5">{work.author}</p>
          )}
        </NavLink>
        {onToggle && (
          <button
            onClick={onToggle}
            className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors shrink-0 ml-2"
            title="Collapse book nav"
          >
            <PanelLeftClose size={16} />
          </button>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-2">
        <CollapsibleSection icon={Layers} label="Content">
          <div className="space-y-0.5">
            {frontChapters.map((chapter) => (
              <ChapterItem key={chapter.id} workId={workId} chapter={chapter} readingMode={readingMode} />
            ))}
            {frontSections.map((s) => (
              <NavLink
                key={s.id}
                to={`/work/${workId}/section/${s.id}`}
                className={`flex items-center gap-2 px-2 py-1 rounded text-sm truncate transition-colors ${
                  sectionId === s.id
                    ? "bg-tc-accent/20 text-tc-accent"
                    : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50"
                }`}
              >
                <BookOpen size={13} className="shrink-0" />
                <span className="truncate">{sectionLabel(s)}</span>
              </NavLink>
            ))}
            {bodyChapters.map((chapter) => (
              <ChapterItem key={chapter.id} workId={workId} chapter={chapter} readingMode={readingMode} />
            ))}
            {backChapters.map((chapter) => (
              <ChapterItem key={chapter.id} workId={workId} chapter={chapter} readingMode={readingMode} />
            ))}
            {backSections.map((s) => (
              <NavLink
                key={s.id}
                to={`/work/${workId}/section/${s.id}`}
                className={`flex items-center gap-2 px-2 py-1 rounded text-sm truncate transition-colors ${
                  sectionId === s.id
                    ? "bg-tc-accent/20 text-tc-accent"
                    : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50"
                }`}
              >
                <BookOpen size={13} className="shrink-0" />
                <span className="truncate">{sectionLabel(s)}</span>
              </NavLink>
            ))}
          </div>
        </CollapsibleSection>

        {!readingMode && (
          <CollapsibleSection icon={Tag} label="Codex" defaultOpen={codexEntries.length > 0}>
            <div className="space-y-0.5">
              {codexEntries.map((entry) => (
                <NavLink
                  key={entry.id}
                  to={`/codex/${entry.id}`}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-2 py-1 rounded text-sm truncate transition-colors ${
                      isActive
                        ? "bg-tc-accent/20 text-tc-accent"
                        : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50"
                    }`
                  }
                >
                  <span className="shrink-0 w-4 h-4 rounded text-[10px] font-bold flex items-center justify-center bg-tc-overlay text-tc-muted">
                    {ENTRY_TYPE_ICONS[entry.entry_type]}
                  </span>
                  <span className="truncate">{entry.name}</span>
                </NavLink>
              ))}
              <NavLink
                to={`/codex?work=${workId}`}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors ${
                    isActive
                      ? "text-tc-accent"
                      : "text-tc-muted hover:text-tc-tertiary"
                  }`
                }
              >
                View all &rarr;
              </NavLink>
            </div>
          </CollapsibleSection>
        )}
      </nav>
    </div>
  );
}
