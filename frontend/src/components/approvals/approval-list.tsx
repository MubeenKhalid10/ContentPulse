"use client";

import {
  CheckCircle2Icon,
  CheckIcon,
  ImageIcon,
  MessageSquareIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { useApproveAll, useApprovals } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { APPROVAL_STATUS_LABEL } from "@/lib/approvals";
import { timeAgo, timeOfDay } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type {
  Approval,
  ApprovalFilter,
  ApprovalStage,
  Platform,
} from "@/types/api";

const PAGE = 30;
const STAGES: { value: ApprovalStage; label: string }[] = [
  { value: "copy", label: "Content approval" },
  { value: "design", label: "Design approval" },
];
const TABS: { value: ApprovalFilter; label: string }[] = [
  { value: "pending", label: "Waiting for approval" },
  { value: "approved", label: "Approved" },
  { value: "changes_requested", label: "Changes needed" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export function ApprovalList() {
  const [{ stage: savedStage, status, platform }, setFilters] =
    usePersistedState<{
      stage: ApprovalStage;
      status: ApprovalFilter;
      platform: "" | Platform;
    }>("approvals", { stage: "copy", status: "pending", platform: "" });
  // Older saved filters have no stage.
  const stage: ApprovalStage = savedStage ?? "copy";
  const setStage = (stage: ApprovalStage) =>
    setFilters((f) => ({ ...f, stage }));
  const setStatus = (status: ApprovalFilter) =>
    setFilters((f) => ({ ...f, status }));
  const setPlatform = (platform: "" | Platform) =>
    setFilters((f) => ({ ...f, platform }));
  const [limit, setLimit] = useState(PAGE);
  const approvals = useApprovals(stage, status, platform, limit);
  const counts = approvals.data?.counts;
  const canReview = useCan()("approval.manage");
  const approveAll = useApproveAll();
  // Submissions ticked to be approved together (only while they wait for a decision).
  const [selected, setSelected] = useState<string[]>([]);
  const selectable = canReview && status === "pending";
  const toggle = (ids: string[], on: boolean) =>
    setSelected((cur) =>
      on
        ? [...new Set([...cur, ...ids])]
        : cur.filter((id) => !ids.includes(id)),
    );
  const approveSelected = () =>
    approveAll.mutate(selected, {
      onSuccess: (r) => {
        setSelected([]);
        if (r.failed)
          toast.error(
            `${r.ok} approved, ${r.failed} could not be approved: ${errorMessage(r.error)}`,
          );
        else
          toast.success(
            stage === "copy"
              ? `${r.ok} ${r.ok === 1 ? "copy" : "copies"} approved. Their design briefs are ready.`
              : `${r.ok} ${r.ok === 1 ? "post" : "posts"} approved and ready to publish.`,
          );
      },
    });

  return (
    <>
      <PageHeader
        title="Approve posts"
        description="Every post is approved twice: first the written copy, then the finished design."
      />
      <div className="grid min-w-0 grid-cols-1 gap-6">
        <Tabs
          value={stage}
          onValueChange={(v) => {
            setStage(v as ApprovalStage);
            setLimit(PAGE);
            setSelected([]);
          }}
        >
          <TabsList variant="line">
            {STAGES.map((s) => (
              <TabsTrigger key={s.value} value={s.value} className="text-base">
                {s.label}
                {(approvals.data?.stage_pending?.[s.value] ?? 0) > 0 && (
                  <span className="ml-1.5 rounded-full bg-primary px-1.5 text-[11px] tabular-nums text-primary-foreground">
                    {approvals.data?.stage_pending?.[s.value]}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <p className="-mt-3 text-sm text-muted-foreground">
          {stage === "copy"
            ? "Check the written post. Approving it opens the design brief."
            : "Check the finished design with the copy. Approving it makes the post ready to publish."}
        </p>
        {counts?.all === 0 && !platform ? (
          <Card>
            <CardContent className="grid justify-items-center gap-4 py-12 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-muted">
                <CheckCircle2Icon className="size-6 text-muted-foreground" />
              </span>
              <div className="grid max-w-md gap-1.5">
                <p className="text-lg font-medium">
                  {stage === "copy"
                    ? "No copy to approve yet"
                    : "No designs to approve yet"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {stage === "copy"
                    ? "Posts appear here when a writer submits their copy for approval."
                    : "Posts appear here after the copy is approved and the design is added and submitted."}
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <Tabs
                value={status}
                onValueChange={(v) => {
                  setStatus(v as ApprovalFilter);
                  setLimit(PAGE);
                }}
              >
                <TabsList>
                  {TABS.map((tab) => (
                    <TabsTrigger key={tab.value} value={tab.value}>
                      {tab.label}
                      {counts &&
                        tab.value !== "all" &&
                        counts[tab.value] > 0 && (
                          <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                            {counts[tab.value]}
                          </span>
                        )}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <SimpleSelect
                aria-label="Platform"
                value={platform || "all"}
                onChange={(v) =>
                  setPlatform(v === "all" ? "" : (v as Platform))
                }
                options={[
                  { value: "all", label: "Any platform" },
                  ...PLATFORM_OPTIONS,
                ]}
                className="w-40 sm:ml-auto"
              />
            </div>

            {approvals.isPending ? (
              <div className="grid gap-3">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-xl" />
                ))}
              </div>
            ) : approvals.data?.items.length ? (
              <>
                <div
                  aria-busy={approvals.isPlaceholderData}
                  className={cn(
                    "transition-opacity",
                    approvals.isPlaceholderData && "opacity-50",
                  )}
                >
                  <DayGroups
                    items={approvals.data.items}
                    dateOf={eventAt}
                    label="Approvals"
                    render={(a) => (
                      <ApprovalRow
                        key={a.id}
                        approval={a}
                        select={
                          selectable
                            ? {
                                checked: selected.includes(a.id),
                                onChange: (on) => toggle([a.id], on),
                              }
                            : undefined
                        }
                      />
                    )}
                  />
                </div>
                {approvals.data.total > approvals.data.items.length && (
                  <Button
                    variant="outline"
                    className="justify-self-center"
                    onClick={() => setLimit((n) => n + PAGE)}
                  >
                    Show more (
                    {approvals.data.total - approvals.data.items.length} left)
                  </Button>
                )}
              </>
            ) : (
              <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                {status === "pending"
                  ? `You're all caught up. No ${stage === "copy" ? "copy" : "designs"} waiting for review.`
                  : "No submissions here."}
              </p>
            )}
          </>
        )}
      </div>
      {selected.length > 0 && (
        <div
          role="region"
          aria-label="Selected submissions"
          className="sticky bottom-4 z-10 mt-6 flex flex-wrap items-center gap-3 rounded-xl border bg-background/95 p-3 shadow-md backdrop-blur"
        >
          <span className="text-sm font-medium">
            {selected.length} selected
          </span>
          <Button
            className="ml-auto"
            size="sm"
            disabled={approveAll.isPending}
            onClick={approveSelected}
          >
            <CheckIcon />
            {approveAll.isPending
              ? "Approving…"
              : stage === "copy"
                ? "Approve selected copy"
                : "Approve selected designs"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      )}
    </>
  );
}

/** The moment a row is about: when it was decided, or submitted while still waiting. */
const eventAt = (a: Approval) => a.reviewed_at ?? a.created_at;

function ApprovalRow({
  approval: a,
  select,
}: {
  approval: Approval;
  select?: { checked: boolean; onChange: (on: boolean) => void };
}) {
  return (
    <li className="relative flex items-center gap-4 rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40">
      {select && (
        <input
          type="checkbox"
          aria-label={`Select ${a.post.title ?? "post"}`}
          checked={select.checked}
          onChange={(e) => select.onChange(e.target.checked)}
          className="relative z-10 size-4 shrink-0 cursor-pointer accent-primary"
        />
      )}
      <span className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-lg bg-muted">
        {a.preview_url ? (
          // Signed, short-lived URL; next/image can't optimize it.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={a.preview_url}
            alt=""
            className="size-full object-cover"
            loading="lazy"
          />
        ) : (
          <ImageIcon className="size-5 text-muted-foreground" />
        )}
      </span>
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <PlatformTag platform={a.post.platform} />
          <Link
            href={`/approvals/${a.id}`}
            className="truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {a.post.title ?? "Untitled post"}
          </Link>
          <Tag tone={APPROVAL_STATUS_TONE[a.status]} dot>
            {APPROVAL_STATUS_LABEL[a.status]}
          </Tag>
          {a.round > 1 && <Tag tone="orange">Round {a.round}</Tag>}
        </div>
        {a.topic_title && (
          <p className="truncate text-xs font-medium text-muted-foreground">
            Topic: {a.topic_title}
          </p>
        )}
        <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span>
            Submitted by{" "}
            {a.submitted_by?.name ?? a.submitted_by?.email ?? "someone"}{" "}
            {timeAgo(a.created_at)}
          </span>
          {a.reviewer && (
            <span>Reviewed by {a.reviewer.name ?? a.reviewer.email}</span>
          )}
          {a.comment_count > 0 && (
            <span className="inline-flex items-center gap-1">
              <MessageSquareIcon className="size-3" />
              {a.comment_count}
            </span>
          )}
        </p>
      </div>
      <time
        dateTime={eventAt(a)}
        className="shrink-0 pr-2 text-sm tabular-nums text-muted-foreground"
      >
        {timeOfDay(eventAt(a))}
      </time>
    </li>
  );
}
