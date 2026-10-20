import { cn } from "@/lib/utils";

/** Search field: full width on phones, takes the free space on one line. */
export const FILTER_SEARCH = "w-full sm:w-auto sm:min-w-36 sm:flex-1";
/** Filter selects: two per row on phones; on one line they fit their label. */
export const FILTER_SELECT =
  "w-[calc(50%-0.25rem)] bg-card sm:w-auto sm:shrink-0";

/** The tabs, search and filter row above every list: one line wherever it
 * fits (the search field gives up its width first), wrapping only when not. */
export function FilterBar({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-2",
        className,
      )}
    >
      {children}
    </div>
  );
}
