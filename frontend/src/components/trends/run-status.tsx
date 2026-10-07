"use client";

import { AlertTriangleIcon, LoaderCircleIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDateTime, timeAgo } from "@/lib/format";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import type { DiscoveryRun, SourceResult } from "@/types/api";

const DOT: Record<SourceResult["status"], string> = {
  ok: "bg-success",
  failed: "bg-destructive",
  not_configured: "bg-muted-foreground/40",
  running: "bg-primary animate-pulse",
  unknown: "bg-muted-foreground/40",
};

function describe(result: SourceResult): string {
  switch (result.status) {
    case "ok":
      return `${result.items} item${result.items === 1 ? "" : "s"} collected`;
    case "failed":
      return result.error ?? "Failed";
    case "not_configured":
      return result.error ?? "Not configured";
    case "running":
      return "Collecting…";
    default:
      return "Unknown source";
  }
}

export function RunStatus({ run }: { run: DiscoveryRun }) {
  const active = run.status === "queued" || run.status === "running";
  const finishedAt = run.finished_at ?? run.created_at;

  return (
    <Card size="sm">
      <CardContent className="grid min-w-0 grid-cols-1 gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {active ? (
            <span className="flex items-center gap-2 font-medium" role="status">
              <LoaderCircleIcon className="size-4 animate-spin text-primary" />
              Collecting trends from {run.sources.length} sources…
            </span>
          ) : run.status === "failed" ? (
            <span className="flex items-center gap-2 font-medium text-destructive">
              <AlertTriangleIcon className="size-4" />
              Last discovery failed
            </span>
          ) : (
            <span className="font-medium">
              Updated{" "}
              <time dateTime={finishedAt} title={formatDateTime(finishedAt)}>
                {timeAgo(finishedAt)}
              </time>
            </span>
          )}
          {!active && run.status === "succeeded" && (
            <span className="text-muted-foreground">
              {run.items_collected} items · {run.trends_created} new trend{run.trends_created === 1 ? "" : "s"}
              {run.trigger === "scheduled" && " · scheduled run"}
            </span>
          )}
        </div>
        {run.status === "failed" && run.error && <p className="text-sm text-muted-foreground">{run.error}</p>}
        <ul className="flex flex-wrap gap-2" aria-label="Source results">
          {Object.entries(run.results).map(([key, result]) => (
            <li key={key}>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <span
                      tabIndex={0}
                      className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  }
                >
                  <span className={cn("size-1.5 rounded-full", DOT[result.status])} aria-hidden />
                  {sourceName(key)}
                  {result.status === "ok" && <span className="font-mono text-muted-foreground">{result.items}</span>}
                  <span className="sr-only">: {describe(result)}</span>
                </TooltipTrigger>
                <TooltipContent className="max-w-72">{describe(result)}</TooltipContent>
              </Tooltip>
            </li>
          ))}
        </ul>
        {run.warnings.length > 0 && !active && (
          <details className="min-w-0 text-xs break-words text-muted-foreground">
            <summary className="cursor-pointer select-none hover:text-foreground">
              {run.warnings.length} note{run.warnings.length === 1 ? "" : "s"} from this run
            </summary>
            <ul className="mt-1.5 grid list-disc gap-0.5 pl-4">
              {run.warnings.map((w, index) => (
                <li key={`${w}-${index}`}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
