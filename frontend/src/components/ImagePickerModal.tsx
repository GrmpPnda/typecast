import { useState, useRef, useCallback } from "react";
import { Upload, X } from "lucide-react";
import { WorkImage } from "@/types";

interface ImagePickerModalProps {
  title: string;
  images: WorkImage[];
  onSelect: (image: WorkImage) => void;
  onUpload?: (file: File) => void;
  onClose: () => void;
  filterTabs?: { key: string; label: string }[];
  activeFilter?: string;
  onFilterChange?: (key: string) => void;
}

export default function ImagePickerModal({
  title,
  images,
  onSelect,
  onUpload,
  onClose,
  filterTabs,
  activeFilter,
  onFilterChange,
}: ImagePickerModalProps) {
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      dragCounter.current = 0;
      const file = e.dataTransfer.files?.[0];
      if (file && file.type.startsWith("image/") && onUpload) {
        onUpload(file);
      }
    },
    [onUpload]
  );

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current === 0) setDragging(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-tc-overlay border border-tc-subtle rounded-xl shadow-2xl w-[580px] h-[520px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-tc-subtle">
          <h3 className="text-sm font-semibold">{title}</h3>
          <button onClick={onClose} className="text-tc-tertiary hover:text-tc-primary p-1">
            <X size={16} />
          </button>
        </div>

        {filterTabs && filterTabs.length > 1 && (
          <div className="flex items-center gap-2 px-4 py-2 border-b border-tc-subtle">
            {filterTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => onFilterChange?.(tab.key)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  activeFilter === tab.key
                    ? "bg-tc-accent text-tc-primary"
                    : "bg-tc-hover text-tc-tertiary hover:text-tc-primary"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-4 gap-2">
            {onUpload && (
              <button
                onClick={() => fileInputRef.current?.click()}
                onDrop={handleDrop}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                className={`aspect-[2/3] rounded-md border-2 border-dashed flex flex-col items-center justify-center gap-1 transition-colors ${
                  dragging
                    ? "border-tc-accent bg-tc-accent/10 text-tc-accent"
                    : "border-tc-strong text-tc-muted hover:border-tc-strong hover:text-tc-secondary"
                }`}
              >
                <Upload size={18} />
                <span className="text-[10px] leading-tight text-center px-1">
                  {dragging ? "Drop here" : "Upload"}
                </span>
              </button>
            )}
            {images.map((img) => (
              <button
                key={img.id}
                onClick={() => onSelect(img)}
                className="aspect-[2/3] rounded-md overflow-hidden border-2 border-tc-strong hover:border-tc-accent transition-colors group relative"
              >
                <img src={img.url} alt={img.alt_text || ""} className="w-full h-full object-cover" />
                {(img.alt_text || img.original_name) && (
                  <div className="absolute inset-x-0 bottom-0 bg-black/70 px-1 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="text-[9px] text-tc-secondary truncate block">
                      {img.alt_text || img.original_name}
                    </span>
                  </div>
                )}
              </button>
            ))}
          </div>
          {!onUpload && images.length === 0 && (
            <div className="text-center py-8 text-tc-muted">
              <p className="text-sm">No images available</p>
            </div>
          )}
          {onUpload && images.length === 0 && (
            <p className="text-center text-xs text-tc-muted mt-4">
              Upload an image or drag and drop onto the tile above
            </p>
          )}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file && onUpload) onUpload(file);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
