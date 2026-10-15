import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AskResponse } from "../api/types";
import { CellChip } from "./CellChip";
import { ErrorState, LoadingState } from "./States";
import { PrimaryButton, Card } from "./ui";
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
        <Card className="border-dashed px-5 py-6">
          <p role="status" className="font-mono text-sm text-night-400">
            No questions yet. Try{" "}
            <q className="font-medium text-night-300">
              Where does the total with surcharge come from?
            </q>
          </p>
        </Card>
      )}
      <ol className="space-y-4" aria-live="polite">
        {turns.map((turn, index) => (
          <li
            key={`${index}-${turn.question}`}
            className="space-y-2"
          >
            <div className="ml-auto w-fit max-w-[85%] rounded-lg rounded-br-sm bg-accent px-4 py-2.5 font-mono text-sm font-medium text-accent-ink">
              {turn.question}
            </div>
            <Card className="border-l-2 border-l-accent p-4 sm:p-5">
              {!turn.answer.traced && (
                <p className="mb-2 inline-block rounded-md border border-night-600 bg-night-950 px-2 py-0.5 font-mono text-sm text-night-300">
                  General answer, not traced to specific cells
                </p>
              )}
              <p className="text-sm leading-relaxed text-night-100">
                {turn.answer.answer}
              </p>
              {turn.answer.cited_cells.length > 0 && (
                <div
                  className="mt-3 flex flex-wrap gap-1.5 border-t border-night-600 pt-3"
                  aria-label="Cited cells"
                >
                  {turn.answer.cited_cells.map((ref) =>
                    chipTarget(workbookId, turn, ref),
                  )}
                </div>
              )}
              {turn.answer.chain.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-mono text-sm font-medium text-link hover:underline">
                    Traced formulas ({turn.answer.chain.length})
                  </summary>
                  <ul className="mt-2 space-y-1 font-mono text-night-300">
                    {turn.answer.chain.map((entry) => (
                      <li
                        key={entry.ref}
                        className="truncate rounded border border-night-600 bg-night-950 px-2 py-1"
                      >
                        <span className="text-link">{entry.ref}</span>
                        <span className="text-night-600"> · </span>
                        <code>{entry.formula ?? "no formula"}</code>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </Card>
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

      <form
        onSubmit={submit}
        className="sticky bottom-4 flex gap-2 rounded-lg border border-night-600 bg-night-800 p-2"
      >
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
          autoComplete="off"
          className="min-w-0 flex-1 rounded-md bg-transparent px-3 py-2 font-mono text-sm text-night-100 outline-none placeholder:text-night-600 disabled:opacity-60"
        />
        <PrimaryButton
          type="submit"
          disabled={ask.isPending || draft.trim() === ""}
        >
          Ask
        </PrimaryButton>
      </form>
    </div>
  );
}
