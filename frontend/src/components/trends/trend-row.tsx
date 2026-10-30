"use client";

import { CheckIcon, RotateCcwIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { DeleteButton } from "@/components/shared/delete-button";
import { Tag } from "@/components/shared/tag";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score } from "@/components/trends/score";
import { Button, buttonVariants } from "@/components/ui/button";
import { useDeleteTrend, useTrendAction } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { marketLabel, sourceName } from "@/lib/trends";
import type { Trend } from "@/types/api";

/** Shortlisting a trend opens its post plans (here on the trend, and under Shortlist & plans). */
export function TrendActions({
  trend,
  compact = false,
}: {
  trend: Trend;
  compact?: boolean;
}) {
  const action = useTrendAction();
  const router = useRouter();
  const remove = useDeleteTrend();
  const pathname = usePathname();
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const deleteButton = (
    <DeleteButton
      title={`Delete “${trend.topic}”?`}
      description="This permanently deletes the trend, its evidence and its topic with any post plans. Posts already written for it are kept. This can't be undone."
      pending={remove.isPending}
      disabled={action.isPending}
      onConfirm={() =>
        remove.mutate(trend.id, {
          onSuccess: () => {
            toast.success(`Deleted “${trend.topic}”`);
            if (pathname.startsWith("/trends/")) router.push("/trends");
          },
          onError,
        })
      }
    />
  );

  if (trend.status === "archived") return deleteButton;
  if (trend.status === "rejected") {
    return (
      <div className="flex gap-1.5">
        <Button
          variant="outline"
          size="sm"
          disabled={action.isPending}
          pending={action.isPending}
          title="Move this trend back to To review"
          onClick={() =>
            action.mutate(
              { id: trend.id, action: "restore" },
              { onSuccess: () => toast.success("Trend restored"), onError },
            )
          }
        >
          <RotateCcwIcon />
          Restore
        </Button>
        {deleteButton}
      </div>
    );
  }
  if (trend.status === "shortlisted") {
    if (!compact) return deleteButton;
    return (
      <div className="flex gap-1.5">
        <Link href={`/trends/${trend.id}?plan=1`} className={buttonVariants({ size: "sm" })}>
          Plan post
        </Link>
        {deleteButton}
      </div>
    );
  }
  return (
    <div className="flex gap-1.5">
      <Button
        size="sm"
        variant="success"
        disabled={action.isPending}
        pending={action.isPending && action.variables?.action === "shortlist"}
        aria-label={`Shortlist ${trend.topic}`}
        onClick={() =>
          action.mutate(
            { id: trend.id, action: "shortlist" },
            {
              onSuccess: () =>
                toast.success(`Shortlisted “${trend.topic}”`, {
                  description: "It's in Shortlist & plans now, ready for a post plan.",
                  action: {
                    label: "Plan post",
                    onClick: () => router.push(`/trends/${trend.id}?plan=1`),
                  },
                }),
              onError,
            },
          )
        }
      >
        <CheckIcon />
        Shortlist
      </Button>
      {!compact && (
        <Button
          size="sm"
          variant="ghost"
          disabled={action.isPending}
          pending={action.isPending && action.variables?.action === "reject"}
          aria-label={`Reject ${trend.topic}`}
          onClick={() =>
            action.mutate(
              { id: trend.id, action: "reject" },
              {
                onSuccess: () => toast.success(`Rejected “${trend.topic}”`),
                onError,
              },
            )
          }
        >
          <XIcon />
          Reject
        </Button>
      )}
    </div>
  );
}

export function TrendRow({
  trend,
  canReview,
  marketNames,
  hideShortlistedTag = false,
}: {
  trend: Trend;
  canReview: boolean;
  marketNames: Map<string, string>;
  /** On the Shortlisted tab every row is shortlisted, so the tag says nothing. */
  hideShortlistedTag?: boolean;
}) {
  return (
    <li className="group relative flex flex-wrap items-start gap-4 rounded-xl p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40 bg-card">
      <div className="grid justify-items-center gap-1">
        <Score score={trend.opportunity_score} />
        <span className="text-xs text-muted-foreground">
          {trend.opportunity_score == null ? "Not scored" : "Score"}
        </span>
      </div>
      <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/trends/${trend.id}`}
            className="line-clamp-2 max-w-full text-base font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {trend.topic}
          </Link>
          <RelevanceBadge
            level={trend.relevance_level}
            overridden={trend.relevance_overridden}
          />
          {trend.status === "shortlisted" && !hideShortlistedTag && (
            <Tag tone="green" dot>
              Shortlisted
            </Tag>
          )}
          {trend.status === "rejected" && (
            <Tag tone="neutral">Rejected · restore it to review again</Tag>
          )}
        </div>
        {(trend.description ?? trend.title) && trend.title !== trend.topic && (
          <p className="line-clamp-1 text-sm text-muted-foreground">
            {trend.description ?? trend.title}
          </p>
        )}
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{trend.sources.map(sourceName).join(" · ")}</span>
          <span aria-hidden>•</span>
          <span>
            {trend.locations
              .slice(0, 3)
              .map((c) => marketLabel(c, marketNames))
              .join(", ")}
            {trend.locations.length > 3 && ` +${trend.locations.length - 3} more`}
          </span>
          <span aria-hidden>•</span>
          <span>
            {trend.mention_count} mention{trend.mention_count === 1 ? "" : "s"}
          </span>
          <span aria-hidden>•</span>
          <time
            dateTime={trend.last_seen_at}
            title={formatDateTime(trend.last_seen_at)}
          >
            Last seen {timeAgo(trend.last_seen_at)}
          </time>
        </p>
      </div>
      <div className="relative z-10 flex basis-full flex-wrap items-center gap-1.5 sm:basis-auto sm:self-center">
        <Link
          href={`/trends/${trend.id}`}
          aria-label={`View trend ${trend.topic}`}
          className={buttonVariants({ variant: "view", size: "sm" })}
        >
          View trend
        </Link>
        {canReview && <TrendActions trend={trend} compact />}
      </div>
    </li>
  );
}
