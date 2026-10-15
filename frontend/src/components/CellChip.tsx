import { Link } from "react-router-dom";

/** Clickable cell reference navigating to its sheet (and group, if known). */
export function CellChip({
  workbookId,
  sheet,
  address,
  groupId,
}: {
  workbookId: string;
  sheet: string;
  address: string;
  groupId?: string | null;
}) {
  const to =
    groupId != null
      ? `/w/${workbookId}/sheets/${encodeURIComponent(sheet)}#group-${groupId}`
      : `/w/${workbookId}/sheets/${encodeURIComponent(sheet)}`;
  return (
    <Link
      to={to}
      className="inline-block rounded bg-blue-50 px-1.5 py-0.5 font-mono text-xs text-blue-800 hover:bg-blue-100 hover:underline"
      aria-label={`Go to ${sheet}!${address}`}
    >
      {sheet}!{address}
    </Link>
  );
}
