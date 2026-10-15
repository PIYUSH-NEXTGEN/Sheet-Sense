import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Severity } from "../api/types";
import { IssueList } from "../components/IssueList";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
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
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Suspicious cells to review</h1>
      <p className="text-sm text-gray-600">
        {filtered.length} of {all.length} shown. These are hints, not proof of
        errors — always check the formula and neighbors.
      </p>

      <div className="flex flex-wrap gap-4">
        <label className="text-sm">
          Severity{" "}
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as "all" | Severity)}
            className="rounded border border-gray-300 px-2 py-1"
          >
            {SEVERITIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Detector{" "}
          <select
            value={detector}
            onChange={(e) => setDetector(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
          >
            {detectors.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      {all.length === 0 ? (
        <EmptyState message="No suspicious cells to review — nothing flagged in this workbook." />
      ) : filtered.length === 0 ? (
        <EmptyState message="No suspicious cells match these filters." />
      ) : (
        <IssueList workbookId={issues.data.workbook_id} issues={filtered} />
      )}
    </div>
  );
}
