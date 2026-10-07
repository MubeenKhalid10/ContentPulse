"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BookOpenIcon, FilePlusIcon, GlobeIcon, RefreshCwIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ActiveJob, JobCounts, KnowledgeStats, LastJobNotice, SemanticSearchNotice } from "@/components/knowledge/crawl-status";
import { DocumentSheet } from "@/components/knowledge/document-sheet";
import { DocumentsTable } from "@/components/knowledge/documents-table";
import { CrawlDialog, DocumentDialog } from "@/components/knowledge/knowledge-dialogs";
import { KnowledgeSearch } from "@/components/knowledge/knowledge-search";
import { PageHeader } from "@/components/shared/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useKnowledgeSummary, useReindex } from "@/hooks/use-knowledge";
import { useOrgId } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import type { KnowledgeDocumentDetail, KnowledgeSummary } from "@/types/api";

/** Refresh lists and tell the user when a background job finishes. */
function useJobCompletion(summary: KnowledgeSummary | undefined) {
  const queryClient = useQueryClient();
  const orgId = useOrgId();
  const activeId = useRef<string | null>(null);

  useEffect(() => {
    const current = summary?.active_job?.id ?? null;
    const finished = activeId.current && !current ? summary?.last_job : null;
    activeId.current = current;
    if (!finished || finished.id === current) return;
    queryClient.invalidateQueries({ queryKey: ["org", orgId, "knowledge"] });
    queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    if (finished.status === "succeeded") {
      toast.success(
        finished.kind === "crawl"
          ? `Crawl finished: ${finished.pages_indexed} page${finished.pages_indexed === 1 ? "" : "s"} indexed, ${finished.pages_unchanged} unchanged`
          : "Re-index finished",
      );
    } else if (finished.status === "cancelled") {
      toast.message("Crawl stopped");
    } else if (finished.status === "failed") {
      toast.error(finished.error ?? "The job failed");
    }
  }, [summary, queryClient, orgId]);
}

export function KnowledgeBase() {
  const summary = useKnowledgeSummary();
  const canManage = useCan()("knowledge.write");
  const reindex = useReindex();
  const [crawlOpen, setCrawlOpen] = useState(false);
  const [docDialog, setDocDialog] = useState<{ editing: KnowledgeDocumentDetail | null } | null>(null);
  const [openDoc, setOpenDoc] = useState<string | null>(null);
  useJobCompletion(summary.data);

  const data = summary.data;
  const busy = !!data?.active_job;
  const isEmpty = data && data.documents === 0 && !data.active_job;

  return (
    <>
      <PageHeader
        title="Knowledge base"
        description="Your website pages and documents. Posts only make claims about you that these sources back up."
        actions={
          canManage &&
          data &&
          !isEmpty && (
            <>
              <Button variant="outline" onClick={() => setDocDialog({ editing: null })}>
                <FilePlusIcon />
                Add document
              </Button>
              <Button onClick={() => setCrawlOpen(true)} disabled={busy}>
                <GlobeIcon />
                Crawl website
              </Button>
            </>
          )
        }
      />

      {!data ? (
        <div className="grid gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : isEmpty ? (
        <EmptyState
          summary={data}
          canManage={canManage}
          onCrawl={() => setCrawlOpen(true)}
          onAddDocument={() => setDocDialog({ editing: null })}
        />
      ) : (
        <div className="grid gap-6">
          {data.active_job ? (
            <ActiveJob job={data.active_job} canManage={canManage} />
          ) : (
            data.last_job && <LastJobNotice job={data.last_job} />
          )}
          <KnowledgeStats summary={data} />
          {!data.embeddings_enabled && <SemanticSearchNotice canManage={canManage} />}
          {data.embeddings_enabled && data.embedded_chunks < data.chunks && canManage && !busy && (
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              Some knowledge is searchable by keyword only.
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0"
                onClick={() => reindex.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) })}
              >
                <RefreshCwIcon />
                Re-index now
              </Button>
            </p>
          )}
          <KnowledgeSearch onOpenDocument={setOpenDoc} />
          {data.last_job && !data.active_job && data.last_job.kind === "crawl" && data.last_job.status === "succeeded" && (
            <div className="-mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
              <span className="text-muted-foreground">Last crawl</span>
              <JobCounts job={data.last_job} />
            </div>
          )}
          <DocumentsTable canManage={canManage} onOpen={setOpenDoc} />
        </div>
      )}

      <CrawlDialog open={crawlOpen} onClose={() => setCrawlOpen(false)} websiteUrl={data?.website_url ?? null} />
      <DocumentDialog open={!!docDialog} editing={docDialog?.editing ?? null} onClose={() => setDocDialog(null)} />
      <DocumentSheet
        documentId={openDoc}
        onClose={() => setOpenDoc(null)}
        canManage={canManage}
        onEdit={(doc) => {
          setOpenDoc(null);
          setDocDialog({ editing: doc });
        }}
      />
    </>
  );
}

function EmptyState({
  summary,
  canManage,
  onCrawl,
  onAddDocument,
}: {
  summary: KnowledgeSummary;
  canManage: boolean;
  onCrawl: () => void;
  onAddDocument: () => void;
}) {
  return (
    <div className="grid gap-4">
      {summary.last_job && <LastJobNotice job={summary.last_job} />}
      <Card>
        <CardContent className="grid justify-items-center gap-4 py-12 text-center">
          <span className="grid size-12 place-items-center rounded-full bg-muted">
            <BookOpenIcon className="size-6 text-muted-foreground" />
          </span>
          <div className="grid max-w-md gap-1.5">
            <p className="text-lg font-medium">Teach ContentPulse about your business</p>
            <p className="text-sm text-muted-foreground">
              {summary.website_url
                ? `Crawl ${summary.website_url.replace(/^https?:\/\//, "").replace(/\/$/, "")} so trend matching and content generation are grounded in what you actually do.`
                : "Add your website to the organization profile, then crawl it so trend matching and content generation are grounded in what you actually do."}
            </p>
          </div>
          {canManage ? (
            <div className="flex flex-wrap justify-center gap-2">
              {summary.website_url ? (
                <Button onClick={onCrawl}>
                  <GlobeIcon />
                  Crawl website
                </Button>
              ) : (
                <Link href="/organization/profile" className={buttonVariants()}>
                  Add your website
                </Link>
              )}
              <Button variant="outline" onClick={onAddDocument}>
                <FilePlusIcon />
                Add a document
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">An admin can crawl the website.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
