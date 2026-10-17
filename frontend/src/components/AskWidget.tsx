import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChatPanel } from "./ChatPanel";

/** Event name any page button can dispatch to open the chat drawer. */
export const OPEN_ASK_EVENT = "sheetsense:ask-open";

export function openAskDrawer() {
  window.dispatchEvent(new CustomEvent(OPEN_ASK_EVENT));
}

/**
 * Floating Ask button + slide-over chat drawer, mounted once in the app
 * layout. Visible on every workbook page (`/w/:id/...`); the chat opens
 * over the current page so context is never lost to navigation.
 */
export function AskWidget() {
  const location = useLocation();
  const [open, setOpen] = useState(false);

  const match = location.pathname.match(/^\/w\/([^/]+)/);
  const workbookId = match?.[1] ?? null;

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener(OPEN_ASK_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_ASK_EVENT, onOpen);
  }, []);

  // Close on navigation; lock body scroll while open.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timer = window.setTimeout(() => {
      document.getElementById("ask-input")?.focus();
    }, 50);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [open ]);

  if (!workbookId) return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Ask about this workbook"
          className="fixed bottom-6 right-6 z-40 inline-flex min-h-[48px] items-center gap-2 rounded-full bg-accent px-5 font-mono text-sm font-bold text-accent-ink shadow-[0_4px_16px_rgba(0,0,0,0.45)] hover:brightness-110"
        >
          <svg
            aria-hidden="true"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
          </svg>
          Ask
        </button>
      )}
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Ask about this workbook"
          className="fixed inset-0 z-50"
        >
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 right-0 flex w-full flex-col border-l border-night-600 bg-night-900 sm:max-w-md">
            <div className="flex items-center justify-between border-b border-night-600 px-4 py-3">
              <h2 className="font-mono text-base font-bold tracking-tight text-night-100">
                Ask about this workbook
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                className="rounded-md border border-night-600 px-2.5 py-1.5 font-mono text-sm text-night-300 hover:border-night-400 hover:text-night-100"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-4">
              <ChatPanel workbookId={workbookId} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
