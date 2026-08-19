import { useRouteError, isRouteErrorResponse, Link } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function ErrorPage() {
  const error = useRouteError();

  let title = "Something went wrong";
  let message = "An unexpected error occurred. Try refreshing the page.";

  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      title = "Page not found";
      message = "The page you're looking for doesn't exist or has been moved.";
    } else {
      title = `Error ${error.status}`;
      message = error.statusText || message;
    }
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-tc-page text-tc-primary text-center px-4">
      <AlertTriangle size={64} className="text-tc-secondary-accent mb-4" />
      <h1 className="text-2xl font-bold mb-2">{title}</h1>
      <p className="text-tc-tertiary mb-6 max-w-md">{message}</p>
      <div className="flex items-center gap-3">
        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
        <Link
          to="/"
          className="px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium transition-colors"
        >
          Back to Library
        </Link>
      </div>
    </div>
  );
}
