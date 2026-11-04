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
import { ApiError, errorMessage } from "@/lib/api";
import type { ApprovalStage, ApprovalStatus, ChangeScope } from "@/types/api";

import { ScopePicker } from "./change-request";

const ALL_SCOPES: ChangeScope[] = ["copy", "design"];

/** Request changes: on a pending submission, or (reopen) on approved work. */
export function ChangesDialog({
  approval: a,
  open,
  onOpenChange,
}: {
  approval: { id: string; status: ApprovalStatus; stage: ApprovalStage };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const changes = useRequestChanges();
  const reopen = useReopen();
  const [note, setNote] = useState("");
  const [scope, setScope] = useState<ChangeScope>("design");
  const approved = a.status === "approved";
  const mutation = approved ? reopen : changes;
  const copyStage = a.stage === "copy";
  const MIN_NOTE = 10;
  const used = note.trim().length;
  const tooShort = used < MIN_NOTE;
  return (
    <AlertDialog open={open} onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}>
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
          <ScopePicker allowed={ALL_SCOPES} value={scope} onChange={setScope} disabled={mutation.isPending} />
        )}
        <Textarea
          aria-label="What should change"
          rows={4}
          maxLength={4000}
          placeholder="e.g. Shorten the headline and use the brand blue on slide 3."
          aria-describedby={tooShort ? "changes-min-length" : undefined}
          disabled={mutation.isPending}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <p className="-mt-2 text-right text-xs tabular-nums text-muted-foreground">{note.length} / 4000</p>
        {tooShort && (
          <p
            id="changes-min-length"
            role="status"
            className="rounded-md border border-amber-300 bg-amber-100 px-3 py-2 text-sm font-medium text-amber-950 dark:border-amber-500/50 dark:bg-amber-500/15 dark:text-amber-100"
          >
            Please use at least {MIN_NOTE} characters to request changes (you are currently using {used}).
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Cancel</AlertDialogCancel>
          {/* A plain button: the dialog stays open if the request fails. */}
          <Button
            disabled={tooShort || mutation.isPending}
            pending={mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { id: a.id, comment: note.trim(), scope: copyStage ? "copy" : scope },
                {
                  onSuccess: () => {
                    toast.success("Changes requested");
                    setNote("");
                    onOpenChange(false);
                  },
                  onError: (e: unknown) => {
                    toast.error(errorMessage(e));
                    // Already decided elsewhere: the lists have reloaded, so close and look.
                    if (e instanceof ApiError && e.status === 409) onOpenChange(false);
                  },
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
