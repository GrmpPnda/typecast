import client from "./client";
import { CodexEntry, CreateCodexEntry, UpdateCodexEntry } from "@/types";

export async function listCodexEntries(
  filters?: { entryType?: string; workId?: string; seriesId?: string }
): Promise<CodexEntry[]> {
  const params: Record<string, string> = {};
  if (filters?.entryType) params.entry_type = filters.entryType;
  if (filters?.workId) params.work_id = filters.workId;
  if (filters?.seriesId) params.series_id = filters.seriesId;
  const { data } = await client.get<CodexEntry[]>("/codex/", { params });
  return data;
}

export async function getCodexEntry(id: string): Promise<CodexEntry> {
  const { data } = await client.get<CodexEntry>(`/codex/${id}`);
  return data;
}

export async function createCodexEntry(
  payload: CreateCodexEntry
): Promise<CodexEntry> {
  const { data } = await client.post<CodexEntry>("/codex/", payload);
  return data;
}

export async function updateCodexEntry(
  id: string,
  payload: UpdateCodexEntry
): Promise<CodexEntry> {
  const { data } = await client.patch<CodexEntry>(`/codex/${id}`, payload);
  return data;
}

export async function deleteCodexEntry(id: string): Promise<void> {
  await client.delete(`/codex/${id}`);
}
