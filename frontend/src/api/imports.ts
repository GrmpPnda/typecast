import client from "./client";
import { Work } from "@/types";

export async function importMarkdownFile(
  file: File,
  options: { title?: string; author?: string; useAi?: boolean } = {}
): Promise<Work> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.title) formData.append("title", options.title);
  if (options.author) formData.append("author", options.author);
  formData.append("use_ai", String(options.useAi ?? true));
  const { data } = await client.post<Work>("/import/markdown", formData);
  return data;
}

export async function importMarkdownPaste(
  content: string,
  options: { title?: string; author?: string; useAi?: boolean } = {}
): Promise<Work> {
  const formData = new FormData();
  formData.append("content", content);
  if (options.title) formData.append("title", options.title);
  if (options.author) formData.append("author", options.author);
  formData.append("use_ai", String(options.useAi ?? true));
  const { data } = await client.post<Work>("/import/paste", formData);
  return data;
}
