import type { GroupWithExplanation, Issue } from "../api/types";
import { IssueList } from "./IssueList";
import { Card } from "./ui";

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
      className="scroll-mt-4"
    >
      <Card className="p-4 sm:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-mono text-base font-bold text-night-100">
            {group.sheet}!{rangeLabel(group.cells)}
          </h3>
          <span className="tnum rounded-md border border-night-600 bg-night-950 px-2 py-0.5 font-mono text-sm text-night-300">
            {group.cells.length} {group.cells.length === 1 ? "cell" : "cells"}
          </span>
          {group.explanation?.source === "template" && (
            <span
              title="Described automatically from the formula pattern; no model call"
              className="rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-sm text-accent"
            >
              auto-described
            </span>
          )}
        </div>
        <p className="mt-2 text-sm leading-relaxed text-night-300">
          {group.explanation ? group.explanation.text : "Explanation unavailable."}
        </p>
        <p className="mt-2 overflow-x-auto rounded-md border border-night-600 bg-night-950 px-3 py-2 font-mono text-sm text-night-100">
          <span className="mr-2 text-night-400">Formula</span>
          <code>{group.sample_formula}</code>
        </p>
        {labelEntries.length > 0 && (
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
            {labelEntries.map(([key, value]) => (
              <div key={key} className="flex gap-2 border-b border-dotted border-night-600 py-1">
                <dt className="shrink-0 font-mono text-night-400">{key}</dt>
                <dd className="truncate text-night-300" title={value}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {issues.length > 0 && (
          <div className="mt-4 border-t border-night-600 pt-3">
          <h4 className="mb-2 font-mono text-sm text-night-400">
            Suspicious cells in this group
          </h4>
            <IssueList workbookId={workbookId} issues={issues} />
          </div>
        )}
      </Card>
    </section>
  );
}
