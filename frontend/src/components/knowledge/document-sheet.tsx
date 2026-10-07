"use client";

import { CircleCheckIcon, CircleDashedIcon } from "lucide-react";

import { DocumentStatus } from "@/components/knowledge/documents-table";
import { SourceLink } from "@/components/knowledge/knowledge-search";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgeDocument } from "@/hooks/use-knowledge";
import type { KnowledgeDocumentDetail } from "@/types/api";

/** Render stored lightweight markdown: "#…" headings and paragraphs. */
function DocumentContent({ markdown }: { markdown: string }) {
  return (
    <div className="grid gap-3 text-sm leading-relaxed">
      {markdown.split(/\n\s*\n/).map((block, i) => {
        const heading = /^(#{1,6})\s+(.*)$/.exec(block.trim());
        if (heading) {
          const level = heading[1].length;
          return (
            <p
              key={i}
              role="heading"
              aria-level={Math.min(level + 2, 6)}
              className={level <= 2 ? "mt-2 font-semibold" : "font-medium"}
            >
              {heading[2]}
            </p>
          );
        }
        return (
          <p key={i} className="text-muted-foreground">
            {block}
          </p>
        );
      })}
    </div>
  );
}

export function DocumentSheet({
  documentId,
  onClose,
  onEdit,
  canManage,
}: {
  documentId: string | null;
  onClose: () => void;
  onEdit: (doc: KnowledgeDocumentDetail) => void;
  canManage: boolean;
}) {
  const doc = useKnowledgeDocument(documentId);
  const data = doc.data;

  return (
    <Sheet open={!!documentId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-xl">
        <SheetHeader className="border-b p-4 pr-12">
          {data ? (
            <>
              <SheetTitle className="leading-snug">{data.title ?? "Untitled"}</SheetTitle>
              <SheetDescription render={<div className="grid gap-2" />}>
                <SourceLink url={data.source_url} documentType={data.document_type} />
                <span className="flex flex-wrap items-center gap-2">
                  <DocumentStatus doc={data} />
                  <span className="text-xs">
                    {data.word_count.toLocaleString()} words · {data.chunks.length} chunks
                  </span>
                  {canManage && data.document_type === "manual" && (
                    <Button size="xs" variant="outline" className="ml-auto" onClick={() => onEdit(data)}>
                      Edit
                    </Button>
                  )}
                </span>
                {data.meta.description && <span className="text-xs italic">{data.meta.description}</span>}
              </SheetDescription>
            </>
          ) : (
            <>
              <SheetTitle className="sr-only">Loading document</SheetTitle>
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </>
          )}
        </SheetHeader>

        {data && (
          <Tabs defaultValue="content" className="min-h-0 flex-1">
            <TabsList className="mx-4 mt-3">
              <TabsTrigger value="content">Content</TabsTrigger>
              <TabsTrigger value="chunks">Chunks ({data.chunks.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="content" className="overflow-y-auto px-4 pb-6">
              {data.crawl_error && <p className="mb-3 text-sm text-destructive">{data.crawl_error}</p>}
              {data.content ? (
                <DocumentContent markdown={data.content} />
              ) : (
                <p className="text-sm text-muted-foreground">No content stored.</p>
              )}
            </TabsContent>
            <TabsContent value="chunks" className="overflow-y-auto px-4 pb-6">
              <p className="mb-3 text-xs text-muted-foreground">
                The exact passages the AI retrieves. Each keeps its section heading for context.
              </p>
              <ol className="grid gap-3">
                {data.chunks.map((chunk) => (
                  <li key={chunk.id} className="grid gap-1.5 rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="font-mono">#{chunk.chunk_index + 1}</span>
                      {chunk.heading && <span className="truncate font-medium text-foreground">{chunk.heading}</span>}
                      <span
                        className="ml-auto inline-flex items-center gap-1"
                        title={chunk.embedded ? "Searchable by meaning" : "Keyword search only"}
                      >
                        {chunk.embedded ? (
                          <CircleCheckIcon className="size-3.5 text-primary" />
                        ) : (
                          <CircleDashedIcon className="size-3.5" />
                        )}
                        ~{chunk.token_count ?? 0} tokens
                      </span>
                    </div>
                    <p className="text-sm whitespace-pre-line text-muted-foreground">{chunk.content}</p>
                  </li>
                ))}
              </ol>
            </TabsContent>
          </Tabs>
        )}
      </SheetContent>
    </Sheet>
  );
}
