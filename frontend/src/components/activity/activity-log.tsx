"use client";

import { useMemo, useState } from "react";

import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Tag } from "@/components/shared/tag";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuditLogs } from "@/hooks/use-organization";
import { useCan } from "@/lib/auth";
import { describeAction, formatDateTime, humanize } from "@/lib/format";
import {
  FREQUENCY_OPTIONS,
  OFFERING_KIND_OPTIONS,
  PLATFORM_OPTIONS,
  ROLE_OPTIONS,
  SOURCE_OPTIONS,
} from "@/lib/options";
import type { Tone } from "@/lib/tones";
import type { AuditLogEntry } from "@/types/api";

// Enum values stored in the audit trail, shown with their UI labels.
const LABELS = new Map<string, string>(
  [
    ...FREQUENCY_OPTIONS,
    ...OFFERING_KIND_OPTIONS,
    ...PLATFORM_OPTIONS,
    ...ROLE_OPTIONS,
    ...SOURCE_OPTIONS,
  ].map((o) => [o.value, o.label]),
);

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "empty";
  if (Array.isArray(value)) return value.length ? value.map(show).join(", ") : "none";
  if (typeof value === "string") return LABELS.get(value) ?? value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// --- Areas: what part of the product a change touched ------------------------------

type Area = "content" | "design" | "trends" | "knowledge" | "organization" | "team";

const AREAS: { value: Area; label: string; tone: Tone }[] = [
  { value: "content", label: "Content", tone: "blue" },
  { value: "design", label: "Design", tone: "violet" },
  { value: "trends", label: "Trends & topics", tone: "amber" },
  { value: "knowledge", label: "Knowledge", tone: "teal" },
  { value: "organization", label: "Organization", tone: "neutral" },
  { value: "team", label: "Team", tone: "pink" },
];
const AREA = new Map(AREAS.map((a) => [a.value, a]));

function areaOf(entry: AuditLogEntry): Area {
  const type = entry.entity_type;
  if (type === "post" || type === "content_strategy" || type.includes("approval")) return "content";
  if (type.startsWith("design")) return "design";
  if (type === "trend" || type === "topic") return "trends";
  if (type.startsWith("knowledge")) return "knowledge";
  if (type === "organization_member" || type.includes("invit")) return "team";
  return "organization";
}

// --- Days ------------------------------------------------------------------------

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function dayLabel(date: Date, now = new Date()): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const daysAgo = Math.round((today.getTime() - day.getTime()) / 86_400_000);
  if (daysAgo === 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  });
}

function groupByDay(entries: AuditLogEntry[]) {
  const groups: { key: string; label: string; entries: AuditLogEntry[] }[] = [];
  for (const entry of entries) {
    const date = new Date(entry.created_at);
    const key = dayKey(date);
    const last = groups.at(-1);
    if (last?.key === key) last.entries.push(entry);
    else groups.push({ key, label: dayLabel(date), entries: [entry] });
  }
  return groups;
}

// --- Page ------------------------------------------------------------------------

export function ActivityLog() {
  const canView = useCan()("organization.write");
  const logs = useAuditLogs(canView);
  const [area, setArea] = useState<"all" | Area>("all");

  const groups = useMemo(() => {
    const entries = (logs.data ?? []).filter((e) => area === "all" || areaOf(e) === area);
    return groupByDay(entries);
  }, [logs.data, area]);

  return (
    <>
      <PageHeader
        title="Activity log"
        description="Every change in this organization: who made it, when, and what changed."
        actions={
          canView && logs.data?.length ? (
            <SimpleSelect
              aria-label="Show changes to"
              value={area}
              onChange={(v) => setArea(v as "all" | Area)}
              options={[
                { value: "all", label: "Everything" },
                ...AREAS.map((a) => ({ value: a.value, label: a.label })),
              ]}
              className="w-48"
            />
          ) : null
        }
      />
      {!canView ? (
        <ReadOnlyNotice>Only admins can view the activity log.</ReadOnlyNotice>
      ) : logs.isPending ? (
        <div className="grid gap-3">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : !groups.length ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {area !== "all" ? "No changes in this area yet." : "No activity yet."}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6">
          {groups.map((group) => (
            <section key={group.key} aria-labelledby={`day-${group.key}`} className="grid gap-2">
              <h2
                id={`day-${group.key}`}
                className="sticky top-14 z-10 flex items-baseline gap-2 bg-background/95 py-1 backdrop-blur lg:top-0"
              >
                <span className="text-sm font-semibold">{group.label}</span>
                <span className="text-xs text-muted-foreground">
                  {group.entries.length} change{group.entries.length === 1 ? "" : "s"}
                </span>
              </h2>
              <Card>
                <CardContent className="p-0">
                  <ol className="divide-y">
                    {group.entries.map((entry) => (
                      <Entry key={entry.id} entry={entry} />
                    ))}
                  </ol>
                </CardContent>
              </Card>
            </section>
          ))}
          {logs.data?.length === 100 && (
            <p className="text-xs text-muted-foreground">Showing the latest 100 changes.</p>
          )}
        </div>
      )}
    </>
  );
}

function Entry({ entry }: { entry: AuditLogEntry }) {
  const changes = Object.keys({ ...entry.old_value, ...entry.new_value });
  // Creation/invite events have no "before": list their values instead of a diff.
  const isDiff = !!entry.old_value && !!entry.new_value;
  const area = AREA.get(areaOf(entry))!;
  const time = new Date(entry.created_at).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <li className="grid gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[4.5rem_minmax(0,1fr)]">
      <time
        dateTime={entry.created_at}
        title={formatDateTime(entry.created_at)}
        className="text-xs text-muted-foreground tabular-nums sm:pt-0.5"
      >
        {time}
      </time>
      <div className="grid min-w-0 gap-1.5">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span>
            <span className="font-medium">{entry.user_name ?? "System"}</span>{" "}
            <span className="text-muted-foreground">{describeAction(entry.action)}</span>
          </span>
          <Tag tone={area.tone}>{area.label}</Tag>
        </p>
        {changes.length > 0 && (
          <details className="group text-xs">
            <summary className="w-fit cursor-pointer text-muted-foreground hover:text-foreground">
              {changes.length === 1
                ? `Show the change to ${humanize(changes[0]!).toLowerCase()}`
                : `Show ${changes.length} changes`}
            </summary>
            <dl className="mt-2 grid gap-1 rounded-lg bg-muted/60 p-3">
              {changes.map((field) => (
                <div key={field} className="grid gap-x-3 sm:grid-cols-[10rem_1fr]">
                  <dt className="text-muted-foreground">{humanize(field)}</dt>
                  <dd className="min-w-0 break-words">
                    {isDiff ? (
                      <>
                        <span className="text-muted-foreground line-through">
                          {show(entry.old_value?.[field])}
                        </span>
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
          </details>
        )}
      </div>
    </li>
  );
}
