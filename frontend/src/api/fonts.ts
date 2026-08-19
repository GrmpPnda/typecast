import { Font } from "../types";
import client from "./client";

export async function listFonts(): Promise<Font[]> {
  const { data } = await client.get<Font[]>("/fonts");
  return data;
}

export async function uploadFont(file: File): Promise<Font> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<Font>("/fonts", form);
  return data;
}

export async function deleteFont(id: string): Promise<void> {
  await client.delete(`/fonts/${id}`);
}
