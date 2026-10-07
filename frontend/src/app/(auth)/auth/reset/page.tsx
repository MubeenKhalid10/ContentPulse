"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { getSupabase, supabaseErrorMessage } from "@/lib/supabase";
import { type ResetPasswordValues, resetPasswordSchema } from "@/schemas/auth";

/** Reached through /auth/callback from a reset email, so a recovery session exists. */
export default function ResetPasswordPage() {
  const router = useRouter();
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });
  const { errors } = form.formState;

  const update = useMutation({
    mutationFn: async ({ password }: ResetPasswordValues) => {
      const supabase = await getSupabase();
      if (!supabase) throw new Error("Password reset isn't available.");
      const { data } = await supabase.auth.getSession();
      if (!data.session) throw new Error("Your reset link has expired. Request a new one.");
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw new Error(supabaseErrorMessage(error.message));
    },
    onSuccess: () => router.replace("/dashboard"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle role="heading" aria-level={1} className="text-xl">Choose a new password</CardTitle>
        <CardDescription>You&apos;ll stay signed in on this device.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit((v) => update.mutate(v))} noValidate className="grid gap-4">
          {update.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(update.error)}</AlertDescription>
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
          <Button type="submit" size="lg" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
