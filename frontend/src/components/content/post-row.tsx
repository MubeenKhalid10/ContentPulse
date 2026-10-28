"use client";

import { AlertTriangleIcon, LoaderCircleIcon, RefreshCwIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { Button } from "@/components/ui/button";
import { useDeletePost, useRegenerate } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatDateTime, timeAgo, timeOfDay } from "@/lib/format";
import { PLATFORM_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Post, PostStatus } from "@/types/api";

import { Check } from "./topic-group";

/** Ready to send for approval: written, not mid-generation, still a draft. */
export const canSubmit = (p: Post) =>
  p.status === "draft" &&
  p.current_version > 0 &&
  p.generation?.status !== "queued" &&
  p.generation?.status !== "running";

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
