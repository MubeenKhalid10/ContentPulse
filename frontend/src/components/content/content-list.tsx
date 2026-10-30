"use client";

import { AlertTriangleIcon, RefreshCwIcon, SendIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { isSwitchingList, ListLoading } from "@/components/shared/loading";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import { FILTER_SEARCH, FILTER_SELECT, FilterBar } from "@/components/shared/filter-bar";
import { SearchInput } from "@/components/shared/search-input";
import { SubTabs } from "@/components/shared/sub-tabs";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { type ContentFilters, usePosts, useSubmitAllForReview } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { PostGroup } from "@/types/api";

import { byTopic, TopicGroup } from "./topic-group";
import { canSubmit } from "./post-row";

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

          {posts.isPending || isSwitchingList(posts, limit) ? (
            <ListLoading label="Loading posts…" />
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
              <div aria-busy={posts.isPlaceholderData}>
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
                      submittingIds={submitAll.isPending ? submitAll.variables : undefined}
                    />
                  )}
                />
              </div>
              {posts.data.total > posts.data.items.length && (
                <Button
                  variant="outline"
                  className="justify-self-center"
                  disabled={posts.isPlaceholderData}
                  pending={posts.isPlaceholderData}
                  onClick={() => setLimit((n) => n + PAGE)}
                >
                  {posts.isPlaceholderData
                    ? "Loading more…"
                    : `Show more (${posts.data.total - posts.data.items.length} left)`}
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
            pending={
              submitAll.isPending &&
              submitAll.variables.length === selected.length &&
              selected.every((id) => submitAll.variables.includes(id))
            }
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
