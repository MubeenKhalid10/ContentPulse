"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, CheckCircle2Icon, MailWarningIcon } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, setActiveOrgId } from "@/lib/api";
import { meQueryKey } from "@/lib/auth";
import { getSupabase, safeNext, supabaseErrorMessage } from "@/lib/supabase";
import type { Me } from "@/types/api";

type State =
  | { kind: "checking" }
  /** Confirmed and signed in on this browser. */
  | { kind: "confirmed"; next: string; hasOrganization: boolean }
  /** Confirmed, but the link was opened somewhere the sign-up didn't start. */
  | { kind: "confirmed-elsewhere" }
  | { kind: "failed"; message: string };

/** Supabase reports a bad link in the query string (PKCE) or in the #fragment. */
function linkError(searchParams: URLSearchParams): string | null {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const description =
    searchParams.get("error_description") ?? fragment.get("error_description");
  const code = searchParams.get("error_code") ?? fragment.get("error_code");
  if (code === "otp_expired")
    return "This confirmation link has expired. Try signing in, or create your account again.";
  return description ? supabaseErrorMessage(description.replace(/\+/g, " ")) : null;
}

/**
 * Where the confirmation email's button lands (`/auth/confirmed`). The
 * Supabase client signs the person in from the link (PKCE), then this page
 * says the address is confirmed and offers the next step.
 */
export function EmailConfirmed() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    const set = (next: State) => {
      if (!cancelled) setState(next);
    };
    (async () => {
      const failure = linkError(searchParams);
      if (failure) return set({ kind: "failed", message: failure });
      const supabase = await getSupabase();
      if (!supabase)
        return set({
          kind: "failed",
          message: "Email confirmation isn't enabled for this workspace.",
        });
      const { error } = await supabase.auth.initialize();
      if (error)
        return set({ kind: "failed", message: supabaseErrorMessage(error.message) });
      const { data } = await supabase.auth.getSession();
      // No session: the link was opened in a different browser or app than the
      // one that signed up. The address is still confirmed, so say so.
      if (!data.session) return set({ kind: "confirmed-elsewhere" });
      const me = await api<Me>("/auth/me");
      if (cancelled) return;
      setActiveOrgId(me.organization_id);
      queryClient.setQueryData(meQueryKey, me);
      const hasOrganization = Boolean(me.organization_id);
      set({
        kind: "confirmed",
        hasOrganization,
        next: safeNext(searchParams.get("next"), hasOrganization ? "/dashboard" : "/onboarding"),
      });
    })().catch((e) =>
      set({
        kind: "failed",
        message: e instanceof Error ? e.message : "Something went wrong.",
      }),
    );
    return () => {
      cancelled = true;
    };
  }, [queryClient, searchParams]);

  if (state.kind === "checking") {
    return (
      <Card aria-busy="true" role="status">
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            Confirming your email…
          </CardTitle>
          <Skeleton className="h-4 w-2/3" />
        </CardHeader>
      </Card>
    );
  }

  if (state.kind === "failed") {
    return (
      <Card>
        <CardHeader>
          <MailWarningIcon className="mb-2 size-6 text-destructive" aria-hidden />
          <CardTitle role="heading" aria-level={1} className="text-xl">
            We couldn&apos;t confirm your email
          </CardTitle>
          <CardDescription role="alert">{state.message}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm text-muted-foreground">
          <p>
            Confirmation links work once. If you already used this one, your email is
            confirmed and you can sign in.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href="/login" className={buttonVariants()}>
              Go to sign in
            </Link>
            <Link href="/register" className={buttonVariants({ variant: "outline" })}>
              Create an account
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  const signedIn = state.kind === "confirmed";
  const isInvite = signedIn && state.next.startsWith("/invite/");
  return (
    <Card>
      <CardHeader>
        <CheckCircle2Icon className="mb-2 size-7 text-success" aria-hidden />
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Your email is confirmed
        </CardTitle>
        <CardDescription>
          {signedIn
            ? "Thanks for confirming. Your ContentPulse account is ready and you're signed in."
            : "Thanks for confirming. Sign in on this device to start using ContentPulse."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {signedIn && !state.hasOrganization && !isInvite && (
          <p className="text-sm text-muted-foreground">
            Next, tell us about your organization. It takes about a minute and lets
            ContentPulse pick trends that fit your business.
          </p>
        )}
        {signedIn ? (
          <Link href={state.next} className={buttonVariants({ size: "lg" })}>
            {isInvite
              ? "Continue to your invitation"
              : state.hasOrganization
                ? "Continue to ContentPulse"
                : "Set up your organization"}
            <ArrowRightIcon />
          </Link>
        ) : (
          <Link href="/login" className={buttonVariants({ size: "lg" })}>
            Go to sign in
            <ArrowRightIcon />
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
