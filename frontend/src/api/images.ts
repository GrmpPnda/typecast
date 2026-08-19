import client from "./client";
import { WorkImage, UpdateImage } from "@/types";

export async function listAllImages(): Promise<WorkImage[]> {
  const { data } = await client.get<WorkImage[]>("/images/all");
  return data;
}

export async function listImages(workId: string): Promise<WorkImage[]> {
  const { data } = await client.get<WorkImage[]>(`/${workId}/images`);
  return data;
}

export async function uploadImage(
  workId: string,
  file: File
): Promise<WorkImage> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<WorkImage>(`/${workId}/images`, form);
  return data;
}

export async function updateImage(
  imageId: string,
  payload: UpdateImage
): Promise<WorkImage> {
  const { data } = await client.put<WorkImage>(`/images/${imageId}`, payload);
  return data;
}

export async function deleteImage(imageId: string): Promise<void> {
  await client.delete(`/images/${imageId}`);
}
