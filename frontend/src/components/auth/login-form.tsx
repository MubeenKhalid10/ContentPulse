"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { useAuthConfig, useLogin } from "@/lib/auth";
import { safeNext } from "@/lib/supabase";
import { type LoginValues, loginSchema } from "@/schemas/auth";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();
  // Supabase sends its own reset emails; local mode needs SMTP on the server.
  const canReset = useAuthConfig().data?.password_reset === true;
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) =>
    login.mutate(values, {
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
                  className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  Forgot password?
                </Link>
              ) : undefined
            }
          >
            <Input
              {...fieldAria("password", errors.password?.message)}
              type="password"
              autoComplete="current-password"
              {...form.register("password")}
            />
          </FormField>
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
