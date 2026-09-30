import { Skeleton } from "@/components/ui/primitives";

/** Route-level fallback inside the shell: the sidebar and top bar stay put, only the content
 * area shows a neutral page skeleton while the next route's code loads. */
export default function ShellLoading() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6" aria-busy="true">
      <Skeleton className="h-7 w-56" />
      <Skeleton className="mt-3 h-4 w-80 max-w-full" />
      <Skeleton className="mt-8 h-40 w-full" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
