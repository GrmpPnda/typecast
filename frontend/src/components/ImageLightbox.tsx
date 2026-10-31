import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * An image shown as large as the screen allows. Tapping the shade, the close
 * button, or pressing Escape closes it; tapping the image itself does not.
 */
export default function ImageLightbox({
  src,
  alt = "",
  onClose,
}: {
  src: string;
  alt?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] bg-black/85 flex items-center justify-center p-2 md:p-0"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={alt || "Image"}
    >
      <img
        src={src}
        alt={alt}
        className="max-h-[90dvh] max-w-full md:max-w-[90vw] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
      <button
        onClick={onClose}
        className="absolute right-3 p-2.5 rounded-full bg-black/60 text-white/90 hover:text-white"
        style={{ top: "calc(0.75rem + env(safe-area-inset-top))" }}
        aria-label="Close"
      >
        <X size={20} />
      </button>
    </div>
  );
}
