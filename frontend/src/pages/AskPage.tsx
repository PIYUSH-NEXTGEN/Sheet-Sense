import { useParams } from "react-router-dom";
import { ChatPanel } from "../components/ChatPanel";
import { PageHeader } from "../components/ui";

/** Ask where a number comes from — traced answers with clickable cells. */
export function AskPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <p role="alert">Missing workbook id.</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        title="Ask about this workbook"
        description="Answers trace the calculation chain and cite the exact cells. Click any chip to jump to its sheet."
      />
      <ChatPanel workbookId={id} />
    </div>
  );
}
