"use client";

import { AlertTriangleIcon, DownloadIcon } from "lucide-react";

import { SignedImage } from "@/components/shared/signed-image";
import { ArticlePreview } from "@/components/content/article-preview";
import { SocialPostPreview } from "@/components/content/social-preview";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fullText } from "@/lib/content";
import { cleanNote } from "@/lib/format";
import type { ApprovalDetail } from "@/types/api";

/** Copy and design in one frame, the way the platform will show them. */
export function PreviewCard({ approval: a }: { approval: ApprovalDetail }) {
  const files = a.creative?.files ?? [];
  const text = a.content ? fullText(a.content.hook, a.content.body, a.content.cta, a.content.hashtags) : "";
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start gap-2">
        <div className="grid flex-1 gap-1">
          <CardTitle>How it will look</CardTitle>
          {a.creative?.note && <CardDescription>“{cleanNote(a.creative.note)}”</CardDescription>}
        </div>
      </CardHeader>
      <CardContent className="grid min-w-0 gap-4">
        {a.copy_changed_since && (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertDescription>
              The copy has changed since this submission (now version {a.post.current_version}). Check that the design still matches.
            </AlertDescription>
          </Alert>
        )}
        {a.post.platform === "blog" ? (
          <div className="mx-auto grid w-full max-w-2xl gap-3">
            {files[0]?.file_type.startsWith("image/") && (
              // Signed, short-lived URLs: next/image can't optimize them.
              <SignedImage src={files[0].url} alt="Featured image" className="aspect-[1.91/1] w-full rounded-xl border object-cover" />
            )}
            {a.content && (
              <ArticlePreview
                title={a.post.title}
                seo={a.content.meta.blog}
                intro={a.content.hook}
                body={a.content.body}
                cta={a.content.cta}
              />
            )}
          </div>
        ) : (
          <SocialPostPreview platform={a.post.platform} text={text} files={files} />
        )}
        {(a.content?.meta.warnings?.length ?? 0) > 0 && (
          <ul className="grid gap-1.5 text-sm text-amber-700 dark:text-amber-400" aria-label="Brand and platform checks">
            {a.content!.meta.warnings!.map((w) => (
              <li key={w} className="flex items-start gap-1.5">
                <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}
        {files.length > 0 && (
          <p className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            Design files:
            {files.map((f) => (
              <a key={f.id} href={f.download_url} className="inline-flex max-w-56 items-center gap-1 underline-offset-4 hover:underline">
                <DownloadIcon className="size-3 shrink-0" />
                <span className="truncate">{f.file_name}</span>
              </a>
            ))}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
