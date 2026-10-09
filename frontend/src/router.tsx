import { createBrowserRouter } from "react-router-dom";
import App from "./App";
import Library from "./pages/Library";
import SeriesDetail from "./pages/SeriesDetail";
import WorkDetail from "./pages/WorkDetail";
import WorkSettings from "./pages/WorkSettings";
import ChapterView from "./pages/ChapterView";
import WritingEditor from "./pages/WritingEditor";
import CodexList from "./pages/CodexList";
import CodexEntryPage from "./pages/CodexEntry";
import Gallery from "./pages/Gallery";
import Import from "./pages/Import";
import ReadingMode from "./pages/ReadingMode";
import SectionView from "./pages/SectionView";
import Settings from "./pages/Settings";
import CoverProduction from "./pages/CoverProduction";
import ErrorPage from "./pages/ErrorPage";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import Setup from "./pages/Setup";

export const router = createBrowserRouter([
  {
    path: "/setup",
    element: <Setup />,
  },
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/",
    element: <App />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <Library /> },
      { path: "series/:id", element: <SeriesDetail /> },
      { path: "work/:id", element: <WorkDetail /> },
      { path: "work/:id/settings", element: <WorkSettings /> },
      { path: "work/:id/chapter/:chapterId", element: <ChapterView /> },
      { path: "work/:id/section/:sectionId", element: <SectionView /> },
      { path: "work/:id/write/:sceneId", element: <WritingEditor /> },
      { path: "work/:id/read", element: <ReadingMode /> },
      { path: "work/:id/cover", element: <CoverProduction /> },
      { path: "codex", element: <CodexList /> },
      { path: "codex/:id", element: <CodexEntryPage /> },
      { path: "gallery", element: <Gallery /> },
      { path: "import", element: <Import /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
