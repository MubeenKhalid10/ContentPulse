"use client";

import { ChevronRightIcon, CopyIcon, LoaderCircleIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { useFromHere } from "@/components/shared/back-link";
import { DeleteButton } from "@/components/shared/delete-button";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useDeletePost, usePosts } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatDateTime, timeAgo } from "@/lib/format";
import type { Post } from "@/types/api";

import { SectionHeader } from "./platform-fit-card";

const POST_DESCRIPTION =
  "This permanently deletes the post and everything attached to it: every version of the copy, its design task and files, and its approvals. The plan it came from is kept. This can't be undone.";

export function TopicPosts({ topicId }: { topicId: string }) {
  const fromHere = useFromHere();
  const posts = usePosts({ status: "all", platform: "", topicId, q: "" }, 50);
  if (!posts.data) return null;
  const items = posts.data.items;
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          icon={CopyIcon}
          title="Generated posts"
          description="Posts created from your plans, with their current review status."
          badge={`${items.length} ${items.length === 1 ? "post" : "posts"}`}
        />
      </CardHeader>
      <CardContent className="grid gap-3">
        {items.length ? (
          <>
            <ul className="grid gap-2" aria-label="Generated posts">
              {items.map((p) => (
                <GeneratedPost key={p.id} post={p} href={fromHere(`/posts/${p.id}`)} />
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Select a post to open it in the studio, review its content, and continue the workflow
              according to its current status.
            </p>
          </>
        ) : (
          <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            No posts yet. Posts appear here once you generate one from a plan.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** One generated post: platform and title, a preview, then its status, version and date. */
function GeneratedPost({ post, href }: { post: Post; href: string }) {
  const isAdmin = useCan()("organization.write");
  const remove = useDeletePost();
  const busy = post.generation?.status === "queued" || post.generation?.status === "running";
  const failed = post.generation?.status === "failed" && !post.current_version;
  return (
    <li className="relative grid gap-1.5 rounded-lg border p-3 transition-colors hover:bg-muted/40">
      <div className="flex items-center gap-2">
        <PlatformTag platform={post.platform} />
        <Link
          href={href}
          className="min-w-0 flex-1 truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {post.title ?? "Untitled post"}
        </Link>
        {post.variant_of_id && <Tag tone="neutral">Variant</Tag>}
        <ChevronRightIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      </div>
      {busy ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <LoaderCircleIcon className="size-4 animate-spin text-primary" />
          Writing…
        </p>
      ) : failed ? (
        <p className="text-sm text-destructive">Writing failed. Open the post to try again.</p>
      ) : (
        post.hook && <p className="line-clamp-1 text-sm text-muted-foreground">{post.hook}</p>
      )}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <Tag tone={POST_STATUS_TONE[post.status]} dot className="h-6 px-2.5 text-xs font-semibold">
          {POST_STATUS_LABEL[post.status]}
        </Tag>
        <span>
          {post.current_version ? `Version ${post.current_version} · ` : ""}
          <time dateTime={post.updated_at} title={formatDateTime(post.updated_at)}>
            Updated {timeAgo(post.updated_at)}
          </time>
        </span>
        {isAdmin && (
          <span className="relative z-10 ml-auto">
            <DeleteButton
              title={`Delete “${post.title ?? "this post"}”?`}
              description={POST_DESCRIPTION}
              pending={remove.isPending}
              onConfirm={() =>
                remove.mutate(post.id, {
                  onSuccess: () => toast.success("Post deleted"),
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            />
          </span>
        )}
      </p>
    </li>
  );
}
