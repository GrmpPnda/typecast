import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { listWorks } from "@/api/works";
import { useState } from "react";
import client from "@/api/client";

export default function Export() {
  const [selectedWork, setSelectedWork] = useState("");
  const [format, setFormat] = useState("markdown");
  const [exporting, setExporting] = useState(false);

  const { data: works = [] } = useQuery({
    queryKey: ["works"],
    queryFn: () => listWorks(),
  });

  const handleExport = async () => {
    if (!selectedWork) return;
    setExporting(true);
    try {
      const { data } = await client.get(
        `/export/${selectedWork}?format=${format}`,
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([data]));
      const link = document.createElement("a");
      link.href = url;
      const ext = format === "markdown" ? "md" : format;
      link.setAttribute("download", `export.${ext}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-8">Export</h1>

      <div className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-tc-secondary mb-2">
            Select Work
          </label>
          <select
            value={selectedWork}
            onChange={(e) => setSelectedWork(e.target.value)}
            className="w-full bg-tc-overlay border border-tc-subtle rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-tc-accent"
          >
            <option value="">Choose a work...</option>
            {works.map((work) => (
              <option key={work.id} value={work.id}>
                {work.title}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-tc-secondary mb-2">
            Format
          </label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="w-full bg-tc-overlay border border-tc-subtle rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-tc-accent"
          >
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
            <option value="txt">Plain Text</option>
          </select>
        </div>

        <button
          onClick={handleExport}
          disabled={!selectedWork || exporting}
          className="flex items-center gap-2 px-4 py-2.5 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Download size={16} />
          {exporting ? "Exporting..." : "Export"}
        </button>
      </div>
    </div>
  );
}
