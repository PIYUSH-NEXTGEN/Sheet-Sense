import { Card } from "./ui";

/** Shared loading / empty / error states used by every page. */
export function LoadingState({ what }: { what: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-3 py-10">
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-night-600 border-t-accent"
      />
      <p className="font-mono text-sm text-night-400">Loading {what}…</p>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <Card className="border-dashed px-6 py-10 text-center">
      <p role="status" className="text-sm text-night-400">
        {message}
      </p>
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3"
    >
      <p className="text-sm font-medium text-danger">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded-md bg-danger px-3 py-1.5 font-mono text-sm font-bold text-night-950 hover:brightness-110"
        >
          Retry
        </button>
      )}
    </div>
  );
}
