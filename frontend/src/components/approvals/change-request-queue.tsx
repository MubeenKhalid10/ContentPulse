"use client";

import { AlertTriangleIcon, CheckCircle2Icon, RefreshCwIcon } from "lucide-react";
import Link from "next/link";

import { ListLoading } from "@/components/shared/loading";
import { PlatformTag } from "@/components/shared/tag";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useChangeRequests } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";

import { ChangeRequestActions, ChangeRequestTag } from "./change-request";

/** Creators' requests to reopen locked work, oldest first. */
export function ChangeRequestQueue() {
  const requests = useChangeRequests();
  if (requests.isPending) return <ListLoading label="Loading change requests…" rows={3} rowClassName="h-24" />;
  if (requests.isError) {
    return (
      <Alert variant="destructive">
        <AlertTriangleIcon />
        <AlertDescription className="grid gap-2">
          <span>Couldn&apos;t load change requests. {errorMessage(requests.error)}</span>
          <Button size="sm" variant="outline" className="w-fit" onClick={() => requests.refetch()}>
            <RefreshCwIcon />
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  if (!requests.data.items.length) {
    return (
      <Card>
        <CardContent className="grid justify-items-center gap-4 py-12 text-center">
          <span className="grid size-12 place-items-center rounded-full bg-muted">
            <CheckCircle2Icon className="size-6 text-muted-foreground" />
          </span>
          <div className="grid max-w-md gap-1.5">
            <p className="text-lg font-medium">No change requests</p>
            <p className="text-sm text-muted-foreground">
              When a creator asks to reopen locked content or a locked design, it appears here for you to decide.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <ul className="grid min-w-0 grid-cols-1 gap-3" aria-label="Change requests">
      {requests.data.items.map((r) => (
        <li key={r.id} className="grid gap-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <div className="flex flex-wrap items-center gap-2">
            <PlatformTag platform={r.post.platform} />
            <Link href={`/posts/${r.post.id}`} className="truncate font-medium underline-offset-4 hover:underline">
              {r.post.title ?? "Untitled post"}
            </Link>
            <ChangeRequestTag request={r} />
          </div>
          {r.topic_title && <p className="truncate text-xs font-medium text-muted-foreground">Topic: {r.topic_title}</p>}
          <p className="whitespace-pre-wrap text-sm">{r.note}</p>
          <p className="text-xs text-muted-foreground">
            Asked by {r.requested_by?.name ?? r.requested_by?.email ?? "someone"}{" "}
            <time dateTime={r.created_at} title={formatDateTime(r.created_at)}>
              {timeAgo(r.created_at)}
            </time>
          </p>
          <ChangeRequestActions request={r} />
        </li>
      ))}
    </ul>
  );
}
