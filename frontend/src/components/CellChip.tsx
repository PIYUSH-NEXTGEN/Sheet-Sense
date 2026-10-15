import { Link } from "react-router-dom";

/** Clickable cell reference that navigates to its sheet. */
export function CellChip({
  workbookId,
  sheet,
  address,
}: {
  workbookId: string;
  sheet: string;
  address: string;
}) {
  return (
    <Link
      to={`/w/${workbookId}/sheets/${encodeURIComponent(sheet)}`}
      className="inline-block rounded bg-blue-50 px-1.5 py-0.5 font-mono text-xs text-blue-800 hover:bg-blue-100 hover:underline"
      aria-label={`Go to ${sheet}!${address}`}
    >
      {sheet}!{address}
    </Link>
  );
}
