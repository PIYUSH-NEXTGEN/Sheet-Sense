import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DependencyGraph } from "../components/DependencyGraph";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, PageHeader, SecondaryButton, SectionTitle, Stat } from "../components/ui";
import { apiErrorMessage, useWorkbook } from "../hooks/useWorkbook";

/** Workbook overview: explanation, stats, dependency map, sheets. */
export function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const overview = useWorkbook(id);
  const [exportError, setExportError] = useState<string | null>(null);

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
    try {
      const blob = await api.exportMarkdown(data.workbook_id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${data.filename.replace(/\.xlsx$/i, "")}.md`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setExportError(apiErrorMessage(error));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={data.filename}
        description="Plain-English overview, dependency map and entry points into the workbook."
        actions={
          <>
            <Link
              to={`/w/${data.workbook_id}/issues`}
              className="inline-flex w-full items-center justify-center rounded-md bg-accent px-3.5 py-2 font-mono text-sm font-bold text-accent-ink hover:brightness-110 sm:w-auto"
            >
              Suspicious cells to review
            </Link>
            <Link
              to={`/w/${data.workbook_id}/ask`}
              className="inline-flex w-full items-center justify-center rounded-md border border-night-600 bg-transparent px-3.5 py-2 font-mono text-sm font-medium text-night-100 hover:border-night-400 hover:bg-night-700 sm:w-auto"
            >
              Ask a question
            </Link>
            <SecondaryButton
              onClick={() => void downloadExport()}
              className="w-full sm:w-auto"
            >
              Export Markdown
            </SecondaryButton>
          </>
        }
      />
      {exportError && <ErrorState message={exportError} />}

      <Card className="p-5 sm:p-6">
        <SectionTitle>What this workbook does</SectionTitle>
        <p className="mt-2 text-sm leading-relaxed text-night-100">
          {data.explanation.text}
        </p>
        {data.warnings.length > 0 && (
          <ul className="mt-3 space-y-1 border-t border-night-600 pt-3 text-sm">
            {data.warnings.map((warning) => (
              <li key={warning} className="flex gap-2 text-warn">
                <span className="font-mono font-semibold">
                  Warning
                </span>
                <span className="font-mono">{warning}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <section aria-label="Statistics">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Sheets" value={String(data.stats.sheets.length)} />
          <Stat label="Formulas" value={String(data.stats.n_formulas)} />
          <Stat label="Inputs" value={String(data.stats.n_inputs)} />
          <Stat label="Outputs" value={String(data.stats.n_outputs)} />
          <Stat label="Groups" value={String(data.stats.n_groups)} />
          <Stat label="High" value={String(counts.high ?? 0)} />
          <Stat label="Medium" value={String(counts.medium ?? 0)} />
          <Stat label="Low" value={String(counts.low ?? 0)} />
        </dl>
      </section>

      <section aria-label="Dependency map" className="space-y-3">
        <SectionTitle>Dependency map</SectionTitle>
        <DependencyGraph workbookId={data.workbook_id} />
      </section>

      <section aria-label="Sheets" className="space-y-3">
        <SectionTitle>Sheets</SectionTitle>
        {data.stats.sheets.length === 0 ? (
          <EmptyState message="No sheets found in this workbook." />
        ) : (
          <Card className="divide-y divide-night-600 overflow-hidden p-0">
            {data.stats.sheets.map((sheet) => (
              <Link
                key={sheet}
                to={`/w/${data.workbook_id}/sheets/${encodeURIComponent(sheet)}`}
                className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-night-700/50 sm:px-5"
              >
                <span className="font-mono text-base font-medium text-night-100">{sheet}</span>
                <span aria-hidden="true" className="text-night-400">
                  →
                </span>
              </Link>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}
