import { useEffect } from "react";

/**
 * A panel that slides over the page from the left, for the phone layout. Tapping
 * the shade behind it or pressing Escape closes it; so does navigating, which
 * the shell handles.
 */
export default function MobileDrawer({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex" role="dialog" aria-modal="true" aria-label={label}>
      <div className="h-full w-72 max-w-[85vw] flex flex-col bg-tc-page border-r border-tc-default shadow-2xl overflow-y-auto">
        {children}
      </div>
      <button
        aria-label="Close"
        onClick={onClose}
        className="flex-1 h-full bg-tc-overlay/60 backdrop-blur-[1px]"
      />
    </div>
  );
}
