"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { CheckEmail } from "@/components/auth/check-email";
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
import { ApiError, errorMessage } from "@/lib/api";
import { useRegister } from "@/lib/auth";
import { type RegisterValues, registerSchema } from "@/schemas/auth";

export default function RegisterPage() {
  const router = useRouter();
  const register = useRegister();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: "", email: "", password: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) =>
    register.mutate(values, {
      onSuccess: ({ needsConfirmation }) => {
        if (needsConfirmation) setSentTo(values.email);
        else router.replace("/onboarding");
      },
      onError: (error) => {
        if (error instanceof ApiError) {
          for (const [field, message] of Object.entries(error.fieldErrors)) {
            form.setError(field as keyof RegisterValues, { message });
          }
        }
      },
    }),
  );

  if (sentTo) {
    return (
      <CheckEmail
        title="Confirm your email"
        email={sentTo}
        body="Click the link in it to activate your account. You'll set up your organization right after."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">
          Create your account
        </CardTitle>
        <CardDescription>
          You&apos;ll set up your organization next. Invited by a teammate? Use
          the link they sent you instead.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          {register.isError &&
            !(
              register.error instanceof ApiError &&
              register.error.status === 422
            ) && (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(register.error)}
                </AlertDescription>
              </Alert>
            )}
          <FormField
            id="full_name"
            label="Full name"
            error={errors.full_name?.message}
          >
            <Input
              {...fieldAria("full_name", errors.full_name?.message)}
              autoComplete="name"
              autoFocus
              {...form.register("full_name")}
            />
          </FormField>
          <FormField
            id="email"
            label="Work email"
            error={errors.email?.message}
          >
            <Input
              {...fieldAria("email", errors.email?.message)}
              type="email"
              autoComplete="email"
              {...form.register("email")}
            />
          </FormField>
          <FormField
            id="password"
            label="Password"
            hint="At least 10 characters."
            error={errors.password?.message}
          >
            <Input
              {...fieldAria("password", errors.password?.message)}
              type="password"
              autoComplete="new-password"
              {...form.register("password")}
            />
          </FormField>
          <Button type="submit" size="lg" disabled={register.isPending}>
            {register.isPending ? "Creating account…" : "Create account"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
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
