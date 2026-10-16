"use client";

import {
  AlertTriangleIcon,
  LoaderCircleIcon,
  SendIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import {
  type ContentFilters,
  usePosts,
  useSubmitAllForReview,
} from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { timeAgo, timeOfDay } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { PLATFORM_LABEL } from "@/lib/topics";
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
  drafts:
    "No drafts. Open a shortlisted topic, plan a post and click Write post.",
  design: "Nothing in design right now.",
  approval: "Nothing waiting for approval.",
  approved: "Nothing ready to publish yet.",
  archived: "No archived posts.",
  all: "No posts yet.",
};

export function ContentList() {
  const [filters, setFilters] = usePersistedState<ContentFilters>("content", {
    status: "drafts",
    platform: "",
    q: "",
  });
  const [limit, setLimit] = useState(PAGE);
  const posts = usePosts(filters, limit);
  const update = (patch: Partial<ContentFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
    setSelected([]);
  };
  const counts = posts.data?.counts;
  const canEdit = useCan()("content.edit");
  const submitAll = useSubmitAllForReview();
  // Posts ticked to be sent for approval together.
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (ids: string[], on: boolean) =>
    setSelected((cur) =>
      on
        ? [...new Set([...cur, ...ids])]
        : cur.filter((id) => !ids.includes(id)),
    );
  const submitSelected = (ids: string[]) =>
    submitAll.mutate(ids, {
      onSuccess: (r) => {
        setSelected((cur) => cur.filter((id) => !ids.includes(id)));
        if (r.failed)
          toast.error(
            `${r.ok} sent, ${r.failed} could not be sent: ${errorMessage(r.error)}`,
          );
        else
          toast.success(
            r.ok === 1
              ? "Sent to an admin for approval"
              : `${r.ok} posts sent to an admin for approval together`,
          );
      },
    });
  const nothingYet = counts?.all === 0 && !filters.q && !filters.platform;

  return (
    <>
      <PageHeader
        title="Write posts"
        description="Write and edit your posts. Posts planned together for one topic stay together here: tick them to send the copy for approval in one go."
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
                Shortlist a topic, plan a post for a platform, then click Write
                post on the topic page.
              </p>
            </div>
            <Link
              href="/topics"
              className={buttonVariants({ variant: "outline" })}
            >
              Go to Topics
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs
              value={filters.status}
              onValueChange={(v) => update({ status: v as PostGroup })}
            >
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
              onChange={(v) =>
                update({
                  platform:
                    v === "all" ? "" : (v as ContentFilters["platform"]),
                })
              }
              options={[
                { value: "all", label: "Any platform" },
                ...PLATFORM_OPTIONS,
              ]}
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
              <div
                aria-busy={posts.isPlaceholderData}
                className={cn(
                  "transition-opacity",
                  posts.isPlaceholderData && "opacity-50",
                )}
              >
                <DayGroups
                  items={byTopic(posts.data.items)}
                  dateOf={(g) => g.updated_at}
                  label="Posts"
                  render={(g) => (
                    <TopicGroup
                      key={g.key}
                      group={g}
                      selectable={canEdit && filters.status === "drafts"}
                      selected={selected}
                      onToggle={toggle}
                      onSubmit={submitSelected}
                      submitting={submitAll.isPending}
                    />
                  )}
                />
              </div>
              {posts.data.total > posts.data.items.length && (
                <Button
                  variant="outline"
                  className="justify-self-center"
                  onClick={() => setLimit((n) => n + PAGE)}
                >
                  Show more ({posts.data.total - posts.data.items.length} left)
                </Button>
              )}
            </>
          ) : (
            <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {filters.q || filters.platform
                ? "No posts match these filters."
                : EMPTY[filters.status]}
            </p>
          )}
        </div>
      )}
      {selected.length > 0 && (
        <div
          role="region"
          aria-label="Selected posts"
          className="sticky bottom-4 z-10 mt-6 flex flex-wrap items-center gap-3 rounded-xl border bg-background/95 p-3 shadow-md backdrop-blur"
        >
          <span className="text-sm font-medium">
            {selected.length} {selected.length === 1 ? "post" : "posts"}{" "}
            selected
          </span>
          <Button
            className="ml-auto"
            size="sm"
            disabled={submitAll.isPending}
            onClick={() => submitSelected(selected)}
          >
            <SendIcon />
            {submitAll.isPending ? "Sending…" : "Submit selected for approval"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      )}
    </>
  );
}

interface TopicPosts {
  key: string;
  topic: Post["topic"];
  posts: Post[];
  updated_at: string;
}

