import client from "./client";

export interface UserProfile {
  id: string;
  email: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  is_admin: boolean;
}

interface TokenResponse {
  token: string;
  user: UserProfile;
}

interface AuthModeResponse {
  mode: string;
}

export async function getAuthMode(): Promise<string> {
  const { data } = await client.get<AuthModeResponse>("/auth/mode");
  return data.mode;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/login", { email, password });
  return data;
}

export async function register(
  email: string,
  username: string,
  display_name: string,
  password: string
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/register", {
    email,
    username,
    display_name,
    password,
  });
  return data;
}

export async function getMe(): Promise<UserProfile> {
  const { data } = await client.get<UserProfile>("/auth/me");
  return data;
}

export async function updateMe(updates: {
  display_name?: string;
  bio?: string;
  avatar_url?: string;
}): Promise<UserProfile> {
  const { data } = await client.put<UserProfile>("/auth/me", updates);
  return data;
}
