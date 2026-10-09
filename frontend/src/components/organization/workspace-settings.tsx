"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckIcon } from "lucide-react";
import Link from "next/link";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormSkeleton, SaveBar } from "@/components/shared/form-skeleton";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { type Option, SimpleSelect } from "@/components/shared/simple-select";
import { TagInput } from "@/components/shared/tag-input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useOrgSettings, useUpdateSettings } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import {
  FREQUENCY_OPTIONS,
  LANGUAGE_OPTIONS,
  PLATFORM_OPTIONS,
  timezoneOptions,
} from "@/lib/options";
import { cn } from "@/lib/utils";
import { settingsSchema } from "@/schemas/organization";
import type { OrganizationSettings } from "@/types/api";

/*
 * Content setup: who you write for, where you publish, and what to listen for,
 * on one page with one save. Each section has an anchor (#audience,
 * #platforms, #discovery) so other pages can link straight to it.
 */

/** Toggle-button group for multi-select over a short option list. */
export function ChoiceChips<T extends string>({
  options,
  value,
  onChange,
  disabled,
  label,
}: {
  options: Option<T>[];
  value: T[];
  onChange: (next: T[]) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            onClick={() =>
              onChange(
                selected
                  ? value.filter((v) => v !== option.value)
                  : [...value, option.value],
              )
            }
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50",
              selected
                ? "border-primary bg-primary/10 text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {selected && <CheckIcon className="size-3.5 text-primary" />}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

const setupSchema = settingsSchema.pick({
  target_markets: true,
  target_audience: true,
  content_goals: true,
  enabled_platforms: true,
  default_language: true,
  default_timezone: true,
  tracked_keywords: true,
  trend_frequency: true,
});
type Input = z.input<typeof setupSchema>;
type Output = z.output<typeof setupSchema>;

export function ContentSetup() {
  const settings = useOrgSettings();
  const canEdit = useCan()("organization.write");
  return (
    <>
      <PageHeader
        title="Content setup"
        description="Who you write for, where you publish, and what to listen for. Used to score every trend and to write every post."
      />
      {!canEdit && <ReadOnlyNotice />}
      {settings.data ? (
        <SetupForm
          key={settings.data.updated_at}
          settings={settings.data}
          canEdit={canEdit}
        />
      ) : (
        <FormSkeleton fields={6} />
      )}
    </>
  );
}

function SetupForm({
  settings,
  canEdit,
}: {
  settings: OrganizationSettings;
  canEdit: boolean;
}) {
  const update = useUpdateSettings();
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(setupSchema),
    defaultValues: {
      target_markets: settings.target_markets,
      target_audience: settings.target_audience ?? "",
      content_goals: settings.content_goals,
      enabled_platforms: settings.enabled_platforms,
      default_language: settings.default_language,
      default_timezone: settings.default_timezone,
      tracked_keywords: settings.tracked_keywords,
      trend_frequency: settings.trend_frequency,
    },
  });
  const { errors, isDirty } = form.formState;

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) =>
        update.mutate(values, {
          onSuccess: () => toast.success("Content setup saved"),
          onError: (e) => toast.error(errorMessage(e)),
        }),
      )}
    >
      <fieldset disabled={!canEdit} className="grid gap-6">
        <Card id="audience" className="scroll-mt-20">
          <CardHeader>
            <CardTitle>Audience &amp; goals</CardTitle>
            <CardDescription>
              Used to score how relevant each trend is to you.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <FormField
              id="target_markets"
              label="Target markets"
              hint="Country names or codes (USA, United Kingdom, DE), or Global. Trend sources search these markets."
            >
              <Controller
                control={form.control}
                name="target_markets"
                render={({ field }) => (
                  <TagInput
                    id="target_markets"
                    value={field.value}
                    onChange={field.onChange}
                    placeholder="Add a market"
                    disabled={!canEdit}
                  />
                )}
              />
            </FormField>
            <FormField
              id="target_audience"
              label="Target audience"
              hint="Who you want to reach, e.g. CTOs and operations leaders at mid-size companies."
              error={errors.target_audience?.message}
            >
              <Textarea
                {...fieldAria(
                  "target_audience",
                  errors.target_audience?.message,
                )}
                rows={3}
                {...form.register("target_audience")}
              />
            </FormField>
            <FormField
              id="content_goals"
              label="Content goals"
              hint="e.g. Thought leadership, lead generation, hiring."
            >
              <Controller
                control={form.control}
                name="content_goals"
                render={({ field }) => (
                  <TagInput
                    id="content_goals"
                    value={field.value}
                    onChange={field.onChange}
                    placeholder="Add a goal"
                    disabled={!canEdit}
                  />
                )}
              />
            </FormField>
          </CardContent>
        </Card>

        <Card id="platforms" className="scroll-mt-20">
          <CardHeader>
            <CardTitle>Platforms &amp; publishing</CardTitle>
            <CardDescription>
              Content is only written for the platforms you turn on. Each has
              its own rules in the{" "}
              <Link
                href="/organization/platforms"
                className="underline underline-offset-4"
              >
                Platform playbook
              </Link>
              .
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <Controller
              control={form.control}
              name="enabled_platforms"
              render={({ field }) => (
                <ChoiceChips
                  label="Platforms"
                  options={PLATFORM_OPTIONS}
                  value={field.value}
                  onChange={field.onChange}
                  disabled={!canEdit}
                />
              )}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <FormField id="default_language" label="Content language">
                <Controller
                  control={form.control}
                  name="default_language"
                  render={({ field }) => (
                    <SimpleSelect
                      id="default_language"
                      value={field.value}
                      onChange={field.onChange}
                      options={LANGUAGE_OPTIONS}
                      disabled={!canEdit}
                    />
                  )}
                />
              </FormField>
              <FormField id="default_timezone" label="Scheduling timezone">
                <Controller
                  control={form.control}
                  name="default_timezone"
                  render={({ field }) => (
                    <SimpleSelect
                      id="default_timezone"
                      value={field.value}
                      onChange={field.onChange}
                      options={timezoneOptions()}
                      disabled={!canEdit}
                    />
                  )}
                />
              </FormField>
            </div>
          </CardContent>
        </Card>

        <Card id="discovery" className="scroll-mt-20">
          <CardHeader>
            <CardTitle>Trend discovery</CardTitle>
            <CardDescription>
              What to listen for and how often. Sources, API keys, subreddits
              and RSS feeds are in{" "}
              <Link
                href="/trends/sources"
                className="underline underline-offset-4"
              >
                Trends › Sources
              </Link>
              .
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <FormField
              id="tracked_keywords"
              label="Keywords to track"
              hint="Topics you always want to hear about. Sources search for these."
            >
              <Controller
                control={form.control}
                name="tracked_keywords"
                render={({ field }) => (
                  <TagInput
                    id="tracked_keywords"
                    value={field.value}
                    onChange={field.onChange}
                    placeholder="e.g. agentic AI"
                    disabled={!canEdit}
                  />
                )}
              />
            </FormField>
            <FormField
              id="trend_frequency"
              label="How Often to Check for New Trends"
              hint="If it is set to daily, Daily runs happen at 8:00 in your organization's timezone."
              className="sm:max-w-xs"
            >
              <Controller
                control={form.control}
                name="trend_frequency"
                render={({ field }) => (
                  <SimpleSelect
                    id="trend_frequency"
                    value={field.value}
                    onChange={field.onChange}
                    options={FREQUENCY_OPTIONS}
                    disabled={!canEdit}
                  />
                )}
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
