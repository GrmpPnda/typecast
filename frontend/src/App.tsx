import { Navigate, Outlet, useMatch } from "react-router-dom";
import SingleSignOnGate from "@/components/SingleSignOnGate";
import { useState, useEffect, useRef, useCallback } from "react";
import { Bot, MessageSquare } from "lucide-react";
import Sidebar from "./components/Sidebar";
import WorkNav from "./components/WorkNav";
import AIChatPanel from "./components/AIChatPanel";
import CommentsSidebar from "./components/CommentsSidebar";
import { useAuth } from "./auth";

export interface PendingComment {
  sceneId: string;
  anchorText: string;
  anchorFrom: number;
  anchorTo: number;
}

export interface AppOutletContext {
  openComments: (commentId?: string) => void;
  startComment: (pending: PendingComment) => void;
  activeCommentId: string | null;
  setActiveCommentId: (id: string | null) => void;
}

function useWorkId(): string | undefined {
  const workMatch = useMatch("/work/:id/*");
  return workMatch?.params.id;
}

function useIsReadingMode(): boolean {
  const match = useMatch("/work/:id/read");
  return !!match;
}

function useChapterAndScene(): { chapterId?: string; sceneId?: string } {
  const chapterMatch = useMatch("/work/:id/chapter/:chapterId");
  const writeMatch = useMatch("/work/:id/write/:sceneId");
  return {
    chapterId: chapterMatch?.params.chapterId,
    sceneId: writeMatch?.params.sceneId,
  };
}

type RightPanel = "ai" | "comments" | null;

export default function App() {
  const { loading, setupRequired, user, authMode } = useAuth();
  const workId = useWorkId();
  const isReadingMode = useIsReadingMode();
  const { chapterId, sceneId } = useChapterAndScene();
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [workNavCollapsed, setWorkNavCollapsed] = useState(false);
  const userToggledRef = useRef(false);
  const [activeCommentId, setActiveCommentId] = useState<string | null>(null);
  const [pendingComment, setPendingComment] = useState<PendingComment | null>(null);

  const showAI = rightPanel === "ai";
  const showComments = rightPanel === "comments" && !!chapterId;

  const bothPanelsVisible = !!workId && rightPanel !== null;

  useEffect(() => {
    if (userToggledRef.current) return;
    setSidebarCollapsed(bothPanelsVisible);
  }, [bothPanelsVisible]);

  const handleSidebarToggle = () => {
    userToggledRef.current = true;
    setSidebarCollapsed((prev) => !prev);
  };

  useEffect(() => {
    userToggledRef.current = false;
  }, [workId, rightPanel]);

  useEffect(() => {
    if (!chapterId) {
      if (rightPanel === "comments") setRightPanel(null);
    }
  }, [chapterId, rightPanel]);

  const openComments = useCallback(
    (commentId?: string) => {
      setRightPanel("comments");
      if (commentId) setActiveCommentId(commentId);
    },
    []
  );

  const startComment = useCallback(
    (pending: PendingComment) => {
      setPendingComment(pending);
      setRightPanel("comments");
    },
    []
  );

  const outletContext: AppOutletContext = {
    openComments,
    startComment,
    activeCommentId,
    setActiveCommentId,
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-tc-page">
        <div className="text-tc-muted text-sm">Loading...</div>
      </div>
    );
  }

  // A deployment with no accounts has to create one before anything else works.
  if (setupRequired) return <Navigate to="/setup" replace />;

  // Signing out only cleared the stored token, so the shell kept rendering with
  // no user: the account panel went blank and cached queries let you keep
  // browsing, because nothing refetched and so nothing hit the 401 interceptor.
  // In local mode auto-login populates the user, so this never fires there.
  if (!user) {
    // Under single sign-on there is no login page of ours to go to.
    if (authMode === "proxy") return <SingleSignOnGate />;
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-tc-base">
      <Sidebar collapsed={sidebarCollapsed} onToggle={handleSidebarToggle} />
      {workId && (
        <aside className={`bg-tc-page border-r border-tc-default flex flex-col overflow-hidden flex-shrink-0 transition-[width] duration-200 ${workNavCollapsed ? "w-10" : "w-56"}`}>
          <WorkNav workId={workId} readingMode={isReadingMode} collapsed={workNavCollapsed} onToggle={() => setWorkNavCollapsed(c => !c)} />
        </aside>
      )}
      <main className="flex-1 overflow-y-auto min-w-0">
        <Outlet context={outletContext} />
      </main>

      {showComments && chapterId && (
        <aside className="w-96 flex-shrink-0 h-full">
          <CommentsSidebar
            chapterId={chapterId}
            activeCommentId={activeCommentId}
            onActiveChange={setActiveCommentId}
            pendingComment={pendingComment}
            onPendingClear={() => setPendingComment(null)}
            onClose={() => {
              setRightPanel(null);
              setActiveCommentId(null);
              setPendingComment(null);
            }}
          />
        </aside>
      )}

      {showAI && (
        <aside className="w-96 flex-shrink-0 h-full">
          <AIChatPanel
            workId={workId}
            chapterId={chapterId}
            sceneId={sceneId}
            onClose={() => setRightPanel(null)}
          />
        </aside>
      )}

      <div className="fixed bottom-6 right-6 flex items-center gap-2 z-50">
        {!showComments && chapterId && (
          <button
            onClick={() => setRightPanel("comments")}
            className="p-3 bg-tc-secondary hover:bg-tc-secondary-hover rounded-full shadow-lg shadow-tc-accent transition-colors"
            title="Comments"
          >
            <MessageSquare size={20} />
          </button>
        )}
        {!showAI && (
          <button
            onClick={() => setRightPanel("ai")}
            className="p-3 bg-tc-accent hover:bg-tc-accent-hover rounded-full shadow-tc-accent transition-colors"
            title="AI Assistant"
          >
            <Bot size={20} />
          </button>
        )}
      </div>
    </div>
  );
}
