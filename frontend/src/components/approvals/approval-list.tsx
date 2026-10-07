"use client";

import { CheckCircle2Icon, ImageIcon, MessageSquareIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApprovals } from "@/hooks/use-approvals";
import { APPROVAL_STATUS_LABEL } from "@/lib/approvals";
import { timeAgo } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { Approval, ApprovalFilter, Platform } from "@/types/api";

const PAGE = 30;
const TABS: { value: ApprovalFilter; label: string }[] = [
  { value: "pending", label: "Waiting for approval" },
  { value: "approved", label: "Approved" },
  { value: "changes_requested", label: "Changes needed" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export function ApprovalList() {
  const [status, setStatus] = useState<ApprovalFilter>("pending");
  const [platform, setPlatform] = useState<"" | Platform>("");
  const [limit, setLimit] = useState(PAGE);
  const approvals = useApprovals(status, platform, limit);
  const counts = approvals.data?.counts;

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Finished posts waiting for your decision. Approve them, or ask for changes."
      />
      {counts?.all === 0 && !platform ? (
        <Card>
          <CardContent className="grid justify-items-center gap-4 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted">
              <CheckCircle2Icon className="size-6 text-muted-foreground" />
            </span>
            <div className="grid max-w-md gap-1.5">
              <p className="text-lg font-medium">Nothing to review yet</p>
              <p className="text-sm text-muted-foreground">
                Posts arrive here when someone adds the design and submits the post.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
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
                    {counts && tab.value !== "all" && counts[tab.value] > 0 && (
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
              onChange={(v) => setPlatform(v === "all" ? "" : (v as Platform))}
              options={[{ value: "all", label: "Any platform" }, ...PLATFORM_OPTIONS]}
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
              <ul
                aria-label="Approvals"
                aria-busy={approvals.isPlaceholderData}
                className={cn("grid gap-3 transition-opacity", approvals.isPlaceholderData && "opacity-50")}
              >
                {approvals.data.items.map((a) => (
                  <ApprovalRow key={a.id} approval={a} />
                ))}
              </ul>
              {approvals.data.total > approvals.data.items.length && (
                <Button variant="outline" className="justify-self-center" onClick={() => setLimit((n) => n + PAGE)}>
                  Show more ({approvals.data.total - approvals.data.items.length} left)
                </Button>
              )}
            </>
          ) : (
            <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {status === "pending" ? "You're all caught up. Nothing is waiting for review." : "No submissions here."}
            </p>
          )}
        </div>
      )}
    </>
  );
}

function ApprovalRow({ approval: a }: { approval: Approval }) {
  return (
    <li className="relative flex items-center gap-4 rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40">
      <span className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-lg bg-muted">
        {a.preview_url ? (
          // Signed, short-lived URL; next/image can't optimize it.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={a.preview_url} alt="" className="size-full object-cover" loading="lazy" />
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
          <Tag tone={APPROVAL_STATUS_TONE[a.status]} dot>{APPROVAL_STATUS_LABEL[a.status]}</Tag>
          {a.round > 1 && <Tag tone="orange">Round {a.round}</Tag>}
        </div>
        <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span>
            Copy v{a.post_version}
            {a.creative_version != null && ` · creative v${a.creative_version}`}
          </span>
          <span>
            Submitted by {a.submitted_by?.name ?? a.submitted_by?.email ?? "someone"} {timeAgo(a.created_at)}
          </span>
          {a.reviewer && <span>Reviewed by {a.reviewer.name ?? a.reviewer.email}</span>}
          {a.comment_count > 0 && (
            <span className="inline-flex items-center gap-1">
              <MessageSquareIcon className="size-3" />
              {a.comment_count}
            </span>
          )}
        </p>
      </div>
    </li>
  );
}
