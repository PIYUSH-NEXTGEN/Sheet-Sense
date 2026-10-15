import { useParams } from "react-router-dom";
import { ChatPanel } from "../components/ChatPanel";

/** Ask where a number comes from — traced answers with clickable cells. */
export function AskPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <p role="alert">Missing workbook id.</p>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Ask about this workbook</h1>
      <ChatPanel workbookId={id} />
    </div>
  );
}
