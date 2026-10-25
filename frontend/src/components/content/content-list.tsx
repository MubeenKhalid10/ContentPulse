"use client";

import {
  AlertTriangleIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  SendIcon,
  SparklesIcon,
  Trash2Icon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import {
  FILTER_SEARCH,
  FILTER_SELECT,
  FilterBar,
} from "@/components/shared/filter-bar";
import { SearchInput } from "@/components/shared/search-input";
import { SubTabs } from "@/components/shared/sub-tabs";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import {
  type ContentFilters,
  useDeletePost,
  usePosts,
  useRegenerate,
  useSubmitAllForReview,
} from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatDateTime, timeAgo, timeOfDay } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { PLATFORM_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Post, PostGroup, PostStatus } from "@/types/api";

const PAGE = 30;
// The writer's view: posts to write, posts sent back, and where submitted
// copy stands (waiting for approval or approved).
const TABS: { value: PostGroup; label: string }[] = [
  { value: "drafts", label: "Draft posts" },
  { value: "changes", label: "Changes requested" },
  { value: "approval", label: "Sent for approval" },
];
const EMPTY: Record<PostGroup, string> = {
  drafts:
    "No drafts yet.",
  changes: "Nothing sent back. Posts an approver asks you to change appear here.",
  design: "Nothing in design right now.",
  approval: "No copy sent for approval yet.",
  approval_pending: "Nothing is waiting for an admin right now.",
  approval_done: "No approved posts yet.",
  approved: "Nothing ready to post yet.",
  archived: "No archived posts.",
  all: "No posts yet.",
};

export function ContentList() {
  const [saved, setFilters] = usePersistedState<ContentFilters>("content", {
    status: "drafts",
    platform: "",
    q: "",
  });
  // A tab saved before it was removed (such as "Waiting for content approval").
  const tabOf = (s: PostGroup): PostGroup =>
    s === "approval_pending" || s === "approval_done" ? "approval" : s;
  const filters: ContentFilters =
    saved.status === "approval"
      ? { ...saved, status: "approval_pending" }
      : TABS.some((t) => t.value === tabOf(saved.status))
        ? saved
        : { ...saved, status: "drafts" };
  const [limit, setLimit] = useState(PAGE);
  const posts = usePosts(filters, limit);
  const update = (patch: Partial<ContentFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
    setSelectedRaw([]);
  };
  const counts = posts.data?.counts;
  const canEdit = useCan()("content.edit");
  const submitAll = useSubmitAllForReview();
  // Posts ticked to be sent for approval together.
  const [selectedRaw, setSelectedRaw] = useState<string[]>([]);
  // Posts that were sent leave the Draft list; the ones that failed stay ticked.
  const stillDraft = new Set(posts.data?.items.filter(canSubmit).map((p) => p.id));
  const selected = selectedRaw.filter((id) => stillDraft.has(id));
  const setSelected = setSelectedRaw;
  // Ids waiting for the "send these?" confirmation.
  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);
  const toggle = (ids: string[], on: boolean) =>
    setSelected((cur) =>
      on
        ? [...new Set([...cur, ...ids])]
        : cur.filter((id) => !ids.includes(id)),
    );
  const submitSelected = (ids: string[]) => setConfirmIds(ids);
  const runSubmit = (ids: string[]) =>
    submitAll.mutate(ids, {
      onSuccess: (r) => {
        if (!r.failed) setSelected((cur) => cur.filter((id) => !ids.includes(id)));
        if (r.failed)
          toast.error(
            `${r.ok} sent, ${r.failed} could not be sent and ${r.failed === 1 ? "stays" : "stay"} selected: ${errorMessage(r.error)}`,
          );
        else
          toast.success(
            r.ok === 1
              ? "Sent to an admin for Content approval"
              : `${r.ok} posts sent to an admin for Content approval together`,
          );
      },
    });
  const nothingYet = counts?.all === 0 && !filters.q && !filters.platform;

  return (
    <>
      <PageHeader
        title="Write posts"
        description="Write and edit your posts. Posts planned together for one topic stay together: tick drafts to send their copy for Content approval in one go."
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
              Go to Shortlist & plans
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <FilterBar>
            <Tabs
              value={tabOf(filters.status)}
              onValueChange={(v) =>
                update({ status: v === "approval" ? "approval_pending" : (v as PostGroup) })
              }
              className="shrink-0"
            >
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                    {counts && counts[tab.value] > 0 && (
                      <span
                        className={cn(
                          "ml-1 rounded-full px-1.5 text-[11px] tabular-nums",
                          tab.value === "changes"
                            ? "bg-primary font-semibold text-primary-foreground"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        {counts[tab.value]}
                      </span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <SearchInput
              aria-label="Search posts"
              placeholder="Search posts"
              value={filters.q}
              onChange={(q) => update({ q })}
              className={FILTER_SEARCH}
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
              className={FILTER_SELECT}
            />
          </FilterBar>
          {tabOf(filters.status) === "approval" && (
            <SubTabs
              label="Approval status"
              value={filters.status}
              onChange={(status) => update({ status })}
              items={[
                { value: "approval_pending", label: "Pending", count: counts?.approval_pending },
                { value: "approval_done", label: "Approved", count: counts?.approval_done },
              ]}
            />
          )}

          {posts.isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-xl" />
              ))}
            </div>
          ) : posts.isError ? (
            <Alert variant="destructive">
              <AlertTriangleIcon />
              <AlertDescription className="grid gap-2">
                <span>Couldn&apos;t load your posts. {errorMessage(posts.error)}</span>
                <Button size="sm" variant="outline" className="w-fit" onClick={() => posts.refetch()}>
                  <RefreshCwIcon />
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
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
            <div className="grid justify-items-center gap-3 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              <p>
                {filters.q || filters.platform
                  ? "No posts match these filters."
                  : EMPTY[filters.status]}
              </p>
              {!filters.q && !filters.platform && filters.status === "drafts" && (
                <Link href="/topics" className={buttonVariants({ variant: "outline", size: "sm" })}>
                  Open Topics to plan a post
                </Link>
              )}
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={!!confirmIds}
        onOpenChange={(o) => !o && setConfirmIds(null)}
        title={`Submit ${confirmIds?.length ?? 0} ${confirmIds?.length === 1 ? "post" : "posts"} for Content approval?`}
        description="An admin will review the copy. While a post is in review its copy is locked, and you can withdraw it from the post page. Once approved, it moves on to design."
        confirmLabel={`Submit ${confirmIds?.length ?? 0} ${confirmIds?.length === 1 ? "post" : "posts"}`}
        pending={submitAll.isPending}
        onConfirm={() => confirmIds && runSubmit(confirmIds)}
      />
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
            {submitAll.isPending ? "Sending…" : "Submit selected for Content approval"}
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
    // The padded label makes a 32px click target around the 16px box.
    <span className="relative z-10 -m-2 grid shrink-0 cursor-pointer place-items-center p-2">
      <input
        type="checkbox"
        aria-label={label}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 cursor-pointer accent-primary"
      />
    </span>
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
    return (
      <PostRow
        post={group.posts[0]}
        contentView
        select={pick(group.posts[0])}
      />
    );
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
            Submit all {ready.length} for Content approval
          </Button>
        )}
      </div>
      <ul
        aria-label={`Posts for ${group.topic?.title ?? "this topic"} for Content approval`}
        className="grid gap-2"
      >
        {group.posts.map((post) => (
          <PostRow
            key={post.id}
            post={post}
            contentView
            select={pick(post)}
          />
        ))}
      </ul>
    </li>
  );
}

