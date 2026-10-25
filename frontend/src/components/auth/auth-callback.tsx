"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { api, errorMessage, setActiveOrgId } from "@/lib/api";
import { meQueryKey } from "@/lib/auth";
import { getSupabase, safeNext, supabaseErrorMessage } from "@/lib/supabase";
import type { Me } from "@/types/api";

/**
 * Landing page for Supabase email links (sign-up confirmation, password reset).
 * The Supabase client exchanges the ?code= on initialization (PKCE); we wait
 * for that, provision the ContentPulse user, then continue to `next`.
 */
export function AuthCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(
    searchParams.get("error_description"),
  );

  useEffect(() => {
    if (error) return;
    let cancelled = false;
    (async () => {
      const supabase = await getSupabase();
      if (!supabase)
        throw new Error(
          "Email sign-in links aren't enabled for this workspace.",
        );
      const { error: initError } = await supabase.auth.initialize();
      if (initError) throw new Error(supabaseErrorMessage(initError.message));
      const { data } = await supabase.auth.getSession();
      if (!data.session)
        throw new Error("This link is invalid or has already been used.");
      const me = await api<Me>("/auth/me");
      if (cancelled) return;
      setActiveOrgId(me.organization_id);
      queryClient.setQueryData(meQueryKey, me);
      const fallback = me.organization_id ? "/dashboard" : "/onboarding";
      router.replace(safeNext(searchParams.get("next"), fallback));
    })().catch((e) => {
      if (!cancelled) setError(errorMessage(e));
    });
    return () => {
      cancelled = true;
    };
  }, [error, queryClient, router, searchParams]);

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            We couldn&apos;t sign you in
          </CardTitle>
          <CardDescription role="alert">
            {error} Links only work once and in the browser where you started.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/login" className={buttonVariants({ size: "lg" })}>
            Go to sign in
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card aria-busy="true" role="status">
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Signing you in…
        </CardTitle>
        <Skeleton className="h-4 w-2/3" />
      </CardHeader>
    </Card>
  );
}
