import client from "./client";
import { Section, CreateSection, UpdateSection } from "@/types";

export async function listSections(workId: string, placement?: string): Promise<Section[]> {
  const { data } = await client.get<Section[]>(`/${workId}/sections`, {
    params: placement ? { placement } : undefined,
  });
  return data;
}

export async function getSection(id: string): Promise<Section> {
  const { data } = await client.get<Section>(`/sections/${id}`);
  return data;
}

export async function createSection(workId: string, payload: CreateSection): Promise<Section> {
  const { data } = await client.post<Section>(`/${workId}/sections`, payload);
  return data;
}

export async function updateSection(id: string, payload: UpdateSection): Promise<Section> {
  const { data } = await client.put<Section>(`/sections/${id}`, payload);
  return data;
}

export async function deleteSection(id: string): Promise<void> {
  await client.delete(`/sections/${id}`);
}
