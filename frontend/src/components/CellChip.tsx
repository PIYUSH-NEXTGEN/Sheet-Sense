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
      className="inline-flex items-center rounded-md border border-link/40 bg-link/10 px-1.5 py-0.5 font-mono text-sm font-medium text-link hover:bg-link/20 hover:underline"
      aria-label={`Go to ${sheet}!${address}`}
    >
      {sheet}!{address}
    </Link>
  );
}
