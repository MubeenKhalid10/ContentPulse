"use client";

import { AlertTriangleIcon, LoaderCircleIcon, SparklesIcon, XCircleIcon } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useCancelJob } from "@/hooks/use-knowledge";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import type { KnowledgeJob, KnowledgeSummary } from "@/types/api";

function host(url: string | null) {
  if (!url) return "your website";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function ActiveJob({ job, canManage }: { job: KnowledgeJob; canManage: boolean }) {
  const cancel = useCancelJob();
  const isCrawl = job.kind === "crawl";
  // Discovery keeps growing during a crawl; the page budget is the real ceiling.
  const total = isCrawl ? Math.max(1, Math.min(job.max_pages, Math.max(job.pages_discovered, 1))) : Math.max(1, job.pages_discovered);
  const percent = Math.min(100, Math.round((job.pages_crawled / total) * 100));

  return (
    <Card>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <LoaderCircleIcon className="size-5 animate-spin text-primary" aria-hidden />
          <div className="grid flex-1 gap-0.5">
            <p className="font-medium" role="status">
              {job.cancel_requested
                ? "Stopping…"
                : job.status === "queued"
                  ? "Starting…"
                  : isCrawl
                    ? `Reading ${host(job.root_url)}`
                    : "Re-indexing your knowledge base"}
            </p>
            <p className="text-sm text-muted-foreground">
              {job.pages_crawled} of {isCrawl ? `up to ${total}` : total} pages processed
              {isCrawl && job.pages_discovered > job.max_pages && ` · ${job.pages_discovered} found`}
            </p>
          </div>
          {canManage && !job.cancel_requested && (
            <Button
              variant="outline"
              size="sm"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id, { onError: (e) => toast.error(errorMessage(e)) })}
            >
              Stop
            </Button>
          )}
        </div>
        <div
          className="h-1.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label="Crawl progress"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full rounded-full bg-primary transition-[width] duration-700" style={{ width: `${percent}%` }} />
        </div>
        <JobCounts job={job} />
      </CardContent>
    </Card>
  );
}

export function JobCounts({ job }: { job: KnowledgeJob }) {
  const items = [
    { label: "Indexed", value: job.pages_indexed },
    { label: "Unchanged", value: job.pages_unchanged },
    { label: "Skipped", value: job.pages_skipped, hint: "Too little text, not a web page, or noindex" },
    { label: "Failed", value: job.pages_failed },
  ];
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline gap-1.5" title={item.hint}>
          <dt className="text-muted-foreground">{item.label}</dt>
          <dd className="font-mono tabular-nums">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function LastJobNotice({ job }: { job: KnowledgeJob }) {
  if (job.status === "failed") {
    return (
      <Alert variant="destructive">
        <XCircleIcon />
        <AlertTitle>The last {job.kind === "crawl" ? "crawl" : "re-index"} failed</AlertTitle>
        <AlertDescription>{job.error ?? "Something went wrong."}</AlertDescription>
      </Alert>
    );
  }
  if (job.warnings.length) {
    return (
      <Alert>
        <AlertTriangleIcon />
        <AlertTitle>Finished with warnings</AlertTitle>
        <AlertDescription>
          <ul className="grid gap-1">
            {job.warnings.map((w, index) => (
              <li key={`${w}-${index}`}>{w}</li>
            ))}
          </ul>
        </AlertDescription>
      </Alert>
    );
  }
  return null;
}

export function KnowledgeStats({ summary }: { summary: KnowledgeSummary }) {
  const coverage = summary.chunks ? Math.round((summary.embedded_chunks / summary.chunks) * 100) : 0;
  const stats = [
    { label: "Pages & documents", value: summary.indexed_documents.toLocaleString() },
    { label: "Knowledge chunks", value: summary.chunks.toLocaleString() },
    {
      label: "Semantic coverage",
      value: summary.embeddings_enabled ? `${coverage}%` : "Off",
    },
    {
      label: "Last crawled",
      value: summary.last_crawled_at ? timeAgo(summary.last_crawled_at) : "Never",
      title: summary.last_crawled_at ? formatDateTime(summary.last_crawled_at) : undefined,
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border lg:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="grid gap-1 bg-card p-4" title={s.title}>
          <dd className="font-mono text-2xl font-semibold tabular-nums">{s.value}</dd>
          <dt className="text-xs text-muted-foreground">{s.label}</dt>
        </div>
      ))}
    </dl>
  );
}

export function SemanticSearchNotice({ canManage }: { canManage: boolean }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">
      <SparklesIcon className="mt-0.5 size-4 shrink-0" />
      <span>
        Search is keyword-only right now.{" "}
        {canManage
          ? "Configure an embedding provider on the server (EMBEDDING_PROVIDER, EMBEDDING_API_KEY), then re-index, to also match by meaning."
          : "An admin can enable meaning-based search."}
      </span>
    </p>
  );
}
