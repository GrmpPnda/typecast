import client from "./client";
import { Profile, CreateProfile, UpdateProfile } from "@/types";

export async function listProfiles(): Promise<Profile[]> {
  const { data } = await client.get<Profile[]>("/profiles");
  return data;
}

export async function getProfile(id: string): Promise<Profile> {
  const { data } = await client.get<Profile>(`/profiles/${id}`);
  return data;
}

export async function createProfile(payload: CreateProfile): Promise<Profile> {
  const { data } = await client.post<Profile>("/profiles", payload);
  return data;
}

export async function updateProfile(
  id: string,
  payload: UpdateProfile
): Promise<Profile> {
  const { data } = await client.put<Profile>(`/profiles/${id}`, payload);
  return data;
}

export async function deleteProfile(id: string): Promise<void> {
  await client.delete(`/profiles/${id}`);
}
