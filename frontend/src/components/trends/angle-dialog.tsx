"use client";

import { ExternalLinkIcon } from "lucide-react";

import { PlatformTag } from "@/components/shared/tag";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { stripCitations, timeAgo } from "@/lib/format";
import { sourceName } from "@/lib/trends";
import type {
  ContentAngle,
  Platform,
  TrendDetail,
  TrendMention,
} from "@/types/api";

const HEADLINES = 3;
const STOP = new Set([
  "this",
  "that",
  "with",
  "from",
  "your",
  "their",
  "about",
  "into",
  "what",
  "when",
  "will",
  "have",
  "more",
  "than",
  "they",
  "them",
  "these",
  "those",
  "post",
  "posts",
]);

function words(text: string): Set<string> {
  return new Set(
    (text.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) ?? []).filter(
      (w) => !STOP.has(w),
    ),
  );
}

/** The trend's own headlines that share words with the idea, best match
 * first. When none do, the most engaged ones (the stored order). */
function headlinesFor(
  angle: ContentAngle,
  mentions: TrendMention[],
): TrendMention[] {
  const target = words(`${angle.title} ${angle.angle}`);
  const seen = new Set<string>();
  const ranked = mentions
    .filter((m) => {
      const key = m.title?.trim().toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((m, i) => {
      let overlap = 0;
      for (const w of words(`${m.title} ${m.description ?? ""}`))
        if (target.has(w)) overlap += 1;
      return { m, i, overlap };
    })
    .sort((a, b) => b.overlap - a.overlap || a.i - b.i);
  const matching = ranked.filter((r) => r.overlap > 0);
  return (matching.length ? matching : ranked)
    .slice(0, HEADLINES)
    .map(({ m }) => m);
}

const safeUrl = (url: string | null | undefined) =>
  url && /^https?:\/\//i.test(url) ? url : null;

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-2">
      <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

/**
 * Details of one post idea. Only stored facts: the idea as saved, the trend's
 * real headlines (title, source, original link, the source's own snippet) and
 * the passages from the organization's website it cites. Nothing is
 * generated or summarized here.
 */
export function AngleDialog({
  angle,
  trend,
  onClose,
  onPlan,
}: {
  angle: ContentAngle | null;
  trend: TrendDetail;
  onClose: () => void;
  onPlan?: (angle: ContentAngle) => void;
}) {
  const headlines = angle ? headlinesFor(angle, trend.mentions) : [];
  const passages = angle
    ? (trend.alignment.passages ?? []).filter((p) =>
        angle.evidence.includes(p.ref),
      )
    : [];

  return (
    <Dialog open={!!angle} onOpenChange={(open) => !open && onClose()}>
      {angle && (
        <DialogContent
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          overlayClassName="bg-black/30 supports-backdrop-filter:backdrop-blur-sm"
        >
          <DialogHeader>
            <DialogTitle className="pr-6">{angle.title}</DialogTitle>
            <DialogDescription>{stripCitations(angle.angle)}</DialogDescription>
            {angle.platforms.length > 0 && (
              <p className="flex flex-wrap gap-1.5">
                {angle.platforms.map((p) => (
                  <PlatformTag key={p} platform={p as Platform} />
                ))}
              </p>
            )}
          </DialogHeader>

          <Section title="From the trend">
            <p className="text-sm">
              <span className="font-medium">{trend.topic}</span>
              <span className="text-muted-foreground">
                {" "}
                · {trend.mention_count} mention
                {trend.mention_count === 1 ? "" : "s"} · seen{" "}
                {timeAgo(trend.last_seen_at)}
              </span>
            </p>
            {headlines.length > 0 ? (
              <ul className="grid gap-2.5">
                {headlines.map((m) => {
                  const url = safeUrl(m.source_url);
                  return (
                    <li key={m.id} className="grid gap-0.5">
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium hover:underline"
                        >
                          {m.title}
                          <ExternalLinkIcon
                            aria-hidden
                            className="ml-1 inline size-3 text-muted-foreground"
                          />
                        </a>
                      ) : (
                        <span className="font-medium">{m.title}</span>
                      )}
                      {m.description && (
                        <p className="line-clamp-2 text-muted-foreground">
                          {m.description}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {sourceName(m.source)}
                        {m.engagement_label && ` · ${m.engagement_label}`}
                      </p>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-muted-foreground">
                No headlines were stored for this trend.
              </p>
            )}
          </Section>

          {passages.length > 0 && (
            <Section title="From your website">
              <ul className="grid gap-2.5">
                {passages.map((p) => {
                  const url = safeUrl(p.url);
                  const name = p.heading || p.title || "Your content";
                  return (
                    <li key={p.ref} className="grid gap-0.5">
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium hover:underline"
                        >
                          {name}
                          <ExternalLinkIcon
                            aria-hidden
                            className="ml-1 inline size-3 text-muted-foreground"
                          />
                        </a>
                      ) : (
                        <span className="font-medium">{name}</span>
                      )}
                      <p className="line-clamp-3 text-muted-foreground">
                        {p.excerpt}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}

          {onPlan && (
            <DialogFooter>
              <Button onClick={() => onPlan(angle)}>
                Plan a post from this idea
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      )}
    </Dialog>
  );
}
