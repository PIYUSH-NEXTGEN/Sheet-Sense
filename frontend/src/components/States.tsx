/** Shared loading / empty / error states used by every page. */
export function LoadingState({ what }: { what: string }) {
  return (
    <p role="status" className="py-8 text-center text-gray-600">
      Loading {what}…
    </p>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <p role="status" className="rounded-lg border border-dashed border-gray-300 bg-white py-8 text-center text-gray-500">
      {message}
    </p>
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
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4">
      <p className="text-sm text-red-800">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded bg-red-700 px-3 py-1 text-sm text-white hover:bg-red-800"
        >
          Retry
        </button>
      )}
    </div>
  );
}
