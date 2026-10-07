"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Controller, useForm } from "react-hook-form";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { FormSkeleton, SaveBar } from "@/components/shared/form-skeleton";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { type Option, SimpleSelect } from "@/components/shared/simple-select";
import { TagInput } from "@/components/shared/tag-input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteOrganization,
  useOrgSettings,
  useUpdateSettings,
} from "@/hooks/use-organization";
import { errorMessage, setActiveOrgId } from "@/lib/api";
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
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useQueryClient } from "@tanstack/react-query";

type Input = z.input<typeof settingsSchema>;
type Output = z.output<typeof settingsSchema>;

export function SettingsEditor() {
  const settings = useOrgSettings();
  const can = useCan();
  const canEdit = can("organization.write");
  const isAdmin = can("users.manage");
  return (
    <>
      <PageHeader
        title="Settings"
        description="Where to look for trends, who you're talking to, and where you publish."
      />
      {!canEdit && <ReadOnlyNotice />}
      {settings.data ? (
        <SettingsForm
          key={settings.data.updated_at}
          settings={settings.data}
          canEdit={canEdit}
          isAdmin={isAdmin}
        />
      ) : (
        <FormSkeleton fields={6} />
      )}
    </>
  );
}

/** Toggle-button group for multi-select over a short option list. */
function ChoiceChips<T extends string>({
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
              onChange(selected ? value.filter((v) => v !== option.value) : [...value, option.value])
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

function SettingsForm({
  settings,
  canEdit,
  isAdmin,
}: {
  settings: OrganizationSettings;
  canEdit: boolean;
  isAdmin: boolean;
}) {
  const update = useUpdateSettings();
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      default_language: settings.default_language,
      default_timezone: settings.default_timezone,
      target_markets: settings.target_markets,
      target_audience: settings.target_audience ?? "",
      content_goals: settings.content_goals,
      enabled_platforms: settings.enabled_platforms,
      tracked_keywords: settings.tracked_keywords,
      subreddits: settings.subreddits,
      rss_feeds: settings.rss_feeds,
      trend_frequency: settings.trend_frequency,
    },
  });
  const { errors, isDirty } = form.formState;

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) =>
        update.mutate(values, {
          onSuccess: () => toast.success("Settings saved"),
          onError: (e) => toast.error(errorMessage(e)),
        }),
      )}
    >
      <fieldset disabled={!canEdit} className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Audience &amp; goals</CardTitle>
            <CardDescription>Used to score how relevant each trend is to you.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <FormField
              id="target_markets"
              label="Target markets"
              hint="Country names or codes (USA, United Kingdom, DE), or Global."
            >
              <Controller
                control={form.control}
                name="target_markets"
                render={({ field }) => (
                  <TagInput id="target_markets" value={field.value} onChange={field.onChange} placeholder="Add a market" disabled={!canEdit} />
                )}
              />
            </FormField>
            <FormField
              id="target_audience"
              label="Target audience"
              hint="Who you want to reach, e.g. CTOs and operations leaders at mid-size companies."
              error={errors.target_audience?.message}
            >
              <Textarea {...fieldAria("target_audience", errors.target_audience?.message)} rows={3} {...form.register("target_audience")} />
            </FormField>
            <FormField id="content_goals" label="Content goals" hint="e.g. Thought leadership, lead generation, hiring.">
              <Controller
                control={form.control}
                name="content_goals"
                render={({ field }) => (
                  <TagInput id="content_goals" value={field.value} onChange={field.onChange} placeholder="Add a goal" disabled={!canEdit} />
                )}
              />
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Platforms</CardTitle>
            <CardDescription>Where you publish. Content is only generated for these.</CardDescription>
          </CardHeader>
          <CardContent>
            <Controller
              control={form.control}
              name="enabled_platforms"
              render={({ field }) => (
                <ChoiceChips label="Platforms" options={PLATFORM_OPTIONS} value={field.value} onChange={field.onChange} disabled={!canEdit} />
              )}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Trend discovery</CardTitle>
            <CardDescription>
              Sources and keywords to watch. Collection starts once trend discovery is enabled.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <p className="text-sm text-muted-foreground">
              Choose which sources to use, and see which need API keys, in{" "}
              <Link href="/trends/sources" className="font-medium text-foreground underline underline-offset-4">
                Trends › Sources
              </Link>
              .
            </p>
            <FormField id="tracked_keywords" label="Keywords to track" hint="Topics you always want to hear about.">
              <Controller
                control={form.control}
                name="tracked_keywords"
                render={({ field }) => (
                  <TagInput id="tracked_keywords" value={field.value} onChange={field.onChange} placeholder="e.g. agentic AI" disabled={!canEdit} />
                )}
              />
            </FormField>
            <div className="grid gap-5 sm:grid-cols-2">
              <FormField
                id="subreddits"
                label="Subreddits"
                hint="Communities your audience reads. Defaults to r/popular."
                error={errors.subreddits?.message ?? errors.subreddits?.find?.((e) => e)?.message}
              >
                <Controller
                  control={form.control}
                  name="subreddits"
                  render={({ field }) => (
                    <TagInput id="subreddits" value={field.value} onChange={field.onChange} placeholder="e.g. r/automation" disabled={!canEdit} />
                  )}
                />
              </FormField>
              <FormField
                id="rss_feeds"
                label="RSS feeds"
                hint="Industry blogs and trade publications (RSS or Atom URLs)."
                error={errors.rss_feeds?.message ?? errors.rss_feeds?.find?.((e) => e)?.message}
              >
                <Controller
                  control={form.control}
                  name="rss_feeds"
                  render={({ field }) => (
                    <TagInput id="rss_feeds" value={field.value} onChange={field.onChange} placeholder="https://example.com/feed" disabled={!canEdit} maxLength={2048} />
                  )}
                />
              </FormField>
            </div>
            <FormField id="trend_frequency" label="Check for new trends" hint="Daily runs happen at 8:00 in your organization's timezone." className="sm:max-w-xs">
              <Controller
                control={form.control}
                name="trend_frequency"
                render={({ field }) => (
                  <SimpleSelect id="trend_frequency" value={field.value} onChange={field.onChange} options={FREQUENCY_OPTIONS} disabled={!canEdit} />
                )}
              />
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Defaults</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <FormField id="default_language" label="Content language">
              <Controller
                control={form.control}
                name="default_language"
                render={({ field }) => (
                  <SimpleSelect id="default_language" value={field.value} onChange={field.onChange} options={LANGUAGE_OPTIONS} disabled={!canEdit} />
                )}
              />
            </FormField>
            <FormField id="default_timezone" label="Scheduling timezone">
              <Controller
                control={form.control}
                name="default_timezone"
                render={({ field }) => (
                  <SimpleSelect id="default_timezone" value={field.value} onChange={field.onChange} options={timezoneOptions()} disabled={!canEdit} />
                )}
              />
            </FormField>
          </CardContent>
        </Card>
      </fieldset>
      {canEdit && <SaveBar dirty={isDirty} pending={update.isPending} onReset={() => form.reset()} />}
      {isAdmin && <DangerZone />}
    </form>
  );
}

function DangerZone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const remove = useDeleteOrganization();
  const [open, setOpen] = useState(false);

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle>Danger zone</CardTitle>
        <CardDescription>
          Permanently remove this workspace and all of its trends, content, members, and settings.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button type="button" variant="destructive" onClick={() => setOpen(true)}>
          Delete workspace
        </Button>
      </CardContent>
      <AlertDialog open={open} onOpenChange={(next) => !remove.isPending && setOpen(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this workspace?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the workspace, its trends, gathered data, content, files,
              and team access. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: () => {
                    setActiveOrgId(null);
                    queryClient.removeQueries({ queryKey: ["org"] });
                    toast.success("Workspace deleted");
                    router.replace("/onboarding");
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              {remove.isPending ? "Deleting…" : "Delete workspace"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
