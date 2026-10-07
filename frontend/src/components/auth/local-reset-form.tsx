"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";
import { type ResetPasswordValues, resetPasswordSchema } from "@/schemas/auth";

/** Reached from the reset email in local sign-in mode (?token=…). */
export function LocalResetForm() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const queryClient = useQueryClient();
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });
  const { errors } = form.formState;

  const reset = useMutation({
    mutationFn: ({ password }: ResetPasswordValues) =>
      api("/auth/password-reset/confirm", { method: "POST", body: { token, password } }),
    onSuccess: () => {
      // Drop anything cached from before the new session.
      queryClient.clear();
      router.replace("/dashboard");
    },
  });

  if (!token) {
    return (
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            This link is incomplete
          </CardTitle>
          <CardDescription>Open the link from your email again, or ask for a new one.</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/forgot-password" className={buttonVariants({ size: "lg", className: "w-full" })}>
            Get a new link
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Choose a new password
        </CardTitle>
        <CardDescription>You&apos;ll be signed in on this device afterwards.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit((v) => reset.mutate(v))} noValidate className="grid gap-4">
          {reset.isError && (
            <Alert variant="destructive">
              <AlertDescription>
                {errorMessage(reset.error)}{" "}
                <Link href="/forgot-password" className="font-medium underline underline-offset-4">
                  Get a new link
                </Link>
              </AlertDescription>
            </Alert>
          )}
          <FormField id="password" label="New password" hint="At least 10 characters." error={errors.password?.message}>
            <Input
              {...fieldAria("password", errors.password?.message)}
              type="password"
              autoComplete="new-password"
              autoFocus
              {...form.register("password")}
            />
          </FormField>
          <FormField id="confirm" label="Confirm password" error={errors.confirm?.message}>
            <Input
              {...fieldAria("confirm", errors.confirm?.message)}
              type="password"
              autoComplete="new-password"
              {...form.register("confirm")}
            />
          </FormField>
          <Button type="submit" size="lg" disabled={reset.isPending}>
            {reset.isPending ? "Saving…" : "Save password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
