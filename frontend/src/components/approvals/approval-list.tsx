"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CheckIcon,
  ImageIcon,
  MessageSquareIcon,
  RefreshCwIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { isSwitchingList, ListLoading } from "@/components/shared/loading";
import { ChangeRequestTag } from "@/components/approvals/change-request";
import { ChangeRequestQueue } from "@/components/approvals/change-request-queue";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { useApproveAll, useApprovals } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { approvalStatusLabel } from "@/lib/approvals";
import { formatDateTime, timeAgo, timeOfDay } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import type {
  Approval,
  ApprovalFilter,
  ApprovalStage,
  Platform,
} from "@/types/api";

const PAGE = 30;
/** "ready" lists posts whose content and design are both approved. */
type View = ApprovalStage | "ready" | "requests";
const VIEWS: { value: View; label: string }[] = [
  { value: "copy", label: "Content approval" },
  { value: "design", label: "Design approval" },
  { value: "ready", label: "Ready to publish" },
  { value: "requests", label: "Change requests" },
];

export function ApprovalList() {
  const [{ stage: savedStage, platform }, setFilters] = usePersistedState<{
    stage: View;
    platform: "" | Platform;
  }>("approvals", { stage: "copy", platform: "" });
  // Older saved filters have no stage.
  const view: View = savedStage ?? "copy";
  const ready = view === "ready";
  // An approval tab lists what waits for a decision. Ready to publish is the
  // approved designs: a design is only approved after its content.
  const stage: ApprovalStage = view === "copy" || view === "requests" ? "copy" : "design";
  const shownStatus: ApprovalFilter = ready ? "approved" : "pending";
  const setStage = (stage: View) => setFilters((f) => ({ ...f, stage }));
  const setPlatform = (platform: "" | Platform) =>
    setFilters((f) => ({ ...f, platform }));
  const [limit, setLimit] = useState(PAGE);
  const approvals = useApprovals(stage, shownStatus, platform, limit);
  const counts = approvals.data?.counts;
  const canReview = useCan()("approval.manage");
  const approveAll = useApproveAll();
  // Submissions ticked to be approved together (only while they wait for a decision).
  const [selectedRaw, setSelected] = useState<string[]>([]);
  // Approved submissions leave the pending list; the ones that failed stay ticked.
  const listed = new Set(approvals.data?.items.map((a) => a.id));
  const selected = selectedRaw.filter((id) => listed.has(id));
  const [confirmOpen, setConfirmOpen] = useState(false);
  const selectable = canReview && shownStatus === "pending";
  const toggle = (ids: string[], on: boolean) =>
    setSelected((cur) =>
      on
        ? [...new Set([...cur, ...ids])]
        : cur.filter((id) => !ids.includes(id)),
    );
  const approveSelected = () =>
    approveAll.mutate(selected, {
      onSuccess: (r) => {
        if (!r.failed) setSelected([]);
        if (r.failed)
          toast.error(
            `${r.ok} approved, ${r.failed} could not be approved and ${r.failed === 1 ? "stays" : "stay"} selected: ${errorMessage(r.error)}`,
          );
        else
          toast.success(
            stage === "copy"
              ? `${r.ok} ${r.ok === 1 ? "copy" : "copies"} approved. Open Add designs to assign who designs them.`
              : `${r.ok} ${r.ok === 1 ? "post" : "posts"} approved and ready to publish.`,
          );
      },
    });

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Every post is approved twice: first the written copy, then the finished design."
      />
      <div className="grid min-w-0 grid-cols-1 gap-6">
        <div className="flex flex-wrap items-center gap-3">
          <Tabs
            value={view}
            onValueChange={(v) => {
              setStage(v as View);
              setLimit(PAGE);
              setSelected([]);
            }}
          >
            <TabsList variant="line">
              {VIEWS.map((s) => {
                const count =
                  (s.value === "ready"
                    ? approvals.data?.ready_count
                    : s.value === "requests"
                      ? approvals.data?.change_request_count
                      : approvals.data?.stage_pending?.[s.value]) ?? 0;
                return (
                  <TabsTrigger
                    key={s.value}
                    value={s.value}
                    className="text-base"
                  >
                    {s.label}
                    {count > 0 && (
                      <span className="ml-1.5 rounded-full bg-primary px-1.5 text-[11px] tabular-nums text-primary-foreground">
                        {count}
                      </span>
                    )}
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>
          {view !== "requests" && (
            <SimpleSelect
              aria-label="Platform"
              value={platform || "all"}
              onChange={(v) => setPlatform(v === "all" ? "" : (v as Platform))}
              options={[
                { value: "all", label: "Any platform" },
                ...PLATFORM_OPTIONS,
              ]}
              className="w-40 sm:ml-auto"
            />
          )}
        </div>
        <p className="-mt-3 text-sm text-muted-foreground">
          {view === "requests"
            ? "Creators asking to reopen locked content or designs. Accept to reopen only what they asked for, or decline with a reason."
            : ready
            ? "Posts with both the content and the design approved. Open one to share it."
            : stage === "copy"
              ? "Check the written post. Approving it sends the post to design."
              : "Check the finished design with the copy. Approving the design also approves the post: it becomes Ready to publish."}
        </p>
        {view === "requests" ? (
          <ChangeRequestQueue />
        ) : (ready ? counts?.approved : counts?.all) === 0 && !platform ? (
          <Card>
            <CardContent className="grid justify-items-center gap-4 py-12 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-muted">
                <CheckCircle2Icon className="size-6 text-muted-foreground" />
              </span>
              <div className="grid max-w-md gap-1.5">
                <p className="text-lg font-medium">
                  {ready
                    ? "No posts ready yet"
                    : stage === "copy"
                      ? "No copy to approve yet"
                      : "No designs to approve yet"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {ready
                    ? "Posts appear here once both their content and design are approved."
                    : stage === "copy"
                      ? "Posts appear here when a writer submits their copy for approval."
                      : "Posts appear here after the copy is approved and the design is added and submitted."}
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            {approvals.isPending || isSwitchingList(approvals, limit) ? (
              <ListLoading label="Loading approvals…" rows={3} rowClassName="h-24" />
            ) : approvals.isError ? (
              <Alert variant="destructive">
                <AlertTriangleIcon />
                <AlertDescription className="grid gap-2">
                  <span>Couldn&apos;t load approvals. {errorMessage(approvals.error)}</span>
                  <Button size="sm" variant="outline" className="w-fit" onClick={() => approvals.refetch()}>
                    <RefreshCwIcon />
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            ) : approvals.data?.items.length ? (
              <>
                <div aria-busy={approvals.isPlaceholderData}>
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
                    disabled={approvals.isPlaceholderData}
                    pending={approvals.isPlaceholderData}
                    onClick={() => setLimit((n) => n + PAGE)}
                  >
                    {approvals.isPlaceholderData
                      ? "Loading more…"
                      : `Show more (${approvals.data.total - approvals.data.items.length} left)`}
                  </Button>
                )}
              </>
            ) : (
              <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                {ready
                  ? "No posts ready on this platform."
                  : `You're all caught up. No ${stage === "copy" ? "copy" : "designs"} waiting for review.`}
              </p>
            )}
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Approve ${selected.length} ${stage === "copy" ? (selected.length === 1 ? "copy" : "copies") : selected.length === 1 ? "design" : "designs"}?`}
        description={
          stage === "copy"
            ? "The copy is locked and each post moves to design. Afterwards, assign who designs each one from Add designs."
            : "Each design and its post are approved and locked, and the posts become Ready to publish."
        }
        confirmLabel={`Approve ${selected.length}`}
        pending={approveAll.isPending}
        onConfirm={approveSelected}
      />
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
            pending={approveAll.isPending}
            onClick={() => setConfirmOpen(true)}
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
        // The padded wrapper makes a 32px click target around the 16px box.
        <span className="relative z-10 -m-2 grid shrink-0 cursor-pointer place-items-center p-2">
          <input
            type="checkbox"
            aria-label={`Select ${a.post.title ?? "post"}`}
            checked={select.checked}
            onChange={(e) => select.onChange(e.target.checked)}
            className="size-4 cursor-pointer accent-primary"
          />
        </span>
      )}
      <span className="grid size-12 shrink-0 place-items-center sm:size-16 overflow-hidden rounded-lg bg-muted">
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
            {approvalStatusLabel(a.status, a.stage)}
          </Tag>
          {a.round > 1 && <Tag tone="orange">Round {a.round}</Tag>}
          <ChangeRequestTag request={a.change_request} />
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
            <time dateTime={a.created_at} title={formatDateTime(a.created_at)}>
              {timeAgo(a.created_at)}
            </time>
          </span>
          {a.reviewer && (
            <span>Reviewed by {a.reviewer.name ?? a.reviewer.email}</span>
          )}
          {a.comment_count > 0 && (
            <span className="inline-flex items-center gap-1" aria-label={`${a.comment_count} comments`}>
              <MessageSquareIcon className="size-3" aria-hidden />
              {a.comment_count}
            </span>
          )}
        </p>
      </div>
      <time
        dateTime={eventAt(a)}
        title={formatDateTime(eventAt(a))}
        className="shrink-0 pr-2 text-sm tabular-nums text-muted-foreground"
      >
        {timeOfDay(eventAt(a))}
      </time>
    </li>
  );
}
