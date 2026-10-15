import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Severity } from "../api/types";
import { IssueList } from "../components/IssueList";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, PageHeader } from "../components/ui";
import { apiErrorMessage } from "../hooks/useWorkbook";

const SEVERITIES: Array<"all" | Severity> = ["all", "high", "medium", "low"];

/** Suspicious cells to review, filterable by severity and detector. */
export function IssuesPage() {
  const { id } = useParams<{ id: string }>();
  const [severity, setSeverity] = useState<"all" | Severity>("all");
  const [detector, setDetector] = useState<string>("all");

  const issues = useQuery({
    queryKey: ["issues", id],
    queryFn: () => api.getIssues(id as string),
    enabled: Boolean(id),
    retry: 1,
  });

  if (issues.isPending) return <LoadingState what="suspicious cells" />;
  if (issues.isError) {
    return (
      <ErrorState
        message={apiErrorMessage(issues.error)}
        onRetry={() => issues.refetch()}
      />
    );
  }

  const all = issues.data.issues;
  const detectors = ["all", ...Array.from(new Set(all.map((i) => i.detector))).sort()];
  const filtered = all.filter(
    (issue) =>
      (severity === "all" || issue.severity === severity) &&
      (detector === "all" || issue.detector === detector),
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Suspicious cells to review"
        description={`${filtered.length} of ${all.length} shown. These are hints, not proof of errors. Always check the formula and neighbors.`}
      />

      <Card className="flex flex-wrap gap-x-6 gap-y-3 px-4 py-3 sm:px-5">
        <label className="flex items-center gap-2 font-mono text-sm text-night-400">
          <span className="font-medium">Severity</span>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as "all" | Severity)}
            className="rounded-md border border-night-600 bg-night-950 px-2 py-1.5 text-sm text-night-100"
          >
            {SEVERITIES.map((option) => (
              <option key={option} value={option}>
                {option === "all" ? "All severities" : option}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 font-mono text-sm text-night-400">
          <span className="font-medium">Detector</span>
          <select
            value={detector}
            onChange={(e) => setDetector(e.target.value)}
            className="rounded-md border border-night-600 bg-night-950 px-2 py-1.5 font-mono text-sm text-night-100"
          >
            {detectors.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </Card>

      {all.length === 0 ? (
        <EmptyState message="No suspicious cells to review. Nothing flagged in this workbook." />
      ) : filtered.length === 0 ? (
        <EmptyState message="No suspicious cells match these filters." />
      ) : (
        <IssueList workbookId={issues.data.workbook_id} issues={filtered} />
      )}
    </div>
  );
}
