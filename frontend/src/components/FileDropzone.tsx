import { useRef, useState } from "react";
import { MAX_FILE_MB } from "../api/client";

/** Drag-and-drop .xlsx picker. Validates extension and size client-side. */
export function FileDropzone({
  onFile,
  disabled,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(file: File | undefined) {
    setError(null);
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (lower.endsWith(".xls") && !lower.endsWith(".xlsx")) {
      // Legacy format: the backend converts it locally when LibreOffice
      // is installed, otherwise it replies with a clear error.
      onFile(file);
      return;
    }
    if (!lower.endsWith(".xlsx")) {
      setError(
        `Only .xlsx workbooks are accepted (got ${file.name}). Macro workbooks (.xlsm) are unsupported.`,
      );
      return;
    }
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      setError(`File is too large (limit ${MAX_FILE_MB} MB).`);
      return;
    }
    onFile(file);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Choose an .xlsx or .xls workbook to analyze"
        aria-disabled={disabled}
        aria-describedby="dropzone-hint"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={onKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) accept(e.dataTransfer.files?.[0]);
        }}
        className={`rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent/10"
            : "border-night-600 bg-night-950 hover:border-accent/60"
        } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
      >
        <svg
          aria-hidden="true"
          className="mx-auto h-9 w-9 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 16V4m0 0 4 4m-4-4-4 4" />
          <path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
        </svg>
        <p className="mt-3 text-base font-semibold text-night-100">
          {disabled ? "Analyzing…" : "Drop an .xlsx file here, or browse"}
        </p>
        <p id="dropzone-hint" className="mt-1 font-mono text-sm text-night-400">
          .xlsx preferred. Old .xls files are converted on your machine
          (needs LibreOffice); macro workbooks (.xlsm) are not supported.
          Files never leave your machine.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          tabIndex={-1}
          aria-hidden="true"
          disabled={disabled}
          onChange={(e) => {
            accept(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
