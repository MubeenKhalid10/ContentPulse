"use client";

import { ChevronLeftIcon, ChevronRightIcon, MoreHorizontalIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Tag } from "@/components/shared/tag";
import { SourceLink } from "@/components/knowledge/knowledge-search";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type DocumentFilter,
  useDeleteDocument,
  useKnowledgeDocuments,
  useUpdateDocument,
} from "@/hooks/use-knowledge";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import type { KnowledgeDocument } from "@/types/api";

const PAGE_SIZE = 25;

export function DocumentStatus({ doc }: { doc: KnowledgeDocument }) {
  if (doc.excluded) return <Tag tone="neutral">Excluded</Tag>;
  if (doc.crawl_status === "failed") return <Tag tone="red" dot>Failed</Tag>;
  if (doc.crawl_status === "embedded") return <Tag tone="green" dot>Indexed</Tag>;
  if (doc.crawl_status === "extracted")
    return (
      <Tag tone="teal" dot title="Searchable by keyword; not yet indexed for meaning">
        Keyword only
      </Tag>
    );
  return <Tag tone="blue" dot>Pending</Tag>;
}

export function DocumentsTable({
  canManage,
  onOpen,
}: {
  canManage: boolean;
  onOpen: (id: string) => void;
}) {
  const [filter, setFilter] = useState<DocumentFilter>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [deleting, setDeleting] = useState<KnowledgeDocument>();
  const docs = useKnowledgeDocuments(filter, q, page, PAGE_SIZE);
  const update = useUpdateDocument();
  const total = docs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <section aria-labelledby="documents-heading" className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="documents-heading" className="mr-auto text-base font-medium">
          Sources
        </h2>
        <Tabs
          value={filter}
          onValueChange={(v) => {
            setFilter(v as DocumentFilter);
            setPage(0);
          }}
        >
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="indexed">Indexed</TabsTrigger>
            <TabsTrigger value="failed">Failed</TabsTrigger>
            <TabsTrigger value="excluded">Excluded</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input
          aria-label="Filter sources"
          placeholder="Filter by title or URL"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(0);
          }}
          className="w-full sm:w-56"
        />
      </div>

      <Card className="py-0">
        {docs.isPending ? (
          <div className="grid gap-3 p-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : docs.data?.items.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Page</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden text-right md:table-cell">Words</TableHead>
                <TableHead className="hidden text-right md:table-cell">Chunks</TableHead>
                <TableHead className="hidden lg:table-cell">Updated</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.data.items.map((doc) => (
                <TableRow key={doc.id} className={doc.excluded ? "text-muted-foreground" : undefined}>
                  <TableCell className="max-w-0 pl-4 sm:max-w-md">
                    <button
                      type="button"
                      onClick={() => onOpen(doc.id)}
                      className="block max-w-full truncate text-left font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {doc.title ?? "Untitled"}
                    </button>
                    <SourceLink url={doc.source_url} documentType={doc.document_type} />
                    {doc.crawl_error && (
                      <p className="truncate text-xs text-destructive" title={doc.crawl_error}>
                        {doc.crawl_error}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <DocumentStatus doc={doc} />
                  </TableCell>
                  <TableCell className="hidden text-right font-mono tabular-nums md:table-cell">
                    {doc.word_count.toLocaleString()}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono tabular-nums md:table-cell">
                    {doc.chunk_count}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">
                    <time dateTime={doc.updated_at} title={formatDateTime(doc.updated_at)}>
                      {timeAgo(doc.updated_at)}
                    </time>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${doc.title ?? doc.source_url}`} />}
                      >
                        <MoreHorizontalIcon />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-44">
                        <DropdownMenuItem onClick={() => onOpen(doc.id)}>View content</DropdownMenuItem>
                        {canManage && (
                          <>
                            <DropdownMenuItem
                              onClick={() =>
                                update.mutate(
                                  { id: doc.id, excluded: !doc.excluded },
                                  {
                                    onSuccess: () =>
                                      toast.success(doc.excluded ? "Included again" : "Excluded from knowledge"),
                                    onError,
                                  },
                                )
                              }
                            >
                              {doc.excluded ? "Include again" : "Exclude"}
                            </DropdownMenuItem>
                            <DropdownMenuItem variant="destructive" onClick={() => setDeleting(doc)}>
                              Delete
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="p-6 text-center text-sm text-muted-foreground">
            {q || filter !== "all" ? "No sources match this filter." : "No sources yet."}
          </p>
        )}
      </Card>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
          <span>
            Page {page + 1} of {pages} · {total} sources
          </span>
          <Button variant="outline" size="icon-sm" aria-label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}>
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Next page"
            disabled={page + 1 >= pages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      )}

      <DeleteDocumentDialog doc={deleting} onClose={() => setDeleting(undefined)} />
    </section>
  );
}

function DeleteDocumentDialog({ doc, onClose }: { doc?: KnowledgeDocument; onClose: () => void }) {
  const remove = useDeleteDocument();
  const crawled = doc?.document_type !== "manual";
  return (
    <AlertDialog open={!!doc} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {doc?.title ?? "this source"}?</AlertDialogTitle>
          <AlertDialogDescription>
            {crawled
              ? "It will come back the next time the website is crawled. To keep it out for good, exclude it instead."
              : "This document and its knowledge are removed permanently."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              doc &&
              remove.mutate(doc.id, {
                onSuccess: () => {
                  toast.success("Deleted");
                  onClose();
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
