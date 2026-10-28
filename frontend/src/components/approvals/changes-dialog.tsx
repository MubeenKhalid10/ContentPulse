"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useReopen, useRequestChanges } from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ApprovalDetail } from "@/types/api";

type Scope = "copy" | "design" | "both";

const SCOPES: { value: Scope; label: string; help: string }[] = [
  { value: "copy", label: "Copy", help: "The writer edits the text. The design stays as it is." },
  { value: "design", label: "Design", help: "The designer revises. The copy stays locked." },
  { value: "both", label: "Both", help: "The text and the design both reopen." },
];

/** Request changes: on a pending submission, or (reopen) on approved work. */
export function ChangesDialog({
  approval: a,
  open,
  onOpenChange,
}: {
  approval: ApprovalDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const changes = useRequestChanges();
  const reopen = useReopen();
  const [note, setNote] = useState("");
  const [scope, setScope] = useState<Scope>("both");
  const approved = a.status === "approved";
  const mutation = approved ? reopen : changes;
  const copyStage = a.stage === "copy";
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>What should change?</AlertDialogTitle>
          <AlertDialogDescription>
            {copyStage
              ? approved
                ? "The approved copy goes back to its writer. Its design task is cancelled until the copy is approved again."
                : "The post goes back to its writer to revise the copy, then they submit it again."
              : "Only what you choose opens for editing. Everything else stays locked."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {!copyStage && (
          <div role="radiogroup" aria-label="What needs changes" className="grid gap-1.5">
            {SCOPES.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={scope === option.value}
                tabIndex={scope === option.value ? 0 : -1}
                onClick={() => setScope(option.value)}
                onKeyDown={(e) => {
                  const i = SCOPES.findIndex((o) => o.value === scope);
                  if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                    e.preventDefault();
                    setScope(SCOPES[(i + 1) % SCOPES.length].value);
                  } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                    e.preventDefault();
                    setScope(SCOPES[(i + SCOPES.length - 1) % SCOPES.length].value);
                  }
                }}
                className={cn(
                  "grid rounded-lg border px-3 py-2 text-left text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  scope === option.value ? "border-primary bg-primary/5" : "hover:bg-muted",
                )}
              >
                <span className="font-medium">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.help}</span>
              </button>
            ))}
          </div>
        )}
        <Textarea
          aria-label="What should change"
          rows={4}
          maxLength={4000}
          placeholder="e.g. Shorten the headline and use the brand blue on slide 3."
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <p className="-mt-2 text-right text-xs tabular-nums text-muted-foreground">{note.length} / 4000</p>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Cancel</AlertDialogCancel>
          {/* A plain button: the dialog stays open if the request fails. */}
          <Button
            disabled={!note.trim() || mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { id: a.id, comment: note.trim(), scope: copyStage ? "both" : scope },
                {
                  onSuccess: () => {
                    toast.success("Changes requested");
                    setNote("");
                    onOpenChange(false);
                  },
                  onError: (e: unknown) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            {mutation.isPending ? "Sending…" : "Request changes"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
