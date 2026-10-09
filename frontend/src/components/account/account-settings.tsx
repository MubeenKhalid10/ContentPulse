"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckIcon,
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  SunIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Tag } from "@/components/shared/tag";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { FormSkeleton } from "@/components/shared/form-skeleton";
import { PageHeader } from "@/components/shared/page-header";
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
import {
  meQueryKey,
  useAuthConfig,
  useLogout,
  useMe,
  useSwitchOrganization,
} from "@/lib/auth";
import { roleLabel } from "@/lib/options";
import { getSupabase, supabaseErrorMessage } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import type { Me } from "@/types/api";

/** Settings: you, not the workspace. Your details, password, theme and workspaces. */
export function AccountSettings() {
  const me = useMe();
  return (
    <>
      <PageHeader
        title="Settings"
        description="Your own account and preferences. Workspace settings live under Organization."
      />
      {me.data ? (
        <div className="grid gap-6">
          <ProfileCard me={me.data} />
          <PasswordCard />
          <AppearanceCard />
          <WorkspacesCard me={me.data} />
          <SessionCard />
        </div>
      ) : (
        <FormSkeleton fields={4} />
      )}
    </>
  );
}

// --- Profile ---------------------------------------------------------------------

const profileSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
});

function ProfileCard({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const form = useForm<
    z.input<typeof profileSchema>,
    unknown,
    z.output<typeof profileSchema>
  >({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: me.name ?? "" },
  });
  const { errors, isDirty } = form.formState;
  const save = useMutation({
    mutationFn: (body: z.output<typeof profileSchema>) =>
      api<Me>("/auth/me", { method: "PATCH", body }),
    onSuccess: (updated) => {
      queryClient.setQueryData(meQueryKey, updated);
      form.reset({ full_name: updated.name ?? "" });
      toast.success("Your name was saved");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const workspace = me.memberships.find(
    (m) => m.organization_id === me.organization_id,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your profile</CardTitle>
        <CardDescription>
          Shown to your team on posts, comments and approvals.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          onSubmit={form.handleSubmit((v) => save.mutate(v))}
          className="grid gap-5 sm:grid-cols-2"
        >
          <FormField
            id="full_name"
            label="Name"
            error={errors.full_name?.message}
          >
            <Input
              {...fieldAria("full_name", errors.full_name?.message)}
              autoComplete="name"
              {...form.register("full_name")}
            />
          </FormField>
          <FormField
            id="email"
            label="Email"
            hint="Your sign-in address. It can't be changed here."
          >
            <Input
              id="email"
              value={me.email}
              readOnly
              className="bg-muted/50"
            />
          </FormField>
          {workspace && me.role && (
            <p className="text-sm text-muted-foreground sm:col-span-2">
              In{" "}
              <span className="font-medium text-foreground">
                {workspace.organization_name}
              </span>{" "}
              you&apos;re {/^[aeiou]/i.test(roleLabel(me.role)) ? "an" : "a"}{" "}
              <span className="font-medium text-foreground">
                {roleLabel(me.role)}
              </span>
              .
            </p>
          )}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button
              type="button"
              variant="ghost"
              disabled={!isDirty || save.isPending}
              onClick={() => form.reset()}
            >
              Discard
            </Button>
            <Button type="submit" disabled={!isDirty || save.isPending}>
              {save.isPending ? "Saving…" : "Save name"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// --- Password --------------------------------------------------------------------

const newPassword = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(128, "Use at most 128 characters.");

const localPasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: newPassword,
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match.",
  });

function PasswordCard() {
  const config = useAuthConfig();
  if (!config.data) return null;
  return <PasswordForm supabaseMode={config.data.provider === "supabase"} />;
}

function PasswordForm({ supabaseMode }: { supabaseMode: boolean }) {
  const form = useForm<z.infer<typeof localPasswordSchema>>({
    resolver: zodResolver(localPasswordSchema),
    // Supabase sign-in has no current-password step: a placeholder satisfies the schema.
    defaultValues: {
      current_password: supabaseMode ? "-" : "",
      new_password: "",
      confirm: "",
    },
  });
  const { errors } = form.formState;
  const change = useMutation({
    mutationFn: async (v: z.infer<typeof localPasswordSchema>) => {
      if (supabaseMode) {
        const supabase = await getSupabase();
        if (!supabase)
          throw new Error("Password changes aren't available right now.");
        const { error } = await supabase.auth.updateUser({
          password: v.new_password,
        });
        if (error) throw new Error(supabaseErrorMessage(error.message));
        return;
      }
      await api<void>("/auth/password", {
        method: "POST",
        body: {
          current_password: v.current_password,
          new_password: v.new_password,
        },
      });
    },
    onSuccess: () => {
      form.reset({
        current_password: supabaseMode ? "-" : "",
        new_password: "",
        confirm: "",
      });
      toast.success("Password changed");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>
          Use at least 10 characters. You stay signed in on this device.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          onSubmit={form.handleSubmit((v) => change.mutate(v))}
          className="grid gap-5 sm:grid-cols-3"
        >
          {!supabaseMode && (
            <FormField
              id="current_password"
              label="Current password"
              error={errors.current_password?.message}
            >
              <Input
                {...fieldAria(
                  "current_password",
                  errors.current_password?.message,
                )}
                type="password"
                autoComplete="current-password"
                {...form.register("current_password")}
              />
            </FormField>
          )}
          <FormField
            id="new_password"
            label="New password"
            error={errors.new_password?.message}
          >
            <Input
              {...fieldAria("new_password", errors.new_password?.message)}
              type="password"
              autoComplete="new-password"
              {...form.register("new_password")}
            />
          </FormField>
          <FormField
            id="confirm"
            label="Confirm new password"
            error={errors.confirm?.message}
          >
            <Input
              {...fieldAria("confirm", errors.confirm?.message)}
              type="password"
              autoComplete="new-password"
              {...form.register("confirm")}
            />
          </FormField>
          <div className="flex justify-end sm:col-span-3">
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? "Changing…" : "Change password"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// --- Appearance ------------------------------------------------------------------

const THEMES = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "Match my device", icon: MonitorIcon },
] as const;

function AppearanceCard() {
  const { theme, setTheme } = useTheme();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Saved on this device.</CardDescription>
      </CardHeader>
      <CardContent>
        <div
          role="radiogroup"
          aria-label="Theme"
          className="flex flex-wrap gap-2"
        >
          {THEMES.map(({ value, label, icon: Icon }) => {
            const selected = theme === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setTheme(value)}
                className={cn(
                  "inline-flex h-10 items-center gap-2 rounded-lg border px-4 text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  selected
                    ? "border-foreground bg-foreground text-background"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
                {selected && <CheckIcon className="size-4" aria-hidden />}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// --- Workspaces ------------------------------------------------------------------

function WorkspacesCard({ me }: { me: Me }) {
  const router = useRouter();
  const switchOrganization = useSwitchOrganization();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your workspaces</CardTitle>
        <CardDescription>
          One workspace per client. Your role can differ in each.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ul className="divide-y rounded-lg border" aria-label="Your workspaces">
          {me.memberships.map((m) => {
            const current = m.organization_id === me.organization_id;
            return (
              <li
                key={m.organization_id}
                className="flex flex-wrap items-center gap-3 px-3 py-2.5"
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {m.organization_name}
                </span>
                <Tag tone="neutral">{roleLabel(m.role)}</Tag>
                {current ? (
                  <Tag tone="green" dot>
                    Current
                  </Tag>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      switchOrganization(m.organization_id);
                      router.push("/dashboard");
                    }}
                  >
                    Switch
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
        <Link
          href="/onboarding"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "justify-self-start",
          )}
        >
          <PlusIcon /> New workspace
        </Link>
      </CardContent>
    </Card>
  );
}

// --- Session ---------------------------------------------------------------------

function SessionCard() {
  const logout = useLogout();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign out</CardTitle>
        <CardDescription>Ends your session on this device.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          type="button"
          variant="outline"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          <LogOutIcon /> Sign out
        </Button>
      </CardContent>
    </Card>
  );
}
