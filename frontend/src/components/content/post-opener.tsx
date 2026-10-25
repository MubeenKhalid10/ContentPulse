"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { BackLink } from "@/components/shared/back-link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { usePost } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { postStageHref, safeFrom, withFrom } from "@/lib/back";

/** Opens a post on the page for its current step: writing, design or approval. */
export function PostOpener({ id }: { id: string }) {
  const post = usePost(id);
  const router = useRouter();
  const from = safeFrom(useSearchParams().get("from"));
  const target = post.data && postStageHref(post.data);

  useEffect(() => {
    if (target) router.replace(from ? withFrom(target, from) : target);
  }, [target, from, router]);

  if (post.isError)
    return (
      <>
        <BackLink href="/content" label="Write posts" />
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(post.error)}</AlertDescription>
        </Alert>
      </>
    );
  return (
    <div role="status" aria-label="Opening post" className="grid gap-4">
      <p className="text-sm text-muted-foreground">Opening post…</p>
      <Skeleton className="h-10 w-2/3" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}
