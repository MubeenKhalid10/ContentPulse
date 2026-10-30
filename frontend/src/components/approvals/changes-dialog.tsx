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
import type { ApprovalStage, ApprovalStatus, ChangeScope } from "@/types/api";

import { ScopePicker } from "./change-request";

const ALL_SCOPES: ChangeScope[] = ["copy", "design", "both"];

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
  const [scope, setScope] = useState<ChangeScope>("both");
  const approved = a.status === "approved";
  const mutation = approved ? reopen : changes;
  const copyStage = a.stage === "copy";
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
          disabled={mutation.isPending}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <p className="-mt-2 text-right text-xs tabular-nums text-muted-foreground">{note.length} / 4000</p>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Cancel</AlertDialogCancel>
          {/* A plain button: the dialog stays open if the request fails. */}
          <Button
            disabled={!note.trim() || mutation.isPending}
            pending={mutation.isPending}
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
