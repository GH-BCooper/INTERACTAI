"use client";

import { History, RotateCcw, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ScoreBadge } from "@/components/score/score-badge";
import { SessionStatusPill } from "@/components/sessions/session-status-pill";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { LocalDate } from "@/components/ui/local-date";
import { capitalize, DifficultyMeter, EmptyState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/segmented";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useSessions } from "@/lib/api/hooks";
import type { SessionListItemOut } from "@/lib/api/types";

const PAGE_SIZE = 20;
const FAMILIES = ["all", "technical", "behavioural", "negotiation", "viva"] as const;
type Family = (typeof FAMILIES)[number];

function SessionRowSkeleton() {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border bg-[var(--bg-card)] px-4 py-3" aria-hidden>
      <div className="flex flex-1 flex-col gap-2">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-3 w-1/3" />
      </div>
      <Skeleton className="h-4 w-16" />
    </div>
  );
}

function monthKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function SessionRow({ s }: { s: SessionListItemOut }) {
  const href = s.status === "closed" ? `/app/sessions/${s.id}` : `/app/practice/${s.id}`;
  return (
    <Link
      href={href}
      className="flex items-center justify-between gap-4 rounded-lg border bg-[var(--bg-card)] px-4 py-3 text-sm transition-colors duration-150 hover:bg-[var(--bg-raised)]"
    >
      <div className="min-w-0">
        <p className="flex items-center gap-2">
          <span className="truncate font-medium">{s.scenario_title}</span>
          {s.retry_of_session_id && (
            <span className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--text-tertiary)]">
              <RotateCcw size={12} aria-hidden /> Retry
            </span>
          )}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-tertiary)]">
          <LocalDate value={s.created_at} withTime />
          {s.scenario_family && <span>· {capitalize(s.scenario_family)}</span>}
          {s.duration_ms ? <span>· {Math.max(1, Math.round(s.duration_ms / 60_000))} min</span> : null}
          {s.difficulty && (
            <span className="hidden sm:inline">
              · <DifficultyMeter difficulty={s.difficulty} />
            </span>
          )}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 sm:flex-row sm:items-center sm:gap-3">
        <SessionStatusPill session={s} />
        {s.status === "closed" && <ScoreBadge score={s.overall_score} />}
      </div>
    </Link>
  );
}

export default function SessionHistoryPage() {
  const [offset, setOffset] = useState(0);
  const [family, setFamily] = useState<Family>("all");
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query.trim(), 250);
  const { data, isPending, isPlaceholderData } = useSessions({
    limit: PAGE_SIZE,
    offset,
    family: family === "all" ? undefined : family,
    q: debouncedQuery || undefined,
  });
  const filtering = family !== "all" || debouncedQuery !== "";

  // Grouped by month, newest first (the API already returns newest first).
  const groups = useMemo(() => {
    const out: { key: string; label: string; items: SessionListItemOut[] }[] = [];
    for (const s of data?.items ?? []) {
      const key = monthKey(s.created_at);
      let group = out.at(-1);
      if (!group || group.key !== key) {
        group = { key, label: s.created_at, items: [] };
        out.push(group);
      }
      group.items.push(s);
    }
    return out;
  }, [data]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader title="Session history" description="Every session you've started, newest first." />

      <div className="mt-6 flex flex-col gap-3">
        <div className="relative">
          <Search size={14} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <Input
            aria-label="Search sessions by scenario"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
            placeholder="Search by scenario…"
            className="pl-9"
          />
        </div>
        <Segmented
          label="Filter by scenario family"
          value={family}
          onChange={(f) => {
            setFamily(f);
            setOffset(0);
          }}
          options={FAMILIES.map((f) => ({ value: f, label: f === "all" ? "All families" : capitalize(f) }))}
        />
      </div>

      <div className={`mt-6 transition-opacity duration-150 ${isPlaceholderData ? "opacity-60" : ""}`}>
        {isPending && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <SessionRowSkeleton key={i} />
            ))}
          </div>
        )}

        {data && data.items.length === 0 && offset === 0 && (
          filtering ? (
            <EmptyState
              compact
              title="No sessions match"
              body="Try a different search or family."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setFamily("all");
                    setQuery("");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<History size={18} />}
              title="No sessions yet"
              body="Start your first one from the scenario library — it will show up here with its score."
              action={
                <ButtonLink href="/app/scenarios" variant="primary" size="sm">
                  Go to the scenario library
                </ButtonLink>
              }
            />
          )
        )}

        {groups.map((g) => (
          <section key={g.key} className="mb-4">
            <h2 className="sticky top-0 z-10 -mx-1 bg-[var(--bg-page)]/90 px-1 py-2 text-xs font-medium text-[var(--text-tertiary)] backdrop-blur">
              <LocalDate value={g.label} options={{ month: "long", year: "numeric" }} />
            </h2>
            <ul className="stagger flex flex-col gap-2">
              {g.items.map((s) => (
                <li key={s.id}>
                  <SessionRow s={s} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between">
          <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>
            Previous
          </Button>
          <span className="text-xs text-[var(--text-tertiary)]">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={offset + PAGE_SIZE >= data.total}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
