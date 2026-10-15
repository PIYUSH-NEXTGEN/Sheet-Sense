import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { FileDropzone } from "../components/FileDropzone";
import { ProgressBar } from "../components/ProgressBar";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useProgress } from "../hooks/useProgress";
import { apiErrorMessage } from "../hooks/useWorkbook";

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
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Upload a workbook</h1>

      <HealthBanner />

      <FileDropzone onFile={(file) => upload.mutate(file)} disabled={busy} />
      {uploadError && <ErrorState message={uploadError} />}

      {analyzing && latest && (
        <ProgressBar
          percent={latest.percent}
          detail={latest.detail}
          failed={failed}
        />
      )}
      {analyzing && failed && latest && (
        <ErrorState
          message={`Analysis failed: ${latest.detail}`}
          onRetry={() => {
            setActiveId(null);
          }}
        />
      )}
      {streamError && <ErrorState message={streamError} />}

      <section aria-label="Past workbooks" className="space-y-2">
        <h2 className="text-lg font-semibold">Past workbooks</h2>
        {workbooks.isPending && <LoadingState what="workbooks" />}
        {workbooks.isError && (
          <ErrorState
            message={apiErrorMessage(workbooks.error)}
            onRetry={() => workbooks.refetch()}
          />
        )}
        {workbooks.isSuccess && workbooks.data.workbooks.length === 0 && (
          <EmptyState message="No workbooks yet — upload an .xlsx file to begin." />
        )}
        {workbooks.isSuccess && workbooks.data.workbooks.length > 0 && (
          <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
            {workbooks.data.workbooks.map((workbook) => (
              <li
                key={workbook.workbook_id}
                className="flex items-center justify-between gap-2 p-3"
              >
                <div className="min-w-0">
                  <Link
                    to={`/w/${workbook.workbook_id}`}
                    className="block truncate font-medium text-blue-700 hover:underline"
                  >
                    {workbook.filename}
                  </Link>
                  <p className="text-xs text-gray-500">
                    {workbook.status}
                    {workbook.error ? ` — ${workbook.error}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => remove.mutate(workbook.workbook_id)}
                  disabled={remove.isPending}
                  aria-label={`Delete ${workbook.filename}`}
                  className="rounded border border-gray-300 px-2 py-1 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
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
    <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
      Explanations are unavailable —{" "}
      <Link to="/setup" className="font-medium text-blue-700 hover:underline">
        open Setup
      </Link>{" "}
      for the exact fix commands. Formulas, dependencies and suspicious cells
      still work.
    </p>
  );
}
