import { ExternalLinkIcon } from "lucide-react";

import { formatDateTime, timeAgo } from "@/lib/format";
import { marketLabel } from "@/lib/trends";
import type { TrendMention } from "@/types/api";

export function groupBySource(
  mentions: TrendMention[],
): [string, TrendMention[]][] {
  const groups = new Map<string, TrendMention[]>();
  for (const m of mentions)
    groups.set(m.source, [...(groups.get(m.source) ?? []), m]);
  return [...groups.entries()];
}

export function MentionItem({
  mention: m,
  marketNames,
}: {
  mention: TrendMention;
  marketNames: Map<string, string>;
}) {
  const when = m.published_at ?? m.detected_at;
  return (
    <li className="grid gap-0.5 rounded-lg border p-3">
      {m.source_url ? (
        <a
          href={m.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-start gap-1 text-sm font-medium underline-offset-4 hover:underline"
        >
          {m.title}
          <ExternalLinkIcon className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
        </a>
      ) : (
        <p className="text-sm font-medium">{m.title}</p>
      )}
      {m.description && (
        <p className="line-clamp-2 text-xs text-muted-foreground">
          {m.description}
        </p>
      )}
      <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
        {m.author && <span>{m.author}</span>}
        {m.engagement_label && (
          <span className="font-medium text-foreground">
            {m.engagement_label}
          </span>
        )}
        {m.location && m.location !== "GLOBAL" && (
          <span>{marketLabel(m.location, marketNames)}</span>
        )}
        <time dateTime={when} title={formatDateTime(when)}>
          {timeAgo(when)}
        </time>
      </p>
    </li>
  );
}
