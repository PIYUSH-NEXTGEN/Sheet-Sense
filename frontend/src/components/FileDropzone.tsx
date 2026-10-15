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
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
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
        aria-label="Choose an .xlsx workbook to analyze"
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
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center ${
          dragging ? "border-blue-600 bg-blue-50" : "border-gray-300 bg-white"
        } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
      >
        <p className="text-lg font-medium">
          {disabled ? "Analyzing…" : "Drop an .xlsx file here, or click to choose one"}
        </p>
        <p id="dropzone-hint" className="mt-1 text-sm text-gray-500">
          Macro workbooks (.xlsm) are not supported. Files stay on your machine.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
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
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
