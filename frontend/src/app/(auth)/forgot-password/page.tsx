"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { AuthCaptcha } from "@/components/auth/captcha";
import { CheckEmail } from "@/components/auth/check-email";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";
import { useAuthConfig } from "@/lib/auth";
import {
  authRedirect,
  getAuthConfig,
  getSupabase,
  supabaseErrorMessage,
} from "@/lib/supabase";
import {
  type ForgotPasswordValues,
  forgotPasswordSchema,
} from "@/schemas/auth";

export default function ForgotPasswordPage() {
  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });
  const { errors } = form.formState;

  const config = useAuthConfig();
  // A CAPTCHA token works once: a new widget (new key) is needed after each attempt.
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaKey, setCaptchaKey] = useState(0);
  const send = useMutation({
    mutationFn: async ({ email }: ForgotPasswordValues) => {
      const supabase = await getSupabase();
      if (supabase) {
        if (!captchaToken) throw new Error("Complete the CAPTCHA challenge.");
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: authRedirect("/auth/callback", "/auth/reset"),
          captchaToken,
        });
        if (error) throw new Error(supabaseErrorMessage(error.message));
        return email;
      }
      const config = await getAuthConfig();
      if (!config.password_reset) {
        throw new Error(
          "Reset emails aren't set up on this server yet. Ask whoever runs ContentPulse for your team to help you get back in.",
        );
      }
      await api("/auth/password-reset", { method: "POST", body: { email } });
      return email;
    },
    onSettled: () => {
      setCaptchaToken(null);
      setCaptchaKey((k) => k + 1);
    },
  });

  // Local sign-in without SMTP: say so up front instead of failing on submit.
  if (config.data && !config.data.password_reset) {
    return (
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            Reset your password
          </CardTitle>
          <CardDescription>
            Reset emails aren&apos;t set up on this server yet. Ask whoever runs
            ContentPulse for your team to help you get back in.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            href="/login"
            className={buttonVariants({ size: "lg", className: "w-full" })}
          >
            Back to sign in
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (send.isSuccess) {
    return (
      <CheckEmail
        title="Check your email"
        email={send.data}
        body="If that email has an account, the link in it lets you choose a new password."
        onUseDifferentEmail={() => send.reset()}
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Reset your password
        </CardTitle>
        <CardDescription>
          Enter your email and we&apos;ll send you a link to choose a new one.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={form.handleSubmit((v) => send.mutate(v))}
          noValidate
          className="grid gap-4"
        >
          {send.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(send.error)}</AlertDescription>
            </Alert>
          )}
          <FormField id="email" label="Email" error={errors.email?.message}>
            <Input
              {...fieldAria("email", errors.email?.message)}
              type="email"
              autoComplete="email"
              autoFocus
              {...form.register("email")}
            />
          </FormField>
          <AuthCaptcha key={captchaKey} onToken={setCaptchaToken} />
          <Button type="submit" size="lg" disabled={send.isPending} pending={send.isPending}>
            {send.isPending ? "Sending…" : "Send reset link"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Remembered it?{" "}
            <Link
              href="/login"
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
