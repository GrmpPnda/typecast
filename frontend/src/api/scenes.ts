import client from "./client";
import { Scene, CreateScene, UpdateScene } from "@/types";

export async function listScenes(chapterId: string): Promise<Scene[]> {
  const { data } = await client.get<Scene[]>(`/chapters/${chapterId}/scenes`);
  return data;
}

export async function getScene(id: string): Promise<Scene> {
  const { data } = await client.get<Scene>(`/scenes/${id}`);
  return data;
}

export async function createScene(payload: CreateScene): Promise<Scene> {
  const { chapter_id, ...body } = payload;
  const { data } = await client.post<Scene>(`/chapters/${chapter_id}/scenes`, body);
  return data;
}

export async function updateScene(
  id: string,
  payload: UpdateScene
): Promise<Scene> {
  const { data } = await client.put<Scene>(`/scenes/${id}`, payload);
  return data;
}

export async function splitScene(id: string): Promise<Scene[]> {
  const { data } = await client.post<Scene[]>(`/scenes/${id}/split`);
  return data;
}

export async function deleteScene(id: string): Promise<void> {
  await client.delete(`/scenes/${id}`);
}
