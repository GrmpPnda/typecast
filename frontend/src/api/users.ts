import client from "./client";

export interface ManagedUser {
  id: string;
  email: string;
  username: string;
  display_name: string;
  is_active: boolean;
  is_admin: boolean;
  /** Single sign-on: whether this person has signed in yet. */
  sso_linked: boolean;
  /** "password", "microsoft", "google", "external", or null (first sign-in decides). */
  auth_provider?: string | null;
}

export async function listUsers(): Promise<ManagedUser[]> {
  const { data } = await client.get<ManagedUser[]>("/users/");
  return data;
}

export async function createUser(payload: {
  email: string;
  username: string;
  display_name: string;
  /** Omitted under single sign-on, where the account links on first sign-in. */
  password?: string;
  is_admin: boolean;
  /** "password", "microsoft", "google", or "any" (whichever they use first). */
  sign_in?: string;
}): Promise<ManagedUser> {
  const { data } = await client.post<ManagedUser>("/users/", payload);
  return data;
}

export async function updateUser(
  id: string,
  updates: { display_name?: string; is_active?: boolean; is_admin?: boolean }
): Promise<ManagedUser> {
  const { data } = await client.patch<ManagedUser>(`/users/${id}`, updates);
  return data;
}

export async function resetUserPassword(id: string, password: string): Promise<void> {
  await client.put(`/users/${id}/password`, { password });
}

/**
 * Delete an account. The server refuses if the account owns any works, series,
 * or conversations, because the user_id foreign keys cascade and would destroy
 * them. Pass purge to confirm that destruction.
 */
export async function deleteUser(id: string, purge = false): Promise<void> {
  await client.delete(`/users/${id}`, { params: purge ? { purge: true } : undefined });
}
