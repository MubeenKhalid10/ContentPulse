"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CheckEmail } from "@/components/auth/check-email";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, errorMessage, setActiveOrgId } from "@/lib/api";
import { meQueryKey, useAuthConfig } from "@/lib/auth";
import { roleLabel } from "@/lib/options";
import { authRedirect, getSupabase, supabaseErrorMessage } from "@/lib/supabase";
import { acceptInviteSchema } from "@/schemas/auth";
import type { InvitePreview, Me } from "@/types/api";

export function AcceptInvite({ token }: { token: string }) {
  const preview = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<InvitePreview>(`/auth/invites/${encodeURIComponent(token)}`),
  });
  const authConfig = useAuthConfig();

  if (preview.isPending || authConfig.isPending) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-full" />
        </CardHeader>
        <CardContent className="grid gap-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (preview.isError) {
    const expired = preview.error instanceof ApiError && preview.error.status === 410;
    return (
      <Alert variant="destructive">
        <AlertTitle>{expired ? "This invitation has expired" : "Invitation not found"}</AlertTitle>
        <AlertDescription>
          {expired
            ? "Ask an admin of the organization to send you a new invitation."
            : "The link may have already been used. Ask an admin to invite you again, or "}
          {!expired && (
            <Link href="/login" className="underline underline-offset-4">
              sign in
            </Link>
          )}
          {!expired && "."}
        </AlertDescription>
      </Alert>
    );
  }

  if (authConfig.data?.provider === "supabase") return <SupabaseAcceptForm token={token} invite={preview.data} />;
  return <AcceptForm token={token} invite={preview.data} />;
}

function useAcceptInvite(token: string) {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: { full_name: string; password?: string }) =>
      api<Me>("/auth/invites/accept", { method: "POST", body: { token, ...values } }),
    onSuccess: (me) => {
      setActiveOrgId(me.organization_id);
      queryClient.setQueryData(meQueryKey, me);
      router.replace("/dashboard");
    },
  });
}

function InviteHeader({ invite }: { invite: InvitePreview }) {
  return (
    <CardHeader>
      <CardTitle role="heading" aria-level={1} className="text-xl">Join {invite.organization_name}</CardTitle>
      <CardDescription>
        You&apos;ve been invited as <strong className="text-foreground">{roleLabel(invite.role)}</strong>{" "}
        with <span className="text-foreground">{invite.email}</span>.
      </CardDescription>
    </CardHeader>
  );
}

const nameOnlySchema = z.object({ full_name: z.string().trim().min(1, "Enter your name.").max(200) });
const SESSION_EMAIL_KEY = ["supabase", "session-email"] as const;

/**
 * Supabase mode: the invitee proves who they are with a Supabase session for
 * the invited email (signing up or in right here), then accepts.
 */
function SupabaseAcceptForm({ token, invite }: { token: string; invite: InvitePreview }) {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: SESSION_EMAIL_KEY,
    queryFn: async () => {
      const supabase = await getSupabase();
      if (!supabase) return null;
      const { data } = await supabase.auth.getSession();
      return data.session?.user.email?.toLowerCase() ?? null;
    },
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: SESSION_EMAIL_KEY });

  if (session.isPending) return null;
  const signedInAs = session.data ?? null;
  if (signedInAs === invite.email.toLowerCase()) return <ConfirmJoin token={token} invite={invite} />;
  if (!signedInAs) return <SupabaseIdentityForm token={token} invite={invite} onSignedIn={refresh} />;

  const signOut = async () => {
    const supabase = await getSupabase();
    await supabase?.auth.signOut();
    await refresh();
  };
  return (
    <Alert>
      <AlertTitle>You&apos;re signed in as {signedInAs}</AlertTitle>
      <AlertDescription>
        This invitation to {invite.organization_name} is for {invite.email}.{" "}
        <button type="button" onClick={signOut} className="font-medium text-foreground underline underline-offset-4">
          Sign out
        </button>{" "}
        to continue with that address.
      </AlertDescription>
    </Alert>
  );
}

