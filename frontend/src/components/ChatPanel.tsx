import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AskResponse } from "../api/types";
import { CellChip } from "./CellChip";
import { ErrorState, LoadingState } from "./States";
import { apiErrorMessage } from "../hooks/useWorkbook";

interface Turn {
  question: string;
  answer: AskResponse;
}

function chipTarget(workbookId: string, turn: Turn, ref: string) {
  const entry = turn.answer.chain.find((item) => item.ref === ref);
  const [sheet, address] = ref.split("!");
  return (
    <CellChip
      key={ref}
      workbookId={workbookId}
      sheet={entry?.sheet ?? sheet ?? ref}
      address={entry?.address ?? address ?? ""}
      groupId={entry?.group_id}
    />
  );
}

/** Chat panel: ask where a number comes from, see the traced chain. */
export function ChatPanel({ workbookId }: { workbookId: string }) {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);

  const ask = useMutation({
    mutationFn: (question: string) => api.ask(workbookId, question),
    onSuccess: (answer, question) => {
      setTurns((prev) => [...prev, { question, answer }]);
      setDraft("");
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (question && !ask.isPending) ask.mutate(question);
  }

  return (
    <div className="space-y-4">
      {turns.length === 0 && !ask.isPending && (
        <p role="status" className="text-sm text-gray-500">
          No questions yet. Try “Where does the total with surcharge come
          from?”
        </p>
      )}
      <ol className="space-y-3" aria-live="polite">
        {turns.map((turn, index) => (
          <li
            key={`${index}-${turn.question}`}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <p className="font-medium">{turn.question}</p>
            <p className="mt-2 text-sm">{turn.answer.answer}</p>
            {turn.answer.cited_cells.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1" aria-label="Cited cells">
                {turn.answer.cited_cells.map((ref) => chipTarget(workbookId, turn, ref))}
              </div>
            )}
            {turn.answer.chain.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-blue-700 hover:underline">
                  Show traced formulas ({turn.answer.chain.length})
                </summary>
                <ul className="mt-1 space-y-0.5 font-mono text-gray-700">
                  {turn.answer.chain.map((entry) => (
                    <li key={entry.ref}>
                      {entry.ref}: <code>{entry.formula ?? "—"}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ol>

      {ask.isPending && <LoadingState what="answer" />}
      {ask.isError && (
        <ErrorState
          message={apiErrorMessage(ask.error)}
          onRetry={() => ask.reset()}
        />
      )}

      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="ask-input" className="sr-only">
          Ask where a number comes from
        </label>
        <input
          id="ask-input"
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Where does the total with surcharge come from?"
          disabled={ask.isPending}
          className="flex-1 rounded border border-gray-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={ask.isPending || draft.trim() === ""}
          className="rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
