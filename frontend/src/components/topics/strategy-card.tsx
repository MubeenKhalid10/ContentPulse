"use client";

import { ArchiveIcon, ArrowRightIcon, PencilIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tag } from "@/components/shared/tag";
import { Button, buttonVariants } from "@/components/ui/button";
import { useGeneratePost } from "@/hooks/use-content";
import { useStrategyAction } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { POST_STATUS_TONE } from "@/lib/tones";
import { PLATFORM_LABEL, STRATEGY_SOURCE_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Post, Strategy } from "@/types/api";

const ROWS: [keyof Strategy, string][] = [
  ["objective", "Objective"],
  ["target_audience", "Audience"],
  ["content_angle", "Angle"],
  ["hook_direction", "Hook"],
  ["cta_direction", "Call to action"],
  ["tone", "Tone"],
  ["recommended_format", "Format"],
];

/** "Write post" from a plan; once written, the card leads to the post. */
export function WritePostButton({ strategy, size = "sm" }: { strategy: Strategy; size?: "sm" | "default" }) {
  const generate = useGeneratePost();
  const router = useRouter();
  return (
    <Button
      size={size}
      disabled={generate.isPending}
      onClick={() =>
        generate.mutate(strategy.id, {
          onSuccess: (post) => router.push(`/content/${post.id}`),
          onError: (e) => toast.error(errorMessage(e)),
        })
      }
    >
      <SparklesIcon />
      {generate.isPending ? "Starting…" : strategy.platform === "blog" ? "Write article" : "Write post"}
    </Button>
  );
}

export function StrategyCard({
  strategy: s,
  post,
  canManage,
  onEdit,
}: {
  strategy: Strategy;
  /** The post written from this plan, if any. */
  post?: Post;
  canManage: boolean;
  onEdit: () => void;
}) {
  const action = useStrategyAction();
  const canGenerate = useCan()("content.generate");
  const [confirmArchive, setConfirmArchive] = useState(false);
  const label = `${PLATFORM_LABEL[s.platform]} · ${s.post_type}`;
  const d = s.details ?? {};
  const seoRows: [string, string | null | undefined][] =
    s.platform === "blog"
      ? [
          ["SEO title", d.seo_title],
          ["Keywords", [d.primary_keyword, ...(d.secondary_keywords ?? [])].filter(Boolean).join(", ")],
          ["Search intent", d.search_intent],
          ["Length", d.target_word_count ? `About ${d.target_word_count.toLocaleString()} words` : null],
          ["Featured image", d.featured_image_direction],
        ]
      : [];
  const active = s.status !== "archived";

  return (
    <article
      aria-label={label}
      className={cn("grid gap-3 rounded-xl p-4 ring-1 ring-foreground/10", !active && "opacity-60")}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">{label}</h3>
        {post ? (
          <Tag tone={POST_STATUS_TONE[post.status]} dot>
            {POST_STATUS_LABEL[post.status]}
          </Tag>
        ) : !active ? (
          <Tag tone="neutral">Archived</Tag>
        ) : null}
        <span className="text-xs text-muted-foreground">{STRATEGY_SOURCE_LABEL[s.source]}</span>
        <div className="ml-auto flex flex-wrap gap-1.5">
          {canManage && active && (
            <Button size="sm" variant="ghost" onClick={onEdit}>
              <PencilIcon />
              Edit plan
            </Button>
          )}
          {post ? (
            <Link href={`/content/${post.id}`} className={buttonVariants({ size: "sm" })}>
              Open post
              <ArrowRightIcon />
            </Link>
          ) : (
            canManage && active && canGenerate && <WritePostButton strategy={s} />
          )}
          {canManage && active && (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Archive ${label}`}
              title="Archive plan"
              onClick={() => setConfirmArchive(true)}
            >
              <ArchiveIcon />
            </Button>
          )}
        </div>
      </header>
      <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[8rem_1fr]">
        {ROWS.filter(([key]) => s[key]).map(([key, title]) => (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{title}</dt>
            <dd>{s[key] as string}</dd>
          </div>
        ))}
        {seoRows
          .filter(([, value]) => value)
          .map(([title, value]) => (
            <div key={title} className="contents">
              <dt className="text-muted-foreground">{title}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        {!!d.outline?.length && (
          <div className="contents">
            <dt className="text-muted-foreground">Outline</dt>
            <dd>
              <ol className="list-decimal space-y-0.5 pl-5">
                {d.outline.map((heading, i) => (
                  <li key={i}>{heading}</li>
                ))}
              </ol>
            </dd>
          </div>
        )}
      </dl>
      {s.rationale && <p className="text-xs text-muted-foreground">Why: {s.rationale}</p>}

      <AlertDialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive this {PLATFORM_LABEL[s.platform]} plan?</AlertDialogTitle>
            <AlertDialogDescription>
              It stays visible on this topic for reference, but can no longer be edited or written from. Posts already
              written from it are not affected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={action.isPending}
              onClick={() => {
                action.mutate(
                  { topicId: s.topic_id, id: s.id, action: "archive" },
                  { onSuccess: () => toast.success("Plan archived"), onError: (e) => toast.error(errorMessage(e)) },
                );
                setConfirmArchive(false);
              }}
            >
              Archive
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </article>
  );
}
