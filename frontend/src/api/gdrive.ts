import client from "./client";

export interface DriveStatus {
  enabled: boolean;
  configured: boolean;
  connected: boolean;
  account_email: string | null;
  folder_id: string | null;
  redirect_uri: string;
  error: string | null;
}

export interface DriveAuthUrl {
  auth_url: string;
  redirect_uri: string;
}

export interface DriveExportRequest {
  format: string;
  profile_id?: string;
  include_images?: boolean;
  compress_images?: boolean;
  convert_to_google_doc?: boolean;
  /** Relative to the Typecast folder; levels are created on demand. */
  folder_path?: string;
  /** Extension is applied server-side from the format. */
  filename?: string;
}

export interface DriveExportResult {
  file_id: string;
  name: string;
  mime_type: string;
  web_view_link: string | null;
  converted_to_google_doc: boolean;
  folder_path: string;
}

export interface DriveFile {
  id: string;
  name: string;
  mime_type: string;
  web_view_link: string | null;
  size: number | null;
  modified_time: string | null;
}

export async function getDriveStatus(): Promise<DriveStatus> {
  const { data } = await client.get<DriveStatus>("/gdrive/status");
  return data;
}

export async function getDriveAuthUrl(): Promise<DriveAuthUrl> {
  const { data } = await client.get<DriveAuthUrl>("/gdrive/auth-url");
  return data;
}

export async function disconnectDrive(): Promise<DriveStatus> {
  const { data } = await client.post<DriveStatus>("/gdrive/disconnect");
  return data;
}

export async function exportWorkToDrive(
  workId: string,
  request: DriveExportRequest
): Promise<DriveExportResult> {
  const { data } = await client.post<DriveExportResult>(
    `/gdrive/works/${workId}/export`,
    request
  );
  return data;
}

export async function listDriveFiles(): Promise<DriveFile[]> {
  const { data } = await client.get<DriveFile[]>("/gdrive/files");
  return data;
}

/** Formats Drive can turn into a native Google Doc on upload. */
export const CONVERTIBLE_FORMATS = new Set(["docx", "html", "txt", "markdown"]);

// --------------------------------------------------------------------------
// Backup to Drive
// --------------------------------------------------------------------------

export interface DriveBackupFile {
  id: string;
  name: string;
  size: number | null;
  modified_time: string | null;
  web_view_link: string | null;
}

export interface DriveBackupResult {
  file_id: string;
  name: string;
  size: number;
  web_view_link: string | null;
  pruned: string[];
}

export interface DriveRestoreResult {
  status: string;
  name: string;
  files_restored: number;
  message: string;
}

export async function listDriveBackups(): Promise<DriveBackupFile[]> {
  const { data } = await client.get<DriveBackupFile[]>("/gdrive/backups");
  return data;
}

/** Upload a backup archive. `keep` prunes older archives; omit to keep all. */
export async function backupToDrive(keep?: number): Promise<DriveBackupResult> {
  const { data } = await client.post<DriveBackupResult>("/gdrive/backup", {
    keep: keep ?? null,
  });
  return data;
}

/** Replaces the local database and all uploads. Unrecoverable. */
export async function restoreFromDrive(fileId: string): Promise<DriveRestoreResult> {
  const { data } = await client.post<DriveRestoreResult>("/gdrive/restore", {
    file_id: fileId,
    confirm: true,
  });
  return data;
}
