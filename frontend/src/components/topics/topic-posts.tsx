"use client";

import {
  ChevronRightIcon,
  CopyIcon,
  FileTextIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { useFromHere } from "@/components/shared/back-link";
import { DeleteButton } from "@/components/shared/delete-button";
import { ListLoading } from "@/components/shared/loading";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useDeletePost, useTopicPosts, useWriteAll } from "@/hooks/use-content";
import { useDeleteStrategy } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { postStatusLabel } from "@/lib/content";
import { formatDateTime, timeAgo } from "@/lib/format";
import type { Post, Strategy, TopicDetail } from "@/types/api";

import { SectionHeader } from "./platform-fit-card";
import { StrategyCard } from "./strategy-card";

const POST_DESCRIPTION =
  "This permanently deletes the post and everything attached to it: every version of the copy, its design task and files, and its approvals. The plan it came from is kept. This can't be undone.";
const DRAFT_DESCRIPTION =
  "This permanently deletes the draft post and the plan it came from, including every version of the copy, its design task and files. This can't be undone.";

/**
 * The trend's work in two lists. Draft posts: plans no post was written from yet,
 * plus posts still in draft. Generated posts: everything past draft.
 */
export function TopicPosts({
  topic,
  canManage,
  onEdit,
}: {
  topic: TopicDetail;
  canManage: boolean;
  onEdit: (strategy: Strategy) => void;
}) {
  const fromHere = useFromHere();
  const can = useCan();
  const canRead = can("content.read");
  const canGenerate = can("content.generate");
  const canWrite = canManage && topic.status === "shortlisted";
  const posts = useTopicPosts(topic.id);
  const writeAll = useWriteAll();
  // No count while loading: "0 posts" would read as the answer. People who
  // can't read posts get a 403 there and still see their plans as drafts.
  const items: Post[] | null = canRead
    ? posts.data && !posts.isPlaceholderData
      ? posts.data.items
      : null
    : [];
  const failed = canRead && posts.isError;
  // A post sent back for changes is back in draft, but it was already written and
  // reviewed: it stays under Generated posts with its "changes requested" status.
  const isDraft = (post: Post) => post.status === "draft" && !post.changes_scope;
  const draftPosts = items?.filter(isDraft) ?? [];
  const generated = items?.filter((post) => !isDraft(post)) ?? [];
  // A plan still waiting for its post is a draft; once written, its post takes its place.
  const plans = items
    ? topic.strategies.filter((s) => !items.some((p) => p.content_strategy_id === s.id))
    : [];
  const draftCount = plans.length + draftPosts.length;
  const loadError = (what: string) => (
    <Alert variant="destructive">
      <AlertDescription className="grid gap-2">
        <span>
          Couldn&apos;t load the {what}. {errorMessage(posts.error)}
        </span>
        <Button size="sm" variant="outline" className="w-fit" onClick={() => posts.refetch()}>
          <RefreshCwIcon />
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <SectionHeader
            icon={FileTextIcon}
            title="Draft posts"
            description="Plans waiting to be written, and posts still being prepared."
            badge={items && !failed ? `${draftCount} ${draftCount === 1 ? "draft" : "drafts"}` : undefined}
            actions={
              canWrite && canGenerate && plans.length > 1 ? (
                <Button
                  size="sm"
                  disabled={writeAll.isPending}
                  pending={writeAll.isPending}
                  onClick={() =>
                    writeAll.mutate(
                      plans.map((s) => s.id),
                      {
                        onError: (e) => toast.error(errorMessage(e)),
                        onSuccess: (r) =>
                          r.failed
                            ? toast.error(
                                `Started ${r.ok}, but ${r.failed} failed: ${errorMessage(r.error)}`,
                              )
                            : toast.success(
                                `Writing ${r.ok} posts. They move to Generated posts once written.`,
                              ),
                      },
                    )
                  }
                >
                  <SparklesIcon />
                  {writeAll.isPending ? "Starting…" : `Write all ${plans.length} posts`}
                </Button>
              ) : null
            }
          />
        </CardHeader>
        <CardContent className="grid gap-3">
          {failed ? (
            loadError("drafts")
          ) : !items ? (
            <ListLoading label="Loading drafts…" rows={1} rowClassName="h-32" />
          ) : draftCount ? (
            <>
              {plans.map((strategy) => (
                <StrategyCard
                  key={strategy.id}
                  strategy={strategy}
                  canManage={canWrite}
                  onEdit={() => onEdit(strategy)}
                />
              ))}
              {draftPosts.length > 0 && (
                <ul className="grid gap-2" aria-label="Draft posts">
                  {draftPosts.map((post) => (
                    <GeneratedPost
                      key={post.id}
                      post={post}
                      href={fromHere(`/posts/${post.id}`)}
                      deletePlan={
                        // Kept when another post was written from the same plan.
                        post.content_strategy_id &&
                        topic.strategies.some((s) => s.id === post.content_strategy_id) &&
                        !items.some(
                          (o) => o.id !== post.id && o.content_strategy_id === post.content_strategy_id,
                        )
                          ? { topicId: topic.id, id: post.content_strategy_id }
                          : undefined
                      }
                    />
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
              No drafts. Plans you create appear here until their post is written.
            </p>
          )}
        </CardContent>
      </Card>
      {canRead && (
        <Card>
          <CardHeader>
            <SectionHeader
              icon={CopyIcon}
              title="Generated posts"
              description="Posts written from your plans, with their current review status."
              badge={items && !failed ? `${generated.length} ${generated.length === 1 ? "post" : "posts"}` : undefined}
            />
          </CardHeader>
          <CardContent className="grid gap-3">
            {failed ? (
              loadError("generated posts")
            ) : !items ? (
              <ListLoading label="Loading generated posts…" rows={1} />
            ) : generated.length ? (
              <>
                <ul className="grid gap-2" aria-label="Generated posts">
                  {generated.map((p) => (
                    <GeneratedPost key={p.id} post={p} href={fromHere(`/posts/${p.id}`)} deletable={false} />
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  Select a post to open it in the studio, review its content, and continue the workflow
                  according to its current status.
                </p>
              </>
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                No generated posts yet. Write a post from one of your drafts to see it here.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** One generated post: platform and title, a preview, then its status, version and date. */
function GeneratedPost({
  post,
  href,
  deletePlan,
  deletable = true,
}: {
  post: Post;
  href: string;
  /** Draft posts: delete the plan with the post, so it doesn't come back as an unwritten plan. */
  deletePlan?: { topicId: string; id: string };
  /** Generated posts have no Delete here; they can still be deleted from their own pages. */
  deletable?: boolean;
}) {
  const isAdmin = useCan()("organization.write");
  const remove = useDeletePost();
  const removePlan = useDeleteStrategy();
  const deleting = remove.isPending || removePlan.isPending;
  const onDelete = async () => {
    try {
      // The plan goes first: deleting the post first would briefly list its plan as unwritten.
      if (deletePlan) await removePlan.mutateAsync(deletePlan);
      await remove.mutateAsync(post.id);
      toast.success("Post deleted");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
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
          {postStatusLabel(post)}
        </Tag>
        <span>
          {post.current_version ? `Version ${post.current_version} · ` : ""}
          <time dateTime={post.updated_at} title={formatDateTime(post.updated_at)}>
            Updated {timeAgo(post.updated_at)}
          </time>
        </span>
        {isAdmin && deletable && (
          <span className="relative z-10 ml-auto">
            <DeleteButton
              title={`Delete “${post.title ?? "this post"}”?`}
              description={deletePlan ? DRAFT_DESCRIPTION : POST_DESCRIPTION}
              pending={deleting}
              onConfirm={onDelete}
            />
          </span>
        )}
      </p>
    </li>
  );
}
