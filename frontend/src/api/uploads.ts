import client from "./client";

export async function uploadCover(
  workId: string,
  file: File
): Promise<{ cover_image_path: string }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<{ cover_image_path: string }>(
    `/works/${workId}/cover`,
    form
  );
  return data;
}

export async function setCoverFromImage(
  workId: string,
  imageUrl: string
): Promise<{ cover_image_path: string }> {
  const { data } = await client.post<{ cover_image_path: string }>(
    `/works/${workId}/cover-from-image`,
    { image_url: imageUrl }
  );
  return data;
}

export async function deleteCover(workId: string): Promise<void> {
  await client.delete(`/works/${workId}/cover`);
}
