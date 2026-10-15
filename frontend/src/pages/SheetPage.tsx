import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { FormulaGroupCard } from "../components/FormulaGroupCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
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
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{data.sheet}</h1>
      {data.explanation && (
        <p className="text-sm text-gray-700">{data.explanation.text}</p>
      )}
      {data.groups.length === 0 ? (
        <EmptyState message="No formula groups on this sheet." />
      ) : (
        <div className="space-y-3">
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
