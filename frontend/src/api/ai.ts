export interface ImageAttachment {
  data: string; // base64
  mime_type: string;
  name: string;
}

export interface Mention {
  type: "codex" | "chapter" | "scene" | "work";
  id: string;
  label: string;
  hasImage?: boolean;
}

export interface AIChatRequest {
  prompt: string;
  work_id?: string;
  chapter_id?: string;
  scene_id?: string;
  conversation_id?: string;
  persona?: string;
  mentions?: { type: string; id: string }[];
  attachments?: { data: string; mime_type: string; name: string }[];
}

export interface ToolEvent {
  tool: string;
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface ConversationEvent {
  id: string;
  persona: string;
}

export interface ImageEvent {
  data: string; // base64
  mime_type: string;
  url: string;
  alt_text: string;
}

export interface StreamCallbacks {
  onToken: (text: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
  onToolStart?: (event: ToolEvent) => void;
  onToolResult?: (event: ToolEvent) => void;
  onConversation?: (event: ConversationEvent) => void;
  onImage?: (event: ImageEvent) => void;
}

export async function streamChat(
  req: AIChatRequest,
  callbacks: StreamCallbacks,
): Promise<void> {
  const { onToken, onDone, onError, onToolStart, onToolResult, onConversation, onImage } = callbacks;

  const res = await fetch("/api/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok || !res.body) {
    onError(`HTTP ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let event = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        event = line.slice(7);
      } else if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        if (event === "token") onToken(data);
        else if (event === "done") onDone();
        else if (event === "error") onError(data);
        else if (event === "tool_start") onToolStart?.(data);
        else if (event === "tool_result") onToolResult?.(data);
        else if (event === "conversation") onConversation?.(data);
        else if (event === "image") onImage?.(data);
        event = "";
      }
    }
  }
}
