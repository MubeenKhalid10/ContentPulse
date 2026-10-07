"use client";

import { CheckIcon, RotateCcwIcon, Undo2Icon, XIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { type TopicAction, useTopicAction } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import type { Topic } from "@/types/api";

const MESSAGES: Record<TopicAction, (title: string) => string> = {
  shortlist: (t) => `Shortlisted “${t}”. Plan a post for it next.`,
  reject: (t) => `Rejected “${t}”`,
  review: (t) => `Removed “${t}” from the shortlist`,
  restore: (t) => `Restored “${t}” to the topics to review`,
  archive: (t) => `Archived “${t}”`,
};

/** Review decisions for a topic (spec §20). Compact = small buttons for list rows. */
export function TopicActions({ topic, compact = false }: { topic: Topic; compact?: boolean }) {
  const action = useTopicAction();
  const run = (kind: TopicAction) =>
    action.mutate(
      { id: topic.id, action: kind },
      {
        onSuccess: () => toast.success(MESSAGES[kind](topic.title)),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  const busy = action.isPending;

  if (topic.status === "archived") return null;
  if (topic.status === "rejected") {
    return (
      <Button variant="outline" size="sm" disabled={busy} onClick={() => run("restore")}>
        <RotateCcwIcon />
        Restore
      </Button>
    );
  }
  if (topic.status === "shortlisted") {
    if (compact) return null;
    return (
      <div className="flex flex-wrap gap-1.5">
        {topic.strategy_count === 0 && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run("review")}>
            <Undo2Icon />
            Remove from shortlist
          </Button>
        )}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => run("reject")}>
          <XIcon />
          Reject
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button size="sm" disabled={busy} aria-label={`Shortlist ${topic.title}`} onClick={() => run("shortlist")}>
        <CheckIcon />
        Shortlist
      </Button>
      <Button size="sm" variant="outline" disabled={busy} aria-label={`Reject ${topic.title}`} onClick={() => run("reject")}>
        <XIcon />
        Reject
      </Button>
    </div>
  );
}
