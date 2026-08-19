import { Link } from "react-router-dom";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <FileQuestion size={64} className="text-tc-muted mb-4" />
      <h1 className="text-2xl font-bold mb-2">Page not found</h1>
      <p className="text-tc-tertiary mb-6 max-w-sm">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Link
        to="/"
        className="px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
      >
        Back to Library
      </Link>
    </div>
  );
}
