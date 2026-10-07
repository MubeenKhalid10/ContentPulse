"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckIcon, CopyIcon } from "lucide-react";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useInviteMember } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { ROLE_DESCRIPTIONS, ROLE_OPTIONS } from "@/lib/options";
import { inviteSchema } from "@/schemas/organization";
import type { InviteResponse, Member } from "@/types/api";

type Values = z.infer<typeof inviteSchema>;

export function InviteDialog({
  open,
  initial,
  onClose,
}: {
  open: boolean;
  initial?: { email: string; role: Member["role"] };
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        {open && <InviteFlow key={initial?.email ?? "new"} initial={initial} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function InviteFlow({
  initial,
  onClose,
}: {
  initial?: { email: string; role: Member["role"] };
  onClose: () => void;
}) {
  const invite = useInviteMember();
  const [result, setResult] = useState<InviteResponse | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(inviteSchema),
    defaultValues: initial ?? { email: "", role: "creator" },
  });
  const { errors } = form.formState;
  const role = useWatch({ control: form.control, name: "role" });

  if (result) return <InviteLink result={result} onClose={onClose} />;

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={form.handleSubmit((values) => invite.mutate(values, { onSuccess: setResult }))}
    >
      <DialogHeader>
        <DialogTitle>{initial ? "New invite link" : "Invite a teammate"}</DialogTitle>
        <DialogDescription>
          {initial
            ? "This replaces their previous link, which stops working."
            : "You'll get a link to send them. It works once and expires in 3 days."}
        </DialogDescription>
      </DialogHeader>
      {invite.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(invite.error)}</AlertDescription>
        </Alert>
      )}
      <FormField id="invite-email" label="Email" error={errors.email?.message}>
        <Input
          {...fieldAria("invite-email", errors.email?.message)}
          type="email"
          autoFocus={!initial}
          readOnly={!!initial}
          {...form.register("email")}
        />
      </FormField>
      <FormField id="invite-role" label="Role" hint={ROLE_DESCRIPTIONS[role]}>
        <Controller
          control={form.control}
          name="role"
          render={({ field }) => (
            <SimpleSelect id="invite-role" value={field.value} onChange={field.onChange} options={ROLE_OPTIONS} />
          )}
        />
      </FormField>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={invite.isPending}>
          {invite.isPending ? "Inviting…" : "Send invite"}
        </Button>
      </DialogFooter>
    </form>
  );
}

function InviteLink({ result, onClose }: { result: InviteResponse; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(result.invite_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the link stays selectable in the field.
    }
  }

  return (
    <div className="grid gap-5">
      <DialogHeader>
        <DialogTitle>{result.email_sent ? "Invitation sent" : "Invite ready"}</DialogTitle>
        <DialogDescription>
          {result.email_sent
            ? `We emailed an invitation to ${result.member.email}. You can also share this link yourself; it's shown only once.`
            : `Send this link to ${result.member.email}. For security it's shown only once.`}
        </DialogDescription>
      </DialogHeader>
      <div className="flex gap-2">
        <Input readOnly value={result.invite_url} aria-label="Invite link" onFocus={(e) => e.target.select()} className="font-mono text-xs" />
        <Button type="button" variant="outline" onClick={copy} aria-label="Copy invite link">
          {copied ? <CheckIcon className="text-primary" /> : <CopyIcon />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <DialogFooter>
        <Button onClick={onClose}>Done</Button>
      </DialogFooter>
    </div>
  );
}
