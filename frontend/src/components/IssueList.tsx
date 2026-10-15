import type { Issue } from "../api/types";
import { CellChip } from "./CellChip";

const SEVERITY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-gray-100 text-gray-700",
};

function neighborEntries(issue: Issue): Array<[string, string]> {
  const neighbors = issue.evidence["neighbors"];
  if (typeof neighbors !== "object" || neighbors === null) return [];
  return Object.entries(neighbors as Record<string, unknown>)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .slice(0, 8);
}

/** List of suspicious cells to review with evidence next to every claim. */
export function IssueList({
  workbookId,
  issues,
}: {
  workbookId: string;
  issues: Issue[];
}) {
  return (
    <ul className="space-y-3">
      {issues.map((issue) => {
        const formula = issue.evidence["formula"];
        return (
          <li
            key={issue.id}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.low}`}
              >
                {issue.severity}
              </span>
              <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">
                {issue.detector}
              </span>
              <CellChip
                workbookId={workbookId}
                sheet={issue.ref.sheet}
                address={issue.ref.address}
              />
            </div>
            <p className="mt-2 text-sm">{issue.message}</p>
            {typeof formula === "string" && formula && (
              <p className="mt-1 font-mono text-xs text-gray-700">
                Formula: <code>{formula}</code>
              </p>
            )}
            {neighborEntries(issue).length > 0 && (
              <div className="mt-1 text-xs text-gray-600">
                <span className="font-medium">Neighbors: </span>
                <ul className="mt-1 space-y-0.5 font-mono">
                  {neighborEntries(issue).map(([address, neighborFormula]) => (
                    <li key={address}>
                      {address}: <code>{neighborFormula}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
