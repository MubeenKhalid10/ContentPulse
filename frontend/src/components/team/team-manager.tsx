"use client";

import { MoreHorizontalIcon, UserPlusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { InviteDialog } from "@/components/team/invite-dialog";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMembers, useRemoveMember, useUpdateMember } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan, useMe } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { ROLE_DESCRIPTIONS, ROLE_OPTIONS, roleLabel } from "@/lib/options";
import type { Member } from "@/types/api";

export function TeamManager() {
  const members = useMembers();
  const canManage = useCan()("users.manage");
  const [inviteFor, setInviteFor] = useState<{ email: string; role: Member["role"] } | null | undefined>();
  const [removing, setRemoving] = useState<Member | undefined>();

  return (
    <>
      <PageHeader
        title="Team"
        description="Who can work in this organization, and what they can do."
        actions={
          canManage && (
            <Button onClick={() => setInviteFor(null)}>
              <UserPlusIcon />
              Invite
            </Button>
          )
        }
      />

      <Card className="py-0">
        {members.isPending ? (
          <CardContent className="grid gap-3 py-4">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Member</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Since</TableHead>
                {canManage && <TableHead className="w-12" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.data?.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  canManage={canManage}
                  onResend={() => setInviteFor({ email: member.email, role: member.role })}
                  onRemove={() => setRemoving(member)}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <dl className="mt-8 grid gap-4 sm:grid-cols-2">
        {ROLE_OPTIONS.map((role) => (
          <div key={role.value} className="grid gap-0.5">
            <dt className="text-sm font-medium">{role.label}</dt>
            <dd className="text-sm text-muted-foreground">{ROLE_DESCRIPTIONS[role.value]}</dd>
          </div>
        ))}
      </dl>

      <InviteDialog
        open={inviteFor !== undefined}
        initial={inviteFor ?? undefined}
        onClose={() => setInviteFor(undefined)}
      />
      <RemoveMemberDialog member={removing} onClose={() => setRemoving(undefined)} />
    </>
  );
}

function MemberRow({
  member,
  canManage,
  onResend,
  onRemove,
}: {
  member: Member;
  canManage: boolean;
  onResend: () => void;
  onRemove: () => void;
}) {
  const me = useMe();
  const update = useUpdateMember();
  const isSelf = me.data?.id === member.user_id;
  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <TableRow className={member.status === "disabled" ? "text-muted-foreground" : undefined}>
      <TableCell className="pl-4">
        <div className="font-medium">
          {member.full_name ?? member.email}
          {isSelf && <span className="ml-1.5 text-xs font-normal text-muted-foreground">(you)</span>}
        </div>
        {member.full_name && <div className="text-xs text-muted-foreground">{member.email}</div>}
      </TableCell>
      <TableCell className="min-w-40">
        {canManage ? (
          <SimpleSelect
            aria-label={`Role for ${member.email}`}
            value={member.role}
            options={ROLE_OPTIONS}
            disabled={update.isPending}
            onChange={(role) =>
              update.mutate(
                { memberId: member.id, role },
                { onSuccess: () => toast.success(`${member.email} is now ${roleLabel(role)}`), onError },
              )
            }
          />
        ) : (
          roleLabel(member.role)
        )}
      </TableCell>
      <TableCell>
        <StatusBadge member={member} />
      </TableCell>
      <TableCell className="hidden text-muted-foreground md:table-cell">
        {member.joined_at ? (
          <time dateTime={member.joined_at} title={formatDateTime(member.joined_at)}>
            {timeAgo(member.joined_at)}
          </time>
        ) : (
          "—"
        )}
      </TableCell>
      {canManage && (
        <TableCell>
          {!isSelf && (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${member.email}`} />}
              >
                <MoreHorizontalIcon />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                {member.status === "invited" && (
                  <DropdownMenuItem onClick={onResend}>New invite link</DropdownMenuItem>
                )}
                {member.status === "active" && (
                  <DropdownMenuItem
                    onClick={() => update.mutate({ memberId: member.id, status: "disabled" }, { onError })}
                  >
                    Disable access
                  </DropdownMenuItem>
                )}
                {member.status === "disabled" && (
                  <DropdownMenuItem
                    onClick={() => update.mutate({ memberId: member.id, status: "active" }, { onError })}
                  >
                    Restore access
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem variant="destructive" onClick={onRemove}>
                  Remove from organization
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </TableCell>
      )}
    </TableRow>
  );
}

function StatusBadge({ member }: { member: Member }) {
  if (member.status === "active") return <Badge variant="secondary">Active</Badge>;
  if (member.status === "disabled") return <Badge variant="outline">Disabled</Badge>;
  const expired = member.invite_expires_at && new Date(member.invite_expires_at) < new Date();
  return (
    <Badge variant="outline" className={expired ? "text-destructive" : "border-warning/50"}>
      {expired ? "Invite expired" : "Invited"}
    </Badge>
  );
}

function RemoveMemberDialog({ member, onClose }: { member: Member | undefined; onClose: () => void }) {
  const remove = useRemoveMember();
  return (
    <AlertDialog open={!!member} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {member?.full_name ?? member?.email}?</AlertDialogTitle>
          <AlertDialogDescription>
            They lose access immediately. Their past work and activity history are kept.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              member &&
              remove.mutate(member.id, {
                onSuccess: () => {
                  toast.success("Member removed");
                  onClose();
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Remove
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
