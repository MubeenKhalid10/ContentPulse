"use client";

import { CheckIcon, RotateCcwIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Tag } from "@/components/shared/tag";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score } from "@/components/trends/score";
import { Button } from "@/components/ui/button";
import { useTrendAction } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { marketLabel, sourceName } from "@/lib/trends";
import type { Trend } from "@/types/api";

/** Shortlisting a trend adds it to Topics, where its posts are planned. */
export function TrendActions({ trend, compact = false }: { trend: Trend; compact?: boolean }) {
  const action = useTrendAction();
  const router = useRouter();
  const onError = (e: unknown) => toast.error(errorMessage(e));

  if (trend.status === "rejected") {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled={action.isPending}
        onClick={() =>
          action.mutate({ id: trend.id, action: "restore" }, { onSuccess: () => toast.success("Trend restored"), onError })
        }
      >
        <RotateCcwIcon />
        Restore
      </Button>
    );
  }
  if (trend.status === "shortlisted") return null;
  return (
    <div className="flex gap-1.5">
      <Button
        size="sm"
        variant={compact ? "outline" : "default"}
        disabled={action.isPending}
        aria-label={`Shortlist ${trend.topic}`}
        onClick={() =>
          action.mutate(
            { id: trend.id, action: "shortlist" },
            {
              onSuccess: (t) =>
                toast.success(`Shortlisted “${trend.topic}”`, {
                  description: "It's in Topics now, ready for a post plan.",
                  action: t.topic_id
                    ? { label: "Plan a post", onClick: () => router.push(`/topics/${t.topic_id}`) }
                    : undefined,
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
          aria-label={`Reject ${trend.topic}`}
          onClick={() =>
            action.mutate({ id: trend.id, action: "reject" }, { onSuccess: () => toast.success(`Rejected “${trend.topic}”`), onError })
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
}: {
  trend: Trend;
  canReview: boolean;
  marketNames: Map<string, string>;
}) {
  return (
    <li className="group relative flex items-start gap-4 rounded-xl p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40 bg-card">
      <Score score={trend.opportunity_score} />
      <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/trends/${trend.id}`}
            className="max-w-full truncate text-base font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {trend.topic}
          </Link>
          <RelevanceBadge level={trend.relevance_level} overridden={trend.relevance_overridden} />
          {trend.status === "shortlisted" && <Tag tone="green" dot>Shortlisted</Tag>}
        </div>
        {(trend.description ?? trend.title) && trend.title !== trend.topic && (
          <p className="line-clamp-1 text-sm text-muted-foreground">{trend.description ?? trend.title}</p>
        )}
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{trend.sources.map(sourceName).join(" · ")}</span>
          <span aria-hidden>•</span>
          <span>{trend.locations.map((c) => marketLabel(c, marketNames)).join(", ")}</span>
          <span aria-hidden>•</span>
          <span>
            {trend.mention_count} mention{trend.mention_count === 1 ? "" : "s"}
          </span>
          <span aria-hidden>•</span>
          <time dateTime={trend.last_seen_at} title={formatDateTime(trend.last_seen_at)}>
            seen {timeAgo(trend.last_seen_at)}
          </time>
        </p>
      </div>
      {canReview && (
        <div className="relative z-10 flex items-center self-center">
          <TrendActions trend={trend} compact />
        </div>
      )}
    </li>
  );
}
