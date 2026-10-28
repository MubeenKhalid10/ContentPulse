"use client";

import Link from "next/link";

import { sourceStatus } from "@/components/trends/sources-manager";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTrendSources } from "@/hooks/use-trends";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function SourceHealth() {
  const sources = useTrendSources();
  const enabled = (sources.data ?? []).filter(
    (s) => s.enabled && s.pricing !== "unavailable",
  );
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="grid gap-1">
            <CardTitle>Source health</CardTitle>
            <CardDescription>
              Current status and last successful sync. Not affected by the period.
            </CardDescription>
          </div>
          <Link
            href="/trends/sources"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {!sources.data ? (
          <Skeleton className="h-32 w-full" />
        ) : enabled.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No sources are on yet.
          </p>
        ) : (
          <ul className="grid gap-2.5" aria-label="Source health">
            {enabled.slice(0, 7).map((s) => {
              const status = sourceStatus(s);
              return (
                <li
                  key={s.key}
                  className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">{s.name}</span>
                  <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs">
                    <span
                      className={cn("size-1.5 rounded-full", status.tone)}
                      aria-hidden
                    />
                    {status.label}
                  </span>
                  <span className="shrink-0 whitespace-nowrap text-right text-xs text-muted-foreground">
                    {s.last_success_at ? (
                      timeAgo(s.last_success_at)
                    ) : (
                      <span title="This source hasn't synced successfully yet">
                        Never synced
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
            {enabled.length > 7 && (
              <li className="text-xs text-muted-foreground">
                +{enabled.length - 7} more in{" "}
                <Link href="/trends/sources" className="underline underline-offset-4">
                  Discovery Sources
                </Link>
              </li>
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// --- Setup checklist (admins, until the essentials are done) -------------------------
