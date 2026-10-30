"use client";

import { toast } from "sonner";

import { useAddPostComment, usePostComments } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";

import { CommentsView } from "./comments-card";

/** The review conversation on the post itself, for everyone who works on it. */
export function PostComments({ postId, currentRound }: { postId: string; currentRound: string }) {
  const can = useCan();
  const comments = usePostComments(postId);
  const add = useAddPostComment();
  return (
    <CommentsView
      comments={comments.data ?? []}
      loading={comments.isPending}
      currentRound={currentRound}
      canComment={can("approval.manage") || can("content.edit")}
      adding={add.isPending}
      onAdd={(body, done) =>
        add.mutate({ postId, body }, { onSuccess: done, onError: (e) => toast.error(errorMessage(e)) })
      }
    />
  );
}
