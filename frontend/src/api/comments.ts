import client from "./client";
import { Comment, CreateComment, UpdateComment } from "@/types";

export async function listComments(sceneId: string): Promise<Comment[]> {
  const { data } = await client.get<Comment[]>(
    `/scenes/${sceneId}/comments`
  );
  return data;
}

export async function listChapterComments(chapterId: string): Promise<Comment[]> {
  const { data } = await client.get<Comment[]>(
    `/chapters/${chapterId}/comments`
  );
  return data;
}

export async function createComment(
  sceneId: string,
  payload: CreateComment
): Promise<Comment> {
  const { data } = await client.post<Comment>(
    `/scenes/${sceneId}/comments`,
    payload
  );
  return data;
}

export async function batchCreateComments(
  sceneId: string,
  payload: CreateComment[]
): Promise<Comment[]> {
  const { data } = await client.post<Comment[]>(
    `/scenes/${sceneId}/comments/batch`,
    payload
  );
  return data;
}

export async function updateComment(
  id: string,
  payload: UpdateComment
): Promise<Comment> {
  const { data } = await client.put<Comment>(`/comments/${id}`, payload);
  return data;
}

export async function deleteComment(id: string): Promise<void> {
  await client.delete(`/comments/${id}`);
}

export async function resolveAllComments(sceneId: string): Promise<void> {
  await client.post(`/scenes/${sceneId}/comments/resolve-all`);
}

export async function applyComment(commentId: string): Promise<{ scene_id: string; content: string; checkpoint: string }> {
  const { data } = await client.post(`/comments/${commentId}/apply`);
  return data;
}

export async function revertScene(sceneId: string): Promise<{ scene_id: string; content: string }> {
  const { data } = await client.post(`/scenes/${sceneId}/revert`);
  return data;
}

export async function clearCheckpoint(sceneId: string): Promise<void> {
  await client.post(`/scenes/${sceneId}/checkpoint/clear`);
}

export async function rewriteScene(sceneId: string): Promise<{ scene_id: string; content: string; checkpoint: string }> {
  const { data } = await client.post(`/scenes/${sceneId}/rewrite`);
  return data;
}
