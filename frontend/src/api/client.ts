/**
 * Local-backend REST client. The only runtime network calls the app makes
 * are to this URL — no CDN assets, no telemetry.
 */
import type {
  AskResponse,
  GraphData,
  GraphLevel,
  HealthStatus,
  IssuesResponse,
  Overview,
  ProgressEvent,
  Severity,
  SheetDetail,
  WorkbookList,
} from "./types";

export const API_BASE = "http://127.0.0.1:8000";
export const MAX_FILE_MB = 10;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Guard against talking to the wrong server on port 8000 (or a stale
 * backend): a mistyped shape becomes an actionable error state, never a
 * white-screen render crash.
 */
function checkShape(
  condition: boolean,
  what: string,
): asserts condition {
  if (!condition) {
    throw new ApiError(
      0,
      `Unexpected response from the backend (${what}). ` +
        "Is the SheetSense backend running on port 8000?",
    );
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the backend at http://127.0.0.1:8000.");
  }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body: unknown = await resp.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // keep the status text
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export interface UploadResult {
  workbook_id: string;
  filename: string;
  status: string;
}

export const api = {
  health(): Promise<HealthStatus> {
    return request<HealthStatus>("/api/health").then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          typeof (body as { ollama?: unknown }).ollama === "object" &&
          typeof (body as { model?: unknown }).model === "object",
        "health status",
      );
      return body;
    });
  },

  listWorkbooks(): Promise<WorkbookList> {
    return request<WorkbookList>("/api/workbooks").then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          Array.isArray((body as { workbooks?: unknown }).workbooks),
        "workbook list",
      );
      return body;
    });
  },

  uploadWorkbook(file: File): Promise<UploadResult> {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<UploadResult>("/api/workbooks", {
      method: "POST",
      body: form,
    });
  },

  deleteWorkbook(workbookId: string): Promise<{ deleted: string }> {
    return request(`/api/workbooks/${workbookId}`, { method: "DELETE" });
  },

  startAnalysis(workbookId: string): Promise<{ workbook_id: string; status: string }> {
    return request(`/api/workbooks/${workbookId}/analyze`, { method: "POST" });
  },

  getOverview(workbookId: string): Promise<Overview> {
    return request<Overview>(`/api/workbooks/${workbookId}/overview`).then(
      (body) => {
        checkShape(
          typeof body === "object" &&
            body !== null &&
            typeof (body as { stats?: unknown }).stats === "object" &&
            Array.isArray(
              (body as { stats?: { sheets?: unknown } }).stats?.sheets,
            ),
          "workbook overview",
        );
        return body;
      },
    );
  },

  getSheet(workbookId: string, sheet: string): Promise<SheetDetail> {
    return request<SheetDetail>(
      `/api/workbooks/${workbookId}/sheets/${encodeURIComponent(sheet)}`,
    ).then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          Array.isArray((body as { groups?: unknown }).groups) &&
          Array.isArray((body as { issues?: unknown }).issues),
        "sheet detail",
      );
      return body;
    });
  },

  getIssues(workbookId: string, severity?: Severity): Promise<IssuesResponse> {
    const query = severity ? `?severity=${severity}` : "";
    return request<IssuesResponse>(
      `/api/workbooks/${workbookId}/issues${query}`,
    ).then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          Array.isArray((body as { issues?: unknown }).issues),
        "issue list",
      );
      return body;
    });
  },

  getGraph(workbookId: string, level: GraphLevel = "sheet"): Promise<GraphData> {
    return request<GraphData>(
      `/api/workbooks/${workbookId}/graph?level=${level}`,
    ).then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          Array.isArray((body as { nodes?: unknown }).nodes) &&
          Array.isArray((body as { edges?: unknown }).edges),
        "dependency graph",
      );
      return body;
    });
  },

  async exportMarkdown(workbookId: string): Promise<Blob> {
    const resp = await fetch(`${API_BASE}/api/workbooks/${workbookId}/export?format=md`);
    if (!resp.ok) {
      throw new ApiError(resp.status, `Export failed: ${resp.statusText}`);
    }
    return await resp.blob();
  },

  ask(workbookId: string, question: string): Promise<AskResponse> {
    return request<AskResponse>(`/api/workbooks/${workbookId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then((body) => {
      checkShape(
        typeof body === "object" &&
          body !== null &&
          typeof (body as { answer?: unknown }).answer === "string" &&
          Array.isArray((body as { cited_cells?: unknown }).cited_cells) &&
          Array.isArray((body as { chain?: unknown }).chain),
        "answer",
      );
      return body;
    });
  },
};

/**
 * Subscribe to SSE progress events. Returns an unsubscribe function.
 * The server closes the stream once the analysis is done or failed.
 */
export function subscribeProgress(
  workbookId: string,
  onEvent: (event: ProgressEvent) => void,
  onError?: (message: string) => void,
): () => void {
  const source = new EventSource(
    `${API_BASE}/api/workbooks/${encodeURIComponent(workbookId)}/progress`,
  );
  source.onmessage = (message: MessageEvent) => {
    try {
      onEvent(JSON.parse(message.data) as ProgressEvent);
    } catch {
      onError?.("Received an unreadable progress event.");
    }
  };
  source.onerror = () => {
    onError?.("Lost connection to the progress stream.");
    source.close();
  };
  return () => source.close();
}
