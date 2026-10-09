import client from "./client";

/** What a restore or import did. Mirrors summary_response() in api/backup.py. */
export interface LoadResult {
  status: string;
  message?: string;
  mode: "replace" | "import";
  dry_run: boolean;
  rows: Record<string, number>;
  total_rows: number;
  files_written: number;
  files_unchanged: number;
  file_conflicts: string[];
  profiles_remapped: number;
  skipped_config: string[];
  secrets_dropped: number;
  dropped_columns: string[];
}

export async function downloadBackup(): Promise<void> {
  const response = await client.get("/backup/backup", { responseType: "blob" });
  const disposition = response.headers["content-disposition"] || "";
  const match = disposition.match(/filename="(.+)"/);
  const filename = match ? match[1] : "typecast-backup.zip";

  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Replace everything, accounts included, with the backup's contents. */
export async function restoreBackup(file: File): Promise<LoadResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<LoadResult>("/backup/restore", form);
  return data;
}

/**
 * Add a backup's works to this install under the signed-in account. Works
 * across SQLite and Postgres. With dryRun the server checks everything and
 * reports what would happen, then rolls back.
 */
export async function importBackup(file: File, dryRun = false): Promise<LoadResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<LoadResult>("/backup/import", form, {
    params: dryRun ? { dry_run: true } : undefined,
  });
  return data;
}
