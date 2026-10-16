"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDeleteOrganization } from "@/hooks/use-organization";
import { api, errorMessage, setActiveOrgId } from "@/lib/api";
import { meQueryKey } from "@/lib/auth";
import type { Me } from "@/types/api";

/** Delete the whole workspace (admins only), behind a confirmation. */
export function DangerZone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const remove = useDeleteOrganization();
  const [open, setOpen] = useState(false);

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle>Danger zone</CardTitle>
        <CardDescription>
          Permanently remove this workspace and all of its trends, content,
          members, and settings.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          type="button"
          variant="destructive"
          onClick={() => setOpen(true)}
        >
          Delete workspace
        </Button>
      </CardContent>
      <AlertDialog
        open={open}
        onOpenChange={(next) => !remove.isPending && setOpen(next)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this workspace?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the workspace, its trends, gathered data,
              content, files, and team access. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: async () => {
                    setActiveOrgId(null);
                    queryClient.removeQueries({ queryKey: ["org"] });
                    toast.success("Workspace deleted");
                    // Land in another organization if there is one; only a user
                    // with none left needs to set a new one up.
                    try {
                      const me = await api<Me>("/auth/me");
                      queryClient.setQueryData(meQueryKey, me);
                      if (me.organization_id) {
                        setActiveOrgId(me.organization_id);
                        router.replace("/dashboard");
                        return;
                      }
                    } catch {
                      // Fall through to onboarding.
                    }
                    router.replace("/onboarding");
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              {remove.isPending ? "Deleting…" : "Delete workspace"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
