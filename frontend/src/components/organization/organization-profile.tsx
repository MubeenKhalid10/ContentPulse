"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormSkeleton, SaveBar } from "@/components/shared/form-skeleton";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { DangerZone } from "@/components/organization/danger-zone";
import { LogoCard } from "@/components/organization/logo-card";
import { SimpleSelect } from "@/components/shared/simple-select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useOrganization,
  useUpdateOrganization,
} from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { timezoneOptions } from "@/lib/options";
import { organizationProfileSchema } from "@/schemas/organization";
import type { Organization } from "@/types/api";

type Input = z.input<typeof organizationProfileSchema>;
type Output = z.output<typeof organizationProfileSchema>;

export function OrganizationProfile() {
  const org = useOrganization();
  const can = useCan();
  const canEdit = can("organization.write");
  const isAdmin = can("users.manage");

  return (
    <>
      <PageHeader
        title="Organization profile"
        description="Who you are and what you do. This decides which trends are relevant to you."
      />
      {!canEdit && <ReadOnlyNotice />}
      {org.data ? (
        <div className="grid gap-6">
          <ProfileForm
            key={org.data.updated_at}
            org={org.data}
            canEdit={canEdit}
          />
          <LogoCard org={org.data} canEdit={canEdit} />
          {isAdmin && <DangerZone />}
        </div>
      ) : (
        <FormSkeleton fields={5} />
      )}
    </>
  );
}

function toInput(org: Organization): Input {
  return {
    name: org.name,
    website_url: org.website_url ?? "",
    industry: org.industry ?? "",
    timezone: org.timezone,
    description: org.description ?? "",
    logo_url: org.logo_url ?? "",
  };
}

function ProfileForm({
  org,
  canEdit,
}: {
  org: Organization;
  canEdit: boolean;
}) {
  const update = useUpdateOrganization();
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(organizationProfileSchema),
    defaultValues: toInput(org),
  });
  const { errors, isDirty } = form.formState;

  const onSubmit = form.handleSubmit((values) =>
    update.mutate(values, {
      onSuccess: () => toast.success("Organization profile saved"),
      onError: (e) => toast.error(errorMessage(e)),
    }),
  );

  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={!canEdit} className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Basics</CardTitle>
            <CardDescription>
              Shown across the workspace and used in AI prompts.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <FormField id="name" label="Name" error={errors.name?.message}>
              <Input
                {...fieldAria("name", errors.name?.message)}
                {...form.register("name")}
              />
            </FormField>
            <FormField
              id="industry"
              label="Industry"
              error={errors.industry?.message}
            >
              <Input
                {...fieldAria("industry", errors.industry?.message)}
                placeholder="e.g. Software development"
                {...form.register("industry")}
              />
            </FormField>
            <FormField
              id="website_url"
              label="Website"
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
                    disabled={!canEdit}
                  />
                )}
              />
            </FormField>
            <FormField
              id="logo_url"
              label="Logo URL"
              hint="Used when no logo file is uploaded below. Also included in design briefs."
              error={errors.logo_url?.message}
              className="sm:col-span-2"
            >
              <Input
                {...fieldAria("logo_url", errors.logo_url?.message)}
                type="url"
                placeholder="https://example.com/logo.svg"
                {...form.register("logo_url")}
              />
            </FormField>
            <FormField
              id="description"
              label="What you do"
              hint="A few sentences on your business, who you serve and what makes you different."
              error={errors.description?.message}
              className="sm:col-span-2"
            >
              <Textarea
                {...fieldAria("description", errors.description?.message)}
                rows={5}
                {...form.register("description")}
              />
            </FormField>
          </CardContent>
        </Card>
      </fieldset>
      {canEdit && (
        <SaveBar
          dirty={isDirty}
          pending={update.isPending}
          onReset={() => form.reset()}
        />
      )}
    </form>
  );
}
