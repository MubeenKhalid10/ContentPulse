"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { CheckEmail } from "@/components/auth/check-email";
import { AuthCaptcha } from "@/components/auth/captcha";
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
import { PasswordInput } from "@/components/auth/password-input";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api";
import { useRegister } from "@/lib/auth";
import { type RegisterValues, registerSchema } from "@/schemas/auth";

export default function RegisterPage() {
  const router = useRouter();
  const register = useRegister();
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  // A CAPTCHA token works once: show a fresh challenge after a failed attempt.
  const [captchaKey, setCaptchaKey] = useState(0);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: "", email: "", password: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) =>
    register.mutate({ ...values, captchaToken: captchaToken ?? undefined }, {
      onSuccess: ({ needsConfirmation }) => {
        if (needsConfirmation) setSentTo(values.email);
        else router.replace("/onboarding");
      },
      onError: (error) => {
        setCaptchaToken(null);
        setCaptchaKey((k) => k + 1);
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
        onUseDifferentEmail={() => setSentTo(null)}
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
          You&apos;ll set up your organization next. If a teammate invited you,
          open the invitation link they sent you instead. It joins you to their
          organization.
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
                  {/already|registered|exists/i.test(errorMessage(register.error)) && (
                    <>
                      {" "}
                      <Link href="/login" className="font-medium underline underline-offset-4">
                        Sign in instead
                      </Link>
                    </>
                  )}
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
            <PasswordInput
              {...fieldAria("password", errors.password?.message)}
              autoComplete="new-password"
              {...form.register("password")}
            />
          </FormField>
          <AuthCaptcha key={captchaKey} onToken={setCaptchaToken} />
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
