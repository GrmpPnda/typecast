import client from "./client";
import { CodexImage, UpdateCodexImage } from "@/types";

export async function uploadCodexImage(
  entryId: string,
  file: File
): Promise<CodexImage> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<CodexImage>(
    `/codex/${entryId}/images`,
    form
  );
  return data;
}

export async function updateCodexImage(
  imageId: string,
  payload: UpdateCodexImage
): Promise<CodexImage> {
  const { data } = await client.patch<CodexImage>(
    `/codex/images/${imageId}`,
    payload
  );
  return data;
}

export async function deleteCodexImage(imageId: string): Promise<void> {
  await client.delete(`/codex/images/${imageId}`);
}
