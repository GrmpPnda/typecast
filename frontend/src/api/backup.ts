import client from "./client";

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

export async function restoreBackup(file: File): Promise<{ status: string; message: string }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<{ status: string; message: string }>(
    "/backup/restore",
    form,
  );
  return data;
}