/** Posts planned for the same topic stay together, newest group first. */
function byTopic(posts: Post[]): TopicPosts[] {
  const groups = new Map<string, TopicPosts>();
  for (const post of posts) {
    const key = post.topic?.id ?? post.id;
    const group = groups.get(key) ?? {
      key,
      topic: post.topic,
      posts: [],
      updated_at: post.updated_at,
    };
    group.posts.push(post);
    if (post.updated_at > group.updated_at) group.updated_at = post.updated_at;
    groups.set(key, group);
  }
  return [...groups.values()];
}

/** Ready to send for approval: written, not mid-generation, still a draft. */
const canSubmit = (p: Post) =>
  p.status === "draft" &&
  p.current_version > 0 &&
  p.generation?.status !== "queued" &&
  p.generation?.status !== "running";

function Check({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (on: boolean) => void;
  label: string;
}) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="relative z-10 size-4 shrink-0 cursor-pointer accent-primary"
    />
  );
}

function TopicGroup({
  group,
  selectable,
  selected,
  onToggle,
  onSubmit,
  submitting,
}: {
  group: TopicPosts;
  selectable: boolean;
  selected: string[];
  onToggle: (ids: string[], on: boolean) => void;
  onSubmit: (ids: string[]) => void;
  submitting: boolean;
}) {
  const ready = group.posts.filter(canSubmit);
  const pick = (post: Post) =>
    selectable && canSubmit(post)
      ? {
          checked: selected.includes(post.id),
          onChange: (on: boolean) => onToggle([post.id], on),
        }
      : undefined;
  if (group.posts.length === 1) {
    return <PostRow post={group.posts[0]} select={pick(group.posts[0])} />;
  }
  const allReady =
    ready.length > 0 && ready.every((p) => selected.includes(p.id));
  return (
    <li className="grid gap-3 rounded-xl bg-muted/30 p-3 ring-1 ring-foreground/10">
      <div className="flex flex-wrap items-center gap-2 px-1">
        {selectable && ready.length > 0 && (
          <Check
            checked={allReady}
            onChange={(on) =>
              onToggle(
                ready.map((p) => p.id),
                on,
              )
            }
            label={`Select all ${group.posts.length} posts for ${group.topic?.title ?? "this topic"}`}
          />
        )}
        <div className="grid min-w-0 flex-1 gap-0.5">
          <span className="truncate font-semibold">
            {group.topic?.title ?? "Posts"}
          </span>
          <span className="text-xs text-muted-foreground">
            {group.posts.length} posts planned together
          </span>
        </div>
        {selectable && ready.length > 1 && (
          <Button
            size="sm"
            variant="outline"
            disabled={submitting}
            onClick={() => onSubmit(ready.map((p) => p.id))}
          >
            <SendIcon />
            Submit all {ready.length} for approval
          </Button>
        )}
      </div>
      <ul
        aria-label={`Posts for ${group.topic?.title ?? "this topic"}`}
        className="grid gap-2"
      >
        {group.posts.map((post) => (
          <PostRow key={post.id} post={post} select={pick(post)} />
        ))}
      </ul>
    </li>
  );
}

export function PostRow({
  post,
  compact = false,
  select,
}: {
  post: Post;
  compact?: boolean;
  /** Shows a checkbox for sending several posts for approval together. */
  select?: { checked: boolean; onChange: (on: boolean) => void };
}) {
  const generation = post.generation;
  const busy =
    generation?.status === "queued" || generation?.status === "running";
  const failed = generation?.status === "failed" && !post.current_version;
  return (
    <li className="relative grid gap-1.5 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40">
      <div className="flex flex-wrap items-center gap-2">
        {select && (
          <Check
            checked={select.checked}
            onChange={select.onChange}
            label={`Select ${PLATFORM_LABEL[post.platform]} post`}
          />
        )}
        <PlatformTag platform={post.platform} />
        <Link
          href={`/content/${post.id}`}
          className="truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {post.title ?? "Untitled post"}
        </Link>
        <Tag tone={POST_STATUS_TONE[post.status]} dot>
          {POST_STATUS_LABEL[post.status]}
        </Tag>
        {post.variant_of_id && <Tag tone="neutral">Variant</Tag>}
        <span className="ml-auto text-xs text-muted-foreground">
          {post.current_version ? `v${post.current_version} · ` : ""}
          {compact ? timeAgo(post.updated_at) : timeOfDay(post.updated_at)}
        </span>
      </div>
      {busy ? (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          role="status"
        >
          <LoaderCircleIcon className="size-4 animate-spin text-primary" />
          Writing…
        </p>
      ) : failed ? (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <AlertTriangleIcon className="size-4" />
          Generation failed. Open the post to try again.
        </p>
      ) : (
        post.hook && (
          <p
            className={cn(
              "text-sm text-muted-foreground",
              compact ? "line-clamp-1" : "line-clamp-2",
            )}
          >
            {post.hook}
          </p>
        )
      )}
    </li>
  );
}
