import { Link, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { AskPage } from "./pages/AskPage";
import { IssuesPage } from "./pages/IssuesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SetupPage } from "./pages/SetupPage";
import { SheetPage } from "./pages/SheetPage";
import { UploadPage } from "./pages/UploadPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function BrandMark() {
  return (
    <span
      aria-hidden="true"
      className="grid h-8 w-8 place-items-center rounded-md bg-accent"
    >
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="1.5" y="1.5" width="15" height="15" rx="2" stroke="#14141c" strokeWidth="1.8" />
        <path d="M1.5 6.5h15M6.5 6.5v10" stroke="#14141c" strokeWidth="1.8" />
        <rect x="8" y="8" width="7" height="7" fill="#14141c" />
      </svg>
    </span>
  );
}

function HealthPill() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
  });
  const ok =
    health.isSuccess && health.data.ollama.reachable && health.data.model.available;
  return (
    <Link
      to="/setup"
      title={ok ? "Backend and model ready" : "Open setup status"}
      aria-label={ok ? "Backend and model ready" : "Setup needed"}
      className="inline-flex items-center gap-1.5 rounded-md border border-night-600 bg-night-800 px-2.5 py-1 font-mono text-sm text-night-300 hover:border-night-400"
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${ok ? "bg-accent" : "bg-warn"}`}
      />
      {ok ? "Ready" : "Setup"}
    </Link>
  );
}

function Layout() {
  const location = useLocation();
  const link = (to: string, label: string) => {
    const active =
      to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
    return (
      <Link
        key={to}
        to={to}
        aria-current={active ? "page" : undefined}
        className={`rounded-md px-3 py-1.5 font-mono text-sm transition-colors ${
          active
            ? "bg-night-700 font-bold text-night-100"
            : "text-night-400 hover:bg-night-800 hover:text-night-100"
        }`}
      >
        {label}
      </Link>
    );
  };
  return (
    <div className="flex min-h-screen flex-col bg-night-900 text-night-100">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-night-800 focus:p-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-night-600 bg-night-950">
        <nav
          aria-label="Primary"
          className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3"
        >
          <Link to="/" className="flex items-center gap-2.5">
            <BrandMark />
            <span className="font-mono text-2xl font-bold tracking-tight">SheetSense</span>
          </Link>
          <div className="ml-6 flex items-center gap-1">
            {link("/", "Workbooks")}
            {link("/setup", "Setup")}
          </div>
          <div className="ml-auto">
            <HealthPill />
          </div>
        </nav>
      </header>
      <main id="content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/w/:id" element={<OverviewPage />} />
          <Route path="/w/:id/issues" element={<IssuesPage />} />
          <Route path="/w/:id/ask" element={<AskPage />} />
          <Route path="/w/:id/sheets/:name" element={<SheetPage />} />
          <Route
            path="*"
            element={<p role="status">Page not found.</p>}
          />
        </Routes>
      </main>
      <footer className="border-t border-night-600 bg-night-950">
        <p className="mx-auto max-w-6xl px-4 py-4 font-mono text-sm text-night-400">
          SheetSense runs fully on your machine. Findings are suspicious cells
          to review. This is not an audit.
        </p>
      </footer>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Layout />
    </QueryClientProvider>
  );
}
