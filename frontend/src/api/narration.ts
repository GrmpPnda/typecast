import client from "./client";

export interface PollyVoice {
  id: string;
  name: string;
  gender: string;
  language: string;
  engines: string[];
}

export interface NarrationSegment {
  index: number;
  speaker: string;
  text: string;
}

export type NarrationEvent =
  | { type: "segments"; segments: NarrationSegment[] }
  | { type: "audio"; index: number; audio: string }
  | { type: "done" }
  | { type: "error"; message: string };

export async function listVoices(): Promise<PollyVoice[]> {
  const { data } = await client.get<PollyVoice[]>("/narration/voices");
  return data;
}

export function getNarrationUrl(workId: string, sceneId: string): string {
  return `/api/narration/works/${workId}/scenes/${sceneId}/narrate`;
}

export function streamNarration(
  workId: string,
  sceneId: string,
  onEvent: (event: NarrationEvent) => void,
  signal?: AbortSignal
): void {
  const token = localStorage.getItem("token");
  const url = getNarrationUrl(workId, sceneId);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  fetch(url, { signal, headers })
    .then(async (res) => {
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        onEvent({ type: "error", message: body || `HTTP ${res.status}` });
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        onEvent({ type: "error", message: "No response body" });
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as NarrationEvent;
              onEvent(event);
            } catch {
              // skip malformed
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onEvent({ type: "error", message: err.message || "Network error" });
      }
    });
}
