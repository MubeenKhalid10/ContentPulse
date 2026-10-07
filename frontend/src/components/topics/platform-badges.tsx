import { PlatformTag } from "@/components/shared/tag";
import { cn } from "@/lib/utils";
import type { Platform } from "@/types/api";

export function PlatformBadges({ platforms, className }: { platforms: Platform[]; className?: string }) {
  if (!platforms.length) return null;
  return (
    <ul className={cn("flex flex-wrap gap-1", className)} aria-label="Recommended platforms">
      {platforms.map((p) => (
        <li key={p}>
          <PlatformTag platform={p} />
        </li>
      ))}
    </ul>
  );
}
