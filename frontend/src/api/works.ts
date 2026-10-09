import client from "./client";
import { Work, CreateWork, UpdateWork } from "@/types";

export async function listWorks(seriesId?: string): Promise<Work[]> {
  const params = seriesId ? { series_id: seriesId } : {};
  const { data } = await client.get<Work[]>("/works/", { params });
  return data;
}

export async function getWork(id: string): Promise<Work> {
  const { data } = await client.get<Work>(`/works/${id}`);
  return data;
}

export async function createWork(payload: CreateWork): Promise<Work> {
  const { data } = await client.post<Work>("/works/", payload);
  return data;
}

export async function updateWork(
  id: string,
  payload: UpdateWork
): Promise<Work> {
  const { data } = await client.put<Work>(`/works/${id}`, payload);
  return data;
}

export async function deleteWork(id: string): Promise<void> {
  await client.delete(`/works/${id}`);
}
