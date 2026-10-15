import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { FormulaGroupCard } from "../components/FormulaGroupCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageHeader } from "../components/ui";
import { apiErrorMessage } from "../hooks/useWorkbook";

/** One sheet: a FormulaGroupCard per group plus the sheet's issues. */
export function SheetPage() {
  const { id, name } = useParams<{ id: string; name: string }>();
  const sheet = useQuery({
    queryKey: ["sheet", id, name],
    queryFn: () => api.getSheet(id as string, name as string),
    enabled: Boolean(id && name),
    retry: 1,
  });

  if (sheet.isPending) return <LoadingState what={`sheet ${name}`} />;
  if (sheet.isError) {
    return (
      <ErrorState
        message={apiErrorMessage(sheet.error)}
        onRetry={() => sheet.refetch()}
      />
    );
  }

  const data = sheet.data;
  return (
    <div className="space-y-5">
      <PageHeader
        title={data.sheet}
        description={data.explanation ? data.explanation.text : undefined}
      />
      {data.inputs.length > 0 && (
        <section aria-label="Input values" className="space-y-3">
          <h2 className="font-mono text-base font-semibold tracking-tight text-night-100">
            Input values ({data.inputs.length})
          </h2>
          <div className="overflow-x-auto rounded-lg border border-night-600 bg-night-800">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead>
                <tr className="border-b border-night-600 font-mono text-night-400">
                  <th scope="col" className="px-4 py-2 font-medium">Cell</th>
                  <th scope="col" className="px-4 py-2 font-medium">Label</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-night-600/60">
                {data.inputs.map((input) => (
                  <tr key={input.address} className="hover:bg-night-700/40">
                    <td className="tnum px-4 py-1.5 font-mono text-link">
                      {input.address}
                    </td>
                    <td className="px-4 py-1.5 text-night-300">
                      {[input.label_left, input.label_above]
                        .filter(Boolean)
                        .join(" / ") || "n/a"}
                    </td>
                    <td className="tnum px-4 py-1.5 text-right font-mono font-medium text-night-100">
                      {String(input.value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {data.groups.length === 0 && data.inputs.length === 0 ? (
        <EmptyState message="No formula groups or inputs on this sheet." />
      ) : (
        <div className="space-y-4">
          {data.groups.map((group) => (
            <FormulaGroupCard
              key={group.id}
              workbookId={data.workbook_id}
              group={group}
              issues={data.issues.filter((issue) =>
                group.cells.includes(issue.ref.address),
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}
