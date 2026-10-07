"use client";

import { AlertTriangleIcon, LoaderCircleIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { POST_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type ContentFilters, usePosts } from "@/hooks/use-content";
import { POST_STATUS_LABEL } from "@/lib/content";
import { timeAgo } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { Post, PostGroup } from "@/types/api";

const PAGE = 30;
const TABS: { value: PostGroup; label: string }[] = [
  { value: "drafts", label: "Drafts" },
  { value: "design", label: "In design" },
  { value: "approval", label: "Waiting for approval" },
  { value: "approved", label: "Ready to publish" },
  { value: "archived", label: "Archived" },
];
const EMPTY: Record<PostGroup, string> = {
  drafts: "No drafts. Open a shortlisted topic, plan a post and click Write post.",
  design: "Nothing in design right now.",
  approval: "Nothing waiting for approval.",
  approved: "Nothing ready to publish yet.",
  archived: "No archived posts.",
  all: "No posts yet.",
};

export function ContentList() {
  const [filters, setFilters] = useState<ContentFilters>({ status: "drafts", platform: "", q: "" });
  const [limit, setLimit] = useState(PAGE);
  const posts = usePosts(filters, limit);
  const update = (patch: Partial<ContentFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };
  const counts = posts.data?.counts;
  const nothingYet = counts?.all === 0 && !filters.q && !filters.platform;

  return (
    <>
      <PageHeader
        title="Content studio"
        description="Write and edit your posts. When the copy is ready, send the post to design. Earlier versions are always kept."
      />
      {nothingYet ? (
        <Card>
          <CardContent className="grid justify-items-center gap-4 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted">
              <SparklesIcon className="size-6 text-muted-foreground" />
            </span>
            <div className="grid max-w-md gap-1.5">
              <p className="text-lg font-medium">No posts yet</p>
              <p className="text-sm text-muted-foreground">
                Shortlist a topic, plan a post for a platform, then click Write post on the topic page.
              </p>
            </div>
            <Link href="/topics" className={buttonVariants({ variant: "outline" })}>
              Go to Topics
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs value={filters.status} onValueChange={(v) => update({ status: v as PostGroup })}>
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                    {counts && counts[tab.value] > 0 && (
                      <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                        {counts[tab.value]}
                      </span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Input
              aria-label="Search posts"
              placeholder="Search posts"
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
              className="w-full sm:w-56"
            />
            <SimpleSelect
              aria-label="Platform"
              value={filters.platform || "all"}
              onChange={(v) => update({ platform: v === "all" ? "" : (v as ContentFilters["platform"]) })}
              options={[{ value: "all", label: "Any platform" }, ...PLATFORM_OPTIONS]}
              className="w-40 sm:ml-auto"
            />
          </div>

          {posts.isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-xl" />
              ))}
            </div>
          ) : posts.data?.items.length ? (
            <>
              <ul
                aria-label="Posts"
                aria-busy={posts.isPlaceholderData}
                className={cn("grid gap-3 transition-opacity", posts.isPlaceholderData && "opacity-50")}
              >
                {posts.data.items.map((post) => (
                  <PostRow key={post.id} post={post} />
                ))}
              </ul>
              {posts.data.total > posts.data.items.length && (
                <Button variant="outline" className="justify-self-center" onClick={() => setLimit((n) => n + PAGE)}>
                  Show more ({posts.data.total - posts.data.items.length} left)
                </Button>
              )}
            </>
          ) : (
            <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {filters.q || filters.platform ? "No posts match these filters." : EMPTY[filters.status]}
            </p>
          )}
        </div>
      )}
    </>
  );
}

export function PostRow({ post, compact = false }: { post: Post; compact?: boolean }) {
  const generation = post.generation;
  const busy = generation?.status === "queued" || generation?.status === "running";
  const failed = generation?.status === "failed" && !post.current_version;
  return (
    <li className="relative grid gap-1.5 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40">
      <div className="flex flex-wrap items-center gap-2">
        <PlatformTag platform={post.platform} />
        <Link
          href={`/content/${post.id}`}
          className="truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {post.title ?? "Untitled post"}
        </Link>
        <Tag tone={POST_STATUS_TONE[post.status]} dot>{POST_STATUS_LABEL[post.status]}</Tag>
        {post.variant_of_id && <Tag tone="neutral">Variant</Tag>}
        <span className="ml-auto text-xs text-muted-foreground">
          {post.current_version ? `v${post.current_version} · ` : ""}
          {timeAgo(post.updated_at)}
        </span>
      </div>
      {busy ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <LoaderCircleIcon className="size-4 animate-spin text-primary" />
          Writing…
        </p>
      ) : failed ? (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <AlertTriangleIcon className="size-4" />
          Generation failed. Open the post to try again.
        </p>
      ) : (
        post.hook && <p className={cn("text-sm text-muted-foreground", compact ? "line-clamp-1" : "line-clamp-2")}>{post.hook}</p>
      )}
    </li>
  );
}
