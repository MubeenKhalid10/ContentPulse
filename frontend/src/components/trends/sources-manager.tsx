"use client";

import { ArrowLeftIcon, ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useToggleSource, useTrendSources } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SourcePricing, TrendSourceInfo } from "@/types/api";

// ids must not contain spaces: aria-labelledby splits on whitespace.
const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-");

const PRICING: Record<SourcePricing, string> = {
  free: "Free",
  free_tier: "Free tier",
  paid: "Paid API",
  unavailable: "No public API",
};

function status(source: TrendSourceInfo): { label: string; tone: string } {
  if (source.pricing === "unavailable") return { label: "Unavailable", tone: "bg-muted-foreground/40" };
  if (!source.configured) return { label: "Needs setup", tone: "bg-warning" };
  if (!source.enabled) return { label: "Off", tone: "bg-muted-foreground/40" };
  switch (source.health) {
    case "healthy":
      return { label: "Working", tone: "bg-success" };
    case "rate_limited":
      return { label: "Rate limited", tone: "bg-warning" };
    case "degraded":
      return { label: "Having trouble", tone: "bg-warning" };
    case "down":
      return { label: "Failing", tone: "bg-destructive" };
    default:
      return { label: "Not run yet", tone: "bg-primary/60" };
  }
}

export function SourcesManager() {
  const sources = useTrendSources();
  const toggle = useToggleSource();
  const canManage = useCan()("trends.manage");

  const groups = sources.data
    ? [
        { title: "Ready to use", items: sources.data.filter((s) => s.configured) },
        {
          title: "Needs setup",
          hint: "These need API keys or extra settings. Add keys to the server's .env file and restart the API; ContentPulse picks them up automatically.",
          items: sources.data.filter((s) => !s.configured && s.pricing !== "unavailable"),
        },
        { title: "Not available", items: sources.data.filter((s) => s.pricing === "unavailable") },
      ].filter((g) => g.items.length)
    : [];

  return (
    <>
      <Link href="/trends" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-4" />
        Trends
      </Link>
      <PageHeader
        title="Trend sources"
        description="Where ContentPulse looks for trends. Sources that aren't set up are skipped; the others still work."
      />
      {!sources.data ? (
        <div className="grid gap-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-8">
          {groups.map((group) => (
            <section key={group.title} aria-labelledby={`group-${slug(group.title)}`} className="grid gap-3">
              <div className="grid gap-1">
                <h2 id={`group-${slug(group.title)}`} className="text-base font-medium">
                  {group.title}
                </h2>
                {group.hint && <p className="max-w-2xl text-sm text-muted-foreground">{group.hint}</p>}
              </div>
              <ul className="grid gap-3 md:grid-cols-2">
                {group.items.map((source) => (
                  <SourceCard
                    key={source.key}
                    source={source}
                    canManage={canManage}
                    pending={toggle.isPending && toggle.variables?.key === source.key}
                    onToggle={(enabled) =>
                      toggle.mutate(
                        { key: source.key, enabled },
                        {
                          onSuccess: () => toast.success(`${source.name} ${enabled ? "enabled" : "disabled"}`),
                          onError: (e) => toast.error(errorMessage(e)),
                        },
                      )
                    }
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function SourceCard({
  source,
  canManage,
  pending,
  onToggle,
}: {
  source: TrendSourceInfo;
  canManage: boolean;
  pending: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const s = status(source);
  const unavailable = source.pricing === "unavailable";
  return (
    <li>
      <Card className={cn("h-full", unavailable && "opacity-80")}>
        <CardContent className="grid gap-3">
          <div className="flex items-start gap-3">
            <div className="grid flex-1 gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-medium">{source.name}</h3>
                <Badge variant="outline">{PRICING[source.pricing]}</Badge>
              </div>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={cn("size-1.5 rounded-full", s.tone)} aria-hidden />
                {s.label}
                {source.mode && source.configured && <span>· {source.mode}</span>}
              </p>
            </div>
            {!unavailable && (
              <Switch
                checked={source.enabled}
                disabled={!canManage || pending}
                onCheckedChange={onToggle}
                aria-label={`Use ${source.name}`}
              />
            )}
          </div>
          <p className="text-sm text-muted-foreground">{source.description}</p>
          {source.missing.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-medium">Set on the server:</p>
              <ul className="flex flex-wrap gap-1.5">
                {source.missing.map((v) => (
                  <li key={v}>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{v}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {source.note && <p className="text-xs text-muted-foreground">{source.note}</p>}
          {source.enabled && !source.configured && !unavailable && (
            <p className="flex items-center gap-1.5 text-xs">
              <span className="size-1.5 rounded-full bg-warning" aria-hidden />
              Enabled, but skipped until it&apos;s configured.
            </p>
          )}
          {source.last_error && source.health !== "healthy" && (
            <p className="rounded-md bg-destructive/10 px-2 py-1 text-xs text-destructive">
              {source.last_error}
              {source.last_failure_at && ` (${timeAgo(source.last_failure_at)})`}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              {source.last_success_at ? (
                <>
                  Last success{" "}
                  <time title={formatDateTime(source.last_success_at)}>{timeAgo(source.last_success_at)}</time>
                </>
              ) : (
                "No successful runs yet"
              )}
            </span>
            {source.docs_url && (
              <a
                href={source.docs_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"
              >
                Docs <ExternalLinkIcon className="size-3" />
              </a>
            )}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
