import client from "./client";

export async function exportWork(
  workId: string,
  format: string,
  profileId?: string,
  includeImages?: boolean,
  compressImages?: boolean
): Promise<Blob> {
  const params: Record<string, string | boolean> = { format };
  if (profileId) params.profile_id = profileId;
  if (includeImages) params.include_images = true;
  if (compressImages) params.compress_images = true;
  const { data } = await client.get(`/works/${workId}/export`, {
    params,
    responseType: "blob",
  });
  return data;
}
