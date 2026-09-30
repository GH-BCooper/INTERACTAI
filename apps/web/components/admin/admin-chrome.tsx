"use client";

import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Label, Select } from "@/components/ui/field";
import { EmptyState, Pill } from "@/components/ui/primitives";

/** docs/ui-audit-2026-09.md §12 — the chrome every admin page shares: a title row marked
 * "Admin", a description, and one filter bar in the same place on every dashboard. */
export function AdminPageHeader({ title, description, filters }: { title: string; description: ReactNode; filters?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-medium">{title}</h1>
          <Pill>Admin</Pill>
        </div>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">{description}</p>
      </div>
      {filters && (
        <div role="group" aria-label="Filters" className="flex flex-wrap items-end gap-3 rounded-lg border bg-[var(--bg-card)] p-3">
          {filters}
        </div>
      )}
    </div>
  );
}

export const WINDOW_OPTIONS = [1, 7, 30, 90, 365] as const;

export function FilterSelect({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-36 flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </Select>
    </div>
  );
}

/** The shared date window: "last N days". */
export function WindowSelect({ value, onChange }: { value: number; onChange: (days: number) => void }) {
  return (
    <FilterSelect id="admin-window" label="Window" value={value} onChange={(v) => onChange(Number(v))}>
      {WINDOW_OPTIONS.map((n) => (
        <option key={n} value={n}>
          Last {n} day{n > 1 ? "s" : ""}
        </option>
      ))}
    </FilterSelect>
  );
}

export function AdminForbidden() {
  return (
    <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <EmptyState
        icon={<ShieldAlert size={18} />}
        title="Admin access required"
        body="This tool is restricted to admin accounts (docs/decisions/0019)."
      />
    </div>
  );
}
