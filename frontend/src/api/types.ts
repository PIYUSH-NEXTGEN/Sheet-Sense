/**
 * TypeScript mirrors of the backend pydantic models (backend/app/core/models.py)
 * plus the REST response shapes. Keep in sync when the backend changes.
 */

export interface CellRef {
  sheet: string;
  address: string; // "F12"
}

export type CellKind = "input" | "formula" | "label" | "empty";

export interface CellRecord {
  ref: CellRef;
  formula: string | null; // "=D12*E12"
  value: unknown; // cached value; null when never calculated
  number_format: string | null;
  label_left: string | null;
  label_above: string | null;
  kind: CellKind;
}

export interface FormulaGroup {
  id: string;
  sheet: string;
  pattern_r1c1: string;
  cells: string[]; // addresses in the contiguous block
  sample_formula: string;
  labels: Record<string, string>;
  sample_values: unknown[];
}

export type Severity = "high" | "medium" | "low";

export interface Issue {
  id: string;
  detector: string;
  severity: Severity;
  ref: CellRef;
  message: string; // written by code templates, never by the model
  evidence: Record<string, unknown>;
}

export interface Explanation {
  target_type: "group" | "sheet" | "workbook";
  target_id: string;
  text: string;
  structured: Record<string, unknown>;
  model: string;
  prompt_version: string;
}

// --- REST shapes ---

export interface HealthStatus {
  backend: string;
  ollama: { url: string; reachable: boolean };
  model: { name: string; available: boolean };
}

export interface WorkbookSummary {
  workbook_id: string;
  filename: string;
  status: string;
  size_bytes: number;
  created_at: string | null;
  error: string | null;
}

export interface WorkbookList {
  workbooks: WorkbookSummary[];
}

export interface ProgressEvent {
  stage: string;
  percent: number;
  detail: string;
}

export interface Stats {
  sheets: string[];
  n_cells: number;
  n_formulas: number;
  n_inputs: number;
  n_outputs: number;
  n_groups: number;
  issues_by_severity: Record<string, number>;
}

export interface Overview {
  workbook_id: string;
  filename: string;
  status: string;
  explanation: Explanation;
  stats: Stats;
  warnings: string[];
  issues_by_severity: Record<string, number>;
}

export interface GroupWithExplanation extends FormulaGroup {
  explanation: Explanation | null;
}

export interface SheetDetail {
  workbook_id: string;
  sheet: string;
  explanation: Explanation | null;
  groups: GroupWithExplanation[];
  issues: Issue[];
}

export interface IssuesResponse {
  workbook_id: string;
  total: number;
  issues: Issue[];
}

export type GraphLevel = "sheet" | "group";

export interface GraphData {
  workbook_id: string;
  level: GraphLevel;
  nodes: Array<Record<string, unknown>>;
  edges: Array<{ source: string; target: string }>;
}
