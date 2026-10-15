import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { apiErrorMessage } from "../hooks/useWorkbook";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

function Commands({ lines }: { lines: string[] }) {
  return (
    <pre className="overflow-x-auto rounded bg-gray-900 p-3 font-mono text-xs text-green-200">
      {lines.join("\n")}
    </pre>
  );
}

/** Setup help: shown when the backend, Ollama, or the model is not ready. */
export function SetupPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
  });

  if (health.isPending) return <LoadingState what="health status" />;
  if (health.isError) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Setup — backend not reachable</h1>
        <ErrorState message={apiErrorMessage(health.error)} onRetry={() => health.refetch()} />
        <p className="text-sm">
          Start it from the <code>backend/</code> directory:
        </p>
        <Commands
          lines={[
            "cd backend",
            "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
          ]}
        />
        <p>
          <Link to="/" className="text-blue-700 hover:underline">
            Back to upload
          </Link>
        </p>
      </div>
    );
  }

  const { ollama, model } = health.data;
  const ready = ollama.reachable && model.available;
  const wantedModel = model.name || "gemma3:4b";

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Setup</h1>
      {ready ? (
        <EmptyState message={`Ready — Ollama is reachable and model ${model.name} is available.`} />
      ) : (
        <>
          {!ollama.reachable && (
            <section aria-label="Ollama not running" className="space-y-2">
              <h2 className="text-lg font-semibold">Ollama is not running</h2>
              <p className="text-sm">
                Install it from <code>https://ollama.com</code>, then start it:
              </p>
              <Commands lines={["ollama serve"]} />
            </section>
          )}
          {ollama.reachable && !model.available && (
            <section aria-label="Model missing" className="space-y-2">
              <h2 className="text-lg font-semibold">Model not available</h2>
              <p className="text-sm">
                Pull a Gemma variant your hardware can handle (see{" "}
                <code>ollama list</code>), then set <code>MODEL_NAME</code> to
                that exact name — e.g. in <code>backend/.env</code> — and
                restart the backend:
              </p>
              <Commands
                lines={[
                  `ollama pull ${wantedModel}`,
                  `MODEL_NAME=${wantedModel}`,
                ]}
              />
            </section>
          )}
        </>
      )}
      <p>
        <Link to="/" className="text-blue-700 hover:underline">
          Continue to upload
        </Link>
      </p>
    </div>
  );
}
