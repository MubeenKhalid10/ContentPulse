"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api";
import { meQueryKey, useLogout } from "@/lib/auth";

/** Shown instead of the organization form until a local account confirms its email. */
export function VerifyEmailNotice({ email }: { email: string }) {
  const queryClient = useQueryClient();
  const logout = useLogout();
  const resend = useMutation({
    mutationFn: () => api("/auth/email/resend", { method: "POST" }),
  });
  const refresh = useMutation({
    mutationFn: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  });

  return (
    <Card>
      <CardHeader>
        <MailCheck className="mb-2 size-6 text-primary" aria-hidden />
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Confirm your email
        </CardTitle>
        <CardDescription>
          We sent a link to{" "}
          <span className="font-medium text-foreground">{email}</span>. Open it to
          continue; you&apos;ll set up your organization right after.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {resend.isError && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(resend.error)}</AlertDescription>
          </Alert>
        )}
        {resend.isSuccess && (
          <p role="status" className="text-sm text-muted-foreground">
            A new link is on its way. Check your spam folder if it doesn&apos;t arrive.
          </p>
        )}
        <Button
          size="lg"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          pending={refresh.isPending}
        >
          I&apos;ve confirmed it
        </Button>
        <Button
          variant="outline"
          onClick={() => resend.mutate()}
          disabled={resend.isPending}
          pending={resend.isPending}
        >
          Send the email again
        </Button>
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="text-center text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Sign out
        </button>
      </CardContent>
    </Card>
  );
}
