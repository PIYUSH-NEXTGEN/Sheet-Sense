import type { Issue } from "../api/types";
import { CellChip } from "./CellChip";
import { Card, DetectorTag, SeverityBadge } from "./ui";

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
          <li key={issue.id}>
            <Card className="p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={issue.severity} />
                <DetectorTag name={issue.detector} />
                <CellChip
                  workbookId={workbookId}
                  sheet={issue.ref.sheet}
                  address={issue.ref.address}
                />
              </div>
              <p className="mt-2.5 text-sm leading-relaxed text-night-100">
                {issue.message}
              </p>
              {typeof formula === "string" && formula && (
                <p className="mt-2 overflow-x-auto rounded-md border border-night-600 bg-night-950 px-3 py-2 font-mono text-sm text-night-100">
                  <span className="mr-2 text-night-400">Formula</span>
                  <code>{formula}</code>
                </p>
              )}
              {neighborEntries(issue).length > 0 && (
                <div className="mt-2">
                  <p className="font-mono text-sm text-night-400">
                    Neighbor evidence
                  </p>
                  <ul className="mt-1 space-y-1 font-mono text-sm text-night-300">
                    {neighborEntries(issue).map(([address, neighborFormula]) => (
                      <li key={address} className="truncate">
                        <span className="text-night-400">{address}</span>{" "}
                        <code>{neighborFormula}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
