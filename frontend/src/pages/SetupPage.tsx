import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { apiErrorMessage } from "../hooks/useWorkbook";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, CodeBlock, PageHeader } from "../components/ui";

function Commands({ lines }: { lines: string[] }) {
  return <CodeBlock>{lines.join("\n")}</CodeBlock>;
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
        <PageHeader title="Setup: backend not reachable" />
        <ErrorState message={apiErrorMessage(health.error)} onRetry={() => health.refetch()} />
        <Card className="space-y-2 p-5">
          <p className="text-sm text-night-300">
            Start it from the <code className="font-mono text-link">backend/</code> directory:
          </p>
          <Commands
            lines={[
              "cd backend",
              "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
            ]}
          />
        </Card>
        <p>
          <Link to="/" className="font-mono text-sm font-medium text-link hover:underline">
            Back to upload
          </Link>
        </p>
      </div>
    );
  }

  const { ollama, model } = health.data;
  const ready = ollama.reachable && model.available;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Setup"
        description="SheetSense needs a running backend, Ollama, and one Gemma model."
        actions={
          <Link
            to="/"
            className="inline-flex min-h-[40px] items-center justify-center rounded-md border border-night-600 bg-transparent px-3.5 py-2 font-mono text-sm font-medium text-night-100 hover:border-night-400 hover:bg-night-700"
          >
            Continue to upload
          </Link>
        }
      />
      {ready ? (
        <EmptyState message={`Ready. Ollama is reachable and model ${model.name} is available.`} />
      ) : (
        <>
          {!ollama.reachable && (
            <Card className="space-y-2 p-5">
              <h2 className="font-mono text-base font-semibold tracking-tight text-night-100">Ollama is not running</h2>
              <p className="text-sm text-night-300">
                Install it from <code className="font-mono text-link">https://ollama.com</code>, then start it:
              </p>
              <Commands lines={["ollama serve"]} />
            </Card>
          )}
          {ollama.reachable && !model.available && (
            <Card className="space-y-2 p-5">
              <h2 className="font-mono text-base font-semibold tracking-tight text-night-100">Model not available</h2>
              {model.name ? (
                <>
                  <p className="text-sm text-night-300">
                    Pull the configured model, then restart the backend:
                  </p>
                  <Commands lines={[`ollama pull ${model.name}`]} />
                </>
              ) : (
                <>
                  <p className="text-sm text-night-300">
                    No model is configured. See which Gemma variants you have
                    installed, then set <code className="font-mono text-link">MODEL_NAME</code> to that exact
                    name, e.g. in <code className="font-mono text-link">backend/.env</code>, and restart
                    the backend:
                  </p>
                  <Commands
                    lines={["ollama list", "MODEL_NAME=<installed-gemma-model>"]}
                  />
                </>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
