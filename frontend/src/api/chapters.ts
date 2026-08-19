import client from "./client";
import { Chapter, CreateChapter, UpdateChapter } from "@/types";

export async function listChapters(workId: string): Promise<Chapter[]> {
  const { data } = await client.get<Chapter[]>(`/${workId}/chapters`);
  return data.sort((a, b) => a.sort_order - b.sort_order);
}

export async function getChapter(id: string): Promise<Chapter> {
  const { data } = await client.get<Chapter>(`/chapters/${id}`);
  return data;
}

export async function createChapter(payload: CreateChapter): Promise<Chapter> {
  const { work_id, ...body } = payload;
  const { data } = await client.post<Chapter>(`/${work_id}/chapters`, body);
  return data;
}

export async function updateChapter(
  id: string,
  payload: UpdateChapter
): Promise<Chapter> {
  const { data } = await client.put<Chapter>(`/chapters/${id}`, payload);
  return data;
}

export async function deleteChapter(id: string): Promise<void> {
  await client.delete(`/chapters/${id}`);
}

export async function reorderChapters(
  workId: string,
  chapters: { id: string; sort_order: number; number?: number | null }[]
): Promise<Chapter[]> {
  const { data } = await client.put<Chapter[]>(`/${workId}/chapters/reorder`, {
    chapters,
  });
  return data;
}
