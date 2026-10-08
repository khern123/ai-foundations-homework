import type { ReactNode } from "react";

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Labelled form field with an inline error message. */
export default function Field({
  label,
  name,
  error,
  children,
}: {
  label: string;
  name: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className={`field ${error ? "has-error" : ""}`}>
      <label htmlFor={name}>{label}</label>
      {children}
      {error && (
        <span className="field-error" id={`${name}-error`}>
          {error}
        </span>
      )}
    </div>
  );
}
