import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import {
  X, Send, Bot, User, Wrench, Plus, History,
  ChevronLeft, Trash2, PenLine, Eye, MessageSquare,
  BookOpen, BookText, FileText, MapPin, Calendar,
  Bug, Package, Clock, Tag, Paperclip, ImageIcon,
  Undo2, CheckCircle,
} from "lucide-react";
import { useQueryClient, useMutation, useQuery } from "@tanstack/react-query";
import { revertScene, clearCheckpoint } from "@/api/comments";
import { listConfig } from "@/api/config";
import { streamChat } from "@/api/ai";
import type { ToolEvent, Mention, ImageAttachment } from "@/api/ai";
import {
  listConversations,
  getConversation,
  deleteConversation,
} from "@/api/conversations";
import type { ConversationListItem, ConversationMessage as StoredMessage } from "@/api/conversations";
import { listCodexEntries } from "@/api/codex";
import { listWorks } from "@/api/works";
import { listChapters } from "@/api/chapters";
import type { CodexEntry, Work, Chapter, Scene } from "@/types";
import Markdown from "react-markdown";

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  images?: { data: string; mime_type: string; name: string }[];
  generatedImage?: { data: string; mime_type: string; url: string };
  checkpoint?: { sceneId: string };
}

interface AIChatPanelProps {
  workId?: string;
  chapterId?: string;
  sceneId?: string;
  onClose: () => void;
}

interface MentionResult {
  type: "codex" | "chapter" | "scene" | "work";
  id: string;
  label: string;
  subtitle: string;
  entryType?: CodexEntry["entry_type"];
  hasImage?: boolean;
}

const CODEX_ICONS: Record<string, typeof User> = {
  character: User,
  location: MapPin,
  event: Calendar,
  species: Bug,
  item: Package,
  timeline: Clock,
  custom: Tag,
};

function MentionIcon({ result, size = 14 }: { result: MentionResult; size?: number }) {
  if (result.type === "work") return <BookOpen size={size} className="text-tc-accent" />;
  if (result.type === "chapter") return <BookText size={size} className="text-tc-accent" />;
  if (result.type === "scene") return <FileText size={size} className="text-emerald-400" />;
  const Icon = CODEX_ICONS[result.entryType || "custom"] || Tag;
  return <Icon size={size} className="text-tc-secondary-accent" />;
}

