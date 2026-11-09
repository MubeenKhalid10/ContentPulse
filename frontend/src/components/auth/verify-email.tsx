"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, CheckCircle2Icon, MailWarningIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api";
import { meQueryKey } from "@/lib/auth";

/**
 * Where the confirmation email's button lands (local sign-in mode). The token
 * travels in the URL fragment (#token=…), which browsers never send to servers,
 * and is removed from the address bar once read. No sign-in is needed: the link
 * may be opened on another device.
 */
export function VerifyEmail() {
  // False while rendering on the server (the fragment isn't visible there).
  const inBrowser = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const [token] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
  });
  const queryClient = useQueryClient();
  const started = useRef(false);
  const verify = useMutation({
    mutationFn: () => api("/auth/email/verify", { method: "POST", body: { token } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  });

  useEffect(() => {
    if (window.location.hash || window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    if (token && !started.current) {
      started.current = true;
      verify.mutate();
    }
  }, [token, verify]);

  if (!inBrowser || (token && !verify.isError && !verify.isSuccess)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            Confirming your email…
          </CardTitle>
        </CardHeader>
      </Card>
    );
  }

  if (verify.isSuccess) {
    return (
      <Card>
        <CardHeader>
          <CheckCircle2Icon className="mb-2 size-7 text-success" aria-hidden />
          <CardTitle role="heading" aria-level={1} className="text-xl">
            Email confirmed
          </CardTitle>
          <CardDescription>
            Thanks, your address is confirmed. Sign in if you aren&apos;t already, then set
            up your organization.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/onboarding" className={buttonVariants({ size: "lg", className: "w-full" })}>
            Continue
            <ArrowRightIcon aria-hidden />
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <MailWarningIcon className="mb-2 size-7 text-destructive" aria-hidden />
        <CardTitle role="heading" aria-level={1} className="text-xl">
          This link didn&apos;t work
        </CardTitle>
        <CardDescription>
          It may have expired or already been replaced by a newer one.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {verify.isError && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(verify.error)}</AlertDescription>
          </Alert>
        )}
        <Link href="/login" className={buttonVariants({ size: "lg", className: "w-full" })}>
          Sign in to get a new link
        </Link>
      </CardContent>
    </Card>
  );
}
