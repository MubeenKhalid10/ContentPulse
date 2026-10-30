"use client";

import { RefreshCwIcon } from "lucide-react";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { PageLoading } from "@/components/shared/loading";
import { BackLink } from "@/components/shared/back-link";
import { PostProgress } from "@/components/shared/post-progress";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { SharePostButton } from "@/components/content/share-post-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useApproval } from "@/hooks/use-approvals";
import { ApiError, errorMessage } from "@/lib/api";
import { approvalStatusLabel } from "@/lib/approvals";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatDateTime, timeAgo } from "@/lib/format";

import { PreviewCard } from "./preview-card";
import { ChangeRequestNotice, ChangeRequestTag } from "./change-request";
import { DecisionCard } from "./decision-card";
import { CommentsCard } from "./comments-card";

export function ReviewPage({ id }: { id: string }) {
  const approval = useApproval(id);
  const back = <BackLink href="/approvals" label="Approvals" />;
  if (approval.isError) {
    const notFound = approval.error instanceof ApiError && approval.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription className="grid gap-2">
            <span>{notFound ? "This submission doesn't exist or isn't in your organization." : errorMessage(approval.error)}</span>
            {!notFound && (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => approval.refetch()}>
                <RefreshCwIcon />
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!approval.data) {
    return (
      <>
        {back}
        <PageLoading label="Loading review…" />
      </>
    );
  }
  const a = approval.data;

  return (
    <>
      {back}
      <div className="mb-6 grid gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{a.post.title ?? "Untitled post"}</h1>
          <PlatformTag platform={a.post.platform} />
          <Tag tone={APPROVAL_STATUS_TONE[a.status]} dot>{approvalStatusLabel(a.status, a.stage)}</Tag>
          {a.round > 1 && <Tag tone="orange">Round {a.round}</Tag>}
          <ChangeRequestTag request={a.change_request} />
          {a.post.status === "final" && (
            <div className="ml-auto">
              <SharePostButton title={a.post.title} platform={a.post.platform} copy={a.content} creative={a.creative} />
            </div>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Submitted by{" "}
          {a.submitted_by?.name ?? a.submitted_by?.email ?? "someone"}{" "}
          <time title={formatDateTime(a.created_at)}>{timeAgo(a.created_at)}</time> · Post: {POST_STATUS_LABEL[a.post.status]}
        </p>
      </div>

      <PostProgress status={a.post.status} />

      <ChangeRequestNotice request={a.change_request} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid min-w-0 grid-cols-1 content-start gap-6 lg:col-span-2">
          <PreviewCard approval={a} />
        </div>

        <div className="grid min-w-0 grid-cols-1 content-start gap-6">
          <DecisionCard approval={a} />
          <CommentsCard approval={a} />
        </div>
      </div>
    </>
  );
}
