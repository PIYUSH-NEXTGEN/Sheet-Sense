import { useEffect, useState } from "react";
import { subscribeProgress } from "../api/client";
import type { ProgressEvent } from "../api/types";

/** SSE-backed analysis progress for one workbook. */
export function useProgress(workbookId: string | null, active: boolean) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  useEffect(() => {
    if (!workbookId || !active) return;
    setEvents([]);
    setStreamError(null);
    return subscribeProgress(
      workbookId,
      (event) => setEvents((prev) => [...prev, event]),
      (message) => setStreamError(message),
    );
  }, [workbookId, active]);

  const latest = events.length > 0 ? events[events.length - 1] : null;
  const done = events.some(
    (event) => event.stage === "persist" || event.stage === "failed",
  );
  const failed = events.some((event) => event.stage === "failed");
  return { events, latest, done, failed, streamError };
}
