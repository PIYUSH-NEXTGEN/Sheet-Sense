import type { ReactNode } from "react";
import type { Severity } from "../api/types";

/**
 * Shared design primitives. Type scale for the whole site: text-2xl for
 * main headings and names, text-base for subheadings, text-sm for normal
 * text. Two typefaces only: sans for prose, mono for code, cells and
 * technical labels.
 */

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-night-600 bg-night-800 ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate font-mono text-2xl font-bold tracking-tight text-night-100">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm text-night-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-mono text-sm font-semibold uppercase tracking-widest text-night-400">
      {children}
    </h2>
  );
}

const SEVERITY_STYLES: Record<Severity, string> = {
  high: "border-danger/40 bg-danger/10 text-danger",
  medium: "border-warn/40 bg-warn/10 text-warn",
  low: "border-night-600 bg-night-700 text-night-300",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-sm font-semibold ${SEVERITY_STYLES[severity]}`}
    >
      {severity}
    </span>
  );
}

export function DetectorTag({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-night-600 bg-night-950 px-1.5 py-0.5 font-mono text-sm text-night-300">
      {name}
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-night-600 bg-night-800 px-4 py-3">
      <dt className="font-mono text-sm font-medium uppercase tracking-widest text-night-400">
        {label}
      </dt>
      <dd className="tnum mt-1 font-mono text-2xl font-bold tracking-tight text-night-100">
        {value}
      </dd>
    </div>
  );
}

export function PrimaryButton({
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex min-h-[40px] items-center justify-center rounded-md bg-accent px-3.5 py-2 font-mono text-sm font-bold text-accent-ink hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50 ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex min-h-[40px] items-center justify-center rounded-md border border-night-600 bg-transparent px-3.5 py-2 font-mono text-sm font-medium text-night-100 hover:border-night-400 hover:bg-night-700 disabled:cursor-not-allowed disabled:opacity-50 ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function CodeBlock({ children }: { children: ReactNode }) {
  return (
    <code className="block overflow-x-auto rounded-md border border-night-600 bg-night-950 px-3 py-2 font-mono text-sm leading-relaxed text-night-100">
      {children}
    </code>
  );
}
