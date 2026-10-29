"use client";

import { ArrowRightIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";

import { PlatformTag, Tag } from "@/components/shared/tag";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { withFrom } from "@/lib/back";
import { useCan } from "@/lib/auth";
import { postStatusLabel } from "@/lib/content";
import { timeAgo } from "@/lib/format";
import { POST_STATUS_TONE } from "@/lib/tones";
import { cn } from "@/lib/utils";
import { nextAction } from "@/lib/workflow";
import type { DashboardOverview, DashboardSummary } from "@/types/api";

export function RecentContent({ data }: { data?: DashboardOverview }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle>Recent content</CardTitle>
          <Link
            href="/content"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-40 w-full" />
        ) : data.recent_posts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Posts you write appear here. Start from a shortlisted topic.
          </p>
        ) : (
          <ul className="divide-y" aria-label="Recent content">
            {data.recent_posts.map((p) => (
              <li key={p.id}>
                <Link
                  href={withFrom(`/posts/${p.id}`, "/dashboard")}
                  className="-mx-2 grid gap-1.5 rounded-md px-2 py-2.5 hover:bg-muted/60"
                >
                  <span className="truncate text-sm font-medium">
                    {p.title?.trim() || "Untitled post"}
                  </span>
                  <span className="flex flex-wrap items-center gap-2">
                    <PlatformTag platform={p.platform} />
                    <Tag tone={POST_STATUS_TONE[p.status]} dot>
                      {postStatusLabel(p)}
                    </Tag>
                    <time
                      dateTime={p.updated_at}
                      className="ml-auto text-xs text-muted-foreground"
                    >
                      {timeAgo(p.updated_at)}
                    </time>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// --- Side column -----------------------------------------------------------------------

export function NextStepCallout({ summary }: { summary: DashboardSummary }) {
  const can = useCan();
  const next = nextAction(summary, can);
  return (
    <section
      aria-labelledby="next-step-title"
      className="dark grid gap-3 rounded-xl bg-background p-5 text-foreground"
    >
      <SparklesIcon className="size-5 text-flash" aria-hidden />
      <div className="grid gap-1">
        <h2 id="next-step-title" className="text-base font-semibold">
          {next.title}
        </h2>
        <p className="text-sm text-muted-foreground">{next.detail}</p>
      </div>
      <Link
        href={next.href}
        className={cn(
          buttonVariants({ variant: "secondary" }),
          "justify-self-start",
        )}
      >
        {next.cta} <ArrowRightIcon />
      </Link>
    </section>
  );
}
