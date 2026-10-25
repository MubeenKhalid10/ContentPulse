"use client";

import { CheckIcon, RotateCcwIcon, Undo2Icon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
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

import { DeleteButton } from "@/components/shared/delete-button";
import { Button, buttonVariants } from "@/components/ui/button";
import { type TopicAction, useDeleteTopic, useTopicAction } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import { topicHref } from "@/lib/topics";
import type { Topic } from "@/types/api";

const MESSAGES: Record<TopicAction, (title: string) => string> = {
  shortlist: (t) => `Shortlisted “${t}”. Plan a post for it next.`,
  reject: (t) => `Rejected “${t}”`,
  review: (t) => `Removed “${t}” from the shortlist`,
  restore: (t) => `Restored “${t}” to the trends to review`,
  archive: (t) => `Archived “${t}”`,
};

/** Reject asks first: it hides the trend from the review list. */
function RejectButton({
  title,
  variant,
  disabled,
  onConfirm,
  ariaLabel,
}: {
  title: string;
  variant: "ghost" | "outline";
  disabled: boolean;
  onConfirm: () => void;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant={variant} disabled={disabled} aria-label={ariaLabel} onClick={() => setOpen(true)}>
        <XIcon />
        Reject
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{`Reject “${title}”?`}</AlertDialogTitle>
            <AlertDialogDescription>
              It leaves your list. You can find it under All trends on Find trends and restore it later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setOpen(false);
                onConfirm();
              }}
            >
              Reject
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/** Review decisions for a topic (spec §20). Compact = small buttons for list rows. */
export function TopicActions({ topic, compact = false }: { topic: Topic; compact?: boolean }) {
  const action = useTopicAction();
  const remove = useDeleteTopic();
  const router = useRouter();
  const pathname = usePathname();
  const run = (kind: TopicAction) =>
    action.mutate(
      { id: topic.id, action: kind },
      {
        onSuccess: () => toast.success(MESSAGES[kind](topic.title)),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  const busy = action.isPending || remove.isPending;
  const deleteButton = (
    <DeleteButton
      title={`Delete “${topic.title}”?`}
      description="This permanently deletes the topic, its post plans and its trend. Posts already written for it are kept. This can't be undone."
      pending={busy}
      onConfirm={() =>
        remove.mutate(topic.id, {
          onSuccess: () => {
            toast.success(`Deleted “${topic.title}”`);
            if (pathname.startsWith("/topics/")) router.push("/topics");
          },
          onError: (e) => toast.error(errorMessage(e)),
        })
      }
    />
  );

  if (topic.status === "archived") return deleteButton;
  if (topic.status === "rejected") {
    return (
      <div className="flex flex-wrap gap-1.5">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => run("restore")}>
          <RotateCcwIcon />
          Restore
        </Button>
        {deleteButton}
      </div>
    );
  }
  if (topic.status === "shortlisted") {
    if (compact)
      return (
        <div className="flex flex-wrap gap-1.5">
          <Link href={topicHref(topic, true)} className={buttonVariants({ size: "sm" })}>
            Plan post
          </Link>
          {deleteButton}
        </div>
      );
    return (
      <div className="flex flex-wrap gap-1.5">
        {topic.strategy_count === 0 ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run("review")}>
            <Undo2Icon />
            Remove from shortlist
          </Button>
        ) : (
          <span title="Not available while this trend has post plans.">
            <Button size="sm" variant="outline" disabled>
              <Undo2Icon />
              Remove from shortlist
            </Button>
          </span>
        )}
        <RejectButton title={topic.title} variant="ghost" disabled={busy} onConfirm={() => run("reject")} />
        {deleteButton}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button size="sm" variant="success" disabled={busy} aria-label={`Shortlist ${topic.title}`} onClick={() => run("shortlist")}>
        <CheckIcon />
        Shortlist
      </Button>
      <RejectButton
        title={topic.title}
        variant="ghost"
        disabled={busy}
        ariaLabel={`Reject ${topic.title}`}
        onConfirm={() => run("reject")}
      />
    </div>
  );
}
