"use client";

import { ExternalLinkIcon, SearchIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useKnowledgeSearch } from "@/hooks/use-knowledge";
import { errorMessage } from "@/lib/api";

const START = "⟦";
const END = "⟧";

/** Render ⟦highlighted⟧ terms from the server's ts_headline output. */
export function Highlighted({ text }: { text: string }) {
  const parts = text.split(new RegExp(`(${START}[^${END}]*${END})`, "g"));
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith(START) ? (
          <mark key={i} className="rounded-sm bg-primary/15 px-0.5 text-foreground">
            {part.slice(1, -1)}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

const MATCH_LABEL = { both: "Keyword + meaning", keyword: "Keyword", semantic: "Meaning" } as const;

export function KnowledgeSearch({ onOpenDocument }: { onOpenDocument: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const search = useKnowledgeSearch();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test what ContentPulse knows</CardTitle>
        <CardDescription>
          This is the retrieval the AI uses before writing. Ask something a customer might.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <form
          role="search"
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (query.trim()) search.mutate(query.trim());
          }}
        >
          <Input
            aria-label="Search the knowledge base"
            placeholder="e.g. What AI services do we offer?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Button type="submit" variant="outline" disabled={!query.trim() || search.isPending}>
            <SearchIcon />
            Search
          </Button>
        </form>

        {search.isPending && (
          <div className="grid gap-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}
        {search.isError && <p className="text-sm text-destructive">{errorMessage(search.error)}</p>}
        {search.data && (
          <div aria-live="polite" className="grid gap-1">
            {search.data.results.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing relevant found. If this is something you offer, add it to your website or as
                a document.
              </p>
            ) : (
              <ol className="grid gap-1">
                {search.data.results.map((hit) => (
                  <li key={hit.chunk_id}>
                    <button
                      type="button"
                      onClick={() => onOpenDocument(hit.document_id)}
                      className="-mx-2 grid w-[calc(100%+1rem)] gap-1 rounded-lg p-2 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{hit.title ?? hit.url}</span>
                        {hit.heading && <span className="text-xs text-muted-foreground">› {hit.heading}</span>}
                        <Badge variant="outline" className="ml-auto text-[10px]">
                          {MATCH_LABEL[hit.match]}
                        </Badge>
                      </span>
                      <span className="line-clamp-3 text-sm text-muted-foreground">
                        <Highlighted text={hit.snippet} />
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {search.data.mode === "keyword" && search.data.results.length > 0 && (
              <p className="text-xs text-muted-foreground">Keyword matching only.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SourceLink({ url, documentType }: { url: string; documentType: string }) {
  if (documentType === "manual") return <span className="text-xs text-muted-foreground">Added manually</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex max-w-full items-center gap-1 truncate text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
    >
      <span className="truncate">{url.replace(/^https?:\/\//, "")}</span>
      <ExternalLinkIcon className="size-3 shrink-0" />
    </a>
  );
}
