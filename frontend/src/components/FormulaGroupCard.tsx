import type { GroupWithExplanation, Issue } from "../api/types";
import { IssueList } from "./IssueList";

function rangeLabel(cells: string[]): string {
  if (cells.length === 0) return "";
  if (cells.length === 1) return cells[0];
  return `${cells[0]}:${cells[cells.length - 1]}`;
}

/** One formula group: explanation, original formula, range, labels, issues. */
export function FormulaGroupCard({
  workbookId,
  group,
  issues,
}: {
  workbookId: string;
  group: GroupWithExplanation;
  issues: Issue[];
}) {
  const labelEntries = Object.entries(group.labels ?? {});
  return (
    <section
      id={`group-${group.id}`}
      aria-label={`Formula group ${group.sheet}!${rangeLabel(group.cells)}`}
      className="scroll-mt-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <h3 className="font-mono text-sm font-semibold">
        {group.sheet}!{rangeLabel(group.cells)}{" "}
        <span className="font-sans font-normal text-gray-500">
          ({group.cells.length} {group.cells.length === 1 ? "cell" : "cells"})
        </span>
      </h3>
      <p className="mt-2 text-sm">
        {group.explanation ? group.explanation.text : "Explanation unavailable."}
      </p>
      <p className="mt-1 font-mono text-xs text-gray-700">
        Formula: <code>{group.sample_formula}</code>
      </p>
      {labelEntries.length > 0 && (
        <dl className="mt-2 text-xs text-gray-600">
          {labelEntries.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <dt className="font-mono text-gray-500">{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {issues.length > 0 && (
        <div className="mt-3">
          <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
            Suspicious cells in this group
          </h4>
          <IssueList workbookId={workbookId} issues={issues} />
        </div>
      )}
    </section>
  );
}
