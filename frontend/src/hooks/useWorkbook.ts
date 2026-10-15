import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Overview } from "../api/types";

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** Workbook overview (analysis result) by id. */
export function useWorkbook(workbookId: string | undefined) {
  return useQuery<Overview, ApiError>({
    queryKey: ["overview", workbookId],
    queryFn: () => api.getOverview(workbookId as string),
    enabled: Boolean(workbookId),
    retry: 1,
  });
}
