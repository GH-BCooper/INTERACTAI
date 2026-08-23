"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useSessions } from "@/lib/api/hooks";

const PAGE_SIZE = 20;

function SessionRowSkeleton() {
  return <div className="h-14 animate-pulse rounded-lg border bg-[var(--bg-card)]" />;
}

export default function SessionHistoryPage() {
  const [offset, setOffset] = useState(0);
  const { data, isPending } = useSessions({ limit: PAGE_SIZE, offset });

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-lg font-medium">Session history</h1>

      <div className="mt-6 flex flex-col gap-2">
        {isPending && Array.from({ length: 5 }).map((_, i) => <SessionRowSkeleton key={i} />)}

        {data && data.items.length === 0 && offset === 0 && (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              No sessions yet — start your first one from the practice library.
            </p>
            <a
              href="/app/scenarios"
              className="mt-3 inline-block text-sm text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              Go to the scenario library
            </a>
          </div>
        )}

        {data?.items.map((s) => (
          <a
            key={s.id}
            href={s.status === "closed" ? `/app/sessions/${s.id}` : `/app/practice/${s.id}`}
            className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-3 text-sm hover:bg-[var(--bg-raised)]"
          >
            <div>
              <p>{new Date(s.created_at).toLocaleString()}</p>
              {s.retry_of_session_id && (
                <p className="text-xs text-[var(--text-tertiary)]">Retry of one question</p>
              )}
            </div>
            <span className="text-xs uppercase text-[var(--text-tertiary)]">{s.status}</span>
          </a>
        ))}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between">
          <Button
            variant="secondary"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          >
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
