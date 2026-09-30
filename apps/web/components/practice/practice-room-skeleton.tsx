import { Skeleton } from "@/components/ui/primitives";

/** The practice room's layout with nothing in it yet — same positions as the live room, so the
 * page doesn't jump when the session becomes live (docs/ui-audit-2026-09.md §7). */
export function PracticeRoomSkeleton({ label = "Loading your session…" }: { label?: string }) {
  return (
    <div className="relative flex h-dvh flex-col items-center justify-center gap-8 bg-[var(--bg-page)] px-6" aria-busy="true">
      <div className="absolute left-1/2 top-6 -translate-x-1/2">
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-48 w-48 items-center justify-center sm:h-56 sm:w-56">
          <div className="h-40 w-40 animate-pulse rounded-full border-2 border-[var(--border)] sm:h-48 sm:w-48" />
        </div>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3 w-16" />
      </div>
      <Skeleton className="h-8 w-40 rounded-full" />
      <div className="absolute bottom-8 flex items-center gap-4">
        <Skeleton className="h-1.5 w-28 rounded-full" />
        <Skeleton className="h-10 w-10 rounded-full" />
        <Skeleton className="h-10 w-10 rounded-full" />
        <Skeleton className="h-10 w-10 rounded-full" />
      </div>
      <p className="sr-only" role="status">
        {label}
      </p>
    </div>
  );
}
