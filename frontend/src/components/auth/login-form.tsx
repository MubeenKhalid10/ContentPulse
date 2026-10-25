"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { useState } from "react";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { AuthCaptcha } from "@/components/auth/captcha";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PasswordInput } from "@/components/auth/password-input";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { useAuthConfig, useLogin } from "@/lib/auth";
import { safeNext } from "@/lib/supabase";
import { type LoginValues, loginSchema } from "@/schemas/auth";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  // A CAPTCHA token works once: show a fresh challenge after a failed attempt.
  const [captchaKey, setCaptchaKey] = useState(0);
  // Supabase sends its own reset emails; local mode needs SMTP on the server.
  const authConfig = useAuthConfig();
  const canReset = authConfig.data?.password_reset === true;
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) =>
    login.mutate({ ...values, captchaToken: captchaToken ?? undefined }, {
      onError: () => {
        setCaptchaToken(null);
        setCaptchaKey((k) => k + 1);
      },
      onSuccess: ({ user }) => {
        router.replace(
          user.organization_id
            ? safeNext(searchParams.get("next"))
            : "/onboarding",
        );
      },
    }),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Sign in
        </CardTitle>
        <CardDescription>
          Welcome back. Pick up where your team left off.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          {login.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(login.error)}</AlertDescription>
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
          <FormField
            id="password"
            label="Password"
            error={errors.password?.message}
            action={
              canReset ? (
                <Link
                  href="/forgot-password"
                  className="inline-flex min-h-8 items-center text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  Forgot password?
                </Link>
              ) : undefined
            }
            hint={
              authConfig.data && !canReset
                ? "Password reset by email is not set up for this workspace."
                : undefined
            }
          >
            <PasswordInput
              {...fieldAria("password", errors.password?.message)}
              autoComplete="current-password"
              {...form.register("password")}
            />
          </FormField>
          <AuthCaptcha key={captchaKey} onToken={setCaptchaToken} />
          <Button type="submit" size="lg" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            New to ContentPulse?{" "}
            <Link
              href="/register"
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              Create an account
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
