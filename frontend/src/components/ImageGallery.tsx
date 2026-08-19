import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef } from "react";
import {
  ImagePlus,
  Trash2,
  Copy,
  Check,
  X,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { listImages, uploadImage, updateImage, deleteImage } from "@/api/images";
import { WorkImage } from "@/types";

function ImageCard({
  image,
  onDelete,
  onCopyMarkdown,
}: {
  image: WorkImage;
  onDelete: () => void;
  onCopyMarkdown: (img: WorkImage) => void;
}) {
  const queryClient = useQueryClient();
  const [editingAlt, setEditingAlt] = useState(false);
  const [altText, setAltText] = useState(image.alt_text);
  const [copied, setCopied] = useState(false);

  const updateMutation = useMutation({
    mutationFn: (data: { alt_text?: string; caption?: string }) =>
      updateImage(image.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images", image.work_id] });
      setEditingAlt(false);
    },
  });

  const handleCopy = () => {
    onCopyMarkdown(image);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group bg-tc-overlay rounded-lg border border-tc-subtle/50 overflow-hidden">
      <div className="aspect-square overflow-hidden">
        <img
          src={image.url}
          alt={image.alt_text || image.original_name}
          className="w-full h-full object-cover"
        />
      </div>
      <div className="p-2">
        <p className="text-xs text-tc-tertiary truncate" title={image.original_name}>
          {image.original_name}
        </p>
        {editingAlt ? (
          <div className="mt-1 flex gap-1">
            <input
              type="text"
              value={altText}
              onChange={(e) => setAltText(e.target.value)}
              placeholder="Alt text..."
              className="flex-1 bg-tc-hover border border-tc-strong rounded px-2 py-0.5 text-xs focus:border-tc-accent focus:outline-none"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") updateMutation.mutate({ alt_text: altText });
                if (e.key === "Escape") setEditingAlt(false);
              }}
            />
            <button
              onClick={() => updateMutation.mutate({ alt_text: altText })}
              className="text-tc-accent hover:text-tc-accent p-0.5"
            >
              <Check size={12} />
            </button>
            <button
              onClick={() => setEditingAlt(false)}
              className="text-tc-muted hover:text-tc-secondary p-0.5"
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <p
            className="text-xs text-tc-muted mt-0.5 cursor-pointer hover:text-tc-tertiary truncate"
            onClick={() => { setAltText(image.alt_text); setEditingAlt(true); }}
            title="Click to edit alt text"
          >
            {image.alt_text || "Add alt text..."}
          </p>
        )}
        {image.width && image.height && (
          <p className="text-xs text-tc-muted mt-0.5">
            {image.width} x {image.height}
          </p>
        )}
      </div>
      <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={handleCopy}
          className="p-1.5 bg-tc-base/80 rounded text-tc-secondary hover:text-tc-primary transition-colors"
          title="Copy markdown"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
        <button
          onClick={() => {
            if (confirm(`Delete "${image.original_name}"?`)) onDelete();
          }}
          className="p-1.5 bg-tc-base/80 rounded text-tc-error hover:text-tc-error transition-colors"
          title="Delete image"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

export default function ImageGallery({
  workId,
  onInsert,
}: {
  workId: string;
  onInsert?: (markdown: string) => void;
}) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [expanded, setExpanded] = useState(false);

  const { data: images = [] } = useQuery({
    queryKey: ["images", workId],
    queryFn: () => listImages(workId),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadImage(workId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images", workId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteImage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images", workId] });
    },
  });

  const handleCopyMarkdown = (img: WorkImage) => {
    const md = `![${img.alt_text || img.original_name}](${img.url})`;
    navigator.clipboard.writeText(md);
    onInsert?.(md);
  };

  return (
    <section className="mb-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm font-semibold text-tc-tertiary uppercase tracking-wide mb-3 hover:text-tc-secondary transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Images ({images.length})
      </button>

      {expanded && (
        <>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = e.target.files;
              if (files) {
                Array.from(files).forEach((f) => uploadMutation.mutate(f));
              }
              e.target.value = "";
            }}
          />
          <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-3 mb-3">
            {images.map((img) => (
              <ImageCard
                key={img.id}
                image={img}
                onDelete={() => deleteMutation.mutate(img.id)}
                onCopyMarkdown={handleCopyMarkdown}
              />
            ))}
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploadMutation.isPending}
              className="aspect-square border-2 border-dashed border-tc-subtle rounded-lg flex flex-col items-center justify-center text-tc-muted hover:border-tc-strong hover:text-tc-tertiary transition-colors"
            >
              <ImagePlus size={20} className="mb-1" />
              <span className="text-xs">Upload</span>
            </button>
          </div>
          {onInsert && (
            <p className="text-xs text-tc-muted">
              Click the copy icon on an image to copy its markdown. Paste it into any scene.
            </p>
          )}
        </>
      )}
    </section>
  );
}
