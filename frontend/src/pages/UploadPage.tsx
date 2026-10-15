import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { FileDropzone } from "../components/FileDropzone";
import { ProgressBar } from "../components/ProgressBar";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, PageHeader, SectionTitle } from "../components/ui";
import { useProgress } from "../hooks/useProgress";
import { apiErrorMessage } from "../hooks/useWorkbook";

const STATUS_STYLES: Record<string, string> = {
  ready: "border-accent/40 bg-accent/10 text-accent",
  analyzing: "border-warn/40 bg-warn/10 text-warn",
  failed: "border-danger/40 bg-danger/10 text-danger",
  uploaded: "border-night-600 bg-night-700 text-night-300",
};

/** Upload, analyze with SSE progress, and manage past workbooks. */
export function UploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const workbooks = useQuery({
    queryKey: ["workbooks"],
    queryFn: () => api.listWorkbooks(),
    retry: 1,
  });

  const startAnalysis = useMutation({
    mutationFn: (workbookId: string) => api.startAnalysis(workbookId),
    onError: (error: unknown) => setUploadError(apiErrorMessage(error)),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadWorkbook(file),
    onSuccess: (data) => {
      setUploadError(null);
      setActiveId(data.workbook_id);
      startAnalysis.mutate(data.workbook_id);
      void queryClient.invalidateQueries({ queryKey: ["workbooks"] });
    },
    onError: (error: unknown) => setUploadError(apiErrorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: (workbookId: string) => api.deleteWorkbook(workbookId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workbooks"] }),
    onError: (error: unknown) => setUploadError(apiErrorMessage(error)),
  });

  const analyzing = activeId !== null;
  const { latest, done, failed, streamError } = useProgress(activeId, analyzing);

  const finishedId = done && !failed && latest?.stage === "persist" ? activeId : null;
  useEffect(() => {
    if (finishedId) {
      setActiveId(null);
      void navigate(`/w/${finishedId}`);
    }
  }, [finishedId, navigate]);

  const busy = upload.isPending || (analyzing && !done);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Analyze a workbook"
        description="Upload an inherited .xlsx file. SheetSense maps its formulas, flags suspicious cells, and explains what it does. All on your machine."
      />

      <HealthBanner />

      <Card className="p-5 sm:p-6">
        <FileDropzone onFile={(file) => upload.mutate(file)} disabled={busy} />
        {uploadError && (
          <div className="mt-4">
            <ErrorState message={uploadError} />
          </div>
        )}
        {analyzing && latest && (
          <div className="mt-4 border-t border-night-600 pt-4">
            <ProgressBar
              percent={latest.percent}
              detail={latest.detail}
              failed={failed}
            />
          </div>
        )}
        {analyzing && failed && latest && (
          <div className="mt-4">
            <ErrorState
              message={`Analysis failed: ${latest.detail}`}
              onRetry={() => setActiveId(null)}
            />
          </div>
        )}
        {streamError && (
          <div className="mt-4">
            <ErrorState message={streamError} />
          </div>
        )}
      </Card>

      <section aria-label="Past workbooks" className="space-y-3">
        <SectionTitle>Past workbooks</SectionTitle>
        {workbooks.isPending && <LoadingState what="workbooks" />}
        {workbooks.isError && (
          <ErrorState
            message={apiErrorMessage(workbooks.error)}
            onRetry={() => workbooks.refetch()}
          />
        )}
        {workbooks.isSuccess && workbooks.data.workbooks.length === 0 && (
          <EmptyState message="No workbooks yet. Upload an .xlsx file to begin." />
        )}
        {workbooks.isSuccess && workbooks.data.workbooks.length > 0 && (
          <Card className="divide-y divide-night-600 overflow-hidden p-0">
            {workbooks.data.workbooks.map((workbook) => (
              <div
                key={workbook.workbook_id}
                className="flex items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-night-700/50 sm:px-5"
              >
                <div className="min-w-0">
                  <Link
                    to={`/w/${workbook.workbook_id}`}
                    className="block truncate font-mono text-base font-medium text-night-100 hover:text-link hover:underline"
                  >
                    {workbook.filename}
                  </Link>
                  <p className="mt-0.5 flex items-center gap-2 font-mono text-sm text-night-400">
                    <span
                      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-semibold ring-inset ${STATUS_STYLES[workbook.status] ?? STATUS_STYLES.uploaded}`}
                    >
                      {workbook.status}
                    </span>
                    {workbook.error ? (
                      <span className="truncate text-danger">{workbook.error}</span>
                    ) : null}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => remove.mutate(workbook.workbook_id)}
                  disabled={remove.isPending}
                  aria-label={`Delete ${workbook.filename}`}
                  className="shrink-0 rounded-md border border-night-600 px-2.5 py-1.5 font-mono text-sm font-medium text-night-400 hover:border-danger/50 hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                >
                  Delete
                </button>
              </div>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}

function HealthBanner() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
  });
  if (health.isPending || health.isError) return null;
  const { ollama, model } = health.data;
  if (ollama.reachable && model.available) return null;
  return (
    <p
      role="status"
      className="rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn"
    >
      Plain-English explanations are unavailable in this state.{" "}
      <Link to="/setup" className="font-semibold underline hover:text-night-100">
        Open Setup
      </Link>{" "}
      for the exact fix. Formulas, dependencies and suspicious cells still work.
    </p>
  );
}
