import { Link, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
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

function HealthDot() {
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
      className={`inline-block h-3 w-3 rounded-full ${ok ? "bg-green-500" : "bg-amber-500"}`}
    />
  );
}

function Layout() {
  const location = useLocation();
  const link = (to: string, label: string) => (
    <Link
      key={to}
      to={to}
      aria-current={location.pathname === to ? "page" : undefined}
      className={`rounded px-2 py-1 text-sm hover:bg-gray-200 ${
        location.pathname === to ? "font-semibold underline" : ""
      }`}
    >
      {label}
    </Link>
  );
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:bg-white focus:p-2"
      >
        Skip to content
      </a>
      <header className="border-b border-gray-200 bg-white">
        <nav
          aria-label="Primary"
          className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3"
        >
          <Link to="/" className="text-lg font-bold">
            SheetSense
          </Link>
          <HealthDot />
          <div className="ml-4 flex gap-1">
            {link("/", "Upload")}
            {link("/setup", "Setup")}
          </div>
        </nav>
      </header>
      <main id="content" className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/w/:id" element={<OverviewPage />} />
          <Route path="/w/:id/issues" element={<IssuesPage />} />
          <Route path="/w/:id/sheets/:name" element={<SheetPage />} />
          <Route
            path="*"
            element={<p role="status">Page not found.</p>}
          />
        </Routes>
      </main>
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
