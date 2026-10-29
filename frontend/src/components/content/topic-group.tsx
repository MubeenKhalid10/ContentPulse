"use client";

import { SendIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Post } from "@/types/api";

import { canSubmit, PostRow } from "./post-row";

interface TopicPosts {
  key: string;
  topic: Post["topic"];
  posts: Post[];
  updated_at: string;
}

/** Posts planned for the same topic stay together, newest group first. */
export function byTopic(posts: Post[]): TopicPosts[] {
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

export function Check({
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

export function TopicGroup({
  group,
  selectable,
  selected,
  onToggle,
  onSubmit,
  submitting,
  submittingIds,
}: {
  group: TopicPosts;
  selectable: boolean;
  selected: string[];
  onToggle: (ids: string[], on: boolean) => void;
  onSubmit: (ids: string[]) => void;
  submitting: boolean;
  /** The posts being sent right now, so only the button that sent them spins. */
  submittingIds?: string[];
}) {
  const ready = group.posts.filter(canSubmit);
  const sendingThese =
    !!submittingIds && submittingIds.length === ready.length && ready.every((p) => submittingIds.includes(p.id));
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
            pending={submitting && sendingThese}
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
