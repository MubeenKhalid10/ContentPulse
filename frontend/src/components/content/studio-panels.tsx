"use client";

import { CheckCircle2Icon, ExternalLinkIcon, HistoryIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { PostRow } from "@/components/content/content-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ArticlePreview } from "@/components/content/article-preview";
import { SocialPostPreview } from "@/components/content/social-preview";
import { usePostVersions, useRestoreVersion } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { DESIGN_FORMAT_LABEL, fullText } from "@/lib/content";
import { formatDateTime, timeAgo } from "@/lib/format";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { PostDetail, PostVersion } from "@/types/api";

export function ChecksPanel({ post }: { post: PostDetail }) {
  const v = post.current;
  if (!v) return null;
  const warnings = v.meta.warnings ?? [];
  const corrections = v.meta.corrections ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Checks</CardTitle>
        <CardDescription>Brand vocabulary and {PLATFORM_LABEL[post.platform]} playbook, for the saved version.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        {warnings.length === 0 ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <CheckCircle2Icon className="size-4 text-primary" />
            No issues found.
          </p>
        ) : (
          <ul className="grid gap-1.5" aria-label="Warnings">
            {warnings.map((w) => (
              <li key={w} className="flex items-start gap-2">
                <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                {w}
              </li>
            ))}
          </ul>
        )}
        {corrections.length > 0 && (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Automatic fixes to the AI output ({corrections.length})</summary>
            <ul className="mt-1 list-disc pl-5">
              {corrections.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

export function PreviewPanel({ post }: { post: PostDetail }) {
  const v = post.current;
  if (!v) return null;
  const text = fullText(v.hook, v.body, v.cta, v.hashtags);
  if (post.platform === "blog") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>Version {v.version_number} as the article would read on your website.</CardDescription>
        </CardHeader>
        <CardContent className="max-h-[36rem] overflow-y-auto">
          <ArticlePreview title={post.title} seo={v.meta.blog} intro={v.hook} body={v.body} cta={v.cta} />
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preview</CardTitle>
        <CardDescription>
          Version {v.version_number} as it would read on {PLATFORM_LABEL[post.platform]}
          {v.meta.design_format ? `, with a ${DESIGN_FORMAT_LABEL[v.meta.design_format].toLowerCase()}` : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <SocialPostPreview platform={post.platform} text={text} files={post.creatives[0]?.files ?? []} />
      </CardContent>
    </Card>
  );
}

export function SourcesPanel({ post }: { post: PostDetail }) {
  const passages = post.current?.meta.passages ?? [];
  const cited = new Set(post.current?.meta.evidence ?? []);
  if (!post.current) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Grounding</CardTitle>
        <CardDescription>
          {passages.length
            ? "Knowledge passages given to the writer. Claims about your organization must come from these."
            : "No knowledge passages matched this topic, so the post should make no specific claims about your organization."}
        </CardDescription>
      </CardHeader>
      {passages.length > 0 && (
        <CardContent>
          <ul className="grid gap-2">
            {passages.map((p) => (
              <li key={p.ref} className="grid gap-0.5 rounded-lg border p-2.5 text-xs">
                <span className="flex items-center gap-2">
                  <Badge variant={cited.has(p.ref) ? "default" : "outline"}>{p.ref}</Badge>
                  <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-4 hover:underline">
                    {p.title ?? p.url}
                    <ExternalLinkIcon className="size-3 text-muted-foreground" />
                  </a>
                  {cited.has(p.ref) && <span className="text-muted-foreground">cited</span>}
                </span>
                <span className="line-clamp-2 text-muted-foreground">{p.excerpt}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  );
}

export function StrategyPanel({ post }: { post: PostDetail }) {
  const s = post.strategy;
  if (!s) return null;
  const rows: [string, string | null][] = [
    ["Post type", s.post_type],
    ["Objective", s.objective],
    ["Angle", s.content_angle],
    ["Audience", s.target_audience],
    [s.platform === "blog" ? "Introduction" : "Hook", s.hook_direction],
    ["Call to action", s.cta_direction],
    ...((s.platform === "blog"
      ? [
          ["Primary keyword", s.details?.primary_keyword ?? null],
          ["Search intent", s.details?.search_intent ?? null],
          ["Outline", s.details?.outline?.join(" · ") || null],
          ["Target length", s.details?.target_word_count ? `About ${s.details.target_word_count.toLocaleString()} words` : null],
        ]
      : []) as [string, string | null][]),
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Plan</CardTitle>
        {post.topic && (
          <CardDescription>
            For{" "}
            <Link href={`/topics/${post.topic.id}`} className="underline underline-offset-4">
              {post.topic.title}
            </Link>
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <dl className="grid gap-2 text-sm">
          {rows
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label} className="grid gap-0.5">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </CardContent>
    </Card>
  );
}

export function VariantsPanel({ post }: { post: PostDetail }) {
  if (!post.variants.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Variants</CardTitle>
        <CardDescription>Other versions written from the same plan, to compare and pick from.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2" aria-label="Variants">
          {post.variants.map((v) => (
            <PostRow key={v.id} post={v} compact />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function VersionsPanel({ post, canEdit }: { post: PostDetail; canEdit: boolean }) {
  const versions = usePostVersions(post.id, post.current_version);
  const [viewing, setViewing] = useState<PostVersion | null>(null);
  if (!post.current_version) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HistoryIcon className="size-4" />
          Version history
        </CardTitle>
        <CardDescription>Every version is kept. Restoring one adds it as a new version.</CardDescription>
      </CardHeader>
      <CardContent>
        {versions.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <ol className="grid gap-1" aria-label="Versions">
            {versions.data?.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => setViewing(v)}
                  className="grid w-full gap-0.5 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted"
                >
                  <span className="flex items-center gap-2">
                    <span className="font-medium">v{v.version_number}</span>
                    {v.version_number === post.current_version && <Badge>Current</Badge>}
                    <span className="text-xs text-muted-foreground">{v.source === "ai" ? (v.meta.engine === "template" ? "Template" : "AI") : "Edited"}</span>
                    <time className="ml-auto text-xs text-muted-foreground" title={formatDateTime(v.created_at)}>
                      {timeAgo(v.created_at)}
                    </time>
                  </span>
                  {v.change_note && <span className="text-xs text-muted-foreground">{v.change_note}</span>}
                </button>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
      <VersionDialog post={post} version={viewing} canRestore={canEdit && post.editable} onClose={() => setViewing(null)} />
    </Card>
  );
}

function VersionDialog({
  post,
  version,
  canRestore,
  onClose,
}: {
  post: PostDetail;
  version: PostVersion | null;
  canRestore: boolean;
  onClose: () => void;
}) {
  const restore = useRestoreVersion();
  const isCurrent = version?.version_number === post.current_version;
  return (
    <Dialog open={!!version} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        {version && (
          <>
            <DialogHeader>
              <DialogTitle>Version {version.version_number}</DialogTitle>
              <DialogDescription>
                {version.change_note ?? "Saved"} · {formatDateTime(version.created_at)}
              </DialogDescription>
            </DialogHeader>
            <p className="rounded-lg bg-muted/50 p-3 text-sm whitespace-pre-wrap">
              {fullText(version.hook, version.body, version.cta, version.hashtags)}
            </p>
            {version.meta.instructions && (
              <p className="text-xs text-muted-foreground">Instructions: {version.meta.instructions}</p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
              {canRestore && !isCurrent && (
                <Button
                  disabled={restore.isPending}
                  onClick={() =>
                    restore.mutate(
                      { id: post.id, number: version.version_number, base: post.current_version },
                      {
                        onSuccess: (p) => {
                          toast.success(`Restored as version ${p.current_version}`);
                          onClose();
                        },
                        onError: (e) => toast.error(errorMessage(e)),
                      },
                    )
                  }
                >
                  Restore this version
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
