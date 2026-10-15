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
        className="h-2.5 w-full overflow-hidden rounded-md bg-night-950"
      >
        <div
          className={`h-full rounded-md transition-all duration-300 ${failed ? "bg-danger" : "bg-accent"}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="mt-1.5 flex items-baseline justify-between gap-2">
        <p className="truncate font-mono text-sm text-night-400">{detail}</p>
        <p className="tnum shrink-0 font-mono text-sm font-bold text-night-100">
          {clamped}%
        </p>
      </div>
    </div>
  );
}
