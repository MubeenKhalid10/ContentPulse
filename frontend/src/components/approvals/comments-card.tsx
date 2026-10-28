"use client";

import { MessageSquarePlusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Tag } from "@/components/shared/tag";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useAddComment } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { COMMENT_KIND_LABEL } from "@/lib/approvals";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApprovalDetail } from "@/types/api";

export function CommentsCard({ approval: a }: { approval: ApprovalDetail }) {
  const can = useCan();
  const canComment = can("approval.manage") || can("content.edit");
  const add = useAddComment();
  const [body, setBody] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Comments</CardTitle>
        <CardDescription>Every round of this post. Each comment shows the versions it refers to.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {a.comments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No comments yet.</p>
        ) : (
          <ol className="grid gap-3" aria-label="Comments">
            {a.comments.map((c) => (
              <li key={c.id} className={cn("grid gap-1 rounded-lg p-3 text-sm", c.approval_request_id === a.id ? "bg-muted/60" : "bg-muted/30")}>
                <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{c.author?.name ?? c.author?.email ?? "Someone"}</span>
                  {COMMENT_KIND_LABEL[c.kind]}
                  {c.approval_request_id !== a.id && <Tag tone="neutral">Previous round</Tag>}
                  <time className="ml-auto" title={formatDateTime(c.created_at)}>
                    {timeAgo(c.created_at)}
                  </time>
                </span>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ol>
        )}
        {canComment && (
          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!body.trim()) return;
              add.mutate(
                { id: a.id, body: body.trim() },
                { onSuccess: () => setBody(""), onError: (err) => toast.error(errorMessage(err)) },
              );
            }}
          >
            <Textarea aria-label="Add a comment" rows={2} maxLength={4000} placeholder="Add a comment" value={body} onChange={(e) => setBody(e.target.value)} />
            <p className="text-right text-xs tabular-nums text-muted-foreground">{body.length} / 4000</p>
            <Button type="submit" size="sm" variant="outline" className="justify-self-end" disabled={!body.trim() || add.isPending}>
              <MessageSquarePlusIcon />
              {add.isPending ? "Posting…" : "Comment"}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
