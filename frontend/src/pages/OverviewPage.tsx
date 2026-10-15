import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { apiErrorMessage, useWorkbook } from "../hooks/useWorkbook";

/** Workbook overview WITHOUT the dependency map (map lands in Phase 6). */
export function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const overview = useWorkbook(id);

  if (overview.isPending) return <LoadingState what="overview" />;
  if (overview.isError) {
    return (
      <ErrorState
        message={apiErrorMessage(overview.error)}
        onRetry={() => overview.refetch()}
      />
    );
  }

  const data = overview.data;
  const counts = data.issues_by_severity ?? {};

  async function downloadExport() {
    const blob = await api.exportMarkdown(data.workbook_id);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${data.filename.replace(/\.xlsx$/i, "")}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{data.filename}</h1>
        <div className="flex gap-2">
          <Link
            to={`/w/${data.workbook_id}/issues`}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm text-white hover:bg-blue-800"
          >
            Suspicious cells to review
          </Link>
          <button
            type="button"
            onClick={() => void downloadExport()}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100"
          >
            Export Markdown
          </button>
        </div>
      </div>

      <section aria-label="Plain-English overview">
        <h2 className="text-lg font-semibold">What this workbook does</h2>
        <p className="mt-1 text-sm">{data.explanation.text}</p>
      </section>

      {data.warnings.length > 0 && (
        <section aria-label="Warnings">
          <h2 className="text-lg font-semibold">Warnings</h2>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Statistics">
        <h2 className="text-lg font-semibold">Statistics</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Sheets" value={String(data.stats.sheets.length)} />
          <Stat label="Formulas" value={String(data.stats.n_formulas)} />
          <Stat label="Inputs" value={String(data.stats.n_inputs)} />
          <Stat label="Outputs" value={String(data.stats.n_outputs)} />
          <Stat label="Formula groups" value={String(data.stats.n_groups)} />
          <Stat label="High" value={String(counts.high ?? 0)} />
          <Stat label="Medium" value={String(counts.medium ?? 0)} />
          <Stat label="Low" value={String(counts.low ?? 0)} />
        </dl>
      </section>

      <section aria-label="Sheets">
        <h2 className="text-lg font-semibold">Sheets</h2>
        {data.stats.sheets.length === 0 ? (
          <EmptyState message="No sheets found in this workbook." />
        ) : (
          <ul className="mt-2 space-y-1">
            {data.stats.sheets.map((sheet) => (
              <li key={sheet}>
                <Link
                  to={`/w/${data.workbook_id}/sheets/${encodeURIComponent(sheet)}`}
                  className="text-blue-700 hover:underline"
                >
                  {sheet}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <dt className="text-xs uppercase text-gray-500">{label}</dt>
      <dd className="text-xl font-semibold">{value}</dd>
    </div>
  );
}
