"use client";

import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuditLogs } from "@/hooks/use-organization";
import { useCan } from "@/lib/auth";
import { describeAction, formatDateTime, humanize, timeAgo } from "@/lib/format";
import {
  FREQUENCY_OPTIONS,
  OFFERING_KIND_OPTIONS,
  PLATFORM_OPTIONS,
  ROLE_OPTIONS,
  SOURCE_OPTIONS,
} from "@/lib/options";
import type { AuditLogEntry } from "@/types/api";

// Enum values stored in the audit trail, shown with their UI labels.
const LABELS = new Map<string, string>(
  [...FREQUENCY_OPTIONS, ...OFFERING_KIND_OPTIONS, ...PLATFORM_OPTIONS, ...ROLE_OPTIONS, ...SOURCE_OPTIONS].map(
    (o) => [o.value, o.label],
  ),
);

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "empty";
  if (Array.isArray(value)) return value.length ? value.map(show).join(", ") : "none";
  if (typeof value === "string") return LABELS.get(value) ?? value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ActivityLog() {
  const canView = useCan()("organization.write");
  const logs = useAuditLogs(canView);

  return (
    <>
      <PageHeader
        title="Activity log"
        description="Every change in this organization: who made it, when, and what changed."
      />
      {!canView ? (
        <ReadOnlyNotice>Only admins can view the activity log.</ReadOnlyNotice>
      ) : logs.isPending ? (
        <div className="grid gap-3">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent>
            <ol className="relative grid gap-6 border-l pl-6">
              {logs.data?.map((entry) => <Entry key={entry.id} entry={entry} />)}
            </ol>
            {logs.data?.length === 100 && (
              <p className="mt-6 text-xs text-muted-foreground">Showing the latest 100 changes.</p>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}

function Entry({ entry }: { entry: AuditLogEntry }) {
  const changes = Object.keys({ ...entry.old_value, ...entry.new_value });
  // Creation/invite events have no "before": list their values instead of a diff.
  const isDiff = !!entry.old_value && !!entry.new_value;

  return (
    <li className="relative">
      <span aria-hidden className="absolute top-1.5 -left-[29px] size-2.5 rounded-full border-2 border-background bg-muted-foreground/50" />
      <p className="text-sm">
        <span className="font-medium">{entry.user_name ?? "System"}</span>{" "}
        <span className="text-muted-foreground">{describeAction(entry.action)}</span>
      </p>
      <time dateTime={entry.created_at} title={formatDateTime(entry.created_at)} className="text-xs text-muted-foreground">
        {timeAgo(entry.created_at)}
      </time>
      {changes.length > 0 && (
        <dl className="mt-2 grid gap-1 rounded-lg bg-muted/60 p-3 text-xs">
          {changes.map((field) => (
            <div key={field} className="grid gap-x-3 sm:grid-cols-[10rem_1fr]">
              <dt className="text-muted-foreground">{humanize(field)}</dt>
              <dd className="min-w-0 break-words">
                {isDiff ? (
                  <>
                    <span className="text-muted-foreground line-through">{show(entry.old_value?.[field])}</span>
                    {" → "}
                    <span>{show(entry.new_value?.[field])}</span>
                  </>
                ) : (
                  show((entry.new_value ?? entry.old_value)?.[field])
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}
