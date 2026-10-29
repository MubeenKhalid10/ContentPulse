"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
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
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage, setActiveOrgId } from "@/lib/api";
import {
  meQueryKey,
  useLogout,
  useMe,
  useSwitchOrganization,
} from "@/lib/auth";
import { browserTimezone, timezoneOptions } from "@/lib/options";
import { organizationSchema } from "@/schemas/organization";
import type { Me, Organization } from "@/types/api";

type Input = z.input<typeof organizationSchema>;
type Output = z.output<typeof organizationSchema>;

export function CreateOrganization() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const logout = useLogout();
  const me = useMe();
  const switchOrganization = useSwitchOrganization();
  const existing = me.data?.memberships ?? [];
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(organizationSchema),
    defaultValues: {
      name: "",
      website_url: "",
      industry: "",
      timezone: "UTC",
      description: "",
    },
  });
  const { errors } = form.formState;

  // Browser-only: setting it during render would mismatch the server HTML.
  useEffect(() => form.setValue("timezone", browserTimezone()), [form]);

  const create = useMutation({
    mutationFn: (values: Output) =>
      api<Organization>("/organizations", { method: "POST", body: values }),
    onSuccess: async (org) => {
      setActiveOrgId(org.id);
      // Prime the session before navigating: a stale "no organization" me
      // would make the app shell bounce straight back here.
      queryClient.setQueryData(meQueryKey, await api<Me>("/auth/me"));
      await queryClient.invalidateQueries({
        predicate: (q) => q.queryKey[0] !== "auth",
      });
      router.replace("/dashboard");
    },
  });

  return (
    <div className="grid gap-4">
      {me.data?.organization_id && (
        <Link
          href="/dashboard"
          className={buttonVariants({ variant: "ghost", className: "justify-self-start" })}
        >
          Back to dashboard
        </Link>
      )}
      {existing.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Continue with an organization you already have
            </CardTitle>
            <CardDescription>
              Skip this form and open one of yours instead.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {existing.map((m) => (
              <Button
                key={m.organization_id}
                type="button"
                variant="outline"
                className="justify-start"
                onClick={() => {
                  switchOrganization(m.organization_id);
                  router.replace("/dashboard");
                }}
              >
                {m.organization_name}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={1} className="text-xl">
            Set up your organization
          </CardTitle>
          <CardDescription>
            ContentPulse uses this to judge which trends matter to you. You can
            refine everything later.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={form.handleSubmit((v) => create.mutate(v))}
            noValidate
            className="grid gap-4"
          >
            {create.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(create.error)}
                </AlertDescription>
              </Alert>
            )}
            <FormField
              id="name"
              label="Organization name"
              error={errors.name?.message}
            >
              <Input
                {...fieldAria("name", errors.name?.message)}
                autoFocus
                {...form.register("name")}
              />
            </FormField>
            <FormField
              id="website_url"
              label="Website"
              hint="Optional. You can add it to your knowledge base next, so posts only use facts it backs up."
              error={errors.website_url?.message}
            >
              <Input
                {...fieldAria("website_url", errors.website_url?.message)}
                type="url"
                placeholder="https://example.com"
                {...form.register("website_url")}
              />
            </FormField>
            <FormField
              id="industry"
              label="Industry"
              hint="Optional."
              error={errors.industry?.message}
            >
              <Input
                {...fieldAria("industry", errors.industry?.message)}
                placeholder="e.g. Software development"
                {...form.register("industry")}
              />
            </FormField>
            <FormField
              id="description"
              label="What you do"
              hint="Optional. One or two sentences, used to judge which trends fit you."
              error={errors.description?.message}
            >
              <Textarea
                {...fieldAria("description", errors.description?.message)}
                rows={3}
                placeholder="e.g. We build custom software and AI agents for finance teams."
                {...form.register("description")}
              />
            </FormField>
            <FormField
              id="timezone"
              label="Timezone"
              error={errors.timezone?.message}
            >
              <Controller
                control={form.control}
                name="timezone"
                render={({ field }) => (
                  <SimpleSelect
                    id="timezone"
                    value={field.value}
                    onChange={field.onChange}
                    options={timezoneOptions()}
                  />
                )}
              />
            </FormField>
            <Button type="submit" size="lg" disabled={create.isPending} pending={create.isPending}>
              {create.isPending ? "Creating…" : "Create organization"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="text-center text-sm text-muted-foreground">
        {me.data?.email ? `Signed in as ${me.data.email}. Not you? ` : "Not you? "}
        <button
          type="button"
          disabled={logout.isPending}
          onClick={() => logout.mutate()}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {logout.isPending ? "Signing out…" : "Sign out"}
        </button>
      </p>
    </div>
  );
}
