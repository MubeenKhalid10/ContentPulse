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
import { Input } from "@/components/ui/input";
import { useDeleteOrganization, useOrganization } from "@/hooks/use-organization";
import { api, errorMessage, setActiveOrgId } from "@/lib/api";
import { meQueryKey } from "@/lib/auth";
import type { Me } from "@/types/api";

/** Delete the whole workspace (admins only), behind a confirmation. */
export function DangerZone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const remove = useDeleteOrganization();
  const org = useOrganization();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const orgName = org.data?.name ?? "";
  const confirmed = !!orgName && typed.trim() === orgName;

  return (
    <Card className="border-destructive/50">
      <CardHeader>
        <CardTitle className="text-destructive">Danger zone</CardTitle>
        <CardDescription>
          Permanently remove this workspace and all of its trends, content,
          members, and settings. Only admins can do this, and it cannot be
          undone.
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
        onOpenChange={(next) => {
          if (remove.isPending) return;
          setOpen(next);
          if (!next) setTyped("");
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this workspace?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the workspace, its trends, gathered data,
              content, files, and team access. Every member loses access
              immediately. This action cannot be undone, so download anything
              you need first.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {orgName && (
            <div className="grid gap-1.5">
              <label htmlFor="confirm-delete-name" className="text-sm">
                Type <span className="font-semibold">{orgName}</span> to
                confirm.
              </label>
              <Input
                id="confirm-delete-name"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                autoComplete="off"
                disabled={remove.isPending}
              />
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending || !confirmed}
              pending={remove.isPending}
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
