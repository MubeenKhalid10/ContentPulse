"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { DashboardOverview, Platform } from "@/types/api";

const PLATFORM_COLOR: Record<Platform, string> = {
  linkedin: "#0a66c2",
  x: "#52525b",
  instagram: "#e1306c",
  facebook: "#4f46e5",
  blog: "#0d9488",
};

export function PlatformBreakdown({ data }: { data?: DashboardOverview }) {
  const entries = (
    Object.entries(data?.platform_breakdown ?? {}) as [Platform, number][]
  )
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  // Donut from stroke-dasharray arcs on a circle of circumference 100: each
  // arc starts where the previous ones end.
  const arcs = entries.map(([platform, n], i) => ({
    platform,
    share: (n / total) * 100,
    start: entries
      .slice(0, i)
      .reduce((sum, [, m]) => sum + (m / total) * 100, 0),
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Platform breakdown</CardTitle>
        <CardDescription>
          Posts by platform, all time. Not affected by the period.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-36 w-full" />
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">No posts yet.</p>
        ) : (
          <div className="flex items-center gap-5">
            <div
              className="relative size-32 shrink-0"
              role="img"
              aria-label={`${total} posts: ${entries.map(([p, n]) => `${PLATFORM_LABEL[p]} ${n}`).join(", ")}`}
            >
              <svg viewBox="0 0 42 42" className="size-full -rotate-90">
                <circle
                  cx="21"
                  cy="21"
                  r="15.915"
                  fill="none"
                  stroke="var(--muted)"
                  strokeWidth="6"
                />
                {arcs.map(({ platform, share, start }) => (
                  <circle
                    key={platform}
                    cx="21"
                    cy="21"
                    r="15.915"
                    fill="none"
                    stroke={PLATFORM_COLOR[platform]}
                    strokeWidth="6"
                    strokeDasharray={`${share} ${100 - share}`}
                    strokeDashoffset={-start}
                  />
                ))}
              </svg>
              <span className="absolute inset-0 grid place-content-center text-center">
                <span className="text-2xl leading-none font-semibold tabular-nums">
                  {total}
                </span>
                <span className="text-xs text-muted-foreground">posts</span>
              </span>
            </div>
            <ul className="grid flex-1 gap-1.5 text-sm">
              {entries.map(([platform, n]) => (
                <li key={platform} className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: PLATFORM_COLOR[platform] }}
                  />
                  <span className="flex-1">{PLATFORM_LABEL[platform]}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {n} ({Math.round((n / total) * 100)}%)
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