/** Past content approval: the writer's part is done. */
const COPY_APPROVED: PostStatus[] = [
  "design_pending",
  "design_in_progress",
  "design_uploaded",
  "pending_approval",
  "approved",
  "final",
];

/** A post whose writing failed: write it again, or drop it and keep the others. */
function FailedPostActions({ post }: { post: Post }) {
  const can = useCan();
  const regenerate = useRegenerate();
  const remove = useDeletePost();
  const busy = regenerate.isPending || remove.isPending;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-destructive">
      <AlertTriangleIcon className="size-4" />
      <span className="mr-auto">
        Writing this post failed.
        {post.generation?.error && <span className="block text-xs font-normal">{post.generation.error}</span>}
      </span>
      {can("content.generate") && (
        <Button
          size="sm"
          variant="outline"
          className="relative z-10"
          disabled={busy}
          onClick={() =>
            regenerate.mutate(
              { id: post.id },
              {
                onSuccess: () => toast.success("Writing it again…"),
                onError,
              },
            )
          }
        >
          <RefreshCwIcon />
          Try again
        </Button>
      )}
      {can("content.edit") && (
        <Button
          size="sm"
          variant="ghost"
          className="relative z-10 text-destructive"
          disabled={busy}
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2Icon />
          Delete
        </Button>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete this failed post?"
        description="Nothing was written, so only this empty post is removed. Your plan and other posts are not affected. This can't be undone."
        confirmLabel="Delete post"
        destructive
        pending={busy}
        onConfirm={() =>
          remove.mutate(post.id, {
            onSuccess: () => toast.success("Failed post deleted"),
            onError,
          })
        }
      />
    </div>
  );
}

export function PostRow({
  post,
  compact = false,
  href,
  contentView = false,
  select,
}: {
  post: Post;
  compact?: boolean;
  /** Where the row opens; the writing studio by default. */
  href?: string;
  /** The writer's view: once the copy is approved, the tag says so. */
  contentView?: boolean;
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
          href={href ?? `/content/${post.id}`}
          className="min-w-0 max-w-full truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {post.title ?? "Untitled post"}
        </Link>
        {contentView && COPY_APPROVED.includes(post.status) ? (
          <Tag tone="green" dot>
            Content approved
          </Tag>
        ) : (
          <Tag tone={POST_STATUS_TONE[post.status]} dot>
            {POST_STATUS_LABEL[post.status]}
          </Tag>
        )}
        {post.variant_of_id && <Tag tone="neutral">Variant</Tag>}
        <span className="ml-auto text-xs text-muted-foreground">
          {post.current_version ? `v${post.current_version} · ` : ""}
          <time dateTime={post.updated_at} title={formatDateTime(post.updated_at)}>
            {compact ? timeAgo(post.updated_at) : timeOfDay(post.updated_at)}
          </time>
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
        <FailedPostActions post={post} />
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