function MentionDropdown({
  results,
  selectedIndex,
  onSelect,
}: {
  results: MentionResult[];
  selectedIndex: number;
  onSelect: (r: MentionResult) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  // Group results by type
  const grouped = useMemo(() => {
    const groups: { type: string; label: string; items: MentionResult[] }[] = [];
    const order: [string, string][] = [
      ["codex", "Codex"],
      ["work", "Works"],
      ["chapter", "Chapters"],
      ["scene", "Scenes"],
    ];
    for (const [type, label] of order) {
      const items = results.filter((r) => r.type === type);
      if (items.length > 0) groups.push({ type, label, items });
    }
    return groups;
  }, [results]);

  let flatIndex = 0;

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 right-0 mb-1 bg-tc-overlay border border-tc-subtle rounded-lg shadow-xl max-h-56 overflow-y-auto z-50"
    >
      {grouped.length === 0 ? (
        <div className="px-3 py-2 text-xs text-tc-muted">No matches</div>
      ) : (
        grouped.map((group) => (
          <div key={group.type}>
            <div className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-tc-muted">
              {group.label}
            </div>
            {group.items.map((item) => {
              const idx = flatIndex++;
              return (
                <button
                  key={`${item.type}-${item.id}`}
                  data-index={idx}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onSelect(item);
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors ${
                    idx === selectedIndex
                      ? "bg-tc-accent/30 text-tc-primary"
                      : "text-tc-secondary hover:bg-tc-hover/50"
                  }`}
                >
                  <MentionIcon result={item} size={14} />
                  <span className="truncate flex-1">{item.label}</span>
                  <span className="text-[10px] text-tc-muted flex-shrink-0">{item.subtitle}</span>
                </button>
              );
            })}
          </div>
        ))
      )}
    </div>
  );
}

/** Highlight @mentions in rendered user messages */
function HighlightMentions({ text }: { text: string }) {
  const parts = text.split(/(@\S+)/g);
  return (
    <p className="whitespace-pre-wrap">
      {parts.map((part, i) =>
        part.startsWith("@") ? (
          <span key={i} className="text-tc-accent font-medium">{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </p>
  );
}

const PERSONAS: { value: string; label: string; icon: string }[] = [
  { value: "author", label: "Author", icon: "pen" },
  { value: "reviewer", label: "Reviewer", icon: "eye" },
  { value: "advisor", label: "Advisor", icon: "info" },
  { value: "auto", label: "Auto", icon: "bot" },
];

const PERSONA_COLORS: Record<string, string> = {
  author: "text-tc-accent",
  reviewer: "text-tc-secondary-accent",
  advisor: "text-emerald-400",
  auto: "text-tc-tertiary",
};

const ACTION_LABELS: Record<string, string> = {
  created_series: "Created series",
  created_work: "Created work",
  created_chapter: "Created chapter",
  updated_scene: "Updated scene",
  created_codex_entry: "Created codex entry",
  created_codex_bulk: "Created codex entries",
  updated_codex_entry: "Updated codex entry",
  summarized_work: "Summarized work",
  generated_image: "Generated image",
  reviewed_scene: "Reviewed scene",
  reviewed_chapter: "Reviewed chapter",
};

const TOOL_LABELS: Record<string, string> = {
  create_series: "Creating series",
  create_work: "Creating work",
  create_chapter: "Creating chapter",
  write_scene: "Writing scene",
  create_codex_entry: "Creating codex entry",
  bulk_create_codex: "Generating codex entries",
  update_codex_entry: "Updating codex entry",
  summarize_work: "Analyzing work",
  list_works: "Looking up works",
  list_series: "Looking up series",
  list_chapters: "Looking up chapters",
  list_codex_entries: "Looking up codex",
  generate_image: "Generating image",
  review_scene: "Reviewing scene",
  review_chapter: "Reviewing chapter",
};

const THINKING_MESSAGES = [
  "Reading your work",
  "Analyzing content",
  "Thinking",
  "Still working",
  "Processing",
  "Almost there",
];

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatRelativeTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString();
}

function PersonaIcon({ persona, size = 12 }: { persona: string; size?: number }) {
  const cls = PERSONA_COLORS[persona] || "text-tc-tertiary";
  if (persona === "reviewer") return <Eye size={size} className={cls} />;
  if (persona === "advisor") return <MessageSquare size={size} className={cls} />;
  if (persona === "author") return <PenLine size={size} className={cls} />;
  return <Bot size={size} className={cls} />;
}

function ThinkingIndicator({ activeTool }: { activeTool: string | null }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    startRef.current = Date.now();
    setElapsed(0);
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const phase = Math.min(Math.floor(elapsed / 8), THINKING_MESSAGES.length - 1);
  const label = activeTool
    ? TOOL_LABELS[activeTool] || activeTool
    : THINKING_MESSAGES[phase];

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg bg-tc-overlay/30 border border-tc-subtle/30">
      <div className="relative flex items-center justify-center w-5 h-5">
        <div className="absolute inset-0 rounded-full border-2 border-tc-accent/30" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-indigo-500 animate-spin" />
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-xs text-tc-tertiary">
          {label}
          <span className="animate-pulse">...</span>
        </span>
      </div>
      <span className="text-xs text-tc-muted tabular-nums flex-shrink-0">
        {formatElapsed(elapsed)}
      </span>
    </div>
  );
}

function ConversationHistoryView({
  workId,
  onSelect,
  onNew,
  onBack,
}: {
  workId?: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onBack: () => void;
}) {
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listConversations(workId).then((data) => {
      setConversations(data);
      setLoading(false);
    });
  }, [workId]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-tc-subtle">
        <button
          onClick={onBack}
          className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-sm font-medium">Conversations</span>
        <button
          onClick={onNew}
          className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
          title="New conversation"
        >
          <Plus size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-center py-8 text-tc-muted text-sm">Loading...</p>
        ) : conversations.length === 0 ? (
          <p className="text-center py-8 text-tc-muted text-sm">No conversations yet</p>
        ) : (
          <div className="py-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-tc-overlay/50 cursor-pointer group transition-colors"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <PersonaIcon persona={conv.persona} size={14} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-tc-secondary truncate">{conv.title}</p>
                    <p className="text-xs text-tc-muted">
                      {conv.message_count} msgs · {formatRelativeTime(conv.updated_at)}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="p-1 text-tc-muted hover:text-tc-error opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AIChatPanel({ workId, chapterId, sceneId, onClose }: AIChatPanelProps) {
  const queryClient = useQueryClient();
  const { data: configEntries = [] } = useQuery({ queryKey: ["config"], queryFn: listConfig });
  const activeModel = useMemo(() => {
    const getVal = (key: string) => configEntries.find((c) => c.key === key)?.value ?? "";
    const provider = getVal("ai_provider");
    if (provider === "bedrock") return getVal("bedrock_model_id");
    if (provider === "openai") return getVal("openai_model") || "gpt-4o";
    return getVal("anthropic_model") || "claude-sonnet-4-20250514";
  }, [configEntries]);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [receivedTokens, setReceivedTokens] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [persona, setPersona] = useState("author");
  const [resolvedPersona, setResolvedPersona] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Attachment state
  const [attachments, setAttachments] = useState<ImageAttachment[]>([]);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Image preview modal
  const [previewImage, setPreviewImage] = useState<{ url: string; alt?: string } | null>(null);

  // Mention state
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionAnchor, setMentionAnchor] = useState<number | null>(null);
  const [showMentionMenu, setShowMentionMenu] = useState(false);
  const [mentionMenuIndex, setMentionMenuIndex] = useState(0);
  const [mentionResults, setMentionResults] = useState<MentionResult[]>([]);

  // Search mentions across cached TanStack Query data, falling back to fetch
  const searchMentions = useCallback(async (query: string): Promise<MentionResult[]> => {
    const q = query.toLowerCase();
    const results: MentionResult[] = [];

    // Codex entries - try cache first, then fetch
    let codexEntries: CodexEntry[] | undefined;
    const codexQueries = queryClient.getQueriesData<CodexEntry[]>({ queryKey: ["codex"] });
    for (const [, data] of codexQueries) {
      if (data && data.length > 0) { codexEntries = data; break; }
    }
    if (!codexEntries) {
      try { codexEntries = await listCodexEntries(workId ? { workId } : undefined); } catch { /* ignore */ }
    }
    if (codexEntries) {
      for (const entry of codexEntries) {
        if (entry.name.toLowerCase().includes(q)) {
          results.push({
            type: "codex",
            id: entry.id,
            label: entry.name,
            subtitle: entry.entry_type.charAt(0).toUpperCase() + entry.entry_type.slice(1),
            entryType: entry.entry_type,
            hasImage: !!entry.primary_image_url,
          });
        }
      }
    }

    // Works - try cache first, then fetch
    let works: Work[] | undefined;
    const worksCache = queryClient.getQueryData<Work[]>(["works"]);
    if (worksCache) { works = worksCache; }
    if (!works) {
      try { works = await listWorks(); } catch { /* ignore */ }
    }
    if (works) {
      for (const w of works) {
        if (w.title.toLowerCase().includes(q)) {
          results.push({ type: "work", id: w.id, label: w.title, subtitle: "Work" });
        }
      }
    }

    // Chapters — search across all works, include work title for disambiguation
    const workTitles: Record<string, string> = {};
    if (works) {
      for (const w of works) workTitles[w.id] = w.title;
    }

    const searchWorkIds = workId ? [workId] : (works || []).map((w) => w.id);
    for (const wid of searchWorkIds) {
      let chapters: Chapter[] | undefined;
      const chaptersCache = queryClient.getQueryData<Chapter[]>(["chapters", { workId: wid }]);
      if (chaptersCache) { chapters = chaptersCache; }
      if (!chapters) {
        try { chapters = await listChapters(wid); } catch { /* ignore */ }
      }
      if (chapters) {
        const wTitle = workTitles[wid] || "Unknown Work";
        for (const ch of chapters) {
          const chTitle = ch.title || `Chapter ${ch.number ?? ch.sort_order}`;
          if (chTitle.toLowerCase().includes(q)) {
            results.push({
              type: "chapter",
              id: ch.id,
              label: chTitle,
              subtitle: `Ch ${ch.number ?? ch.sort_order} · ${wTitle}`,
            });
          }
        }
      }

      // Scenes from this work's cached scene data
      const sceneQueries = queryClient.getQueriesData<Scene[]>({ queryKey: ["scenes"] });
      for (const [, data] of sceneQueries) {
        if (data) {
          for (const sc of data) {
            if (sc.title && sc.title.toLowerCase().includes(q)) {
              if (!results.some((r) => r.type === "scene" && r.id === sc.id)) {
                results.push({
                  type: "scene",
                  id: sc.id,
                  label: sc.title,
                  subtitle: `Scene · ${workTitles[wid] || "Unknown Work"}`,
                });
              }
            }
          }
        }
      }
    }

    return results.slice(0, 20);
  }, [queryClient, workId]);

  // Update mention search results when query changes
  useEffect(() => {
    if (mentionQuery === null || mentionQuery === "") {
      // Show all results when query is empty (just typed @)
      if (mentionQuery === "") {
        searchMentions("").then((r) => {
          setMentionResults(r);
          setMentionMenuIndex(0);
        });
      } else {
        setMentionResults([]);
      }
      return;
    }
    const timer = setTimeout(() => {
      searchMentions(mentionQuery).then((r) => {
        setMentionResults(r);
        setMentionMenuIndex(0);
      });
    }, 100);
    return () => clearTimeout(timer);
  }, [mentionQuery, searchMentions]);

  const closeMentionMenu = useCallback(() => {
    setShowMentionMenu(false);
    setMentionQuery(null);
    setMentionAnchor(null);
    setMentionResults([]);
    setMentionMenuIndex(0);
  }, []);

  const insertMention = useCallback((result: MentionResult) => {
    if (mentionAnchor === null) return;
    const before = input.slice(0, mentionAnchor);
    const cursorPos = inputRef.current?.selectionStart ?? input.length;
    const after = input.slice(cursorPos);
    const mentionText = `@${result.label} `;
    const newInput = before + mentionText + after;
    setInput(newInput);
    setMentions((prev) => {
      // Avoid duplicates
      if (prev.some((m) => m.type === result.type && m.id === result.id)) return prev;
      return [...prev, { type: result.type, id: result.id, label: result.label, hasImage: result.hasImage }];
    });
    closeMentionMenu();
    // Restore cursor position after React re-render
    const newCursorPos = before.length + mentionText.length;
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  }, [input, mentionAnchor, closeMentionMenu]);

  const removeMention = useCallback((idx: number) => {
    setMentions((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  useEffect(() => {
    let cancelled = false;
    listConversations(workId).then((convs) => {
      if (cancelled || convs.length === 0) return;
      const sorted = [...convs].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );
      loadConversation(sorted[0].id);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    inputRef.current?.focus();
  }, [showHistory]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming, activeTool]);

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["works"] });
    queryClient.invalidateQueries({ queryKey: ["series"] });
    queryClient.invalidateQueries({ queryKey: ["chapters"] });
    queryClient.invalidateQueries({ queryKey: ["scenes"] });
    queryClient.invalidateQueries({ queryKey: ["codex"] });
    queryClient.invalidateQueries({ queryKey: ["comments"] });
    if (workId) {
      queryClient.invalidateQueries({ queryKey: ["work", workId] });
      queryClient.invalidateQueries({ queryKey: ["images", workId] });
    }
  }, [queryClient, workId]);

  const revertMutation = useMutation({
    mutationFn: revertScene,
    onSuccess: (_data, sceneId) => {
      invalidateAll();
      setMessages((prev) =>
        prev.map((m) =>
          m.checkpoint?.sceneId === sceneId ? { ...m, checkpoint: undefined } : m
        )
      );
    },
  });

  const acceptMutation = useMutation({
    mutationFn: clearCheckpoint,
    onSuccess: (_data, sceneId) => {
      invalidateAll();
      setMessages((prev) =>
        prev.map((m) =>
          m.checkpoint?.sceneId === sceneId ? { ...m, checkpoint: undefined } : m
        )
      );
    },
  });

  const loadConversation = useCallback(async (id: string) => {
    try {
      const conv = await getConversation(id);
      setConversationId(conv.id);
      setPersona(conv.persona);
      setResolvedPersona(null);
      const loaded: Message[] = conv.messages.map((m: StoredMessage) => {
        if (m.role === "tool") {
          let toolName: string | undefined;
          try {
            const parsed = JSON.parse(m.content);
            toolName = parsed.tool;
          } catch { /* ignore */ }
          const label = toolName ? (ACTION_LABELS[`created_${toolName}`] || TOOL_LABELS[toolName] || toolName) : "Tool";
          return { role: "tool" as const, content: label, toolName };
        }
        return { role: m.role as "user" | "assistant", content: m.content };
      });
      setMessages(loaded);
      setShowHistory(false);
    } catch {
      /* ignore */
    }
  }, []);

  const startNewConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setResolvedPersona(null);
    setShowHistory(false);
  }, []);

  const handleImageAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(",")[1];
        setAttachments(prev => [...prev, {
          data: base64,
          mime_type: file.type,
          name: file.name,
        }]);
      };
      reader.readAsDataURL(file);
    }
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const handleSend = async () => {
    const prompt = input.trim();
    if (!prompt || streaming) return;

    const currentMentions = mentions;
    const currentAttachments = attachments;
    setInput("");
    setMentions([]);
    setAttachments([]);
    closeMentionMenu();
    setMessages((prev) => [...prev, {
      role: "user",
      content: prompt,
      images: currentAttachments.length > 0 ? currentAttachments : undefined,
    }]);
    setStreaming(true);
    setActiveTool(null);
    setReceivedTokens(false);

    let assistantContent = "";
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    await streamChat(
      {
        prompt,
        work_id: workId,
        chapter_id: chapterId,
        scene_id: sceneId,
        conversation_id: conversationId || undefined,
        persona,
        mentions: currentMentions.length > 0
          ? currentMentions.map((m) => ({ type: m.type, id: m.id }))
          : undefined,
        attachments: currentAttachments.length > 0 ? currentAttachments : undefined,
      },
      {
        onToken: (token) => {
          assistantContent += token;
          setReceivedTokens(true);
          setActiveTool(null);
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: assistantContent };
            return updated;
          });
        },
        onDone: () => {
          setStreaming(false);
          setActiveTool(null);
          setReceivedTokens(false);
          invalidateAll();
        },
        onError: (err) => {
          const errorMsg = assistantContent
            ? assistantContent
            : `**Error:** ${err}`;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: errorMsg };
            return updated;
          });
          setStreaming(false);
          setActiveTool(null);
          setReceivedTokens(false);
        },
        onToolStart: (event: ToolEvent) => {
          const label = TOOL_LABELS[event.tool] || event.tool;
          setMessages((prev) => [
            ...prev,
            { role: "tool", content: `${label}...`, toolName: event.tool, toolInput: event.input },
          ]);
          assistantContent = "";
          setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
          setActiveTool(event.tool);
          setReceivedTokens(false);
        },
        onToolResult: (event: ToolEvent) => {
          const result = event.result || {};
          const action = result.action as string | undefined;
          const label = (action && ACTION_LABELS[action]) || "Done";
          const count = result.count as number | undefined;
          const title = (result.title as string) || (result.name as string) || "";
          const summary = count
            ? `${label}: **${count} entries**`
            : title ? `${label}: **${title}**` : label;
          const hasImage = result.has_image as boolean | undefined;
          const imageUrl = result.url as string | undefined;
          const imageMime = (result.mime_type as string) || "image/png";
          const checkpointed = result.checkpointed as boolean | undefined;
          const sceneId = result.scene_id as string | undefined;
          setMessages((prev) => {
            const updated = [...prev];
            let toolIdx = -1;
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].role === "tool") { toolIdx = i; break; }
            }
            if (toolIdx >= 0) {
              updated[toolIdx] = {
                ...updated[toolIdx],
                content: summary,
                ...(hasImage && imageUrl ? {
                  generatedImage: { data: "", mime_type: imageMime, url: imageUrl },
                } : {}),
                ...(checkpointed && sceneId ? {
                  checkpoint: { sceneId },
                } : {}),
              };
            }
            return updated;
          });
          setActiveTool(null);
          invalidateAll();
        },
        onConversation: (event) => {
          setConversationId(event.id);
          if (event.persona !== persona) {
            setResolvedPersona(event.persona);
          }
        },
      },
    );
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    const cursorPos = e.target.selectionStart ?? val.length;
    setInput(val);

    // Detect @ mention trigger
    // Look backwards from cursor for an unescaped @ that starts a mention query
    const textBeforeCursor = val.slice(0, cursorPos);
    const atIdx = textBeforeCursor.lastIndexOf("@");
    if (atIdx >= 0) {
      // Check that @ is at start of input or preceded by whitespace
      const charBefore = atIdx > 0 ? textBeforeCursor[atIdx - 1] : " ";
      if (charBefore === " " || charBefore === "\n" || atIdx === 0) {
        const queryText = textBeforeCursor.slice(atIdx + 1);
        // Only treat as mention if the query has no spaces (single token after @)
        // or allow multi-word search up to a limit
        if (!queryText.includes("\n") && queryText.length <= 40) {
          setMentionQuery(queryText);
          setMentionAnchor(atIdx);
          setShowMentionMenu(true);
          return;
        }
      }
    }
    // No active mention
    if (showMentionMenu) closeMentionMenu();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showMentionMenu && mentionResults.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionMenuIndex((prev) => Math.min(prev + 1, mentionResults.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionMenuIndex((prev) => Math.max(prev - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(mentionResults[mentionMenuIndex]);
        return;
      }
    }
    if (e.key === "Escape" && showMentionMenu) {
      e.preventDefault();
      closeMentionMenu();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const showThinking = streaming && !receivedTokens;
  const displayPersona = resolvedPersona || persona;

  if (showHistory) {
    return (
      <div className="flex flex-col h-full bg-tc-base border-l border-tc-subtle">
        <ConversationHistoryView
          workId={workId}
          onSelect={loadConversation}
          onNew={startNewConversation}
          onBack={() => setShowHistory(false)}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-tc-base border-l border-tc-subtle">
      <div className="flex items-center justify-between px-4 py-3 border-b border-tc-subtle">
        <div className="flex items-center gap-2">
          <PersonaIcon persona={displayPersona} size={16} />
          <select
            value={persona}
            onChange={(e) => {
              setPersona(e.target.value);
              setResolvedPersona(null);
            }}
            disabled={streaming}
            className="bg-transparent text-sm font-medium text-tc-secondary focus:outline-none cursor-pointer appearance-none pr-4"
            style={{ backgroundImage: "url(\"data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e\")", backgroundPosition: "right 0 center", backgroundRepeat: "no-repeat", backgroundSize: "1.25em 1.25em" }}
          >
            {PERSONAS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          {resolvedPersona && persona === "auto" && (
            <span className="text-xs text-tc-muted">
              → {resolvedPersona}
            </span>
          )}
          {activeModel && (
            <span className="text-xs text-tc-muted truncate max-w-[140px]" title={activeModel}>
              {activeModel.replace(/^us\.(anthropic|amazon|meta)\./, "").split(":")[0].replace(/-v\d+$/, "")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowHistory(true)}
            className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            title="Conversation history"
          >
            <History size={16} />
          </button>
          <button
            onClick={startNewConversation}
            className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
            title="New conversation"
          >
            <Plus size={16} />
          </button>
          <button
            onClick={onClose}
            className="p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-8 text-tc-muted">
            <Bot size={32} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">
              Ask me to create works, write chapters, build your codex, summarize content, or brainstorm ideas.
            </p>
            <div className="mt-4 flex justify-center gap-2">
              {PERSONAS.filter((p) => p.value !== "auto").map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPersona(p.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    persona === p.value
                      ? "bg-tc-hover text-tc-secondary"
                      : "bg-tc-overlay/50 text-tc-muted hover:text-tc-secondary"
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <PersonaIcon persona={p.value} size={10} />
                    {p.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === "tool" ? (
              <div>
                <div className="py-1.5 px-3 rounded bg-tc-overlay/50 border border-tc-subtle/50 text-xs text-tc-tertiary">
                  <div className="flex items-center gap-2">
                    <Wrench size={12} className="text-tc-accent flex-shrink-0" />
                    <span className="prose prose-invert prose-sm max-w-none">
                      <Markdown>{msg.content}</Markdown>
                    </span>
                  </div>
                  {msg.checkpoint && (
                    <div className="flex items-center gap-2 mt-1.5 pt-1.5 border-t border-tc-subtle/50">
                      <span className="text-[10px] text-tc-muted">Scene checkpointed</span>
                      <button
                        onClick={() => revertMutation.mutate(msg.checkpoint!.sceneId)}
                        disabled={revertMutation.isPending}
                        className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-tc-secondary-accent hover:text-tc-secondary-accent bg-tc-secondary-subtle hover:bg-tc-secondary-subtle rounded transition-colors disabled:opacity-50"
                      >
                        <Undo2 size={10} /> Revert
                      </button>
                      <button
                        onClick={() => acceptMutation.mutate(msg.checkpoint!.sceneId)}
                        disabled={acceptMutation.isPending}
                        className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-tc-success hover:text-tc-success bg-tc-success-subtle hover:bg-tc-success-subtle rounded transition-colors disabled:opacity-50"
                      >
                        <CheckCircle size={10} /> Accept
                      </button>
                    </div>
                  )}
                  {msg.toolInput && Object.keys(msg.toolInput).length > 0 && (
                    <details className="mt-1.5">
                      <summary className="cursor-pointer text-tc-muted hover:text-tc-tertiary text-[10px] uppercase tracking-wider select-none">
                        Tool input
                      </summary>
                      <pre className="mt-1 text-[10px] text-tc-muted whitespace-pre-wrap break-all bg-tc-base/50 rounded p-2 max-h-40 overflow-y-auto">
                        {JSON.stringify(msg.toolInput, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
                {msg.generatedImage && (
                  <div className="mt-1.5">
                    <img
                      src={msg.generatedImage.url || `data:${msg.generatedImage.mime_type};base64,${msg.generatedImage.data}`}
                      alt="AI generated"
                      className="max-w-[280px] rounded-lg border border-tc-subtle cursor-pointer hover:border-tc-accent transition-colors"
                      onClick={() => setPreviewImage({ url: msg.generatedImage!.url || `data:${msg.generatedImage!.mime_type};base64,${msg.generatedImage!.data}` })}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className={`flex gap-2 ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role === "assistant" && (
                  <div className="flex-shrink-0 w-6 h-6 rounded bg-tc-accent/20 flex items-center justify-center mt-0.5">
                    <PersonaIcon persona={displayPersona} />
                  </div>
                )}
                {(msg.content || msg.role !== "assistant") && (
                  <div
                    className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-tc-accent/30 text-tc-secondary"
                        : "bg-tc-overlay text-tc-secondary"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-invert prose-sm max-w-none">
                        <Markdown>{msg.content}</Markdown>
                      </div>
                    ) : (
                      <>
                        {msg.images && msg.images.length > 0 && (
                          <div className="flex gap-1.5 mb-1.5 flex-wrap">
                            {msg.images.map((img, j) => (
                              <img
                                key={j}
                                src={`data:${img.mime_type};base64,${img.data}`}
                                alt={img.name}
                                className="w-20 h-20 object-cover rounded"
                              />
                            ))}
                          </div>
                        )}
                        <HighlightMentions text={msg.content} />
                      </>
                    )}
                  </div>
                )}
                {msg.role === "user" && (
                  <div className="flex-shrink-0 w-6 h-6 rounded bg-tc-hover flex items-center justify-center mt-0.5">
                    <User size={12} className="text-tc-tertiary" />
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {showThinking && <ThinkingIndicator activeTool={activeTool} />}
      </div>

      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setPreviewImage(null)}
        >
          <div
            className="relative max-w-[90vw] max-h-[90vh]"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={previewImage.url}
              alt={previewImage.alt || "Generated image"}
              className="max-w-full max-h-[85vh] rounded-lg"
            />
            <div className="absolute top-2 right-2 flex gap-1">
              <button
                onClick={async () => {
                  try {
                    const resp = await fetch(previewImage.url);
                    const blob = await resp.blob();
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = blobUrl;
                    a.download = "generated-image.png";
                    a.click();
                    URL.revokeObjectURL(blobUrl);
                  } catch { /* ignore */ }
                }}
                className="p-1.5 bg-tc-base/80 hover:bg-tc-overlay rounded-lg text-tc-secondary hover:text-tc-primary transition-colors"
                title="Download"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              </button>
              <button
                onClick={() => setPreviewImage(null)}
                className="p-1.5 bg-tc-base/80 hover:bg-tc-overlay rounded-lg text-tc-secondary hover:text-tc-primary transition-colors"
                title="Close"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="border-t border-tc-subtle p-3">
        {mentions.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {mentions.map((m, i) => (
              <span
                key={`${m.type}-${m.id}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tc-accent/20 text-tc-accent text-xs border border-tc-accent/30"
              >
                <MentionIcon result={{ ...m, subtitle: "", type: m.type }} size={10} />
                {m.label}
                {m.hasImage && <ImageIcon size={10} className="text-tc-accent/50" />}
                <button
                  onClick={() => removeMention(i)}
                  className="ml-0.5 hover:text-tc-accent transition-colors"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}
        {attachments.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {attachments.map((att, i) => (
              <div key={i} className="relative group">
                <img
                  src={`data:${att.mime_type};base64,${att.data}`}
                  alt={att.name}
                  className="w-16 h-16 object-cover rounded-lg border border-tc-subtle"
                />
                <button
                  onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))}
                  className="absolute -top-1.5 -right-1.5 p-0.5 bg-tc-overlay border border-tc-subtle rounded-full text-tc-tertiary hover:text-tc-error opacity-0 group-hover:opacity-100 transition-all"
                >
                  <X size={10} />
                </button>
                <span className="absolute bottom-0 left-0 right-0 bg-black/60 text-[9px] text-tc-secondary text-center truncate px-1 rounded-b-lg">
                  {att.name}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="relative">
          {showMentionMenu && (
            <MentionDropdown
              results={mentionResults}
              selectedIndex={mentionMenuIndex}
              onSelect={insertMention}
            />
          )}
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onBlur={() => {
                // Delay to allow click events on the dropdown to fire
                setTimeout(() => {
                  if (showMentionMenu) closeMentionMenu();
                }, 200);
              }}
              placeholder="Ask the AI... (@ to mention)"
              rows={2}
              className="flex-1 bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm resize-none focus:border-tc-accent focus:outline-none"
            />
            <button
              onClick={() => imageInputRef.current?.click()}
              disabled={streaming}
              className="self-end p-2 text-tc-muted hover:text-tc-secondary transition-colors"
              title="Attach image"
            >
              <Paperclip size={16} />
            </button>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageAttach}
              className="hidden"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              className="self-end p-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
