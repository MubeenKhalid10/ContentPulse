"use client";

import { LoaderCircleIcon, UserRoundIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssignTask } from "@/hooks/use-design";
import { useMembers } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { roleLabel } from "@/lib/options";

/**
 * Shown right after an admin approves a post's content: the design task is
 * open, so pick who designs it. One click assigns; "Assign later" leaves it
 * open for any designer to take.
 */
export function AssignDesignerDialog({
  taskId,
  open,
  onDone,
}: {
  taskId: string | null;
  open: boolean;
  onDone: () => void;
}) {
  const members = useMembers();
  const assign = useAssignTask();
  const [assigningId, setAssigningId] = useState<string | null>(null);
  // Admins and creators can add designs (viewers cannot).
  const designers = (members.data ?? []).filter(
    (m) => m.status === "active" && (m.role === "admin" || m.role === "creator"),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Content approved. Who designs it?</DialogTitle>
          <DialogDescription>
            The design brief is ready. Pick the person who will add the design; they will see it
            under Add designs.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {members.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : designers.length ? (
            designers.map((m) => (
              <Button
                key={m.user_id}
                variant="outline"
                className="h-auto justify-start gap-3 py-2 text-left"
                disabled={assign.isPending || !taskId}
                onClick={() =>
                  taskId &&
                  (setAssigningId(m.user_id),
                  assign.mutate(
                    { id: taskId, assigneeId: m.user_id },
                    {
                      onSuccess: () => {
                        toast.success(`Design assigned to ${m.full_name ?? m.email}`);
                        onDone();
                      },
                      onError: (e) => toast.error(errorMessage(e)),
                      onSettled: () => setAssigningId(null),
                    },
                  ))
                }
              >
                {assigningId === m.user_id && assign.isPending ? (
                  <LoaderCircleIcon className="animate-spin" aria-hidden />
                ) : (
                  <UserRoundIcon aria-hidden />
                )}
                <span className="grid">
                  <span className="font-medium">{m.full_name ?? m.email}</span>
                  <span className="text-xs text-muted-foreground">{roleLabel(m.role)}</span>
                </span>
              </Button>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              No team members can add designs yet. Invite a creator under Team.
            </p>
          )}
        </div>
        <DialogFooter className="sm:items-center">
          <p className="text-xs text-muted-foreground sm:mr-auto">
            Assign later leaves the design open: any teammate who can add designs can take it from Add designs.
          </p>
          <Button variant="ghost" onClick={onDone} disabled={assign.isPending}>
            Assign later
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
