/** Accessible progress bar for analysis progress. */
export function ProgressBar({
  percent,
  detail,
  failed,
}: {
  percent: number;
  detail: string;
  failed?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="w-full" aria-live="polite">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-label={failed ? "Analysis failed" : "Analysis progress"}
        className="h-3 w-full overflow-hidden rounded bg-gray-200"
      >
        <div
          className={`h-full transition-all ${failed ? "bg-red-500" : "bg-blue-600"}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <p className="mt-1 text-sm text-gray-600">
        {clamped}% — {detail}
      </p>
    </div>
  );
}
