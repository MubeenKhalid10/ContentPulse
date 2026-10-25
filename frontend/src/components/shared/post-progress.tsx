"use client";

import { CheckIcon } from "lucide-react";

import { useCan } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { PostStatus } from "@/types/api";

const STAGES = [
  "Plan",
  "Write",
  "Content approval",
  "Design",
  "Design approval",
  "Ready to publish",
] as const;

/** Which stage the post is in (index into STAGES) and who acts next. */
type Actor = "writer" | "admin" | "designer";
const POSITION: Partial<Record<PostStatus, { at: number; next: string; actor?: Actor }>> = {
  draft: { at: 1, next: "the writer", actor: "writer" },
  content_review: { at: 2, next: "an admin", actor: "admin" },
  design_pending: { at: 3, next: "a designer", actor: "designer" },
  design_in_progress: { at: 3, next: "a designer", actor: "designer" },
  design_uploaded: { at: 3, next: "a designer, who submits it", actor: "designer" },
  changes_requested: { at: 3, next: "a designer (changes requested)", actor: "designer" },
  pending_approval: { at: 4, next: "an admin", actor: "admin" },
  approved: { at: 5, next: "an admin, who marks it ready", actor: "admin" },
  final: { at: 6, next: "" },
};

/**
 * Where a post is on its way to "Ready to publish", and who acts next. The
 * stages are joined by a line: finished stages and the line behind them are
 * green, the current stage is solid, what is still ahead is grey.
 */
export function PostProgress({ status, className }: { status: PostStatus; className?: string }) {
  const can = useCan();
  const position = POSITION[status];
  if (!position) {
    if (status !== "rejected" && status !== "archived") return null;
    return (
      <p className={cn("mb-6 rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground", className)}>
        {status === "rejected"
          ? "This post was rejected and has left the workflow."
          : "This post is archived and has left the workflow."}
      </p>
    );
  }
  const { at, next, actor } = position;
  const yourTurn =
    actor === "admin" ? can("approval.manage") : actor === "writer" || actor === "designer" ? can("content.edit") : false;
  return (
    <nav aria-label="Post progress" className={cn("mb-6 grid gap-2.5", className)}>
      <p className="text-xs font-medium text-muted-foreground sm:hidden">
        Step {Math.min(at + 1, STAGES.length)} of {STAGES.length}: {STAGES[Math.min(at, STAGES.length - 1)]}
      </p>
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-6 sm:gap-x-6">
        {STAGES.map((stage, i) => {
          const done = i < at;
          const current = i === at && at < STAGES.length;
          const last = i === STAGES.length - 1;
          return (
            <li key={stage} aria-current={current ? "step" : undefined} className="relative flex">
              <span
                className={cn(
                  "flex min-h-9 w-full items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-center text-xs leading-tight font-medium",
                  done &&
                    "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200",
                  current &&
                    "border-primary bg-primary text-primary-foreground shadow-sm ring-4 ring-primary/15",
                  !done && !current && "border-border bg-muted/40 text-muted-foreground",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "grid size-4 shrink-0 place-items-center rounded-full text-[10px] font-semibold tabular-nums",
                    done && "bg-emerald-600 text-white dark:bg-emerald-500 dark:text-emerald-950",
                    current && "bg-primary-foreground text-primary",
                    !done && !current && "bg-border text-muted-foreground",
                  )}
                >
                  {done ? <CheckIcon className="size-2.5" strokeWidth={3} /> : i + 1}
                </span>
                {stage}
                <span className="sr-only">{done ? " (done)" : current ? " (current)" : " (later)"}</span>
              </span>
              {/* The line fills the gap to the next box: same length everywhere, on one level. */}
              {!last && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute top-1/2 left-full hidden h-0.5 w-6 -translate-y-1/2 sm:block",
                    i < at ? "bg-emerald-500" : "bg-border",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
      {next && (
        <p className="text-sm text-muted-foreground">
          {yourTurn ? (
            <>
              <span className="font-medium text-foreground">Your turn.</span> Next step is with {next}.
            </>
          ) : (
            <>
              Next step is with <span className="font-medium text-foreground">{next}</span>.
            </>
          )}
        </p>
      )}
    </nav>
  );
}
