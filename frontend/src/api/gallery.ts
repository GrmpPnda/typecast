import client from "./client";

export interface GalleryItem {
  id: string;
  source: "gallery" | "cover" | "codex";
  url: string;
  original_name: string;
  mime_type: string | null;
  size_bytes: number | null;
  width: number | null;
  height: number | null;
  alt_text: string;
  tags: string;
  work_id: string | null;
  work_title: string | null;
  codex_entry_id: string | null;
  codex_entry_name: string | null;
  manageable: boolean;
  created_at: string | null;
}

export async function listGallery(): Promise<GalleryItem[]> {
  const { data } = await client.get<GalleryItem[]>("/gallery");
  return data;
}

export async function updateGalleryImage(
  imageId: string,
  payload: { alt_text?: string; tags?: string }
): Promise<GalleryItem> {
  const { data } = await client.put<GalleryItem>(`/gallery/images/${imageId}`, payload);
  return data;
}

export async function reassignImage(
  imageId: string,
  workId: string
): Promise<GalleryItem> {
  const { data } = await client.put<GalleryItem>(`/gallery/images/${imageId}/reassign`, {
    work_id: workId,
  });
  return data;
}

export async function bulkDeleteImages(imageIds: string[]): Promise<void> {
  await client.post("/gallery/images/bulk-delete", { image_ids: imageIds });
}

/** Extract the raw UUID from a source-prefixed gallery id (e.g. "image:<uuid>"). */
export function galleryRawId(id: string): string {
  const idx = id.indexOf(":");
  return idx === -1 ? id : id.slice(idx + 1);
}
