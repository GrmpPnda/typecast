import client from "./client";

export interface ConfigEntry {
  key: string;
  value: string;
  is_secret: boolean;
}

export async function listConfig(): Promise<ConfigEntry[]> {
  const { data } = await client.get<ConfigEntry[]>("/config/");
  return data;
}

export async function updateConfig(
  entries: { key: string; value: string; is_secret?: boolean }[]
): Promise<ConfigEntry[]> {
  const { data } = await client.put<ConfigEntry[]>("/config/", { entries });
  return data;
}

export interface BedrockModel {
  id: string;
  label: string;
}

export async function fetchBedrockModels(): Promise<BedrockModel[]> {
  const { data } = await client.get<BedrockModel[]>("/config/bedrock-models");
  return data;
}

export async function fetchBedrockImageModels(): Promise<BedrockModel[]> {
  const { data } = await client.get<BedrockModel[]>("/config/bedrock-image-models");
  return data;
}