function ConfirmJoin({ token, invite }: { token: string; invite: InvitePreview }) {
  const accept = useAcceptInvite(token);
  const form = useForm<z.infer<typeof nameOnlySchema>>({
    resolver: zodResolver(nameOnlySchema),
    defaultValues: { full_name: "" },
  });
  const { errors } = form.formState;
  return (
    <Card>
      <InviteHeader invite={invite} />
      <CardContent>
        <form onSubmit={form.handleSubmit((v) => accept.mutate(v))} noValidate className="grid gap-4">
          {accept.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(accept.error)}</AlertDescription>
            </Alert>
          )}
          <FormField id="full_name" label="Your name" error={errors.full_name?.message}>
            <Input
              {...fieldAria("full_name", errors.full_name?.message)}
              autoComplete="name"
              autoFocus
              {...form.register("full_name")}
            />
          </FormField>
          <Button type="submit" size="lg" disabled={accept.isPending}>
            {accept.isPending ? "Joining…" : `Join ${invite.organization_name}`}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SupabaseIdentityForm({
  token,
  invite,
  onSignedIn,
}: {
  token: string;
  invite: InvitePreview;
  onSignedIn: () => void;
}) {
  const [hasAccount, setHasAccount] = useState(invite.has_account);
  const [confirmationSent, setConfirmationSent] = useState(false);
  const accept = useAcceptInvite(token);
  const schema = acceptInviteSchema(hasAccount);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", password: "" },
  });
  const { errors } = form.formState;

  const identify = useMutation({
    mutationFn: async ({ full_name, password }: z.infer<typeof schema>) => {
      const supabase = await getSupabase();
      if (!supabase) throw new Error("Sign-in is unavailable.");
      if (hasAccount) {
        const { error } = await supabase.auth.signInWithPassword({ email: invite.email, password });
        if (error) throw new Error(supabaseErrorMessage(error.message));
        return { full_name, signedIn: true };
      }
      const { data, error } = await supabase.auth.signUp({
        email: invite.email,
        password,
        options: {
          data: { full_name },
          emailRedirectTo: authRedirect("/auth/callback", `/invite/${encodeURIComponent(token)}`),
        },
      });
      if (error) throw new Error(supabaseErrorMessage(error.message));
      return { full_name, signedIn: Boolean(data.session) };
    },
    onSuccess: ({ full_name, signedIn }) => {
      if (!signedIn) return setConfirmationSent(true);
      // Signed in now: on failure fall back to the signed-in view of the invite.
      accept.mutate({ full_name }, { onError: onSignedIn });
    },
  });

  if (confirmationSent) {
    return (
      <CheckEmail
        title="Confirm your email"
        email={invite.email}
        body={`The link brings you back here to finish joining ${invite.organization_name}.`}
      />
    );
  }

  const pending = identify.isPending || accept.isPending;
  const failure = identify.error ?? accept.error;
  return (
    <Card>
      <InviteHeader invite={invite} />
      <CardContent>
        <form onSubmit={form.handleSubmit((v) => identify.mutate(v))} noValidate className="grid gap-4">
          {failure && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(failure)}</AlertDescription>
            </Alert>
          )}
          <FormField id="full_name" label="Your name" error={errors.full_name?.message}>
            <Input
              {...fieldAria("full_name", errors.full_name?.message)}
              autoComplete="name"
              autoFocus
              {...form.register("full_name")}
            />
          </FormField>
          <FormField
            id="password"
            label={hasAccount ? "Your password" : "Choose a password"}
            hint={hasAccount ? `Sign in as ${invite.email}.` : "At least 10 characters."}
            error={errors.password?.message}
          >
            <Input
              {...fieldAria("password", errors.password?.message)}
              type="password"
              autoComplete={hasAccount ? "current-password" : "new-password"}
              {...form.register("password")}
            />
          </FormField>
          <Button type="submit" size="lg" disabled={pending}>
            {pending ? "Joining…" : `Join ${invite.organization_name}`}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {hasAccount ? "New to ContentPulse?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => {
                setHasAccount(!hasAccount);
                form.clearErrors();
                identify.reset();
              }}
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              {hasAccount ? "Create a password instead" : "Sign in instead"}
            </button>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

function AcceptForm({ token, invite }: { token: string; invite: InvitePreview }) {
  const schema = acceptInviteSchema(invite.has_account);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", password: "" },
  });
  const { errors } = form.formState;

  const accept = useAcceptInvite(token);

  return (
    <Card>
      <InviteHeader invite={invite} />
      <CardContent>
        <form onSubmit={form.handleSubmit((v) => accept.mutate(v))} noValidate className="grid gap-4">
          {accept.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(accept.error)}</AlertDescription>
            </Alert>
          )}
          <FormField id="full_name" label="Your name" error={errors.full_name?.message}>
            <Input
              {...fieldAria("full_name", errors.full_name?.message)}
              autoComplete="name"
              autoFocus
              {...form.register("full_name")}
            />
          </FormField>
          <FormField
            id="password"
            label={invite.has_account ? "Your current password" : "Choose a password"}
            hint={
              invite.has_account
                ? "You already have an account. Confirm it's you."
                : "At least 10 characters."
            }
            error={errors.password?.message}
          >
            <Input
              {...fieldAria("password", errors.password?.message)}
              type="password"
              autoComplete={invite.has_account ? "current-password" : "new-password"}
              {...form.register("password")}
            />
          </FormField>
          <Button type="submit" size="lg" disabled={accept.isPending}>
            {accept.isPending ? "Joining…" : `Join ${invite.organization_name}`}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
