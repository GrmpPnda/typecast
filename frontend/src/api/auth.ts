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

export interface AuthState {
  mode: string;
  open_registration: boolean;
  /** True when the deployment is in multi-user mode with no accounts yet. */
  setup_required: boolean;
  /** Proxy (single sign-on) mode: where the proxy signs people in and out. */
  login_url?: string | null;
  logout_url?: string | null;
}

export async function getAuthState(): Promise<AuthState> {
  const { data } = await client.get<AuthState>("/auth/mode");
  return data;
}

/** Create the first administrator. Only works while no account exists. */
export async function completeSetup(payload: {
  email: string;
  username: string;
  display_name: string;
  password: string;
}): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/setup", payload);
  return data;
}

export async function changeMyPassword(
  current_password: string,
  new_password: string
): Promise<void> {
  await client.put("/auth/me/password", { current_password, new_password });
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
