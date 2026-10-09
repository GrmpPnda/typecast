import client from "./client";
import { Series, CreateSeries, UpdateSeries } from "@/types";

export async function listSeries(): Promise<Series[]> {
  const { data } = await client.get<Series[]>("/series/");
  return data;
}

export async function getSeries(id: string): Promise<Series> {
  const { data } = await client.get<Series>(`/series/${id}`);
  return data;
}

export async function createSeries(payload: CreateSeries): Promise<Series> {
  const { data } = await client.post<Series>("/series/", payload);
  return data;
}

export async function updateSeries(
  id: string,
  payload: UpdateSeries
): Promise<Series> {
  const { data } = await client.patch<Series>(`/series/${id}`, payload);
  return data;
}

export async function deleteSeries(id: string): Promise<void> {
  await client.delete(`/series/${id}`);
}

export async function uploadSeriesCover(id: string, file: File): Promise<{ cover_image_path: string }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post(`/series/${id}/cover`, form);
  return data;
}

export async function setSeriesCoverFromImage(
  id: string,
  imageUrl: string
): Promise<{ cover_image_path: string }> {
  const { data } = await client.post<{ cover_image_path: string }>(
    `/series/${id}/cover-from-image`,
    { image_url: imageUrl }
  );
  return data;
}

export async function deleteSeriesCover(id: string): Promise<void> {
  await client.delete(`/series/${id}/cover`);
}
