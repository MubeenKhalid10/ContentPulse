import { LoaderCircleIcon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Says in words that something is still loading, so a half-filled page isn't taken for the result. */
export function LoadingNotice({ label, className }: { label: string; className?: string }) {
  return (
    <p className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)} role="status">
      <LoaderCircleIcon aria-hidden className="size-4 animate-spin text-primary" />
      {label}
    </p>
  );
}

/** A list or section that hasn't loaded: the notice above placeholder rows. */
export function ListLoading({
  label,
  rows = 4,
  rowClassName = "h-20",
}: {
  label: string;
  rows?: number;
  rowClassName?: string;
}) {
  return (
    <div className="grid gap-3" aria-busy="true">
      <LoadingNotice label={label} />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn("w-full rounded-xl", rowClassName)} />
      ))}
    </div>
  );
}

/** A whole page that hasn't loaded. */
export function PageLoading({ label }: { label: string }) {
  return (
    <div className="grid gap-6" aria-busy="true">
      <LoadingNotice label={label} />
      <Skeleton className="h-10 w-2/3" />
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-32 w-full rounded-xl" />
    </div>
  );
}

/**
 * True while a list still shows the items of the previous filter or tab, which aren't the answer
 * to what was asked. False during "Show more": the items on screen stay correct, so they stay.
 */
export function isSwitchingList(
  query: { isPlaceholderData: boolean; data?: { items: unknown[]; total: number } },
  limit: number,
): boolean {
  if (!query.isPlaceholderData || !query.data) return false;
  const shown = query.data.items.length;
  return !(limit > shown && query.data.total > shown);
}
